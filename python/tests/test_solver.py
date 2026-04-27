"""Tests for the solver per `docs/solver_contract.md`.

Covers Phase 1 / Phase 2 behavior, `crFloor` modes (`SMART_MEDIAN`,
`MANUAL`, `X = 0` disable), whole-run failure (`UnsatisfiedResult`),
seeded determinism (§16), and the scoring-blind property (the solver
package MUST NOT import the scorer).

Standalone runnable via `python3 python/tests/test_solver.py`.
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
    Doctor,
    DoctorGroup,
    EligibilityRule,
    FixedAssignment,
    MachineEffect,
    NormalizedModel,
    Request,
    RosterDay,
    RosterPeriod,
    SlotDemand,
    SlotTypeDefinition,
)
from rostermonster.rule_engine import evaluate as rule_engine_evaluate  # noqa: E402
from rostermonster.snapshot import (  # noqa: E402
    DayLocator,
    DoctorLocator,
    PrefilledAssignmentLocator,
    RequestLocator,
)
from rostermonster.solver import (  # noqa: E402
    CandidateSet,
    CrFloorConfig,
    CrFloorMode,
    PreferenceSeedingConfig,
    TerminationBounds,
    UnsatisfiedResult,
    compute_cr_floor,
    solve,
)


# --- Minimal-but-real model ----------------------------------------------


def _model(
    *,
    doctors: int = 5,
    days: int = 5,
    micu_call_required: int = 1,
    mhd_call_required: int = 1,
    standby: bool = False,
) -> NormalizedModel:
    """ICU/HD-shaped model: configurable doctor count, period length, demand."""
    period_days = tuple(
        RosterDay(
            dateKey=f"2026-05-{i + 1:02d}",
            dayIndex=i,
            provenance=DayLocator(dayIndex=i),
        )
        for i in range(days)
    )
    period = RosterPeriod(periodId="2026-05", periodLabel="May 2026", days=period_days)
    # 1 ICU_ONLY, 1 ICU_HD, 1 HD_ONLY by default; extras alternate ICU_HD/HD_ONLY.
    doctor_specs = [
        ("dr_icu", "ICU_ONLY", "MICU"),
        ("dr_both", "ICU_HD", "MICU_HD"),
        ("dr_hd", "HD_ONLY", "MHD"),
    ]
    while len(doctor_specs) < doctors:
        i = len(doctor_specs)
        if i % 2 == 0:
            doctor_specs.append((f"dr_both_{i}", "ICU_HD", "MICU_HD"))
        else:
            doctor_specs.append((f"dr_hd_{i}", "HD_ONLY", "MHD"))
    doctor_objs = tuple(
        Doctor(
            doctorId=did,
            displayName=did.replace("_", " ").title(),
            groupId=gid,
            provenance=DoctorLocator(sectionKey=sk, doctorIndexInSection=idx),
        )
        for idx, (did, gid, sk) in enumerate(doctor_specs[:doctors])
    )
    groups = (
        DoctorGroup(groupId="ICU_ONLY"),
        DoctorGroup(groupId="ICU_HD"),
        DoctorGroup(groupId="HD_ONLY"),
    )
    slot_types = (
        SlotTypeDefinition(slotType="MICU_CALL", displayLabel="MICU Call", slotFamily="MICU", slotKind="CALL"),
        SlotTypeDefinition(slotType="MHD_CALL", displayLabel="MHD Call", slotFamily="MHD", slotKind="CALL"),
    )
    if standby:
        slot_types = slot_types + (
            SlotTypeDefinition(slotType="MICU_STANDBY", displayLabel="MICU Standby", slotFamily="MICU", slotKind="STANDBY"),
            SlotTypeDefinition(slotType="MHD_STANDBY", displayLabel="MHD Standby", slotFamily="MHD", slotKind="STANDBY"),
        )
    demand_specs: list[tuple[str, int]] = [
        ("MICU_CALL", micu_call_required),
        ("MHD_CALL", mhd_call_required),
    ]
    if standby:
        demand_specs += [("MICU_STANDBY", 1), ("MHD_STANDBY", 1)]
    slot_demand = tuple(
        SlotDemand(
            dateKey=day.dateKey,
            slotType=slot_type,
            requiredCount=req,
            provenance=DayLocator(dayIndex=day.dayIndex),
        )
        for day in period_days
        for slot_type, req in demand_specs
    )
    eligibility = (
        EligibilityRule(slotType="MICU_CALL", eligibleGroups=("ICU_ONLY", "ICU_HD")),
        EligibilityRule(slotType="MHD_CALL", eligibleGroups=("ICU_HD", "HD_ONLY")),
    )
    if standby:
        eligibility = eligibility + (
            EligibilityRule(slotType="MICU_STANDBY", eligibleGroups=("ICU_ONLY", "ICU_HD")),
            EligibilityRule(slotType="MHD_STANDBY", eligibleGroups=("ICU_HD", "HD_ONLY")),
        )
    return NormalizedModel(
        period=period,
        doctors=doctor_objs,
        doctorGroups=groups,
        slotTypes=slot_types,
        slotDemand=slot_demand,
        eligibility=eligibility,
    )


def _solve(model, **kwargs):
    """Test-suite shim that injects the standard rule-engine handle into
    every `solve()` call. `ruleEngine` is a required input per solver §9
    input #2 and addressed in PR #85 round-3 fixes — production callers
    pass it explicitly; the test suite does the same via this helper to
    keep individual tests focused on the behavior they exercise."""
    kwargs.setdefault("ruleEngine", rule_engine_evaluate)
    return solve(model, **kwargs)


def _cr_request(doctor_id: str, day_index: int) -> Request:
    return Request(
        doctorId=doctor_id,
        dateKey=f"2026-05-{day_index + 1:02d}",
        rawRequestText="CR",
        recognizedRawTokens=("CR",),
        canonicalClasses=(CanonicalRequestClass.CR,),
        machineEffects=(MachineEffect.callPreferencePositive,),
        provenance=RequestLocator(sourceDoctorKey=doctor_id, dayIndex=day_index),
    )


# --- Output-shape sanity -------------------------------------------------


def test_solve_returns_candidate_set_on_simple_model() -> None:
    """Minimal model with sufficient doctor coverage → CandidateSet, never
    UnsatisfiedResult. `candidates` MUST be non-empty per §10.1."""
    model = _model()
    result = _solve(
        model,
        seed=42,
        terminationBounds=TerminationBounds(maxCandidates=3),
    )
    assert isinstance(result, CandidateSet)
    assert len(result.candidates) == 3
    for cand in result.candidates:
        assert cand.assignments  # non-empty
    # candidateId is a 1-indexed run-monotonic integer per
    # docs/selector_contract.md §16. Dense, no gaps, emission-order stable.
    assert [cand.candidateId for cand in result.candidates] == [1, 2, 3]
    assert all(isinstance(cand.candidateId, int) for cand in result.candidates)
    # Diagnostics shape.
    assert result.diagnostics.strategyId == "SEEDED_RANDOM_BLIND"
    assert result.diagnostics.fillOrderPolicy == "MOST_CONSTRAINED_FIRST"
    assert result.diagnostics.candidateEmitCount == 3
    assert result.diagnostics.unfilledDemandCount == 0
    assert result.diagnostics.seed == 42


def test_each_candidate_covers_full_demand() -> None:
    """Each TrialCandidate must carry one `AssignmentUnit` for every demand
    unit (full roster per §10.1)."""
    model = _model()
    result = _solve(
        model,
        seed=7,
        terminationBounds=TerminationBounds(maxCandidates=2),
    )
    assert isinstance(result, CandidateSet)
    expected_units = sum(sd.requiredCount for sd in model.slotDemand)
    for cand in result.candidates:
        assert len(cand.assignments) == expected_units


# --- §16 determinism -----------------------------------------------------


def test_byte_identical_under_fixed_inputs() -> None:
    """Per §16: identical inputs MUST produce identical outputs."""
    model = _model()
    bounds = TerminationBounds(maxCandidates=4)
    r1 = _solve(model, seed=12345, terminationBounds=bounds)
    r2 = _solve(model, seed=12345, terminationBounds=bounds)
    assert r1 == r2


def test_byte_identical_across_pythonhashseed_values() -> None:
    """Regression test for the Codex P1 finding on PR #85: the strategy
    MUST iterate `eligibleGroups` in a stable order (model-declared, not
    `frozenset`) so determinism holds across Python processes with
    differing `PYTHONHASHSEED`. Without the fix, two subprocesses with
    different hash seeds can emit different rosters under identical inputs,
    violating §16.

    Verified by running a tiny driver script under two distinct
    `PYTHONHASHSEED` env values and comparing the serialized result."""
    import os
    import subprocess

    driver = (
        "import sys; sys.path.insert(0, %r);\n"
        "from rostermonster.rule_engine import evaluate;\n"
        "from rostermonster.solver import solve, TerminationBounds;\n"
        "import test_solver;\n"
        "model = test_solver._model();\n"
        "result = solve(model, ruleEngine=evaluate, seed=12345, terminationBounds=TerminationBounds(maxCandidates=3));\n"
        "for cand in result.candidates:\n"
        "    print(cand.candidateId, [(u.dateKey, u.slotType, u.unitIndex, u.doctorId) for u in cand.assignments]);\n"
    ) % str(ROOT)

    def run_with_seed(hash_seed: str) -> str:
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = hash_seed
        # Need test_solver importable as a module from cwd.
        env["PYTHONPATH"] = (
            str(Path(__file__).resolve().parent) + os.pathsep + str(ROOT)
        )
        out = subprocess.run(
            [sys.executable, "-c", driver],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout

    out_a = run_with_seed("0")
    out_b = run_with_seed("42")
    out_c = run_with_seed("99999")
    assert out_a == out_b == out_c, (
        f"solver output diverged across PYTHONHASHSEED values "
        f"(determinism §16 broken):\nseed=0:\n{out_a}\nseed=42:\n{out_b}\n"
        f"seed=99999:\n{out_c}"
    )


def test_negated_seed_produces_distinct_output() -> None:
    """Per Codex P2 round-5 finding on PR #85: CPython's `Random.seed(int)`
    normalizes via `abs(...)`, so `solve(seed=k)` and `solve(seed=-k)` would
    drive the same RNG stream and emit identical rosters even though §9
    accepts the full signed 64-bit range. The fix masks the signed seed into
    an unsigned 64-bit bit pattern before RNG init, restoring the full
    entropy of the contract-declared input space."""
    model = _model()
    bounds = TerminationBounds(maxCandidates=2)
    r_pos = _solve(model, seed=12345, terminationBounds=bounds)
    r_neg = _solve(model, seed=-12345, terminationBounds=bounds)
    assert isinstance(r_pos, CandidateSet)
    assert isinstance(r_neg, CandidateSet)
    assert tuple(c.assignments for c in r_pos.candidates) != tuple(
        c.assignments for c in r_neg.candidates
    ), (
        "solve(seed=12345) and solve(seed=-12345) emitted identical rosters "
        "— signed-seed RNG aliasing is back; signed→unsigned mask was "
        "removed or bypassed"
    )


def test_different_seeds_can_produce_different_outputs() -> None:
    """Determinism is per-seed; different seeds may produce different rosters
    (not strictly required by the contract, but a healthy implementation
    should respond to seed variation in non-trivial models)."""
    model = _model()
    bounds = TerminationBounds(maxCandidates=3)
    r1 = _solve(model, seed=1, terminationBounds=bounds)
    r2 = _solve(model, seed=999, terminationBounds=bounds)
    assert isinstance(r1, CandidateSet)
    assert isinstance(r2, CandidateSet)
    # At least one candidate differs across seeds — not a normative property,
    # but flags pathologically-non-random implementations.
    a = tuple(c.assignments for c in r1.candidates)
    b = tuple(c.assignments for c in r2.candidates)
    assert a != b, (
        "different seeds produced byte-identical CandidateSets — strategy is "
        "not consuming the seed for randomization"
    )


# --- crFloor modes -------------------------------------------------------


def test_smart_median_floor_uses_median_cr_count() -> None:
    """Per §13.1: `X = floor(median(CR-count-per-doctor))`."""
    model = _model(doctors=3)
    # dr_icu has 3 CR requests, dr_both has 1, dr_hd has 0 → sorted [0,1,3]
    # → median = 1.
    model = replace(
        model,
        requests=(
            _cr_request("dr_icu", 0),
            _cr_request("dr_icu", 1),
            _cr_request("dr_icu", 2),
            _cr_request("dr_both", 3),
        ),
    )
    x = compute_cr_floor(model, CrFloorConfig(mode=CrFloorMode.SMART_MEDIAN))
    assert x == 1


def test_manual_floor_uses_manual_value() -> None:
    """Per §13.2: `X = manualValue`."""
    model = _model()
    x = compute_cr_floor(
        model,
        CrFloorConfig(mode=CrFloorMode.MANUAL, manualValue=4),
    )
    assert x == 4


def test_manual_floor_requires_manual_value() -> None:
    """Per §13.2: MANUAL without `manualValue` is a configuration defect."""
    model = _model()
    raised = False
    try:
        compute_cr_floor(model, CrFloorConfig(mode=CrFloorMode.MANUAL))
    except ValueError:
        raised = True
    assert raised


def test_manual_floor_rejects_negative() -> None:
    """Per §13.2: `manualValue` MUST be `>= 0`."""
    model = _model()
    raised = False
    try:
        compute_cr_floor(
            model,
            CrFloorConfig(mode=CrFloorMode.MANUAL, manualValue=-1),
        )
    except ValueError:
        raised = True
    assert raised


def test_manual_floor_rejects_non_integer() -> None:
    """Per §13.2: `manualValue` MUST be a non-negative INTEGER. Floats and
    bools are caller-side configuration bugs that should fail fast at
    `compute_cr_floor` rather than silently propagating into Phase 1's
    placement counter (e.g. `placed_for_doctor >= 1.5` would change Phase 1
    semantics relative to the integer contract). Codex P2 finding on PR #85."""
    model = _model()

    for bad_value in (1.5, 0.0, True, False, "3"):
        raised = False
        try:
            compute_cr_floor(
                model,
                # CrFloorConfig has `manualValue: int | None`; test runtime
                # rejection for callers that bypass the type hint.
                CrFloorConfig(mode=CrFloorMode.MANUAL, manualValue=bad_value),  # type: ignore[arg-type]
            )
        except ValueError:
            raised = True
        assert raised, (
            f"compute_cr_floor accepted non-integer manualValue {bad_value!r} "
            f"(type {type(bad_value).__name__}); should fail per §13.2"
        )


