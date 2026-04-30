"""Production CLI shim per `docs/snapshot_adapter_contract.md` §11.

Reads a Snapshot-shape JSON file produced by the Apps Script extractor
(per `docs/decision_log.md` D-0040 transport — operator-saved browser
download), runs the full M2 compute pipeline (parser → solver → scorer
→ selector), and writes a `FinalResultEnvelope` JSON file alongside the
input.

Usage::

    python -m rostermonster.run --snapshot path/to/snapshot.json
    python -m rostermonster.run --snapshot path/to/snapshot.json \\
        --output path/to/result.json --seed 12345

Exit codes:
- 0: success — winning candidate selected, FinalResultEnvelope written.
- 1: failure — snapshot did not parse to CONSUMABLE, OR solver returned
  an UnsatisfiedResult (no rule-valid roster found within the search
  budget). The FinalResultEnvelope is still written, carrying the
  failure-branch shape per `docs/selector_contract.md` §10.2.
- 2: invalid CLI usage — missing `--snapshot`, file not readable, etc.

For pilot scope this CLI deliberately keeps surface narrow. Operator
launches it from the terminal, points at the downloaded JSON, gets a
result file. Future work covers richer modes (interactive selection,
multi-template support, sidecar output directory).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any, Iterable

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
from rostermonster.templates import icu_hd_template_artifact

# Stable default seed for pilot runs. Operators can override via `--seed`.
# Picked once and pinned here to keep first-release runs reproducible.
_DEFAULT_SEED = 20260504
_DEFAULT_MAX_CANDIDATES = 32


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns the process exit code."""
    args = _parse_args(argv)
    snapshot_path = Path(args.snapshot)
    if not snapshot_path.is_file():
        print(f"snapshot file not found: {snapshot_path}", file=sys.stderr)
        return 2

    output_path = (
        Path(args.output) if args.output
        else snapshot_path.with_name(snapshot_path.stem + ".result.json")
    )

    raw = json.loads(snapshot_path.read_text())
    snapshot = _snapshot_from_dict(raw)
    template = icu_hd_template_artifact()
    parser_result = parse(snapshot, template)

    if parser_result.consumability is not Consumability.CONSUMABLE:
        print(
            f"NON_CONSUMABLE — {len(parser_result.issues)} issue(s):",
            file=sys.stderr,
        )
        for issue in parser_result.issues:
            print(f"  [{issue.severity}] {issue.code}: {issue.message}",
                  file=sys.stderr)
        # Write a minimal failure envelope so the operator workflow has a
        # stable artifact even on failure. Selector failure-branch shape
        # is for SOLVER UnsatisfiedResult; pre-solve admission failure is
        # NOT a selector concern, so we emit a small CLI-specific error
        # JSON instead.
        output_path.write_text(json.dumps({
            "status": "PARSER_NON_CONSUMABLE",
            "snapshotPath": str(snapshot_path),
            "issueCount": len(parser_result.issues),
            "issues": [
                {"severity": i.severity.name if hasattr(i.severity, "name")
                 else str(i.severity),
                 "code": i.code, "message": i.message}
                for i in parser_result.issues
            ],
        }, indent=2))
        print(f"\nWrote diagnostic to {output_path}", file=sys.stderr)
        return 1

    # CONSUMABLE: run the full M2 pipeline.
    model = parser_result.normalizedModel
    config = parser_result.scoringConfig or ScoringConfig.first_release_defaults(model)

    solver_result = solve(
        model,
        ruleEngine=rule_engine_evaluate,
        seed=args.seed,
        terminationBounds=TerminationBounds(maxCandidates=args.max_candidates),
    )
    # Resolve retention mode + sidecar directory. FULL retention requires a
    # sidecar dir per `docs/selector_contract.md` §13 / §14; if omitted, we
    # default to a sibling directory next to the output JSON.
    retention_mode = RetentionMode[args.retention.upper()]
    sidecar_dir: Path | None = None
    if retention_mode is RetentionMode.FULL:
        sidecar_dir = (Path(args.sidecar_dir) if args.sidecar_dir
                       else output_path.parent / (output_path.stem + ".sidecars"))
        sidecar_dir.mkdir(parents=True, exist_ok=True)

    if not isinstance(solver_result, CandidateSet):
        # Solver returned UnsatisfiedResult — whole-run failure. Selector
        # forwards via the failure branch per `docs/selector_contract.md` §15.
        envelope = select(
            solver_result,
            retentionMode=RetentionMode.BEST_ONLY,
            runEnvelope=_build_run_envelope(snapshot, args.seed),
        )
        _write_output(envelope, snapshot, template, output_path,
                      writeback_ready=args.writeback_ready)
        print(f"UNSATISFIED — no rule-valid roster found within "
              f"{args.max_candidates} candidate budget. "
              f"Result written to {output_path}", file=sys.stderr)
        return 1

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
        runEnvelope=_build_run_envelope(snapshot, args.seed),
        sidecarTargetDir=sidecar_dir,
    )
    _write_output(envelope, snapshot, template, output_path,
                  writeback_ready=args.writeback_ready)
    if isinstance(envelope.result, AllocationResult):
        score_total = envelope.result.winnerScore.totalScore
        n_filled = sum(
            1 for a in envelope.result.winnerAssignment if a.doctorId is not None
        )
        n_total = len(envelope.result.winnerAssignment)
        msg = (f"Selected winner across {len(scored.candidates)} candidates. "
               f"Score: {score_total:.3f}. "
               f"Assignments filled: {n_filled}/{n_total}. "
               f"Output: {output_path}")
        if sidecar_dir is not None:
            msg += (f"\nFULL retention sidecars: "
                    f"{envelope.result.candidatesSummaryPath} + "
                    f"{envelope.result.candidatesFullPath}")
        print(msg)
        return 0
    # Defensive: any non-AllocationResult means selector returned the
    # failure branch shape (e.g., snapshot was structurally consumable but
    # zero candidates produced). Write the envelope and exit non-zero.
    print(f"NO ALLOCATION — selector returned failure-branch result. "
          f"Result written to {output_path}", file=sys.stderr)
    return 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m rostermonster.run",
        description=(
            "Run the Roster Monster compute pipeline against an "
            "extractor-produced snapshot JSON file."
        ),
    )
    p.add_argument(
        "--snapshot", required=True,
        help="path to snapshot JSON file (produced by the Apps Script extractor)",
    )
    p.add_argument(
        "--output", default=None,
        help="output path for the FinalResultEnvelope JSON "
             "(default: <snapshot>.result.json alongside the input)",
    )
    p.add_argument(
        "--seed", type=int, default=_DEFAULT_SEED,
        help=f"RNG seed for solver determinism (default {_DEFAULT_SEED})",
    )
    p.add_argument(
        "--max-candidates", type=int, default=_DEFAULT_MAX_CANDIDATES,
        help=f"max number of candidates the solver enumerates "
             f"(default {_DEFAULT_MAX_CANDIDATES})",
    )
    p.add_argument(
        "--retention", choices=["BEST_ONLY", "FULL"], default="BEST_ONLY",
        help="selector retention mode per `docs/selector_contract.md` §13. "
             "BEST_ONLY (default) keeps only the winner; FULL emits "
             "sidecar files (candidates_summary.csv + candidates_full.json) "
             "with the full ranked candidate set",
    )
    p.add_argument(
        "--sidecar-dir", default=None,
        help="directory for FULL-retention sidecar files (only meaningful "
             "with --retention FULL; defaults to <output>.sidecars/ "
             "alongside the output file)",
    )
    p.add_argument(
        "--writeback-ready",
        type=_parse_bool,
        default=True,
        help="when true (default), the output JSON is the writeback envelope "
             "wrapper per `docs/decision_log.md` D-0045 + D-0047 (single file "
             "containing FinalResultEnvelope + snapshot subset + doctorIdMap, "
             "ready to upload to the launcher's writeback form). When false, "
             "the output is the bare FinalResultEnvelope (pre-M3 C1 behavior, "
             "useful for callers that don't intend to writeback).",
    )
    return p.parse_args(argv)


