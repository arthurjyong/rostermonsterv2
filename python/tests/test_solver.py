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
    result = solve(
        model,
        seed=42,
        terminationBounds=TerminationBounds(maxCandidates=3),
    )
    assert isinstance(result, CandidateSet)
    assert len(result.candidates) == 3
    for cand in result.candidates:
        assert cand.assignments  # non-empty
        # candidateId pattern.
        assert cand.candidateId.startswith("c") and len(cand.candidateId) == 5
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
    result = solve(
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
    r1 = solve(model, seed=12345, terminationBounds=bounds)
    r2 = solve(model, seed=12345, terminationBounds=bounds)
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
        "from rostermonster.solver import solve, TerminationBounds;\n"
        "import test_solver;\n"
        "model = test_solver._model();\n"
        "result = solve(model, seed=12345, terminationBounds=TerminationBounds(maxCandidates=3));\n"
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


def test_different_seeds_can_produce_different_outputs() -> None:
    """Determinism is per-seed; different seeds may produce different rosters
    (not strictly required by the contract, but a healthy implementation
    should respond to seed variation in non-trivial models)."""
    model = _model()
    bounds = TerminationBounds(maxCandidates=3)
    r1 = solve(model, seed=1, terminationBounds=bounds)
    r2 = solve(model, seed=999, terminationBounds=bounds)
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


def test_x_zero_disables_phase_1() -> None:
    """Per §13.3: `X = 0` makes Phase 1 a no-op; strategy reduces to
    Phase 2 alone. With no CR requests, SMART_MEDIAN evaluates to 0 over
    a model where every doctor has 0 CRs."""
    model = _model()
    # No requests → median = 0 → Phase 1 no-op.
    result = solve(
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
    result = solve(
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
    result = solve(
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
    result = solve(
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
    result = solve(
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
    result = solve(
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
    result = solve(
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
        solve(
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
        solve(
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
        solve(model, seed=1, terminationBounds=TerminationBounds(maxCandidates=0))
    except ValueError:
        raised = True
    assert raised


# --- Scoring-blind property (architectural invariant) --------------------


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
