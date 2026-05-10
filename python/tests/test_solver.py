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


# --- M7 C2 Task 2C: _candidate_seeds private override -------------------


def test_candidate_seeds_override_byte_identical_to_default() -> None:
    """Cross-surface byte-identity invariant per `docs/solver_contract.md`
    §12A.10 + M7 C2 Task 2C: passing `_candidate_seeds=derive_K_seeds(seed,
    K)` MUST produce byte-identical output to omitting the override and
    letting `solve()` derive internally. This is the property the Cloud
    Batch worker relies on — the orchestrator pre-derives all K_approved
    seeds via `derive_K_seeds`, partitions them per-task, and each worker
    calls `solve(_candidate_seeds=its_8_seeds)`. If override-vs-derive
    diverges, the local-CLI vs Cloud-Batch determinism re-audit at M7 C2
    T2G fails."""
    from rostermonster.solver import derive_K_seeds  # noqa: PLC0415

    model = _model()
    bounds = TerminationBounds(maxCandidates=3)
    r_default = _solve(model, seed=12345, terminationBounds=bounds)
    derived = derive_K_seeds(12345, 3)
    r_override = _solve(
        model, seed=12345, terminationBounds=bounds,
        _candidate_seeds=derived,
    )
    assert isinstance(r_default, CandidateSet)
    assert isinstance(r_override, CandidateSet)
    assert tuple(c.assignments for c in r_default.candidates) == tuple(
        c.assignments for c in r_override.candidates
    ), (
        "_candidate_seeds=derive_K_seeds(seed,K) diverged from omitting the "
        "override — Task 2C escape hatch is not byte-identical to default "
        "K-seed derivation; orchestrator/worker determinism is broken."
    )


def test_candidate_seeds_override_uses_provided_seeds() -> None:
    """Different `_candidate_seeds` values MUST drive different
    trajectories. If override is silently ignored and `solve()` falls back
    to deriving from `seed`, two runs with the same `seed` but different
    overrides would emit identical candidate sets — this test guards
    against that regression."""
    model = _model()
    bounds = TerminationBounds(maxCandidates=2)
    seeds_a = [111, 222]
    seeds_b = [333, 444]
    r_a = _solve(
        model, seed=12345, terminationBounds=bounds,
        _candidate_seeds=seeds_a,
    )
    r_b = _solve(
        model, seed=12345, terminationBounds=bounds,
        _candidate_seeds=seeds_b,
    )
    assert isinstance(r_a, CandidateSet)
    assert isinstance(r_b, CandidateSet)
    assert tuple(c.assignments for c in r_a.candidates) != tuple(
        c.assignments for c in r_b.candidates
    ), (
        "different _candidate_seeds produced byte-identical CandidateSets "
        "— override is being silently ignored"
    )


def test_candidate_seeds_length_mismatch_rejected() -> None:
    """`len(_candidate_seeds)` MUST equal `terminationBounds.maxCandidates`
    — the loop iterates over the seed list and any mismatch would either
    truncate trajectories silently or raise IndexError deep in the loop."""
    model = _model()
    bounds = TerminationBounds(maxCandidates=3)
    for bad in ([1, 2], [1, 2, 3, 4]):
        try:
            _solve(
                model, seed=42, terminationBounds=bounds,
                _candidate_seeds=bad,
            )
        except ValueError as e:
            assert "length" in str(e).lower() or "maxCandidates" in str(e)
            continue
        raise AssertionError(
            f"_candidate_seeds={bad!r} (vs maxCandidates=3) should have "
            f"raised ValueError"
        )


def test_candidate_seeds_non_list_rejected() -> None:
    """`_candidate_seeds` is typed `list[int]` and the validator MUST
    reject non-list inputs — tuples / strings / dicts at the boundary
    rather than letting them slip through and fail downstream."""
    model = _model()
    bounds = TerminationBounds(maxCandidates=2)
    for bad in ((1, 2), "12", {1: 2}):
        try:
            _solve(
                model, seed=42, terminationBounds=bounds,
                _candidate_seeds=bad,  # type: ignore[arg-type]
            )
        except ValueError as e:
            assert "list" in str(e)
            continue
        raise AssertionError(
            f"_candidate_seeds={bad!r} (non-list) should have raised "
            f"ValueError"
        )