def test_manual_floor_accepts_string_mode_value() -> None:
    """`CrFloorMode` is a `(str, Enum)`, so callers MAY legitimately pass
    the bare string `"MANUAL"` per the contract's value vocabulary
    (docs/solver_contract.md §13). `compute_cr_floor` MUST compare modes by
    value equality, not object identity, so the string form is honored
    rather than silently falling through to `SMART_MEDIAN`. Codex P1
    finding on PR #85."""
    model = _model()
    # Construct CrFloorConfig with the string value directly — this skirts
    # the enum constructor that callers might use, but exercises the
    # mode-comparison path that takes whatever value lands in `config.mode`.
    config = CrFloorConfig(mode="MANUAL", manualValue=7)  # type: ignore[arg-type]
    x = compute_cr_floor(model, config)
    assert x == 7, (
        f"compute_cr_floor fell through to SMART_MEDIAN when given the "
        f"contract-valid string mode 'MANUAL'; got X={x}"
    )


def test_unknown_cr_floor_mode_is_rejected() -> None:
    """Modes outside `{SMART_MEDIAN, MANUAL}` are first-release defects per
    §13. Silently defaulting to SMART_MEDIAN would mask configuration
    typos."""
    model = _model()
    raised = False
    try:
        compute_cr_floor(
            model,
            CrFloorConfig(mode="GENEROUS", manualValue=2),  # type: ignore[arg-type]
        )
    except ValueError:
        raised = True
    assert raised


