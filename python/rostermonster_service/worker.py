"""Cloud Batch worker for the M7 LAHC parallel-solver path per
`docs/cloud_compute_contract.md` §8.7.

**Amended at M7 C4 T2A.1 (2026-05-12) per the Codex P1.7 single-VM
amendment locked in PR #147 + the M7 C4 Task 1 plan in PR #148:**
collapsed from per-task worker on `c3-highcpu-8` (Pool of 8 trajectories,
seeds slice read from per-task `seeds.json`) to single-VM worker on
`c3-highcpu-88` (Pool of K_approved=88 trajectories, all seeds derived
locally from `RM_MASTER_SEED` env). Cloud Batch v1's `Job.taskGroups[]`
is limited to one task group (Codex P1.7 finding) — workers + finalizer
must run on one VM in one Python process. The inline finalize step
lands at M7 C4 T2A.2; this PR (T2A.1) keeps the result.json output
schema so `/compute-lahc-test` continues to work end-to-end via the
existing M7 C2 orchestrator polling path.

Single-image dispatch: the same container that Cloud Run runs as a Flask
service (`gunicorn rostermonster_service.app:app`) is invoked by Cloud
Batch with the command override `python -m rostermonster_service.worker
--run-id <runId>` so the Batch task starts in worker mode. The
`taskSpec.runnables[0].container.commands[]` array on the Batch job spec
(set by `batch_job_spec.py`) carries the override; the single-image
discipline preserves the D-0050 dual-track guarantee that both surfaces
run the same Python compute core.

Input contract:
  gs://rostermonsterv2-lahc/{runId}/snapshot.json   # input snapshot (orchestrator-written)
  RM_MASTER_SEED env var                            # §9 input #3 master seed
  RM_K_APPROVED env var                             # K trajectories (default 88)

  NOTE: per-task `seeds.json` is RETIRED under single-task — the worker
  derives K seeds locally via `derive_K_seeds(masterSeed, K)` per
  §12A.10 (single source of truth shared with the local-CLI K-trajectory
  loop). The orchestrator no longer pre-derives or partitions seeds.

Output contract:
  gs://rostermonsterv2-lahc/{runId}/result.json   # this worker's output (single-task)

Per-task `result.json` schema (this worker writes, T2A.1 orchestrator
aggregates; T2A.2 will move aggregation into this worker inline):
```
{
  "schemaVersion": 1,
  "runId": "<runId>",
  "masterSeed": <int>,
  "kApproved": <int>,
  "candidates": [
    {
      "candidateSeed": <int>,
      "assignments": [...],
      "iters": <int>,
      "acceptedMoves": <int>,
      "bestScore": <float | null>,
      "terminalScore": <float | null>
    },
    ...
  ],
  "failedTrajectories": [
    {
      "candidateSeed": <int>,
      "unfilledDemand": [...]
    },
    ...
  ],
  "aggregateAttempts": <int>,
  "aggregateRejectionsByReason": {<code>: <int>}
}
```

K' = `len(result.json["candidates"])` directly (no cross-task summation
under single-task pattern).

Determinism (§12A.4 + §12A.10): each pool child calls `solve(K=1,
_candidate_seeds=[its_one_seed], strategyId=LAHC, ...)` per the M7 C2
Task 2C escape hatch; the worker derives all K seeds via
`derive_K_seeds(masterSeed, K)` so the per-trajectory seed list is
byte-identical to the local CLI's K-trajectory loop.

Env vars plumbed at T2A.1 but unused until T2A.2's inline finalize step:
- `RM_OPERATOR_EMAIL`: operator's email address (T2A.2 finalize uses
  this to populate the callback POST body).
- `RM_LAUNCHER_CALLBACK_URL`: launcher's USER_DEPLOYING callback URL
  (T2A.2 finalize POSTs to this; empty for `/compute-lahc-test` skips
  the POST).
- `RM_SUBMIT_TIMESTAMP_MS`: epoch ms at submitJob time (T2A.2 finalize
  reads this for the 510s elapsed self-check).
"""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable

from rostermonster.analysis import analyze
from rostermonster.analysis.output import render_analyzer_output_json
from rostermonster.parser import Consumability, parse
from rostermonster.pipeline import _snapshot_from_dict, _to_jsonable
from rostermonster.rule_engine import evaluate as rule_engine_evaluate
from rostermonster.scorer import ScoringConfig
from rostermonster.solver import (
    STRATEGY_LAHC,
    CandidateSet,
    LahcParams,
    TerminationBounds,
    UnsatisfiedResult,
    derive_K_seeds,
    solve,
)
from rostermonster.templates import icu_hd_template_artifact
from rostermonster_service.gcs import (
    ReadJsonFn,
    WriteJsonFn,
    make_gcs_adapter,
)
from rostermonster_service.post_aggregation import (
    build_full_sidecar_dict,
    build_post_aggregation_envelope,
)


log = logging.getLogger("rostermonster_service.worker")

# §8.7 GCS bucket holding all M7 LAHC run artifacts. Override via env for
# tests / dev — production reads the canonical bucket every time.
_BUCKET_ENV = "LAHC_BUCKET"
_DEFAULT_BUCKET = "rostermonsterv2-lahc"

# §8.7 single-VM dense-pack inputs (Codex P1.7 amendment). Master seed
# + K are env-plumbed by the orchestrator so the worker derives all K
# trajectory seeds locally via derive_K_seeds() per §12A.10 — no
# per-task seeds.json file under single-task.
_MASTER_SEED_ENV = "RM_MASTER_SEED"
_K_APPROVED_ENV = "RM_K_APPROVED"
# Per-attempt id stamped by the orchestrator into the Batch job env;
# echoed by the worker into result.json so the orchestrator can validate
# on read that result.json belongs to THIS attempt (Codex P2 round 2
# finding 4 fix — re-introduced after T2A.1's initial drop, since two
# concurrent /compute-lahc-test replays of the same (snapshotId,
# masterSeed) produce the same deterministic runId and would otherwise
# collide on result.json overwrites). Stays empty for callers that
# don't need replay-collision protection.
_ATTEMPT_ID_ENV = "RM_ATTEMPT_ID"