def test_candidate_seeds_non_int_element_rejected() -> None:
    """Each element MUST be `int` (matching `derive_K_seeds`'s emitted
    type). Non-int elements (str, float, None) MUST reject so a bad
    upstream serialization (e.g., orchestrator JSON-decode glitch
    surfacing seeds as strings) fails fast at the solver boundary rather
    than degrading the trajectory silently."""
    model = _model()
    bounds = TerminationBounds(maxCandidates=2)
    for bad in (["1", "2"], [1.5, 2.5], [1, None]):
        try:
            _solve(
                model, seed=42, terminationBounds=bounds,
                _candidate_seeds=bad,  # type: ignore[arg-type]
            )
        except ValueError as e:
            assert "int" in str(e)
            continue
        raise AssertionError(
            f"_candidate_seeds={bad!r} (non-int element) should have "
            f"raised ValueError"
        )


def test_candidate_seeds_bool_element_rejected() -> None:
    """`bool` is an `int` subclass in Python; reject `True`/`False`
    elements explicitly so they don't slip through as `1`/`0` — same
    isinstance-with-bool-rejection discipline `solve()` applies to
    `seed` and `terminationBounds.maxCandidates` at §9 / §15."""
    model = _model()
    bounds = TerminationBounds(maxCandidates=2)
    for bad in ([True, False], [1, True]):
        try:
            _solve(
                model, seed=42, terminationBounds=bounds,
                _candidate_seeds=bad,  # type: ignore[arg-type]
            )
        except ValueError as e:
            assert "int" in str(e)
            continue
        raise AssertionError(
            f"_candidate_seeds={bad!r} (bool element) should have raised "
            f"ValueError"
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
    before any §10 output construction begins. Registered strategies as of
    M6 C1 are exactly {SEEDED_RANDOM_BLIND, LAHC} per §11.1."""
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


def test_lahc_requires_scoring_config() -> None:
    """Per docs/solver_contract.md §12A.6 + §11.2 extension clause: LAHC
    consumes scoring as a read-only oracle. solve() MUST validate
    scoringConfig presence at the boundary so the failure mode is "fail
    fast" not "AttributeError deep in LAHC inner loop"."""
    from rostermonster.solver import STRATEGY_LAHC

    model = _model()
    raised = False
    try:
        _solve(
            model,
            seed=1,
            terminationBounds=TerminationBounds(maxCandidates=1),
            strategyId=STRATEGY_LAHC,
            # NOTE: deliberately omitting scoringConfig.
        )
    except ValueError as e:
        raised = True
        assert "scoringConfig" in str(e), (
            f"ValueError should mention scoringConfig; got: {e!s}"
        )
    assert raised


def test_lahc_returns_unsatisfied_only_when_all_trajectories_fail() -> None:
    """Per docs/solver_contract.md §12A.8 + §14: LAHC's whole-run failure
    aggregation is "all K trajectories' seed-roster steps fail" — distinct
    from SEEDED_RANDOM_BLIND's "any unfillable attempt → fail".

    This test forces ALL trajectories to fail (1 ICU_ONLY doctor, demand
    includes MHD_CALL which no doctor can fill) and asserts:
    - LAHC returns UnsatisfiedResult (not a partial CandidateSet).
    - The error reasons reference both the strategyId AND a trajectory
      index, proving the per-trajectory aggregation path was exercised.

    Codex caught the inverse bug on PR #127 round 1: pre-fix, the solver
    aborted on the FIRST failed trajectory even for LAHC, which would
    discard subsequent successful trajectories and report whole-run
    failure when partial-success was the correct outcome.
    """
    from rostermonster.scorer.result import ScoringConfig
    from rostermonster.solver import LahcParams, STRATEGY_LAHC

    # ICU_ONLY only — no doctor eligible for MHD_CALL, every trajectory's
    # seed-roster step (run_seeded_random_blind) returns unfillable.
    model = _model(doctors=1, standby=False)
    scoring_config = ScoringConfig.first_release_defaults(model)
    params = LahcParams(historyListLength=10, idleThreshold=10, maxIters=20)
    result = _solve(
        model,
        seed=42,
        terminationBounds=TerminationBounds(maxCandidates=3),
        strategyId=STRATEGY_LAHC,
        scoringConfig=scoring_config,
        lahcParams=params,
    )
    assert isinstance(result, UnsatisfiedResult)
    assert result.unfilledDemand
    for entry in result.unfilledDemand:
        assert entry.slotType == "MHD_CALL"
    # Per-trajectory aggregation surfaces strategyId + trajectory index in
    # the failure message — proves the new aggregation path is exercised
    # rather than the legacy abort-on-first-failure path.
    for issue in result.reasons:
        assert issue.code == "UNFILLABLE_DEMAND"
        assert "LAHC" in issue.message, (
            f"strategyId should appear in LAHC failure message; got: {issue.message}"
        )
        assert "trajectory" in issue.message, (
            f"per-trajectory aggregation should mention trajectory index; "
            f"got: {issue.message}"
        )
    # §12A.9 LAHC diagnostics MUST also surface on UnsatisfiedResult — the
    # all-trajectories-failed branch needs the same transparency payload as
    # the success branch. Codex P2 round-3 caught this: pre-fix, the all-fail
    # branch dropped lahcHistoryListLength + perTrajectoryStatus on the floor.
    diag = result.diagnostics
    assert diag.lahcHistoryListLength == 10, diag.lahcHistoryListLength
    assert diag.lahcMaxIters == 20, diag.lahcMaxIters
    assert diag.lahcIdleThreshold == 10, diag.lahcIdleThreshold
    assert diag.seedDerivationFunction is not None
    assert diag.perTrajectoryStatus is not None and len(diag.perTrajectoryStatus) == 3
    assert all(s == "SEED_FAILED" for s in diag.perTrajectoryStatus), (
        f"all 3 trajectories should have SEED_FAILED status; got {diag.perTrajectoryStatus}"
    )
    # Codex P2 round-4: `reasons` MUST surface every (trajectory, unit) pair
    # — pre-fix, dedup-by-unit collapsed all 3 trajectories' failures into 1
    # ValidationIssue when they collided on the same unit. With 3 trajectories
    # all failing on the same K MHD_CALL units, len(reasons) should equal
    # 3 * len(unfilledDemand), but unfilledDemand stays deduped (operator-
    # facing summary).
    assert len(result.reasons) == 3 * len(result.unfilledDemand), (
        f"reasons should NOT be unit-deduped — got {len(result.reasons)} reasons "
        f"for {len(result.unfilledDemand)} unfilled units across 3 trajectories; "
        f"expected {3 * len(result.unfilledDemand)}"
    )
    # Each trajectory index 0/1/2 should appear among the reasons' contexts.
    seen_trajectories = {issue.context.get("trajectoryIndex") for issue in result.reasons}
    assert seen_trajectories == {0, 1, 2}, (
        f"all 3 trajectory indices should appear in reasons; got {seen_trajectories}"
    )


def test_lahc_smoke_returns_candidate_set() -> None:
    """Per docs/solver_contract.md §12A: LAHC dispatches end-to-end and
    emits a non-empty CandidateSet under valid inputs. Smoke-level test;
    byte-identical determinism + accept-rule unit semantics covered in
    M6 C2 Task 2C's integration tests."""
    from rostermonster.scorer.result import ScoringConfig, uniform_point_rules
    from rostermonster.solver import LahcParams, STRATEGY_LAHC

    model = _model()
    # `first_release_defaults(model)` builds a ScoringConfig with every
    # required component weight pre-populated + uniform_point_rules covering
    # the (slotType, dateKey) cross-product per scorer §11 + D-0038. Same
    # helper used throughout test_scorer.py.
    scoring_config = ScoringConfig.first_release_defaults(model)
    # Tight params for a fast smoke run — full defaults take seconds even on
    # this minimal fixture, while idleThreshold=10/maxIters=20 finish in ms.
    params = LahcParams(
        historyListLength=10, idleThreshold=10, maxIters=20
    )
    result = _solve(
        model,
        seed=1,
        terminationBounds=TerminationBounds(maxCandidates=2),
        strategyId=STRATEGY_LAHC,
        scoringConfig=scoring_config,
        lahcParams=params,
    )
    assert isinstance(result, CandidateSet), (
        f"LAHC should return CandidateSet under valid inputs; got "
        f"{type(result).__name__}"
    )
    assert len(result.candidates) == 2, (
        f"K=2 trajectories → 2 candidates; got {len(result.candidates)}"
    )
    assert result.diagnostics.strategyId == "LAHC"
    # Codex P2 round-4: LAHC inner-loop rule-engine rejections (proposed
    # swaps/reassignments that violated SAME_DAY_ALREADY_HELD, BACK_TO_BACK_CALL,
    # etc.) MUST tally into ruleEngineRejectionsByReason — pre-fix, LAHC
    # always returned an empty dict here, hiding real funnel work from
    # SearchDiagnostics §18.1. With 4 doctors / 2 days of demand under
    # rule constraints, at least some proposed moves get rejected.
    rejections = result.diagnostics.ruleEngineRejectionsByReason
    assert isinstance(rejections, dict)
    assert sum(rejections.values()) > 0, (
        f"LAHC should surface rule-engine rejection codes from move attempts; "
        f"got empty rejection counts: {rejections}"
    )
    # Codex P2 round-5: placementAttempts MUST include the seed-phase
    # (Phase 1/2 SEEDED_RANDOM_BLIND placement attempts) on top of the
    # inner-loop move-generator tries — pre-fix, both accumulators started
    # from zero so successful LAHC's `placementAttempts` undercounted by
    # exactly the seed phase's work. Sanity floor: every successful
    # trajectory must have placed at least N=len(roster) cells in Phase 2,
    # so total placementAttempts is at least 2 * sum(per-trajectory roster
    # sizes). Use a loose floor (each trajectory had >0 seed attempts).
    assert result.diagnostics.placementAttempts >= 2 * len(result.candidates[0].assignments), (
        f"placementAttempts should include seed-phase work for both trajectories; "
        f"got {result.diagnostics.placementAttempts}"
    )
    # Codex P2 round-6: placementAttempts MUST count actual rule-engine
    # evaluations — pre-fix, it counted random-sample try counts from
    # successful move generators only, omitting (a) the second
    # rule_engine call inside _generate_valid_swap and (b) all 100
    # exhausted tries when the primary move type returned None and the
    # fallback was used. Invariant: placementAttempts ≥ total rejection
    # count, since every rejection IS one rule-engine evaluation.
    assert result.diagnostics.placementAttempts >= sum(rejections.values()), (
        f"placementAttempts ({result.diagnostics.placementAttempts}) must "
        f"be ≥ summed rejections ({sum(rejections.values())}) — every "
        f"rejection is a rule-engine evaluation, so attempts < rejections "
        f"would be self-contradictory"
    )
    # Codex P2 round-7: per §12A.3, the only valid inner-loop termination
    # paths are `idleThreshold` and `maxIters`. Pre-fix, if both bounded
    # random move samplers missed in a single iteration the trajectory
    # would `break` and emit early — making perTrajectoryIters routinely
    # smaller than idleThreshold on sparse move spaces. Floor: every
    # successful trajectory must run at least `idleThreshold` iterations
    # (or hit `maxIters`, which is also >= idleThreshold here).
    per_iters = result.diagnostics.perTrajectoryIters
    assert per_iters is not None
    assert all(it >= 10 for it in per_iters), (
        f"every successful trajectory should run >= idleThreshold (10) "
        f"iterations before terminating; got {per_iters}"
    )


def test_lahc_byte_identical_under_fixed_inputs() -> None:
    """Per docs/solver_contract.md §12A.4 + §16: LAHC's K-trajectory output
    MUST be byte-identical given identical
    `(strategyId, normalizedModel, ruleEngine, seed, fillOrderPolicy,
    terminationBounds, preferenceSeeding, lahcParams, scoringConfig)` —
    same scoring oracle, same trajectory-seed derivation, same accept
    decisions, same emitted CandidateSet.
    """
    from rostermonster.scorer.result import ScoringConfig
    from rostermonster.solver import LahcParams, STRATEGY_LAHC

    model = _model()
    scoring_config = ScoringConfig.first_release_defaults(model)
    params = LahcParams(historyListLength=10, idleThreshold=10, maxIters=20)
    bounds = TerminationBounds(maxCandidates=3)
    r1 = _solve(
        model,
        seed=98765,
        terminationBounds=bounds,
        strategyId=STRATEGY_LAHC,
        scoringConfig=scoring_config,
        lahcParams=params,
    )
    r2 = _solve(
        model,
        seed=98765,
        terminationBounds=bounds,
        strategyId=STRATEGY_LAHC,
        scoringConfig=scoring_config,
        lahcParams=params,
    )
    assert r1 == r2, "LAHC outputs must be byte-identical under fixed inputs"


def test_lahc_byte_identical_across_pythonhashseed_values() -> None:
    """Per §12A.4 + §16: LAHC determinism MUST hold across Python processes
    with differing `PYTHONHASHSEED` values. Mirrors the SEEDED_RANDOM_BLIND
    cross-process determinism test (Codex P1 finding on PR #85). The LAHC
    inner loop adds extra PYTHONHASHSEED-sensitive surfaces (rule-engine
    rejection counter dict iteration, eligibility frozenset/dict iteration
    inside `_generate_valid_reassign`, history list dict-not-used) — they
    all need to either iterate stably or stay write-only.
    """
    import os
    import subprocess

    driver = (
        "import sys; sys.path.insert(0, %r);\n"
        "from rostermonster.rule_engine import evaluate;\n"
        "from rostermonster.solver import (\n"
        "    solve, TerminationBounds, LahcParams, STRATEGY_LAHC,\n"
        ");\n"
        "from rostermonster.scorer.result import ScoringConfig;\n"
        "import test_solver;\n"
        "model = test_solver._model();\n"
        "cfg = ScoringConfig.first_release_defaults(model);\n"
        "params = LahcParams(historyListLength=10, idleThreshold=10, maxIters=20);\n"
        "result = solve(model, ruleEngine=evaluate, seed=98765,\n"
        "    terminationBounds=TerminationBounds(maxCandidates=3),\n"
        "    strategyId=STRATEGY_LAHC, scoringConfig=cfg, lahcParams=params);\n"
        "for cand in result.candidates:\n"
        "    print(cand.candidateId, [(u.dateKey, u.slotType, u.unitIndex, u.doctorId) for u in cand.assignments]);\n"
    ) % str(ROOT)

    def run_with_seed(hash_seed: str) -> str:
        env = os.environ.copy()
        env["PYTHONHASHSEED"] = hash_seed
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
        f"LAHC output diverged across PYTHONHASHSEED values "
        f"(determinism §16 broken):\nseed=0:\n{out_a}\nseed=42:\n{out_b}\n"
        f"seed=99999:\n{out_c}"
    )