def test_x_zero_disables_phase_1() -> None:
    """Per §13.3: `X = 0` makes Phase 1 a no-op; strategy reduces to
    Phase 2 alone. With no CR requests, SMART_MEDIAN evaluates to 0 over
    a model where every doctor has 0 CRs."""
    model = _model()
    # No requests → median = 0 → Phase 1 no-op.
    result = _solve(
        model,
        seed=42,
        terminationBounds=TerminationBounds(maxCandidates=2),
        preferenceSeeding=PreferenceSeedingConfig(
            crFloor=CrFloorConfig(mode=CrFloorMode.MANUAL, manualValue=0)
        ),
    )
    assert isinstance(result, CandidateSet)
    assert result.diagnostics.crFloorComputed == 0


# --- Phase 1 honors CR placements ----------------------------------------


def test_phase1_honors_cr_when_floor_high_enough() -> None:
    """With X high enough and a single CR request, Phase 1 should place that
    doctor on a call slot on the CR's date in the emitted candidate."""
    model = _model()
    model = replace(model, requests=(_cr_request("dr_icu", 2),))
    result = _solve(
        model,
        seed=11,
        terminationBounds=TerminationBounds(maxCandidates=1),
        preferenceSeeding=PreferenceSeedingConfig(
            crFloor=CrFloorConfig(mode=CrFloorMode.MANUAL, manualValue=5)
        ),
    )
    assert isinstance(result, CandidateSet)
    cand = result.candidates[0]
    placements_for_dr_icu_on_day3 = [
        u
        for u in cand.assignments
        if u.doctorId == "dr_icu" and u.dateKey == "2026-05-03"
    ]
    # dr_icu MAY have ended up on MICU_CALL or MICU_STANDBY on the CR date.
    # Phase 1 specifically targets call slots; we assert MICU_CALL placement.
    call_placements = [
        u for u in placements_for_dr_icu_on_day3 if u.slotType == "MICU_CALL"
    ]
    assert call_placements, (
        f"Phase 1 did not honor dr_icu's CR on 2026-05-03: assignments "
        f"on that date for dr_icu: {placements_for_dr_icu_on_day3}"
    )