def _parse_bool(value: str) -> bool:
    """Loose bool parser for the --writeback-ready CLI flag. Accepts
    `true`/`false`/`yes`/`no`/`1`/`0` (case-insensitive)."""
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"true", "yes", "1", "y", "t"}:
        return True
    if s in {"false", "no", "0", "n", "f"}:
        return False
    raise argparse.ArgumentTypeError(
        f"expected a boolean (true/false/yes/no/1/0), got {value!r}"
    )


# --- snapshot JSON deserialization ----------------------------------------


def _snapshot_from_dict(raw: dict) -> Snapshot:
    """Build a `Snapshot` from a raw dict (typically `json.loads` output).

    Mirrors `python/tests/test_real_icu_hd_may_2026.py` `_load_real_snapshot`
    but accepts the dict directly so callers can read from any source.
    Strict per the snapshot contract: required fields raise KeyError.
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
    """Construct a `RunEnvelope` for the CLI run from snapshot metadata.

    Runtime-supplied fields (`runId`, `seed`, `generationTimestamp`) are
    derived from snapshot metadata + CLI args; other fields take pilot-
    scope defaults that match the integration smoke test pattern.
    """
    md = snapshot.metadata
    return RunEnvelope(
        runId=md.snapshotId,  # snapshotId IS the run identifier on local CLI
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


def _write_output(envelope: FinalResultEnvelope, snapshot: Snapshot,
                  template, output_path: Path, *,
                  writeback_ready: bool) -> None:
    """Serialize the CLI's output JSON to disk. When `writeback_ready` is
    true (the M3 C1+ default per `docs/decision_log.md` D-0047), the output
    is the writeback wrapper envelope per D-0045 (single file containing
    `finalResultEnvelope` + `snapshot` subset + `doctorIdMap`). When false,
    the output is the bare `FinalResultEnvelope` (pre-M3 C1 behavior, kept
    available for callers that don't intend to writeback — for example,
    test harnesses that assert on the selector's exact output shape per
    `docs/selector_contract.md` §10)."""
    if writeback_ready:
        payload = _assemble_writeback_wrapper(envelope, snapshot, template)
    else:
        payload = _to_jsonable(envelope)
    output_path.write_text(json.dumps(payload, indent=2))


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
    shell content per `docs/writeback_contract.md` §10.1. Categories
    pinned by D-0045 sub-decision 3:
    `columnADoctorNames` + `requestCells` + `callPointCells` +
    `prefilledFixedAssignmentCells` + `shellParameters`. Full snapshot
    fields (record-level locators, physical source refs, raw cell text
    beyond what the writeback tab needs) are deliberately omitted."""
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
        # Fall back to section key if the template doesn't declare a
        # mapping (defensive — should never happen for ICU/HD first
        # release where the template covers all snapshot sections).
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
    as `Doctor.doctorId`, so doctorId = sourceDoctorKey here. Apps Script
    writeback library uses this map to resolve `AssignmentUnit.doctorId`
    to the column-A cell value via §12.1."""
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


if __name__ == "__main__":
    sys.exit(main())
