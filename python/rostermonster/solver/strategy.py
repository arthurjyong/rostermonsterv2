"""`SEEDED_RANDOM_BLIND` strategy implementation per `docs/solver_contract.md` §12.

Two-phase composite:
- Phase 1 — `CR_MINIMUM_PER_DOCTOR` preference seeding (§12, §12.1).
- Phase 2 — `MOST_CONSTRAINED_FIRST` fill (§12, §12.2).

Both phases consult the rule engine for every proposed placement (§12) and
remain scoring-blind end-to-end (§9, §11).

Determinism is byte-identical under fixed inputs per §16: the only entropy
source is the per-candidate `random.Random(...)` instance derived from the
caller-supplied seed; iteration over model entities follows model-declared
order; tie-breaking uses seeded shuffles.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from random import Random

from rostermonster.domain import (
    AssignmentUnit,
    CanonicalRequestClass,
    NormalizedModel,
    Request,
)
from rostermonster.rule_engine import (
    Decision,
    RuleState,
    ViolationReason,
    evaluate,
)


# --- Demand-unit bookkeeping -------------------------------------------------


@dataclass(frozen=True)
class _DemandUnit:
    """One unit of demand keyed by `(dateKey, slotType, unitIndex)`.

    Materialized from `SlotDemand.requiredCount` — a `requiredCount`-of-N row
    expands into N units indexed `0..N-1`. FixedAssignments occupy units in
    ascending `unitIndex` order (D-0029: same-`(dateKey, slotType)` units are
    equivalent for doctor admissibility but `UNIT_ALREADY_FILLED` correctly
    branches on `unitIndex`).
    """

    dateKey: str
    slotType: str
    unitIndex: int


def _materialize_demand(model: NormalizedModel) -> list[_DemandUnit]:
    """Expand `SlotDemand` into per-unit demand entries in model-declared
    order: outer = SlotDemand iteration, inner = `unitIndex` 0..requiredCount-1."""
    return [
        _DemandUnit(sd.dateKey, sd.slotType, i)
        for sd in model.slotDemand
        for i in range(sd.requiredCount)
    ]


def _seat_fixed_assignments(
    model: NormalizedModel,
    demand: list[_DemandUnit],
) -> tuple[list[AssignmentUnit], list[_DemandUnit]]:
    """Adopt `FixedAssignment[]` into `AssignmentUnit[]` form, occupying the
    lowest-indexed available `unitIndex` per `(dateKey, slotType)`. Returns
    `(seated_units, residual_demand)`.

    FixedAssignments without a matching unfilled demand cell are dropped
    silently here — this is parser-stage admission territory per
    `docs/parser_normalizer_contract.md` §14, not a solver responsibility.
    """
    by_slot_day: dict[tuple[str, str], list[_DemandUnit]] = defaultdict(list)
    for unit in demand:
        by_slot_day[(unit.dateKey, unit.slotType)].append(unit)
    for k in by_slot_day:
        by_slot_day[k].sort(key=lambda u: u.unitIndex)

    seated: list[AssignmentUnit] = []
    consumed: set[tuple[str, str, int]] = set()
    for fixed in model.fixedAssignments:
        candidates = by_slot_day.get((fixed.dateKey, fixed.slotType), [])
        target = next(
            (
                u
                for u in candidates
                if (u.dateKey, u.slotType, u.unitIndex) not in consumed
            ),
            None,
        )
        if target is None:
            continue
        consumed.add((target.dateKey, target.slotType, target.unitIndex))
        seated.append(
            AssignmentUnit(
                dateKey=target.dateKey,
                slotType=target.slotType,
                unitIndex=target.unitIndex,
                doctorId=fixed.doctorId,
            )
        )
    residual = [
        u
        for u in demand
        if (u.dateKey, u.slotType, u.unitIndex) not in consumed
    ]
    return seated, residual


# --- Eligibility lookups -----------------------------------------------------


def _eligibility_index(model: NormalizedModel) -> dict[str, frozenset[str]]:
    """`slotType → frozenset(eligibleGroups)` index built once per solve."""
    return {er.slotType: frozenset(er.eligibleGroups) for er in model.eligibility}


def _doctors_by_id(model: NormalizedModel) -> dict[str, str]:
    """`doctorId → groupId` index for fast eligibility checks."""
    return {d.doctorId: d.groupId for d in model.doctors}


def _call_slot_types(model: NormalizedModel) -> frozenset[str]:
    return frozenset(st.slotType for st in model.slotTypes if st.slotKind == "CALL")


# --- Rule-engine integration -------------------------------------------------


@dataclass
class _RejectionTally:
    """Mutable accumulator for `SearchDiagnostics.ruleEngineRejectionsByReason`
    and the placement-attempts counter. Kept private so the strategy can
    update it as it walks rejections without threading a dict through every
    helper. The solver entry copies the counts into a frozen `dict[str, int]`
    before constructing `SearchDiagnostics`.
    """

    counts: dict[str, int]
    attempts: int = 0

    def record(self, reasons: tuple[ViolationReason, ...]) -> None:
        for reason in reasons:
            self.counts[reason.code] = self.counts.get(reason.code, 0) + 1


def _try_place(
    model: NormalizedModel,
    state: RuleState,
    proposed: AssignmentUnit,
    tally: _RejectionTally,
) -> Decision:
    """Single-call rule-engine adjudication; rejections are tallied for
    diagnostics. Every call counts as one placement attempt."""
    tally.attempts += 1
    decision = evaluate(model, state, proposed)
    if not decision.valid:
        tally.record(decision.reasons)
    return decision


# --- Phase 1 -----------------------------------------------------------------


def _doctor_cr_requests(model: NormalizedModel, doctor_id: str) -> list[Request]:
    """All CR-class requests for a doctor in model-declared `requests` order."""
    return [
        req
        for req in model.requests
        if req.doctorId == doctor_id
        and CanonicalRequestClass.CR in req.canonicalClasses
    ]


def _phase1_seed_cr(
    model: NormalizedModel,
    cr_floor_x: int,
    seated: list[AssignmentUnit],
    residual: list[_DemandUnit],
    rng: Random,
    tally: _RejectionTally,
) -> tuple[list[AssignmentUnit], list[_DemandUnit]]:
    """Phase 1 best-effort CR seeding per §12 + §12.1.

    For each doctor d with CR requests, attempts up to `X` placements onto
    call-slot demand units on the CR's date where d is eligible. Each
    placement is rule-engine-validated. Below-floor outcomes are accepted
    (§12.1 — Phase 1 is best-effort, never fails the run).

    `X = 0` short-circuits the entire phase per §13.3.
    """
    if cr_floor_x <= 0:
        return list(seated), list(residual)

    eligibility = _eligibility_index(model)
    doctor_group = _doctors_by_id(model)
    call_slots = _call_slot_types(model)

    # Doctor iteration order is seeded for cross-candidate variation; CR list
    # within a doctor is also seeded (§12.1 — "in strategy-internal
    # deterministic order under seed").
    doctor_ids = [d.doctorId for d in model.doctors]
    rng.shuffle(doctor_ids)

    state_units = list(seated)
    remaining = list(residual)

    for doctor_id in doctor_ids:
        crs = _doctor_cr_requests(model, doctor_id)
        if not crs:
            continue
        rng.shuffle(crs)
        placed_for_doctor = 0
        group = doctor_group[doctor_id]
        for cr in crs:
            if placed_for_doctor >= cr_floor_x:
                break
            # Eligible call-slot demand units on this CR's date.
            slot_options = [
                u
                for u in remaining
                if u.dateKey == cr.dateKey
                and u.slotType in call_slots
                and group in eligibility.get(u.slotType, frozenset())
            ]
            if not slot_options:
                continue
            rng.shuffle(slot_options)
            for option in slot_options:
                proposed = AssignmentUnit(
                    dateKey=option.dateKey,
                    slotType=option.slotType,
                    unitIndex=option.unitIndex,
                    doctorId=doctor_id,
                )
                decision = _try_place(
                    model, RuleState(assignments=tuple(state_units)), proposed, tally
                )
                if decision.valid:
                    state_units.append(proposed)
                    remaining.remove(option)
                    placed_for_doctor += 1
                    break
            # If no rule-engine-valid option found, §12.1 says skip this CR
            # and try next; nothing else to do here.

    return state_units, remaining


# --- Phase 2 -----------------------------------------------------------------


def _phase2_fill(
    model: NormalizedModel,
    seated: list[AssignmentUnit],
    residual: list[_DemandUnit],
    rng: Random,
    tally: _RejectionTally,
) -> tuple[list[AssignmentUnit], list[_DemandUnit]]:
    """Phase 2 `MOST_CONSTRAINED_FIRST` fill per §12 + §12.2.

    On each iteration, picks the demand unit with the fewest
    eligible-and-rule-engine-valid doctors; places one of those doctors;
    removes the demand unit from `remaining`. Tie-breaks on demand-unit
    selection AND doctor selection are seeded (§12.2). Returns
    `(state, leftover_unfillable_demand)`. Whole-run failure happens when
    `leftover` is non-empty — handled by the caller per §14.
    """
    eligibility = _eligibility_index(model)
    doctor_group = _doctors_by_id(model)

    state_units = list(seated)
    remaining = list(residual)

    # Cache eligible-doctors-by-group once outside the loop. This narrows the
    # rule-engine evaluations to the eligibility-passing slice.
    doctor_ids_by_group: dict[str, list[str]] = defaultdict(list)
    for d in model.doctors:
        doctor_ids_by_group[d.groupId].append(d.doctorId)

    while remaining:
        scored: list[tuple[int, _DemandUnit, list[str]]] = []
        for unit in remaining:
            eligible_groups = eligibility.get(unit.slotType, frozenset())
            candidate_doctors: list[str] = []
            for group in eligible_groups:
                candidate_doctors.extend(doctor_ids_by_group.get(group, []))
            valid: list[str] = []
            current_state = RuleState(assignments=tuple(state_units))
            for doc_id in candidate_doctors:
                proposed = AssignmentUnit(
                    dateKey=unit.dateKey,
                    slotType=unit.slotType,
                    unitIndex=unit.unitIndex,
                    doctorId=doc_id,
                )
                decision = _try_place(model, current_state, proposed, tally)
                if decision.valid:
                    valid.append(doc_id)
            scored.append((len(valid), unit, valid))

        # Tie-break demand-unit picks under seed: rng-shuffle the equal-score
        # set, then pick min-by-count.
        rng.shuffle(scored)
        scored.sort(key=lambda t: t[0])

        top_count, picked_unit, picked_eligible = scored[0]
        if top_count == 0:
            # No valid doctor for this demand unit — whole-run failure.
            unfillable = [t[1] for t in scored if t[0] == 0]
            return state_units, unfillable

        rng.shuffle(picked_eligible)
        chosen_doctor = picked_eligible[0]
        state_units.append(
            AssignmentUnit(
                dateKey=picked_unit.dateKey,
                slotType=picked_unit.slotType,
                unitIndex=picked_unit.unitIndex,
                doctorId=chosen_doctor,
            )
        )
        remaining.remove(picked_unit)

    return state_units, []


# --- Public composite-strategy entry ----------------------------------------


@dataclass(frozen=True)
class _StrategyOutcome:
    """Internal return shape for one candidate's strategy run.

    `assignments` is the full-roster tuple including FixedAssignment-derived
    units and solver-placed units. `unfillable` is non-empty iff the run
    branches to `UnsatisfiedResult` per §14. `attempts` is the placement-
    attempt count (rule-engine evaluations across both phases) for
    diagnostics. `rejection_counts` is the per-rule rejection tally for
    `SearchDiagnostics.ruleEngineRejectionsByReason`.
    """

    assignments: tuple[AssignmentUnit, ...]
    unfillable: tuple[_DemandUnit, ...]
    attempts: int
    rejection_counts: dict[str, int]


def run_seeded_random_blind(
    model: NormalizedModel,
    seed: int,
    cr_floor_x: int,
) -> _StrategyOutcome:
    """One candidate construction under `SEEDED_RANDOM_BLIND` per §12.

    `seed` is the per-candidate seed (not the run-level seed) — the solver
    entry derives per-candidate seeds from the caller's run seed plus the
    candidate index for cross-candidate variation while preserving overall
    determinism (§16).

    Returns a `_StrategyOutcome` that captures both the success branch
    (`unfillable` empty → caller emits `TrialCandidate`) and the failure
    branch (`unfillable` non-empty → caller emits `UnsatisfiedResult` per
    §14, no partial CandidateSet).
    """
    rng = Random(seed)
    tally = _RejectionTally(counts={})

    demand = _materialize_demand(model)
    seated, residual = _seat_fixed_assignments(model, demand)

    state, residual = _phase1_seed_cr(
        model, cr_floor_x, seated, residual, rng, tally
    )
    state, unfillable = _phase2_fill(model, state, residual, rng, tally)

    return _StrategyOutcome(
        assignments=tuple(state),
        unfillable=tuple(unfillable),
        attempts=tally.attempts,
        rejection_counts=dict(tally.counts),
    )