# --- Phase 2 fills remaining demand ---------------------------------------


def test_solver_emits_no_unfilled_units_in_normal_run() -> None:
    """On a feasibly-constrained model, Phase 2 fills all demand and no
    `doctorId=None` AssignmentUnits leak into emitted candidates."""
    model = _model()
    result = _solve(
        model,
        seed=99,
        terminationBounds=TerminationBounds(maxCandidates=2),
    )
    assert isinstance(result, CandidateSet)
    for cand in result.candidates:
        for unit in cand.assignments:
            assert unit.doctorId is not None, (
                f"unfilled AssignmentUnit leaked into CandidateSet: {unit}"
            )


# --- §14 whole-run failure -----------------------------------------------


def test_unsatisfied_result_when_demand_cannot_be_filled() -> None:
    """Per §14: if any demand unit cannot be filled under rule-engine
    validity, the solver returns `UnsatisfiedResult` — not a partial
    `CandidateSet`."""
    # 1 doctor (ICU_ONLY) but model has both MICU_CALL and MHD_CALL demand;
    # no doctor is eligible for MHD_CALL → guaranteed unfillable.
    model = _model(doctors=1, standby=False)
    result = _solve(
        model,
        seed=42,
        terminationBounds=TerminationBounds(maxCandidates=3),
    )
    assert isinstance(result, UnsatisfiedResult)
    assert result.unfilledDemand
    # Every unfilled unit MUST be MHD_CALL — ICU_ONLY can't fill MHD.
    for entry in result.unfilledDemand:
        assert entry.slotType == "MHD_CALL"
    # `reasons` carries one ValidationIssue per unfilled unit.
    assert len(result.reasons) == len(result.unfilledDemand)
    for issue in result.reasons:
        assert issue.code == "UNFILLABLE_DEMAND"


