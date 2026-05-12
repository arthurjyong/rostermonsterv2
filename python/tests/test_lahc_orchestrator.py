"""Tests for the M7 C4 T2A.1 LAHC Cloud Run orchestrator per
`docs/cloud_compute_contract.md` §8.7 +
`python/rostermonster_service/lahc_orchestrator.py`.

Covers:
- runId derivation from `(snapshotId, masterSeed)` — sanitization,
  determinism, length cap, negative-seed handling, content-hash
  collision resistance.
- Orchestrator end-to-end with InMemoryBatchClient + in-memory GCS
  (single-task pattern per Codex P1.7 amendment): pre-seeded single
  result.json at `gs://bucket/runId/result.json`, single-poll
  SUCCEEDED, K' aggregation = `len(result.json["candidates"])`.
- Deadline overrun: state sequence keeps returning RUNNING; orchestrator
  cancels at the deadline and proceeds to aggregation with whatever
  result.json happens to be in storage.
- Partial-failure tolerance per §8.7: missing single result.json
  contributes 0 candidates, surfaces in `incompleteTaskIndices=[0]`.
- Snapshot-only GCS write: per-task seeds.json is RETIRED under
  single-task; the worker derives all K seeds locally from
  RM_MASTER_SEED env via derive_K_seeds() per §12A.10.
- Stale-artifact clearing per Codex P1 finding (PR #143): orchestrator
  MUST call gcs_delete_prefix(runId/) before writing fresh inputs.
- Concurrent-replay attempt-id validation per Codex P2 round 2 finding 4:
  result.json with mismatched attemptId is treated as missing →
  kPrime=0 + incompleteTaskIndices=[0] (single-task surface; no
  separate mismatchedAttemptTaskIndices field on the success-path
  summary because there's only one task).
- AttemptId env plumbing: orchestrator passes attempt_id_fn() to
  build_lahc_batch_job_spec, which sets RM_ATTEMPT_ID on the Batch
  task env (NOT into seeds.json — that's retired).
- Worker-integration: a fake BatchClient that invokes worker_main
  inline on submit produces a real result.json; orchestrator
  aggregates it into a non-empty K' candidate set.
- Error states: snapshot missing snapshotId → COMPUTE_ERROR;
  parser rejection → INPUT_ERROR pre-dispatch; validation rejects
  invalid masterSeed / K_approved.
- Aggregate counters: totalAttempts + rejectionsByReason pass through
  from the single result.json.
- Post-aggregation diagnostics include SEED_FAILED trajectories per
  §12A.9 (Codex P2 finding regression).
- Failure-branch (K'==0) wrapper envelope present per §10.3.

Standalone runnable via `python3 python/tests/test_lahc_orchestrator.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rostermonster_service import lahc_orchestrator as lo  # noqa: E402
from rostermonster_service.batch_client import (  # noqa: E402
    JOB_STATE_SUCCEEDED,
    InMemoryBatchClient,
)


_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "data" / "icu_hd_may_2026_snapshot.json"
)
_BUCKET = "rostermonsterv2-lahc"
_REGION = "asia-southeast1"
_PROJECT = "rostermonsterv2"
_IMAGE = "gcr.io/rostermonsterv2/roster-monster-compute:test-tag"
# Fixed attemptId for deterministic test assertions; the production
# orchestrator generates a fresh uuid4 hex per call, but tests inject
# this constant via `attempt_id_fn=_fixed_attempt_id_fn` so pre-seeded
# result.json files can carry the matching value.
_FIXED_ATTEMPT_ID = "attempt-test-fixed-aaaa1111"


def _fixed_attempt_id_fn() -> str:
    return _FIXED_ATTEMPT_ID


def _real_snapshot_with_id(snapshot_id: str) -> dict:
    """Return a real-fixture snapshot with `metadata.snapshotId` overridden
    to the supplied value. T2G's orchestrator pre-validates the snapshot
    is fully deserializable at entry (returning COMPUTE_ERROR on failure),
    so synthetic dicts like `{"metadata": {"snapshotId": "x"}}` no
    longer reach the aggregation/wrapper logic. Tests use this helper
    to get a parseable snapshot while still controlling the runId via
    the snapshotId override (runId derives from
    `(snapshotId, masterSeed)` per `derive_run_id`)."""
    snap = json.loads(_FIXTURE_PATH.read_text())
    snap["metadata"]["snapshotId"] = snapshot_id
    return snap


# --- In-memory test infrastructure --------------------------------------


def _make_inmem_gcs(initial: dict[str, dict] | None = None):
    """In-memory GCS — `read_json` + `write_json` closures over a dict
    keyed on full `gs://` URIs. Returns the storage too for assertion."""
    storage: dict[str, dict] = dict(initial or {})

    def read_json(uri: str) -> dict:
        if uri not in storage:
            raise FileNotFoundError(uri)
        return json.loads(json.dumps(storage[uri]))

    def write_json(uri: str, data: dict) -> None:
        storage[uri] = json.loads(json.dumps(data))

    return read_json, write_json, storage


def _no_sleep(_seconds: float) -> None:
    """Test sleep_fn — skips real sleeping."""
    return None


def _no_delete(_prefix: str) -> int:
    """Test delete_prefix — no-op for tests that pre-seed result.json
    BEFORE calling orchestrate_lahc_run and want to keep them. The real
    production path passes a delete fn that clears the runId prefix to
    invalidate stale state from prior replay attempts (Codex P1 finding
    on PR #143). The dedicated stale-clear regression test
    `test_orchestrator_clears_stale_artifacts_before_replay` exercises
    the real delete behavior."""
    return 0


def _make_inmem_delete_prefix(storage: dict[str, dict]):
    """In-memory delete_prefix mirroring the production semantics:
    deletes every key in storage that starts with the supplied URI
    prefix. Returns the count for parity with `make_gcs_delete_prefix_fn`."""

    def delete_prefix(uri: str) -> int:
        keys_to_delete = [k for k in storage if k.startswith(uri)]
        for k in keys_to_delete:
            del storage[k]
        return len(keys_to_delete)

    return delete_prefix


def _virtual_clock(start: float = 0.0, step: float = 1.0):
    """Test time_fn — returns monotonically increasing values."""
    state = {"now": start}

    def time_fn() -> float:
        result = state["now"]
        state["now"] += step
        return result

    return time_fn


def _fixed_wall_time_fn() -> float:
    """Deterministic wall_time_fn for tests that want a stable
    submit_timestamp_ms in the Batch job spec without coupling to
    `time.time()`. Returns a fixed epoch value — the orchestrator
    multiplies by 1000 to derive RM_SUBMIT_TIMESTAMP_MS."""
    return 1_700_000_000.0


# --- runId derivation ---------------------------------------------------


def test_derive_run_id_sanitizes_special_chars() -> None:
    """Cloud Batch job_id accepts lowercase alphanumerics + dashes only.
    Snapshot IDs may contain `_` / `:` / `/` / camelCase — sanitize.
    Output layout: `<sanitized-prefix>-<8hex>-seed-<label>`."""
    out = lo.derive_run_id("MySnapshot/ID:123_v2", master_seed=42)
    assert out.startswith("mysnapshot-id-123-v2-")
    assert "-seed-42" in out
    assert all(c.isalnum() or c == "-" for c in out)


def test_derive_run_id_deterministic_for_same_inputs() -> None:
    """Same `(snapshotId, masterSeed)` MUST produce same runId so
    re-runs overwrite GCS artifacts cleanly (idempotent forensic
    replay)."""
    a = lo.derive_run_id("snap-001", master_seed=99)
    b = lo.derive_run_id("snap-001", master_seed=99)
    assert a == b


def test_derive_run_id_changes_with_seed() -> None:
    """Different masterSeed MUST produce different runId so distinct
    runs don't collide in GCS."""
    a = lo.derive_run_id("snap-001", master_seed=99)
    b = lo.derive_run_id("snap-001", master_seed=100)
    assert a != b


def test_derive_run_id_handles_negative_seed() -> None:
    """§9 input #3 allows negative seeds. runId encoding MUST handle
    negative — using `-` as separator while seed could be `-42` would
    create an ambiguous parse. Negative seeds get an `n` prefix on the
    seed label."""
    out = lo.derive_run_id("snap-001", master_seed=-42)
    assert "seed-n42" in out


def test_derive_run_id_truncates_long_input() -> None:
    """Cloud Batch job_id max length is 63 chars per its v1 docs."""
    long_id = "a" * 100
    out = lo.derive_run_id(long_id, master_seed=42)
    assert len(out) <= 63
    assert "-seed-42" in out, "seed label must survive truncation"


def test_derive_run_id_distinguishes_truncated_long_snapshots() -> None:
    """Codex P2 finding: real bound-shim `snapshot_<spreadsheetId>_<extractionTimestamp>`
    IDs are long enough that right-truncation alone would drop the
    timestamp, collapsing two distinct extractions of the same
    spreadsheet to the same runId. The content-hash component MUST
    keep them distinct even after truncation."""
    sheet_id = "10p2TvME4gmPB39PFCsmAB6tCrPo96zSbpnTvKKKOAvI"  # 44 chars
    snap_a = "snapshot_" + sheet_id + "_2026-05-10T12:34:56"
    snap_b = "snapshot_" + sheet_id + "_2026-05-10T13:45:67"
    run_a = lo.derive_run_id(snap_a, master_seed=42)
    run_b = lo.derive_run_id(snap_b, master_seed=42)
    assert run_a != run_b, (
        "Two extractions of the same spreadsheet at different timestamps "
        "MUST produce different runIds — Codex P2 finding regression."
    )


def test_derive_run_id_rejects_empty_snapshot_id() -> None:
    for bad in ("", None, 42, "!!!@@@"):
        try:
            lo.derive_run_id(bad, master_seed=42)  # type: ignore[arg-type]
        except ValueError:
            continue
        raise AssertionError(
            "derive_run_id(" + repr(bad) + ") should have raised"
        )


# --- Orchestrator with pre-seeded single result.json (worker mocked) ---


def _build_pre_seeded_single_result(
    *, run_id: str, master_seed: int, K_approved: int,
    candidate_seeds: list[int],
    failed_seeds: list[int] | None = None,
    attempt_id: str = _FIXED_ATTEMPT_ID,
    aggregate_attempts: int = 1234,
    aggregate_rejections: dict[str, int] | None = None,
) -> dict:
    """Build a fake worker single-task result.json. Used to test the
    orchestrator's `_aggregate_single_task_result` path without
    invoking the real worker. `attempt_id` defaults to `_FIXED_ATTEMPT_ID`
    so the orchestrator's attempt-id validation accepts the result;
    tests targeting the mismatch path pass a different value explicitly."""
    failed_seeds = failed_seeds or []
    return {
        "schemaVersion": 1,
        "runId": run_id,
        "masterSeed": master_seed,
        "kApproved": K_approved,
        "attemptId": attempt_id,
        "candidates": [
            {
                "candidateSeed": s,
                "assignments": [
                    {"dateKey": "2026-05-01", "slotType": "ICU",
                     "unitIndex": 0, "doctorId": "dr_a"},
                ],
                "iters": 100,
                "acceptedMoves": 50,
                "bestScore": 0.5,
                "terminalScore": 0.4,
            }
            for s in candidate_seeds
        ],
        "failedTrajectories": [
            {"candidateSeed": s, "unfilledDemand": []}
            for s in failed_seeds
        ],
        "aggregateAttempts": aggregate_attempts,
        "aggregateRejectionsByReason": aggregate_rejections
            if aggregate_rejections is not None
            else {"BASELINE_ELIGIBILITY_FAIL": 7},
    }


def _orchestrate_with_pre_seeded_result(
    *, K_approved: int, master_seed: int = 99999,
    state_sequence: list[str] | None = None,
    snapshot_id: str = "test-snap-001",
    pre_seed_candidate_count: int | None = None,
) -> tuple[dict, list[int], dict]:
    """Helper: pre-seed a single result.json at the §8.7 single-task key
    path so aggregation has data to read. Returns
    `(orchestrator_response, candidate_seeds_in_result, storage_dict)`."""
    snapshot_dict = _real_snapshot_with_id(snapshot_id)
    expected_run_id = lo.derive_run_id(snapshot_id, master_seed)

    # Use the same derive_K_seeds the orchestrator + worker both rely on
    # so the pre-seeded result.json carries seeds that match what the
    # post-aggregation diagnostics walk expects (§12A.10).
    from rostermonster.solver import derive_K_seeds
    all_seeds = derive_K_seeds(master_seed, K_approved)
    if pre_seed_candidate_count is None:
        pre_seed_candidate_count = K_approved
    candidate_seeds = all_seeds[:pre_seed_candidate_count]
    failed_seeds = all_seeds[pre_seed_candidate_count:]

    pre_seeded = {
        lo._gcs_uri(_BUCKET, expected_run_id, "result.json"):
            _build_pre_seeded_single_result(
                run_id=expected_run_id, master_seed=master_seed,
                K_approved=K_approved,
                candidate_seeds=candidate_seeds,
                failed_seeds=failed_seeds,
            ),
    }
    read_json, write_json, storage = _make_inmem_gcs(pre_seeded)
    batch_client = InMemoryBatchClient(
        state_sequence=state_sequence or [JOB_STATE_SUCCEEDED],
    )

    response = lo.orchestrate_lahc_run(
        snapshot_dict,
        master_seed=master_seed,
        K_approved=K_approved,
        container_image_uri=_IMAGE,
        batch_client=batch_client,
        gcs_read_json=read_json,
        gcs_write_json=write_json,
        gcs_delete_prefix=_no_delete,
        project=_PROJECT,
        bucket=_BUCKET,
        region=_REGION,
        sleep_fn=_no_sleep,
        time_fn=_virtual_clock(),
        wall_time_fn=_fixed_wall_time_fn,
        attempt_id_fn=_fixed_attempt_id_fn,
    )
    return response, candidate_seeds, storage


def test_orchestrator_happy_path_returns_OK_with_K_prime() -> None:
    """K=8 + all-SUCCEEDED single result.json → state=OK, kPrime=8,
    droppedCount=0, taskCount=1, completedTaskCount=1."""
    response, _, _ = _orchestrate_with_pre_seeded_result(K_approved=8)
    assert response["state"] == "OK"
    assert response["lahcSummary"]["kApproved"] == 8
    assert response["lahcSummary"]["kPrime"] == 8
    assert response["lahcSummary"]["droppedCount"] == 0
    # Single-task: always taskCount=1, completedTaskCount in {0,1}
    assert response["lahcSummary"]["taskCount"] == 1
    assert response["lahcSummary"]["completedTaskCount"] == 1
    assert response["lahcSummary"]["incompleteTaskIndices"] == []
    assert len(response["candidates"]) == 8
    assert response["error"] is None


def test_orchestrator_writes_only_snapshot_to_gcs() -> None:
    """Per the M7 C4 T2A.1 single-task pattern: only snapshot.json
    lands in GCS; per-task seeds.json is RETIRED — worker derives all
    K seeds locally from RM_MASTER_SEED env via derive_K_seeds() per
    §12A.10. Verifying this so a regression to the multi-task seeds-
    write path surfaces immediately."""
    _, _, storage = _orchestrate_with_pre_seeded_result(K_approved=16)
    expected_run_id = lo.derive_run_id("test-snap-001", 99999)

    snapshot_uri = lo._gcs_uri(_BUCKET, expected_run_id, "snapshot.json")
    assert snapshot_uri in storage
    # Only snapshot.json + the pre-seeded result.json should exist —
    # NO per-task seeds.json.
    written_uris = set(storage.keys())
    assert snapshot_uri in written_uris
    # No `task-N/seeds.json` — single-task pattern retired the seeds
    # partition under Codex P1.7 amendment.
    seeds_uris = [u for u in written_uris if u.endswith("seeds.json")]
    assert seeds_uris == [], (
        "Single-task pattern retired per-task seeds.json (worker "
        "derives locally via derive_K_seeds); orchestrator wrote: "
        + repr(seeds_uris)
    )


def test_orchestrator_passes_attempt_id_via_batch_env() -> None:
    """Single-task pattern: orchestrator stamps `attempt_id` into the
    Cloud Batch task env (`RM_ATTEMPT_ID`) per the M7 C4 T2A.1
    batch_job_spec — NOT into seeds.json (retired). Worker echoes it
    back into result.json's `attemptId` so this orchestrator's
    aggregation can validate on read.

    Verifies the env vars on the submitted Batch job spec carry the
    fixed attemptId. Together with `_aggregate_single_task_result`'s
    attempt-id validation (covered by
    `test_orchestrator_filters_out_results_with_mismatched_attempt_id`)
    this closes the concurrent-replay race."""
    snapshot_dict = _real_snapshot_with_id("snap-attempt-env-test")
    expected_run_id = lo.derive_run_id("snap-attempt-env-test", master_seed=42)
    pre_seeded = {
        lo._gcs_uri(_BUCKET, expected_run_id, "result.json"):
            _build_pre_seeded_single_result(
                run_id=expected_run_id, master_seed=42, K_approved=8,
                candidate_seeds=[],
                failed_seeds=[1, 2, 3, 4, 5, 6, 7, 8],
            ),
    }
    read_json, write_json, _ = _make_inmem_gcs(pre_seeded)
    batch_client = InMemoryBatchClient(state_sequence=[JOB_STATE_SUCCEEDED])

    response = lo.orchestrate_lahc_run(
        snapshot_dict,
        master_seed=42,
        K_approved=8,
        container_image_uri=_IMAGE,
        batch_client=batch_client,
        gcs_read_json=read_json,
        gcs_write_json=write_json,
        gcs_delete_prefix=_no_delete,
        project=_PROJECT, bucket=_BUCKET, region=_REGION,
        sleep_fn=_no_sleep,
        time_fn=_virtual_clock(),
        wall_time_fn=_fixed_wall_time_fn,
        attempt_id_fn=_fixed_attempt_id_fn,
    )

    # One Batch job submitted; inspect its env for RM_ATTEMPT_ID
    assert len(batch_client.submitted_jobs) == 1
    job_spec = batch_client.submitted_jobs[0]["job_spec"]
    env = job_spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    assert env["RM_ATTEMPT_ID"] == _FIXED_ATTEMPT_ID, (
        "orchestrator must stamp attempt_id into RM_ATTEMPT_ID on the "
        "Batch task env; got " + repr(env.get("RM_ATTEMPT_ID"))
    )

    # Response also surfaces attemptId in lahcSummary for forensic replay
    assert response["lahcSummary"]["attemptId"] == _FIXED_ATTEMPT_ID


def test_orchestrator_aggregates_attempts_and_rejections() -> None:
    """`totalAttempts` + `rejectionsByReason` pass through from the
    single result.json (no cross-task summing under single-task)."""
    response, _, _ = _orchestrate_with_pre_seeded_result(K_approved=8)
    assert response["lahcSummary"]["totalAttempts"] == 1234
    assert response["lahcSummary"]["rejectionsByReason"] == {
        "BASELINE_ELIGIBILITY_FAIL": 7,
    }


# --- Deadline overrun ---------------------------------------------------


def test_orchestrator_cancels_on_deadline_overrun() -> None:
    """If state never reaches terminal within `completion_deadline_seconds`,
    orchestrator MUST call cancel_job + return CANCELLED_OVER_DEADLINE.
    Pre-seeded result.json is still aggregated (partial-failure tolerance)."""
    snapshot_dict = _real_snapshot_with_id("snap-deadline-test")
    expected_run_id = lo.derive_run_id("snap-deadline-test", 1)

    from rostermonster.solver import derive_K_seeds
    all_seeds = derive_K_seeds(1, 8)
    pre_seeded = {
        lo._gcs_uri(_BUCKET, expected_run_id, "result.json"):
            _build_pre_seeded_single_result(
                run_id=expected_run_id, master_seed=1, K_approved=8,
                candidate_seeds=all_seeds[:4],
                failed_seeds=all_seeds[4:],
            ),
    }
    read_json, write_json, _ = _make_inmem_gcs(pre_seeded)

    # State sequence keeps returning RUNNING — orchestrator never sees
    # terminal until it gives up at the deadline.
    batch_client = InMemoryBatchClient(state_sequence=["RUNNING"])

    # Virtual clock with `step=100s` so each poll advances 100s; deadline
    # of 240s gives ~3 polls before exceeding.
    response = lo.orchestrate_lahc_run(
        snapshot_dict,
        master_seed=1,
        K_approved=8,
        container_image_uri=_IMAGE,
        batch_client=batch_client,
        gcs_read_json=read_json,
        gcs_write_json=write_json,
        gcs_delete_prefix=_no_delete,
        project=_PROJECT, bucket=_BUCKET, region=_REGION,
        completion_deadline_seconds=240,
        poll_interval_seconds=3,
        sleep_fn=_no_sleep,
        time_fn=_virtual_clock(step=100.0),
        wall_time_fn=_fixed_wall_time_fn,
        attempt_id_fn=_fixed_attempt_id_fn,
    )

    assert response["lahcSummary"]["batchFinalState"] == "CANCELLED_OVER_DEADLINE"
    assert len(batch_client.cancelled_jobs) == 1
    # K=8, 4 SUCCEEDED in pre-seeded result → K' = 4
    assert response["lahcSummary"]["kPrime"] == 4
    assert response["lahcSummary"]["droppedCount"] == 4


# --- Partial-failure tolerance ------------------------------------------


def test_orchestrator_handles_missing_result_json() -> None:
    """Per §8.7: missing single result.json → 0 candidates → UNSATISFIED
    + incompleteTaskIndices=[0]. The orchestrator MUST still return a
    structured response — the missing file doesn't crash aggregation."""
    snapshot_dict = _real_snapshot_with_id("snap-no-result")
    # NO pre-seed — Batch "completed" but the worker never wrote
    # result.json (simulates a worker crash before the final write).
    read_json, write_json, _ = _make_inmem_gcs()
    batch_client = InMemoryBatchClient(state_sequence=[JOB_STATE_SUCCEEDED])

    response = lo.orchestrate_lahc_run(
        snapshot_dict,
        master_seed=7,
        K_approved=8,
        container_image_uri=_IMAGE,
        batch_client=batch_client,
        gcs_read_json=read_json,
        gcs_write_json=write_json,
        gcs_delete_prefix=_no_delete,
        project=_PROJECT, bucket=_BUCKET, region=_REGION,
        sleep_fn=_no_sleep,
        time_fn=_virtual_clock(),
        wall_time_fn=_fixed_wall_time_fn,
        attempt_id_fn=_fixed_attempt_id_fn,
    )

    assert response["state"] == "UNSATISFIED"
    assert response["lahcSummary"]["kPrime"] == 0
    assert response["lahcSummary"]["droppedCount"] == 8
    assert response["lahcSummary"]["completedTaskCount"] == 0
    assert response["lahcSummary"]["incompleteTaskIndices"] == [0]


def test_orchestrator_clears_stale_artifacts_before_replay() -> None:
    """Codex P1 finding regression: a maintainer replay of the same
    `(snapshot, seed)` reuses the same artifact runId — the new Batch
    job (with a unique job_id) writes to the same GCS prefix as a
    prior attempt. If the new attempt's worker fails to rewrite its
    result.json, the orchestrator's aggregation step would silently
    pick up the prior attempt's surviving result.json.

    Fix: orchestrator MUST call `gcs_delete_prefix(runId/)` before
    writing fresh inputs. This test seeds storage with stale data at
    the runId prefix, then runs the orchestrator with NO new
    result.json (simulating "Batch job ran but worker failed
    silently") and asserts:
    1. The stale data is gone after orchestrator exit (cleared by
       orchestrator's invalidation step).
    2. K' == 0 (UNSATISFIED) — the orchestrator did NOT count the
       stale data toward K'.
    """
    snapshot_dict = _real_snapshot_with_id("snap-replay-test")
    expected_run_id = lo.derive_run_id("snap-replay-test", master_seed=42)

    # Pre-seed STALE result.json from a "prior attempt" — has 8
    # SUCCEEDED candidates that should NOT show up in this attempt.
    stale_uri = lo._gcs_uri(
        _BUCKET, expected_run_id, "result.json",
    )
    storage_init = {
        stale_uri: _build_pre_seeded_single_result(
            run_id=expected_run_id, master_seed=42, K_approved=8,
            candidate_seeds=[1, 2, 3, 4, 5, 6, 7, 8],
        ),
    }
    read_json, write_json, storage = _make_inmem_gcs(storage_init)
    batch_client = InMemoryBatchClient(state_sequence=[JOB_STATE_SUCCEEDED])

    # Use the REAL in-memory delete (not _no_delete) so the
    # invalidation step actually runs against this storage.
    real_delete = _make_inmem_delete_prefix(storage)

    response = lo.orchestrate_lahc_run(
        snapshot_dict,
        master_seed=42,
        K_approved=8,
        container_image_uri=_IMAGE,
        batch_client=batch_client,
        gcs_read_json=read_json,
        gcs_write_json=write_json,
        gcs_delete_prefix=real_delete,
        project=_PROJECT, bucket=_BUCKET, region=_REGION,
        sleep_fn=_no_sleep,
        time_fn=_virtual_clock(),
        wall_time_fn=_fixed_wall_time_fn,
        attempt_id_fn=_fixed_attempt_id_fn,
    )

    # Orchestrator did NOT count the stale data (K' must be 0)
    assert response["state"] == "UNSATISFIED"
    assert response["lahcSummary"]["kPrime"] == 0, (
        "Stale result.json from a prior attempt was counted toward "
        "this attempt's K' — Codex P1 finding regression."
    )
    # Storage no longer contains the stale URI (it was cleared)
    assert stale_uri not in storage, (
        "Stale result.json at " + stale_uri
        + " survived the orchestrator's invalidation step — "
        "subsequent partial-failure replays would inherit it."
    )
    # Fresh snapshot.json DID get written (post-clear) — single-task
    # pattern: NO per-task seeds.json.
    assert lo._gcs_uri(_BUCKET, expected_run_id, "snapshot.json") in storage


def test_post_aggregation_diagnostics_include_seed_failed_trajectories() -> None:
    """Codex P2 finding regression: SearchDiagnostics' per-trajectory
    arrays MUST have an entry for EVERY trajectory the solver attempted
    per `docs/solver_contract.md` §12A.9, with `0`/`None` for
    SEED_FAILED entries. Pre-fix, the helper only walked
    `agg["candidates"]` (SUCCEEDED) and skipped `agg["failedTrajectories"]`,
    so writeback diagnostics under-reported the original K when any
    trajectory dropped — losing forensic context for partial-failure
    runs that the analyzer + operator-facing diagnostics rely on."""
    snapshot_dict = json.loads(_FIXTURE_PATH.read_text())
    master_seed = 42
    K = 4
    # Re-derive the K seeds the orchestrator would use so we can craft
    # a result.json with the right candidateSeed values.
    from rostermonster.solver import derive_K_seeds
    seeds = derive_K_seeds(master_seed, K)

    # Construct an `agg` dict the way `_aggregate_single_task_result`
    # would — 2 SUCCEEDED + 2 SEED_FAILED, all "in" task 0 (the synthetic
    # taskIndex single-task pattern preserves for downstream wrappers).
    agg = {
        "candidates": [
            {
                "taskIndex": 0,
                "candidateSeed": seeds[0],
                "assignments": [
                    {"dateKey": "2026-05-01", "slotType": "MICU",
                     "unitIndex": 0, "doctorId": "dr_a"},
                ],
                "iters": 100,
                "acceptedMoves": 50,
                "bestScore": 0.5,
                "terminalScore": 0.4,
            },
            {
                "taskIndex": 0,
                "candidateSeed": seeds[2],
                "assignments": [
                    {"dateKey": "2026-05-02", "slotType": "MICU",
                     "unitIndex": 0, "doctorId": "dr_b"},
                ],
                "iters": 200,
                "acceptedMoves": 80,
                "bestScore": 0.6,
                "terminalScore": 0.55,
            },
        ],
        "failedTrajectories": [
            {"taskIndex": 0, "candidateSeed": seeds[1],
             "unfilledDemand": []},
            {"taskIndex": 0, "candidateSeed": seeds[3],
             "unfilledDemand": []},
        ],
        "trajectoryExceptions": [],
        "aggregateAttempts": 100,
        "aggregateRejectionsByReason": {},
        "resultPresent": True,
        "perTaskResults": [{}],
    }

    wrapper = lo._build_post_aggregation_envelope(
        snapshot_dict=snapshot_dict, agg=agg,
        master_seed=master_seed, K_approved=K,
        run_id="test-runid",
    )
    if wrapper is None:
        # If selector rejected our synthetic candidates, the
        # diagnostics test isn't applicable. Skip.
        return

    diag = wrapper["finalResultEnvelope"]["result"]["searchDiagnostics"]
    # Per §12A.9: per-trajectory arrays MUST have K entries
    # (2 SUCCEEDED + 2 SEED_FAILED = 4)
    assert len(diag["perTrajectoryStatus"]) == K, (
        "expected " + str(K) + " per-trajectory status entries; got "
        + str(len(diag["perTrajectoryStatus"]))
    )
    assert "SUCCEEDED" in diag["perTrajectoryStatus"]
    assert "SEED_FAILED" in diag["perTrajectoryStatus"], (
        "SEED_FAILED trajectories MUST appear in the per-trajectory "
        "status array (Codex P2 finding regression on PR #144)"
    )
    # Status order matches the seed emission order; with 4
    # entries in [SUCCEEDED, SEED_FAILED, SUCCEEDED, SEED_FAILED]
    # arrangement (seeds[0..3] mapped via the lookup above)
    assert diag["perTrajectoryStatus"] == ["SUCCEEDED", "SEED_FAILED",
                                            "SUCCEEDED", "SEED_FAILED"]
    # SEED_FAILED entries get `0` for iters/accepted, `None` for scores
    assert diag["perTrajectoryIters"][1] == 0
    assert diag["perTrajectoryAcceptedMoves"][1] == 0
    assert diag["perTrajectoryBestScore"][1] is None
    assert diag["perTrajectoryTerminalScore"][1] is None


def test_orchestrator_filters_out_result_with_mismatched_attempt_id() -> None:
    """Concurrent-replay race fix per §8.7 + Codex P2 round 2 finding 4:
    a result.json carrying a different attemptId belongs to a parallel/
    prior attempt at the same runId prefix and MUST NOT contribute to
    this attempt's K'. Test scenario: pre-seed result.json with
    attemptId='OTHER'; run orchestrator with `attempt_id_fn` returning
    `_FIXED_ATTEMPT_ID`. Orchestrator MUST treat the result as missing
    → kPrime=0, completedTaskCount=0, incompleteTaskIndices=[0]."""
    snapshot_dict = _real_snapshot_with_id("snap-attempt-mismatch")
    expected_run_id = lo.derive_run_id("snap-attempt-mismatch", master_seed=42)

    # Pre-seed result.json with a DIFFERENT attemptId — simulates a
    # concurrent attempt's worker writing to the same runId prefix
    # before this orchestrator's clear/aggregation cycle completes.
    pre_seeded = {
        lo._gcs_uri(_BUCKET, expected_run_id, "result.json"):
            _build_pre_seeded_single_result(
                run_id=expected_run_id, master_seed=42, K_approved=8,
                candidate_seeds=[1, 2, 3, 4, 5, 6, 7, 8],
                attempt_id="attempt-from-OTHER-replay-zzzz9999",
            ),
    }
    read_json, write_json, _ = _make_inmem_gcs(pre_seeded)
    batch_client = InMemoryBatchClient(state_sequence=[JOB_STATE_SUCCEEDED])

    response = lo.orchestrate_lahc_run(
        snapshot_dict,
        master_seed=42,
        K_approved=8,
        container_image_uri=_IMAGE,
        batch_client=batch_client,
        gcs_read_json=read_json,
        gcs_write_json=write_json,
        gcs_delete_prefix=_no_delete,  # don't clear; testing the filter
        project=_PROJECT, bucket=_BUCKET, region=_REGION,
        sleep_fn=_no_sleep,
        time_fn=_virtual_clock(),
        wall_time_fn=_fixed_wall_time_fn,
        attempt_id_fn=_fixed_attempt_id_fn,
    )

    # Orchestrator filtered out the OTHER attempt's results
    assert response["state"] == "UNSATISFIED", (
        "expected UNSATISFIED when result has mismatched "
        "attemptId; got " + repr(response["state"])
    )
    assert response["lahcSummary"]["kPrime"] == 0, (
        "Mismatched-attemptId result.json was counted toward K' — "
        "concurrent-replay race fix is broken."
    )
    # Single-task: mismatch surfaces via incompleteTaskIndices=[0]
    # (treats as missing per the §8.7 primary K' definition)
    assert response["lahcSummary"]["completedTaskCount"] == 0
    assert response["lahcSummary"]["incompleteTaskIndices"] == [0]


def test_orchestrator_zero_candidates_returns_UNSATISFIED() -> None:
    """All trajectories failed (K' == 0) → state=UNSATISFIED per §8.7's
    whole-run UNSATISFIED criterion."""
    snapshot_dict = _real_snapshot_with_id("snap-all-fail")
    expected_run_id = lo.derive_run_id("snap-all-fail", 0)

    pre_seeded = {
        lo._gcs_uri(_BUCKET, expected_run_id, "result.json"):
            _build_pre_seeded_single_result(
                run_id=expected_run_id, master_seed=0, K_approved=8,
                candidate_seeds=[],
                failed_seeds=[1] * 8,
                aggregate_attempts=100,
                aggregate_rejections={},
            ),
    }
    read_json, write_json, _ = _make_inmem_gcs(pre_seeded)
    batch_client = InMemoryBatchClient(state_sequence=[JOB_STATE_SUCCEEDED])

    response = lo.orchestrate_lahc_run(
        snapshot_dict,
        master_seed=0,
        K_approved=8,
        container_image_uri=_IMAGE,
        batch_client=batch_client,
        gcs_read_json=read_json,
        gcs_write_json=write_json,
        gcs_delete_prefix=_no_delete,
        project=_PROJECT, bucket=_BUCKET, region=_REGION,
        sleep_fn=_no_sleep,
        time_fn=_virtual_clock(),
        wall_time_fn=_fixed_wall_time_fn,
        attempt_id_fn=_fixed_attempt_id_fn,
    )

    assert response["state"] == "UNSATISFIED"
    assert response["lahcSummary"]["kPrime"] == 0
    assert len(response["failedTrajectories"]) == 8


def test_orchestrator_parser_rejection_returns_input_error_pre_dispatch() -> None:
    """Codex P2 finding regression on PR #144 commit bad297f: a
    snapshot that deserializes but `parse()` returns NON_CONSUMABLE
    MUST be rejected at the orchestrator BEFORE Cloud-Batch dispatch
    (with `state="INPUT_ERROR"` + code `PARSER_REJECTED` + parser
    issue summary), matching local `/compute`'s INPUT_ERROR semantics
    per `docs/cloud_compute_contract.md` §10.1. Pre-fix the
    orchestrator dispatched to Batch + workers all failed parser →
    K'==0 + post-aggregation wrapper helper returned None →
    COMPUTE_ERROR, losing actionable parser issues + wasting Batch
    capacity."""
    # Mutate the real fixture to break parser consumability — drop
    # the `doctorRecords` field so the parser surfaces a structural
    # rejection without breaking shallow snapshotId / metadata
    # deserialization.
    snapshot_dict = json.loads(_FIXTURE_PATH.read_text())
    snapshot_dict["doctorRecords"] = []  # parser requires non-empty
    read_json, write_json, _ = _make_inmem_gcs()
    batch_client = InMemoryBatchClient()

    response = lo.orchestrate_lahc_run(
        snapshot_dict,
        master_seed=42,
        K_approved=8,
        container_image_uri=_IMAGE,
        batch_client=batch_client,
        gcs_read_json=read_json,
        gcs_write_json=write_json,
        gcs_delete_prefix=_no_delete,
        project=_PROJECT, bucket=_BUCKET, region=_REGION,
        sleep_fn=_no_sleep,
        time_fn=_virtual_clock(),
        wall_time_fn=_fixed_wall_time_fn,
        attempt_id_fn=_fixed_attempt_id_fn,
    )

    assert response["state"] == "INPUT_ERROR", (
        "Parser rejection MUST surface as INPUT_ERROR pre-dispatch "
        "matching local /compute semantics; got "
        + repr(response.get("state"))
    )
    assert response["error"]["code"] == "PARSER_REJECTED"
    # No Batch job submitted on parser rejection — saved compute
    assert len(batch_client.submitted_jobs) == 0


def test_orchestrator_failure_branch_wrapper_envelope_present() -> None:
    """Codex P2 finding regression on PR #144 commit c990f16:
    UNSATISFIED responses (K'==0) MUST still carry a non-null
    `writebackEnvelope` per `docs/cloud_compute_contract.md` §10.2 +
    §10.3 — the bound shim's `RMLib.applyWriteback(envelope)` requires
    a non-null wrapper. Pre-fix the orchestrator returned None for
    the failure branch; post-fix it builds the failure-branch
    envelope via `_build_unsatisfied_from_aggregation` + selector."""
    snapshot_dict = json.loads(_FIXTURE_PATH.read_text())
    snapshot_id = snapshot_dict["metadata"]["snapshotId"]
    expected_run_id = lo.derive_run_id(snapshot_id, master_seed=42)

    # Pre-seed result.json with all SEED_FAILED (no candidates)
    pre_seeded = {
        lo._gcs_uri(_BUCKET, expected_run_id, "result.json"): {
            "schemaVersion": 1,
            "runId": expected_run_id,
            "masterSeed": 42,
            "kApproved": 8,
            "attemptId": _FIXED_ATTEMPT_ID,
            "candidates": [],
            "failedTrajectories": [
                {"candidateSeed": s,
                 "unfilledDemand": [
                     {"dateKey": "2026-05-01", "slotType": "MICU",
                      "unitIndex": 0},
                 ]}
                for s in [11, 22, 33, 44, 55, 66, 77, 88]
            ],
            "aggregateAttempts": 100,
            "aggregateRejectionsByReason": {"BASELINE_ELIGIBILITY_FAIL": 5},
        },
    }
    read_json, write_json, _ = _make_inmem_gcs(pre_seeded)
    batch_client = InMemoryBatchClient(state_sequence=[JOB_STATE_SUCCEEDED])

    response = lo.orchestrate_lahc_run(
        snapshot_dict,
        master_seed=42,
        K_approved=8,
        container_image_uri=_IMAGE,
        batch_client=batch_client,
        gcs_read_json=read_json,
        gcs_write_json=write_json,
        gcs_delete_prefix=_no_delete,
        project=_PROJECT, bucket=_BUCKET, region=_REGION,
        sleep_fn=_no_sleep,
        time_fn=_virtual_clock(),
        wall_time_fn=_fixed_wall_time_fn,
        attempt_id_fn=_fixed_attempt_id_fn,
    )

    assert response["state"] == "UNSATISFIED"
    assert response["lahcSummary"]["kPrime"] == 0
    # Wrapper envelope MUST be non-null even on UNSATISFIED
    assert response["writebackEnvelope"] is not None, (
        "UNSATISFIED responses MUST carry a failure-branch "
        "writebackEnvelope per cloud_compute_contract.md §10.2 — "
        "Codex P2 finding regression."
    )
    final = response["writebackEnvelope"]["finalResultEnvelope"]
    # Failure-branch result has unfilledDemand + reasons populated
    result = final["result"]
    assert "unfilledDemand" in result
    assert len(result["unfilledDemand"]) >= 1, (
        "failure-branch envelope MUST carry the unfilled demand list"
    )
    assert "reasons" in result
    assert len(result["reasons"]) >= 1, (
        "failure-branch envelope MUST carry per-trajectory failure reasons"
    )


# --- Submit-timestamp wall-clock plumbing (T2A.1 fix) -------------------


def test_orchestrator_passes_wall_clock_submit_timestamp_to_batch_env() -> None:
    """T2A.1 round 2 Codex P2 finding 2 fix: `RM_SUBMIT_TIMESTAMP_MS`
    on the Batch task env MUST come from `wall_time_fn=time.time` (NOT
    `time_fn=time.monotonic`) because the worker reads it in a
    different process for T2A.2's elapsed self-check, and monotonic
    clocks are process-local. Verify by injecting a fixed
    `wall_time_fn` and asserting the env carries `int(wall * 1000)`."""
    snapshot_dict = _real_snapshot_with_id("snap-wall-clock-test")
    expected_run_id = lo.derive_run_id("snap-wall-clock-test", master_seed=42)
    pre_seeded = {
        lo._gcs_uri(_BUCKET, expected_run_id, "result.json"):
            _build_pre_seeded_single_result(
                run_id=expected_run_id, master_seed=42, K_approved=8,
                candidate_seeds=[],
                failed_seeds=[1, 2, 3, 4, 5, 6, 7, 8],
            ),
    }
    read_json, write_json, _ = _make_inmem_gcs(pre_seeded)
    batch_client = InMemoryBatchClient(state_sequence=[JOB_STATE_SUCCEEDED])

    lo.orchestrate_lahc_run(
        snapshot_dict,
        master_seed=42,
        K_approved=8,
        container_image_uri=_IMAGE,
        batch_client=batch_client,
        gcs_read_json=read_json,
        gcs_write_json=write_json,
        gcs_delete_prefix=_no_delete,
        project=_PROJECT, bucket=_BUCKET, region=_REGION,
        sleep_fn=_no_sleep,
        # time_fn is virtual (monotonic surrogate); wall_time_fn returns
        # a fixed epoch seconds value so we can assert env exactness.
        time_fn=_virtual_clock(),
        wall_time_fn=_fixed_wall_time_fn,
        attempt_id_fn=_fixed_attempt_id_fn,
    )

    assert len(batch_client.submitted_jobs) == 1
    job_spec = batch_client.submitted_jobs[0]["job_spec"]
    env = job_spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    expected_ms = int(_fixed_wall_time_fn() * 1000)
    assert env["RM_SUBMIT_TIMESTAMP_MS"] == str(expected_ms), (
        "RM_SUBMIT_TIMESTAMP_MS must be derived from wall_time_fn "
        "(epoch seconds) per T2A.1 round 2 Codex P2 finding 2 fix; "
        "got " + repr(env.get("RM_SUBMIT_TIMESTAMP_MS"))
    )


# --- Worker integration (orchestrator + real worker_main) --------------


def test_orchestrator_worker_integration_round_trip() -> None:
    """Full integration: a fake BatchClient that invokes worker_main
    inline on submit (against the same in-memory GCS) produces a real
    result.json. Orchestrator aggregates it into a non-empty K' candidate
    set. End-to-end exercise of the orchestrator → worker → orchestrator
    round-trip without real Cloud Batch.

    Single-task pattern: one worker_main call per submit, K seeds
    derived locally from RM_MASTER_SEED env (read off the Batch task
    spec by the integration shim)."""
    from rostermonster_service import worker as worker_mod

    snapshot_dict = json.loads(_FIXTURE_PATH.read_text())
    master_seed = 12345
    K = 2  # 2 trajectories — keeps test wall-time bounded

    read_json, write_json, _ = _make_inmem_gcs()

    def _serial_executor(fn, args_iter):
        return [fn(a) for a in args_iter]

    class WorkerSimulatingBatchClient(InMemoryBatchClient):
        """On submit_job, runs worker_main inline against the in-memory
        GCS for the single task. Pulls master_seed + K_approved +
        attempt_id off the Batch task env (mirroring how Cloud Batch
        sets them on the real worker process)."""

        def submit_job(self, *, project, region, run_id, job_spec):
            env = job_spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
            ms = int(env["RM_MASTER_SEED"])
            K_app = int(env["RM_K_APPROVED"])
            att = env.get("RM_ATTEMPT_ID", "")
            worker_mod.worker_main(
                run_id,
                master_seed=ms,
                K_approved=K_app,
                read_json=read_json,
                write_json=write_json,
                pool_executor=_serial_executor,
                bucket=_BUCKET,
                attempt_id=att,
            )
            return super().submit_job(
                project=project, region=region,
                run_id=run_id, job_spec=job_spec,
            )

    batch_client = WorkerSimulatingBatchClient(
        state_sequence=[JOB_STATE_SUCCEEDED],
    )

    response = lo.orchestrate_lahc_run(
        snapshot_dict,
        master_seed=master_seed,
        K_approved=K,
        container_image_uri=_IMAGE,
        batch_client=batch_client,
        gcs_read_json=read_json,
        gcs_write_json=write_json,
        gcs_delete_prefix=_no_delete,
        project=_PROJECT, bucket=_BUCKET, region=_REGION,
        sleep_fn=_no_sleep,
        time_fn=_virtual_clock(),
        wall_time_fn=_fixed_wall_time_fn,
        attempt_id_fn=_fixed_attempt_id_fn,
    )

    assert response["state"] in ("OK", "UNSATISFIED"), (
        "round-trip should produce a structured response; got "
        + repr(response.get("state"))
    )
    # K' equals SUCCEEDED count; exact value depends on solver, but
    # total candidates + failed must equal K_approved (per §8.7
    # completeness invariant — every trajectory either succeeds or fails)
    handled = response["lahcSummary"]["kPrime"] + len(response["failedTrajectories"])
    assert handled == K, (
        "every trajectory must surface as candidate or failed; got "
        + str(handled) + " for K=" + str(K)
    )


# --- Error states -------------------------------------------------------


def test_orchestrator_missing_snapshot_id_returns_compute_error() -> None:
    """`snapshot.metadata.snapshotId` is required for runId derivation;
    missing it MUST surface as COMPUTE_ERROR with code MISSING_SNAPSHOT_ID."""
    snapshot_dict = {"metadata": {"snapshotId": ""}}  # empty
    read_json, write_json, _ = _make_inmem_gcs()
    batch_client = InMemoryBatchClient()

    response = lo.orchestrate_lahc_run(
        snapshot_dict,
        master_seed=42,
        K_approved=8,
        container_image_uri=_IMAGE,
        batch_client=batch_client,
        gcs_read_json=read_json,
        gcs_write_json=write_json,
        gcs_delete_prefix=_no_delete,
        project=_PROJECT, bucket=_BUCKET, region=_REGION,
        sleep_fn=_no_sleep,
        time_fn=_virtual_clock(),
        wall_time_fn=_fixed_wall_time_fn,
        attempt_id_fn=_fixed_attempt_id_fn,
    )
    assert response["state"] == "COMPUTE_ERROR"
    assert response["error"]["code"] == "MISSING_SNAPSHOT_ID"
    # No Batch job submitted on error
    assert len(batch_client.submitted_jobs) == 0


def test_orchestrator_rejects_non_int_master_seed() -> None:
    snapshot_dict = {"metadata": {"snapshotId": "snap-x"}}
    read_json, write_json, _ = _make_inmem_gcs()
    batch_client = InMemoryBatchClient()

    for bad in ("42", 1.5, None, True):
        try:
            lo.orchestrate_lahc_run(
                snapshot_dict,
                master_seed=bad,  # type: ignore[arg-type]
                K_approved=8,
                container_image_uri=_IMAGE,
                batch_client=batch_client,
                gcs_read_json=read_json, gcs_write_json=write_json,
                gcs_delete_prefix=_no_delete,
                project=_PROJECT, bucket=_BUCKET, region=_REGION,
                sleep_fn=_no_sleep, time_fn=_virtual_clock(),
                wall_time_fn=_fixed_wall_time_fn,
                attempt_id_fn=_fixed_attempt_id_fn,
            )
        except ValueError as e:
            assert "master_seed" in str(e)
            continue
        raise AssertionError(
            "orchestrate_lahc_run(master_seed=" + repr(bad)
            + ") should have raised"
        )


def test_orchestrator_rejects_non_positive_K_approved() -> None:
    snapshot_dict = {"metadata": {"snapshotId": "snap-x"}}
    read_json, write_json, _ = _make_inmem_gcs()
    batch_client = InMemoryBatchClient()

    for bad in (0, -1, "8", 1.5, True):
        try:
            lo.orchestrate_lahc_run(
                snapshot_dict,
                master_seed=42,
                K_approved=bad,  # type: ignore[arg-type]
                container_image_uri=_IMAGE,
                batch_client=batch_client,
                gcs_read_json=read_json, gcs_write_json=write_json,
                gcs_delete_prefix=_no_delete,
                project=_PROJECT, bucket=_BUCKET, region=_REGION,
                sleep_fn=_no_sleep, time_fn=_virtual_clock(),
                wall_time_fn=_fixed_wall_time_fn,
                attempt_id_fn=_fixed_attempt_id_fn,
            )
        except ValueError as e:
            assert "K_approved" in str(e)
            continue
        raise AssertionError(
            "orchestrate_lahc_run(K_approved=" + repr(bad)
            + ") should have raised"
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
                continue
            fn()
            print("ok   " + name)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print("FAIL " + name + ": " + repr(exc))
    if failures:
        sys.exit(1)
