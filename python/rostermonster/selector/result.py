"""Selector result + envelope types per `docs/selector_contract.md`.

Public input/output shapes of the selector module. Mirrors the per-module
pattern (parser/, scorer/, solver/ each own their result shapes); these
types are referenced by the contract under `docs/domain_model.md` §10.3 /
§12.4 but the concrete language-level shape lives here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from rostermonster.domain import AssignmentUnit, ValidationIssue
from rostermonster.scorer import ScoreResult
from rostermonster.solver import (
    SearchDiagnostics,
    TrialCandidate,
    UnfilledDemandEntry,
)

# First-release strategy identifier per selector §11.1.
SELECTOR_STRATEGY_HIGHEST_SCORE_WITH_CASCADE = "HIGHEST_SCORE_WITH_CASCADE"

# Selector contract version per §2.1. Bumped from v1 to v2 under D-0032.
SELECTOR_CONTRACT_VERSION = 2

# Sidecar artifact schema version per §19.
SIDECAR_SCHEMA_VERSION = 1


class RetentionMode(str, Enum):
    """`retentionMode` values per selector §13.

    `BEST_ONLY` is the operator-facing default — no per-candidate artifacts
    are retained. `FULL` is the opt-in audit mode — sidecar files are
    written per §14. `TOP_K` and `FULL_WITH_DIAGNOSTICS` are deferred to
    `docs/future_work.md` FW-0013 Phase 2.
    """

    BEST_ONLY = "BEST_ONLY"
    FULL = "FULL"


@dataclass(frozen=True)
class ScoredTrialCandidate:
    """A `TrialCandidate` paired with its `ScoreResult`.

    The selector's input per §9 item 1 is a `CandidateSet` whose
    `TrialCandidate.score` field has been populated by the scorer. The
    solver's `TrialCandidate` shape (per `docs/solver_contract.md` §10.1)
    intentionally carries no score field — score presence is stage-
    dependent. We pair `(candidate, score)` here so the selector consumes
    a single, structurally-explicit shape and never has to reach into a
    nullable score field on `TrialCandidate`.
    """

    candidate: TrialCandidate
    score: ScoreResult


@dataclass(frozen=True)
class ScoredCandidateSet:
    """The selector's success-branch input per §9 item 1.

    Wraps the solver's `CandidateSet` plus per-candidate `ScoreResult`
    entries. `diagnostics` is forwarded from the solver. Caller (typically
    a thin run-orchestrator) is responsible for scoring every emitted
    candidate before constructing this shape; partial scoring is a
    contract-breaking caller defect, not a selector responsibility.
    """

    candidates: tuple[ScoredTrialCandidate, ...]
    diagnostics: SearchDiagnostics


@dataclass(frozen=True)
class RunEnvelope:
    """Execution-layer-supplied run identity and provenance per §9 item 3
    + §16.

    The selector MUST NOT synthesize any field on this envelope — `runId`
    and `generationTimestamp` arrive from the caller (typically a run
    orchestrator at the local-run boundary). All fields ride through
    unchanged on `FinalResultEnvelope.runEnvelope` so retained artifacts
    are unambiguously traceable when found out of context (§16.4).

    `sourceSpreadsheetId` and `sourceTabName` are required under
    `contractVersion: 2` (D-0032) — they are not consumed by the selector
    itself but are required at the boundary so a downstream writeback
    adapter cannot receive a contract-compliant envelope that lacks them.
    """

    runId: str
    snapshotRef: str
    configRef: str
    seed: int
    fillOrderPolicy: str
    crFloorMode: str
    crFloorComputed: int
    generationTimestamp: str
    sourceSpreadsheetId: str
    sourceTabName: str


@dataclass(frozen=True)
class TrialBatchScoreSummary:
    """Per-batch score-distribution summary per §17.2.

    `totalScore` carries five-number summary; each component carries
    min/max/median. Populated by the selector when the solver surfaces
    `TrialBatchResult` (§17.4 — first-release `SEEDED_RANDOM_BLIND` does
    not surface batches, so first-release runs leave this empty in
    practice).
    """

    totalScoreMin: float
    totalScoreMax: float
    totalScoreMedian: float
    totalScoreMean: float
    totalScoreStddev: float
    componentMinMaxMedian: dict[str, tuple[float, float, float]]


@dataclass(frozen=True)
class TrialBatchResult:
    """Per-batch result per `docs/domain_model.md` §12.4 + §17.

    Selector-owned fields (`bestCandidate`, `scoreSummary`) are populated
    retroactively by the selector after scoring; solver-owned fields
    (batch identity, raw `TrialCandidate[]`) ride through unchanged.
    First-release solver does not surface batches per
    `docs/solver_contract.md` §18.2, so this shape exists for contract-
    completeness and forward compatibility.
    """

    batchId: str
    candidates: tuple[ScoredTrialCandidate, ...]
    bestCandidate: ScoredTrialCandidate | None = None
    scoreSummary: TrialBatchScoreSummary | None = None


@dataclass(frozen=True)
class AllocationResult:
    """Selector success-branch result per §10.1.

    Carries the winning candidate's full roster (`AssignmentUnit[]`) and
    its full `ScoreResult` component breakdown. `candidatesSummaryPath` /
    `candidatesFullPath` are populated under `FULL` retention only and
    MUST be absent under `BEST_ONLY` retention (§13).
    """

    winnerAssignment: tuple[AssignmentUnit, ...]
    winnerScore: ScoreResult
    searchDiagnostics: SearchDiagnostics
    trialBatches: tuple[TrialBatchResult, ...] = ()
    candidatesSummaryPath: str | None = None
    candidatesFullPath: str | None = None


@dataclass(frozen=True)
class UnsatisfiedResultEnvelope:
    """Selector failure-branch result per §10.2.

    Forwards the solver's `UnsatisfiedResult` payload unchanged. No
    candidates and no sidecars on this branch regardless of retention
    mode (§15).
    """

    unfilledDemand: tuple[UnfilledDemandEntry, ...]
    reasons: tuple[ValidationIssue, ...]
    searchDiagnostics: SearchDiagnostics


@dataclass(frozen=True)
class FinalResultEnvelope:
    """Top-level selector output per §10.

    Branch discipline (§10.3): exactly one of `AllocationResult` or
    `UnsatisfiedResultEnvelope` is in the `result` slot. `runEnvelope`
    carries through unchanged from the input per §16.4.
    """

    runEnvelope: RunEnvelope
    retentionMode: RetentionMode
    selectorStrategyId: str
    result: AllocationResult | UnsatisfiedResultEnvelope
