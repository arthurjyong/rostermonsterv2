"""Pure-function solver entry per `docs/solver_contract.md`.

Public entry: `solve(normalizedModel, *, ruleEngine, seed, terminationBounds,
preferenceSeeding=None, fillOrderPolicy=..., strategyId=...) → CandidateSet
| UnsatisfiedResult`.

First-release strategy is `SEEDED_RANDOM_BLIND` (§11.1, §12). The solver is
scoring-blind end-to-end (§9, §11) — it imports nothing from
`rostermonster.scorer` and never touches scoring config.

`ruleEngine` is a caller-supplied handle per §9 input #2 — the solver does
not bind to any single rule-engine implementation, so callers can swap in
cached/indexed evaluators (or test doubles) behind the same surface.

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
from rostermonster.solver.strategy import RuleEngineFn, run_seeded_random_blind


def _per_candidate_seed(rng: Random) -> int:
    """Derive one per-candidate seed from the run-level RNG. Using `getrandbits`
    keeps the seed inside the 64-bit signed range used by `Random()` and stays
    deterministic under the parent stream."""
    return rng.getrandbits(63)


def solve(
    normalizedModel: NormalizedModel,
    *,
    ruleEngine: RuleEngineFn,
    seed: int,
    terminationBounds: TerminationBounds,
    preferenceSeeding: PreferenceSeedingConfig | None = None,
    fillOrderPolicy: str = FILL_ORDER_POLICY_MOST_CONSTRAINED_FIRST,
    strategyId: str = STRATEGY_SEEDED_RANDOM_BLIND,
) -> CandidateSet | UnsatisfiedResult:
    """Run the active solver strategy for `terminationBounds.maxCandidates`
    candidates per `docs/solver_contract.md`.

    `ruleEngine` is a required input per §9 input #2 — a callable
    `(NormalizedModel, RuleState, AssignmentUnit) → Decision` that adjudicates
    hard validity of any proposed placement. Callers typically pass
    `rostermonster.rule_engine.evaluate`, but the solver remains decoupled
    from any specific implementation so test fixtures (and future
    cached/indexed implementations) can be substituted at the boundary.

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
    max_candidates = terminationBounds.maxCandidates
    # `bool` is a subclass of `int` in Python; reject it explicitly so
    # `True`/`False` don't slip through as 1/0 — the §15 contract requires a
    # positive integer, and a boolean configuration value is almost
    # certainly a caller-side bug. Same discipline as `crFloor.manualValue`.
    if isinstance(max_candidates, bool) or not isinstance(max_candidates, int):
        raise ValueError(
            f"terminationBounds.maxCandidates must be a positive integer "
            f"per docs/solver_contract.md §15; got "
            f"{type(max_candidates).__name__}={max_candidates!r}"
        )
    if max_candidates <= 0:
        raise ValueError(
            f"terminationBounds.maxCandidates must be a positive integer "
            f"per docs/solver_contract.md §15; got {max_candidates!r}"
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
            ruleEngine,
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
                candidateId=index + 1,
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
