"""Parser admission tests — positive + negative cases for ICU/HD first release.

Pytest-compatible (each `test_*` function works as a discovered test). Also
runnable directly with `python3 tests/test_parser.py` — the `__main__` block
calls every `test_*` function and reports pass/fail counts. Exit code is 0
on full pass, 1 on any failure.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

# Allow running this file directly via `python3 tests/test_parser.py`
# from the `python/` directory (sys.path then includes the test file's
# directory, not the package root).
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rostermonster.domain import (  # noqa: E402  (import after sys.path)
    CanonicalRequestClass,
    Doctor,
    DoctorGroup,
    EligibilityRule,
    MachineEffect,
    NormalizedModel,
    RosterDay,
    RosterPeriod,
    SlotDemand,
    SlotTypeDefinition,
)
from rostermonster.parser import (  # noqa: E402
    Consumability,
    IssueSeverity,
    parse,
)
from rostermonster.parser.admission import (  # noqa: E402
    ISSUE_DAY_INDEX_NON_CONTIGUOUS,
    ISSUE_DOCTOR_KEY_DUPLICATE,
    ISSUE_DOCTOR_SECTION_UNKNOWN,
    ISSUE_HANDOFF_DOCTOR_GROUP_ORPHAN,
    ISSUE_HANDOFF_FIXED_ASSIGNMENT_SLOT_ORPHAN,
    ISSUE_HANDOFF_REQUEST_DOCTOR_ORPHAN,
    ISSUE_PREFILLED_DOCTOR_NAME_AMBIGUOUS,
    ISSUE_PREFILLED_DOCTOR_NAME_UNRESOLVED,
    ISSUE_PREFILLED_DOCTOR_TWO_SLOTS_SAME_DAY,
    ISSUE_PREFILLED_SURFACE_UNKNOWN,
    ISSUE_REQUEST_DOCTOR_REF_BROKEN,
    ISSUE_TEMPLATE_MISMATCH,
    _verify_handoff_consistency,
)
from rostermonster.parser.request_semantics import (  # noqa: E402
    ISSUE_REQUEST_DUPLICATE_TOKEN,
    ISSUE_REQUEST_MALFORMED_GRAMMAR,
    ISSUE_REQUEST_UNKNOWN_TOKEN,
)
from rostermonster.snapshot import (  # noqa: E402
    DayLocator,
    DoctorLocator,
    PrefilledAssignmentLocator,
    RequestLocator,
)
from tests.fixtures import (  # noqa: E402
    icu_hd_snapshot,
    icu_hd_template_artifact,
    with_ambiguous_prefill_doctor,
    with_duplicate_doctor_key,
    with_malformed_request_grammar,
    with_non_contiguous_day_index,
    with_prefill_doctor_two_slots_same_day,
    with_prefill_into_unknown_surface,
    with_prefill_using_messy_whitespace_and_case,
    with_request_referencing_unknown_doctor,
    with_unknown_doctor_section,
    with_unknown_request_token,
    with_unresolved_prefill_doctor,
)


# --- helpers ---------------------------------------------------------------


def _issue_codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


def _has_issue_with(result, code: str, severity: IssueSeverity) -> bool:
    return any(
        issue.code == code and issue.severity is severity for issue in result.issues
    )


# --- positive cases --------------------------------------------------------


def test_minimal_valid_snapshot_is_consumable() -> None:
    """A minimal valid ICU/HD snapshot lands at CONSUMABLE with the
    normalizedModel populated end-to-end."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    result = parse(snapshot, template)

    assert result.consumability is Consumability.CONSUMABLE, (
        f"expected CONSUMABLE, got {result.consumability!r} with issues "
        f"{_issue_codes(result)}"
    )
    assert result.normalizedModel is not None

    nm = result.normalizedModel
    assert nm.period.periodId == "2026-05"
    assert len(nm.period.days) == 5
    assert len(nm.doctors) == 6
    assert len(nm.doctorGroups) == 3
    assert len(nm.slotTypes) == 4
    # 5 days * 4 slots = 20 demand units, all requiredCount=1.
    assert len(nm.slotDemand) == 20
    assert all(sd.requiredCount == 1 for sd in nm.slotDemand)
    assert len(nm.eligibility) == 4

    # CR on day 0 for Dr Alpha → callPreferencePositive on dailyEffects.
    cr_day0 = next(
        (
            de
            for de in nm.dailyEffects
            if de.doctorId == "micu_dr_a" and de.dateKey == "2026-05-01"
        ),
        None,
    )
    assert cr_day0 is not None, "expected dailyEffect for Dr Alpha on day 0"
    assert MachineEffect.callPreferencePositive in cr_day0.effects

    # AL on day 2 → FULL_DAY_OFF → sameDayHardBlock + prevDayCallSoftPenaltyTrigger.
    al_day2 = next(
        (
            de
            for de in nm.dailyEffects
            if de.doctorId == "micu_dr_a" and de.dateKey == "2026-05-03"
        ),
        None,
    )
    assert al_day2 is not None
    assert MachineEffect.sameDayHardBlock in al_day2.effects
    assert MachineEffect.prevDayCallSoftPenaltyTrigger in al_day2.effects

    # Prefilled assignment for Dr Foxtrot resolves into a FixedAssignment.
    assert len(nm.fixedAssignments) == 1
    fa = nm.fixedAssignments[0]
    assert fa.doctorId == "mhd_dr_f"
    assert fa.slotType == "MHD_CALL"
    assert fa.dateKey == "2026-05-04"