def test_lahc_distinct_trajectories_under_same_run() -> None:
    """Per §12A.2: K trajectories within a single LAHC run MUST be
    INDEPENDENT — derived from per-trajectory seeds via `derive(seed, i)`,
    no shared state, no information flow. Distinct seeds + independent
    moves should produce distinct rosters across the K candidates (the
    spec's whole point — defeating "K-observations-along-a-single-
    trajectory" near-clones per §12A.2's rejected alternative).
    """
    from rostermonster.scorer.result import ScoringConfig
    from rostermonster.solver import LahcParams, STRATEGY_LAHC

    model = _model()
    scoring_config = ScoringConfig.first_release_defaults(model)
    params = LahcParams(historyListLength=10, idleThreshold=10, maxIters=20)
    result = _solve(
        model,
        seed=12345,
        terminationBounds=TerminationBounds(maxCandidates=3),
        strategyId=STRATEGY_LAHC,
        scoringConfig=scoring_config,
        lahcParams=params,
    )
    assert isinstance(result, CandidateSet)
    assert len(result.candidates) == 3
    # Hash each candidate's full assignment vector. With 3 trajectories
    # each running 20-iteration LAHC over a non-trivial model, byte-
    # identical rosters across all K would indicate the trajectory seeds
    # collapsed — a determinism / independence regression.
    rosters = {
        tuple((u.dateKey, u.slotType, u.unitIndex, u.doctorId) for u in cand.assignments)
        for cand in result.candidates
    }
    assert len(rosters) >= 2, (
        f"K=3 LAHC trajectories should produce at least 2 distinct rosters; "
        f"got {len(rosters)} unique out of {len(result.candidates)}"
    )


