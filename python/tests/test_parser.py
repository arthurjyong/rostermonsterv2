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
    MachineEffect,
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
    ISSUE_PREFILLED_DOCTOR_NAME_AMBIGUOUS,
    ISSUE_PREFILLED_DOCTOR_NAME_UNRESOLVED,
    ISSUE_PREFILLED_DOCTOR_TWO_SLOTS_SAME_DAY,
    ISSUE_PREFILLED_SURFACE_UNKNOWN,
    ISSUE_REQUEST_DOCTOR_REF_BROKEN,
    ISSUE_TEMPLATE_MISMATCH,
)
from rostermonster.parser.request_semantics import (  # noqa: E402
    ISSUE_REQUEST_DUPLICATE_TOKEN,
    ISSUE_REQUEST_MALFORMED_GRAMMAR,
    ISSUE_REQUEST_UNKNOWN_TOKEN,
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
