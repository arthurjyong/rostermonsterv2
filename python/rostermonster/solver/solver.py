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

from rostermonster.domain import IssueSeverity, NormalizedModel, ValidationIssue
from rostermonster.solver.cr_floor import compute_cr_floor
from rostermonster.solver.lahc import LahcParams, make_scoring_oracle
from rostermonster.solver.result import (
    FILL_ORDER_POLICY_MOST_CONSTRAINED_FIRST,
    STRATEGY_LAHC,
    STRATEGY_SEEDED_RANDOM_BLIND,
    CandidateSet,
    PreferenceSeedingConfig,
    SearchDiagnostics,
    TerminationBounds,
    TrialCandidate,
    UnfilledDemandEntry,
    UnsatisfiedResult,
)
from rostermonster.solver.seeds import derive_K_seeds
from rostermonster.solver.strategy import RuleEngineFn
from rostermonster.solver.strategy_registry import get_strategy

# 64-bit signed integer bounds per `docs/solver_contract.md` §9 input #3.
_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1


def _build_unsatisfied(
    *,
    failed_outcomes: list[tuple[int, int, tuple]],
    strategyId: str,
    fillOrderPolicy: str,
    crFloorMode: str,
    crFloorComputed: int,
    seed: int,
    aggregate_attempts: int,
    aggregate_rejections: dict[str, int],
    candidate_emit_count: int,
    lahc_diag_kwargs: dict | None = None,
) -> UnsatisfiedResult:
    """Build an UnsatisfiedResult from the deterministic complete union of
    per-trajectory failures per `docs/solver_contract.md` §14 + §12A.8.

    `failed_outcomes` is a list of `(trajectory_index, candidate_seed,
    unfillable)` triples in trajectory order. The resulting `unfilledDemand`
    de-duplicates byte-identical (dateKey, slotType, unitIndex) entries
    while preserving deterministic per-trajectory order; `reasons` carries
    the union of `ValidationIssue` entries with per-trajectory `seed`
    context for debugging.

    SEEDED_RANDOM_BLIND aborts on the first failure (one entry); LAHC
    aggregates all K trajectories' failures (per §12A.8 — surface every
    cause that affected any trajectory, never a "representative subset").

    Dedup discipline:
    - `unfilledDemand` IS deduped by unit (operator-facing summary —
      surfacing the same `(dateKey, slotType, unitIndex)` K times when
      every trajectory failed on it would just be noise).
    - `reasons` is NOT deduped — every (trajectory_index, unit) pair gets
      its own `ValidationIssue` so debugging can see which specific seed
      hit which specific failure (per §12A.8 "complete per-trajectory
      failure data").
    """
    seen_units: set[tuple[str, str, int]] = set()
    unfilled_list: list[UnfilledDemandEntry] = []
    reasons_list: list[ValidationIssue] = []
    for trajectory_index, candidate_seed, unfillable in failed_outcomes:
        for u in unfillable:
            key = (u.dateKey, u.slotType, u.unitIndex)
            # Always emit a reason — preserves per-trajectory debugging
            # data even when multiple trajectories collide on the same unit.
            reasons_list.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code="UNFILLABLE_DEMAND",
                    message=(
                        f"No eligible-and-rule-valid doctor for "
                        f"({u.dateKey}, {u.slotType}, unit {u.unitIndex}) "
                        f"under {strategyId} with seed={candidate_seed} "
                        f"(trajectory {trajectory_index})"
                    ),
                    context={
                        "dateKey": u.dateKey,
                        "slotType": u.slotType,
                        "unitIndex": u.unitIndex,
                        "trajectoryIndex": trajectory_index,
                        "seed": candidate_seed,
                    },
                )
            )
            # Dedupe `unfilledDemand` only — the operator-facing list shows
            # each affected unit once.
            if key in seen_units:
                continue
            seen_units.add(key)
            unfilled_list.append(
                UnfilledDemandEntry(
                    dateKey=u.dateKey,
                    slotType=u.slotType,
                    unitIndex=u.unitIndex,
                )
            )
    diagnostics = SearchDiagnostics(
        strategyId=strategyId,
        fillOrderPolicy=fillOrderPolicy,
        crFloorMode=crFloorMode,
        crFloorComputed=crFloorComputed,
        seed=seed,
        placementAttempts=aggregate_attempts,
        ruleEngineRejectionsByReason=dict(aggregate_rejections),
        candidateEmitCount=candidate_emit_count,
        unfilledDemandCount=len(unfilled_list),
        **(lahc_diag_kwargs or {}),
    )
    return UnsatisfiedResult(
        unfilledDemand=tuple(unfilled_list),
        reasons=tuple(reasons_list),
        diagnostics=diagnostics,
    )


