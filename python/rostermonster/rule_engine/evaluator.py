"""Stateless rule engine evaluator per `docs/rule_engine_contract.md`.

Public entry: `evaluate(normalizedModel, ruleState, proposedUnit) → Decision`.

Implements:
- §11 first-release hard-rule enumeration (5 rules).
- §12 canonical violation ordering (cheapest-first; full-list, not first-hit).
- §13 stateless public surface (no caching exposed at the contract surface;
  per-call internal indexing is permitted).
- §15 FixedAssignment scoped handling (rule engine does not re-adjudicate
  fixed assignments against themselves — the solver MUST NOT feed fixed
  units back as `proposedUnit`; downstream validity DOES fire against
  fixed-assignment neighbors via `BACK_TO_BACK_CALL`).
- §16 separation from soft-effect evaluation (no consultation of
  `prevDayCallSoftPenaltyTrigger` / `callPreferencePositive`; only
  `sameDayHardBlock` is read because it IS a hard rule per §11).
- §17 determinism (pure function of inputs; identical outputs across
  repeated invocations on the same inputs).
"""

from __future__ import annotations

from datetime import date, timedelta

from rostermonster.domain import (
    AssignmentUnit,
    MachineEffect,
    NormalizedModel,
)
from rostermonster.rule_engine.result import (
    CANONICAL_ORDER,
    Decision,
    RULE_BACK_TO_BACK_CALL,
    RULE_BASELINE_ELIGIBILITY_FAIL,
    RULE_SAME_DAY_ALREADY_HELD,
    RULE_SAME_DAY_HARD_BLOCK,
    RULE_UNIT_ALREADY_FILLED,
    ViolationReason,
)
from rostermonster.rule_engine.state import RuleState


def _shift_iso_date(iso: str, days: int) -> str:
    """Shift an ISO 8601 dateKey by ±N days. Per D-0033, dateKeys arrive in
    `YYYY-MM-DD` form normalized by the snapshot adapter; we do calendar
    arithmetic rather than dayIndex arithmetic so the back-to-back check
    remains correct even if a future template introduces non-contiguous
    day axes."""
    return (date.fromisoformat(iso) + timedelta(days=days)).isoformat()