# §8.7 + §10A inline finalize step inputs (M7 C4 T2A.2 PR-A). Plumbed by
# the orchestrator via the Cloud Batch task env; the finalize step reads
# them to drive the callback POST per `docs/cloud_compute_contract.md`
# §10A.5 / §10A.6 / §10A.7. Empty strings on any of these short-circuit
# the callback POST (test-path fallback + maintainer `/compute-lahc-test`
# back-compat per D-0071 sub-decision 14).
_OPERATOR_EMAIL_ENV = "RM_OPERATOR_EMAIL"
_LAUNCHER_CALLBACK_URL_ENV = "RM_LAUNCHER_CALLBACK_URL"
_SUBMIT_TIMESTAMP_MS_ENV = "RM_SUBMIT_TIMESTAMP_MS"

# §8.7 finalize-step self-check threshold (D-0071 sub-decision 7 + Codex
# P1 round 10 + P2 round 12 amendments). 510s reserves ~90s for the
# finalize step's aggregate + score + select + analyzer + callback POST +
# email so OPERATOR-FACING total wall stays ≤ 600s / 10-min cap. Don't
# raise to 600s without also rebudgeting the finalize step — pre-P2-12
# was 600s and could blow operator wall to ~650-680s when Pool finished
# at 590s.
_FINALIZE_SELF_CHECK_THRESHOLD_MS = 510_000

# §10A.7 retry behavior for the callback POST. 3 retries with
# exponential backoff (2s, 4s, 8s) per D-0071 sub-decision 10. Total
# worst-case wall for the POST + retry chain: ~16s + 3 × HTTP timeout.
_CALLBACK_POST_RETRY_COUNT = 3
_CALLBACK_POST_BACKOFF_SECONDS = (2.0, 4.0, 8.0)

# §10A.6 callback envelope schemaVersion. Separate from §11 contract
# version (governs §9 + §10 boundary) per the §10A.8 versioning note.
_CALLBACK_SCHEMA_VERSION = 1

# `docs/analysis_contract.md` topK default — `pipeline.run_pipeline` uses
# this; the inline finalize mirrors it for byte-identity on the
# operator-facing AnalyzerOutput surface. Override via env for maintainer
# experiments; production stays at the default.
_ANALYZER_TOP_K_ENV = "RM_ANALYZER_TOP_K"
_DEFAULT_ANALYZER_TOP_K = 5

# §8.7 single-VM dense-pack default K (Codex P1.7 amendment). M7
# production = K=88 (c3-highcpu-88 within current C3_CPUS=108 quota);
# future quota bump → K=176 via FW-0040.
_DEFAULT_K_APPROVED = 88

# FW-0037 elbow tuple — M7 production LAHC parameters per
# `docs/delivery_plan.md` §9 + the M7 architecture lock at D-0070.
# Hardcoded here because the worker is the M7-specific surface; tunable
# LAHC defaults for other surfaces remain in `LahcParams()`.
_LAHC_HISTORY_LIST_LENGTH = 50
_LAHC_IDLE_THRESHOLD = 3500
_LAHC_SWAP_PROBABILITY = 0.5

# Result.json schema version per the §8.7 amendment. Bump if the result
# shape changes in a way that breaks the orchestrator's aggregation.
_RESULT_SCHEMA_VERSION = 1


# I/O ports — `ReadJsonFn` + `WriteJsonFn` come from `gcs.py` (shared
# with the M7 C2 Task 2F orchestrator). `PoolExecutorFn` is worker-only.
# `pool_executor(fn, args_iter) -> list` — defaults to multiprocessing.Pool;
# tests pass a serial executor to keep test time bounded + avoid spawn issues.
PoolExecutorFn = Callable[[Callable[..., Any], list[Any]], list[Any]]


def _gcs_uri(bucket: str, run_id: str, *parts: str) -> str:
    """Build a `gs://bucket/runId/...` URI deterministically per §8.7."""
    return "gs://" + bucket + "/" + "/".join((run_id, *parts))


def _run_one_trajectory(args: tuple) -> dict:
    """Pool worker — runs one LAHC trajectory under the FW-0037 elbow tuple
    via `solve(K=1, _candidate_seeds=[seed])` per the M7 C2 Task 2C escape
    hatch.

    Lives at module top-level so `multiprocessing.Pool.map` can pickle it.
    Returns a dict (also picklable) carrying either the SUCCEEDED candidate
    or the SEED_FAILED unfilled demand, plus aggregate attempt + rejection
    counters for the per-task aggregation.

    Per-trajectory exceptions are caught + surfaced as a third state
    (`status="EXCEPTION"`) so a single child raising doesn't lose the
    other trajectories' results. Per §12A.8's drop-and-continue
    discipline: each trajectory is independent; one failure doesn't fail
    the whole task.
    """
    model, scoring_config, lahc_params, master_seed, candidate_seed = args
    try:
        result = solve(
            model,
            ruleEngine=rule_engine_evaluate,
            seed=master_seed,
            terminationBounds=TerminationBounds(maxCandidates=1),
            strategyId=STRATEGY_LAHC,
            scoringConfig=scoring_config,
            lahcParams=lahc_params,
            _candidate_seeds=[candidate_seed],
        )
    except Exception as e:
        log.exception(
            "Trajectory raised for candidate_seed=%s; surfacing as EXCEPTION",
            candidate_seed,
        )
        return {
            "status": "EXCEPTION",
            "candidateSeed": candidate_seed,
            "exceptionType": type(e).__name__,
            "exceptionMessage": str(e),
        }

    if isinstance(result, CandidateSet):
        # SUCCEEDED — exactly one candidate per K=1 LAHC call.
        cand = result.candidates[0]
        diag = result.diagnostics
        return {
            "status": "SUCCEEDED",
            "candidateSeed": candidate_seed,
            "assignments": _to_jsonable(cand.assignments),
            # §12A.9 per-trajectory diagnostics — single-trajectory tuples
            # have one element each; pull it out so the per-task aggregator
            # gets flat fields per candidate.
            "iters": int(diag.perTrajectoryIters[0])
                if diag.perTrajectoryIters else 0,
            "acceptedMoves": int(diag.perTrajectoryAcceptedMoves[0])
                if diag.perTrajectoryAcceptedMoves else 0,
            "bestScore": diag.perTrajectoryBestScore[0]
                if diag.perTrajectoryBestScore else None,
            "terminalScore": diag.perTrajectoryTerminalScore[0]
                if diag.perTrajectoryTerminalScore else None,
            "placementAttempts": int(diag.placementAttempts),
            "rejectionsByReason": dict(diag.ruleEngineRejectionsByReason),
        }

    assert isinstance(result, UnsatisfiedResult)
    # SEED_FAILED — single-trajectory LAHC returned UnsatisfiedResult means
    # the only trajectory dropped on per-trajectory seed-construction
    # failure per §12A.8.
    return {
        "status": "SEED_FAILED",
        "candidateSeed": candidate_seed,
        "unfilledDemand": _to_jsonable(result.unfilledDemand),
        "placementAttempts": int(result.diagnostics.placementAttempts),
        "rejectionsByReason": dict(result.diagnostics.ruleEngineRejectionsByReason),
    }


