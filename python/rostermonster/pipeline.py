"""Shared compute core per `docs/decision_log.md` D-0050.

Both the local CLI wrapper (`rostermonster.run`) and the cloud HTTP
wrapper (`rostermonster_service.app`) call into `run_pipeline()` here,
so solver-strategy experiments performed via the local CLI are
guaranteed reproducible in the cloud and any cloud-mode defect is
reproducible from the local CLI by replaying the same `(snapshot,
optionalConfig)` per `docs/cloud_compute_contract.md` §13.

Public surface:
- `run_pipeline(...)` — runs parser → solver → scorer → selector
  end-to-end and returns a `PipelineResult` carrying the structured
  state + envelope + resolved-config metadata.
- `_snapshot_from_dict(...)` — JSON deserializer (re-exported from
  `rostermonster.run` for backwards-compat with existing tests).
- `_assemble_writeback_wrapper(...)` — wrapper-envelope assembly
  per D-0045 (re-exported from `rostermonster.run` for backwards-
  compat).
- `_to_jsonable(...)` — recursive JSON serializer (re-exported).

Per D-0053: when `seed` is omitted, the shared core picks a fresh
seed via `random.randint(0, 2**31-1)`. The resolved seed is recorded
in the returned `PipelineResult.resolved_seed` AND in
`envelope.runEnvelope.seed` so the operator can replay any run by
passing that value back as an explicit override.
"""

from __future__ import annotations

import dataclasses
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from rostermonster.parser import Consumability, parse
from rostermonster.rule_engine import evaluate as rule_engine_evaluate
from rostermonster.scorer import ScoringConfig, score
from rostermonster.selector import (
    AllocationResult,
    FinalResultEnvelope,
    RetentionMode,
    RunEnvelope,
    ScoredCandidateSet,
    ScoredTrialCandidate,
    select,
)
from rostermonster.snapshot import (
    CallPointLocator,
    CallPointRecord,
    ComponentWeightLocator,
    ComponentWeightRecord,
    DayLocator,
    DayRecord,
    DoctorLocator,
    DoctorRecord,
    ExtractionSummary,
    PeriodRef,
    PhysicalSourceRef,
    PrefilledAssignmentLocator,
    PrefilledAssignmentRecord,
    RequestLocator,
    RequestRecord,
    ScoringConfigRecords,
    Snapshot,
    SnapshotMetadata,
)
from rostermonster.solver import CandidateSet, TerminationBounds, solve

# Default candidate budget when caller omits the override. Per D-0053,
# there is intentionally NO default seed constant — omitted seed means
# random per invocation.
_DEFAULT_MAX_CANDIDATES = 32

# Upper bound on the random-seed namespace per D-0053. 2**31 - 1 is the
# largest signed-int32 value, which is safe across every RNG / hashable
# downstream we care about.
_RANDOM_SEED_MAX = 2 ** 31 - 1


PipelineState = Literal["OK", "UNSATISFIED", "PARSER_NON_CONSUMABLE"]


@dataclass(frozen=True)
class PipelineResult:
    """Structured result returned by `run_pipeline()`.

    Both wrappers (CLI + HTTP) dispatch on `state`:
    - `OK`: parser admitted snapshot, solver produced candidates,
      selector returned an `AllocationResult`. `envelope` is populated;
      `parser_issues` is empty.
    - `UNSATISFIED`: parser admitted snapshot but solver returned an
      `UnsatisfiedResultEnvelope` (no rule-valid roster within budget),
      OR selector returned a failure-branch envelope. `envelope` is
      populated with the failure-branch shape; `parser_issues` is empty.
    - `PARSER_NON_CONSUMABLE`: parser rejected the snapshot at admission
      time. `envelope` is None; `parser_issues` carries the issues.

    The `INPUT_ERROR` and `COMPUTE_ERROR` states from
    `docs/cloud_compute_contract.md` §10 are wrapper-level concerns
    (HTTP wrapper validates request shape and catches uncaught
    exceptions before/around `run_pipeline()`); the shared core does
    not surface them directly.
    """

    state: PipelineState
    envelope: FinalResultEnvelope | None
    parser_issues: tuple[Any, ...]
    resolved_seed: int
    resolved_max_candidates: int
    candidate_count: int