# --- Fixed assignments are first-class -----------------------------------


def test_unmatched_fixed_assignment_raises() -> None:
    """Per Codex P1 round-3 finding on PR #85: a `FixedAssignment` whose
    `(slotType, dateKey)` has no available demand unit is a parser-stage
    admission defect that the solver MUST surface — silent drop would
    omit an operator pin from the emitted CandidateSet, breaking the
    fixed-assignment preservation guarantee in solver §10.1."""
    model = _model(days=2)
    # MICU_CALL on day 0 has requiredCount=1; pin two doctors there → the
    # second cannot be seated and is an over-fixed admission defect.
    fixed_a = FixedAssignment(
        dateKey="2026-05-01",
        slotType="MICU_CALL",
        doctorId="dr_icu",
        provenance=PrefilledAssignmentLocator(
            surfaceId="MICU", rowOffset=0, dayIndex=0
        ),
    )
    fixed_b = FixedAssignment(
        dateKey="2026-05-01",
        slotType="MICU_CALL",
        doctorId="dr_both",
        provenance=PrefilledAssignmentLocator(
            surfaceId="MICU", rowOffset=1, dayIndex=0
        ),
    )
    model = replace(model, fixedAssignments=(fixed_a, fixed_b))
    raised = False
    err_msg = ""
    try:
        _solve(
            model,
            seed=1,
            terminationBounds=TerminationBounds(maxCandidates=1),
        )
    except ValueError as exc:
        raised = True
        err_msg = str(exc)
    assert raised, (
        "solver silently dropped an unmatchable FixedAssignment instead of "
        "raising; fixed-assignment preservation per solver §10.1 broken"
    )
    assert "2026-05-01" in err_msg and "MICU_CALL" in err_msg, (
        f"error message must name the offending fixed-assignment slot for "
        f"diagnostic clarity; got {err_msg!r}"
    )