def _default_pool_executor_factory(pool_size: int) -> PoolExecutorFn:
    """Production pool executor factory — builds an executor at the requested
    Pool size matching the §8.7 single-VM dense-pack invariant (1 trajectory
    per vCPU on `c3-highcpu-88` = K=88). Tests inject a serial executor to
    keep test time bounded and sidestep multiprocessing spawn semantics in
    CI."""
    def _exec(fn: Callable[..., Any], args_iter: list[Any]) -> list[Any]:
        with multiprocessing.Pool(pool_size) as pool:
            return pool.map(fn, args_iter)
    return _exec


# I/O ports for the inline finalize step (M7 C4 T2A.2 PR-A). Injectable
# so tests can exercise the callback POST path without making real HTTPS
# calls or hitting the metadata server.
HttpPostFn = Callable[[str, dict[str, Any], float], int]
"""HTTP POST adapter — `(url, body_dict, timeout_seconds) -> status_code`.
Implementations MUST raise on transport / connection errors so the retry
loop in `_post_callback_with_retry` can backoff; returning a 5xx is
treated as retryable (same backoff), returning a 4xx is terminal."""
IdTokenFn = Callable[[str], str]
"""ID token minter — `(audience_url) -> id_token_string`. Production
hits the Cloud Batch VM's metadata server at `instance/service-accounts/
default/identity?audience=<url>&format=full` per §10A.5; tests inject a
fake that returns a sentinel string."""
WallTimeFn = Callable[[], float]
"""Wall-clock seconds since epoch — `time.time` in production, fixed
value in tests. Used for the §8.7 510s self-check + the diagnostics
`wallTimeSeconds` field."""