def run_pipeline(
    snapshot: Snapshot,
    template: Any,
    *,
    max_candidates: int | None = None,
    seed: int | None = None,
    retention_mode: RetentionMode = RetentionMode.BEST_ONLY,
    sidecar_dir: Path | None = None,
) -> PipelineResult:
    """Run the full M2 compute pipeline end-to-end.

    Args:
        snapshot: parsed `Snapshot` (typically from `_snapshot_from_dict`).
        template: template artifact (typically `icu_hd_template_artifact()`).
        max_candidates: solver candidate budget. When None, falls back
            to `_DEFAULT_MAX_CANDIDATES` (currently 32). Must be a
            positive integer when explicitly passed.
        seed: RNG seed for the solver's `SEEDED_RANDOM_BLIND` strategy.
            When None, a fresh seed is picked via `random.randint(0,
            _RANDOM_SEED_MAX)` per `docs/decision_log.md` D-0053.
        retention_mode: selector retention mode. Defaults to BEST_ONLY.
        sidecar_dir: target directory for FULL-retention sidecars.
            Required when retention_mode is FULL.

    Returns: `PipelineResult` carrying the dispatch state + populated
    envelope (when applicable) + resolved seed/max_candidates so
    callers can replay by passing the resolved values back as
    explicit overrides.
    """
    resolved_max_candidates = (
        max_candidates if max_candidates is not None else _DEFAULT_MAX_CANDIDATES
    )
    resolved_seed = (
        seed if seed is not None else random.randint(0, _RANDOM_SEED_MAX)
    )

    parser_result = parse(snapshot, template)
    if parser_result.consumability is not Consumability.CONSUMABLE:
        return PipelineResult(
            state="PARSER_NON_CONSUMABLE",
            envelope=None,
            parser_issues=tuple(parser_result.issues),
            resolved_seed=resolved_seed,
            resolved_max_candidates=resolved_max_candidates,
            candidate_count=0,
        )

    model = parser_result.normalizedModel
    config = (parser_result.scoringConfig
              or ScoringConfig.first_release_defaults(model))

    solver_result = solve(
        model,
        ruleEngine=rule_engine_evaluate,
        seed=resolved_seed,
        terminationBounds=TerminationBounds(
            maxCandidates=resolved_max_candidates
        ),
    )

    run_envelope = _build_run_envelope(snapshot, resolved_seed)

    if not isinstance(solver_result, CandidateSet):
        # Whole-run UnsatisfiedResult — selector forwards via the
        # failure branch per `docs/selector_contract.md` §15. We pin
        # BEST_ONLY for the failure-branch envelope to avoid triggering
        # a sidecar emission for a no-candidates run.
        envelope = select(
            solver_result,
            retentionMode=RetentionMode.BEST_ONLY,
            runEnvelope=run_envelope,
        )
        return PipelineResult(
            state="UNSATISFIED",
            envelope=envelope,
            parser_issues=(),
            resolved_seed=resolved_seed,
            resolved_max_candidates=resolved_max_candidates,
            candidate_count=0,
        )

    scored = ScoredCandidateSet(
        candidates=tuple(
            ScoredTrialCandidate(
                candidate=cand,
                score=score(cand.assignments, model, config),
            )
            for cand in solver_result.candidates
        ),
        diagnostics=solver_result.diagnostics,
    )
    envelope = select(
        scored,
        retentionMode=retention_mode,
        runEnvelope=run_envelope,
        sidecarTargetDir=sidecar_dir,
    )

    if not isinstance(envelope.result, AllocationResult):
        # Defensive: selector returned the failure-branch shape (e.g.,
        # zero scored candidates after filtering). Treat as UNSATISFIED
        # for caller's dispatch purposes.
        return PipelineResult(
            state="UNSATISFIED",
            envelope=envelope,
            parser_issues=(),
            resolved_seed=resolved_seed,
            resolved_max_candidates=resolved_max_candidates,
            candidate_count=len(scored.candidates),
        )

    return PipelineResult(
        state="OK",
        envelope=envelope,
        parser_issues=(),
        resolved_seed=resolved_seed,
        resolved_max_candidates=resolved_max_candidates,
        candidate_count=len(scored.candidates),
    )


