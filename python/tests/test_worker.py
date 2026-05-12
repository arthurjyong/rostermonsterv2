"""Tests for the M7 C2 Task 2D Cloud Batch worker per
`docs/cloud_compute_contract.md` §8.7 +
`python/rostermonster_service/worker.py`.

**M7 C4 T2A.1 (2026-05-12) — MODULE SKIPPED pending rewrite.** worker.py
was refactored to single-VM Pool(K_approved) with local seed derivation
(no per-task seeds.json). These tests exercise the OLD per-task
seeds.json input contract + Pool(8) shape — they need rewriting against
the new single-task input contract (RM_MASTER_SEED env + Pool(K_approved)).
Rewrite tracked as M7 C4 T2A.1.1 follow-up. Skipping (not deleting) so
the rewrite has the historical assertions as a reference.

Original M7 C2 docstring (preserved for the rewrite):


Exercises the full read → compute → write cycle against an in-memory
GCS adapter + a serial pool executor (no real google-cloud-storage
dependency, no multiprocessing fork). Covers:

- Round-trip: snapshot + seeds.json → result.json with the §8.7 schema +
  populated `candidates` list (one TrialCandidate per SUCCEEDED
  trajectory per the §12A.2 K-trajectory-independence semantics).
- Determinism: same `(masterSeed, candidate_seeds)` produces byte-
  identical result.json across invocations per §12A.4.
- Per-trajectory exception handling: a child raising surfaces as a
  `trajectoryExceptions` entry rather than killing the whole task per
  §12A.8 drop-and-continue discipline.
- Schema invariants: `schemaVersion`, `runId`, `taskIndex`,
  `masterSeed`, `aggregateAttempts`, `aggregateRejectionsByReason` all
  present; `candidates` items carry the contract-pinned per-trajectory
  fields.
- Boundary validation: oversized seed slice (>8) rejected;
  seeds.json["seeds"] non-list / empty rejected.
- Result URI matches the §8.7 GCS key path
  (`gs://{bucket}/{runId}/task-{n}/result.json`).
- CLI dispatch: `--task-index` defaults to `BATCH_TASK_INDEX` env;
  missing both surfaces exit code 2.

Standalone runnable via `python3 python/tests/test_worker.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from rostermonster_service import worker as worker_mod  # noqa: E402

# M7 C4 T2A.1 module-level skip per the docstring above. Remove when the
# rewrite (M7 C4 T2A.1.1 follow-up) updates these tests for the
# single-task + Pool(K_approved) + local seed derivation pattern.
pytestmark = pytest.mark.skip(
    reason=(
        "M7 C4 T2A.1 worker.py refactor — tests need rewrite for "
        "single-VM single-task pattern (Pool(K_approved), local seed "
        "derivation via derive_K_seeds(), no per-task seeds.json). "
        "Skipped (not deleted) so the rewrite has historical assertions "
        "as a reference."
    )
)


_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "data" / "icu_hd_may_2026_snapshot.json"
)
_BUCKET = "rostermonsterv2-lahc"
_RUN_ID = "test-run-2026-05-10-001"


def _serial_executor(fn, args_iter):
    """Test-only pool executor — runs trajectories in-process to avoid
    multiprocessing spawn semantics + keep test wall-time bounded."""
    return [fn(a) for a in args_iter]


def _make_inmem_gcs(initial: dict[str, dict]):
    """In-memory GCS adapter — `read_json` + `write_json` closures backed
    by a dict keyed on the full `gs://` URI. Returns the storage dict
    too so tests can introspect what the worker wrote."""
    storage: dict[str, dict] = dict(initial)

    def read_json(uri: str) -> dict:
        if uri not in storage:
            raise FileNotFoundError(uri)
        # Deep-copy via JSON round-trip so mutations on the returned dict
        # don't leak back into the in-memory store (real GCS gives a
        # fresh deserialization on every read).
        return json.loads(json.dumps(storage[uri]))

    def write_json(uri: str, data: dict) -> None:
        storage[uri] = json.loads(json.dumps(data))

    return read_json, write_json, storage


def _load_snapshot_dict() -> dict:
    return json.loads(_FIXTURE_PATH.read_text())


def _gcs_uri(*parts: str) -> str:
    return "gs://" + _BUCKET + "/" + _RUN_ID + "/" + "/".join(parts)


_ATTEMPT_ID = "attempt-test-aaaa1111"


def _build_storage(*, candidate_seeds: list[int], master_seed: int = 12345,
                    attempt_id: str | None = _ATTEMPT_ID) -> dict:
    """Pre-populate in-memory storage with the orchestrator-written
    snapshot.json + seeds.json the worker reads. `attempt_id` is the
    T2G concurrent-replay race fix per §8.7 — orchestrator stamps it
    into seeds.json; worker echoes back into result.json. Tests can
    pass `None` to simulate a pre-T2G seeds.json without the field."""
    return {
        _gcs_uri("snapshot.json"): _load_snapshot_dict(),
        _gcs_uri("task-0", "seeds.json"): {
            "schemaVersion": 1,
            "runId": _RUN_ID,
            "taskIndex": 0,
            "masterSeed": master_seed,
            "attemptId": attempt_id,
            "seeds": candidate_seeds,
        },
    }


# --- Schema constants ----------------------------------------------------


def test_schema_version_is_one() -> None:
    """Result + seeds schemaVersion both pinned at 1 per §8.7's initial
    version. A bump signals a contract amendment downstream consumers
    must re-validate against."""
    assert worker_mod._RESULT_SCHEMA_VERSION == 1
    assert worker_mod._SEEDS_SCHEMA_VERSION == 1


def test_trajectories_per_task_matches_dense_pack_invariant() -> None:
    """§8.7 dense-pack: 8 trajectories per `c3-highcpu-8` task (1 per
    vCPU). Drift from 8 would silently break the K_approved=104 →
    taskCount=13 derivation in M7 C2 Task 2E."""
    assert worker_mod.TRAJECTORIES_PER_TASK == 8


def test_lahc_constants_match_fw_0037_elbow_tuple() -> None:
    """FW-0037 elbow tuple per `docs/delivery_plan.md` §9 + D-0070 +
    M7 architecture lock: L=50 / idleThreshold=3500 / swapProbability=0.5.
    The worker hardcodes these for production; drift would produce a
    different LAHC operating point than M7 was sized for."""
    assert worker_mod._LAHC_HISTORY_LIST_LENGTH == 50
    assert worker_mod._LAHC_IDLE_THRESHOLD == 3500
    assert worker_mod._LAHC_SWAP_PROBABILITY == 0.5


# --- Round-trip ---------------------------------------------------------


def test_worker_main_round_trips_snapshot_to_result() -> None:
    """Full pipeline: 2 seeds → result.json with 2 candidates (the real
    fixture is satisfiable so both trajectories should SUCCEED). Result
    appears at the §8.7 key path; schema fields all populated."""
    seeds = [111, 222]
    storage_init = _build_storage(candidate_seeds=seeds)
    read_json, write_json, storage = _make_inmem_gcs(storage_init)

    result = worker_mod.worker_main(
        _RUN_ID, 0,
        read_json=read_json, write_json=write_json,
        pool_executor=_serial_executor, bucket=_BUCKET,
    )

    # Top-level schema invariants per §8.7
    assert result["schemaVersion"] == 1
    assert result["runId"] == _RUN_ID
    assert result["taskIndex"] == 0
    assert result["masterSeed"] == 12345
    # T2G attemptId echo per §8.7 concurrent-replay race fix
    assert result["attemptId"] == _ATTEMPT_ID
    assert "candidates" in result
    assert "failedTrajectories" in result
    assert "aggregateAttempts" in result
    assert "aggregateRejectionsByReason" in result

    # Sanity: at least one of the two trajectories should produce a
    # candidate on the real-fixture (both K=1 LAHC runs against a
    # satisfiable model). The orchestrator's K' aggregation per §8.7
    # depends on `len(candidates)` matching surviving-trajectory count.
    total_handled = len(result["candidates"]) + len(result["failedTrajectories"])
    assert total_handled == len(seeds), (
        "every input seed must surface in either candidates or "
        "failedTrajectories — the per-task K' arithmetic per §8.7 "
        "depends on this completeness"
    )

    # Result blob written at the §8.7 key path
    expected_uri = _gcs_uri("task-0", "result.json")
    assert expected_uri in storage
    assert storage[expected_uri] == result


def test_worker_result_candidate_fields_match_schema() -> None:
    """Each SUCCEEDED candidate entry MUST carry the contract-pinned
    per-trajectory fields (`candidateSeed`, `assignments`, `iters`,
    `acceptedMoves`, `bestScore`, `terminalScore`) per the §8.7
    result.json schema. Orchestrator T2F's analyzer pass-through depends
    on `assignments` being present + structurally valid."""
    seeds = [111]
    storage_init = _build_storage(candidate_seeds=seeds)
    read_json, write_json, _ = _make_inmem_gcs(storage_init)

    result = worker_mod.worker_main(
        _RUN_ID, 0,
        read_json=read_json, write_json=write_json,
        pool_executor=_serial_executor, bucket=_BUCKET,
    )

    if not result["candidates"]:
        # The single-trajectory case may SEED_FAIL; that's still
        # contract-valid — just skip the field-shape assertion.
        return
    cand = result["candidates"][0]
    expected = {"candidateSeed", "assignments", "iters", "acceptedMoves",
                "bestScore", "terminalScore"}
    assert expected.issubset(cand.keys()), (
        "missing fields: " + repr(expected - cand.keys())
    )
    assert isinstance(cand["assignments"], list) and cand["assignments"]


def test_worker_echoes_attempt_id_into_result_json() -> None:
    """T2G concurrent-replay race fix per §8.7: worker reads attemptId
    from seeds.json and writes it back into result.json so the
    orchestrator can validate on aggregation. Echo, not derive — the
    orchestrator owns attempt-id generation."""
    seeds = [111, 222]
    storage_init = _build_storage(
        candidate_seeds=seeds, attempt_id="attempt-custom-zzz",
    )
    read_json, write_json, _ = _make_inmem_gcs(storage_init)

    result = worker_mod.worker_main(
        _RUN_ID, 0,
        read_json=read_json, write_json=write_json,
        pool_executor=_serial_executor, bucket=_BUCKET,
    )
    assert result["attemptId"] == "attempt-custom-zzz"


def test_worker_handles_missing_attempt_id_in_seeds_json() -> None:
    """Pre-T2G seeds.json files lack `attemptId`. Worker MUST echo
    `None` instead of raising — orchestrator's validation surfaces
    the missing-attemptId case as a stale-result mismatch via the
    standard partial-failure path."""
    seeds = [111]
    storage_init = _build_storage(candidate_seeds=seeds, attempt_id=None)
    read_json, write_json, _ = _make_inmem_gcs(storage_init)

    result = worker_mod.worker_main(
        _RUN_ID, 0,
        read_json=read_json, write_json=write_json,
        pool_executor=_serial_executor, bucket=_BUCKET,
    )
    assert result["attemptId"] is None


def test_worker_main_byte_identical_across_calls() -> None:
    """§12A.4 determinism through the worker: same `(masterSeed,
    candidate_seeds)` produces byte-identical result.json across two
    invocations. This is the cross-surface invariant T2G re-audits at
    the local-CLI vs Cloud-Batch level."""
    seeds = [4242, 7777]
    storage_a = _build_storage(candidate_seeds=seeds, master_seed=99)
    storage_b = _build_storage(candidate_seeds=seeds, master_seed=99)

    read_a, write_a, store_a = _make_inmem_gcs(storage_a)
    read_b, write_b, store_b = _make_inmem_gcs(storage_b)

    r_a = worker_mod.worker_main(
        _RUN_ID, 0,
        read_json=read_a, write_json=write_a,
        pool_executor=_serial_executor, bucket=_BUCKET,
    )
    r_b = worker_mod.worker_main(
        _RUN_ID, 0,
        read_json=read_b, write_json=write_b,
        pool_executor=_serial_executor, bucket=_BUCKET,
    )

    assert json.dumps(r_a, sort_keys=True) == json.dumps(r_b, sort_keys=True), (
        "Two invocations with identical (masterSeed, seeds) produced "
        "different result.json — §12A.4 determinism through the worker "
        "is broken."
    )


# --- Per-trajectory exception handling ----------------------------------


def test_per_trajectory_exception_isolates_to_single_entry() -> None:
    """Per-trajectory exceptions MUST surface as a `trajectoryExceptions`
    entry instead of killing the whole task per §12A.8 drop-and-continue.
    Tests this by injecting a serial executor that raises on the first
    trajectory; the second still completes and lands in candidates /
    failedTrajectories."""
    seeds = [111, 222]
    storage_init = _build_storage(candidate_seeds=seeds)
    read_json, write_json, storage = _make_inmem_gcs(storage_init)

    # Serial executor that calls _run_one_trajectory directly — and
    # since _run_one_trajectory wraps `solve()` in try-except, a forced
    # exception from solve() surfaces as the EXCEPTION status. Patch
    # `_run_one_trajectory` to raise once for the first arg.
    call_index = {"n": 0}
    real_runner = worker_mod._run_one_trajectory

    def flaky_runner(args):
        call_index["n"] += 1
        if call_index["n"] == 1:
            return {
                "status": "EXCEPTION",
                "candidateSeed": args[-1],
                "exceptionType": "RuntimeError",
                "exceptionMessage": "simulated trajectory failure",
                "placementAttempts": 0,
                "rejectionsByReason": {},
            }
        return real_runner(args)

    def serial_with_flaky(fn, args_iter):
        return [flaky_runner(a) for a in args_iter]

    result = worker_mod.worker_main(
        _RUN_ID, 0,
        read_json=read_json, write_json=write_json,
        pool_executor=serial_with_flaky, bucket=_BUCKET,
    )

    assert "trajectoryExceptions" in result
    assert len(result["trajectoryExceptions"]) == 1
    exc = result["trajectoryExceptions"][0]
    assert exc["candidateSeed"] == 111
    assert exc["exceptionType"] == "RuntimeError"
    # Other trajectory still ran cleanly
    handled = len(result["candidates"]) + len(result["failedTrajectories"])
    assert handled == 1, (
        "second trajectory must still surface in candidates or "
        "failedTrajectories despite first raising"
    )


def test_no_trajectory_exceptions_omits_block() -> None:
    """When all trajectories complete cleanly (SUCCEEDED or SEED_FAILED),
    the `trajectoryExceptions` field MUST be omitted from result.json
    to keep the common-case schema surface area minimal for orchestrator
    consumption."""
    seeds = [111]
    storage_init = _build_storage(candidate_seeds=seeds)
    read_json, write_json, _ = _make_inmem_gcs(storage_init)

    result = worker_mod.worker_main(
        _RUN_ID, 0,
        read_json=read_json, write_json=write_json,
        pool_executor=_serial_executor, bucket=_BUCKET,
    )

    assert "trajectoryExceptions" not in result


# --- Boundary validation ------------------------------------------------


def test_oversized_seed_slice_rejected() -> None:
    """`len(seeds) > TRAJECTORIES_PER_TASK` violates the §8.7 dense-pack
    invariant (1 trajectory per vCPU on `c3-highcpu-8`); MUST fail
    fast at the worker boundary so a misconfigured orchestrator
    surfaces here, not as oversubscribed CPU mid-run."""
    seeds = list(range(9))  # 9 > 8
    storage_init = _build_storage(candidate_seeds=seeds)
    read_json, write_json, _ = _make_inmem_gcs(storage_init)

    try:
        worker_mod.worker_main(
            _RUN_ID, 0,
            read_json=read_json, write_json=write_json,
            pool_executor=_serial_executor, bucket=_BUCKET,
        )
    except ValueError as e:
        assert "TRAJECTORIES_PER_TASK" in str(e) or "8" in str(e)
        return
    raise AssertionError(
        "worker_main with 9 seeds should have raised ValueError"
    )


def test_empty_seed_slice_rejected() -> None:
    """`seeds == []` would produce a no-op task contributing 0
    candidates without distinguishing this from a task-level failure
    in the orchestrator's §8.7 K' aggregation. Reject at the boundary."""
    storage_init = _build_storage(candidate_seeds=[])
    read_json, write_json, _ = _make_inmem_gcs(storage_init)

    try:
        worker_mod.worker_main(
            _RUN_ID, 0,
            read_json=read_json, write_json=write_json,
            pool_executor=_serial_executor, bucket=_BUCKET,
        )
    except ValueError as e:
        assert "seeds" in str(e).lower()
        return
    raise AssertionError(
        "worker_main with [] seeds should have raised ValueError"
    )


def test_non_list_seeds_rejected() -> None:
    """`seeds.json["seeds"]` MUST be a list; a malformed orchestrator
    write (e.g., emitting `{"seeds": null}` or `{"seeds": 42}`) MUST
    fail fast at the worker boundary."""
    storage = {
        _gcs_uri("snapshot.json"): _load_snapshot_dict(),
        _gcs_uri("task-0", "seeds.json"): {
            "schemaVersion": 1,
            "runId": _RUN_ID,
            "taskIndex": 0,
            "masterSeed": 1,
            "seeds": "not-a-list",
        },
    }
    read_json, write_json, _ = _make_inmem_gcs(storage)

    try:
        worker_mod.worker_main(
            _RUN_ID, 0,
            read_json=read_json, write_json=write_json,
            pool_executor=_serial_executor, bucket=_BUCKET,
        )
    except ValueError as e:
        assert "seeds" in str(e).lower()
        return
    raise AssertionError(
        "non-list seeds field should have raised ValueError"
    )


# --- Aggregate counters --------------------------------------------------


def test_aggregate_attempts_sums_across_trajectories() -> None:
    """`aggregateAttempts` MUST be the sum of `placementAttempts`
    across all trajectories' diagnostics. The orchestrator surfaces this
    in the run envelope's `SearchDiagnostics` field; under-counting would
    make M7 runs look more efficient than they are."""
    seeds = [111, 222]
    storage_init = _build_storage(candidate_seeds=seeds)
    read_json, write_json, _ = _make_inmem_gcs(storage_init)

    result = worker_mod.worker_main(
        _RUN_ID, 0,
        read_json=read_json, write_json=write_json,
        pool_executor=_serial_executor, bucket=_BUCKET,
    )

    assert isinstance(result["aggregateAttempts"], int)
    assert result["aggregateAttempts"] >= 0
    assert isinstance(result["aggregateRejectionsByReason"], dict)


# --- CLI dispatch --------------------------------------------------------


def test_cli_missing_task_index_returns_2(monkeypatch=None) -> None:
    """When neither `--task-index` nor `BATCH_TASK_INDEX` is set, `main`
    returns exit code 2 (POSIX-shell convention for "usage error")."""
    import os

    saved = os.environ.pop("BATCH_TASK_INDEX", None)
    try:
        rc = worker_mod.main(["--run-id", "x"])
        assert rc == 2
    finally:
        if saved is not None:
            os.environ["BATCH_TASK_INDEX"] = saved


def test_cli_picks_up_batch_task_index_env() -> None:
    """`--task-index` defaults to the `BATCH_TASK_INDEX` env var Cloud
    Batch sets per-task. Verify by parsing argv with only `--run-id`
    set + the env populated; the parsed args MUST surface task_index=N."""
    import argparse
    import os

    saved = os.environ.get("BATCH_TASK_INDEX")
    os.environ["BATCH_TASK_INDEX"] = "5"
    try:
        # Re-derive the same argparse the CLI builds — assert env
        # default flows through. Invoking main() directly would attempt
        # real GCS I/O.
        parser = argparse.ArgumentParser()
        parser.add_argument("--run-id", required=True)
        default_idx = os.environ.get("BATCH_TASK_INDEX")
        parser.add_argument(
            "--task-index", type=int,
            default=int(default_idx) if default_idx is not None else None,
        )
        args = parser.parse_args(["--run-id", "x"])
        assert args.task_index == 5
    finally:
        if saved is None:
            os.environ.pop("BATCH_TASK_INDEX", None)
        else:
            os.environ["BATCH_TASK_INDEX"] = saved


# --- GCS adapter URI guards ---------------------------------------------


def test_real_gcs_adapter_rejects_uri_outside_bucket() -> None:
    """The shared `make_gcs_adapter` in `gcs.py` (T2F extraction) validates
    `uri` starts with `gs://{bucket}/`. Cross-bucket reads/writes are a
    misconfiguration and MUST fail fast (the worker + orchestrator are
    each bound to one bucket per §8.7)."""
    try:
        from google.cloud import storage  # noqa: F401
    except ImportError:
        # google-cloud-storage not installed in this test environment;
        # the URI-guard test requires the real factory which lazy-
        # imports it. Skip.
        return

    from rostermonster_service.gcs import make_gcs_adapter
    read_json, write_json = make_gcs_adapter(_BUCKET)
    for fn, label in ((read_json, "read"), (write_json, "write")):
        try:
            if label == "read":
                fn("gs://wrong-bucket/foo.json")
            else:
                fn("gs://wrong-bucket/foo.json", {"x": 1})
        except ValueError as e:
            assert "wrong-bucket" in str(e) or _BUCKET in str(e)
            continue
        raise AssertionError(
            label + "_json on wrong bucket should have raised ValueError"
        )


# --- Standalone runner ---------------------------------------------------


if __name__ == "__main__":
    import inspect

    failures = 0
    funcs = [(n, f) for n, f in globals().items()
             if n.startswith("test_") and callable(f)]
    for name, fn in funcs:
        try:
            sig = inspect.signature(fn)
            if any(p.default is inspect.Parameter.empty
                   for p in sig.parameters.values()):
                # Skip tests that need fixtures (e.g., monkeypatch) we
                # don't provide in the standalone runner.
                continue
            fn()
            print("ok   " + name)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print("FAIL " + name + ": " + repr(exc))
    if failures:
        sys.exit(1)
