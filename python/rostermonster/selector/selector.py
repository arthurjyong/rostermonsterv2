"""Pure-function selector entry per `docs/selector_contract.md`.

Public entry: `select(scoredCandidateSet, *, retentionMode, runEnvelope,
selectorStrategyId, selectorStrategyConfig=None, sidecarTargetDir=None)
→ FinalResultEnvelope`.

The selector is the third stage of the `solver → scorer → selector`
pipeline (D-0027). It picks a winner from a scored `CandidateSet` (or
forwards the solver's `UnsatisfiedResult` on the failure branch) and
optionally emits sidecar artifacts under `FULL` retention (§14).

Determinism (§18): identical inputs produce byte-identical
`FinalResultEnvelope` content and (under `FULL`) byte-identical sidecar
files within a single implementation on a single platform. The selector
MUST NOT consume clocks, env vars, or filesystem state; sidecar emission
is the only permitted side effect.

The selector synthesizes nothing about identity (§16.4): `runId`,
`generationTimestamp`, and the rest of `runEnvelope` are passed through
unchanged. `candidateId` ordering is honored unchanged from the solver's
emission order.
"""

from __future__ import annotations

from pathlib import Path

from rostermonster.solver import CandidateSet, UnsatisfiedResult
from rostermonster.selector.result import (
    SELECTOR_STRATEGY_HIGHEST_SCORE_WITH_CASCADE,
    AllocationResult,
    FinalResultEnvelope,
    RetentionMode,
    RunEnvelope,
    ScoredCandidateSet,
    UnsatisfiedResultEnvelope,
)
from rostermonster.selector.sidecars import write_sidecars
from rostermonster.selector.strategy import pick_highest_score_with_cascade


def select(
    scoredCandidateSet: ScoredCandidateSet | UnsatisfiedResult,
    *,
    retentionMode: RetentionMode,
    runEnvelope: RunEnvelope,
    selectorStrategyId: str = SELECTOR_STRATEGY_HIGHEST_SCORE_WITH_CASCADE,
    selectorStrategyConfig: dict | None = None,
    sidecarTargetDir: Path | None = None,
) -> FinalResultEnvelope:
    """Select the winning candidate and emit the final result envelope.

    Branch discipline (§10.3): exactly one of `AllocationResult` or
    `UnsatisfiedResultEnvelope` is in `result`. The branch is determined
    by the input shape — `ScoredCandidateSet` → success; `UnsatisfiedResult`
    → failure (§15).

    Strategy gating (§11.1): `selectorStrategyId` MUST be a registered
    first-release strategy. Unknown IDs are rejected before any §10
    output construction begins.

    `sidecarTargetDir` is required under `FULL` retention on the success
    branch (§14 sidecar files MUST be written). Filesystem placement is
    execution-layer-owned per §14.3 — the caller picks the directory.
    Under `BEST_ONLY` retention or on the failure branch, sidecar emission
    is skipped regardless of whether `sidecarTargetDir` is supplied.

    `selectorStrategyConfig` is reserved for future strategies per §11.2;
    `HIGHEST_SCORE_WITH_CASCADE` accepts and ignores it (§9 item 5
    — first-release strategy declares no required config fields).
    """
    if selectorStrategyId != SELECTOR_STRATEGY_HIGHEST_SCORE_WITH_CASCADE:
        raise ValueError(
            f"Unknown selectorStrategyId {selectorStrategyId!r}; "
            f"first-release strategy set is exactly "
            f"{{ {SELECTOR_STRATEGY_HIGHEST_SCORE_WITH_CASCADE!r} }} per "
            f"docs/selector_contract.md §11.1"
        )
    if not isinstance(retentionMode, RetentionMode):
        # Tolerate the bare string form of the value vocabulary per the
        # same `(str, Enum)` discipline applied across the solver and
        # scorer. Operators MAY pass the bare string `"FULL"` or
        # `"BEST_ONLY"` per the contract's value vocabulary.
        try:
            retentionMode = RetentionMode(retentionMode)
        except ValueError as exc:
            raise ValueError(
                f"Unknown retentionMode {retentionMode!r}; first-release "
                f"set is exactly {{ BEST_ONLY, FULL }} per "
                f"docs/selector_contract.md §13"
            ) from exc

    # --- failure branch (§15) ----------------------------------------
    if isinstance(scoredCandidateSet, UnsatisfiedResult):
        return FinalResultEnvelope(
            runEnvelope=runEnvelope,
            retentionMode=retentionMode,
            selectorStrategyId=selectorStrategyId,
            result=UnsatisfiedResultEnvelope(
                unfilledDemand=scoredCandidateSet.unfilledDemand,
                reasons=scoredCandidateSet.reasons,
                searchDiagnostics=scoredCandidateSet.diagnostics,
            ),
        )

    # --- success branch (§10.1) --------------------------------------
    if not isinstance(scoredCandidateSet, ScoredCandidateSet):
        raise TypeError(
            f"select() expected ScoredCandidateSet or UnsatisfiedResult; "
            f"got {type(scoredCandidateSet).__name__}. The solver emits "
            f"CandidateSet (unscored); the caller must score it before "
            f"passing in. See docs/selector_contract.md §9 item 1."
        )
    if not scoredCandidateSet.candidates:
        # Empty success-branch input violates `docs/solver_contract.md`
        # §10.1 (CandidateSet MUST be non-empty on success). Surface as
        # a caller defect rather than silently emitting an
        # AllocationResult with no winner.
        raise ValueError(
            "select() received an empty ScoredCandidateSet on the success "
            "branch; docs/solver_contract.md §10.1 forbids empty "
            "CandidateSet — caller upstream is the defect"
        )

    winner = pick_highest_score_with_cascade(scoredCandidateSet.candidates)

    summary_path: str | None = None
    full_path: str | None = None
    if retentionMode is RetentionMode.FULL:
        if sidecarTargetDir is None:
            raise ValueError(
                "sidecarTargetDir is required under FULL retention so the "
                "selector knows where to emit candidates_summary.csv and "
                "candidates_full.json per docs/selector_contract.md §14"
            )
        sp, fp = write_sidecars(
            Path(sidecarTargetDir),
            scoredCandidateSet.candidates,
            runEnvelope,
        )
        summary_path = str(sp)
        full_path = str(fp)

    allocation = AllocationResult(
        winnerAssignment=winner.candidate.assignments,
        winnerScore=winner.score,
        searchDiagnostics=scoredCandidateSet.diagnostics,
        # First-release SEEDED_RANDOM_BLIND does not surface batches per
        # solver §18.2; selector §17.4 says when no batches are surfaced
        # the selector has nothing to populate. Empty tuple is contract-
        # compliant.
        trialBatches=(),
        candidatesSummaryPath=summary_path,
        candidatesFullPath=full_path,
    )

    return FinalResultEnvelope(
        runEnvelope=runEnvelope,
        retentionMode=retentionMode,
        selectorStrategyId=selectorStrategyId,
        result=allocation,
    )
