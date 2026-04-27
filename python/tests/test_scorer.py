"""Tests for the scorer per `docs/scorer_contract.md`.

Covers the two mandatory contract property tests (the §13 direction-guard
invariant and the §12 `crReward` diminishing-marginal-utility curve), one
positive test per first-release component, the §10 component-breakdown
completeness rule, the §17 determinism requirement, and the §11 missing-
weights configuration-defect path.

Standalone runnable via `python3 python/tests/test_scorer.py`.
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
    CanonicalRequestClass,
    DailyEffectState,
    Doctor,
    DoctorGroup,
    EligibilityRule,
    MachineEffect,
    NormalizedModel,
    Request,
    RosterDay,
    RosterPeriod,
    SlotDemand,
    SlotTypeDefinition,
)
from rostermonster.scorer import (  # noqa: E402
    ALL_COMPONENTS,
    COMPONENT_CR_REWARD,
    COMPONENT_DUAL_ELIGIBLE_ICU_BONUS,
    COMPONENT_POINT_BALANCE_GLOBAL,
    COMPONENT_POINT_BALANCE_WITHIN_SECTION,
    COMPONENT_PRE_LEAVE_PENALTY,
    COMPONENT_SPACING_PENALTY,
    COMPONENT_STANDBY_ADJACENCY_PENALTY,
    COMPONENT_STANDBY_COUNT_FAIRNESS_PENALTY,
    COMPONENT_UNFILLED_PENALTY,
    ScoreDirection,
    ScoringConfig,
    score,
)
from rostermonster.snapshot import (  # noqa: E402
    DayLocator,
    DoctorLocator,
    RequestLocator,
)


# --- Minimal-but-real model ---------------------------------------------


def _model() -> NormalizedModel:
    """Small ICU/HD-shaped model: 3 docs (ICU_ONLY, ICU_HD, HD_ONLY), 5 days,
    4 slot types. Tests opt in to requests / DailyEffectState as needed."""
    days = tuple(
        RosterDay(
            dateKey=f"2026-05-{i + 1:02d}",
            dayIndex=i,
            provenance=DayLocator(dayIndex=i),
        )
        for i in range(5)
    )
    period = RosterPeriod(periodId="2026-05", periodLabel="May 2026", days=days)
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


def _unit(doctor_id: str | None, slot: str, date_key: str, unit_index: int = 0) -> AssignmentUnit:
    return AssignmentUnit(
        dateKey=date_key,
        slotType=slot,
        unitIndex=unit_index,
        doctorId=doctor_id,
    )


# --- Component breakdown completeness (§10) ------------------------------


def test_score_result_carries_every_first_release_component() -> None:
    """Per §10 every first-release component identifier MUST appear in
    `ScoreResult.components`, even when contributing zero."""
    model = _model()
    config = ScoringConfig.first_release_defaults()
    result = score((), model, config)
    for component in ALL_COMPONENTS:
        assert component in result.components, (
            f"missing required component {component!r} per §10"
        )
    assert result.direction is ScoreDirection.HIGHER_IS_BETTER


def test_missing_weight_raises() -> None:
    """Per §11, `weights` MUST cover every first-release component;
    omission is a configuration defect."""
    model = _model()
    config = ScoringConfig(weights={COMPONENT_UNFILLED_PENALTY: -1.0})
    raised = False
    try:
        score((), model, config)
    except ValueError:
        raised = True
    assert raised


def test_wrong_sign_weight_raises_per_scorer_10_and_15() -> None:
    """Per §10 / §15 sign orientation is a property of the component, not the
    weight. Penalty weight > 0 (or reward weight < 0) inverts the direction-
    guard invariant — for example, a positive `unfilledPenalty` weight would
    make adding unfilled assignments INCREASE totalScore. score() rejects
    mis-signed weights at config validation rather than allowing the
    inversion."""
    model = _model()

    # Penalty given positive weight — wrong sign.
    weights_a = ScoringConfig.first_release_defaults().weights.copy()
    weights_a[COMPONENT_UNFILLED_PENALTY] = +100.0
    raised_a = False
    try:
        score((), model, ScoringConfig(weights=weights_a))
    except ValueError:
        raised_a = True
    assert raised_a, "expected ValueError for positive unfilledPenalty weight"

    # Reward given negative weight — wrong sign.
    weights_b = ScoringConfig.first_release_defaults().weights.copy()
    weights_b[COMPONENT_CR_REWARD] = -1.0
    raised_b = False
    try:
        score((), model, ScoringConfig(weights=weights_b))
    except ValueError:
        raised_b = True
    assert raised_b, "expected ValueError for negative crReward weight"

    # Zero weight is allowed for both penalty and reward (component
    # contributes nothing); not a sign violation.
    weights_c = ScoringConfig.first_release_defaults().weights.copy()
    weights_c[COMPONENT_UNFILLED_PENALTY] = 0.0
    weights_c[COMPONENT_CR_REWARD] = 0.0
    score((), model, ScoringConfig(weights=weights_c))  # must not raise


# --- Per-component positive tests ----------------------------------------


def test_unfilled_penalty_fires_on_unfilled_unit() -> None:
    model = _model()
    config = ScoringConfig.first_release_defaults()
    alloc = (_unit(None, "MICU_CALL", "2026-05-01"),)
    result = score(alloc, model, config)
    assert result.components[COMPONENT_UNFILLED_PENALTY] < 0


def test_cr_reward_honors_cr_request() -> None:
    """A CR request from a doctor matched by a same-date call placement
    contributes positive reward to crReward."""
    model = _model()
    model = replace(
        model,
        requests=(
            Request(
                doctorId="dr_icu",
                dateKey="2026-05-02",
                rawRequestText="CR",
                recognizedRawTokens=("CR",),
                canonicalClasses=(CanonicalRequestClass.CR,),
                machineEffects=(MachineEffect.callPreferencePositive,),
                provenance=RequestLocator(sourceDoctorKey="dr_icu", dayIndex=1),
            ),
        ),
    )
    config = ScoringConfig.first_release_defaults()
    alloc = (_unit("dr_icu", "MICU_CALL", "2026-05-02"),)
    result = score(alloc, model, config)
    assert result.components[COMPONENT_CR_REWARD] > 0


def test_pre_leave_penalty_fires_on_call_before_leave() -> None:
    """Doctor on call day N, with prevDayCallSoftPenaltyTrigger firing on
    day N+1 → preLeavePenalty contributes negative."""
    model = _model()
    model = replace(
        model,
        dailyEffects=(
            DailyEffectState(
                doctorId="dr_icu",
                dateKey="2026-05-03",
                effects=(
                    MachineEffect.sameDayHardBlock,
                    MachineEffect.prevDayCallSoftPenaltyTrigger,
                ),
                provenance=RequestLocator(sourceDoctorKey="dr_icu", dayIndex=2),
            ),
        ),
    )
    config = ScoringConfig.first_release_defaults()
    alloc = (_unit("dr_icu", "MICU_CALL", "2026-05-02"),)
    result = score(alloc, model, config)
    assert result.components[COMPONENT_PRE_LEAVE_PENALTY] < 0


def test_dual_eligible_icu_bonus_fires_for_icu_hd_on_micu() -> None:
    model = _model()
    config = ScoringConfig.first_release_defaults()
    alloc = (_unit("dr_both", "MICU_CALL", "2026-05-01"),)
    result = score(alloc, model, config)
    assert result.components[COMPONENT_DUAL_ELIGIBLE_ICU_BONUS] > 0


def test_dual_eligible_icu_bonus_zero_for_icu_only_doctor() -> None:
    """ICU_ONLY doctor on MICU does NOT contribute to dualEligibleIcuBonus —
    this component is specifically about ICU_HD doctors taking MICU work."""
    model = _model()
    config = ScoringConfig.first_release_defaults()
    alloc = (_unit("dr_icu", "MICU_CALL", "2026-05-01"),)
    result = score(alloc, model, config)
    assert result.components[COMPONENT_DUAL_ELIGIBLE_ICU_BONUS] == 0.0


def test_spacing_penalty_fires_on_close_call_pair() -> None:
    """Two calls for the same doctor 2 days apart — fall under the 3-day
    minimum-gap threshold → one spacingPenalty unit fires."""
    model = _model()
    config = ScoringConfig.first_release_defaults()
    alloc = (
        _unit("dr_both", "MICU_CALL", "2026-05-01"),
        _unit("dr_both", "MHD_CALL", "2026-05-03"),
    )
    result = score(alloc, model, config)
    assert result.components[COMPONENT_SPACING_PENALTY] < 0


def test_spacing_penalty_zero_when_calls_far_apart() -> None:
    """Two calls 4 days apart → no spacing penalty (≥ 3-day threshold)."""
    model = _model()
    config = ScoringConfig.first_release_defaults()
    alloc = (
        _unit("dr_both", "MICU_CALL", "2026-05-01"),
        _unit("dr_both", "MHD_CALL", "2026-05-05"),
    )
    result = score(alloc, model, config)
    assert result.components[COMPONENT_SPACING_PENALTY] == 0.0


def test_standby_adjacency_penalty_fires() -> None:
    """Same doctor: standby on day N + call on day N+1 → standby-adjacency
    penalty fires."""
    model = _model()
    config = ScoringConfig.first_release_defaults()
    alloc = (
        _unit("dr_both", "MICU_STANDBY", "2026-05-01"),
        _unit("dr_both", "MICU_CALL", "2026-05-02"),
    )
    result = score(alloc, model, config)
    assert result.components[COMPONENT_STANDBY_ADJACENCY_PENALTY] < 0


def test_point_balance_within_section_zero_when_only_one_doctor_per_group() -> None:
    """`pvariance` of a single-element list is zero; the minimal model has
    one doctor per group, so within-section variance is 0."""
    model = _model()
    config = ScoringConfig.first_release_defaults()
    alloc = (_unit("dr_icu", "MICU_CALL", "2026-05-01"),)
    result = score(alloc, model, config)
    assert result.components[COMPONENT_POINT_BALANCE_WITHIN_SECTION] == 0.0


def test_point_balance_global_negative_when_unbalanced() -> None:
    """Three doctors, only one takes a call — the other two have zero call
    load, producing positive variance → negative pointBalanceGlobal."""
    model = _model()
    config = ScoringConfig.first_release_defaults()
    alloc = (
        _unit("dr_icu", "MICU_CALL", "2026-05-01"),
        _unit("dr_icu", "MICU_CALL", "2026-05-04"),
    )
    result = score(alloc, model, config)
    assert result.components[COMPONENT_POINT_BALANCE_GLOBAL] < 0


def test_point_balance_falls_back_to_one_per_call_when_pointrules_empty() -> None:
    """Per scorer v2 §11 (D-0037): missing `(slotType, dateKey)` entries fall
    back to `1.0` per-call. With empty pointRules dict, point_balance_global
    reduces to call-count variance — equivalent to the prior 1-point-per-call
    behavior."""
    model = _model()
    # Two configs: empty pointRules (default) vs explicit 1.0 for each
    # placement. Both should produce identical pointBalance scores.
    config_empty = ScoringConfig.first_release_defaults()
    config_explicit = ScoringConfig(
        weights=dict(config_empty.weights),
        pointRules={
            ("MICU_CALL", "2026-05-01"): 1.0,
            ("MICU_CALL", "2026-05-04"): 1.0,
        },
    )
    alloc = (
        _unit("dr_icu", "MICU_CALL", "2026-05-01"),
        _unit("dr_icu", "MICU_CALL", "2026-05-04"),
    )
    s_empty = score(alloc, model, config_empty)
    s_explicit = score(alloc, model, config_explicit)
    assert s_empty.components[COMPONENT_POINT_BALANCE_GLOBAL] == \
        s_explicit.components[COMPONENT_POINT_BALANCE_GLOBAL]
    assert s_empty.components[COMPONENT_POINT_BALANCE_WITHIN_SECTION] == \
        s_explicit.components[COMPONENT_POINT_BALANCE_WITHIN_SECTION]


def test_point_balance_consumes_point_rules_when_overridden() -> None:
    """Per scorer v2 §11 (D-0037): pointBalance components MUST consume
    `pointRules` for per-call point weighting. Set a heavy weight on one
    specific (slotType, dateKey) and confirm the variance reflects the
    weighted points, not a flat 1-per-call count."""
    model = _model()
    weights = dict(ScoringConfig.first_release_defaults().weights)
    # Zero out everything except pointBalanceGlobal to measure it in isolation.
    for component in weights:
        if component != COMPONENT_POINT_BALANCE_GLOBAL:
            weights[component] = 0.0

    # Allocation: dr_icu takes one MICU_CALL on 2026-05-01; dr_both takes one
    # MICU_CALL on 2026-05-02. Without weighting, each has 1 call point —
    # variance is 0 across doctors with one call each (and 0 for the third
    # doctor with no calls means variance > 0 only because of dr_hd).
    alloc = (
        _unit("dr_icu", "MICU_CALL", "2026-05-01"),
        _unit("dr_both", "MICU_CALL", "2026-05-02"),
    )

    # With pointRules empty (1.0 fallback for both placements):
    # loads = [1.0, 1.0, 0.0] → variance ≈ 0.222.
    config_unweighted = ScoringConfig(weights=weights, pointRules={})
    s_unweighted = score(alloc, model, config_unweighted)

    # With pointRules giving dr_icu's day 3.0× weight:
    # loads = [3.0, 1.0, 0.0] → variance > prior variance.
    config_weighted = ScoringConfig(
        weights=weights,
        pointRules={("MICU_CALL", "2026-05-01"): 3.0},
    )
    s_weighted = score(alloc, model, config_weighted)

    # Larger spread of loads ⇒ larger variance ⇒ more-negative pointBalance
    # under negative weight. Both must remain non-positive (penalty
    # orientation per §10), and the weighted case must be strictly more
    # negative than the unweighted case.
    assert s_unweighted.components[COMPONENT_POINT_BALANCE_GLOBAL] < 0
    assert s_weighted.components[COMPONENT_POINT_BALANCE_GLOBAL] < 0
    assert (
        s_weighted.components[COMPONENT_POINT_BALANCE_GLOBAL]
        < s_unweighted.components[COMPONENT_POINT_BALANCE_GLOBAL]
    ), (
        f"weighted pointBalanceGlobal ({s_weighted.components[COMPONENT_POINT_BALANCE_GLOBAL]}) "
        f"must be strictly more negative than unweighted "
        f"({s_unweighted.components[COMPONENT_POINT_BALANCE_GLOBAL]}) "
        f"when one placement carries a 3.0× point weight"
    )


def test_standby_count_fairness_penalty_negative_when_unbalanced() -> None:
    model = _model()
    config = ScoringConfig.first_release_defaults()
    alloc = (
        _unit("dr_icu", "MICU_STANDBY", "2026-05-01"),
        _unit("dr_icu", "MICU_STANDBY", "2026-05-03"),
    )
    result = score(alloc, model, config)
    assert result.components[COMPONENT_STANDBY_COUNT_FAIRNESS_PENALTY] < 0


# --- §13 direction-guard property test (mandatory) -----------------------


def test_direction_guard_invariant_holds_per_scorer_13() -> None:
    """For any valid allocation A with score S1, converting one filled
    `AssignmentUnit` to unfilled (`doctorId=None`) yields A' with score
    S2 where S2.totalScore ≤ S1.totalScore. Per scorer §13, this property
    MUST be exercised in any scorer implementation's test suite."""
    model = _model()
    config = ScoringConfig.first_release_defaults()
    # Several distinct filled allocations; for each, mutate every filled
    # unit to unfilled and confirm S2 ≤ S1.
    sample_allocations = [
        (_unit("dr_icu", "MICU_CALL", "2026-05-01"),),
        (
            _unit("dr_both", "MICU_CALL", "2026-05-01"),
            _unit("dr_hd", "MHD_STANDBY", "2026-05-02"),
        ),
        (
            _unit("dr_icu", "MICU_CALL", "2026-05-01"),
            _unit("dr_both", "MICU_STANDBY", "2026-05-02"),
            _unit("dr_hd", "MHD_CALL", "2026-05-04"),
            _unit("dr_both", "MHD_STANDBY", "2026-05-05"),
        ),
    ]
    for alloc in sample_allocations:
        s1 = score(alloc, model, config)
        for i, unit in enumerate(alloc):
            if unit.doctorId is None:
                continue
            mutated = list(alloc)
            mutated[i] = replace(unit, doctorId=None)
            s2 = score(tuple(mutated), model, config)
            assert s2.totalScore <= s1.totalScore, (
                f"direction-guard violation: converting {unit!r} to unfilled "
                f"increased score from {s1.totalScore} to {s2.totalScore}"
            )


