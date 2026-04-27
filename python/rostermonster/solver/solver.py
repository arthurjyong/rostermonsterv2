"""Pure-function solver entry per `docs/solver_contract.md`.

Public entry: `solve(normalizedModel, seed, fillOrderPolicy, terminationBounds,
preferenceSeeding) → CandidateSet | UnsatisfiedResult`.

First-release strategy is `SEEDED_RANDOM_BLIND` (§11.1, §12). The solver is
scoring-blind end-to-end (§9, §11) — it imports nothing from
`rostermonster.scorer` and never touches scoring config.

Determinism (§16): identical inputs produce byte-identical outputs within a
single implementation on a single platform. Per-candidate seeds are derived
from the run seed deterministically so multi-candidate runs vary across
candidates while remaining reproducible.
"""

from __future__ import annotations

from random import Random

from rostermonster.domain import IssueSeverity, NormalizedModel, ValidationIssue
from rostermonster.solver.cr_floor import compute_cr_floor
from rostermonster.solver.result import (
    FILL_ORDER_POLICY_MOST_CONSTRAINED_FIRST,
    STRATEGY_SEEDED_RANDOM_BLIND,
    CandidateSet,
    PreferenceSeedingConfig,
    SearchDiagnostics,
    TerminationBounds,
    TrialCandidate,
    UnfilledDemandEntry,
    UnsatisfiedResult,
)
from rostermonster.solver.strategy import run_seeded_random_blind


def _per_candidate_seed(rng: Random) -> int:
    """Derive one per-candidate seed from the run-level RNG. Using `getrandbits`
    keeps the seed inside the 64-bit signed range used by `Random()` and stays
    deterministic under the parent stream."""
    return rng.getrandbits(63)


def solve(
    normalizedModel: NormalizedModel,
    *,
    seed: int,
    terminationBounds: TerminationBounds,
    preferenceSeeding: PreferenceSeedingConfig | None = None,
    fillOrderPolicy: str = FILL_ORDER_POLICY_MOST_CONSTRAINED_FIRST,
    strategyId: str = STRATEGY_SEEDED_RANDOM_BLIND,
) -> CandidateSet | UnsatisfiedResult:
    """Run the active solver strategy for `terminationBounds.maxCandidates`
    candidates per `docs/solver_contract.md`.

    Branch discipline (§10.3): exactly one of `CandidateSet` or
    `UnsatisfiedResult` is returned. `UnsatisfiedResult` is emitted as soon
    as any candidate construction surfaces unfillable demand — partial
    candidates are NOT leaked into `CandidateSet` (§14).

    `preferenceSeeding=None` defaults to `SMART_MEDIAN` per §13.1 ("default
    mode when `preferenceSeeding` is omitted or when
    `preferenceSeeding.crFloor` is omitted").
    """
    if strategyId != STRATEGY_SEEDED_RANDOM_BLIND:
        raise ValueError(
            f"Unknown strategyId {strategyId!r}; first-release strategy set "
            f"is exactly {{ {STRATEGY_SEEDED_RANDOM_BLIND!r} }} per "
            f"docs/solver_contract.md §11.1"
        )
    if fillOrderPolicy != FILL_ORDER_POLICY_MOST_CONSTRAINED_FIRST:
        raise ValueError(
            f"Unknown fillOrderPolicy {fillOrderPolicy!r}; first-release "
            f"set is exactly {{ {FILL_ORDER_POLICY_MOST_CONSTRAINED_FIRST!r} }} "
            f"per docs/solver_contract.md §12.3"
        )
    if terminationBounds.maxCandidates <= 0:
        raise ValueError(
            f"terminationBounds.maxCandidates must be a positive integer "
            f"per docs/solver_contract.md §15; got "
            f"{terminationBounds.maxCandidates!r}"
        )

    seeding = preferenceSeeding if preferenceSeeding is not None else PreferenceSeedingConfig()
    cr_floor_x = compute_cr_floor(normalizedModel, seeding.crFloor)

    run_rng = Random(seed)
    candidates: list[TrialCandidate] = []
    aggregate_attempts = 0
    aggregate_rejections: dict[str, int] = {}

    for index in range(terminationBounds.maxCandidates):
        candidate_seed = _per_candidate_seed(run_rng)
        outcome = run_seeded_random_blind(
            normalizedModel,
            candidate_seed,
            cr_floor_x,
        )
        aggregate_attempts += outcome.attempts
        for code, count in outcome.rejection_counts.items():
            aggregate_rejections[code] = aggregate_rejections.get(code, 0) + count

        if outcome.unfillable:
            # §14 whole-run failure: surface the unfillable units from this
            # candidate's attempt and abort. No partial CandidateSet leaks.
            unfilled = tuple(
                UnfilledDemandEntry(
                    dateKey=u.dateKey,
                    slotType=u.slotType,
                    unitIndex=u.unitIndex,
                )
                for u in outcome.unfillable
            )
            reasons = tuple(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code="UNFILLABLE_DEMAND",
                    message=(
                        f"No eligible-and-rule-valid doctor for "
                        f"({u.dateKey}, {u.slotType}, unit {u.unitIndex}) "
                        f"under SEEDED_RANDOM_BLIND with seed={candidate_seed}"
                    ),
                    context={
                        "dateKey": u.dateKey,
                        "slotType": u.slotType,
                        "unitIndex": u.unitIndex,
                    },
                )
                for u in outcome.unfillable
            )
            diagnostics = SearchDiagnostics(
                strategyId=strategyId,
                fillOrderPolicy=fillOrderPolicy,
                crFloorMode=seeding.crFloor.mode,
                crFloorComputed=cr_floor_x,
                seed=seed,
                placementAttempts=aggregate_attempts,
                ruleEngineRejectionsByReason=dict(aggregate_rejections),
                candidateEmitCount=len(candidates),
                unfilledDemandCount=len(unfilled),
            )
            return UnsatisfiedResult(
                unfilledDemand=unfilled,
                reasons=reasons,
                diagnostics=diagnostics,
            )

        candidates.append(
            TrialCandidate(
                candidateId=f"c{index + 1:04d}",
                assignments=outcome.assignments,
            )
        )

    diagnostics = SearchDiagnostics(
        strategyId=strategyId,
        fillOrderPolicy=fillOrderPolicy,
        crFloorMode=seeding.crFloor.mode,
        crFloorComputed=cr_floor_x,
        seed=seed,
        placementAttempts=aggregate_attempts,
        ruleEngineRejectionsByReason=dict(aggregate_rejections),
        candidateEmitCount=len(candidates),
        unfilledDemandCount=0,
    )
    return CandidateSet(
        candidates=tuple(candidates),
        diagnostics=diagnostics,
    )
