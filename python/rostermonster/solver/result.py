"""Solver result + config types per `docs/solver_contract.md` §9–§13, §15, §18.

Shapes here are public input/output types of the solver module. The solver
is scoring-blind by contract (§9 + §11) — none of these types reference the
scorer interface or any scoring config.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from rostermonster.domain import AssignmentUnit, ValidationIssue

# First-release strategy / policy identifiers per solver §11–§12.
STRATEGY_SEEDED_RANDOM_BLIND = "SEEDED_RANDOM_BLIND"
FILL_ORDER_POLICY_MOST_CONSTRAINED_FIRST = "MOST_CONSTRAINED_FIRST"


class CrFloorMode(str, Enum):
    """`crFloor` modes per solver §13."""

    SMART_MEDIAN = "SMART_MEDIAN"
    MANUAL = "MANUAL"


@dataclass(frozen=True)
class CrFloorConfig:
    """`preferenceSeeding.crFloor` shape per solver §13.

    `manualValue` is required and MUST be `>= 0` when `mode = MANUAL` per
    §13.2; ignored when `mode = SMART_MEDIAN`.
    """

    mode: CrFloorMode = CrFloorMode.SMART_MEDIAN
    manualValue: int | None = None


@dataclass(frozen=True)
class PreferenceSeedingConfig:
    """`preferenceSeeding` shape per solver §9.

    First-release surface is `crFloor` only. Defaulting `crFloor` to
    `SMART_MEDIAN` matches §13.1's "default mode when `preferenceSeeding`
    is omitted or when `preferenceSeeding.crFloor` is omitted."
    """

    crFloor: CrFloorConfig = field(default_factory=CrFloorConfig)


@dataclass(frozen=True)
class TerminationBounds:
    """`terminationBounds` shape per solver §15.

    First-release surface is exactly one field: `maxCandidates` (required,
    positive integer). Wall-clock termination is deliberately excluded per
    §15 to preserve byte-identical determinism (§16).
    """

    maxCandidates: int


@dataclass(frozen=True)
class UnfilledDemandEntry:
    """One unfillable `(dateKey, slotType, unitIndex)` per solver §10.2.

    Emitted in `UnsatisfiedResult.unfilledDemand` when no valid placement
    exists for a demand unit under the active strategy's constraints.
    """

    dateKey: str
    slotType: str
    unitIndex: int


@dataclass(frozen=True)
class SearchDiagnostics:
    """Run-level transparency payload per solver §18.1.

    `crFloorComputed` is the `X` value used by Phase 1 (§13.4 audit
    requirement: under `SMART_MEDIAN`, `X` depends on input distribution; under
    `MANUAL`, `X` was operator-set — both must be recoverable from the run
    artifact). `ruleEngineRejectionsByReason` aggregates `(rule_code → count)`
    for transparency on candidate-generation funnel.
    """

    strategyId: str
    fillOrderPolicy: str
    crFloorMode: CrFloorMode
    crFloorComputed: int
    seed: int
    placementAttempts: int
    ruleEngineRejectionsByReason: dict[str, int]
    candidateEmitCount: int
    unfilledDemandCount: int


@dataclass(frozen=True)
class TrialCandidate:
    """One candidate roster emitted by the solver per solver §10.1.

    `assignments` covers the full roster — `FixedAssignment`-derived entries
    plus solver-placed `AssignmentUnit` entries. The `score` field is
    intentionally absent at solver-emission stage; the scorer populates it
    downstream. The contract forbids the solver from populating any score
    field.

    `candidateId` is a stable per-run identifier: `f"c{index:04d}"` where
    `index` is the emit order under the run's seed (1-indexed for
    operator-friendliness; `c0001` reads better than `c0000`). Used by the
    selector for the `(runId, candidateId)` traceability anchor per
    `docs/selector_contract.md`.
    """

    candidateId: str
    assignments: tuple[AssignmentUnit, ...]


@dataclass(frozen=True)
class CandidateSet:
    """Solver success-branch output per solver §10.1.

    `candidates` MUST be non-empty per §10.1; emitting an empty
    `CandidateSet` is contract-breaking. When no valid complete candidate is
    reachable under the active bounds, the solver returns
    `UnsatisfiedResult` (§10.2) instead.
    """

    candidates: tuple[TrialCandidate, ...]
    diagnostics: SearchDiagnostics


@dataclass(frozen=True)
class UnsatisfiedResult:
    """Solver whole-run-failure-branch output per solver §10.2.

    Returned when any non-fixed demand unit cannot be filled under
    rule-engine validity within the active termination bounds. Per §14, no
    partial allocations are emitted — `unfilledDemand` enumerates the
    demand units the solver could not satisfy on at least one attempted
    candidate construction.
    """

    unfilledDemand: tuple[UnfilledDemandEntry, ...]
    reasons: tuple[ValidationIssue, ...]
    diagnostics: SearchDiagnostics