def test_lahc_emits_best_roster_when_terminal_diverges() -> None:
    """Per §12A.1 step 5 + §12A.2: LAHC emits each trajectory's bestRoster
    (paired with bestSoFar at termination), NOT terminal currentRoster.
    Late acceptance (§12A.1.c dual-clause) routinely accepts moves below
    bestSoFar after first reaching it, so terminal can be strictly worse
    than best — and emitting terminal would discard a better candidate.

    Codex P2 round-1 on PR #128: just asserting `best >= terminal` is
    tautological — it's an invariant of `best_so_far` only advancing on
    strict improvement. The real regression to guard is "did LAHC emit
    the best-score roster, not the terminal-score one?" Pre-fix `run_lahc`
    returning `current_roster` instead of `best_roster` would still leave
    the diagnostic invariant intact.

    This test forces strict divergence (seed=1 + 500 maxIters yields a
    trajectory where best=-6.5 strictly beats terminal=-7.0 on the
    minimal 5-doctor / 5-day fixture) and then RE-SCORES the emitted
    candidate with the same scoring oracle — asserting the emitted
    roster scores to `bestSoFar`, NOT to `terminal currentScore`. If
    `run_lahc` regressed to emitting terminal, this test would fail
    even though the diagnostic invariant still held.
    """
    from rostermonster.scorer.result import ScoringConfig
    from rostermonster.solver import LahcParams, STRATEGY_LAHC
    from rostermonster.solver.lahc import make_scoring_oracle

    model = _model()
    scoring_config = ScoringConfig.first_release_defaults(model)
    # Larger budgets so late-acceptance has room to drop below best.
    # Empirically (seed=1, idleThreshold=50, maxIters=500), trajectory 1
    # diverges: best=-6.5, terminal=-7.0.
    params = LahcParams(historyListLength=20, idleThreshold=50, maxIters=500)
    result = _solve(
        model,
        seed=1,
        terminationBounds=TerminationBounds(maxCandidates=3),
        strategyId=STRATEGY_LAHC,
        scoringConfig=scoring_config,
        lahcParams=params,
    )
    assert isinstance(result, CandidateSet)
    diag = result.diagnostics
    assert diag.perTrajectoryBestScore is not None
    assert diag.perTrajectoryTerminalScore is not None

    # 1. Hard invariant: best >= terminal for every trajectory
    #    (best_so_far only advances on strict improvement).
    for i, (best, term) in enumerate(
        zip(diag.perTrajectoryBestScore, diag.perTrajectoryTerminalScore)
    ):
        assert best is not None and term is not None
        assert best >= term, (
            f"trajectory {i}: bestSoFar ({best}) should be >= terminal ({term}) — "
            f"§12A.1.f says best_so_far only advances on strict improvement"
        )

    # 2. Strict divergence MUST occur for at least one trajectory under
    #    these params/seed — otherwise the rest of this test is vacuous.
    divergent_indices = [
        i
        for i, (b, t) in enumerate(
            zip(diag.perTrajectoryBestScore, diag.perTrajectoryTerminalScore)
        )
        if b is not None and t is not None and b > t
    ]
    assert divergent_indices, (
        f"expected at least one trajectory with strict best > terminal under "
        f"seed=1 / maxIters=500; got per-trajectory scores best="
        f"{diag.perTrajectoryBestScore} terminal={diag.perTrajectoryTerminalScore}. "
        f"If params changed and divergence no longer triggers here, find a new "
        f"seed/params that does — this test is meant to exercise §12A.1 step 5."
    )

    # 3. The real regression guard: emitted candidate's roster MUST score
    #    to `bestSoFar`, NOT to terminal `currentScore`. Pre-fix LAHC
    #    returning terminal_roster would yield emitted_score == terminal,
    #    not best — caught here by re-scoring the emitted assignments
    #    with the same oracle LAHC consulted internally.
    oracle = make_scoring_oracle(scoring_config)
    for i in divergent_indices:
        candidate = result.candidates[i]
        emitted_score = oracle(model, candidate.assignments)
        best_score = diag.perTrajectoryBestScore[i]
        terminal_score = diag.perTrajectoryTerminalScore[i]
        assert emitted_score == best_score, (
            f"trajectory {i}: emitted candidate must score to bestSoFar "
            f"({best_score}); got {emitted_score}. §12A.1 step 5 requires "
            f"emitting bestRoster, not terminal currentRoster."
        )
        assert emitted_score != terminal_score, (
            f"trajectory {i}: emitted score ({emitted_score}) equals terminal "
            f"({terminal_score}) — this trajectory is supposed to be divergent, "
            f"so emitting terminal would silently match. Test setup error."
        )


