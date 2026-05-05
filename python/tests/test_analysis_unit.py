"""Unit tests for the analyzer engine per `docs/analysis_contract.md`.

Covers admission (§9.1 / §9.2 / §9.5 / §10.0 / §11), selection (§11
cascade), aggregates (§10 + §13), and serialization (§15 byte-
identical determinism). Synthetic inputs throughout — integration
tests on real ICU/HD data live in `test_analysis_integration.py`.

Standalone runnable via `python3 python/tests/test_analysis_unit.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rostermonster.analysis.admission import (  # noqa: E402
    AnalyzerInputError,
    TOP_K_MAX,
    TOP_K_MIN,
    admit,
    validate_coherence,
    validate_doctor_resolvability,
    validate_full_retention,
    validate_non_empty_candidates,
    validate_success_branch,
    validate_top_k,
)
from rostermonster.analysis.aggregates import (  # noqa: E402
    _gini,
    _is_weekend,
    build_hot_and_locked_days,
    build_pairwise_hamming,
)
from rostermonster.analysis.output import (  # noqa: E402
    ANALYSIS_CONTRACT_VERSION,
    AnalyzerOutput,
    AnalyzerSource,
    ComparisonAggregates,
    TopKResult,
    render_analyzer_output_json,
)
from rostermonster.analysis.selection import select_top_k


# -- helpers --

def _candidate(
    candidate_id: int,
    total_score: float,
    *,
    pbg: float = 0.0,
    cr: float = 0.0,
    assignments: list[dict] | None = None,
) -> dict:
    """Build a sidecar-shape candidate dict for cascade testing."""
    return {
        "candidateId": candidate_id,
        "assignments": assignments if assignments is not None else [],
        "score": {
            "totalScore": total_score,
            "direction": "HIGHER_IS_BETTER",
            "components": {
                "pointBalanceGlobal": pbg,
                "crReward": cr,
                "pointBalanceWithinSection": 0.0,
                "spacingPenalty": 0.0,
                "preLeavePenalty": 0.0,
                "unfilledPenalty": 0.0,
                "dualEligibleIcuBonus": 0.0,
                "standbyAdjacencyPenalty": 0.0,
                "standbyCountFairnessPenalty": 0.0,
            },
        },
    }


def _expect_raises(exc_type, fn, *args, match: str | None = None, **kwargs):
    """Tiny helper mirroring pytest.raises but for the standalone
    runner pattern used in this repo's tests."""
    raised = False
    try:
        fn(*args, **kwargs)
    except exc_type as e:
        raised = True
        if match is not None and match not in str(e):
            raise AssertionError(
                f"expected message containing {match!r}; got {e!r}"
            )
    assert raised, f"expected {exc_type.__name__} to be raised"


# -- admission: §11 K bounds --

def test_validate_top_k_accepts_in_range() -> None:
    validate_top_k(1)
    validate_top_k(5)
    validate_top_k(20)


def test_validate_top_k_rejects_zero() -> None:
    _expect_raises(AnalyzerInputError, validate_top_k, 0, match="≥")


def test_validate_top_k_rejects_above_max() -> None:
    _expect_raises(AnalyzerInputError, validate_top_k, 21, match="≤")


def test_validate_top_k_rejects_negative() -> None:
    _expect_raises(AnalyzerInputError, validate_top_k, -1, match="≥")


def test_validate_top_k_rejects_non_integer() -> None:
    _expect_raises(AnalyzerInputError, validate_top_k, 5.0,
                   match="must be an integer")


def test_validate_top_k_rejects_bool() -> None:
    _expect_raises(AnalyzerInputError, validate_top_k, True,
                   match="must be an integer")


def test_top_k_constants() -> None:
    assert TOP_K_MIN == 1
    assert TOP_K_MAX == 20


# -- admission: §9.1 FULL retention --

def test_validate_full_retention_accepts_full() -> None:
    validate_full_retention(
        {"finalResultEnvelope": {"retentionMode": "FULL"}}
    )


def test_validate_full_retention_rejects_best_only() -> None:
    _expect_raises(
        AnalyzerInputError,
        validate_full_retention,
        {"finalResultEnvelope": {"retentionMode": "BEST_ONLY"}},
        match="retentionMode == FULL",
    )


def test_validate_full_retention_rejects_missing_envelope() -> None:
    _expect_raises(
        AnalyzerInputError,
        validate_full_retention,
        {},
        match="missing 'finalResultEnvelope'",
    )


