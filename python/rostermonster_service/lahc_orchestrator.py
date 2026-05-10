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
import uuid
from typing import Any, Callable

from rostermonster.domain import AssignmentUnit
from rostermonster.parser import Consumability, parse
from rostermonster.pipeline import _assemble_writeback_wrapper, _snapshot_from_dict
from rostermonster.scorer import ScoringConfig, score
from rostermonster.selector import (
    AllocationResult,
    LahcParamsRecord,
    LahcStrategyConfig,
    RetentionMode,
    RunEnvelope,
    ScoredCandidateSet,
    ScoredTrialCandidate,
    select,
)
from rostermonster.solver import (
    STRATEGY_LAHC,
    CandidateSet,
    LahcParams,
    SearchDiagnostics,
    TrialCandidate,
    derive_K_seeds,
)
from rostermonster.templates import icu_hd_template_artifact
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
from rostermonster_service.gcs import (
    DeletePrefixFn,
    ReadJsonFn,
    WriteJsonFn,
)


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
    expected_attempt_id: str,
    gcs_read_json: ReadJsonFn,
) -> dict[str, Any]:
    """Read per-task `result.json` files from GCS and aggregate.
    Missing / unreadable results contribute 0 candidates per §8.7's
    primary K' definition; they're counted in `incomplete_task_indices`
    so the response surfaces which tasks contributed nothing.

    Validates each result.json's `attemptId` against the
    `expected_attempt_id` per the §8.7 concurrent-replay race fix
    (T2G): a result.json with a mismatched / missing attemptId belongs
    to a different attempt at the same runId prefix and MUST NOT
    contribute candidates to this attempt's K'. Mismatches are counted
    in `mismatched_attempt_task_indices` for diagnostics + treated the
    same as missing results.
    """
    candidates: list[dict] = []
    failed_trajectories: list[dict] = []
    trajectory_exceptions: list[dict] = []
    aggregate_attempts = 0
    aggregate_rejections: dict[str, int] = {}
    completed_task_indices: list[int] = []
    incomplete_task_indices: list[int] = []
    mismatched_attempt_task_indices: list[int] = []
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

        # §8.7 attemptId validation per the T2G concurrent-replay race
        # fix: a result.json from a different attempt (or pre-T2G with
        # no attemptId) at the same runId prefix MUST NOT contribute
        # to this attempt's K'.
        result_attempt_id = result.get("attemptId")
        if result_attempt_id != expected_attempt_id:
            log.warning(
                "Task %d result.json has attemptId=%r; expected %r — "
                "treating as missing (stale from a prior attempt)",
                task_index, result_attempt_id, expected_attempt_id,
            )
            per_task_results.append(None)
            incomplete_task_indices.append(task_index)
            mismatched_attempt_task_indices.append(task_index)
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
        "mismatchedAttemptTaskIndices": mismatched_attempt_task_indices,
        "perTaskResults": per_task_results,
    }


def _assignment_unit_from_dict(d: dict) -> AssignmentUnit:
    """Inverse of `_to_jsonable(AssignmentUnit)` — rebuilds an
    `AssignmentUnit` from the worker's serialized dict form so the
    orchestrator's downstream scorer/selector can consume it."""
    return AssignmentUnit(
        dateKey=d["dateKey"],
        slotType=d["slotType"],
        unitIndex=int(d["unitIndex"]),
        doctorId=d["doctorId"],
    )