def test_duplicate_recognized_tokens_emits_warning_but_stays_consumable() -> None:
    """`NC, NC` triggers a non-blocking warning per request_semantics §12 but
    the snapshot remains CONSUMABLE."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    result = parse(snapshot, template)
    assert result.consumability is Consumability.CONSUMABLE
    assert _has_issue_with(
        result, ISSUE_REQUEST_DUPLICATE_TOKEN, IssueSeverity.WARNING
    )


def test_request_parse_issues_mirror_onto_normalized_request() -> None:
    """parser_normalizer §10 rule 4 — request parse issues must also appear on
    the relevant normalized Request when a normalized Request exists in a
    CONSUMABLE output. The top-level channel remains authoritative."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    result = parse(snapshot, template)
    assert result.consumability is Consumability.CONSUMABLE

    # The duplicate-token request is Dr Charlie's `NC, NC` on day 1.
    charlie_day1 = next(
        (
            r
            for r in result.normalizedModel.requests
            if r.doctorId == "icuhd_dr_c" and r.dateKey == "2026-05-02"
        ),
        None,
    )
    assert charlie_day1 is not None, "expected normalized Request for Dr Charlie day 1"
    mirrored_codes = {issue.code for issue in charlie_day1.parseIssues}
    assert ISSUE_REQUEST_DUPLICATE_TOKEN in mirrored_codes, (
        f"expected duplicate-token issue mirrored onto Request; got "
        f"{mirrored_codes}"
    )

    # Top-level remains authoritative (§10 rule 1).
    assert _has_issue_with(
        result, ISSUE_REQUEST_DUPLICATE_TOKEN, IssueSeverity.WARNING
    )

    # Requests with no warnings have empty parseIssues.
    alpha_day0 = next(
        r for r in result.normalizedModel.requests
        if r.doctorId == "micu_dr_a" and r.dateKey == "2026-05-01"
    )
    assert alpha_day0.parseIssues == ()


def test_slot_type_definition_carries_display_label() -> None:
    """domain_model.md §7.6 — SlotTypeDefinition first-release minimum required
    fields are `slotType` + `displayLabel`. Verify both are populated from the
    template artifact's slot record."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    result = parse(snapshot, template)
    assert result.consumability is Consumability.CONSUMABLE
    nm = result.normalizedModel

    by_slot = {st.slotType: st for st in nm.slotTypes}
    assert by_slot["MICU_CALL"].displayLabel == "MICU Call"
    assert by_slot["MICU_STANDBY"].displayLabel == "MICU Standby"
    assert by_slot["MHD_CALL"].displayLabel == "MHD Call"
    assert by_slot["MHD_STANDBY"].displayLabel == "MHD Standby"


def test_provenance_traces_back_to_snapshot_locators() -> None:
    """parser_normalizer §16 — snapshot-derived entities carry recoverable
    linkage back to origin records/locators. Verify provenance is populated
    on Doctor / RosterDay / Request / FixedAssignment / DailyEffectState /
    SlotDemand and matches the corresponding snapshot locator."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    result = parse(snapshot, template)
    assert result.consumability is Consumability.CONSUMABLE
    nm = result.normalizedModel

    # Doctor.provenance — DoctorLocator.
    alpha = next(d for d in nm.doctors if d.doctorId == "micu_dr_a")
    assert isinstance(alpha.provenance, DoctorLocator)
    assert alpha.provenance.sectionKey == "MICU"
    assert alpha.provenance.doctorIndexInSection == 0

    # RosterDay.provenance — DayLocator.
    day0 = next(d for d in nm.period.days if d.dayIndex == 0)
    assert isinstance(day0.provenance, DayLocator)
    assert day0.provenance.dayIndex == 0

    # SlotDemand.provenance — DayLocator (per-day side of template×day product).
    sd_day0_call = next(
        sd
        for sd in nm.slotDemand
        if sd.dateKey == "2026-05-01" and sd.slotType == "MICU_CALL"
    )
    assert isinstance(sd_day0_call.provenance, DayLocator)
    assert sd_day0_call.provenance.dayIndex == 0

    # Request.provenance — RequestLocator.
    cr_req = next(
        r
        for r in nm.requests
        if r.doctorId == "micu_dr_a" and r.dateKey == "2026-05-01"
    )
    assert isinstance(cr_req.provenance, RequestLocator)
    assert cr_req.provenance.sourceDoctorKey == "micu_dr_a"
    assert cr_req.provenance.dayIndex == 0

    # DailyEffectState.provenance — same RequestLocator as the originating Request.
    al_de = next(
        de
        for de in nm.dailyEffects
        if de.doctorId == "micu_dr_a" and de.dateKey == "2026-05-03"
    )
    assert isinstance(al_de.provenance, RequestLocator)
    assert al_de.provenance.sourceDoctorKey == "micu_dr_a"
    assert al_de.provenance.dayIndex == 2

    # FixedAssignment.provenance — PrefilledAssignmentLocator.
    fa = nm.fixedAssignments[0]
    assert isinstance(fa.provenance, PrefilledAssignmentLocator)
    assert fa.provenance.surfaceId == "lowerRosterAssignments"
    assert fa.provenance.rowOffset == 2
    assert fa.provenance.dayIndex == 3


