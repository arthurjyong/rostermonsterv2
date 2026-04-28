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
    DailyEffectState,
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
    ISSUE_DAY_RAW_DATE_NOT_ISO,
    ISSUE_DOCTOR_KEY_DUPLICATE,
    ISSUE_DOCTOR_SECTION_UNKNOWN,
    ISSUE_HANDOFF_DAILY_EFFECT_DATE_ORPHAN,
    ISSUE_HANDOFF_DAILY_EFFECT_DOCTOR_ORPHAN,
    ISSUE_HANDOFF_DOCTOR_GROUP_ORPHAN,
    ISSUE_HANDOFF_FIXED_ASSIGNMENT_SLOT_ORPHAN,
    ISSUE_HANDOFF_REQUEST_DOCTOR_ORPHAN,
    ISSUE_HANDOFF_SLOT_DEMAND_INCOMPLETE,
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
from rostermonster.parser.scoring_overlay import (  # noqa: E402
    ISSUE_SCORING_CALL_POINT_MALFORMED,
    ISSUE_SCORING_COMPONENT_WEIGHT_MALFORMED,
    ISSUE_SCORING_COMPONENT_WEIGHT_MIS_SIGNED,
    ISSUE_SCORING_POINT_ROW_KEY_DUPLICATE,
    ISSUE_SCORING_POINT_ROW_SLOT_TYPE_DUPLICATE,
)
from rostermonster.snapshot import (  # noqa: E402
    CallPointLocator,
    CallPointRecord,
    ComponentWeightLocator,
    ComponentWeightRecord,
    DayLocator,
    DoctorLocator,
    PrefilledAssignmentLocator,
    RequestLocator,
    ScoringConfigRecords,
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


def test_handoff_consistency_check_catches_daily_effect_orphans() -> None:
    """parser_normalizer §17 — DailyEffectState with unknown doctorId or
    dateKey must surface as a handoff defect. Without this check, a parser
    regression in request → effect projection could ship CONSUMABLE with
    orphaned effect facts that downstream stages would silently consume."""
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
    doctors = (
        Doctor(
            doctorId="dr_a",
            displayName="Dr A",
            groupId="ICU_ONLY",
            provenance=DoctorLocator(sectionKey="MICU", doctorIndexInSection=0),
        ),
    )
    bad_model = NormalizedModel(
        period=period,
        doctors=doctors,
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
        dailyEffects=(
            DailyEffectState(
                doctorId="dr_ghost",  # orphan: not in doctors
                dateKey="2026-05-01",
                effects=(MachineEffect.sameDayHardBlock,),
                provenance=RequestLocator(sourceDoctorKey="dr_ghost", dayIndex=0),
            ),
            DailyEffectState(
                doctorId="dr_a",
                dateKey="2026-12-31",  # orphan: not in period.days
                effects=(MachineEffect.sameDayHardBlock,),
                provenance=RequestLocator(sourceDoctorKey="dr_a", dayIndex=99),
            ),
        ),
    )

    issues = _verify_handoff_consistency(bad_model)
    codes = {i.code for i in issues}
    assert ISSUE_HANDOFF_DAILY_EFFECT_DOCTOR_ORPHAN in codes
    assert ISSUE_HANDOFF_DAILY_EFFECT_DATE_ORPHAN in codes


def test_handoff_consistency_check_catches_slot_demand_incompleteness() -> None:
    """parser_normalizer §17 — SlotDemand must cover every (dateKey × slotType)
    pair implied by period.days × slotTypes. A normalization defect that drops
    a pair would otherwise silently slip past the per-record orphan checks and
    cause downstream solvers to under-allocate."""
    period = RosterPeriod(
        periodId="p1",
        periodLabel="P1",
        days=(
            RosterDay(
                dateKey="2026-05-01",
                dayIndex=0,
                provenance=DayLocator(dayIndex=0),
            ),
            RosterDay(
                dateKey="2026-05-02",
                dayIndex=1,
                provenance=DayLocator(dayIndex=1),
            ),
        ),
    )
    bad_model = NormalizedModel(
        period=period,
        doctors=(),
        doctorGroups=(DoctorGroup(groupId="ICU_ONLY"),),
        slotTypes=(
            SlotTypeDefinition(
                slotType="MICU_CALL",
                displayLabel="MICU Call",
                slotFamily="MICU",
                slotKind="CALL",
            ),
            SlotTypeDefinition(
                slotType="MICU_STANDBY",
                displayLabel="MICU Standby",
                slotFamily="MICU",
                slotKind="STANDBY",
            ),
        ),
        # Expected: 2 days × 2 slot types = 4 SlotDemand records.
        # Missing: (2026-05-02, MICU_STANDBY) — exactly the kind of pair drop
        # that the per-record orphan checks would not catch.
        slotDemand=(
            SlotDemand(
                dateKey="2026-05-01",
                slotType="MICU_CALL",
                requiredCount=1,
                provenance=DayLocator(dayIndex=0),
            ),
            SlotDemand(
                dateKey="2026-05-01",
                slotType="MICU_STANDBY",
                requiredCount=1,
                provenance=DayLocator(dayIndex=0),
            ),
            SlotDemand(
                dateKey="2026-05-02",
                slotType="MICU_CALL",
                requiredCount=1,
                provenance=DayLocator(dayIndex=1),
            ),
        ),
        eligibility=(
            EligibilityRule(slotType="MICU_CALL", eligibleGroups=("ICU_ONLY",)),
            EligibilityRule(
                slotType="MICU_STANDBY", eligibleGroups=("ICU_ONLY",)
            ),
        ),
    )

    issues = _verify_handoff_consistency(bad_model)
    incompleteness_issues = [
        i for i in issues if i.code == ISSUE_HANDOFF_SLOT_DEMAND_INCOMPLETE
    ]
    assert len(incompleteness_issues) == 1
    assert incompleteness_issues[0].context == {
        "dateKey": "2026-05-02",
        "slotType": "MICU_STANDBY",
    }


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


# --- scoring-config overlay (D-0037 / D-0038) ------------------------------


def _phys_ref():
    """Lazy import so overlay tests can construct snapshot records without
    pulling in the full fixtures module's `_physical_ref` private helper."""
    from rostermonster.snapshot import PhysicalSourceRef

    return PhysicalSourceRef(
        sheetName="CGH ICU/HD Call",
        sheetGid="0",
        a1Refs=("Z1",),
    )


def test_scoring_config_uses_template_defaults_when_no_operator_overrides() -> None:
    """Per `parser_normalizer_contract.md` §9 backstop rule: when the
    snapshot's `scoringConfigRecords` is empty (operator hasn't edited the
    Scorer Config tab), the parser overlay fills `ScoringConfig` purely
    from template defaults. Per D-0038 the resulting `pointRules` MUST
    cover the full (call-slot × period day) cross-product."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    result = parse(snapshot, template)

    assert result.consumability is Consumability.CONSUMABLE
    cfg = result.scoringConfig
    assert cfg is not None, "CONSUMABLE result MUST carry a scoringConfig per §9"

    # weights map matches template defaults.
    for component, default in template.componentWeights.items():
        assert cfg.weights[component] == default

    # pointRules cover the full cross-product (D-0038 producer coverage).
    call_slot_types = {
        st.slotType for st in result.normalizedModel.slotTypes if st.slotKind == "CALL"
    }
    expected_keys = {
        (slot_type, day.dateKey)
        for slot_type in call_slot_types
        for day in result.normalizedModel.period.days
    }
    assert set(cfg.pointRules.keys()) == expected_keys, (
        "pointRules must cover the full call-slot × day cross-product per "
        "D-0038; missing or extra keys"
    )


def test_scoring_config_weekday_weekend_defaults_match_template_rule() -> None:
    """Per `template_artifact_contract.md` §9: pointRow defaultRule values
    are 1.0 / 1.75 / 2.0 / 1.5 keyed by `(this_day, next_day)` weekday-vs-
    weekend classification. Verify the parser overlay applies them
    correctly using calendar dates."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    result = parse(snapshot, template)
    cfg = result.scoringConfig
    assert cfg is not None
    # icu_hd_snapshot() uses dateKeys 2026-05-01 (Fri), 02 (Sat), 03 (Sun),
    # 04 (Mon), 05 (Tue). Expected weights for MICU_CALL:
    #   Fri → Sat = weekday → weekend       → 1.75
    #   Sat → Sun = weekend → weekend       → 2.0
    #   Sun → Mon = weekend → weekday       → 1.5
    #   Mon → Tue = weekday → weekday       → 1.0
    #   Tue → Wed = weekday → weekday       → 1.0
    expected = {
        ("MICU_CALL", "2026-05-01"): 1.75,
        ("MICU_CALL", "2026-05-02"): 2.0,
        ("MICU_CALL", "2026-05-03"): 1.5,
        ("MICU_CALL", "2026-05-04"): 1.0,
        ("MICU_CALL", "2026-05-05"): 1.0,
    }
    for key, want in expected.items():
        assert cfg.pointRules[key] == want, (
            f"expected pointRules[{key}] = {want} per template defaultRule "
            f"weekday/weekend mapping; got {cfg.pointRules[key]}"
        )


def test_operator_component_weight_override_flows_through_overlay() -> None:
    """Per §9 sheet-wins rule: a populated, parseable, sign-correct
    operator weight cell MUST override the template default."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    snapshot = replace(
        snapshot,
        scoringConfigRecords=ScoringConfigRecords(
            componentWeightRecords=(
                ComponentWeightRecord(
                    componentId="crReward",
                    rawValue="7.5",
                    sourceLocator=ComponentWeightLocator(componentId="crReward"),
                    physicalSourceRef=_phys_ref(),
                ),
            ),
        ),
    )
    result = parse(snapshot, template)
    assert result.consumability is Consumability.CONSUMABLE
    assert result.scoringConfig.weights["crReward"] == 7.5
    # Other components still use template defaults.
    assert result.scoringConfig.weights["unfilledPenalty"] == -100.0


def test_blank_operator_weight_falls_back_to_template_default() -> None:
    """Per §9: a record with empty / whitespace-only `rawValue` is treated
    as "absent" and falls back to template default — distinct from a
    populated-but-malformed cell, which is admission-blocking."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    snapshot = replace(
        snapshot,
        scoringConfigRecords=ScoringConfigRecords(
            componentWeightRecords=(
                ComponentWeightRecord(
                    componentId="crReward",
                    rawValue="   ",  # whitespace-only → blank
                    sourceLocator=ComponentWeightLocator(componentId="crReward"),
                    physicalSourceRef=_phys_ref(),
                ),
            ),
        ),
    )
    result = parse(snapshot, template)
    assert result.consumability is Consumability.CONSUMABLE
    assert result.scoringConfig.weights["crReward"] == template.componentWeights["crReward"]


