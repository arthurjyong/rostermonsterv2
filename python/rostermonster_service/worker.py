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
import logging
import multiprocessing
import os
import sys
from typing import Any, Callable

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
) -> dict:
    """Worker entry point — orchestrates the read → compute → write cycle
    for the single Cloud Batch task. Returns the result.json dict (also
    written to GCS at the §8.7 result key).

    All I/O ports are injected so tests exercise the full pipeline against
    an in-memory storage fixture without touching real GCS.

    Snapshot deserialization or parser-rejection surfaces in the
    result.json's `parserRejection` field (NOT raised) — the orchestrator's
    aggregation per §8.7 partial-failure tolerance treats this the same
    as a worker error-state (0 candidates contributed).

    **Amended at M7 C4 T2A.1**: seeds are derived locally from `master_seed`
    + `K_approved` via `derive_K_seeds()`; the per-task `seeds.json` GCS
    read is RETIRED (single-task pattern). Pool size defaults to K_approved
    (production: 88).
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
    return result


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
    log.info(
        "Worker starting: run_id=%s master_seed=%d K_approved=%d bucket=%s attempt_id=%s",
        args.run_id, args.master_seed, args.k_approved, bucket, attempt_id or "<none>",
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
