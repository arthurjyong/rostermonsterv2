"""Tests for the shared post-aggregation pipeline per
`python/rostermonster_service/post_aggregation.py` (extracted at M7 C4
T2A.2 PR-A from `lahc_orchestrator.py`).

Two surfaces consume this module: `worker.py`'s inline finalize step
(operator path) + `lahc_orchestrator.py`'s `/compute-lahc-test`
maintainer path. Tests here cover the surface-agnostic pipeline
(score → select → wrapper envelope, plus the new `build_full_sidecar_dict`
helper); surface-specific behavior is covered in `test_worker.py` and
`test_lahc_orchestrator.py`.

Light-weight by design — no real LAHC solver runs (the orchestrator
test path already exercises end-to-end byte-identity via
`test_lahc_orchestrator.py::test_orchestrator_worker_integration_round_trip`
which carries `@pytest.mark.slow`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rostermonster.solver import derive_K_seeds  # noqa: E402
from rostermonster_service import post_aggregation as pa  # noqa: E402


_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "data" / "icu_hd_may_2026_snapshot.json"
)


def _load_snapshot_dict() -> dict:
    return json.loads(_FIXTURE_PATH.read_text())


def _build_synthetic_agg(*, master_seed: int, K: int,
                          succeed_indices: list[int]) -> dict:
    """Build an `agg` dict matching what `worker_main` emits after
    aggregation — synthetic SUCCEEDED entries for `succeed_indices`,
    synthetic SEED_FAILED for the rest. Avoids running the real solver."""
    seeds = derive_K_seeds(master_seed, K)
    candidates = []
    failed = []
    for i, seed in enumerate(seeds):
        if i in succeed_indices:
            candidates.append({
                "taskIndex": 0,
                "candidateSeed": seed,
                "assignments": [
                    {"dateKey": "2026-05-01", "slotType": "ICU",
                     "unitIndex": 0, "doctorId": "dr_a"},
                ],
                "iters": 100,
                "acceptedMoves": 50,
                "bestScore": 0.5,
                "terminalScore": 0.4,
            })
        else:
            failed.append({
                "taskIndex": 0,
                "candidateSeed": seed,
                "unfilledDemand": [],
            })
    return {
        "candidates": candidates,
        "failedTrajectories": failed,
        "trajectoryExceptions": [],
        "aggregateAttempts": 100,
        "aggregateRejectionsByReason": {},
        "resultPresent": True,
        "perTaskResults": [{}],
    }


# --- assignment_unit_from_dict ------------------------------------------


def test_assignment_unit_from_dict_round_trip() -> None:
    """Inverse of `_to_jsonable(AssignmentUnit)` — keys map directly to
    the AssignmentUnit dataclass fields."""
    unit = pa.assignment_unit_from_dict({
        "dateKey": "2026-05-01",
        "slotType": "ICU",
        "unitIndex": 2,
        "doctorId": "dr_x",
    })
    assert unit.dateKey == "2026-05-01"
    assert unit.slotType == "ICU"
    assert unit.unitIndex == 2
    assert unit.doctorId == "dr_x"


def test_assignment_unit_from_dict_coerces_unit_index_to_int() -> None:
    """Worker emits `unitIndex` as int via `_to_jsonable`, but a
    maintainer hand-crafted result.json could pass a stringified int.
    Helper coerces."""
    unit = pa.assignment_unit_from_dict({
        "dateKey": "2026-05-01",
        "slotType": "ICU",
        "unitIndex": "3",
        "doctorId": "dr_y",
    })
    assert unit.unitIndex == 3


# --- build_post_aggregation_envelope ------------------------------------


def test_build_post_aggregation_envelope_success_branch() -> None:
    """K' > 0 → SUCCESS branch produces a wrapper envelope with
    finalResultEnvelope.result carrying winnerAssignment + score."""
    snapshot_dict = _load_snapshot_dict()
    master_seed = 42
    K = 2
    agg = _build_synthetic_agg(
        master_seed=master_seed, K=K, succeed_indices=[0, 1],
    )

    wrapper = pa.build_post_aggregation_envelope(
        snapshot_dict=snapshot_dict, agg=agg,
        master_seed=master_seed, K_approved=K,
        run_id="test-runid",
    )

    assert wrapper is not None
    final = wrapper["finalResultEnvelope"]
    # SUCCESS branch carries an AllocationResult with winnerAssignment
    assert "result" in final
    assert "winnerAssignment" in final["result"]
    # Diagnostics MUST have K entries (1 per trajectory)
    diag = final["result"]["searchDiagnostics"]
    assert len(diag["perTrajectoryStatus"]) == K
    assert all(s == "SUCCEEDED" for s in diag["perTrajectoryStatus"])


def test_build_post_aggregation_envelope_failure_branch_K_prime_zero() -> None:
    """K' == 0 → FAILURE branch synthesizes UnsatisfiedResult; wrapper
    envelope still non-null per §10.3 (bound shim's `applyWriteback`
    requires non-null envelope on UNSATISFIED)."""
    snapshot_dict = _load_snapshot_dict()
    master_seed = 42
    K = 4
    # All trajectories failed — pre-fix this would return None / skip
    # the failure branch
    seeds = derive_K_seeds(master_seed, K)
    agg = {
        "candidates": [],
        "failedTrajectories": [
            {"taskIndex": 0, "candidateSeed": s,
             "unfilledDemand": [
                 {"dateKey": "2026-05-01", "slotType": "ICU",
                  "unitIndex": 0},
             ]}
            for s in seeds
        ],
        "trajectoryExceptions": [],
        "aggregateAttempts": 100,
        "aggregateRejectionsByReason": {"BASELINE_ELIGIBILITY_FAIL": 5},
        "resultPresent": True,
        "perTaskResults": [{}],
    }

    wrapper = pa.build_post_aggregation_envelope(
        snapshot_dict=snapshot_dict, agg=agg,
        master_seed=master_seed, K_approved=K,
        run_id="test-runid-failed",
    )

    assert wrapper is not None, (
        "FAILURE branch (K'==0) MUST still produce a wrapper envelope "
        "per §10.3"
    )
    final = wrapper["finalResultEnvelope"]
    # Failure-branch result has unfilledDemand + reasons populated
    result = final["result"]
    assert "unfilledDemand" in result
    assert len(result["unfilledDemand"]) >= 1
    assert "reasons" in result
    assert len(result["reasons"]) >= 1


def test_build_post_aggregation_diagnostics_mix_succeeded_seed_failed() -> None:
    """§12A.9: per-trajectory arrays MUST carry an entry for EVERY
    trajectory the solver attempted, with `0` / `None` for SEED_FAILED.
    Verifies the lookup-by-candidateSeed walk in
    `build_post_aggregation_envelope`."""
    snapshot_dict = _load_snapshot_dict()
    master_seed = 42
    K = 4
    # SUCCEEDED at indices [0, 2]; SEED_FAILED at [1, 3]
    agg = _build_synthetic_agg(
        master_seed=master_seed, K=K, succeed_indices=[0, 2],
    )

    wrapper = pa.build_post_aggregation_envelope(
        snapshot_dict=snapshot_dict, agg=agg,
        master_seed=master_seed, K_approved=K,
        run_id="test-runid-mix",
    )

    assert wrapper is not None
    diag = wrapper["finalResultEnvelope"]["result"]["searchDiagnostics"]
    assert diag["perTrajectoryStatus"] == [
        "SUCCEEDED", "SEED_FAILED", "SUCCEEDED", "SEED_FAILED",
    ]
    # SEED_FAILED entries get 0 for iters/accepted, None for scores
    assert diag["perTrajectoryIters"][1] == 0
    assert diag["perTrajectoryAcceptedMoves"][1] == 0
    assert diag["perTrajectoryBestScore"][1] is None
    assert diag["perTrajectoryTerminalScore"][1] is None


# --- build_unsatisfied_from_aggregation ---------------------------------


def test_build_unsatisfied_from_aggregation_dedupes_unfilled_demand() -> None:
    """Per `solver.py::_build_unsatisfied`'s discipline: `unfilledDemand`
    deduped by `(dateKey, slotType, unitIndex)`. Two trajectories failing
    on the same unit produce ONE entry in unfilledDemand but TWO
    entries in `reasons` (one per failed trajectory × unit)."""
    from rostermonster.solver import SearchDiagnostics, STRATEGY_LAHC

    diagnostics = SearchDiagnostics(
        strategyId=STRATEGY_LAHC,
        fillOrderPolicy="MOST_CONSTRAINED_FIRST",
        crFloorMode="SMART_MEDIAN",
        crFloorComputed=0.0,
        seed=42,
        placementAttempts=10,
        ruleEngineRejectionsByReason={},
        candidateEmitCount=0,
        unfilledDemandCount=0,
    )
    agg = {
        "failedTrajectories": [
            {
                "candidateSeed": 111, "taskIndex": 0,
                "unfilledDemand": [
                    {"dateKey": "2026-05-01", "slotType": "ICU", "unitIndex": 0},
                ],
            },
            {
                "candidateSeed": 222, "taskIndex": 0,
                "unfilledDemand": [
                    # Same unit as 111 → deduped in unfilledDemand
                    {"dateKey": "2026-05-01", "slotType": "ICU", "unitIndex": 0},
                    # Different unit → distinct entry
                    {"dateKey": "2026-05-02", "slotType": "ICU", "unitIndex": 1},
                ],
            },
        ],
    }

    result = pa.build_unsatisfied_from_aggregation(
        agg=agg, diagnostics=diagnostics, master_seed=42,
    )

    # 2 distinct units → 2 unfilledDemand entries
    assert len(result.unfilledDemand) == 2
    # 3 (trajectory, unit) pairs → 3 reasons entries
    assert len(result.reasons) == 3
    # Diagnostics get unfilledDemandCount overridden to len(unfilled_list)
    assert result.diagnostics.unfilledDemandCount == 2


# --- build_full_sidecar_dict --------------------------------------------


def test_build_full_sidecar_dict_success_path() -> None:
    """The full sidecar carries `runId`, `generationTimestamp`,
    `schemaVersion`, + a `candidates` list with assignments + score.
    The analyzer admission code keys on these fields per
    `docs/analysis_contract.md` §10.0."""
    snapshot_dict = _load_snapshot_dict()
    master_seed = 42
    K = 2
    agg = _build_synthetic_agg(
        master_seed=master_seed, K=K, succeed_indices=[0, 1],
    )

    sidecar = pa.build_full_sidecar_dict(
        snapshot_dict=snapshot_dict, agg=agg,
        master_seed=master_seed, K_approved=K,
        run_id="test-runid",
    )

    assert sidecar is not None
    assert "schemaVersion" in sidecar
    assert "runId" in sidecar
    assert "generationTimestamp" in sidecar
    assert "candidates" in sidecar
    assert len(sidecar["candidates"]) == K
    # candidateId is 1-indexed dense
    assert [c["candidateId"] for c in sidecar["candidates"]] == [1, 2]
    # Each candidate has assignments + score
    for cand in sidecar["candidates"]:
        assert "assignments" in cand
        assert "score" in cand
        assert "totalScore" in cand["score"]
        assert "direction" in cand["score"]
        assert "components" in cand["score"]


def test_build_full_sidecar_dict_returns_none_when_k_prime_zero() -> None:
    """No candidates → no sidecar — analyzer doesn't run on K'==0 per
    `docs/analysis_contract.md` §9.2 + §10A.6's `analyzerOutput: null`
    convention for UNSATISFIED."""
    snapshot_dict = _load_snapshot_dict()
    agg = {
        "candidates": [],
        "failedTrajectories": [],
        "trajectoryExceptions": [],
        "aggregateAttempts": 0,
        "aggregateRejectionsByReason": {},
        "resultPresent": True,
        "perTaskResults": [{}],
    }
    sidecar = pa.build_full_sidecar_dict(
        snapshot_dict=snapshot_dict, agg=agg,
        master_seed=42, K_approved=4,
        run_id="test-runid",
    )
    assert sidecar is None


def test_build_full_sidecar_matches_envelope_run_id() -> None:
    """The analyzer's admission rule requires
    `fullSidecar.runId == envelope.finalResultEnvelope.runEnvelope.runId`.
    Both surfaces source runId from `snapshot.metadata.snapshotId` per
    §13 byte-identity — verify they agree on the same fixture."""
    snapshot_dict = _load_snapshot_dict()
    master_seed = 42
    K = 1
    agg = _build_synthetic_agg(
        master_seed=master_seed, K=K, succeed_indices=[0],
    )

    wrapper = pa.build_post_aggregation_envelope(
        snapshot_dict=snapshot_dict, agg=agg,
        master_seed=master_seed, K_approved=K,
        run_id="test-runid-irrelevant",
    )
    sidecar = pa.build_full_sidecar_dict(
        snapshot_dict=snapshot_dict, agg=agg,
        master_seed=master_seed, K_approved=K,
        run_id="test-runid-irrelevant",
    )

    assert wrapper is not None
    assert sidecar is not None
    envelope_run_id = wrapper["finalResultEnvelope"]["runEnvelope"]["runId"]
    assert sidecar["runId"] == envelope_run_id, (
        "sidecar.runId MUST match envelope.runEnvelope.runId — analyzer "
        "admission depends on it"
    )


# --- Standalone runner ---------------------------------------------------


if __name__ == "__main__":
    failures = 0
    funcs = [(n, f) for n, f in globals().items()
             if n.startswith("test_") and callable(f)]
    for name, fn in funcs:
        try:
            fn()
            print("ok   " + name)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print("FAIL " + name + ": " + repr(exc))
    if failures:
        sys.exit(1)