# --- §12 crReward diminishing-marginal-utility property test (mandatory) -


def test_cr_reward_strictly_diminishes_per_doctor() -> None:
    """Per scorer §12: kth honored CR per doctor (k ≥ 2) MUST contribute
    strictly less than the (k − 1)th. Property test by varying the count
    of honored CRs for one doctor and inspecting the per-step delta."""
    model = _model()
    # Set up CR requests for dr_both on days 0, 1, 2, 3, 4 (5 honor-able CRs).
    cr_requests = tuple(
        Request(
            doctorId="dr_both",
            dateKey=f"2026-05-{i + 1:02d}",
            rawRequestText="CR",
            recognizedRawTokens=("CR",),
            canonicalClasses=(CanonicalRequestClass.CR,),
            machineEffects=(MachineEffect.callPreferencePositive,),
            provenance=RequestLocator(sourceDoctorKey="dr_both", dayIndex=i),
        )
        for i in range(5)
    )
    model = replace(model, requests=cr_requests)
    # Use a config with only crReward weighted; zero out everything else so
    # we measure the curve in isolation.
    weights = {c: 0.0 for c in ALL_COMPONENTS}
    weights[COMPONENT_CR_REWARD] = 5.0
    config = ScoringConfig(weights=weights)

    rewards: list[float] = []
    for k in range(1, 6):
        alloc = tuple(
            _unit("dr_both", "MICU_CALL", f"2026-05-{i + 1:02d}")
            for i in range(k)
        )
        rewards.append(score(alloc, model, config).components[COMPONENT_CR_REWARD])

    deltas = [rewards[i] - rewards[i - 1] for i in range(1, len(rewards))]
    # Each delta is the marginal contribution of adding the kth honored CR.
    # Strict-monotonic-decrease: delta[k=2] < delta[k=1], etc.
    for i in range(1, len(deltas)):
        assert deltas[i] < deltas[i - 1], (
            f"crReward marginal contribution did not strictly decrease at "
            f"k={i + 2}: {deltas[i]!r} not < {deltas[i - 1]!r} (per scorer §12)"
        )
    # And every delta is strictly positive (each honored CR adds reward).
    for d in deltas:
        assert d > 0


# --- §17 determinism -----------------------------------------------------


def test_repeated_scoring_is_byte_identical() -> None:
    model = _model()
    config = ScoringConfig.first_release_defaults()
    alloc = (
        _unit("dr_icu", "MICU_CALL", "2026-05-01"),
        _unit("dr_both", "MHD_STANDBY", "2026-05-02"),
    )
    s1 = score(alloc, model, config)
    s2 = score(alloc, model, config)
    s3 = score(alloc, model, config)
    assert s1 == s2 == s3


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