def test_handoff_consistency_check_catches_internal_defects() -> None:
    """parser_normalizer §17 — the internal handoff-consistency defense layer
    fires when a malformed NormalizedModel reaches it (parser-internal defect,
    not a snapshot/template issue). Constructing a model with orphan
    references directly bypasses normal admission and exercises the backstop."""
    period = RosterPeriod(
        periodId="p1",
        periodLabel="P1",
        days=(
            RosterDay(
                dateKey="2026-05-01",
                dayIndex=0,
                provenance=DayLocator(dayIndex=0),
            ),
        ),
    )
    bad_model = NormalizedModel(
        period=period,
        doctors=(
            Doctor(
                doctorId="dr_a",
                displayName="Dr A",
                groupId="GHOST_GROUP",  # orphan: not in doctorGroups
                provenance=DoctorLocator(
                    sectionKey="MICU", doctorIndexInSection=0
                ),
            ),
        ),
        doctorGroups=(DoctorGroup(groupId="ICU_ONLY"),),
        slotTypes=(
            SlotTypeDefinition(
                slotType="MICU_CALL",
                displayLabel="MICU Call",
                slotFamily="MICU",
                slotKind="CALL",
            ),
        ),
        slotDemand=(
            SlotDemand(
                dateKey="2026-05-01",
                slotType="MICU_CALL",
                requiredCount=1,
                provenance=DayLocator(dayIndex=0),
            ),
        ),
        eligibility=(
            EligibilityRule(slotType="MICU_CALL", eligibleGroups=("ICU_ONLY",)),
        ),
    )

    issues = _verify_handoff_consistency(bad_model)
    codes = {i.code for i in issues}
    assert ISSUE_HANDOFF_DOCTOR_GROUP_ORPHAN in codes