def worker_main(
    run_id: str,
    *,
    master_seed: int,
    K_approved: int,
    read_json: ReadJsonFn,
    write_json: WriteJsonFn,
    pool_executor: PoolExecutorFn | None = None,
    bucket: str = _DEFAULT_BUCKET,
    attempt_id: str = "",
    # --- M7 C4 T2A.2 PR-A: inline finalize step ports ------------------
    # Empty strings on callback_url / operator_email short-circuit the
    # POST (test path + maintainer `/compute-lahc-test` back-compat per
    # D-0071 sub-decision 14). submit_timestamp_ms_str carries the
    # epoch-ms front-door submitJob time for the §8.7 510s self-check;
    # empty defaults to "0" which makes the self-check vacuously pass.
    callback_url: str = "",
    operator_email: str = "",
    submit_timestamp_ms_str: str = "",
    batch_job_name: str = "",
    analyzer_top_k: int = _DEFAULT_ANALYZER_TOP_K,
    http_post_fn: HttpPostFn | None = None,
    id_token_fn: IdTokenFn | None = None,
    wall_time_fn: WallTimeFn = time.time,
    generated_at_fn: Callable[[], str] = lambda: datetime.now(tz=timezone.utc).isoformat(),
) -> dict:
    """Worker entry point — orchestrates the read → compute → write →
    finalize cycle for the single Cloud Batch task. Returns the
    result.json dict (also written to GCS at the §8.7 result key).

    All I/O ports are injected so tests exercise the full pipeline against
    an in-memory storage fixture without touching real GCS or HTTPS.

    Snapshot deserialization or parser-rejection surfaces in the
    result.json's `parserRejection` field (NOT raised) — the orchestrator's
    aggregation per §8.7 partial-failure tolerance treats this the same
    as a worker error-state (0 candidates contributed); the finalize step
    is SKIPPED on that path (no candidates to score).

    **Amended at M7 C4 T2A.1**: seeds are derived locally from `master_seed`
    + `K_approved` via `derive_K_seeds()`; the per-task `seeds.json` GCS
    read is RETIRED (single-task pattern). Pool size defaults to K_approved
    (production: 88).

    **Amended at M7 C4 T2A.2 PR-A**: inline finalize step runs AFTER the
    Pool aggregation completes. Reads `RM_OPERATOR_EMAIL` /
    `RM_LAUNCHER_CALLBACK_URL` / `RM_SUBMIT_TIMESTAMP_MS` env vars (or
    function kwargs for tests); does the 510s self-check; runs aggregate
    + score + select + analyzer + POST callback per §10A. Skips the POST
    when `callback_url` is empty (test-path + maintainer
    `/compute-lahc-test` back-compat per D-0071 sub-decision 14).
    """
    snapshot_uri = _gcs_uri(bucket, run_id, "snapshot.json")
    result_uri = _gcs_uri(bucket, run_id, "result.json")

    if pool_executor is None:
        pool_executor = _default_pool_executor_factory(K_approved)

    # --- Derive trajectory seeds locally (§12A.10) ---------------------
    # Single source of truth shared with the local-CLI K-trajectory loop.
    # Negative seeds are handled by derive_K_seeds via _UINT64_MASK per
    # §12A.10; byte-identity holds for positive AND negative master seeds.
    candidate_seeds = derive_K_seeds(master_seed, K_approved)

    # --- Load input snapshot ------------------------------------------
    snapshot_dict = read_json(snapshot_uri)

    # --- Parse snapshot -----------------------------------------------
    snapshot = _snapshot_from_dict(snapshot_dict)
    template = icu_hd_template_artifact()
    parser_result = parse(snapshot, template)
    if parser_result.consumability is not Consumability.CONSUMABLE:
        # Parser rejected the snapshot. Worker can't run; emit a result
        # the orchestrator can aggregate (0 candidates contributed).
        result = _build_parser_failure_result(
            run_id=run_id,
            master_seed=master_seed,
            K_approved=K_approved,
            attempt_id=attempt_id,
            parser_issues=parser_result.issues,
        )
        write_json(result_uri, result)
        return result

    model = parser_result.normalizedModel
    scoring_config = (parser_result.scoringConfig
                      or ScoringConfig.first_release_defaults(model))
    lahc_params = LahcParams(
        historyListLength=_LAHC_HISTORY_LIST_LENGTH,
        idleThreshold=_LAHC_IDLE_THRESHOLD,
        swapProbability=_LAHC_SWAP_PROBABILITY,
    )

    # --- Run trajectories in parallel ----------------------------------
    args_list = [
        (model, scoring_config, lahc_params, master_seed, int(s))
        for s in candidate_seeds
    ]
    per_trajectory = pool_executor(_run_one_trajectory, args_list)

    # --- Aggregate result ----------------------------------------------
    candidates: list[dict] = []
    failed: list[dict] = []
    exceptions: list[dict] = []
    aggregate_attempts = 0
    aggregate_rejections: dict[str, int] = {}

    for entry in per_trajectory:
        if "placementAttempts" in entry:
            aggregate_attempts += int(entry["placementAttempts"])
        for code, count in entry.get("rejectionsByReason", {}).items():
            aggregate_rejections[code] = aggregate_rejections.get(code, 0) + int(count)

        status = entry["status"]
        if status == "SUCCEEDED":
            candidates.append({
                "candidateSeed": entry["candidateSeed"],
                "assignments": entry["assignments"],
                "iters": entry["iters"],
                "acceptedMoves": entry["acceptedMoves"],
                "bestScore": entry["bestScore"],
                "terminalScore": entry["terminalScore"],
            })
        elif status == "SEED_FAILED":
            failed.append({
                "candidateSeed": entry["candidateSeed"],
                "unfilledDemand": entry["unfilledDemand"],
            })
        elif status == "EXCEPTION":
            exceptions.append({
                "candidateSeed": entry["candidateSeed"],
                "exceptionType": entry["exceptionType"],
                "exceptionMessage": entry["exceptionMessage"],
            })

    result: dict[str, Any] = {
        "schemaVersion": _RESULT_SCHEMA_VERSION,
        "runId": run_id,
        "masterSeed": master_seed,
        "kApproved": K_approved,
        # attemptId echoed back so the orchestrator can validate on read
        # that result.json belongs to THIS attempt — closes the
        # concurrent-replay overwrite race per Codex P2 round 2 finding
        # 4. Empty string when caller didn't supply an attemptId (no
        # collision protection needed for that surface).
        "attemptId": attempt_id,
        "candidates": candidates,
        "failedTrajectories": failed,
        "aggregateAttempts": aggregate_attempts,
        "aggregateRejectionsByReason": aggregate_rejections,
    }
    # Only surface the exceptions block when non-empty so the common case
    # (all trajectories cleanly SUCCEEDED or SEED_FAILED) keeps the
    # result.json surface area minimal for orchestrator consumption.
    if exceptions:
        result["trajectoryExceptions"] = exceptions

    write_json(result_uri, result)

    # --- Inline finalize step (M7 C4 T2A.2 PR-A) -----------------------
    # Runs always after Pool aggregation per §8.7 + D-0071 sub-decision
    # 12 — no `SUCCEEDED_OR_FAILED` dependency mechanic (Cloud Batch v1
    # doesn't support it; single-task pattern makes this structural).
    # Best-effort discipline: finalize failures log + continue rather
    # than raise (the operator-facing path is the callback POST itself;
    # finalize-internal exceptions surface via callback `state` =
    # COMPUTE_ERROR per §10A.6 finding 9). When callback_url is empty
    # the entire callback POST is SKIPPED — that's the test-path +
    # maintainer `/compute-lahc-test` back-compat (D-0071 sub-decision
    # 14) where the orchestrator does the post-aggregation in its own
    # process from the GCS-written result.json.
    if callback_url:
        _inline_finalize(
            run_id=run_id,
            attempt_id=attempt_id,
            master_seed=master_seed,
            K_approved=K_approved,
            snapshot_dict=snapshot_dict,
            agg_result=result,
            callback_url=callback_url,
            operator_email=operator_email,
            submit_timestamp_ms_str=submit_timestamp_ms_str,
            batch_job_name=batch_job_name,
            analyzer_top_k=analyzer_top_k,
            http_post_fn=http_post_fn,
            id_token_fn=id_token_fn,
            wall_time_fn=wall_time_fn,
            generated_at_fn=generated_at_fn,
        )

    return result