def test_solver_consumes_supplied_rule_engine_handle() -> None:
    """Per Codex P2 round-3 finding on PR #85 + solver §9 input #2: the
    `ruleEngine` is an explicit input to `solve()`. A caller-supplied
    handle MUST be the only authority the solver consults for hard
    validity. Substituting a stub that always rejects MUST cause the
    solver to fail to fill any demand and return `UnsatisfiedResult`,
    proving the input is honored end-to-end (and that no internal
    rule-engine import shortcut bypasses the supplied handle)."""
    from rostermonster.rule_engine import Decision, ViolationReason

    def reject_all(model_arg, state_arg, proposed_arg) -> Decision:
        return Decision.reject(
            (
                ViolationReason(
                    code="BASELINE_ELIGIBILITY_FAIL",
                    context={"reason": "stub-reject-all"},
                ),
            )
        )

    model = _model()
    result = solve(
        model,
        ruleEngine=reject_all,
        seed=42,
        terminationBounds=TerminationBounds(maxCandidates=1),
    )
    assert isinstance(result, UnsatisfiedResult), (
        "solver bypassed the caller-supplied rule-engine handle — got "
        f"{type(result).__name__} instead of UnsatisfiedResult under a "
        f"reject-everything stub"
    )
    # Sanity: every unfilled unit is reported.
    assert result.unfilledDemand
    # And the stub's rejection reason is the only thing tallied.
    assert result.diagnostics.ruleEngineRejectionsByReason == {
        "BASELINE_ELIGIBILITY_FAIL": result.diagnostics.placementAttempts
    }


def test_fixed_assignment_is_carried_into_candidate_assignments() -> None:
    """Per `docs/domain_model.md` §10.1 + solver §10.1: TrialCandidate
    assignments cover the full roster INCLUDING FixedAssignment-derived
    units. The solver MUST not displace fixed assignments."""
    model = _model(days=2)
    fixed = FixedAssignment(
        dateKey="2026-05-01",
        slotType="MICU_CALL",
        doctorId="dr_icu",
        provenance=PrefilledAssignmentLocator(
            surfaceId="MICU", rowOffset=0, dayIndex=0
        ),
    )
    model = replace(model, fixedAssignments=(fixed,))
    result = _solve(
        model,
        seed=1,
        terminationBounds=TerminationBounds(maxCandidates=2),
    )
    assert isinstance(result, CandidateSet)
    for cand in result.candidates:
        # The fixed assignment lives in every emitted candidate.
        match = [
            u
            for u in cand.assignments
            if u.dateKey == "2026-05-01"
            and u.slotType == "MICU_CALL"
            and u.unitIndex == 0
        ]
        assert len(match) == 1
        assert match[0].doctorId == "dr_icu"