def test_lahc_against_real_icu_hd_may_2026_fixture() -> None:
    """End-to-end: LAHC on the real-ICU/HD May 2026 dev-copy snapshot
    consumed by parser → solver → CandidateSet. Validates that LAHC
    works against a 22-doctor / 29-day / 116-slot real-world workload,
    not just the small synthetic `_model()` fixture. K-candidate emission
    shape per §12A.2.
    """
    import json
    from pathlib import Path
    from rostermonster.parser.admission import parse
    from rostermonster.parser.result import Consumability
    from rostermonster.pipeline import _snapshot_from_dict
    from rostermonster.solver import LahcParams, STRATEGY_LAHC
    from rostermonster.templates import icu_hd_template_artifact

    snapshot_path = (
        Path(__file__).resolve().parent / "data" / "icu_hd_may_2026_snapshot.json"
    )
    raw = json.loads(snapshot_path.read_text())
    snapshot = _snapshot_from_dict(raw)
    template = icu_hd_template_artifact()
    parsed = parse(snapshot, template)
    assert parsed.consumability is Consumability.CONSUMABLE
    model = parsed.normalizedModel
    scoring_config = parsed.scoringConfig
    assert scoring_config is not None

    # Tight params — ICU/HD May has 116 slot units across 22 doctors;
    # the seed phase + a 50-iter inner loop runs in seconds. K=2 is enough
    # to validate the K-trajectory shape against a real fixture without
    # bloating CI runtime.
    params = LahcParams(historyListLength=20, idleThreshold=50, maxIters=100)
    result = _solve(
        model,
        seed=2026_05_07,
        terminationBounds=TerminationBounds(maxCandidates=2),
        strategyId=STRATEGY_LAHC,
        scoringConfig=scoring_config,
        lahcParams=params,
    )
    assert isinstance(result, CandidateSet), (
        f"LAHC on real ICU/HD May 2026 fixture should yield CandidateSet; "
        f"got {type(result).__name__}"
    )
    assert len(result.candidates) == 2
    # Each candidate must cover the full demand (29 days × 4 slot types =
    # 116 demand units, all requiredCount=1).
    for cand in result.candidates:
        assert len(cand.assignments) == 116, (
            f"candidate {cand.candidateId}: expected 116 assignments "
            f"(29 days × 4 slot types); got {len(cand.assignments)}"
        )
        # All assignments populated (no doctorId=None on a successful run).
        assert all(a.doctorId is not None for a in cand.assignments)