def test_mis_signed_operator_weight_is_non_consumable() -> None:
    """Per parser_normalizer §14: an operator-edited penalty given a
    positive value (or reward given a negative value) violates the
    component's sign orientation per scorer §10 / §15 and is admission-
    blocking. Penalty must be ≤ 0; reward must be ≥ 0."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    snapshot = replace(
        snapshot,
        scoringConfigRecords=ScoringConfigRecords(
            componentWeightRecords=(
                ComponentWeightRecord(
                    componentId="unfilledPenalty",
                    rawValue="42",  # penalty given POSITIVE → mis-signed
                    sourceLocator=ComponentWeightLocator(componentId="unfilledPenalty"),
                    physicalSourceRef=_phys_ref(),
                ),
            ),
        ),
    )
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert ISSUE_SCORING_COMPONENT_WEIGHT_MIS_SIGNED in _issue_codes(result)


def test_malformed_operator_weight_is_non_consumable() -> None:
    """Per §14: a populated but non-numeric `rawValue` is admission-
    blocking (parser must not silently substitute a default)."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    snapshot = replace(
        snapshot,
        scoringConfigRecords=ScoringConfigRecords(
            componentWeightRecords=(
                ComponentWeightRecord(
                    componentId="crReward",
                    rawValue="not-a-number",
                    sourceLocator=ComponentWeightLocator(componentId="crReward"),
                    physicalSourceRef=_phys_ref(),
                ),
            ),
        ),
    )
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert ISSUE_SCORING_COMPONENT_WEIGHT_MALFORMED in _issue_codes(result)