def solve(
    normalizedModel: NormalizedModel,
    *,
    ruleEngine: RuleEngineFn,
    seed: int,
    terminationBounds: TerminationBounds,
    preferenceSeeding: PreferenceSeedingConfig | None = None,
    fillOrderPolicy: str = FILL_ORDER_POLICY_MOST_CONSTRAINED_FIRST,
    strategyId: str = STRATEGY_SEEDED_RANDOM_BLIND,
    scoringConfig=None,
    lahcParams: LahcParams | None = None,
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
    # §11.1: strategy resolution rejects unregistered ids BEFORE any §10
    # output construction begins. Registered ids dispatch through the
    # registry's `_StrategyDescriptor.run` callable per
    # docs/solver_contract.md §11.
    descriptor = get_strategy(strategyId)

    # §12A.6 + §11.2 extension clause: LAHC requires the read-only scoring
    # oracle (derived from scoringConfig) and lahcParams. SEEDED_RANDOM_BLIND
    # ignores both (it's scoring-blind end-to-end per §12). Validate at the
    # boundary so the failure mode is "fail fast in solve()" not "AttributeError
    # deep in the LAHC inner loop".
    strategy_kwargs: dict = {}
    if strategyId == STRATEGY_LAHC:
        if scoringConfig is None:
            raise ValueError(
                "scoringConfig is required when strategyId='LAHC' per "
                "docs/solver_contract.md §12A.6 (read-only scoring oracle "
                "extension clause); SEEDED_RANDOM_BLIND remains scoring-blind."
            )
        # Oracle construction is encapsulated in `lahc.py` — the only
        # solver-package module authorized to consume the scorer interface
        # per §12A.6 + §11.2 extension clause. The solver core stays
        # scoring-blind by default.
        strategy_kwargs["scoring_oracle"] = make_scoring_oracle(scoringConfig)
        strategy_kwargs["lahc_params"] = (
            lahcParams if lahcParams is not None else LahcParams()
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

    # `seed` is a 64-bit signed integer per §9. `random.Random` itself
    # accepts non-int and arbitrary-width inputs, so contract-invalid inputs
    # silently produce unexpected RNG streams unless we guard at the
    # boundary. Same isinstance-with-bool-rejection discipline as
    # `crFloor.manualValue` and `terminationBounds.maxCandidates`.
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError(
            f"seed must be a 64-bit signed integer per "
            f"docs/solver_contract.md §9; got "
            f"{type(seed).__name__}={seed!r}"
        )
    if not (_INT64_MIN <= seed <= _INT64_MAX):
        raise ValueError(
            f"seed must fit in a 64-bit signed integer per "
            f"docs/solver_contract.md §9 "
            f"({_INT64_MIN} <= seed <= {_INT64_MAX}); got {seed!r}"
        )

    seeding = preferenceSeeding if preferenceSeeding is not None else PreferenceSeedingConfig()
    cr_floor_x = compute_cr_floor(normalizedModel, seeding.crFloor)

    # K-trajectory seeds are derived via the shared `derive_K_seeds` helper
    # per `docs/solver_contract.md` §12A.10 (single source of truth across
    # the local CLI and the Cloud Run Service orchestrator). The helper
    # owns the load-bearing `_UINT64_MASK` step that prevents CPython's
    # `Random.seed(int)` `abs(...)` from aliasing contract-valid `seed` and
    # `-seed` inputs to the same RNG stream.
    candidate_seeds = derive_K_seeds(seed, terminationBounds.maxCandidates)
    candidates: list[TrialCandidate] = []
    aggregate_attempts = 0
    aggregate_rejections: dict[str, int] = {}

    # Per-strategy failure aggregation per `docs/solver_contract.md` §14
    # + §12A.8:
    # - `SEEDED_RANDOM_BLIND` (single-attempt-style — even at K candidates
    #   the K rosters come from one feasibility outcome): ANY unfillable
    #   attempt → whole-run UnsatisfiedResult. Existing pre-M6 behavior.
    # - `LAHC` (multi-trajectory K-independent attempts per §12A.2): drop
    #   per-trajectory seed-roster failures; only return UnsatisfiedResult
    #   when ALL K trajectories' seed steps fail. If at least one
    #   trajectory succeeds, emit a non-empty CandidateSet with the
    #   successful trajectories' rosters per §12A.8.
    abort_on_first_failure = strategyId != STRATEGY_LAHC

    # Track the union of all per-trajectory failures for the all-trajectories-
    # failed UnsatisfiedResult path per §12A.8 (deterministic complete
    # union; per-trajectory order preserved).
    failed_outcomes: list[tuple[int, int, tuple]] = []  # (trajectory_index, candidate_seed, unfillable)

    # LAHC-only per-trajectory diagnostics per §12A.9 — populated for every
    # outer-loop iteration regardless of success/failure so the operator can
    # reconstruct what each trajectory did. Indexed by outer-loop index.
    per_trajectory_status: list[str] = []
    per_trajectory_iters: list[int] = []
    per_trajectory_accepted: list[int] = []
    per_trajectory_best_score: list[float | None] = []
    per_trajectory_terminal_score: list[float | None] = []

    for index, candidate_seed in enumerate(candidate_seeds):
        outcome = descriptor.run(
            ruleEngine,
            normalizedModel,
            candidate_seed,
            cr_floor_x,
            **strategy_kwargs,
        )
        aggregate_attempts += outcome.attempts
        for code, count in outcome.rejection_counts.items():
            aggregate_rejections[code] = aggregate_rejections.get(code, 0) + count

        # Collect §12A.9 per-trajectory data when LAHC is active. SEEDED_RANDOM_BLIND
        # outcomes don't populate `strategy_data`, so the lists stay empty
        # for non-LAHC strategies and SearchDiagnostics gets `None` for
        # those fields.
        if strategyId == STRATEGY_LAHC:
            sd = outcome.strategy_data or {}
            if outcome.unfillable:
                per_trajectory_status.append("SEED_FAILED")
                per_trajectory_iters.append(0)
                per_trajectory_accepted.append(0)
                per_trajectory_best_score.append(None)
                per_trajectory_terminal_score.append(None)
            else:
                per_trajectory_status.append("SUCCEEDED")
                per_trajectory_iters.append(int(sd.get("iters", 0)))
                per_trajectory_accepted.append(int(sd.get("accepted_moves", 0)))
                per_trajectory_best_score.append(sd.get("best_score"))
                per_trajectory_terminal_score.append(sd.get("terminal_score"))

        if outcome.unfillable:
            failed_outcomes.append((index, candidate_seed, outcome.unfillable))
            if abort_on_first_failure:
                # SEEDED_RANDOM_BLIND any-fail-fails (§14): surface the
                # unfillable units from this candidate's attempt and abort.
                # No partial CandidateSet leaks.
                return _build_unsatisfied(
                    failed_outcomes=failed_outcomes,
                    strategyId=strategyId,
                    fillOrderPolicy=fillOrderPolicy,
                    crFloorMode=seeding.crFloor.mode,
                    crFloorComputed=cr_floor_x,
                    seed=seed,
                    aggregate_attempts=aggregate_attempts,
                    aggregate_rejections=aggregate_rejections,
                    candidate_emit_count=len(candidates),
                )
            # LAHC drop-and-continue: trajectory dropped, continue to next.
            continue

        # Successful trajectory — emit as TrialCandidate. candidateId is a
        # 1-indexed dense integer per `docs/selector_contract.md` §16.1; with
        # LAHC's drop-and-continue, len(candidates)+1 keeps the ids dense
        # across dropped trajectories.
        candidates.append(
            TrialCandidate(
                candidateId=len(candidates) + 1,
                assignments=outcome.assignments,
            )
        )

    # §12A.9 LAHC-specific diagnostic fields surface only when the active
    # strategy is LAHC; otherwise they stay `None`. Built BEFORE the
    # all-fail branch so both `_build_unsatisfied` (all-fail) and the
    # success-path diagnostics get the same LAHC fields.
    lahc_diag_kwargs: dict = {}
    if strategyId == STRATEGY_LAHC:
        lp: LahcParams = strategy_kwargs["lahc_params"]
        lahc_diag_kwargs = {
            "lahcHistoryListLength": lp.historyListLength,
            "lahcMaxIters": lp.maxIters,
            "lahcIdleThreshold": lp.idleThreshold,
            "lahcSwapProbability": lp.swapProbability,
            "seedDerivationFunction": "python.Random.getrandbits.candidate_seed",
            "perTrajectoryStatus": tuple(per_trajectory_status),
            "perTrajectoryIters": tuple(per_trajectory_iters),
            "perTrajectoryAcceptedMoves": tuple(per_trajectory_accepted),
            "perTrajectoryBestScore": tuple(per_trajectory_best_score),
            "perTrajectoryTerminalScore": tuple(per_trajectory_terminal_score),
        }

    # All K trajectories have run. Decide success vs whole-run failure.
    if not candidates:
        # All trajectories failed (LAHC: every seed step returned unfillable;
        # SEEDED_RANDOM_BLIND: would've already aborted on the first failure
        # so this branch is unreachable for SEEDED_RANDOM_BLIND).
        return _build_unsatisfied(
            failed_outcomes=failed_outcomes,
            strategyId=strategyId,
            fillOrderPolicy=fillOrderPolicy,
            crFloorMode=seeding.crFloor.mode,
            crFloorComputed=cr_floor_x,
            seed=seed,
            aggregate_attempts=aggregate_attempts,
            aggregate_rejections=aggregate_rejections,
            candidate_emit_count=0,
            lahc_diag_kwargs=lahc_diag_kwargs,
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
        **lahc_diag_kwargs,
    )
    return CandidateSet(
        candidates=tuple(candidates),
        diagnostics=diagnostics,
    )
