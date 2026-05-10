"""Cloud Run orchestrator for the M7 LAHC parallel-solver path per
`docs/cloud_compute_contract.md` §8.7 + `docs/delivery_plan.md` §9 M7 C2
Task 2F.

`orchestrate_lahc_run(snapshot_dict, ...)` is the entry point the M7 C2
Task 2F maintainer-only `/compute-lahc-test` route calls. End-to-end
flow:

  1. Derive runId from `(snapshotId, masterSeed)` so re-runs of the same
     parameters overwrite GCS artifacts deterministically (idempotent),
     and different parameters produce distinct artifact paths.
  2. Pre-derive all `K_approved` trajectory seeds via
     `derive_K_seeds(masterSeed, K_approved)` per §12A.10 — single
     source of truth shared with the local-CLI K-trajectory loop.
  3. Partition the K-length seed list into per-task slices of up to
     `TRAJECTORIES_PER_TASK = 8` per the §8.7 dense-pack invariant.
     Final task may carry fewer when K_approved isn't a multiple of 8
     (current production K=104 → all 13 tasks fully packed at 8).
  4. Write input snapshot.json + per-task seeds.json files to GCS at
     the §8.7 key paths. The worker (T2D) picks them up via the same
     URI scheme.
  5. Build the Cloud Batch job spec via T2E's
     `build_lahc_batch_job_spec(...)` and submit to Cloud Batch.
  6. Poll `batch.jobs.get` at `_DEFAULT_POLL_INTERVAL_SECONDS`. On
     terminal state (SUCCEEDED / FAILED / CANCELLED), proceed to
     aggregation. On wall-clock elapsed > `_COMPLETION_DEADLINE_SECONDS`
     (240s per §8.7), call `cancel_job` + proceed to aggregation
     anyway (partial-failure tolerance).
  7. Read per-task `result.json` files from GCS. Missing / unreadable
     results contribute 0 candidates to K' per §8.7's primary K'
     definition.
  8. Aggregate: `K' = sum(len(result.json["candidates"]))` across
     completed tasks; `dropped_count = K_approved - K'` is the derived
     diagnostic. Returns a structured summary dict the test route
     surfaces verbatim.

The wrapper-envelope assembly (scorer → selector → final envelope) is
NOT part of T2F's scope per the §9 cadence — that lands at T2G
alongside the determinism re-audit, which needs the scored winner to
verify byte-identity vs the local CLI. T2F's response is a raw K'
summary suitable for maintainer inspection.

All I/O ports are injectable for testability — production wires the
real `BatchClient` + `make_gcs_adapter(...)`; tests pass
`InMemoryBatchClient` + an in-memory dict-backed adapter.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Callable

from rostermonster.solver import derive_K_seeds
from rostermonster_service.batch_client import (
    JOB_STATE_CANCELLED,
    JOB_STATE_FAILED,
    JOB_STATE_SUCCEEDED,
    TERMINAL_JOB_STATES,
)
from rostermonster_service.batch_job_spec import (
    build_lahc_batch_job_spec,
    task_count_for_K,
)
from rostermonster_service.gcs import ReadJsonFn, WriteJsonFn


log = logging.getLogger("rostermonster_service.lahc_orchestrator")

# §8.7 invariants — replicated here (vs imported from worker.py) so the
# orchestrator can be reasoned about standalone without reading the
# worker's module to know dense-pack semantics.
TRAJECTORIES_PER_TASK = 8
_DEFAULT_BUCKET = "rostermonsterv2-lahc"
_DEFAULT_REGION = "asia-southeast1"

# §8.7 timing invariants. The 240s orchestrator-side completion deadline
# leaves ~10s buffer before the M7 C3 Cloud Run Service 250s wall (per
# D-0070 sub-decision 5); polling cadence ~3s gives 80 polls within the
# budget without flooding the Batch API.
_COMPLETION_DEADLINE_SECONDS = 240
_DEFAULT_POLL_INTERVAL_SECONDS = 3

# Run state strings — orchestrator-defined, surface in the response dict
# alongside the Cloud Batch job state so the maintainer can distinguish
# orchestrator-side timeout from a Batch-side failure.
_BATCH_FINAL_STATE_SUCCEEDED = JOB_STATE_SUCCEEDED
_BATCH_FINAL_STATE_FAILED = JOB_STATE_FAILED
_BATCH_FINAL_STATE_CANCELLED = JOB_STATE_CANCELLED
_BATCH_FINAL_STATE_CANCELLED_OVER_DEADLINE = "CANCELLED_OVER_DEADLINE"


def _gcs_uri(bucket: str, run_id: str, *parts: str) -> str:
    return "gs://" + bucket + "/" + "/".join((run_id, *parts))


def derive_run_id(snapshot_id: str, master_seed: int) -> str:
    """Derive a unique-but-deterministic runId from `(snapshotId,
    masterSeed)` so re-runs with identical parameters overwrite GCS
    artifacts (idempotent forensic replay) while different parameters —
    including different extractions of the same spreadsheet at
    different timestamps — get distinct paths.

    Real bound-shim snapshot IDs are `snapshot_<spreadsheetId>_<extractionTimestamp>`
    per `docs/snapshot_adapter_contract.md`. The spreadsheetId portion
    alone can run ~44 chars; sanitization + a `-seed-N` suffix would
    exceed Cloud Batch's 63-char `job_id` cap and force right-truncation
    that drops the timestamp, collapsing two distinct extractions of
    the same spreadsheet to the same runId. To preserve uniqueness
    under truncation, we mix a content hash of the FULL `(snapshot_id,
    master_seed)` tuple into the runId and reserve fixed-length slots
    for the readable prefix + entropy hash + seed label. Two
    extractions of the same spreadsheet with the same seed produce
    different snapshot_ids → different content hashes → different
    runIds. Idempotency is preserved by hashing the same input tuple.
    """
    if not isinstance(snapshot_id, str) or not snapshot_id:
        raise ValueError(
            "snapshot_id must be a non-empty string; got "
            + type(snapshot_id).__name__ + "=" + repr(snapshot_id)
        )
    sanitized = "".join(
        c.lower() if c.isalnum() else "-" for c in snapshot_id
    ).strip("-")
    if not sanitized:
        raise ValueError(
            "snapshot_id sanitized to empty string; original was "
            + repr(snapshot_id)
        )

    # 8-hex-char content hash over the full unsanitized input tuple
    # disambiguates collisions when sanitized + truncated forms would
    # match. 16^8 = 4.3B distinct values per (snapshot_id, master_seed)
    # combination — collision-resistant for the maintainer test path's
    # request volume.
    content_hash = hashlib.sha256(
        (snapshot_id + ":" + str(master_seed)).encode("utf-8")
    ).hexdigest()[:8]

    seed_label = "n" + str(abs(master_seed)) if master_seed < 0 else str(master_seed)

    # Layout: <readable-prefix>-<8hex>-seed-<label>
    # Reserve room for the entropy hash + seed suffix; truncate the
    # readable prefix as needed.
    suffix = "-" + content_hash + "-seed-" + seed_label
    max_len = 63  # Cloud Batch v1 job_id length cap

    prefix_room = max_len - len(suffix)
    if prefix_room < 1:
        # Suffix alone exceeds budget (extreme seed values). Fall back
        # to hash-only — still unique per tuple + still job_id-conformant.
        return ("h-" + content_hash + "-seed-" + seed_label)[:max_len]

    return sanitized[:prefix_room] + suffix


def _partition_seeds(seeds: list[int], per_task: int = TRAJECTORIES_PER_TASK) -> list[list[int]]:
    """Slice a K-length seed list into per-task chunks of `per_task`.
    Final chunk may be smaller when len(seeds) isn't a multiple of
    per_task (matches the §8.7 partial-pack tolerance for the final
    task at full M7 quota K=2,500)."""
    return [
        seeds[i:i + per_task]
        for i in range(0, len(seeds), per_task)
    ]


def _poll_until_terminal_or_deadline(
    *,
    batch_client,  # BatchClient | InMemoryBatchClient
    job_name: str,
    deadline_seconds: float,
    poll_interval_seconds: float,
    sleep_fn: Callable[[float], None],
    time_fn: Callable[[], float],
) -> tuple[str, float]:
    """Poll a Cloud Batch job until terminal or deadline. Returns
    `(final_state, elapsed_seconds)` where `final_state` is one of
    `_BATCH_FINAL_STATE_*` constants. `_CANCELLED_OVER_DEADLINE` is
    distinct from `_CANCELLED` (the latter would be a maintainer-issued
    cancel via the Cloud Console, not orchestrator-issued via deadline)."""
    t_start = time_fn()
    while True:
        state = batch_client.get_job_state(job_name=job_name)
        elapsed = time_fn() - t_start
        if state in TERMINAL_JOB_STATES:
            return state, elapsed
        if elapsed > deadline_seconds:
            log.warning(
                "Batch job %s exceeded %.1fs deadline (state=%s, elapsed=%.1fs); cancelling",
                job_name, deadline_seconds, state, elapsed,
            )
            batch_client.cancel_job(job_name=job_name)
            return _BATCH_FINAL_STATE_CANCELLED_OVER_DEADLINE, elapsed
        sleep_fn(poll_interval_seconds)


def _aggregate_results(
    *,
    task_count: int,
    bucket: str,
    run_id: str,
    gcs_read_json: ReadJsonFn,
) -> dict[str, Any]:
    """Read per-task `result.json` files from GCS and aggregate.
    Missing / unreadable results contribute 0 candidates per §8.7's
    primary K' definition; they're counted in `incomplete_task_indices`
    so the response surfaces which tasks contributed nothing."""
    candidates: list[dict] = []
    failed_trajectories: list[dict] = []
    trajectory_exceptions: list[dict] = []
    aggregate_attempts = 0
    aggregate_rejections: dict[str, int] = {}
    completed_task_indices: list[int] = []
    incomplete_task_indices: list[int] = []
    per_task_results: list[dict | None] = []

    for task_index in range(task_count):
        result_uri = _gcs_uri(
            bucket, run_id, "task-" + str(task_index), "result.json",
        )
        try:
            result = gcs_read_json(result_uri)
        except Exception as e:
            log.warning(
                "Failed to read result.json for task %d (%s): %s",
                task_index, result_uri, e,
            )
            per_task_results.append(None)
            incomplete_task_indices.append(task_index)
            continue

        per_task_results.append(result)
        completed_task_indices.append(task_index)
        for cand in result.get("candidates", []):
            candidates.append({"taskIndex": task_index, **cand})
        for failed in result.get("failedTrajectories", []):
            failed_trajectories.append({"taskIndex": task_index, **failed})
        for exc in result.get("trajectoryExceptions", []):
            trajectory_exceptions.append({"taskIndex": task_index, **exc})
        aggregate_attempts += int(result.get("aggregateAttempts", 0))
        for code, count in result.get("aggregateRejectionsByReason", {}).items():
            aggregate_rejections[code] = aggregate_rejections.get(code, 0) + int(count)

    return {
        "candidates": candidates,
        "failedTrajectories": failed_trajectories,
        "trajectoryExceptions": trajectory_exceptions,
        "aggregateAttempts": aggregate_attempts,
        "aggregateRejectionsByReason": aggregate_rejections,
        "completedTaskIndices": completed_task_indices,
        "incompleteTaskIndices": incomplete_task_indices,
        "perTaskResults": per_task_results,
    }


def orchestrate_lahc_run(
    snapshot_dict: dict,
    *,
    master_seed: int,
    K_approved: int,
    container_image_uri: str,
    batch_client,  # BatchClient | InMemoryBatchClient
    gcs_read_json: ReadJsonFn,
    gcs_write_json: WriteJsonFn,
    project: str,
    bucket: str = _DEFAULT_BUCKET,
    region: str = _DEFAULT_REGION,
    completion_deadline_seconds: float = _COMPLETION_DEADLINE_SECONDS,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
    time_fn: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Orchestrate one M7 LAHC Cloud Batch run end-to-end. Returns a
    structured response dict the maintainer-only `/compute-lahc-test`
    route surfaces verbatim.

    The response shape (M7 C2 Task 2F scope — wrapper-envelope assembly
    deferred to T2G):

    ```
    {
      "state": "OK" | "UNSATISFIED" | "COMPUTE_ERROR",
      "lahcSummary": {
        "runId": "...",
        "masterSeed": <int>,
        "kApproved": <int>,
        "kPrime": <int>,                       // surviving-trajectory count
        "droppedCount": <int>,                 // K_approved - kPrime
        "taskCount": <int>,
        "completedTaskCount": <int>,
        "incompleteTaskIndices": [<int>, ...], // tasks with no readable result.json
        "totalAttempts": <int>,
        "rejectionsByReason": {<code>: <int>},
        "batchJobName": "projects/.../jobs/...",
        "batchFinalState": "SUCCEEDED" | "FAILED" | "CANCELLED" | "CANCELLED_OVER_DEADLINE",
        "elapsedSeconds": <float>
      },
      "candidates": [...],                     // raw aggregated candidates per result.json
      "failedTrajectories": [...],             // SEED_FAILED per §12A.8
      "trajectoryExceptions": [...],           // optional
      "error": null | {"code": "...", "message": "..."}
    }
    ```

    `state="OK"` iff `kPrime > 0` (at least one trajectory produced a
    candidate). `state="UNSATISFIED"` iff `kPrime == 0` (all
    trajectories dropped on per-trajectory seed-construction failure
    per §12A.8 OR every task failed to complete). `state="COMPUTE_ERROR"`
    is reserved for orchestrator-level failures (snapshot missing
    metadata, etc.).
    """
    # --- Validation --------------------------------------------------
    if (isinstance(master_seed, bool)
            or not isinstance(master_seed, int)):
        raise ValueError(
            "master_seed must be int; got " + type(master_seed).__name__
        )
    if (isinstance(K_approved, bool)
            or not isinstance(K_approved, int)
            or K_approved <= 0):
        raise ValueError(
            "K_approved must be a positive int; got " + repr(K_approved)
        )
    metadata = snapshot_dict.get("metadata") if isinstance(snapshot_dict, dict) else None
    if not isinstance(metadata, dict) or not metadata.get("snapshotId"):
        return _build_compute_error(
            run_id="",
            master_seed=master_seed,
            K_approved=K_approved,
            code="MISSING_SNAPSHOT_ID",
            message=(
                "snapshot.metadata.snapshotId is required for runId derivation; "
                "got snapshot.metadata=" + repr(metadata)
            ),
        )
    snapshot_id = metadata["snapshotId"]
    run_id = derive_run_id(snapshot_id, master_seed)

    # --- Seed pre-derivation + partition -----------------------------
    all_seeds = derive_K_seeds(master_seed, K_approved)
    per_task_seeds = _partition_seeds(all_seeds)
    task_count = len(per_task_seeds)
    # Sanity: should match T2E's task_count_for_K.
    assert task_count == task_count_for_K(K_approved), (
        "partition produced " + str(task_count)
        + " tasks; task_count_for_K(K) = " + str(task_count_for_K(K_approved))
    )

    # --- Write snapshot + per-task seeds to GCS ----------------------
    snapshot_uri = _gcs_uri(bucket, run_id, "snapshot.json")
    gcs_write_json(snapshot_uri, snapshot_dict)
    for task_index, seeds in enumerate(per_task_seeds):
        seeds_uri = _gcs_uri(
            bucket, run_id, "task-" + str(task_index), "seeds.json",
        )
        gcs_write_json(seeds_uri, {
            "schemaVersion": 1,
            "runId": run_id,
            "taskIndex": task_index,
            "masterSeed": master_seed,
            "seeds": seeds,
        })

    # --- Build + submit Batch job ------------------------------------
    job_spec = build_lahc_batch_job_spec(
        run_id=run_id,
        K_approved=K_approved,
        container_image_uri=container_image_uri,
        bucket=bucket,
        region=region,
    )
    job_name = batch_client.submit_job(
        project=project, region=region, run_id=run_id, job_spec=job_spec,
    )
    log.info("Batch job submitted: %s (taskCount=%d)", job_name, task_count)

    # --- Poll for terminal state or deadline -------------------------
    final_state, elapsed = _poll_until_terminal_or_deadline(
        batch_client=batch_client,
        job_name=job_name,
        deadline_seconds=completion_deadline_seconds,
        poll_interval_seconds=poll_interval_seconds,
        sleep_fn=sleep_fn,
        time_fn=time_fn,
    )

    # --- Aggregate per-task result.json ------------------------------
    agg = _aggregate_results(
        task_count=task_count,
        bucket=bucket,
        run_id=run_id,
        gcs_read_json=gcs_read_json,
    )

    candidates = agg["candidates"]
    k_prime = len(candidates)
    state = "OK" if k_prime > 0 else "UNSATISFIED"

    summary = {
        "runId": run_id,
        "masterSeed": master_seed,
        "kApproved": K_approved,
        "kPrime": k_prime,
        "droppedCount": K_approved - k_prime,
        "taskCount": task_count,
        "completedTaskCount": len(agg["completedTaskIndices"]),
        "incompleteTaskIndices": agg["incompleteTaskIndices"],
        "totalAttempts": agg["aggregateAttempts"],
        "rejectionsByReason": agg["aggregateRejectionsByReason"],
        "batchJobName": job_name,
        "batchFinalState": final_state,
        "elapsedSeconds": round(elapsed, 3),
    }

    response: dict[str, Any] = {
        "state": state,
        "lahcSummary": summary,
        "candidates": candidates,
        "failedTrajectories": agg["failedTrajectories"],
        "error": None,
    }
    if agg["trajectoryExceptions"]:
        response["trajectoryExceptions"] = agg["trajectoryExceptions"]
    return response


def _build_compute_error(
    *, run_id: str, master_seed: int, K_approved: int,
    code: str, message: str,
) -> dict:
    """Orchestrator-level error response (e.g., snapshot missing
    snapshotId). Returns the same dict shape as the success path so
    callers don't have to special-case error responses."""
    return {
        "state": "COMPUTE_ERROR",
        "lahcSummary": {
            "runId": run_id,
            "masterSeed": master_seed,
            "kApproved": K_approved,
            "kPrime": 0,
            "droppedCount": K_approved,
            "taskCount": 0,
            "completedTaskCount": 0,
            "incompleteTaskIndices": [],
            "totalAttempts": 0,
            "rejectionsByReason": {},
            "batchJobName": "",
            "batchFinalState": "NOT_SUBMITTED",
            "elapsedSeconds": 0.0,
        },
        "candidates": [],
        "failedTrajectories": [],
        "error": {"code": code, "message": message},
    }