# --- Diagnostics ---------------------------------------------------------


def test_diagnostics_records_seed_and_cr_floor() -> None:
    """Per §13.4 + §18.1: `crFloorMode`, `crFloorComputed`, and `seed` MUST
    be recorded on `SearchDiagnostics`."""
    model = _model()
    model = replace(model, requests=(_cr_request("dr_icu", 0),))
    result = _solve(
        model,
        seed=2026,
        terminationBounds=TerminationBounds(maxCandidates=1),
        preferenceSeeding=PreferenceSeedingConfig(
            crFloor=CrFloorConfig(mode=CrFloorMode.MANUAL, manualValue=2)
        ),
    )
    assert isinstance(result, CandidateSet)
    assert result.diagnostics.seed == 2026
    assert result.diagnostics.crFloorMode == CrFloorMode.MANUAL
    assert result.diagnostics.crFloorComputed == 2


def test_diagnostics_records_rule_engine_rejections() -> None:
    """Per §18.1: rule-engine rejections by reason are aggregated into
    diagnostics across the search funnel. With multi-slot demand per day,
    Phase 2 evaluates every eligible doctor against every demand unit; the
    doctor already placed on day k's first slot is rule-rejected when
    considered for day k's second slot under `SAME_DAY_ALREADY_HELD`."""
    model = _model()
    result = _solve(
        model,
        seed=42,
        terminationBounds=TerminationBounds(maxCandidates=1),
    )
    assert isinstance(result, CandidateSet)
    # Some rejection MUST have been recorded — the diagnostics dict should
    # carry at least one rule code with positive count.
    assert result.diagnostics.ruleEngineRejectionsByReason, (
        "no rule-engine rejections logged across the search funnel; "
        "diagnostics empty"
    )
    assert sum(result.diagnostics.ruleEngineRejectionsByReason.values()) > 0
    assert result.diagnostics.placementAttempts > 0


# --- Strategy / fillOrderPolicy gating -----------------------------------


def test_unknown_strategy_id_is_rejected() -> None:
    """Per §11.1: strategy resolution MUST reject unregistered strategyIds
    before any §10 output construction begins."""
    model = _model()
    raised = False
    try:
        _solve(
            model,
            seed=1,
            terminationBounds=TerminationBounds(maxCandidates=1),
            strategyId="HILL_CLIMB_FUTURE",
        )
    except ValueError:
        raised = True
    assert raised


def test_unknown_fill_order_policy_is_rejected() -> None:
    """First-release fillOrderPolicy is exactly `MOST_CONSTRAINED_FIRST`
    per §12.3."""
    model = _model()
    raised = False
    try:
        _solve(
            model,
            seed=1,
            terminationBounds=TerminationBounds(maxCandidates=1),
            fillOrderPolicy="ROUND_ROBIN",
        )
    except ValueError:
        raised = True
    assert raised


def test_max_candidates_must_be_positive() -> None:
    """Per §15: `maxCandidates` MUST be a positive integer."""
    model = _model()
    raised = False
    try:
        _solve(model, seed=1, terminationBounds=TerminationBounds(maxCandidates=0))
    except ValueError:
        raised = True
    assert raised


def test_seed_rejects_non_integer_or_out_of_range() -> None:
    """Per §9 input #3 + Codex P2 round-4 finding on PR #85: `seed` MUST
    be a 64-bit signed integer. Python's `random.Random` accepts any
    hashable seed (str, float, bool, arbitrary-width int) and silently
    produces aliased/unexpected RNG streams; the solver MUST guard at the
    boundary so contract-invalid inputs fail fast."""
    model = _model()
    bounds = TerminationBounds(maxCandidates=1)
    bad_inputs: list = [
        1.5,
        0.0,
        True,
        False,
        "42",
        2**63,         # one past max signed int64
        -(2**63) - 1,  # one before min signed int64
    ]
    for bad in bad_inputs:
        raised = False
        try:
            _solve(
                model,
                seed=bad,  # type: ignore[arg-type]
                terminationBounds=bounds,
            )
        except ValueError:
            raised = True
        assert raised, (
            f"_solve accepted invalid seed {bad!r} "
            f"(type {type(bad).__name__}); should fail per §9"
        )

    # Boundary values MUST be accepted (signed int64 endpoints).
    _solve(model, seed=2**63 - 1, terminationBounds=bounds)
    _solve(model, seed=-(2**63), terminationBounds=bounds)