def test_operator_per_day_call_point_override_flows_through_overlay() -> None:
    """Per §9: a populated callPointRecord overrides the template default
    for that specific (callPointRowKey, dayIndex). Result is reflected in
    `pointRules[(slotType, dateKey)]` via the slotType binding declared
    in template_artifact §9."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    snapshot = replace(
        snapshot,
        scoringConfigRecords=ScoringConfigRecords(
            callPointRecords=(
                CallPointRecord(
                    callPointRowKey="MICU_CALL_POINT",
                    dayIndex=0,  # 2026-05-01 (Fri) — template default 1.75
                    rawValue="3.0",
                    sourceLocator=CallPointLocator(
                        callPointRowKey="MICU_CALL_POINT", dayIndex=0
                    ),
                    physicalSourceRef=_phys_ref(),
                ),
            ),
        ),
    )
    result = parse(snapshot, template)
    assert result.consumability is Consumability.CONSUMABLE
    # Operator override applied via slotType binding (MICU_CALL_POINT → MICU_CALL).
    assert result.scoringConfig.pointRules[("MICU_CALL", "2026-05-01")] == 3.0
    # Other days still use template defaults (Sat = 2.0).
    assert result.scoringConfig.pointRules[("MICU_CALL", "2026-05-02")] == 2.0


def test_malformed_call_point_cell_is_non_consumable() -> None:
    """Per §14: a populated but non-numeric callPoint `rawValue` is
    admission-blocking (parser must not silently substitute a default)."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    snapshot = replace(
        snapshot,
        scoringConfigRecords=ScoringConfigRecords(
            callPointRecords=(
                CallPointRecord(
                    callPointRowKey="MICU_CALL_POINT",
                    dayIndex=0,
                    rawValue="oops",
                    sourceLocator=CallPointLocator(
                        callPointRowKey="MICU_CALL_POINT", dayIndex=0
                    ),
                    physicalSourceRef=_phys_ref(),
                ),
            ),
        ),
    )
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert ISSUE_SCORING_CALL_POINT_MALFORMED in _issue_codes(result)