def _inline_finalize(
    *,
    run_id: str,
    attempt_id: str,
    master_seed: int,
    K_approved: int,
    snapshot_dict: dict,
    agg_result: dict,
    callback_url: str,
    operator_email: str,
    submit_timestamp_ms_str: str,
    batch_job_name: str,
    analyzer_top_k: int,
    http_post_fn: HttpPostFn | None,
    id_token_fn: IdTokenFn | None,
    wall_time_fn: WallTimeFn,
    generated_at_fn: Callable[[], str],
) -> None:
    """Inline finalize step — runs in the same Python process as the
    Pool, after `Pool.close() + .join()` returns (under the §8.7 single-
    task pattern there's no separate finalizer task). Drives the
    aggregate + score + select + analyzer + POST callback chain per
    §10A.

    Best-effort discipline: this function MUST NOT raise. All internal
    exceptions are caught + surfaced via the callback POST's
    `state="COMPUTE_ERROR"` so the launcher can email the operator
    with the failure code per §10A.7. The only case where the operator
    doesn't get an email is when the callback POST itself fails after
    retries — that's the FW-0039 silent-outcome gap accepted-for-v1.

    Self-check at 510s elapsed since `RM_SUBMIT_TIMESTAMP_MS` per §8.7
    sub-decision 7 + Codex P2 round 12 fix — if the Pool ran long, the
    finalize step SKIPS aggregation/scoring/analyzer entirely and POSTs
    a TIMEOUT failure so the launcher can email the operator within the
    10-min cap.
    """
    finalize_started_at = wall_time_fn()

    # Default I/O fns (production callers don't need to inject).
    http_post = http_post_fn or _default_http_post_fn
    id_token = id_token_fn or _default_id_token_fn

    # --- 510s self-check (§8.7 + Codex P2 round 12 fix) ---------------
    # Skip aggregation when elapsed > 510s; POST timeout failure
    # immediately so the launcher emails the operator within the 600s
    # operator-facing cap.
    submit_ms = _parse_submit_timestamp_ms(submit_timestamp_ms_str)
    if submit_ms > 0:
        elapsed_ms = int(finalize_started_at * 1000) - submit_ms
        if elapsed_ms > _FINALIZE_SELF_CHECK_THRESHOLD_MS:
            log.warning(
                "Finalize self-check tripped: elapsed=%dms > threshold=%dms; "
                "skipping aggregation + POSTing timeout-failure callback",
                elapsed_ms, _FINALIZE_SELF_CHECK_THRESHOLD_MS,
            )
            timeout_body = _build_compute_error_callback_body(
                run_id=run_id,
                attempt_id=attempt_id,
                operator_email=operator_email,
                K_approved=K_approved,
                k_prime=0,
                wall_time_seconds=elapsed_ms / 1000.0,
                batch_job_name=batch_job_name,
                error_code="FINALIZE_TIMEOUT",
                error_message=(
                    "Finalize self-check tripped — Pool elapsed "
                    + str(elapsed_ms // 1000)
                    + "s exceeds 510s budget. The 10-min operator-"
                    "facing cap is governed by this self-check; the "
                    "Cloud Batch task itself is still within the 660s "
                    "safety net but the finalize step would have "
                    "blown the 600s cap had it run."
                ),
            )
            _post_callback_with_retry(
                callback_url=callback_url,
                body=timeout_body,
                run_id=run_id,
                attempt_id=attempt_id,
                id_token_fn=id_token,
                http_post_fn=http_post,
            )
            return

    # --- Aggregate + score + select + wrapper envelope ----------------
    # Reuse the shared post-aggregation helper (the same pipeline the
    # maintainer-test path goes through via the orchestrator). Catch
    # exceptions broadly — any failure here MUST surface via the
    # callback's COMPUTE_ERROR path rather than dropping the operator
    # into the FW-0039 silent-outcome gap.
    try:
        wrapper_envelope = build_post_aggregation_envelope(
            snapshot_dict=snapshot_dict,
            agg=_agg_to_post_aggregation_shape(agg_result),
            master_seed=master_seed,
            K_approved=K_approved,
            run_id=run_id,
        )
    except Exception as e:  # noqa: BLE001 — best-effort finalize discipline
        log.exception("Aggregation raised; surfacing as COMPUTE_ERROR callback")
        wall_time_seconds = wall_time_fn() - finalize_started_at
        if submit_ms > 0:
            wall_time_seconds = (
                int(wall_time_fn() * 1000) - submit_ms
            ) / 1000.0
        body = _build_compute_error_callback_body(
            run_id=run_id,
            attempt_id=attempt_id,
            operator_email=operator_email,
            K_approved=K_approved,
            k_prime=len(agg_result.get("candidates", [])),
            wall_time_seconds=wall_time_seconds,
            batch_job_name=batch_job_name,
            error_code="AGGREGATION_EXCEPTION",
            error_message=(
                type(e).__name__ + ": " + str(e)
            ),
        )
        _post_callback_with_retry(
            callback_url=callback_url,
            body=body,
            run_id=run_id,
            attempt_id=attempt_id,
            id_token_fn=id_token,
            http_post_fn=http_post,
        )
        return

    # --- State dispatch + analyzer ------------------------------------
    candidates = agg_result.get("candidates", [])
    k_prime = len(candidates)
    if k_prime > 0:
        state = "OK"
        try:
            analyzer_output_dict = _build_analyzer_output(
                snapshot_dict=snapshot_dict,
                wrapper_envelope=wrapper_envelope,
                agg_result=agg_result,
                master_seed=master_seed,
                K_approved=K_approved,
                run_id=run_id,
                top_k=analyzer_top_k,
                generated_at=generated_at_fn(),
            )
        except Exception as e:  # noqa: BLE001
            log.exception("Analyzer raised; surfacing as COMPUTE_ERROR callback")
            wall_time_seconds = (
                (int(wall_time_fn() * 1000) - submit_ms) / 1000.0
                if submit_ms > 0
                else wall_time_fn() - finalize_started_at
            )
            body = _build_compute_error_callback_body(
                run_id=run_id,
                attempt_id=attempt_id,
                operator_email=operator_email,
                K_approved=K_approved,
                k_prime=k_prime,
                wall_time_seconds=wall_time_seconds,
                batch_job_name=batch_job_name,
                error_code="ANALYZER_EXCEPTION",
                error_message=(
                    type(e).__name__ + ": " + str(e)
                ),
            )
            _post_callback_with_retry(
                callback_url=callback_url,
                body=body,
                run_id=run_id,
                attempt_id=attempt_id,
                id_token_fn=id_token,
                http_post_fn=http_post,
            )
            return
    else:
        # K' == 0 routes via UNSATISFIED per §12A.8 (NOT COMPUTE_ERROR)
        # — the snapshot's request set is unfeasible under the rule
        # engine, NOT a compute defect. The wrapper carries the
        # failure-branch envelope built by
        # `build_unsatisfied_from_aggregation` inside
        # `build_post_aggregation_envelope`.
        state = "UNSATISFIED"
        analyzer_output_dict = None

    # --- Build callback body + POST -----------------------------------
    wall_time_seconds = (
        (int(wall_time_fn() * 1000) - submit_ms) / 1000.0
        if submit_ms > 0
        else wall_time_fn() - finalize_started_at
    )
    body = _build_success_or_unsatisfied_callback_body(
        run_id=run_id,
        attempt_id=attempt_id,
        operator_email=operator_email,
        state=state,
        writeback_envelope=wrapper_envelope,
        analyzer_output=analyzer_output_dict,
        K_approved=K_approved,
        k_prime=k_prime,
        wall_time_seconds=wall_time_seconds,
        batch_job_name=batch_job_name,
    )

    try:
        _post_callback_with_retry(
            callback_url=callback_url,
            body=body,
            run_id=run_id,
            attempt_id=attempt_id,
            id_token_fn=id_token,
            http_post_fn=http_post,
        )
    except Exception:  # noqa: BLE001
        # _post_callback_with_retry already retries + logs on terminal
        # failures; this outer catch is defense-in-depth so any
        # surprise exception inside it never raises out of the
        # finalize step (worker.py contract: finalize MUST NOT raise).
        log.exception("Callback POST raised unexpectedly outside the retry loop")


def _agg_to_post_aggregation_shape(agg_result: dict) -> dict:
    """Coerce `worker_main`'s in-process aggregation result into the
    `agg` dict shape `post_aggregation.build_post_aggregation_envelope`
    expects (matches `lahc_orchestrator._aggregate_single_task_result`
    output shape so the helper is surface-agnostic).

    `worker_main` emits `candidates` / `failedTrajectories` /
    `trajectoryExceptions` without a `taskIndex` key per the §8.7
    single-task pattern — the post-aggregation helper expects
    `taskIndex: 0` on each entry. Stamp it here so the helper's lookup
    by `candidateSeed` keys work + the wrapper envelope's `taskIndex`-
    aware fields stay consistent with the orchestrator-test surface."""
    return {
        "candidates": [
            {"taskIndex": 0, **c} for c in agg_result.get("candidates", [])
        ],
        "failedTrajectories": [
            {"taskIndex": 0, **f}
            for f in agg_result.get("failedTrajectories", [])
        ],
        "trajectoryExceptions": [
            {"taskIndex": 0, **e}
            for e in agg_result.get("trajectoryExceptions", [])
        ],
        "aggregateAttempts": int(agg_result.get("aggregateAttempts", 0)),
        "aggregateRejectionsByReason": dict(
            agg_result.get("aggregateRejectionsByReason", {})
        ),
        "resultPresent": True,
        "perTaskResults": [agg_result],
    }


def _parse_submit_timestamp_ms(s: str) -> int:
    """Parse `RM_SUBMIT_TIMESTAMP_MS` env value to int; return 0 if
    empty / malformed (skips the self-check vacuously). Production
    callers MUST pass a valid epoch-ms value; the leniency here is for
    the maintainer test path that doesn't set the env."""
    if not s:
        return 0
    try:
        return int(s)
    except (TypeError, ValueError):
        log.warning("Malformed submit_timestamp_ms=%r; treating as 0", s)
        return 0


def _build_analyzer_output(
    *,
    snapshot_dict: dict,
    wrapper_envelope: dict,
    agg_result: dict,
    master_seed: int,
    K_approved: int,
    run_id: str,
    top_k: int,
    generated_at: str,
) -> dict:
    """Build the `AnalyzerOutput` JSON dict the callback POST carries.
    Returns the JSON-serializable dict per `render_analyzer_output_json`'s
    rendering (we round-trip through json.dumps + json.loads to keep
    the surface boundary clean).

    Skipped on the failure branch (K' == 0) — caller checks state
    first.
    """
    full_sidecar = build_full_sidecar_dict(
        snapshot_dict=snapshot_dict,
        agg=_agg_to_post_aggregation_shape(agg_result),
        master_seed=master_seed,
        K_approved=K_approved,
        run_id=run_id,
    )
    if full_sidecar is None:
        raise ValueError(
            "build_full_sidecar_dict returned None despite K' > 0 — "
            "internal invariant broken"
        )
    output = analyze(
        snapshot_dict,
        wrapper_envelope,
        full_sidecar,
        topK=top_k,
        generatedAt=generated_at,
    )
    # round-trip through render_analyzer_output_json so the callback
    # POST body matches the on-disk artifact byte-for-byte.
    return json.loads(render_analyzer_output_json(output))


def _build_success_or_unsatisfied_callback_body(
    *,
    run_id: str,
    attempt_id: str,
    operator_email: str,
    state: str,
    writeback_envelope: dict | None,
    analyzer_output: dict | None,
    K_approved: int,
    k_prime: int,
    wall_time_seconds: float,
    batch_job_name: str,
) -> dict:
    """Build the §10A.6 callback body for OK / UNSATISFIED states.
    `idToken` is injected at POST time per §10A.5 (mint via metadata
    server with audience = callback_url just before the request)."""
    return {
        # idToken filled by _post_callback_with_retry before each send
        "idToken": "",
        "schemaVersion": _CALLBACK_SCHEMA_VERSION,
        "runId": run_id,
        "attemptId": attempt_id,
        "operatorEmail": operator_email,
        "state": state,
        "writebackEnvelope": writeback_envelope,
        "analyzerOutput": analyzer_output,
        "error": None,
        "diagnostics": {
            "kApproved": K_approved,
            "kPrime": k_prime,
            "droppedCount": K_approved - k_prime,
            "wallTimeSeconds": round(wall_time_seconds, 3),
            "batchJobName": batch_job_name,
        },
    }


def _build_compute_error_callback_body(
    *,
    run_id: str,
    attempt_id: str,
    operator_email: str,
    K_approved: int,
    k_prime: int,
    wall_time_seconds: float,
    batch_job_name: str,
    error_code: str,
    error_message: str,
) -> dict:
    """Build the §10A.6 callback body for COMPUTE_ERROR state.
    Codes per §10A.6 finding 9: AGGREGATION_EXCEPTION /
    ANALYZER_EXCEPTION / FINALIZER_EXCEPTION / FINALIZE_TIMEOUT (new at
    M7 C4 T2A.2 PR-A — surfaces the 510s self-check trip per §8.7 +
    Codex P2 round 12 fix)."""
    return {
        "idToken": "",
        "schemaVersion": _CALLBACK_SCHEMA_VERSION,
        "runId": run_id,
        "attemptId": attempt_id,
        "operatorEmail": operator_email,
        "state": "COMPUTE_ERROR",
        "writebackEnvelope": None,
        "analyzerOutput": None,
        "error": {
            "code": error_code,
            "message": error_message,
        },
        "diagnostics": {
            "kApproved": K_approved,
            "kPrime": k_prime,
            "droppedCount": K_approved - k_prime,
            "wallTimeSeconds": round(wall_time_seconds, 3),
            "batchJobName": batch_job_name,
        },
    }


def _post_callback_with_retry(
    *,
    callback_url: str,
    body: dict,
    run_id: str,
    attempt_id: str,
    id_token_fn: IdTokenFn,
    http_post_fn: HttpPostFn,
) -> None:
    """POST callback body to the launcher Web App per §10A.7. Retries
    up to `_CALLBACK_POST_RETRY_COUNT` times with `_CALLBACK_POST_BACKOFF_SECONDS`
    exponential backoff on transport errors + 5xx responses; terminal on
    2xx + 4xx (no retry on client errors per §10A.7).

    Builds the §10A.3 URL with `runId` + `attemptId` query params here
    so callers don't need to pre-assemble the URL.

    Mints a fresh ID token for each attempt — tokens have a ~1h
    lifetime so a single mint would normally suffice, but minting per
    attempt is robust against retries that span longer than expected
    + costs only a metadata-server round-trip (<10ms typical).

    Logs each attempt's outcome to Cloud Logging. Does NOT raise on
    terminal failure — caller is `_inline_finalize`, which is
    contracted not to raise (FW-0039 silent-outcome gap).
    """
    qsep = "&" if "?" in callback_url else "?"
    full_url = (
        callback_url + qsep + "action=async-render-callback"
        + "&runId=" + run_id + "&attemptId=" + attempt_id
    )

    backoffs = list(_CALLBACK_POST_BACKOFF_SECONDS)
    max_attempts = _CALLBACK_POST_RETRY_COUNT + 1  # initial + retries

    for attempt_n in range(max_attempts):
        try:
            id_token = id_token_fn(callback_url)
        except Exception as e:  # noqa: BLE001
            log.exception(
                "ID token mint failed on attempt %d; treating as 5xx-retryable",
                attempt_n + 1,
            )
            if attempt_n < max_attempts - 1:
                time.sleep(backoffs[attempt_n])
                continue
            log.error(
                "Callback POST terminal: ID token mint failed after %d attempts (%s)",
                max_attempts, str(e),
            )
            return

        body["idToken"] = id_token
        try:
            status = http_post_fn(full_url, body, 30.0)
        except Exception as e:  # noqa: BLE001
            log.exception(
                "Callback POST attempt %d raised; treating as 5xx-retryable",
                attempt_n + 1,
            )
            if attempt_n < max_attempts - 1:
                time.sleep(backoffs[attempt_n])
                continue
            log.error(
                "Callback POST terminal after %d attempts: %s (run_id=%s)",
                max_attempts, str(e), run_id,
            )
            return

        if 200 <= status < 300:
            log.info(
                "Callback POST succeeded (status=%d, run_id=%s, state=%s)",
                status, run_id, body.get("state"),
            )
            return

        if 400 <= status < 500:
            log.error(
                "Callback POST 4xx terminal (status=%d, run_id=%s, "
                "state=%s) — no retry per §10A.7",
                status, run_id, body.get("state"),
            )
            return

        # 5xx — retry per §10A.7
        log.warning(
            "Callback POST 5xx (status=%d, run_id=%s, attempt=%d/%d)",
            status, run_id, attempt_n + 1, max_attempts,
        )
        if attempt_n < max_attempts - 1:
            time.sleep(backoffs[attempt_n])

    log.error(
        "Callback POST exhausted retries (run_id=%s, state=%s) — "
        "operator falls into FW-0039 silent-outcome gap",
        run_id, body.get("state"),
    )


def _default_id_token_fn(audience_url: str) -> str:
    """Production ID-token minter — hits the Cloud Batch VM's metadata
    server per §10A.5. Audience claim MUST match the callback Web App
    URL exactly (the launcher validates `aud` against the deployment's
    URL). `&format=full` per Codex P1 round 13 fix — the default
    `format=standard` token omits `email` / `email_verified` claims
    that the launcher's tokeninfo validation requires.

    Imports `requests` lazily so unit tests that mock this function
    don't pay the import cost; production callers that hit this path
    are the only ones that need the dependency.
    """
    import urllib.parse
    import requests  # type: ignore[import-not-found]

    metadata_url = (
        "http://metadata.google.internal/computeMetadata/v1/"
        "instance/service-accounts/default/identity"
        "?audience=" + urllib.parse.quote(audience_url, safe="")
        + "&format=full"
    )
    response = requests.get(
        metadata_url,
        headers={"Metadata-Flavor": "Google"},
        timeout=5.0,
    )
    response.raise_for_status()
    return response.text


def _default_http_post_fn(url: str, body: dict, timeout: float) -> int:
    """Production HTTPS POST — wraps `requests.post`. Returns the HTTP
    status code; raises on connection / DNS / timeout errors (the
    retry loop in `_post_callback_with_retry` treats raises as 5xx-
    retryable per §10A.7)."""
    import requests  # type: ignore[import-not-found]

    response = requests.post(
        url,
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    return response.status_code


def _build_parser_failure_result(
    *, run_id: str, master_seed: int, K_approved: int,
    attempt_id: str, parser_issues,
) -> dict:
    """Result-shaped envelope when the parser rejects the snapshot. The
    orchestrator's §8.7 aggregation treats this the same as a missing
    task (0 candidates contributed); the embedded parser-issues block is
    for forensic replay."""
    return {
        "schemaVersion": _RESULT_SCHEMA_VERSION,
        "runId": run_id,
        "masterSeed": master_seed,
        "kApproved": K_approved,
        "attemptId": attempt_id,
        "candidates": [],
        "failedTrajectories": [],
        "aggregateAttempts": 0,
        "aggregateRejectionsByReason": {},
        "parserRejection": {
            "issueCount": len(parser_issues),
            "issues": [
                {
                    "severity": getattr(i.severity, "name", str(i.severity)),
                    "code": i.code,
                    "message": i.message,
                }
                for i in parser_issues[:5]
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry: `python -m rostermonster_service.worker --run-id <runId>`.

    Reads `RM_MASTER_SEED` + `RM_K_APPROVED` env vars (set by the
    orchestrator via the Batch job spec's task environment). Local
    maintainer invocation can override via CLI flags.

    Returns POSIX-shell exit codes (0 on success; 2 on worker-level failure).
    """
    parser = argparse.ArgumentParser(
        description="Cloud Batch LAHC worker (M7 C4 T2A.1 single-VM)"
    )
    parser.add_argument(
        "--run-id", required=True,
        help="runEnvelope.runId per docs/selector_contract.md v2 §9; "
             "MUST match the orchestrator-written snapshot key path.",
    )
    default_master_seed = os.environ.get(_MASTER_SEED_ENV)
    parser.add_argument(
        "--master-seed", type=int,
        default=int(default_master_seed) if default_master_seed is not None else None,
        help="§9 input #3 master seed. Defaults to "
             + _MASTER_SEED_ENV + " env var (Batch task env).",
    )
    default_k = os.environ.get(_K_APPROVED_ENV)
    parser.add_argument(
        "--k-approved", type=int,
        default=int(default_k) if default_k is not None else _DEFAULT_K_APPROVED,
        help="K trajectories to run in Pool(K). Defaults to "
             + _K_APPROVED_ENV + " env var; falls back to "
             + str(_DEFAULT_K_APPROVED) + ".",
    )
    args = parser.parse_args(argv)

    if args.master_seed is None:
        print(
            "ERROR: --master-seed required (or set " + _MASTER_SEED_ENV + ")",
            file=sys.stderr,
        )
        return 2

    bucket = os.environ.get(_BUCKET_ENV, _DEFAULT_BUCKET)
    attempt_id = os.environ.get(_ATTEMPT_ID_ENV, "")
    # M7 C4 T2A.2 PR-A inline finalize step env plumbing. Empty
    # defaults make the finalize step skip the callback POST (test-
    # path + maintainer `/compute-lahc-test` back-compat per D-0071
    # sub-decision 14).
    callback_url = os.environ.get(_LAUNCHER_CALLBACK_URL_ENV, "")
    operator_email = os.environ.get(_OPERATOR_EMAIL_ENV, "")
    submit_timestamp_ms_str = os.environ.get(_SUBMIT_TIMESTAMP_MS_ENV, "")
    analyzer_top_k_env = os.environ.get(_ANALYZER_TOP_K_ENV)
    try:
        analyzer_top_k = (
            int(analyzer_top_k_env) if analyzer_top_k_env
            else _DEFAULT_ANALYZER_TOP_K
        )
    except ValueError:
        log.warning(
            "Malformed %s=%r; falling back to default %d",
            _ANALYZER_TOP_K_ENV, analyzer_top_k_env, _DEFAULT_ANALYZER_TOP_K,
        )
        analyzer_top_k = _DEFAULT_ANALYZER_TOP_K

    log.info(
        "Worker starting: run_id=%s master_seed=%d K_approved=%d bucket=%s "
        "attempt_id=%s callback_url=%s operator_email=%s",
        args.run_id, args.master_seed, args.k_approved, bucket,
        attempt_id or "<none>",
        callback_url or "<none>",
        operator_email or "<none>",
    )

    read_json, write_json = make_gcs_adapter(bucket)
    try:
        worker_main(
            args.run_id,
            master_seed=args.master_seed,
            K_approved=args.k_approved,
            read_json=read_json,
            write_json=write_json,
            bucket=bucket,
            attempt_id=attempt_id,
            callback_url=callback_url,
            operator_email=operator_email,
            submit_timestamp_ms_str=submit_timestamp_ms_str,
            analyzer_top_k=analyzer_top_k,
        )
    except Exception as e:
        log.exception("Worker raised; attempting best-effort error-result write")
        # Best-effort error result so the orchestrator's §8.7 aggregation
        # has something to read instead of silently treating the task as
        # missing. If THIS write also fails (e.g., GCS unreachable), fall
        # through to non-zero exit and rely on Cloud Batch's per-task
        # state machinery.
        error_uri = _gcs_uri(bucket, args.run_id, "result.json")
        try:
            write_json(error_uri, {
                "schemaVersion": _RESULT_SCHEMA_VERSION,
                "runId": args.run_id,
                "masterSeed": args.master_seed,
                "kApproved": args.k_approved,
                "attemptId": attempt_id,
                "candidates": [],
                "failedTrajectories": [],
                "aggregateAttempts": 0,
                "aggregateRejectionsByReason": {},
                "workerError": {
                    "exceptionType": type(e).__name__,
                    "exceptionMessage": str(e),
                },
            })
        except Exception:
            log.exception("Failed to write worker-error result.json")
        return 2

    log.info("Worker finished cleanly: run_id=%s", args.run_id)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    sys.exit(main())
