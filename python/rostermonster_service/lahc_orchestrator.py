"""Cloud Run orchestrator for the M7 LAHC parallel-solver path per
`docs/cloud_compute_contract.md` §8.7 + `docs/delivery_plan.md` §9 M7 C2
Task 2F.

**Concurrent-replay race closed at T2G via attempt-id validation:**
the runId is deterministic per `(snapshotId, masterSeed)` so two
maintainer-issued replays of the same parameters share the same GCS
artifact prefix. The pre-write `gcs_delete_prefix(runId/)` step
(below) keeps a serial replay clean. Concurrent replays were a P1
race window flagged at T2F (PR #143) — closed at T2G by stamping a
fresh `attemptId` (uuid4 hex) into every per-task `seeds.json`, the
worker echoes it back into `result.json`, and aggregation validates
`result.attemptId == expected_attempt_id` on read; mismatched /
missing attemptIds are treated as missing per §8.7's primary K'
definition. So if two orchestrator calls overlap on the same runId,
each sees only its own attempt's results — at worst one attempt
sees all its inputs stomped (UNSATISFIED) but never a polluted /
mixed K' aggregation.

`orchestrate_lahc_run(snapshot_dict, ...)` is the entry point the
maintainer-only `/compute-lahc-test` route calls (D-0071 sub-decision
14 — kept after the operator path moves async at M7 C4 because it
exposes the synchronous-from-curl maintainer test pattern). The
operator path no longer routes through this orchestrator: M7 C4 T2A.2
PR-A moved the polling + aggregation + scoring + analyzer + callback
POST chain INLINE into `worker.py`'s finalize step (per §8.7
finalizer-inline pattern, Codex P1.7 amendment). End-to-end flow for
the maintainer test path:

  1. Derive runId from `(snapshotId, masterSeed)` so re-runs of the
     same parameters overwrite GCS artifacts deterministically
     (idempotent), and different parameters produce distinct artifact
     paths.
  2. Write input snapshot.json to GCS at the §8.7 key path. The
     worker derives all K trajectory seeds locally via
     `derive_K_seeds(masterSeed, K_approved)` per §12A.10 (no
     per-task seeds.json under the single-task pivot per Codex P1.7
     amendment).
  3. Build the Cloud Batch job spec via
     `build_lahc_batch_job_spec(...)` and submit to Cloud Batch with
     `RM_LAUNCHER_CALLBACK_URL=""` (empty — maintainer test path
     skips the worker's inline callback POST per worker.py's
     `_inline_finalize` short-circuit).
  4. Poll `batch.jobs.get` at `_DEFAULT_POLL_INTERVAL_SECONDS`. On
     terminal state (SUCCEEDED / FAILED / CANCELLED), proceed to
     aggregation. On wall-clock elapsed > `_COMPLETION_DEADLINE_SECONDS`
     (240s per §8.7), call `cancel_job` + proceed to aggregation
     anyway (partial-failure tolerance).
  5. Read single `result.json` from GCS at `gs://bucket/{runId}/result.json`
     (single-task pattern — no per-task subdirs). Missing / unreadable
     result contributes 0 candidates to K' per §8.7's primary K'
     definition.
  6. Run the post-aggregation pipeline (score → select → wrapper
     envelope) via `post_aggregation.build_post_aggregation_envelope`
     so the test route returns the same `writebackEnvelope` shape as
     the operator path's inline finalize POSTs to the launcher.
     Returns a structured summary dict the test route surfaces
     verbatim.

All I/O ports are injectable for testability — production wires the
real `BatchClient` + `make_gcs_adapter(...)`; tests pass
`InMemoryBatchClient` + an in-memory dict-backed adapter.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import time
import uuid
from typing import Any, Callable

from rostermonster.parser import Consumability, parse
from rostermonster.pipeline import _snapshot_from_dict
from rostermonster.templates import icu_hd_template_artifact
from rostermonster_service.batch_client import (
    JOB_STATE_CANCELLED,
    JOB_STATE_FAILED,
    JOB_STATE_SUCCEEDED,
    TERMINAL_JOB_STATES,
)
from rostermonster_service.batch_job_spec import build_lahc_batch_job_spec
from rostermonster_service.gcs import (
    DeletePrefixFn,
    ReadJsonFn,
    WriteJsonFn,
)
from rostermonster_service.post_aggregation import (
    build_post_aggregation_envelope,
)


log = logging.getLogger("rostermonster_service.lahc_orchestrator")

# §8.7 invariants — replicated here (vs imported from worker.py) so the
# orchestrator can be reasoned about standalone without reading the
# worker's module to know dense-pack semantics.
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



def _aggregate_single_task_result(
    *,
    bucket: str,
    run_id: str,
    expected_attempt_id: str,
    gcs_read_json: ReadJsonFn,
) -> dict[str, Any]:
    """Read the single result.json from GCS and surface its contents in
    the shape `build_post_aggregation_envelope` expects.

    Under M7 C4 T2A.1 single-task pattern (Codex P1.7 amendment), the
    worker writes one result.json at `gs://bucket/{runId}/result.json`
    (no per-task subdirectory). Missing / unreadable results contribute
    0 candidates per §8.7's primary K' definition; `resultPresent=False`
    signals the orchestrator should treat as UNSATISFIED + flag the
    incomplete task in the response summary.

    **attemptId validation** (Codex P2 round 2 finding 4 fix): two
    concurrent /compute-lahc-test replays of the same `(snapshotId,
    masterSeed)` produce the same deterministic runId and would
    otherwise overwrite each other's result.json. The orchestrator
    stamps a per-attempt `attempt_id` into the worker's env; the worker
    echoes it back into result.json's `attemptId`; this aggregator
    treats a result.json with mismatched (or missing when
    expected_attempt_id is non-empty) attemptId the same as missing.
    Empty `expected_attempt_id` skips the check (caller didn't need
    collision protection for that surface).
    """
    candidates: list[dict] = []
    failed_trajectories: list[dict] = []
    trajectory_exceptions: list[dict] = []
    aggregate_attempts = 0
    aggregate_rejections: dict[str, int] = {}
    result_present = False
    per_task_results: list[dict | None] = [None]

    result_uri = _gcs_uri(bucket, run_id, "result.json")
    try:
        result = gcs_read_json(result_uri)
    except Exception as e:
        log.warning(
            "Failed to read result.json (%s): %s — treating as missing",
            result_uri, e,
        )
        return {
            "candidates": candidates,
            "failedTrajectories": failed_trajectories,
            "trajectoryExceptions": trajectory_exceptions,
            "aggregateAttempts": aggregate_attempts,
            "aggregateRejectionsByReason": aggregate_rejections,
            "resultPresent": False,
            "perTaskResults": per_task_results,
        }

    # Attempt-id validation per Codex P2 round 2 finding 4 fix.
    if expected_attempt_id:
        result_attempt_id = result.get("attemptId")
        if result_attempt_id != expected_attempt_id:
            log.warning(
                "result.json has attemptId=%r; expected %r — treating "
                "as missing (concurrent replay collided on the deterministic "
                "runId, OR a prior attempt's result.json wasn't cleared)",
                result_attempt_id, expected_attempt_id,
            )
            return {
                "candidates": candidates,
                "failedTrajectories": failed_trajectories,
                "trajectoryExceptions": trajectory_exceptions,
                "aggregateAttempts": aggregate_attempts,
                "aggregateRejectionsByReason": aggregate_rejections,
                "resultPresent": False,
                "perTaskResults": per_task_results,
            }

    result_present = True
    per_task_results = [result]
    for cand in result.get("candidates", []):
        # Preserve the "taskIndex": 0 shape `build_post_aggregation_envelope`
        # expects under the multi-task aggregation contract; under
        # single-task there's exactly one task at index 0.
        candidates.append({"taskIndex": 0, **cand})
    for failed in result.get("failedTrajectories", []):
        failed_trajectories.append({"taskIndex": 0, **failed})
    for exc in result.get("trajectoryExceptions", []):
        trajectory_exceptions.append({"taskIndex": 0, **exc})
    aggregate_attempts = int(result.get("aggregateAttempts", 0))
    for code, count in result.get("aggregateRejectionsByReason", {}).items():
        aggregate_rejections[code] = aggregate_rejections.get(code, 0) + int(count)

    return {
        "candidates": candidates,
        "failedTrajectories": failed_trajectories,
        "trajectoryExceptions": trajectory_exceptions,
        "aggregateAttempts": aggregate_attempts,
        "aggregateRejectionsByReason": aggregate_rejections,
        "resultPresent": result_present,
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
    gcs_delete_prefix: DeletePrefixFn,
    project: str,
    bucket: str = _DEFAULT_BUCKET,
    region: str = _DEFAULT_REGION,
    completion_deadline_seconds: float = _COMPLETION_DEADLINE_SECONDS,
    poll_interval_seconds: float = _DEFAULT_POLL_INTERVAL_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
    time_fn: Callable[[], float] = time.monotonic,
    wall_time_fn: Callable[[], float] = time.time,
    attempt_id_fn: Callable[[], str] = lambda: uuid.uuid4().hex,
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

    # Validate the snapshot is fully deserializable BEFORE dispatching
    # to Cloud Batch. The route's body validation only checks the
    # shallow `snapshot.metadata.snapshotId` presence; a snapshot can
    # have a valid snapshotId but be otherwise malformed (e.g., missing
    # required `periodRef` / `doctorRecords` / etc.). Without this
    # check, workers fail uniformly + K'==0 + the post-aggregation
    # wrapper helper can't re-parse the snapshot to build a failure-
    # branch envelope, leaving `writebackEnvelope=null` while still
    # reporting `state=UNSATISFIED` (§10.3 violation). Codex P2
    # finding on PR #144 commit 80e0ceb. Surfacing as COMPUTE_ERROR
    # here keeps the §10.3 invariant + saves the maintainer the
    # Cloud Batch round-trip cost on a snapshot that can't possibly
    # produce a valid envelope.
    try:
        snapshot_obj = _snapshot_from_dict(snapshot_dict)
    except (KeyError, TypeError, ValueError) as e:
        return _build_compute_error(
            run_id=run_id,
            master_seed=master_seed,
            K_approved=K_approved,
            code="SNAPSHOT_NOT_DESERIALIZABLE",
            message=(
                "snapshot has a valid snapshotId but is otherwise not "
                "deserializable (" + type(e).__name__ + ": " + str(e)
                + "). Surfacing as COMPUTE_ERROR here per §10.3 — "
                "the maintainer test path can't produce a valid "
                "writebackEnvelope without a parseable snapshot."
            ),
        )

    # Validate parser consumability BEFORE dispatching to Cloud Batch.
    # A snapshot that deserializes but is parser-NON_CONSUMABLE (per
    # `docs/parser_normalizer_contract.md`) is an input defect — the
    # local `/compute` path surfaces it as INPUT_ERROR with code
    # PARSER_REJECTED + a truncated issue summary, NOT COMPUTE_ERROR.
    # Without this check, Cloud-Batch workers all fail uniformly on
    # the same parser rejection and the orchestrator maps the resulting
    # K'==0 + null wrapper to COMPUTE_ERROR / WRAPPER_ASSEMBLY_FAILED
    # — losing the actionable parser issues + wasting Batch compute on
    # a request that can't produce a valid envelope. Codex P2 finding
    # on PR #144 commit bad297f.
    template = icu_hd_template_artifact()
    parser_result = parse(snapshot_obj, template)
    if parser_result.consumability is not Consumability.CONSUMABLE:
        issue_summary = "; ".join(
            "[" + getattr(i.severity, "name", str(i.severity)) + "] "
            + i.code + ": " + i.message
            for i in parser_result.issues[:5]
        )
        if len(parser_result.issues) > 5:
            issue_summary += (
                " (+" + str(len(parser_result.issues) - 5) + " more "
                "issues — truncated for response brevity)"
            )
        return _build_input_error(
            run_id=run_id,
            master_seed=master_seed,
            K_approved=K_approved,
            code="PARSER_REJECTED",
            message=(
                "Parser rejected the snapshot at admission with "
                + str(len(parser_result.issues)) + " issue(s): "
                + issue_summary
            ),
        )

    # Per-attempt unique ID — kept for cross-call disambiguation in the
    # response summary (useful for the maintainer to correlate Cloud
    # Logging entries against a specific orchestrator call). The §8.7
    # concurrent-replay race fix from T2G is no longer load-bearing
    # under single-task (Codex P1.7 amendment, M7 C4 T2A.1) — there's
    # one task per runId, so per-task attemptId echoing isn't needed.
    # Concurrent-rejection at the front door (T2D) closes the cross-
    # request race via Cloud Batch labels per D-0071 sub-decision 8.
    attempt_id = attempt_id_fn()

    # --- Invalidate stale artifacts from a prior replay attempt -------
    # The runId is intentionally deterministic per (snapshotId, masterSeed)
    # so forensic replay is idempotent at the artifact-prefix level —
    # but Batch job_id is per-call unique (a replay submits a fresh
    # Batch job, not the same one). Without this clear step, a partial-
    # failure on a replay would silently inherit a stale result.json
    # from the prior attempt at the same runId prefix.
    prefix_uri = _gcs_uri(bucket, run_id) + "/"
    deleted_count = gcs_delete_prefix(prefix_uri)
    if deleted_count:
        log.info(
            "Cleared %d stale artifacts at %s before fresh attempt",
            deleted_count, prefix_uri,
        )

    # --- Write snapshot to GCS ----------------------------------------
    # Under M7 C4 T2A.1 single-task pattern, per-task seeds.json is
    # RETIRED — the worker derives all K seeds locally from
    # RM_MASTER_SEED env via derive_K_seeds() per §12A.10. Only the
    # snapshot needs to land in GCS.
    snapshot_uri = _gcs_uri(bucket, run_id, "snapshot.json")
    gcs_write_json(snapshot_uri, snapshot_dict)

    # --- Build + submit Batch job ------------------------------------
    # M7 C4 T2A.1 single-task spec: master_seed + K_approved flow via
    # env vars set on the task spec (read by worker.py). For
    # /compute-lahc-test, operator_email + launcher_callback_url are
    # not supplied — they default to empty (worker.py T2A.1 doesn't
    # use them; T2A.2's inline finalize step will read them when
    # those land).
    source_spreadsheet_id = metadata.get("sourceSpreadsheetId") or snapshot_id
    # Wall-clock epoch ms — NOT time_fn() (which defaults to time.monotonic
    # and is process-local; the worker reads RM_SUBMIT_TIMESTAMP_MS in a
    # different process for T2A.2's elapsed self-check, so the timestamp
    # must be in the comparable epoch-time scale). Codex P2 round 2
    # finding 2 fix.
    submit_ts_ms = int(wall_time_fn() * 1000)
    job_spec = build_lahc_batch_job_spec(
        run_id=run_id,
        container_image_uri=container_image_uri,
        master_seed=master_seed,
        source_spreadsheet_id=source_spreadsheet_id,
        attempt_id=attempt_id,
        submit_timestamp_ms=submit_ts_ms,
        K_approved=K_approved,
        bucket=bucket,
        region=region,
    )
    job_name = batch_client.submit_job(
        project=project, region=region, run_id=run_id, job_spec=job_spec,
    )
    log.info("Batch job submitted: %s (single-task, K=%d)", job_name, K_approved)

    # --- Poll for terminal state or deadline -------------------------
    final_state, elapsed = _poll_until_terminal_or_deadline(
        batch_client=batch_client,
        job_name=job_name,
        deadline_seconds=completion_deadline_seconds,
        poll_interval_seconds=poll_interval_seconds,
        sleep_fn=sleep_fn,
        time_fn=time_fn,
    )

    # --- Aggregate single result.json --------------------------------
    agg = _aggregate_single_task_result(
        bucket=bucket,
        run_id=run_id,
        expected_attempt_id=attempt_id,
        gcs_read_json=gcs_read_json,
    )

    candidates = agg["candidates"]
    k_prime = len(candidates)
    state = "OK" if k_prime > 0 else "UNSATISFIED"

    summary = {
        "runId": run_id,
        "attemptId": attempt_id,
        "masterSeed": master_seed,
        "kApproved": K_approved,
        "kPrime": k_prime,
        "droppedCount": K_approved - k_prime,
        "taskCount": 1,
        "completedTaskCount": 1 if agg["resultPresent"] else 0,
        "incompleteTaskIndices": [] if agg["resultPresent"] else [0],
        "totalAttempts": agg["aggregateAttempts"],
        "rejectionsByReason": agg["aggregateRejectionsByReason"],
        "batchJobName": job_name,
        "batchFinalState": final_state,
        "elapsedSeconds": round(elapsed, 3),
    }

    # T2G: post-aggregation pipeline — score K' candidates (success
    # branch) OR build failure-branch envelope from
    # failedTrajectories aggregation (UNSATISFIED branch). Either way
    # produces a non-null wrapper per `docs/cloud_compute_contract.md`
    # §10.3 (OK/UNSATISFIED MUST carry a non-null
    # writebackEnvelope). The helper only returns None on a defensive
    # post-Batch parser rejection (snapshot deserialized fine at
    # orchestrator entry but parse() rejected — shouldn't happen since
    # snapshot is immutable in GCS); detect + promote to COMPUTE_ERROR
    # rather than violating §10.3.
    wrapper_envelope = build_post_aggregation_envelope(
        snapshot_dict=snapshot_dict,
        agg=agg,
        master_seed=master_seed,
        K_approved=K_approved,
        run_id=run_id,
    )

    if wrapper_envelope is None:
        log.error(
            "Wrapper envelope assembly returned None despite orchestrator "
            "pre-validation; promoting to COMPUTE_ERROR per §10.3"
        )
        return _build_compute_error(
            run_id=run_id,
            master_seed=master_seed,
            K_approved=K_approved,
            code="WRAPPER_ASSEMBLY_FAILED",
            message=(
                "Post-aggregation wrapper envelope assembly failed "
                "despite the orchestrator's pre-dispatch snapshot "
                "deserializability check. Parser rejected the snapshot "
                "post-Batch, suggesting state corruption between entry "
                "and aggregation. Surfacing as COMPUTE_ERROR per §10.3 "
                "to honor the OK/UNSATISFIED non-null-wrapper invariant."
            ),
        )

    response: dict[str, Any] = {
        "state": state,
        "lahcSummary": summary,
        "writebackEnvelope": wrapper_envelope,
        "candidates": candidates,
        "failedTrajectories": agg["failedTrajectories"],
        "error": None,
    }
    if agg["trajectoryExceptions"]:
        response["trajectoryExceptions"] = agg["trajectoryExceptions"]
    return response


def _build_input_error(
    *, run_id: str, master_seed: int, K_approved: int,
    code: str, message: str,
) -> dict:
    """Orchestrator-level input-error response (e.g., parser rejected
    the snapshot at admission). Mirrors `_build_compute_error`'s shape
    but with `state="INPUT_ERROR"` + `writebackEnvelope=None` per
    `docs/cloud_compute_contract.md` §10.1 — INPUT_ERROR responses
    MAY have a null wrapper since they fire before any compute."""
    return {
        "state": "INPUT_ERROR",
        "lahcSummary": {
            "runId": run_id,
            "attemptId": "",
            "masterSeed": master_seed,
            "kApproved": K_approved,
            "kPrime": 0,
            "droppedCount": K_approved,
            "taskCount": 0,
            "completedTaskCount": 0,
            "incompleteTaskIndices": [],
            "mismatchedAttemptTaskIndices": [],
            "totalAttempts": 0,
            "rejectionsByReason": {},
            "batchJobName": "",
            "batchFinalState": "NOT_SUBMITTED",
            "elapsedSeconds": 0.0,
        },
        "writebackEnvelope": None,
        "candidates": [],
        "failedTrajectories": [],
        "error": {"code": code, "message": message},
    }


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
            "attemptId": "",
            "masterSeed": master_seed,
            "kApproved": K_approved,
            "kPrime": 0,
            "droppedCount": K_approved,
            "taskCount": 0,
            "completedTaskCount": 0,
            "incompleteTaskIndices": [],
            "mismatchedAttemptTaskIndices": [],
            "totalAttempts": 0,
            "rejectionsByReason": {},
            "batchJobName": "",
            "batchFinalState": "NOT_SUBMITTED",
            "elapsedSeconds": 0.0,
        },
        "writebackEnvelope": None,
        "candidates": [],
        "failedTrajectories": [],
        "error": {"code": code, "message": message},
    }