# -- admission: §9.2 success branch --

def test_validate_success_branch_accepts_allocation_result() -> None:
    envelope = {
        "finalResultEnvelope": {
            "retentionMode": "FULL",
            "result": {"winnerAssignment": [], "winnerScore": {}},
        }
    }
    validate_success_branch(envelope)


def test_validate_success_branch_rejects_failure_branch() -> None:
    envelope = {
        "finalResultEnvelope": {
            "retentionMode": "FULL",
            "result": {"unfilledDemand": [], "reasons": []},
        }
    }
    _expect_raises(
        AnalyzerInputError, validate_success_branch, envelope,
        match="UnsatisfiedResultEnvelope",
    )


# -- admission: §9.5 coherence --

def test_validate_coherence_accepts_matching_triple() -> None:
    snapshot = {"metadata": {"snapshotId": "snap_X"}}
    envelope = {
        "finalResultEnvelope": {
            "runEnvelope": {"snapshotRef": "snap_X", "runId": "run_Y"}
        }
    }
    sidecar = {"runId": "run_Y"}
    validate_coherence(snapshot, envelope, sidecar)


def test_validate_coherence_rejects_snapshot_mismatch() -> None:
    snapshot = {"metadata": {"snapshotId": "snap_X"}}
    envelope = {
        "finalResultEnvelope": {
            "runEnvelope": {"snapshotRef": "snap_OTHER", "runId": "r"}
        }
    }
    sidecar = {"runId": "r"}
    _expect_raises(AnalyzerInputError, validate_coherence,
                   snapshot, envelope, sidecar,
                   match="snapshot↔envelope")


def test_validate_coherence_rejects_sidecar_run_mismatch() -> None:
    snapshot = {"metadata": {"snapshotId": "snap_X"}}
    envelope = {
        "finalResultEnvelope": {
            "runEnvelope": {"snapshotRef": "snap_X", "runId": "run_A"}
        }
    }
    sidecar = {"runId": "run_DIFFERENT"}
    _expect_raises(AnalyzerInputError, validate_coherence,
                   snapshot, envelope, sidecar,
                   match="envelope↔sidecar")


# -- admission: §10.0 doctor resolvability --

def test_validate_doctor_resolvability_accepts_known_ids() -> None:
    snapshot = {"doctorRecords": [
        {"sourceDoctorKey": "DR_A"},
        {"sourceDoctorKey": "DR_B"},
    ]}
    sidecar = {"candidates": [{
        "assignments": [
            {"doctorId": "DR_A"},
            {"doctorId": "DR_B"},
            {"doctorId": None},  # unfilled, ignored
        ]
    }]}
    validate_doctor_resolvability(snapshot, sidecar)


def test_validate_doctor_resolvability_rejects_unknown_id() -> None:
    snapshot = {"doctorRecords": [{"sourceDoctorKey": "DR_A"}]}
    sidecar = {"candidates": [{
        "assignments": [{"doctorId": "DR_GHOST"}]
    }]}
    _expect_raises(AnalyzerInputError, validate_doctor_resolvability,
                   snapshot, sidecar,
                   match="doctor-identity drift")


# -- admission: non-empty candidates --

def test_validate_non_empty_candidates_accepts_one_or_more() -> None:
    validate_non_empty_candidates({"candidates": [{"assignments": []}]})


def test_validate_non_empty_candidates_rejects_empty_list() -> None:
    _expect_raises(AnalyzerInputError, validate_non_empty_candidates,
                   {"candidates": []},
                   match="cannot have zero candidates")


def test_validate_non_empty_candidates_rejects_missing_field() -> None:
    _expect_raises(AnalyzerInputError, validate_non_empty_candidates,
                   {"runId": "x"},
                   match="missing or not a list")


# -- admission: full admit pipeline order --

def test_admit_runs_all_checks() -> None:
    snapshot = {
        "metadata": {"snapshotId": "S"},
        "doctorRecords": [{"sourceDoctorKey": "D"}],
    }
    envelope = {
        "finalResultEnvelope": {
            "retentionMode": "FULL",
            "runEnvelope": {"snapshotRef": "S", "runId": "R"},
            "result": {"winnerAssignment": [], "winnerScore": {}},
        }
    }
    sidecar = {"runId": "R", "candidates": [
        {"assignments": [{"doctorId": "D"}]}
    ]}
    admit(snapshot, envelope, sidecar, requested_top_k=5)


