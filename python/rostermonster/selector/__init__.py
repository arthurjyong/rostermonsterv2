"""Selector module per `docs/selector_contract.md`.

Public entry: `select(scoredCandidateSet, *, retentionMode, runEnvelope,
selectorStrategyId, selectorStrategyConfig=None, sidecarTargetDir=None)
→ FinalResultEnvelope`.

Pure-function reference implementation of `HIGHEST_SCORE_WITH_CASCADE`
per §11.1 + §12. Emits sidecar artifacts (`candidates_summary.csv`,
`candidates_full.json`) under `FULL` retention per §14. Synthesizes
nothing about identity (§16.4) — `runEnvelope` rides through unchanged.
"""

from rostermonster.selector.result import (
    SELECTOR_CONTRACT_VERSION,
    SELECTOR_STRATEGY_HIGHEST_SCORE_WITH_CASCADE,
    SIDECAR_SCHEMA_VERSION,
    AllocationResult,
    FinalResultEnvelope,
    RetentionMode,
    RunEnvelope,
    ScoredCandidateSet,
    ScoredTrialCandidate,
    TrialBatchResult,
    TrialBatchScoreSummary,
    UnsatisfiedResultEnvelope,
)
from rostermonster.selector.selector import select
from rostermonster.selector.sidecars import (
    FULL_FILE_NAME,
    SUMMARY_FILE_NAME,
    write_sidecars,
)
from rostermonster.selector.strategy import pick_highest_score_with_cascade

__all__ = [
    "select",
    "pick_highest_score_with_cascade",
    "write_sidecars",
    "FinalResultEnvelope",
    "AllocationResult",
    "UnsatisfiedResultEnvelope",
    "RunEnvelope",
    "RetentionMode",
    "ScoredCandidateSet",
    "ScoredTrialCandidate",
    "TrialBatchResult",
    "TrialBatchScoreSummary",
    "SELECTOR_STRATEGY_HIGHEST_SCORE_WITH_CASCADE",
    "SELECTOR_CONTRACT_VERSION",
    "SIDECAR_SCHEMA_VERSION",
    "SUMMARY_FILE_NAME",
    "FULL_FILE_NAME",
]