# --- snapshot JSON deserialization ----------------------------------------


def _snapshot_from_dict(raw: dict) -> Snapshot:
    """Build a `Snapshot` from a raw dict (typically `json.loads` output).

    Strict per the snapshot contract: required fields raise KeyError.
    Used by both the CLI (file-on-disk) and the HTTP wrapper (request
    body) so the on-disk and over-the-wire snapshot shapes are
    enforced identically.
    """
    md = raw["metadata"]
    return Snapshot(
        metadata=SnapshotMetadata(
            snapshotId=md["snapshotId"],
            templateId=md.get("templateId", "cgh_icu_hd"),
            templateVersion=md.get("templateVersion", 1),
            sourceSpreadsheetId=md["sourceSpreadsheetId"],
            sourceTabName=md["sourceTabName"],
            generationTimestamp=md["generationTimestamp"],
            periodRef=PeriodRef(
                periodId=md["periodRef"]["periodId"],
                periodLabel=md["periodRef"].get("periodLabel", ""),
            ),
            extractionSummary=ExtractionSummary(
                doctorRecordCount=md["extractionSummary"]["doctorRecordCount"],
                dayRecordCount=md["extractionSummary"]["dayRecordCount"],
                requestRecordCount=md["extractionSummary"]["requestRecordCount"],
                prefilledAssignmentRecordCount=md["extractionSummary"][
                    "prefilledAssignmentRecordCount"
                ],
            ),
        ),
        doctorRecords=tuple(_doctor_record(d) for d in raw["doctorRecords"]),
        dayRecords=tuple(_day_record(d) for d in raw["dayRecords"]),
        requestRecords=tuple(_request_record(d) for d in raw["requestRecords"]),
        prefilledAssignmentRecords=tuple(
            _prefilled_record(d) for d in raw["prefilledAssignmentRecords"]
        ),
        scoringConfigRecords=_scoring_config_records(raw),
    )


def _physical_source_ref(d: dict) -> PhysicalSourceRef:
    return PhysicalSourceRef(
        sheetName=d["sheetName"],
        sheetGid=str(d["sheetGid"]),
        a1Refs=tuple(d["a1Refs"]),
    )


def _doctor_record(d: dict) -> DoctorRecord:
    loc = d["sourceLocator"]
    return DoctorRecord(
        sourceDoctorKey=d["sourceDoctorKey"],
        displayName=d["displayName"],
        rawSectionText=d["rawSectionText"],
        sourceLocator=DoctorLocator(
            sectionKey=loc["sectionKey"],
            doctorIndexInSection=loc["doctorIndexInSection"],
        ),
        physicalSourceRef=_physical_source_ref(d["physicalSourceRef"]),
    )


def _day_record(d: dict) -> DayRecord:
    return DayRecord(
        dayIndex=d["dayIndex"],
        rawDateText=d["rawDateText"],
        sourceLocator=DayLocator(dayIndex=d["sourceLocator"]["dayIndex"]),
        physicalSourceRef=_physical_source_ref(d["physicalSourceRef"]),
    )