def test_lahc_swap_probability_rejects_out_of_range() -> None:
    """`LahcParams.swapProbability` must be in [0.0, 1.0] per
    `docs/solver_contract.md` §12A.7. Validates fail-loud at construction."""
    from rostermonster.solver import LahcParams

    # In-range values accepted (0.0, 0.5, 1.0 endpoints).
    LahcParams(swapProbability=0.0)
    LahcParams(swapProbability=0.5)
    LahcParams(swapProbability=1.0)

    bad_values = [-0.1, 1.0001, 2.0, float("nan"), float("inf"), True, "0.5", None]
    for bad in bad_values:
        raised = False
        try:
            LahcParams(swapProbability=bad)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            raised = True
        assert raised, (
            f"LahcParams(swapProbability={bad!r}) should have raised but didn't"
        )


def test_lahc_swap_probability_extremes_complete_via_fallback() -> None:
    """Per §12A.1.a: when the primary move type's bounded random sampler
    returns None, the fallback (other move type) still fires. So
    swap_p=0.0 (reassign-primary, swap-fallback) and swap_p=1.0
    (swap-primary, reassign-fallback) MUST both produce a non-empty
    CandidateSet under valid inputs — neither degenerates to the
    soft-miss-then-idle-trip-immediately failure mode.

    Smoke-level: with the minimal _model() fixture and tight termination
    bounds, both extreme swap_p values should reach a valid winner.
    """
    from rostermonster.scorer.result import ScoringConfig
    from rostermonster.solver import LahcParams, STRATEGY_LAHC

    model = _model()
    scoring_config = ScoringConfig.first_release_defaults(model)

    for swap_p in (0.0, 1.0):
        result = _solve(
            model,
            seed=12345,
            terminationBounds=TerminationBounds(maxCandidates=2),
            strategyId=STRATEGY_LAHC,
            scoringConfig=scoring_config,
            lahcParams=LahcParams(
                historyListLength=10,
                idleThreshold=10,
                maxIters=20,
                swapProbability=swap_p,
            ),
        )
        assert isinstance(result, CandidateSet), (
            f"swap_p={swap_p}: extreme swap_p should still emit "
            f"CandidateSet via fallback move type; got {type(result).__name__}"
        )
        assert len(result.candidates) == 2, (
            f"swap_p={swap_p}: expected K=2 candidates; got "
            f"{len(result.candidates)}"
        )


