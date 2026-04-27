"""Tests for the rule engine implementation per `docs/rule_engine_contract.md`.

Covers each of the five first-release hard rules positively (rule passes
when it should) and negatively (rule fires when it should), plus the §12
canonical-ordering rule when multiple violations co-fire, plus the §15
FixedAssignment-as-neighbor case (rule engine fires BACK_TO_BACK_CALL
against a fixed call exactly as it would against a solver-placed call),
plus the §17 / §13 statelessness/determinism property.

Standalone runnable via `python3 python/tests/test_rule_engine.py` (no
pytest dependency) and pytest-discoverable.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rostermonster.domain import (  # noqa: E402
    AssignmentUnit,
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
from rostermonster.rule_engine import (  # noqa: E402
    CANONICAL_ORDER,
    Decision,
    RULE_BACK_TO_BACK_CALL,
    RULE_BASELINE_ELIGIBILITY_FAIL,
    RULE_SAME_DAY_ALREADY_HELD,
    RULE_SAME_DAY_HARD_BLOCK,
    RULE_UNIT_ALREADY_FILLED,
    RuleState,
    evaluate,
)
from rostermonster.snapshot import (  # noqa: E402
    DayLocator,
    DoctorLocator,
    RequestLocator,
)


# --- Minimal NormalizedModel builder for rule-engine unit tests ----------


def _minimal_model() -> NormalizedModel:
    """A small ICU/HD-shaped NormalizedModel sufficient for rule-engine tests.

    - 3 days (2026-05-01 to 2026-05-03), all contiguous.
    - 4 slot types (MICU_CALL/STANDBY, MHD_CALL/STANDBY); CALL slotKind drives
      BACK_TO_BACK_CALL.
    - 3 doctors: dr_icu (ICU_ONLY), dr_both (ICU_HD), dr_hd (HD_ONLY).
    - 3 groups, 4 eligibility rules matching the ICU/HD template specimen.
    - No DailyEffectState by default; tests opt in to hard blocks.
    """
    days = tuple(
        RosterDay(
            dateKey=f"2026-05-{i + 1:02d}",
            dayIndex=i,
            provenance=DayLocator(dayIndex=i),
        )
        for i in range(3)
    )
    period = RosterPeriod(
        periodId="2026-05",
        periodLabel="May 2026",
        days=days,
    )
    doctors = (
        Doctor(
            doctorId="dr_icu",
            displayName="Dr ICU",
            groupId="ICU_ONLY",
            provenance=DoctorLocator(sectionKey="MICU", doctorIndexInSection=0),
        ),
        Doctor(
            doctorId="dr_both",
            displayName="Dr Both",
            groupId="ICU_HD",
            provenance=DoctorLocator(sectionKey="MICU_HD", doctorIndexInSection=0),
        ),
        Doctor(
            doctorId="dr_hd",
            displayName="Dr HD",
            groupId="HD_ONLY",
            provenance=DoctorLocator(sectionKey="MHD", doctorIndexInSection=0),
        ),
    )
    groups = (
        DoctorGroup(groupId="ICU_ONLY"),
        DoctorGroup(groupId="ICU_HD"),
        DoctorGroup(groupId="HD_ONLY"),
    )
    slot_types = (
        SlotTypeDefinition(slotType="MICU_CALL", displayLabel="MICU Call", slotFamily="MICU", slotKind="CALL"),
        SlotTypeDefinition(slotType="MICU_STANDBY", displayLabel="MICU Standby", slotFamily="MICU", slotKind="STANDBY"),
        SlotTypeDefinition(slotType="MHD_CALL", displayLabel="MHD Call", slotFamily="MHD", slotKind="CALL"),
        SlotTypeDefinition(slotType="MHD_STANDBY", displayLabel="MHD Standby", slotFamily="MHD", slotKind="STANDBY"),
    )
    slot_demand = tuple(
        SlotDemand(
            dateKey=day.dateKey,
            slotType=st.slotType,
            requiredCount=1,
            provenance=DayLocator(dayIndex=day.dayIndex),
        )
        for day in days
        for st in slot_types
    )
    eligibility = (
        EligibilityRule(slotType="MICU_CALL", eligibleGroups=("ICU_ONLY", "ICU_HD")),
        EligibilityRule(slotType="MICU_STANDBY", eligibleGroups=("ICU_ONLY", "ICU_HD")),
        EligibilityRule(slotType="MHD_CALL", eligibleGroups=("ICU_HD", "HD_ONLY")),
        EligibilityRule(slotType="MHD_STANDBY", eligibleGroups=("ICU_HD", "HD_ONLY")),
    )
    return NormalizedModel(
        period=period,
        doctors=doctors,
        doctorGroups=groups,
        slotTypes=slot_types,
        slotDemand=slot_demand,
        eligibility=eligibility,
    )


def _propose(doctor_id: str, slot: str, date_key: str, unit_index: int = 0) -> AssignmentUnit:
    return AssignmentUnit(
        dateKey=date_key,
        slotType=slot,
        unitIndex=unit_index,
        doctorId=doctor_id,
    )


def _placed(doctor_id: str | None, slot: str, date_key: str, unit_index: int = 0) -> AssignmentUnit:
    return AssignmentUnit(
        dateKey=date_key,
        slotType=slot,
        unitIndex=unit_index,
        doctorId=doctor_id,
    )


def _codes(decision: Decision) -> list[str]:
    return [r.code for r in decision.reasons]


# --- Positive: clean placement admits ------------------------------------


def test_clean_placement_admits() -> None:
    """A doctor-eligible, no-conflict placement on an empty ruleState produces
    Decision(valid=True, reasons=())."""
    model = _minimal_model()
    state = RuleState.empty()
    proposed = _propose("dr_icu", "MICU_CALL", "2026-05-01")
    decision = evaluate(model, state, proposed)
    assert decision.valid
    assert decision.reasons == ()


# --- Per-rule negative tests ---------------------------------------------


def test_baseline_eligibility_fail_fires() -> None:
    """HD-only doctor proposed for MICU_CALL — eligibility list excludes them."""
    model = _minimal_model()
    state = RuleState.empty()
    proposed = _propose("dr_hd", "MICU_CALL", "2026-05-01")
    decision = evaluate(model, state, proposed)
    assert not decision.valid
    assert RULE_BASELINE_ELIGIBILITY_FAIL in _codes(decision)


def test_same_day_hard_block_fires() -> None:
    """Doctor with sameDayHardBlock fired on the date proposed."""
    model = _minimal_model()
    model = replace(
        model,
        dailyEffects=(
            DailyEffectState(
                doctorId="dr_icu",
                dateKey="2026-05-01",
                effects=(MachineEffect.sameDayHardBlock,),
                provenance=RequestLocator(sourceDoctorKey="dr_icu", dayIndex=0),
            ),
        ),
    )
    state = RuleState.empty()
    proposed = _propose("dr_icu", "MICU_CALL", "2026-05-01")
    decision = evaluate(model, state, proposed)
    assert not decision.valid
    assert RULE_SAME_DAY_HARD_BLOCK in _codes(decision)


def test_same_day_already_held_fires() -> None:
    """Doctor already placed in another slot on the same date."""
    model = _minimal_model()
    state = RuleState(
        assignments=(_placed("dr_icu", "MICU_STANDBY", "2026-05-01"),)
    )
    proposed = _propose("dr_icu", "MICU_CALL", "2026-05-01")
    decision = evaluate(model, state, proposed)
    assert not decision.valid
    assert RULE_SAME_DAY_ALREADY_HELD in _codes(decision)


def test_unit_already_filled_fires() -> None:
    """Same (dateKey, slotType, unitIndex) already filled by another doctor."""
    model = _minimal_model()
    state = RuleState(
        assignments=(_placed("dr_both", "MICU_CALL", "2026-05-01", unit_index=0),)
    )
    proposed = _propose("dr_icu", "MICU_CALL", "2026-05-01", unit_index=0)
    decision = evaluate(model, state, proposed)
    assert not decision.valid
    assert RULE_UNIT_ALREADY_FILLED in _codes(decision)


def test_unit_already_filled_branches_on_unit_index_per_d0029() -> None:
    """Per D-0029, UNIT_ALREADY_FILLED is the only rule that branches on
    unitIndex. A different unitIndex on the same (dateKey, slotType) does
    NOT fire UNIT_ALREADY_FILLED."""
    model = _minimal_model()
    state = RuleState(
        assignments=(_placed("dr_icu", "MICU_CALL", "2026-05-01", unit_index=0),)
    )
    proposed = _propose("dr_both", "MICU_CALL", "2026-05-01", unit_index=1)
    decision = evaluate(model, state, proposed)
    # No UNIT_ALREADY_FILLED.
    assert RULE_UNIT_ALREADY_FILLED not in _codes(decision)


def test_back_to_back_call_fires_on_prior_day() -> None:
    """Call slot on day N — call slot already placed for the same doctor on
    day N-1 fires BACK_TO_BACK_CALL."""
    model = _minimal_model()
    state = RuleState(
        assignments=(_placed("dr_icu", "MICU_CALL", "2026-05-01"),)
    )
    proposed = _propose("dr_icu", "MICU_CALL", "2026-05-02")
    decision = evaluate(model, state, proposed)
    assert not decision.valid
    assert RULE_BACK_TO_BACK_CALL in _codes(decision)


def test_back_to_back_call_fires_on_following_day() -> None:
    """Symmetric forward-direction adjacency."""
    model = _minimal_model()
    state = RuleState(
        assignments=(_placed("dr_icu", "MICU_CALL", "2026-05-03"),)
    )
    proposed = _propose("dr_icu", "MICU_CALL", "2026-05-02")
    decision = evaluate(model, state, proposed)
    assert not decision.valid
    assert RULE_BACK_TO_BACK_CALL in _codes(decision)


def test_back_to_back_call_does_not_fire_on_standby_neighbor() -> None:
    """STANDBY is not a call slot per the template specimen; adjacent standby
    must NOT fire BACK_TO_BACK_CALL."""
    model = _minimal_model()
    state = RuleState(
        assignments=(_placed("dr_icu", "MICU_STANDBY", "2026-05-01"),)
    )
    proposed = _propose("dr_icu", "MICU_CALL", "2026-05-02")
    decision = evaluate(model, state, proposed)
    assert RULE_BACK_TO_BACK_CALL not in _codes(decision)


def test_back_to_back_call_does_not_fire_when_proposed_is_standby() -> None:
    """Even if a prior-day call exists, a standby placement is not a call —
    BACK_TO_BACK_CALL should not fire (it scopes to call slots only per §11)."""
    model = _minimal_model()
    state = RuleState(
        assignments=(_placed("dr_icu", "MICU_CALL", "2026-05-01"),)
    )
    proposed = _propose("dr_icu", "MICU_STANDBY", "2026-05-02")
    decision = evaluate(model, state, proposed)
    assert RULE_BACK_TO_BACK_CALL not in _codes(decision)


# --- §15 FixedAssignment-as-neighbor case --------------------------------


def test_back_to_back_call_fires_against_fixed_call_neighbor() -> None:
    """Per §15: BACK_TO_BACK_CALL must fire against a fixed call on an
    adjacent date exactly as it would against a solver-placed call. The rule
    engine sees fixed-derived units and solver-placed units the same way in
    ruleState — there is no special path for fixed assignments."""
    model = _minimal_model()
    # Simulate a fixed assignment by placing it directly into ruleState — the
    # solver will normally seed ruleState with fixed-derived units this way.
    state = RuleState(
        assignments=(_placed("dr_icu", "MICU_CALL", "2026-05-01"),)
    )
    proposed = _propose("dr_icu", "MICU_CALL", "2026-05-02")
    decision = evaluate(model, state, proposed)
    assert not decision.valid
    assert RULE_BACK_TO_BACK_CALL in _codes(decision)


# --- §12 canonical-ordering test -----------------------------------------


def test_canonical_ordering_full_list_when_multiple_rules_fire() -> None:
    """Per §12, when multiple rules fire, reasons are ordered cheapest-first
    in the canonical sequence and the list contains EVERY applicable
    violation (not first-hit-only)."""
    model = _minimal_model()
    # Add a hard block AND prior-day call AND already-held same-day so 4 of
    # the 5 rules can fire on one probe (eligibility passes for ICU_HD doctor).
    model = replace(
        model,
        dailyEffects=(
            DailyEffectState(
                doctorId="dr_both",
                dateKey="2026-05-02",
                effects=(MachineEffect.sameDayHardBlock,),
                provenance=RequestLocator(sourceDoctorKey="dr_both", dayIndex=1),
            ),
        ),
    )
    state = RuleState(
        assignments=(
            # Same-day already held: dr_both already on MHD_STANDBY 2026-05-02.
            _placed("dr_both", "MHD_STANDBY", "2026-05-02"),
            # Unit already filled: dr_icu on MICU_CALL unit 0 on 2026-05-02.
            _placed("dr_icu", "MICU_CALL", "2026-05-02", unit_index=0),
            # Prior-day call for dr_both: dr_both on MICU_CALL 2026-05-01.
            _placed("dr_both", "MICU_CALL", "2026-05-01"),
        ),
    )
    # dr_both proposed for MICU_CALL on 2026-05-02 unit 0:
    # - BASELINE_ELIGIBILITY_FAIL: passes (ICU_HD eligible for MICU_CALL).
    # - SAME_DAY_HARD_BLOCK: fires (hard block on 2026-05-02).
    # - SAME_DAY_ALREADY_HELD: fires (dr_both on MHD_STANDBY same date).
    # - UNIT_ALREADY_FILLED: fires (unit already filled by dr_icu).
    # - BACK_TO_BACK_CALL: fires (dr_both on call 2026-05-01).
    proposed = _propose("dr_both", "MICU_CALL", "2026-05-02", unit_index=0)
    decision = evaluate(model, state, proposed)
    assert not decision.valid
    codes = _codes(decision)
    # 4 violations expected (eligibility passes).
    assert len(codes) == 4, f"expected 4 fired rules, got {codes}"
    # Canonical-ordering: §12 ordering must be respected. Strip eligibility
    # since it doesn't fire.
    expected_order = [c for c in CANONICAL_ORDER if c != RULE_BASELINE_ELIGIBILITY_FAIL]
    assert codes == expected_order


# --- §13 / §17 statelessness + determinism -------------------------------


def test_repeated_evaluations_are_byte_identical() -> None:
    """Per §13 + §17: the rule engine MUST produce byte-identical Decision
    outputs across repeated invocations on identical inputs."""
    model = _minimal_model()
    model = replace(
        model,
        dailyEffects=(
            DailyEffectState(
                doctorId="dr_icu",
                dateKey="2026-05-01",
                effects=(MachineEffect.sameDayHardBlock,),
                provenance=RequestLocator(sourceDoctorKey="dr_icu", dayIndex=0),
            ),
        ),
    )
    state = RuleState(
        assignments=(_placed("dr_icu", "MICU_STANDBY", "2026-05-01"),)
    )
    proposed = _propose("dr_icu", "MICU_CALL", "2026-05-01")
    first = evaluate(model, state, proposed)
    second = evaluate(model, state, proposed)
    third = evaluate(model, state, proposed)
    assert first == second == third


def test_proposed_unit_with_null_doctor_id_raises() -> None:
    """Per §9: proposedUnit.doctorId MUST NOT be None for a hard-validity
    query. Implementation rejects it explicitly."""
    model = _minimal_model()
    state = RuleState.empty()
    bad_proposed = AssignmentUnit(
        dateKey="2026-05-01",
        slotType="MICU_CALL",
        unitIndex=0,
        doctorId=None,
    )
    raised = False
    try:
        evaluate(model, state, bad_proposed)
    except ValueError:
        raised = True
    assert raised, "evaluate must raise ValueError on null-doctorId proposedUnit"


# --- standalone runner ---------------------------------------------------


def _all_tests():
    return [v for k, v in globals().items() if k.startswith("test_") and callable(v)]


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
