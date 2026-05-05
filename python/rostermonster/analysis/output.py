"""`AnalyzerOutput` dataclasses + JSON serialization per
`docs/analysis_contract.md` §10.

Mirrors the per-module result-shape pattern used in selector/, parser/,
solver/ etc. Pure data definitions; no compute. Byte-identical
deterministic serialization per §15 via `sort_keys=True` + `indent=2` +
trailing newline (same discipline as `selector/sidecars.py`).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

# Contract version per `docs/analysis_contract.md` §2.
ANALYSIS_CONTRACT_VERSION = 1


@dataclass(frozen=True)
class ComponentBreakdown:
    """Per-component contribution per §10.3.

    `weighted` is the contribution to `totalScore` (sign-correct per
    scorer §10). `raw` is the pre-weight magnitude (`weighted /
    weights[componentName]` when weight is non-zero; sentinel `0` when
    weight is zero per §10.3 v1 tolerance). `rankAcrossTopK` is 1-indexed
    over the returned K. `gapToNextRanked` is the weighted gap to the
    next-best candidate on this component; `None` on rank == returned.
    """

    weighted: float
    raw: float
    rankAcrossTopK: int
    gapToNextRanked: float | None


@dataclass(frozen=True)
class PerDoctorAggregates:
    """Tier 2 per-doctor equity per §10.6.

    `cumulativeCallPoints` is computed against the post-overlay scoring
    config per §10.6 call-point source note (parser overlay reuse).
    Public-holiday metrics omitted in v1 per §10.6 PH-deferral note —
    parked as FW-0031.
    """

    callCount: int
    standbyCount: int
    weekendCallCount: int
    cumulativeCallPoints: float
    maxConsecutiveDaysOff: int


@dataclass(frozen=True)
class AssignmentRefRecord:
    """Per-cell assignment ride-through per §10.5.

    Includes `unitIndex` so multi-slot days (`requiredCount > 1`) remain
    distinguishable; Hamming-distance comparisons in §10.7 use the full
    `(dateKey, slotType, unitIndex)` triple.

    `doctorId` is a string per `Doctor.doctorId` in the domain model
    (first-release identity rule per §10.0: doctorId ==
    snapshot.doctorRecords[*].sourceDoctorKey); `None` represents an
    explicit unfilled unit per `docs/domain_model.md` §10.2.
    """

    dateKey: str
    slotType: str
    unitIndex: int
    doctorId: str | None


@dataclass(frozen=True)
class AnalyzerCandidate:
    """Per-candidate analyzer payload per §10.2.

    `ruleViolations` is NOT a v1 field per §10.2 PH-style omission note
    — Tier 6 surface deferred to FW-0032. `recommended` is `True` iff
    `rankByTotalScore == 1` per §11.1.
    """

    candidateId: int
    rankByTotalScore: int
    recommended: bool
    totalScore: float
    scoreComponents: dict[str, ComponentBreakdown]
    fillStats: dict[str, int]
    perDoctor: dict[str, PerDoctorAggregates]
    assignment: list[AssignmentRefRecord]


@dataclass(frozen=True)
class TopKResult:
    """Top-K selection result per §10.1.

    `returned == min(requested, candidatesAvailable)` per §11 step 4.
    `candidates` is ordered by §11 ranking (totalScore desc → cascade).
    """

    requested: int
    returned: int
    candidates: list[AnalyzerCandidate]


@dataclass(frozen=True)
class EquityScalars:
    """Tier 3 per-candidate fairness rollups per §10.8.

    Public-holiday equity scalars omitted in v1 in lockstep with the
    Tier 2 PH-field deferral.
    """

    callCount: dict[str, float]
    weekendCallCount: dict[str, float]
    cumulativeCallPoints: dict[str, float]


@dataclass(frozen=True)
class HotDayEntry:
    """Tier 4 day-level: a date where the K candidates produce more than
    one distinct doctor-tuple per §10.7."""

    dateKey: str
    distinctAssignments: int


@dataclass(frozen=True)
class LockedDayEntry:
    """Tier 4 day-level: a date where all K candidates assign the same
    doctor-tuple per §10.7."""

    dateKey: str


@dataclass(frozen=True)
class ComparisonAggregates:
    """Cross-candidate aggregates per §10.7.

    `pairwiseHammingDistance` is symmetric; v1 emits the full square
    (both `[a][b]` and `[b][a]`) to spare readers from triangle-lookup
    bookkeeping. JSON object keys are stringified integers per JSON
    serialization conventions.
    """

    pairwiseHammingDistance: dict[int, dict[int, int]]
    hotDays: list[HotDayEntry]
    lockedDays: list[LockedDayEntry]
    perCandidateEquity: dict[int, EquityScalars]


@dataclass(frozen=True)
class AnalyzerSource:
    """Run-identity ride-through per §10.

    Sourced from `envelope.finalResultEnvelope.runEnvelope`. Echo only;
    analyzer MUST NOT branch on these fields per §12.
    """

    runId: str
    seed: int | None
    sourceSpreadsheetId: str
    sourceTabName: str


@dataclass(frozen=True)
class AnalyzerOutput:
    """Top-level analyzer output per §10.

    `contractVersion` is pinned at v1 per §2. `generatedAt` is ride-
    through from the §9 input #5 caller-supplied timestamp; analyzer
    MUST NOT call `datetime.now()` per §15. `doctorIdMap` is analyzer-
    constructed per §10.0 mapping rule (NOT a passthrough of
    `envelope.doctorIdMap` which is a list-of-records).
    """

    contractVersion: int
    generatedAt: str
    source: AnalyzerSource
    topK: TopKResult
    comparison: ComparisonAggregates
    doctorIdMap: dict[str, str]


def _to_jsonable(obj: Any) -> Any:
    """Recursively convert dataclass / nested dict / list trees to
    JSON-serializable shapes. Mirrors the helper at `pipeline.py` of the
    main wrapper-envelope path."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        # JSON object keys must be strings; stringify int keys for
        # `doctorIdMap` and `pairwiseHammingDistance` etc.
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


def render_analyzer_output_json(output: AnalyzerOutput) -> str:
    """Render `AnalyzerOutput` as byte-identical-deterministic JSON
    text per §15.

    `json.dumps(..., sort_keys=True, indent=2)` + trailing newline match
    the discipline in `selector/sidecars.py` so the analyzer's emit
    profile lines up with the rest of the per-run artifact set.
    """
    payload = _to_jsonable(output)
    return json.dumps(payload, sort_keys=True, indent=2) + "\n"