def _build_post_aggregation_envelope(
    *,
    snapshot_dict: dict,
    agg: dict,
    master_seed: int,
    K_approved: int,
    run_id: str,
) -> dict | None:
    """T2G post-aggregation pipeline: take the K' candidates the orchestrator
    aggregated from per-task result.json files + run them through the
    standard scorer → selector → wrapper-envelope chain (matching what
    `pipeline.run_pipeline()` does for the local CLI path) so the
    `/compute-lahc-test` route returns the same `writebackEnvelope` shape
    as the existing `POST /compute` route.

    Returns the wrapper envelope dict, or `None` if K' == 0 (caller
    should surface UNSATISFIED state without a wrapper). The orchestrator
    stays the only post-T2D module that consumes the scorer/selector
    surface for the LAHC path; worker stays scoring-blind end-to-end per
    `docs/solver_contract.md` §9 / §11.
    """
    candidates_raw = agg["candidates"]
    if not candidates_raw:
        return None

    # Re-parse snapshot. Worker also did this per-task, but the
    # orchestrator needs its own NormalizedModel + ScoringConfig to
    # score candidates + run selector. Cost is one parse on the
    # operator-response wall (~50ms for K=104 at production scale,
    # ~5ms per `tests/test_pipeline.py` measurements) — acceptable
    # vs the alternative of serializing model state through GCS.
    #
    # Defensive guard: in production the route validates the snapshot
    # shape before invoking the orchestrator, so `_snapshot_from_dict`
    # always succeeds. Test scenarios that use synthetic minimal
    # snapshots (e.g., `{"metadata": {"snapshotId": "x"}}`) for
    # aggregation testing get `wrapperEnvelope=None` instead of a
    # raised exception — the wrapper assembly is opportunistic post-
    # aggregation, not a contract guarantee on every orchestrator path.
    try:
        snapshot = _snapshot_from_dict(snapshot_dict)
    except (KeyError, TypeError, ValueError) as e:
        log.warning(
            "Snapshot deserialization failed in post-aggregation "
            "(%s: %s); returning no wrapper envelope",
            type(e).__name__, e,
        )
        return None
    template = icu_hd_template_artifact()
    parser_result = parse(snapshot, template)
    if parser_result.consumability is not Consumability.CONSUMABLE:
        # Orchestrator's parse rejected the snapshot post-Batch — this
        # shouldn't happen unless the snapshot mutated mid-flight (which
        # it can't, since we wrote it to GCS at orchestration entry).
        # Fail fast rather than silently drop the wrapper.
        log.error(
            "Orchestrator parse rejected snapshot post-Batch: %d issues",
            len(parser_result.issues),
        )
        return None

    model = parser_result.normalizedModel
    scoring_config = (parser_result.scoringConfig
                      or ScoringConfig.first_release_defaults(model))

    # Reconstruct CandidateSet from agg["candidates"]. Each candidate's
    # assignments came from the worker as JSON dicts; convert back to
    # AssignmentUnit objects so the scorer/selector can consume them.
    # `candidateId` is 1-indexed dense per `docs/selector_contract.md`
    # §16; the orchestrator's emission order = aggregation order across
    # tasks (task-0 candidates first, then task-1, ...).
    trial_candidates = tuple(
        TrialCandidate(
            candidateId=i + 1,
            assignments=tuple(
                _assignment_unit_from_dict(a) for a in cand["assignments"]
            ),
        )
        for i, cand in enumerate(candidates_raw)
    )

    # Build SearchDiagnostics. Per `docs/solver_contract.md` §12A.9, the
    # per-trajectory arrays MUST have an entry for EVERY trajectory the
    # solver attempted, with `0` / `None` for `SEED_FAILED` entries.
    # Walk the original (task_index, candidate_seed) emission order so
    # the arrays are flattened in the same order the local-CLI's
    # `solve()` produces — this is the §12A.9 invariant the analyzer +
    # writeback consumers depend on.
    #
    # Missing tasks (no result.json on aggregation) contribute no
    # per-trajectory entries; this is a Cloud-Batch-specific gap with
    # no local-CLI analog. Operators see those tasks counted in
    # `lahcSummary.incompleteTaskIndices` instead.
    candidate_lookup = {
        (c["taskIndex"], c["candidateSeed"]): c
        for c in candidates_raw
    }
    failed_lookup = {
        (f["taskIndex"], f["candidateSeed"]): f
        for f in agg["failedTrajectories"]
    }
    all_seeds = derive_K_seeds(master_seed, K_approved)
    # Local re-import to avoid circular: _partition_seeds is module-level.
    per_task_seeds = _partition_seeds(all_seeds)
    per_traj_status_list: list[str] = []
    per_traj_iters_list: list[int] = []
    per_traj_accepted_list: list[int] = []
    per_traj_best_list: list[float | None] = []
    per_traj_terminal_list: list[float | None] = []
    for t_idx, t_seeds in enumerate(per_task_seeds):
        for seed in t_seeds:
            key = (t_idx, seed)
            if key in candidate_lookup:
                c = candidate_lookup[key]
                per_traj_status_list.append("SUCCEEDED")
                per_traj_iters_list.append(int(c["iters"]))
                per_traj_accepted_list.append(int(c["acceptedMoves"]))
                per_traj_best_list.append(c["bestScore"])
                per_traj_terminal_list.append(c["terminalScore"])
            elif key in failed_lookup:
                per_traj_status_list.append("SEED_FAILED")
                per_traj_iters_list.append(0)
                per_traj_accepted_list.append(0)
                per_traj_best_list.append(None)
                per_traj_terminal_list.append(None)
            # else: missing task — no per-trajectory entry recorded;
            # surfaces via `lahcSummary.incompleteTaskIndices`.
    per_traj_status = tuple(per_traj_status_list)
    per_traj_iters = tuple(per_traj_iters_list)
    per_traj_accepted = tuple(per_traj_accepted_list)
    per_traj_best = tuple(per_traj_best_list)
    per_traj_terminal = tuple(per_traj_terminal_list)

    diagnostics = SearchDiagnostics(
        strategyId=STRATEGY_LAHC,
        fillOrderPolicy="MOST_CONSTRAINED_FIRST",
        # cr_floor + crFloorMode aren't recoverable from per-task
        # result.json (worker doesn't write them). Use the SMART_MEDIAN
        # default — matches what worker computed internally per
        # `docs/solver_contract.md` §13.1. Re-deriving the exact value
        # locally would require the same compute_cr_floor call the
        # worker did; for T2G's wrapper-envelope shape this is
        # sufficient (operator-facing diagnostics surface other LAHC
        # fields more prominently).
        crFloorMode="SMART_MEDIAN",
        crFloorComputed=0,
        seed=master_seed,
        placementAttempts=int(agg["aggregateAttempts"]),
        ruleEngineRejectionsByReason=dict(agg["aggregateRejectionsByReason"]),
        candidateEmitCount=len(trial_candidates),
        unfilledDemandCount=0,
        lahcHistoryListLength=50,   # FW-0037 elbow tuple per worker.py
        lahcMaxIters=None,
        lahcIdleThreshold=3500,
        lahcSwapProbability=0.5,
        seedDerivationFunction="python.Random.getrandbits.candidate_seed",
        perTrajectoryStatus=per_traj_status,
        perTrajectoryIters=per_traj_iters,
        perTrajectoryAcceptedMoves=per_traj_accepted,
        perTrajectoryBestScore=per_traj_best,
        perTrajectoryTerminalScore=per_traj_terminal,
    )
    candidate_set = CandidateSet(
        candidates=trial_candidates,
        diagnostics=diagnostics,
    )

    # Score each candidate and assemble ScoredCandidateSet (mirrors
    # pipeline.run_pipeline()'s post-solve step).
    scored = ScoredCandidateSet(
        candidates=tuple(
            ScoredTrialCandidate(
                candidate=cand,
                score=score(cand.assignments, model, scoring_config),
            )
            for cand in candidate_set.candidates
        ),
        diagnostics=diagnostics,
    )

    # Build RunEnvelope mirroring pipeline._build_run_envelope's LAHC
    # branch. The orchestrator's run_id is per-call unique (encodes
    # snapshotId + masterSeed + content hash); the standard runEnvelope
    # uses `snapshot.metadata.snapshotId`, but for the cloud-LAHC path
    # surfacing the orchestrator's runId in the envelope keeps GCS
    # forensic replay traceable from the writeback artifact.
    md = snapshot.metadata
    run_envelope = RunEnvelope(
        runId=run_id,
        snapshotRef=md.snapshotId,
        configRef="first_release_defaults",
        seed=master_seed,
        fillOrderPolicy="MOST_CONSTRAINED_FIRST",
        crFloorMode="SMART_MEDIAN",
        crFloorComputed=0,
        generationTimestamp=md.generationTimestamp,
        sourceSpreadsheetId=md.sourceSpreadsheetId,
        sourceTabName=md.sourceTabName,
        solverStrategy=STRATEGY_LAHC,
        solverStrategyConfig=LahcStrategyConfig(
            lahcParams=LahcParamsRecord(
                historyListLength=50,
                idleThreshold=3500,
                maxIters=LahcParams().maxIters,
                swapProbability=0.5,
            ),
        ),
    )

    # Select the winner + assemble FinalResultEnvelope.
    envelope = select(
        scored,
        retentionMode=RetentionMode.BEST_ONLY,
        runEnvelope=run_envelope,
    )

    if not isinstance(envelope.result, AllocationResult):
        # Selector returned the failure-branch shape (e.g., zero scored
        # candidates after filtering). Treat as no-wrapper.
        log.warning(
            "Selector failure-branch envelope returned with K'=%d; "
            "no wrapper envelope produced",
            len(trial_candidates),
        )
        return None

    return _assemble_writeback_wrapper(envelope, snapshot, template)


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

    # Per-attempt unique ID for the §8.7 concurrent-replay race fix
    # (T2G). Stamped into every per-task seeds.json; worker echoes
    # back into result.json; aggregation validates on read so a
    # concurrent attempt at the same runId can't pollute this
    # attempt's K' aggregation.
    attempt_id = attempt_id_fn()

    # --- Seed pre-derivation + partition -----------------------------
    all_seeds = derive_K_seeds(master_seed, K_approved)
    per_task_seeds = _partition_seeds(all_seeds)
    task_count = len(per_task_seeds)
    # Sanity: should match T2E's task_count_for_K.
    assert task_count == task_count_for_K(K_approved), (
        "partition produced " + str(task_count)
        + " tasks; task_count_for_K(K) = " + str(task_count_for_K(K_approved))
    )

    # --- Invalidate stale artifacts from a prior replay attempt -------
    # The runId is intentionally deterministic per (snapshotId, masterSeed)
    # so forensic replay is idempotent at the artifact-prefix level —
    # but Batch job_id is per-call unique (a replay submits a fresh
    # Batch job, not the same one). Without this clear step, a partial-
    # failure on a replay would silently inherit stale per-task
    # result.json files from the prior attempt at the same runId
    # prefix, inflating K' with rosters that didn't come from this
    # attempt. Codex P1 finding on PR #143.
    #
    # `gcs_delete_prefix` is REQUIRED (no default) so production callers
    # cannot silently skip the clear. Tests that exercise aggregation
    # in isolation (pre-seeding result.jsons before calling this
    # function) opt into a no-op delete fn explicitly with a comment.
    prefix_uri = _gcs_uri(bucket, run_id) + "/"
    deleted_count = gcs_delete_prefix(prefix_uri)
    if deleted_count:
        log.info(
            "Cleared %d stale artifacts at %s before fresh attempt",
            deleted_count, prefix_uri,
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
            "attemptId": attempt_id,
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
        "taskCount": task_count,
        "completedTaskCount": len(agg["completedTaskIndices"]),
        "incompleteTaskIndices": agg["incompleteTaskIndices"],
        "mismatchedAttemptTaskIndices": agg["mismatchedAttemptTaskIndices"],
        "totalAttempts": agg["aggregateAttempts"],
        "rejectionsByReason": agg["aggregateRejectionsByReason"],
        "batchJobName": job_name,
        "batchFinalState": final_state,
        "elapsedSeconds": round(elapsed, 3),
    }

    # T2G: post-aggregation pipeline — score K' candidates, run
    # selector, build wrapper envelope so the route returns the same
    # shape as POST /compute. None when K'==0 (UNSATISFIED).
    wrapper_envelope = _build_post_aggregation_envelope(
        snapshot_dict=snapshot_dict,
        agg=agg,
        master_seed=master_seed,
        K_approved=K_approved,
        run_id=run_id,
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