def _request_record(d: dict) -> RequestRecord:
    loc = d["sourceLocator"]
    return RequestRecord(
        sourceDoctorKey=d["sourceDoctorKey"],
        dayIndex=d["dayIndex"],
        rawRequestText=d["rawRequestText"],
        sourceLocator=RequestLocator(
            sourceDoctorKey=loc["sourceDoctorKey"],
            dayIndex=loc["dayIndex"],
        ),
        physicalSourceRef=_physical_source_ref(d["physicalSourceRef"]),
    )


def _prefilled_record(d: dict) -> PrefilledAssignmentRecord:
    loc = d["sourceLocator"]
    return PrefilledAssignmentRecord(
        dayIndex=d["dayIndex"],
        rawAssignedDoctorText=d["rawAssignedDoctorText"],
        surfaceId=d["surfaceId"],
        rowOffset=d["rowOffset"],
        sourceLocator=PrefilledAssignmentLocator(
            surfaceId=loc["surfaceId"],
            rowOffset=loc["rowOffset"],
            dayIndex=loc["dayIndex"],
        ),
        physicalSourceRef=_physical_source_ref(d["physicalSourceRef"]),
    )


def _scoring_config_records(raw: dict) -> ScoringConfigRecords:
    block = raw.get("scoringConfigRecords", {}) or {}
    return ScoringConfigRecords(
        componentWeightRecords=tuple(
            _component_weight_record(r)
            for r in block.get("componentWeightRecords", [])
        ),
        callPointRecords=tuple(
            _call_point_record(r) for r in block.get("callPointRecords", [])
        ),
    )


def _component_weight_record(d: dict) -> ComponentWeightRecord:
    loc = d["sourceLocator"]
    return ComponentWeightRecord(
        componentId=d["componentId"],
        rawValue=d["rawValue"],
        sourceLocator=ComponentWeightLocator(componentId=loc["componentId"]),
        physicalSourceRef=_physical_source_ref(d["physicalSourceRef"]),
    )


def _call_point_record(d: dict) -> CallPointRecord:
    loc = d["sourceLocator"]
    return CallPointRecord(
        callPointRowKey=d["callPointRowKey"],
        dayIndex=d["dayIndex"],
        rawValue=d["rawValue"],
        sourceLocator=CallPointLocator(
            callPointRowKey=loc["callPointRowKey"],
            dayIndex=loc["dayIndex"],
        ),
        physicalSourceRef=_physical_source_ref(d["physicalSourceRef"]),
    )


# --- runtime helpers -------------------------------------------------------


def _build_run_envelope(snapshot: Snapshot, seed: int) -> RunEnvelope:
    """Construct a `RunEnvelope` from snapshot metadata + the resolved seed.

    Runtime-supplied fields (`runId`, `seed`, `generationTimestamp`) are
    derived from the snapshot + caller-supplied seed; other fields take
    pilot-scope defaults that match the integration smoke test pattern.
    """
    md = snapshot.metadata
    return RunEnvelope(
        runId=md.snapshotId,
        snapshotRef=md.snapshotId,
        configRef="first_release_defaults",
        seed=seed,
        fillOrderPolicy="MOST_CONSTRAINED_FIRST",
        crFloorMode="SMART_MEDIAN",
        crFloorComputed=0,
        generationTimestamp=md.generationTimestamp,
        sourceSpreadsheetId=md.sourceSpreadsheetId,
        sourceTabName=md.sourceTabName,
    )


# --- writeback wrapper assembly (per D-0045) ------------------------------


def _assemble_writeback_wrapper(envelope: FinalResultEnvelope,
                                  snapshot: Snapshot,
                                  template) -> dict[str, Any]:
    """Wrap the FinalResultEnvelope with a snapshot subset + doctorIdMap so
    the operator uploads ONE file to the launcher's writeback form per
    `docs/decision_log.md` D-0045 + D-0047. Concrete keys/order are
    implementation-slice per `docs/writeback_contract.md` §22; categories of
    content are pinned by D-0045 sub-decisions 1..4."""
    return {
        "schemaVersion": 1,
        "finalResultEnvelope": _to_jsonable(envelope),
        "snapshot": _build_writeback_snapshot_subset(snapshot, template),
        "doctorIdMap": _build_doctor_id_map(snapshot),
    }