def test_admit_short_circuits_on_top_k() -> None:
    _expect_raises(AnalyzerInputError, admit,
                   {}, {}, {}, requested_top_k=0,
                   match="top-K")


# -- selection: §11 cascade --

def test_select_top_k_orders_by_total_score_desc() -> None:
    candidates = [
        _candidate(1, 10.0),
        _candidate(2, 30.0),
        _candidate(3, 20.0),
    ]
    selected = select_top_k(candidates, requested=3)
    assert [c["candidateId"] for c in selected] == [2, 3, 1]


def test_select_top_k_truncates_to_requested() -> None:
    candidates = [_candidate(i, float(i)) for i in range(1, 11)]
    selected = select_top_k(candidates, requested=3)
    assert len(selected) == 3
    assert [c["candidateId"] for c in selected] == [10, 9, 8]


def test_select_top_k_returns_fewer_than_requested_when_pool_small() -> None:
    candidates = [_candidate(1, 10.0), _candidate(2, 5.0)]
    selected = select_top_k(candidates, requested=5)
    assert len(selected) == 2
    assert [c["candidateId"] for c in selected] == [1, 2]


def test_select_top_k_cascade_breaks_tie_on_pbg() -> None:
    candidates = [
        _candidate(1, 10.0, pbg=-5.0, cr=2.0),
        _candidate(2, 10.0, pbg=-3.0, cr=1.0),  # less-negative → wins
    ]
    selected = select_top_k(candidates, requested=2)
    assert selected[0]["candidateId"] == 2


def test_select_top_k_cascade_falls_through_to_cr() -> None:
    candidates = [
        _candidate(1, 10.0, pbg=-3.0, cr=2.0),  # higher cr → wins
        _candidate(2, 10.0, pbg=-3.0, cr=1.0),
    ]
    selected = select_top_k(candidates, requested=2)
    assert selected[0]["candidateId"] == 1


def test_select_top_k_cascade_falls_through_to_candidate_id_numeric() -> None:
    # Critical: numeric not lexicographic. "10" < "2" lexicographically
    # would invert the intended order; numeric comparison gives 2 first.
    candidates = [
        _candidate(10, 10.0, pbg=-3.0, cr=2.0),
        _candidate(2, 10.0, pbg=-3.0, cr=2.0),  # lower numeric id → wins
    ]
    selected = select_top_k(candidates, requested=2)
    assert selected[0]["candidateId"] == 2  # NOT 10


def test_select_top_k_rejects_missing_pbg_component() -> None:
    bad = {
        "candidateId": 1,
        "assignments": [],
        "score": {
            "totalScore": 10.0,
            "components": {"crReward": 0.0},  # missing pointBalanceGlobal
        },
    }
    _expect_raises(AnalyzerInputError, select_top_k, [bad], 1,
                   match="pointBalanceGlobal")


# -- aggregates: weekend classification --

def test_is_weekend_saturday_sunday() -> None:
    assert _is_weekend("2026-05-02")  # Saturday
    assert _is_weekend("2026-05-03")  # Sunday
    assert not _is_weekend("2026-05-04")  # Monday
    assert not _is_weekend("2026-05-08")  # Friday


# -- aggregates: gini --

def test_gini_zero_distribution() -> None:
    assert _gini([0.0, 0.0, 0.0]) == 0.0


def test_gini_perfectly_equal() -> None:
    assert _gini([5.0, 5.0, 5.0]) == 0.0


def test_gini_unequal_distribution() -> None:
    assert _gini([0.0, 0.0, 10.0]) > 0.5  # heavily skewed


# -- aggregates: pairwise Hamming --

def test_pairwise_hamming_identical_candidates_are_zero() -> None:
    cand1 = {
        "candidateId": 1,
        "assignments": [
            {"dateKey": "2026-05-01", "slotType": "MICU_CALL",
             "unitIndex": 0, "doctorId": "DR_A"},
        ],
    }
    cand2 = {
        "candidateId": 2,
        "assignments": [
            {"dateKey": "2026-05-01", "slotType": "MICU_CALL",
             "unitIndex": 0, "doctorId": "DR_A"},
        ],
    }
    h = build_pairwise_hamming([cand1, cand2])
    assert h[1][2] == 0
    assert h[2][1] == 0
    assert h[1][1] == 0