def evaluate(
    normalizedModel: NormalizedModel,
    ruleState: RuleState,
    proposedUnit: AssignmentUnit,
) -> Decision:
    """Adjudicate hard validity of `proposedUnit` against `normalizedModel`
    and `ruleState`. Returns a `Decision` per `docs/rule_engine_contract.md`
    §10 with full-list canonical-ordered reasons on rejection (§12).

    Per §9, `proposedUnit.doctorId` MUST NOT be `None`; unfilled-unit
    representation is a downstream concern, not a rule-engine input.
    """
    if proposedUnit.doctorId is None:
        raise ValueError(
            "proposedUnit.doctorId MUST NOT be None per "
            "docs/rule_engine_contract.md §9"
        )

    # ----- model-derived lookups (cheap on first-release ICU/HD scale) -----
    # Eligibility: slotType → frozenset of eligibleGroups.
    eligibility_by_slot: dict[str, frozenset[str]] = {
        er.slotType: frozenset(er.eligibleGroups)
        for er in normalizedModel.eligibility
    }
    # Doctor: doctorId → groupId.
    group_by_doctor: dict[str, str] = {
        d.doctorId: d.groupId for d in normalizedModel.doctors
    }
    # Call-slot identity per §11 rule 5: template-declared via slotKind.
    call_slot_types: frozenset[str] = frozenset(
        st.slotType for st in normalizedModel.slotTypes if st.slotKind == "CALL"
    )
    # Same-day hard block: (doctorId, dateKey) firing sameDayHardBlock.
    hard_block_dates: frozenset[tuple[str, str]] = frozenset(
        (de.doctorId, de.dateKey)
        for de in normalizedModel.dailyEffects
        if MachineEffect.sameDayHardBlock in de.effects
    )

    # ----- ruleState-derived lookups -----
    # (doctorId, dateKey) for any placed unit with non-null doctorId — drives
    # SAME_DAY_ALREADY_HELD.
    doctor_dates: set[tuple[str, str]] = {
        (a.doctorId, a.dateKey)
        for a in ruleState.assignments
        if a.doctorId is not None
    }
    # (dateKey, slotType, unitIndex) — drives UNIT_ALREADY_FILLED. Per D-0029
    # this is the only hard rule that branches on `unitIndex`.
    filled_units: set[tuple[str, str, int]] = {
        (a.dateKey, a.slotType, a.unitIndex)
        for a in ruleState.assignments
        if a.doctorId is not None
    }
    # (doctorId, dateKey) for any placed call-slot unit — drives
    # BACK_TO_BACK_CALL adjacency check.
    doctor_call_dates: set[tuple[str, str]] = {
        (a.doctorId, a.dateKey)
        for a in ruleState.assignments
        if a.doctorId is not None and a.slotType in call_slot_types
    }

    # ----- collect violations in canonical order -----
    reasons: list[ViolationReason] = []

    # Rule 1: BASELINE_ELIGIBILITY_FAIL.
    eligible_groups = eligibility_by_slot.get(proposedUnit.slotType, frozenset())
    doctor_group = group_by_doctor.get(proposedUnit.doctorId)
    if doctor_group is None or doctor_group not in eligible_groups:
        reasons.append(
            ViolationReason(
                code=RULE_BASELINE_ELIGIBILITY_FAIL,
                context={
                    "doctorId": proposedUnit.doctorId,
                    "doctorGroupId": doctor_group,
                    "slotType": proposedUnit.slotType,
                    "eligibleGroups": sorted(eligible_groups),
                },
            )
        )

    # Rule 2: SAME_DAY_HARD_BLOCK.
    if (proposedUnit.doctorId, proposedUnit.dateKey) in hard_block_dates:
        reasons.append(
            ViolationReason(
                code=RULE_SAME_DAY_HARD_BLOCK,
                context={
                    "doctorId": proposedUnit.doctorId,
                    "dateKey": proposedUnit.dateKey,
                },
            )
        )

    # Rule 3: SAME_DAY_ALREADY_HELD.
    if (proposedUnit.doctorId, proposedUnit.dateKey) in doctor_dates:
        reasons.append(
            ViolationReason(
                code=RULE_SAME_DAY_ALREADY_HELD,
                context={
                    "doctorId": proposedUnit.doctorId,
                    "dateKey": proposedUnit.dateKey,
                },
            )
        )

    # Rule 4: UNIT_ALREADY_FILLED. Per D-0029 this is the only rule that
    # branches on unitIndex.
    if (
        proposedUnit.dateKey,
        proposedUnit.slotType,
        proposedUnit.unitIndex,
    ) in filled_units:
        reasons.append(
            ViolationReason(
                code=RULE_UNIT_ALREADY_FILLED,
                context={
                    "dateKey": proposedUnit.dateKey,
                    "slotType": proposedUnit.slotType,
                    "unitIndex": proposedUnit.unitIndex,
                },
            )
        )

    # Rule 5: BACK_TO_BACK_CALL. Only fires when proposedUnit is on a call
    # slot. Adjacency checked via ISO date arithmetic (D-0033) so the rule
    # remains correct under future non-contiguous day axes.
    if proposedUnit.slotType in call_slot_types:
        try:
            prev_date = _shift_iso_date(proposedUnit.dateKey, -1)
            next_date = _shift_iso_date(proposedUnit.dateKey, +1)
        except ValueError:
            # Malformed dateKey — should not happen in a CONSUMABLE model
            # per parser_normalizer §13 / D-0033, but fail closed if it does.
            reasons.append(
                ViolationReason(
                    code=RULE_BACK_TO_BACK_CALL,
                    context={
                        "doctorId": proposedUnit.doctorId,
                        "dateKey": proposedUnit.dateKey,
                        "note": "non-ISO dateKey blocks adjacency check",
                    },
                )
            )
        else:
            adjacent_call = (
                (proposedUnit.doctorId, prev_date) in doctor_call_dates
                or (proposedUnit.doctorId, next_date) in doctor_call_dates
            )
            if adjacent_call:
                reasons.append(
                    ViolationReason(
                        code=RULE_BACK_TO_BACK_CALL,
                        context={
                            "doctorId": proposedUnit.doctorId,
                            "dateKey": proposedUnit.dateKey,
                            "slotType": proposedUnit.slotType,
                            "adjacentCallDates": sorted(
                                d
                                for d in (prev_date, next_date)
                                if (proposedUnit.doctorId, d) in doctor_call_dates
                            ),
                        },
                    )
                )

    if not reasons:
        return Decision.admit()

    # §12: canonical-ordered, full-list. Reasons were appended in canonical
    # order above by construction; the explicit sort is a defensive belt
    # against future rule additions landing out of order.
    order_index = {code: i for i, code in enumerate(CANONICAL_ORDER)}
    reasons.sort(key=lambda r: order_index.get(r.code, len(CANONICAL_ORDER)))
    return Decision.reject(tuple(reasons))
