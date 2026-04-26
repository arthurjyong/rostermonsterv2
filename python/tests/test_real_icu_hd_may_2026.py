"""M2 C3 T3 — hand-test against real ICU/HD May 2026 source data.

Loads the committed JSON snapshot fixture (derived from the dev-copy
xlsx via `extract_icu_hd_may_2026.py`) and exercises the parser end-to-end:
- positive case: real CONSUMABLE pass with expected counts and a smattering
  of substantive request-semantics checks against operator-entered codes;
- negative case: take the real snapshot, deliberately corrupt one field,
  verify NON_CONSUMABLE with the right structured reason.

Pytest-compatible. Also runnable directly via
`python3 python/tests/test_real_icu_hd_may_2026.py`. Exit code 0 on full
pass, 1 on any failure.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rostermonster.domain import (  # noqa: E402
    CanonicalRequestClass,
    MachineEffect,
)
from rostermonster.parser import Consumability, parse  # noqa: E402
from rostermonster.parser.admission import (  # noqa: E402
    ISSUE_DAY_INDEX_NON_CONTIGUOUS,
    ISSUE_DOCTOR_SECTION_UNKNOWN,
)
from rostermonster.snapshot import (  # noqa: E402
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
    Snapshot,
    SnapshotMetadata,
)
from tests.fixtures import icu_hd_template_artifact  # noqa: E402

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "data" / "icu_hd_may_2026_snapshot.json"
)


# --- JSON → Snapshot loader -----------------------------------------------


def _physical_ref(d: dict) -> PhysicalSourceRef:
    return PhysicalSourceRef(
        sheetName=d["sheetName"],
        sheetGid=d["sheetGid"],
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
        physicalSourceRef=_physical_ref(d["physicalSourceRef"]),
    )


def _day_record(d: dict) -> DayRecord:
    return DayRecord(
        dayIndex=d["dayIndex"],
        rawDateText=d["rawDateText"],
        sourceLocator=DayLocator(dayIndex=d["sourceLocator"]["dayIndex"]),
        physicalSourceRef=_physical_ref(d["physicalSourceRef"]),
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
        physicalSourceRef=_physical_ref(d["physicalSourceRef"]),
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
        physicalSourceRef=_physical_ref(d["physicalSourceRef"]),
    )


def _load_real_snapshot() -> Snapshot:
    raw = json.loads(FIXTURE_PATH.read_text())
    md = raw["metadata"]
    return Snapshot(
        metadata=SnapshotMetadata(
            snapshotId=md["snapshotId"],
            templateId=md["templateId"],
            templateVersion=md["templateVersion"],
            sourceSpreadsheetId=md["sourceSpreadsheetId"],
            sourceTabName=md["sourceTabName"],
            generationTimestamp=md["generationTimestamp"],
            periodRef=PeriodRef(
                periodId=md["periodRef"]["periodId"],
                periodLabel=md["periodRef"]["periodLabel"],
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
    )


# --- Positive case --------------------------------------------------------


def test_real_icu_hd_may_2026_is_consumable() -> None:
    """End-to-end: real ICU/HD May 2026 dev-copy snapshot lands at CONSUMABLE
    with expected counts and substantive request-semantics behavior."""
    template = icu_hd_template_artifact()
    snapshot = _load_real_snapshot()
    result = parse(snapshot, template)

    issue_codes = {i.code for i in result.issues}
    assert result.consumability is Consumability.CONSUMABLE, (
        f"expected CONSUMABLE on real ICU/HD May 2026 input; got "
        f"{result.consumability!r} with issues {issue_codes}"
    )

    nm = result.normalizedModel
    # Period: 29 days, 2026-05-04 to 2026-06-01.
    assert nm.period.periodId == "2026-05"
    assert len(nm.period.days) == 29
    assert nm.period.days[0].dateKey == "2026-05-04"
    assert nm.period.days[-1].dateKey == "2026-06-01"

    # Doctor counts per group: 9 ICU_ONLY + 6 ICU_HD + 7 HD_ONLY = 22 total.
    assert len(nm.doctors) == 22
    by_group: dict[str, int] = {}
    for doc in nm.doctors:
        by_group[doc.groupId] = by_group.get(doc.groupId, 0) + 1
    assert by_group == {"ICU_ONLY": 9, "ICU_HD": 6, "HD_ONLY": 7}, (
        f"unexpected per-group doctor counts: {by_group}"
    )

    # SlotDemand cross-product: 29 days × 4 slot types = 116 records,
    # all requiredCount=1 in first release.
    assert len(nm.slotDemand) == 29 * 4
    assert all(sd.requiredCount == 1 for sd in nm.slotDemand)

    # No prefilled assignments — operator hasn't filled any in May 2026 yet.
    assert nm.fixedAssignments == ()

    # Substantive request-semantics checks. We verify a handful of operator-
    # entered codes parse to the expected canonical/effect shape per
    # docs/request_semantics_contract.md §9 / §10. We look for any AL/CR/EMCC
    # request rather than asserting on a specific date, so the test stays
    # durable against dev-copy data shifts within the same ICU/HD shape.

    # AL → FULL_DAY_OFF → {sameDayHardBlock, prevDayCallSoftPenaltyTrigger}.
    al_req = next(
        (r for r in nm.requests if "AL" in r.recognizedRawTokens), None
    )
    assert al_req is not None, "expected at least one AL request in real input"
    assert CanonicalRequestClass.FULL_DAY_OFF in al_req.canonicalClasses
    assert MachineEffect.sameDayHardBlock in al_req.machineEffects
    assert MachineEffect.prevDayCallSoftPenaltyTrigger in al_req.machineEffects

    # EMCC → PM_OFF → same effect set as FULL_DAY_OFF
    # (sameDayHardBlock + prevDayCallSoftPenaltyTrigger).
    emcc_req = next(
        (r for r in nm.requests if "EMCC" in r.recognizedRawTokens), None
    )
    assert emcc_req is not None, "expected at least one EMCC request in real input"
    assert CanonicalRequestClass.PM_OFF in emcc_req.canonicalClasses
    assert MachineEffect.sameDayHardBlock in emcc_req.machineEffects
    assert MachineEffect.prevDayCallSoftPenaltyTrigger in emcc_req.machineEffects

    # CR requests should produce callPreferencePositive only (and no hard block).
    cr_reqs = [r for r in nm.requests if "CR" in r.recognizedRawTokens]
    assert cr_reqs, "expected at least one CR request"
    for r in cr_reqs:
        assert MachineEffect.callPreferencePositive in r.machineEffects
        assert MachineEffect.sameDayHardBlock not in r.machineEffects, (
            f"CR alone must not trigger hard block (request: {r.rawRequestText!r}, "
            f"doctor={r.doctorId}, date={r.dateKey})"
        )

    # Blank request cells are CONSUMABLE no-ops — they emit a Request record
    # with empty token / class / effect sets per §9 / §10.
    blank_count = sum(1 for r in nm.requests if r.rawRequestText == "")
    assert blank_count > 0, "expected blank cells to materialize as no-effect Requests"

    # DailyEffectState — at least one doctor on at least one day fires
    # sameDayHardBlock (from any AL/NC/PM_OFF/EMCC).
    assert any(
        MachineEffect.sameDayHardBlock in de.effects for de in nm.dailyEffects
    ), "expected at least one sameDayHardBlock somewhere in daily effects"


# --- Negative case --------------------------------------------------------


def test_real_icu_hd_may_2026_corrupted_section_is_non_consumable() -> None:
    """Negative case: take the real snapshot, reassign one doctor's section
    to one not declared in the template; verify NON_CONSUMABLE per
    parser_normalizer §14 (canonical doctor group cannot be resolved)."""
    template = icu_hd_template_artifact()
    snapshot = _load_real_snapshot()

    # Move the first doctor into a ghost section.
    docs = list(snapshot.doctorRecords)
    docs[0] = replace(
        docs[0],
        sourceLocator=replace(
            docs[0].sourceLocator, sectionKey="GHOST_SECTION"
        ),
    )
    corrupted = replace(snapshot, doctorRecords=tuple(docs))

    result = parse(corrupted, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert result.normalizedModel is None
    codes = {i.code for i in result.issues}
    assert ISSUE_DOCTOR_SECTION_UNKNOWN in codes


def test_real_icu_hd_may_2026_corrupted_day_axis_is_non_consumable() -> None:
    """Negative case: drop the middle day record, breaking dayIndex contiguity
    per snapshot_contract.md §8 / parser_normalizer §13."""
    template = icu_hd_template_artifact()
    snapshot = _load_real_snapshot()

    middle = len(snapshot.dayRecords) // 2
    days = tuple(d for i, d in enumerate(snapshot.dayRecords) if i != middle)
    corrupted = replace(snapshot, dayRecords=days)

    result = parse(corrupted, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    codes = {i.code for i in result.issues}
    assert ISSUE_DAY_INDEX_NON_CONTIGUOUS in codes


# --- standalone runner ----------------------------------------------------


def _all_tests():
    return [
        v
        for k, v in globals().items()
        if k.startswith("test_") and callable(v)
    ]


def main() -> int:
    failures: list[tuple[str, BaseException]] = []
    passes = 0
    for fn in _all_tests():
        try:
            fn()
            passes += 1
            print(f"  PASS  {fn.__name__}")
        except BaseException as exc:
            failures.append((fn.__name__, exc))
            print(f"  FAIL  {fn.__name__}: {exc}", file=sys.stderr)

    total = passes + len(failures)
    print(f"\n{passes}/{total} passed")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