def test_pairwise_hamming_different_doctors_count_as_diff() -> None:
    cand1 = {
        "candidateId": 1,
        "assignments": [
            {"dateKey": "2026-05-01", "slotType": "S",
             "unitIndex": 0, "doctorId": "DR_A"},
            {"dateKey": "2026-05-02", "slotType": "S",
             "unitIndex": 0, "doctorId": "DR_B"},
        ],
    }
    cand2 = {
        "candidateId": 2,
        "assignments": [
            {"dateKey": "2026-05-01", "slotType": "S",
             "unitIndex": 0, "doctorId": "DR_C"},
            {"dateKey": "2026-05-02", "slotType": "S",
             "unitIndex": 0, "doctorId": "DR_B"},
        ],
    }
    h = build_pairwise_hamming([cand1, cand2])
    assert h[1][2] == 1


def test_pairwise_hamming_unit_index_matters() -> None:
    cand1 = {
        "candidateId": 1,
        "assignments": [
            {"dateKey": "2026-05-01", "slotType": "S",
             "unitIndex": 0, "doctorId": "A"},
            {"dateKey": "2026-05-01", "slotType": "S",
             "unitIndex": 1, "doctorId": "B"},
        ],
    }
    cand2 = {
        "candidateId": 2,
        "assignments": [
            {"dateKey": "2026-05-01", "slotType": "S",
             "unitIndex": 0, "doctorId": "B"},
            {"dateKey": "2026-05-01", "slotType": "S",
             "unitIndex": 1, "doctorId": "A"},
        ],
    }
    h = build_pairwise_hamming([cand1, cand2])
    assert h[1][2] == 2


# -- aggregates: hot/locked days --

def test_hot_and_locked_days_classification() -> None:
    cand1 = {
        "candidateId": 1,
        "assignments": [
            {"dateKey": "2026-05-01", "slotType": "S",
             "unitIndex": 0, "doctorId": "A"},
            {"dateKey": "2026-05-02", "slotType": "S",
             "unitIndex": 0, "doctorId": "X"},
        ],
    }
    cand2 = {
        "candidateId": 2,
        "assignments": [
            {"dateKey": "2026-05-01", "slotType": "S",
             "unitIndex": 0, "doctorId": "A"},
            {"dateKey": "2026-05-02", "slotType": "S",
             "unitIndex": 0, "doctorId": "Y"},
        ],
    }
    hot, locked = build_hot_and_locked_days(
        [cand1, cand2], ["2026-05-01", "2026-05-02"]
    )
    assert [e.dateKey for e in locked] == ["2026-05-01"]
    assert [e.dateKey for e in hot] == ["2026-05-02"]
    assert hot[0].distinctAssignments == 2


# -- output serialization --

def test_render_analyzer_output_emits_trailing_newline() -> None:
    output = AnalyzerOutput(
        contractVersion=ANALYSIS_CONTRACT_VERSION,
        generatedAt="2026-05-04T10:00:00Z",
        source=AnalyzerSource(
            runId="r", seed=12345,
            sourceSpreadsheetId="s", sourceTabName="t",
        ),
        topK=TopKResult(requested=0, returned=0, candidates=[]),
        comparison=ComparisonAggregates(
            pairwiseHammingDistance={},
            hotDays=[], lockedDays=[],
            perCandidateEquity={},
        ),
        doctorIdMap={},
    )
    text = render_analyzer_output_json(output)
    assert text.endswith("\n")
    payload = json.loads(text)
    assert payload["contractVersion"] == 1
    assert payload["generatedAt"] == "2026-05-04T10:00:00Z"


def test_render_analyzer_output_byte_identical_on_repeated_call() -> None:
    output = AnalyzerOutput(
        contractVersion=ANALYSIS_CONTRACT_VERSION,
        generatedAt="2026-05-04T10:00:00Z",
        source=AnalyzerSource(
            runId="r", seed=12345,
            sourceSpreadsheetId="s", sourceTabName="t",
        ),
        topK=TopKResult(requested=0, returned=0, candidates=[]),
        comparison=ComparisonAggregates(
            pairwiseHammingDistance={},
            hotDays=[], lockedDays=[],
            perCandidateEquity={},
        ),
        doctorIdMap={"D_X": "Dr. X"},
    )
    a = render_analyzer_output_json(output)
    b = render_analyzer_output_json(output)
    assert a == b
    assert a.encode("utf-8") == b.encode("utf-8")


# -- standalone runner ------------------------------------------------

def _all_tests():
    return [v for k, v in globals().items()
            if k.startswith("test_") and callable(v)]


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