def test_non_iso_raw_date_is_non_consumable() -> None:
    """Per Codex P1 round-1 finding on PR #88 + D-0033: snapshot adapter
    normalizes dates to ISO 8601; if a malformed raw date reaches the
    parser, downstream consumers (rule engine `_shift_iso_date`, scoring
    overlay `_default_point_for_day`) would crash with `ValueError`. The
    parser MUST validate ISO format at admission and surface non-ISO
    values as NON_CONSUMABLE through the normal admission channel."""
    snapshot = icu_hd_snapshot()
    template = icu_hd_template_artifact()
    # Replace one day's rawDateText with a garbage string. Other days
    # remain valid so we isolate the ISO-validation behavior.
    bad_days = list(snapshot.dayRecords)
    bad_days[0] = replace(bad_days[0], rawDateText="not-a-date")
    snapshot = replace(snapshot, dayRecords=tuple(bad_days))
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert ISSUE_DAY_RAW_DATE_NOT_ISO in _issue_codes(result)


def test_non_finite_operator_weight_is_non_consumable() -> None:
    """Per Codex P1 round-2 finding on PR #88: `float()` accepts non-finite
    literals like 'inf', '-inf', 'nan', and overflowed numerics like
    '1e309'. Sign-orientation only checks the operator, so a non-finite
    weight would propagate to `score()` as non-finite totals and dominate
    candidate ordering. Surface as malformed instead."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    for raw in ("inf", "-inf", "nan", "1e309"):
        bad_snapshot = replace(
            snapshot,
            scoringConfigRecords=ScoringConfigRecords(
                componentWeightRecords=(
                    ComponentWeightRecord(
                        componentId="crReward",
                        rawValue=raw,
                        sourceLocator=ComponentWeightLocator(componentId="crReward"),
                        physicalSourceRef=_phys_ref(),
                    ),
                ),
            ),
        )
        result = parse(bad_snapshot, template)
        assert result.consumability is Consumability.NON_CONSUMABLE, (
            f"non-finite weight rawValue {raw!r} should be NON_CONSUMABLE; "
            f"got {result.consumability!r}"
        )
        assert ISSUE_SCORING_COMPONENT_WEIGHT_MALFORMED in _issue_codes(result)


def test_non_finite_call_point_cell_is_non_consumable() -> None:
    """Per Codex P1 round-2 finding on PR #88: same finite-numeric
    requirement applies to call-point cells. A non-finite pointRules
    entry would make `pointBalance*` components (and totals) non-finite."""
    template = icu_hd_template_artifact()
    snapshot = icu_hd_snapshot()
    for raw in ("inf", "nan", "1e309"):
        bad_snapshot = replace(
            snapshot,
            scoringConfigRecords=ScoringConfigRecords(
                callPointRecords=(
                    CallPointRecord(
                        callPointRowKey="MICU_CALL_POINT",
                        dayIndex=0,
                        rawValue=raw,
                        sourceLocator=CallPointLocator(
                            callPointRowKey="MICU_CALL_POINT", dayIndex=0
                        ),
                        physicalSourceRef=_phys_ref(),
                    ),
                ),
            ),
        )
        result = parse(bad_snapshot, template)
        assert result.consumability is Consumability.NON_CONSUMABLE, (
            f"non-finite call-point rawValue {raw!r} should be "
            f"NON_CONSUMABLE; got {result.consumability!r}"
        )
        assert ISSUE_SCORING_CALL_POINT_MALFORMED in _issue_codes(result)


def test_duplicate_point_row_key_is_non_consumable() -> None:
    """Per Codex P2 round-2 finding on PR #88: duplicate `pointRows[].rowKey`
    declarations would silently overwrite earlier entries; one row's
    defaults/overrides could be applied to multiple slot bindings without
    any admission error. Surface as NON_CONSUMABLE."""
    from rostermonster.template_artifact import PointRowDefinition

    template = icu_hd_template_artifact()
    # Add a second pointRow that uses the same rowKey but different slotType
    # to isolate the rowKey-duplicate path (vs slotType-duplicate path).
    duplicate_row = PointRowDefinition(
        rowKey=template.pointRows[0].rowKey,  # MICU_CALL_POINT
        slotType="MHD_CALL",
        label="Bogus duplicate row",
        defaultRule=template.pointRows[0].defaultRule,
    )
    template = replace(template, pointRows=template.pointRows + (duplicate_row,))
    snapshot = icu_hd_snapshot()
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert ISSUE_SCORING_POINT_ROW_KEY_DUPLICATE in _issue_codes(result)


def test_duplicate_point_row_slot_type_is_non_consumable() -> None:
    """Per Codex P2 round-1 finding on PR #88 + template_artifact §9: each
    call slot has at most one pointRow. Duplicate `pointRows[].slotType`
    bindings would silently overwrite earlier rows in the slotType→rowKey
    mapping; populated `callPointRecords` for the overwritten row would
    look structurally valid but never be applied. Surface as
    NON_CONSUMABLE rather than silently-wrong scoring."""
    template = icu_hd_template_artifact()
    # Add a second pointRow that binds to the same slotType as MICU_CALL_POINT.
    duplicate_row = template.pointRows[0]  # MICU_CALL_POINT
    extra = replace(duplicate_row, rowKey="MICU_CALL_POINT_ALIAS")
    template = replace(template, pointRows=template.pointRows + (extra,))
    snapshot = icu_hd_snapshot()
    result = parse(snapshot, template)
    assert result.consumability is Consumability.NON_CONSUMABLE
    assert ISSUE_SCORING_POINT_ROW_SLOT_TYPE_DUPLICATE in _issue_codes(result)


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