def _build_writeback_snapshot_subset(snapshot: Snapshot,
                                       template) -> dict[str, Any]:
    """Project the full Snapshot into the writeback contract §9 'snapshot'
    subset that the Apps Script writeback library needs to reconstruct
    shell content per `docs/writeback_contract.md` §10.1."""
    section_to_group = {
        s.sectionKey: s.groupId for s in template.inputSheetSections
    }

    column_a = [
        {
            "sectionGroup": rec.sourceLocator.sectionKey,
            "rowIndex": rec.sourceLocator.doctorIndexInSection,
            "value": rec.displayName,
        }
        for rec in snapshot.doctorRecords
    ]

    request_cells = [
        {
            "sourceDoctorKey": rec.sourceDoctorKey,
            "dayIndex": rec.dayIndex,
            "value": rec.rawRequestText,
        }
        for rec in snapshot.requestRecords
    ]

    call_point_cells = [
        {
            "callPointRowKey": rec.callPointRowKey,
            "dayIndex": rec.dayIndex,
            "value": rec.rawValue,
        }
        for rec in snapshot.scoringConfigRecords.callPointRecords
    ]

    prefilled = [
        {
            "surfaceId": rec.surfaceId,
            "rowOffset": rec.rowOffset,
            "dayIndex": rec.dayIndex,
            "value": rec.rawAssignedDoctorText,
        }
        for rec in snapshot.prefilledAssignmentRecords
    ]

    output_assignment_rows = [
        {
            "surfaceId": surface.surfaceId,
            "slotType": row.slotId,
            "rowOffset": row.rowOffset,
        }
        for surface in template.outputSurfaces
        for row in surface.assignmentRows
    ]

    doctor_count_by_group: dict[str, int] = {}
    for rec in snapshot.doctorRecords:
        section_key = rec.sourceLocator.sectionKey
        group_id = section_to_group.get(section_key, section_key)
        doctor_count_by_group[group_id] = (
            doctor_count_by_group.get(group_id, 0) + 1
        )

    period_start = (snapshot.dayRecords[0].rawDateText
                    if snapshot.dayRecords else "")
    period_end = (snapshot.dayRecords[-1].rawDateText
                  if snapshot.dayRecords else "")

    return {
        "columnADoctorNames": column_a,
        "requestCells": request_cells,
        "callPointCells": call_point_cells,
        "prefilledFixedAssignmentCells": prefilled,
        "outputAssignmentRows": output_assignment_rows,
        "shellParameters": {
            "department": template.identity.label,
            "periodStartDate": period_start,
            "periodEndDate": period_end,
            "doctorCountByGroup": doctor_count_by_group,
        },
    }


def _build_doctor_id_map(snapshot: Snapshot) -> list[dict[str, Any]]:
    """Build the `doctorIdMap` per `docs/writeback_contract.md` §9 item 3 +
    §12. First-release parser passes `sourceDoctorKey` through unchanged
    as `Doctor.doctorId`, so doctorId = sourceDoctorKey here."""
    return [
        {
            "doctorId": rec.sourceDoctorKey,
            "sectionGroup": rec.sourceLocator.sectionKey,
            "rowIndex": rec.sourceLocator.doctorIndexInSection,
        }
        for rec in snapshot.doctorRecords
    ]


def _to_jsonable(value: Any) -> Any:
    """Recursively convert dataclasses, tuples, frozensets, and Enums into
    JSON-serializable Python primitives."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: _to_jsonable(getattr(value, f.name))
            for f in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return [_to_jsonable(v) for v in sorted(value, key=str)]
    if hasattr(value, "name") and hasattr(value, "value") and not isinstance(
            value, (int, str, float)):
        # Looks like an Enum — emit by name.
        return value.name
    if isinstance(value, Path):
        return str(value)
    return value