def test_lahc_swap_probability_surfaces_in_search_diagnostics() -> None:
    """Per `docs/solver_contract.md` §12A.9: the resolved
    `swapProbability` MUST surface on `SearchDiagnostics.lahcSwapProbability`
    so FULL-retention artifacts at non-default `swap_p` are
    distinguishable from default-`0.5` runs and replayable. Asserts both
    extreme values (0.0, 1.0) and the default round-trip cleanly through
    the diagnostic.
    """
    from rostermonster.scorer.result import ScoringConfig
    from rostermonster.solver import LahcParams, STRATEGY_LAHC

    model = _model()
    scoring_config = ScoringConfig.first_release_defaults(model)
    bounds = TerminationBounds(maxCandidates=2)

    for swap_p in (0.0, 0.5, 1.0):
        result = _solve(
            model, seed=24680, terminationBounds=bounds,
            strategyId=STRATEGY_LAHC, scoringConfig=scoring_config,
            lahcParams=LahcParams(
                historyListLength=10, idleThreshold=10, maxIters=20,
                swapProbability=swap_p,
            ),
        )
        assert isinstance(result, CandidateSet)
        assert result.diagnostics.lahcSwapProbability == swap_p, (
            f"swap_p={swap_p}: SearchDiagnostics.lahcSwapProbability "
            f"should carry resolved value; got "
            f"{result.diagnostics.lahcSwapProbability}"
        )