def test_max_candidates_rejects_non_integer() -> None:
    """Per §15 + Codex P2 round-3 finding on PR #85: `maxCandidates` MUST
    be a positive INTEGER. Floats and bools (which are int subclasses in
    Python) and strings are caller-side configuration bugs that should
    fail fast at the boundary rather than mishandling silently
    (`True` accepted as `1`, `1.5` failing later with a TypeError, etc.)."""
    model = _model()
    for bad_value in (1.5, 0.0, True, False, "2", "3.0"):
        raised = False
        try:
            _solve(
                model,
                seed=1,
                # Bypass the dataclass type hint to test runtime rejection.
                terminationBounds=TerminationBounds(maxCandidates=bad_value),  # type: ignore[arg-type]
            )
        except ValueError:
            raised = True
        assert raised, (
            f"_solve accepted non-integer maxCandidates {bad_value!r} "
            f"(type {type(bad_value).__name__}); should fail per §15"
        )


# --- Scoring-blind property (architectural invariant) --------------------


def test_phase2_dedupes_doctors_when_eligible_groups_repeat() -> None:
    """Per Codex P1 round-6 finding on PR #85: `EligibilityRule.eligibleGroups`
    is a tuple, so the contract does not forbid the same group from being
    listed twice. Phase 2 must dedupe per-unit candidate doctors while
    preserving first-seen order; otherwise duplicated entries would
    double-count in the `MOST_CONSTRAINED_FIRST` constraint count, skew the
    seeded tie-break, and could spuriously trigger `UnsatisfiedResult` even
    when a full valid assignment exists.

    Behavioral equivalence: a model with `eligibleGroups=("ICU_HD", "ICU_HD")`
    MUST produce the same output as one with `eligibleGroups=("ICU_HD",)`."""
    base = _model()
    bounds = TerminationBounds(maxCandidates=2)

    duplicated_eligibility = tuple(
        EligibilityRule(
            slotType=er.slotType,
            eligibleGroups=tuple(g for g in er.eligibleGroups for _ in range(2)),
        )
        for er in base.eligibility
    )
    dup_model = replace(base, eligibility=duplicated_eligibility)

    r_dedup = _solve(base, seed=7, terminationBounds=bounds)
    r_dup = _solve(dup_model, seed=7, terminationBounds=bounds)

    assert isinstance(r_dedup, CandidateSet)
    assert isinstance(r_dup, CandidateSet)
    assert tuple(c.assignments for c in r_dedup.candidates) == tuple(
        c.assignments for c in r_dup.candidates
    ), (
        "duplicated eligibleGroups produced a different CandidateSet from "
        "the deduped version — Phase 2 dedup is missing or order-unstable"
    )


def test_solver_package_does_not_import_scorer() -> None:
    """Per §9 + §11: the solver MUST NOT consume the scorer interface.
    Architectural invariant: `rostermonster.solver` and its submodules MUST
    NOT import anything from `rostermonster.scorer`. This test reads each
    Python source file under `solver/` and grep-checks for actual import
    statements (not arbitrary substring matches — docstrings legitimately
    cite the scorer contract by name)."""
    solver_root = Path(__file__).resolve().parent.parent / "rostermonster" / "solver"
    offenders: list[str] = []
    for src in sorted(solver_root.glob("*.py")):
        for raw_line in src.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith(("from rostermonster.scorer", "import rostermonster.scorer")):
                offenders.append(f"{src.name}: {line}")
    assert not offenders, (
        f"solver package files import the scorer (violates "
        f"docs/solver_contract.md §9 + §11 scoring-blind rule): {offenders}"
    )


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