def test_canonical_classes_are_deterministically_ordered() -> None:
    """Request `EXAM, NC` should canonicalize to FULL_DAY_OFF + NC in alphabetical
    order per request_semantics_contract.md §15."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    first_req = snapshot.requestRecords[0]
    mutated_first = replace(first_req, rawRequestText="EXAM, NC")
    snapshot = replace(
        snapshot,
        requestRecords=(mutated_first,) + snapshot.requestRecords[1:],
    )
    result = parse(snapshot, template)
    assert result.consumability is Consumability.CONSUMABLE
    req = next(
        (r for r in result.normalizedModel.requests if r.doctorId == "micu_dr_a" and r.dateKey == "2026-05-01"),
        None,
    )
    assert req is not None
    # Sorted by enum.value: CR < FULL_DAY_OFF < NC < PM_OFF.
    assert req.canonicalClasses == (
        CanonicalRequestClass.FULL_DAY_OFF,
        CanonicalRequestClass.NC,
    )


# --- negative cases — §13 structural ---------------------------------------


def test_template_mismatch_is_non_consumable() -> None:
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    snapshot = replace(
        snapshot,
        metadata=replace(snapshot.metadata, templateId="other_template"),
    )
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert result.normalizedModel is None
    assert ISSUE_TEMPLATE_MISMATCH in _issue_codes(result)


def test_duplicate_doctor_key_is_non_consumable() -> None:
    template = icu_hd_template_artifact()
    snapshot = with_duplicate_doctor_key(icu_hd_snapshot())
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert result.normalizedModel is None
    assert ISSUE_DOCTOR_KEY_DUPLICATE in _issue_codes(result)


def test_non_contiguous_day_index_is_non_consumable() -> None:
    template = icu_hd_template_artifact()
    snapshot = with_non_contiguous_day_index(icu_hd_snapshot())
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert ISSUE_DAY_INDEX_NON_CONTIGUOUS in _issue_codes(result)


def test_request_referencing_unknown_doctor_is_non_consumable() -> None:
    template = icu_hd_template_artifact()
    snapshot = with_request_referencing_unknown_doctor(icu_hd_snapshot())
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert ISSUE_REQUEST_DOCTOR_REF_BROKEN in _issue_codes(result)


# --- negative cases — §14 semantic -----------------------------------------


def test_unknown_doctor_section_is_non_consumable() -> None:
    template = icu_hd_template_artifact()
    snapshot = with_unknown_doctor_section(icu_hd_snapshot())
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert ISSUE_DOCTOR_SECTION_UNKNOWN in _issue_codes(result)


def test_malformed_request_grammar_is_non_consumable() -> None:
    """Slash delimiter per request_semantics_contract.md §6 / §13."""
    template = icu_hd_template_artifact()
    snapshot = with_malformed_request_grammar(icu_hd_snapshot())
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert ISSUE_REQUEST_MALFORMED_GRAMMAR in _issue_codes(result)


def test_unknown_request_token_is_non_consumable() -> None:
    """Unknown token in mixed known+unknown content per §13."""
    template = icu_hd_template_artifact()
    snapshot = with_unknown_request_token(icu_hd_snapshot())
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert ISSUE_REQUEST_UNKNOWN_TOKEN in _issue_codes(result)


# --- negative cases — §14 prefilled-assignment specifics -------------------


def test_unresolved_prefill_doctor_is_non_consumable() -> None:
    template = icu_hd_template_artifact()
    snapshot = with_unresolved_prefill_doctor(icu_hd_snapshot())
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert ISSUE_PREFILLED_DOCTOR_NAME_UNRESOLVED in _issue_codes(result)


def test_ambiguous_prefill_doctor_is_non_consumable() -> None:
    template = icu_hd_template_artifact()
    snapshot = with_ambiguous_prefill_doctor(icu_hd_snapshot())
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert ISSUE_PREFILLED_DOCTOR_NAME_AMBIGUOUS in _issue_codes(result)


def test_prefill_unknown_surface_is_non_consumable() -> None:
    template = icu_hd_template_artifact()
    snapshot = with_prefill_into_unknown_surface(icu_hd_snapshot())
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert ISSUE_PREFILLED_SURFACE_UNKNOWN in _issue_codes(result)


def test_prefill_with_messy_whitespace_and_case_resolves_per_d0034() -> None:
    """D-0034 — doctor-name matching applies trim + internal-whitespace-collapse
    + casefold on both sides of the comparison. `   dr   foxtrot  ` resolves
    to `Dr Foxtrot`."""
    template = icu_hd_template_artifact()
    snapshot = with_prefill_using_messy_whitespace_and_case(icu_hd_snapshot())
    result = parse(snapshot, template)
    assert result.consumability is Consumability.CONSUMABLE, (
        f"expected CONSUMABLE per D-0034 normalization; got {result.consumability!r} "
        f"with issues {_issue_codes(result)}"
    )
    assert len(result.normalizedModel.fixedAssignments) == 1
    assert result.normalizedModel.fixedAssignments[0].doctorId == "mhd_dr_f"


def test_prefill_doctor_two_slots_same_day_is_non_consumable() -> None:
    template = icu_hd_template_artifact()
    snapshot = with_prefill_doctor_two_slots_same_day(icu_hd_snapshot())
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert ISSUE_PREFILLED_DOCTOR_TWO_SLOTS_SAME_DAY in _issue_codes(result)


# --- standalone runner -----------------------------------------------------


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
        except BaseException as exc:  # noqa: BLE001 — capture for reporting
            failures.append((fn.__name__, exc))
            print(f"  FAIL  {fn.__name__}: {exc}", file=sys.stderr)

    total = passes + len(failures)
    print(f"\n{passes}/{total} passed")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