def test_lahc_default_swap_probability_byte_identical_to_pre_field() -> None:
    """The `swapProbability` field was added during M6 C4 with default
    0.5 — chosen specifically to reproduce the historical hardcoded
    `rng.random() < 0.5` behavior. Two runs at default swap_p MUST be
    byte-identical (sanity check that the field plumbing didn't shift
    the RNG stream).
    """
    from rostermonster.scorer.result import ScoringConfig
    from rostermonster.solver import LahcParams, STRATEGY_LAHC

    model = _model()
    scoring_config = ScoringConfig.first_release_defaults(model)
    bounds = TerminationBounds(maxCandidates=3)

    # Default swap_p (0.5) implicit
    r1 = _solve(
        model, seed=98765, terminationBounds=bounds,
        strategyId=STRATEGY_LAHC, scoringConfig=scoring_config,
        lahcParams=LahcParams(
            historyListLength=10, idleThreshold=10, maxIters=20,
        ),
    )
    # Default swap_p (0.5) explicit
    r2 = _solve(
        model, seed=98765, terminationBounds=bounds,
        strategyId=STRATEGY_LAHC, scoringConfig=scoring_config,
        lahcParams=LahcParams(
            historyListLength=10, idleThreshold=10, maxIters=20,
            swapProbability=0.5,
        ),
    )
    assert r1 == r2, (
        "implicit-default vs explicit-default swap_p=0.5 should produce "
        "byte-identical CandidateSet (default chosen to preserve historical "
        "hardcoded 0.5 behavior)"
    )


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
    """Per §9 + §11: the solver MUST NOT consume the scorer interface, EXCEPT
    via §11.2's `scoringConsultation: "READ_ONLY_ORACLE"` extension clause
    (activated by `LAHC` per §12A.6 — M6 C1 closure / D-0067).

    Architectural invariant: every `rostermonster.solver` source file MUST
    NOT import anything from `rostermonster.scorer`, EXCEPT `lahc.py` which
    is the §12A.6-authorized exception (LAHC consults scoring as a read-only
    oracle to evaluate move proposals against the accept criterion). All
    other solver modules — including `solver.py`, `strategy.py`,
    `strategy_registry.py`, `cr_floor.py`, `result.py` — remain
    scoring-blind end-to-end.

    This test reads each Python source file under `solver/` and grep-checks
    for actual import statements (not arbitrary substring matches —
    docstrings legitimately cite the scorer contract by name)."""
    # §12A.6-authorized exception: lahc.py opts into the read-only scoring
    # oracle per §11.2's extension clause. Adding new strategy modules that
    # opt in: append the file name here AND ensure the corresponding
    # contract section is updated.
    ALLOWED_SCORER_IMPORTERS = {"lahc.py"}

    solver_root = Path(__file__).resolve().parent.parent / "rostermonster" / "solver"
    offenders: list[str] = []
    for src in sorted(solver_root.glob("*.py")):
        if src.name in ALLOWED_SCORER_IMPORTERS:
            continue
        for raw_line in src.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith(("from rostermonster.scorer", "import rostermonster.scorer")):
                offenders.append(f"{src.name}: {line}")
    assert not offenders, (
        f"solver package files import the scorer (violates "
        f"docs/solver_contract.md §9 + §11 scoring-blind rule): {offenders}. "
        f"Only {sorted(ALLOWED_SCORER_IMPORTERS)} are authorized per §12A.6."
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
