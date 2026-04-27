"""First-release scoring components per `docs/scorer_contract.md` + the
nine identifiers enumerated in `docs/domain_model.md` §11.2.

Each component is a pure function of `(allocation, normalizedModel,
scoringConfig)` returning its signed contribution to `totalScore`. The
orchestrator in `scorer.py` sums them. Per §10 every first-release
component MUST appear in `ScoreResult.components` even when contributing
zero, so each function returns a float (not optionally `None`).

First-release simplifications (out-of-scope details documented inline):
- Point load is "1 point per call" rather than weekday/weekend-weighted
  per `docs/template_artifact_contract.md` §9 `pointRows.defaultRule`,
  because the parser-consumable template artifact subset does not
  currently carry point-row data. Likely surfaces as an OD entry.
- `spacingPenalty` uses a fixed minimum-gap threshold (3 days); operator-
  tuneable spacing parameters are FW-0007 territory.
- `dualEligibleIcuBonus` rewards ICU_HD doctors taking MICU slots (the
  operator-flexible direction); the v1 magnitude tuning lands per FW-0014.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import pvariance

from rostermonster.domain import (
    AssignmentUnit,
    CanonicalRequestClass,
    MachineEffect,
    NormalizedModel,
)
from rostermonster.scorer.result import (
    COMPONENT_CR_REWARD,
    COMPONENT_DUAL_ELIGIBLE_ICU_BONUS,
    COMPONENT_POINT_BALANCE_GLOBAL,
    COMPONENT_POINT_BALANCE_WITHIN_SECTION,
    COMPONENT_PRE_LEAVE_PENALTY,
    COMPONENT_SPACING_PENALTY,
    COMPONENT_STANDBY_ADJACENCY_PENALTY,
    COMPONENT_STANDBY_COUNT_FAIRNESS_PENALTY,
    COMPONENT_UNFILLED_PENALTY,
    ScoringConfig,
)

# First-release `spacingPenalty` minimum-gap threshold. Two call placements
# for the same doctor closer than this many days each contribute one penalty
# unit; tunable threshold lives behind FW-0007.
_SPACING_MIN_GAP_DAYS = 3


def _shift_iso_date(iso: str, days: int) -> str:
    return (date.fromisoformat(iso) + timedelta(days=days)).isoformat()


def _call_slot_types(model: NormalizedModel) -> frozenset[str]:
    """Template-driven call-slot identity (mirrors rule_engine §11)."""
    return frozenset(st.slotType for st in model.slotTypes if st.slotKind == "CALL")


def _standby_slot_types(model: NormalizedModel) -> frozenset[str]:
    return frozenset(st.slotType for st in model.slotTypes if st.slotKind == "STANDBY")


# --- 1. unfilledPenalty --------------------------------------------------


def unfilled_penalty(
    allocation: tuple[AssignmentUnit, ...],
    model: NormalizedModel,
    config: ScoringConfig,
) -> float:
    """Penalty per `AssignmentUnit` with `doctorId is None`. Drives the §13
    direction-guard invariant — converting a filled unit to unfilled MUST NOT
    increase totalScore. With `unfilledPenalty` weight strongly negative and
    no other component out-rewarding the conversion, the invariant holds."""
    weight = config.weights[COMPONENT_UNFILLED_PENALTY]
    n_unfilled = sum(1 for a in allocation if a.doctorId is None)
    return n_unfilled * weight


# --- 2 + 3. point balance components -------------------------------------


def _call_points_per_doctor(
    allocation: tuple[AssignmentUnit, ...],
    call_slots: frozenset[str],
    point_rules: dict[tuple[str, str], float],
) -> dict[str, float]:
    """Per-doctor weighted call-point load per scorer v2 §11. Each call-slot
    `AssignmentUnit` contributes `point_rules[(slotType, dateKey)]` to its
    doctor's running total. `point_rules` is assumed complete over the
    `(call-slot, dateKey)` cross-product (validated once at `score()` entry
    per scorer §11 D-0038) — direct dict access raises if a producer-side
    defect lets a missing key reach this point."""
    points: dict[str, float] = defaultdict(float)
    for a in allocation:
        if a.doctorId is None or a.slotType not in call_slots:
            continue
        points[a.doctorId] += point_rules[(a.slotType, a.dateKey)]
    return points


def point_balance_within_section(
    allocation: tuple[AssignmentUnit, ...],
    model: NormalizedModel,
    config: ScoringConfig,
) -> float:
    """Penalty proportional to call-point-load variance within each doctor
    group. Lower variance ⇒ smaller penalty (more balanced load within the
    section). Per-call point weight comes from `config.pointRules` per
    scorer v2 §11; missing entries fall back to `1.0` per-call."""
    weight = config.weights[COMPONENT_POINT_BALANCE_WITHIN_SECTION]
    if weight == 0:
        return 0.0
    call_slots = _call_slot_types(model)
    points_per_doctor = _call_points_per_doctor(allocation, call_slots, config.pointRules)

    # Group doctors by groupId.
    by_group: dict[str, list[float]] = defaultdict(list)
    for doc in model.doctors:
        by_group[doc.groupId].append(points_per_doctor.get(doc.doctorId, 0.0))

    total_variance = 0.0
    for group_loads in by_group.values():
        if len(group_loads) > 1:
            total_variance += pvariance(group_loads)
    return total_variance * weight


def point_balance_global(
    allocation: tuple[AssignmentUnit, ...],
    model: NormalizedModel,
    config: ScoringConfig,
) -> float:
    """Penalty proportional to call-point-load variance across all doctors.
    Lower variance ⇒ smaller penalty (more balanced load across the roster
    as a whole). Per-call point weight comes from `config.pointRules` per
    scorer v2 §11; missing entries fall back to `1.0` per-call."""
    weight = config.weights[COMPONENT_POINT_BALANCE_GLOBAL]
    if weight == 0:
        return 0.0
    call_slots = _call_slot_types(model)
    points_per_doctor = _call_points_per_doctor(allocation, call_slots, config.pointRules)

    loads = [points_per_doctor.get(doc.doctorId, 0.0) for doc in model.doctors]
    if len(loads) <= 1:
        return 0.0
    return pvariance(loads) * weight


# --- 4. spacingPenalty ---------------------------------------------------


def spacing_penalty(
    allocation: tuple[AssignmentUnit, ...],
    model: NormalizedModel,
    config: ScoringConfig,
) -> float:
    """Penalty for any pair of call placements for the same doctor within
    `_SPACING_MIN_GAP_DAYS` days of each other. Note: the rule engine
    already rejects strict back-to-back call (gap < 2 days) per
    `BACK_TO_BACK_CALL`; this component soft-penalizes the next-tightest
    cluster (gap < `_SPACING_MIN_GAP_DAYS`) so spacing improves beyond the
    hard-rule floor."""
    weight = config.weights[COMPONENT_SPACING_PENALTY]
    if weight == 0:
        return 0.0
    call_slots = _call_slot_types(model)

    # Collect call dates per doctor (as `date` objects for arithmetic).
    by_doctor: dict[str, list[date]] = defaultdict(list)
    for a in allocation:
        if a.doctorId is not None and a.slotType in call_slots:
            try:
                by_doctor[a.doctorId].append(date.fromisoformat(a.dateKey))
            except ValueError:
                continue

    n_violations = 0
    for dates_list in by_doctor.values():
        dates_sorted = sorted(dates_list)
        for i in range(len(dates_sorted) - 1):
            gap = (dates_sorted[i + 1] - dates_sorted[i]).days
            if gap < _SPACING_MIN_GAP_DAYS:
                n_violations += 1
    return n_violations * weight


# --- 5. preLeavePenalty --------------------------------------------------


def pre_leave_penalty(
    allocation: tuple[AssignmentUnit, ...],
    model: NormalizedModel,
    config: ScoringConfig,
) -> float:
    """Penalty when a doctor is placed on a call slot the day before a
    `prevDayCallSoftPenaltyTrigger` fires for that doctor. Per scorer §14,
    scorer reads `DailyEffectState` directly. Per `docs/domain_model.md`
    §8.2 the trigger fires on the date of leave/PM_OFF; the penalty applies
    when call is on the *prior* day."""
    weight = config.weights[COMPONENT_PRE_LEAVE_PENALTY]
    if weight == 0:
        return 0.0
    call_slots = _call_slot_types(model)

    # (doctorId, dateKey) where prev-day-call trigger fires.
    trigger_dates: set[tuple[str, str]] = {
        (de.doctorId, de.dateKey)
        for de in model.dailyEffects
        if MachineEffect.prevDayCallSoftPenaltyTrigger in de.effects
    }

    n_violations = 0
    for a in allocation:
        if a.doctorId is None or a.slotType not in call_slots:
            continue
        try:
            next_date = _shift_iso_date(a.dateKey, +1)
        except ValueError:
            continue
        if (a.doctorId, next_date) in trigger_dates:
            n_violations += 1
    return n_violations * weight


# --- 6. crReward (diminishing marginal utility per doctor) ---------------


def cr_reward(
    allocation: tuple[AssignmentUnit, ...],
    model: NormalizedModel,
    config: ScoringConfig,
) -> float:
    """Reward for honored `CR` requests. Per scorer §12, kth honored CR per
    doctor (k ≥ 2) MUST contribute strictly less than (k − 1)th — first-
    release curve is harmonic (`weight / k`). A `CR` request is "honored"
    when the allocation places that doctor on any call slot on the request
    date."""
    weight = config.weights[COMPONENT_CR_REWARD]
    if weight == 0:
        return 0.0
    call_slots = _call_slot_types(model)

    on_call: set[tuple[str, str]] = {
        (a.doctorId, a.dateKey)
        for a in allocation
        if a.doctorId is not None and a.slotType in call_slots
    }

    honored_per_doctor: dict[str, int] = defaultdict(int)
    for req in model.requests:
        if CanonicalRequestClass.CR in req.canonicalClasses:
            if (req.doctorId, req.dateKey) in on_call:
                honored_per_doctor[req.doctorId] += 1

    total = 0.0
    for count in honored_per_doctor.values():
        for k in range(1, count + 1):
            total += weight / k
    return total


# --- 7. dualEligibleIcuBonus --------------------------------------------


def dual_eligible_icu_bonus(
    allocation: tuple[AssignmentUnit, ...],
    model: NormalizedModel,
    config: ScoringConfig,
) -> float:
    """Bonus per MICU-family assignment held by an ICU_HD-grouped doctor.
    Rewards using ICU_HD flexibility on the MICU side. Magnitude tuning is
    FW-0014 territory; sign is positive (reward)."""
    weight = config.weights[COMPONENT_DUAL_ELIGIBLE_ICU_BONUS]
    if weight == 0:
        return 0.0

    group_by_doctor = {d.doctorId: d.groupId for d in model.doctors}
    micu_slot_types = frozenset(
        st.slotType for st in model.slotTypes if st.slotFamily == "MICU"
    )

    n_bonus = 0
    for a in allocation:
        if a.doctorId is None:
            continue
        if a.slotType not in micu_slot_types:
            continue
        if group_by_doctor.get(a.doctorId) == "ICU_HD":
            n_bonus += 1
    return n_bonus * weight


# --- 8. standbyAdjacencyPenalty ------------------------------------------


def standby_adjacency_penalty(
    allocation: tuple[AssignmentUnit, ...],
    model: NormalizedModel,
    config: ScoringConfig,
) -> float:
    """Penalty when the same doctor has standby on day N and call on day N±1.
    Captures the 'soft-clash' shape that the hard-rule layer leaves alone
    (rule engine's `BACK_TO_BACK_CALL` only scopes to call-vs-call)."""
    weight = config.weights[COMPONENT_STANDBY_ADJACENCY_PENALTY]
    if weight == 0:
        return 0.0
    call_slots = _call_slot_types(model)
    standby_slots = _standby_slot_types(model)

    on_call: set[tuple[str, str]] = {
        (a.doctorId, a.dateKey)
        for a in allocation
        if a.doctorId is not None and a.slotType in call_slots
    }

    n_violations = 0
    for a in allocation:
        if a.doctorId is None or a.slotType not in standby_slots:
            continue
        try:
            prev_d = _shift_iso_date(a.dateKey, -1)
            next_d = _shift_iso_date(a.dateKey, +1)
        except ValueError:
            continue
        if (a.doctorId, prev_d) in on_call:
            n_violations += 1
        if (a.doctorId, next_d) in on_call:
            n_violations += 1
    return n_violations * weight


# --- 9. standbyCountFairnessPenalty --------------------------------------


def standby_count_fairness_penalty(
    allocation: tuple[AssignmentUnit, ...],
    model: NormalizedModel,
    config: ScoringConfig,
) -> float:
    """Penalty proportional to standby-count variance across all doctors.
    Lower variance ⇒ smaller penalty (more even standby distribution)."""
    weight = config.weights[COMPONENT_STANDBY_COUNT_FAIRNESS_PENALTY]
    if weight == 0:
        return 0.0
    standby_slots = _standby_slot_types(model)

    counts: dict[str, int] = defaultdict(int)
    for a in allocation:
        if a.doctorId is not None and a.slotType in standby_slots:
            counts[a.doctorId] += 1

    loads = [float(counts.get(doc.doctorId, 0)) for doc in model.doctors]
    if len(loads) <= 1:
        return 0.0
    return pvariance(loads) * weight
