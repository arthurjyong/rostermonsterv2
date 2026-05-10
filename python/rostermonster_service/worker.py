"""Cloud Batch worker for the M7 LAHC parallel-solver path per
`docs/cloud_compute_contract.md` §8.7 + `docs/delivery_plan.md` §9 M7 C2
Task 2D.

Single-image dispatch: the same container that Cloud Run runs as a Flask
service (`gunicorn rostermonster_service.app:app`) is invoked by Cloud
Batch with the command override `python -m rostermonster_service.worker
--run-id <runId>` so each Batch task starts in worker mode. The
`taskSpec.runnables[0].container.commands[]` array on the Batch job spec
(set by the M7 C2 Task 2E orchestrator) carries the override; the
single-image discipline preserves the D-0050 dual-track guarantee that
both surfaces run the same Python compute core.

Input contract (read from GCS at the §8.7 keys):
  gs://rostermonsterv2-lahc/{runId}/snapshot.json     # input snapshot (orchestrator-written)
  gs://rostermonsterv2-lahc/{runId}/task-{n}/seeds.json  # per-task seed slice (orchestrator-written)

Output contract (written to GCS at the §8.7 key):
  gs://rostermonsterv2-lahc/{runId}/task-{n}/result.json  # this worker's output

Per-task `seeds.json` schema (orchestrator-written, consumed here):
```
{
  "schemaVersion": 1,
  "runId": "<runId>",
  "taskIndex": <n>,
  "masterSeed": <int>,
  "seeds": [<int>, ...]   // up to TRAJECTORIES_PER_TASK seeds; per-task slice
                          // of the K_approved seeds the orchestrator pre-derived
                          // via derive_K_seeds(masterSeed, K_approved).
}
```

Per-task `result.json` schema (this worker writes, M7 C2 Task 2F orchestrator
aggregates per `docs/cloud_compute_contract.md` §8.7's K' definition):
```
{
  "schemaVersion": 1,
  "runId": "<runId>",
  "taskIndex": <n>,
  "masterSeed": <int>,
  "candidates": [               // SUCCEEDED trajectories only — len(candidates)
                                // is the per-task contribution to K' per §8.7
    {
      "candidateSeed": <int>,
      "assignments": [...],     // _to_jsonable(TrialCandidate.assignments)
      "iters": <int>,
      "acceptedMoves": <int>,
      "bestScore": <float | null>,
      "terminalScore": <float | null>
    },
    ...
  ],
  "failedTrajectories": [       // SEED_FAILED trajectories per §12A.8
    {
      "candidateSeed": <int>,
      "unfilledDemand": [...]   // _to_jsonable(UnsatisfiedResult.unfilledDemand)
    },
    ...
  ],
  "aggregateAttempts": <int>,                    // sum across all 8 trajectories
  "aggregateRejectionsByReason": {<code>: <int>} // sum across all 8 trajectories
}
```

The orchestrator (Task 2F) computes `K' = sum(len(result.json["candidates"]))`
across completed tasks, treating cancelled/missing/failed-after-retry tasks as
contributing 0 candidates per §8.7's primary K' definition.

Determinism (§12A.4 + §12A.10): each pool child calls `solve(K=1,
_candidate_seeds=[its_one_seed], strategyId=LAHC, ...)` per the Task 2C
escape hatch; the orchestrator pre-derives all K_approved seeds via
`derive_K_seeds(masterSeed, K_approved)` and partitions them per-task so
the per-task seed list reaching this worker is byte-identical to the
local CLI's K-trajectory loop.
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

# Cloud Batch sets `BATCH_TASK_INDEX` on each task per its v1 worker
# contract; we accept it as the default for `--task-index` so the
# orchestrator doesn't have to encode the index in the command override.
_BATCH_TASK_INDEX_ENV = "BATCH_TASK_INDEX"

# §8.7 dense-pack invariant: 8 trajectories per `c3-highcpu-8` task,
# matching the 8 vCPU + multiprocessing.Pool(8) pattern. The per-task
# seed slice from the orchestrator MUST be `<= TRAJECTORIES_PER_TASK`;
# the final task in a non-multiple-of-8 K_approved partition may carry
# fewer (current production K=104 → all tasks fully packed at 8).
TRAJECTORIES_PER_TASK = 8

# FW-0037 elbow tuple — M7 production LAHC parameters per
# `docs/delivery_plan.md` §9 M7 C2 Task 2D + the M7 architecture lock at
# D-0070. Hardcoded here because the worker is the M7-specific surface;
# tunable LAHC defaults for other surfaces remain in `LahcParams()`.
_LAHC_HISTORY_LIST_LENGTH = 50
_LAHC_IDLE_THRESHOLD = 3500
_LAHC_SWAP_PROBABILITY = 0.5

# Result.json schema version per the §8.7 amendment. Bump if the result
# shape changes in a way that breaks the orchestrator's aggregation.
_RESULT_SCHEMA_VERSION = 1
# Seeds.json schema version per the §8.7 amendment.
_SEEDS_SCHEMA_VERSION = 1


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
    via `solve(K=1, _candidate_seeds=[seed])` per the Task 2C escape hatch.

    Lives at module top-level so `multiprocessing.Pool.map` can pickle it.
    Returns a dict (also picklable) carrying either the SUCCEEDED candidate
    or the SEED_FAILED unfilled demand, plus aggregate attempt + rejection
    counters for the parent's per-task aggregation.

    Per-trajectory exceptions are caught + surfaced as a third state
    (`status="EXCEPTION"`) so a single child raising doesn't lose the
    other 7 trajectories' results. Per §12A.8's drop-and-continue
    discipline: each trajectory is independent; one failure (or exception)
    doesn't fail the whole task.
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
    # failure per §12A.8. Treat as a failed trajectory (per-task K'
    # contribution: 0).
    return {
        "status": "SEED_FAILED",
        "candidateSeed": candidate_seed,
        "unfilledDemand": _to_jsonable(result.unfilledDemand),
        "placementAttempts": int(result.diagnostics.placementAttempts),
        "rejectionsByReason": dict(result.diagnostics.ruleEngineRejectionsByReason),
    }


def _default_pool_executor(
    fn: Callable[..., Any], args_iter: list[Any],
) -> list[Any]:
    """Production pool executor — `multiprocessing.Pool(TRAJECTORIES_PER_TASK)`
    matching the §8.7 dense-pack invariant (8 trajectories per
    `c3-highcpu-8` VM, 1 trajectory per vCPU). Tests inject a serial
    executor to keep test time bounded and sidestep multiprocessing
    spawn semantics in CI."""
    with multiprocessing.Pool(TRAJECTORIES_PER_TASK) as pool:
        return pool.map(fn, args_iter)


def worker_main(
    run_id: str,
    task_index: int,
    *,
    read_json: ReadJsonFn,
    write_json: WriteJsonFn,
    pool_executor: PoolExecutorFn = _default_pool_executor,
    bucket: str = _DEFAULT_BUCKET,
) -> dict:
    """Worker entry point — orchestrates the read → compute → write cycle
    for one Cloud Batch task. Returns the result.json dict (also written
    to GCS at the §8.7 result key for orchestrator pickup).

    All I/O ports are injected so tests exercise the full pipeline against
    an in-memory storage fixture without touching real GCS.

    Snapshot deserialization or parser-rejection surfaces in the top-level
    result.json's `state` field (NOT raised) — the orchestrator's
    aggregation per §8.7 partial-failure tolerance treats a worker
    error-state result.json the same as a missing one (0 candidates
    contributed). Letting the worker propagate the exception would mask
    the failure mode in Cloud Batch logs without giving the orchestrator
    a structured diagnostic.
    """
    snapshot_uri = _gcs_uri(bucket, run_id, "snapshot.json")
    seeds_uri = _gcs_uri(bucket, run_id, "task-" + str(task_index), "seeds.json")
    result_uri = _gcs_uri(bucket, run_id, "task-" + str(task_index), "result.json")

    # --- Load inputs ---------------------------------------------------
    snapshot_dict = read_json(snapshot_uri)
    seeds_dict = read_json(seeds_uri)

    candidate_seeds = seeds_dict["seeds"]
    master_seed = int(seeds_dict["masterSeed"])
    # `attemptId` per the M7 C2 Task 2G concurrent-replay race fix
    # (`docs/cloud_compute_contract.md` §8.7): orchestrator stamps an
    # attemptId into seeds.json; worker echoes it back into result.json
    # so the orchestrator can validate on read that result.json belongs
    # to THIS attempt (not a stale prior attempt at the same runId
    # prefix). Pre-T2G seeds.json files lacked this field; treat
    # missing as a non-fatal None so the orchestrator's validation
    # logic surfaces the mismatch rather than the worker raising on
    # historical replays.
    attempt_id = seeds_dict.get("attemptId")

    if not isinstance(candidate_seeds, list) or not candidate_seeds:
        raise ValueError(
            "seeds.json[\"seeds\"] must be a non-empty list of ints; got "
            + repr(candidate_seeds)
        )
    if len(candidate_seeds) > TRAJECTORIES_PER_TASK:
        raise ValueError(
            "seeds.json[\"seeds\"] has " + str(len(candidate_seeds))
            + " entries; per-task cap is " + str(TRAJECTORIES_PER_TASK)
            + " per docs/cloud_compute_contract.md §8.7 dense-pack invariant"
        )

    # --- Parse snapshot -----------------------------------------------
    snapshot = _snapshot_from_dict(snapshot_dict)
    template = icu_hd_template_artifact()
    parser_result = parse(snapshot, template)
    if parser_result.consumability is not Consumability.CONSUMABLE:
        # Parser rejected the snapshot. Worker can't run; emit a result
        # the orchestrator can aggregate (0 candidates contributed).
        result = _build_parser_failure_result(
            run_id=run_id, task_index=task_index, master_seed=master_seed,
            attempt_id=attempt_id, parser_issues=parser_result.issues,
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

    # --- Aggregate per-task result -------------------------------------
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
        "taskIndex": task_index,
        "masterSeed": master_seed,
        # Echo attemptId from seeds.json so orchestrator can validate
        # this result.json belongs to its attempt (T2G concurrent-replay
        # race fix per §8.7). Pre-T2G seeds.json without attemptId
        # results in `None` here; orchestrator's validation surfaces the
        # mismatch as "missing" per the standard partial-failure path.
        "attemptId": attempt_id,
        "candidates": candidates,
        "failedTrajectories": failed,
        "aggregateAttempts": aggregate_attempts,
        "aggregateRejectionsByReason": aggregate_rejections,
    }
    # Only surface the exceptions block when non-empty so the common case
    # (all 8 trajectories cleanly SUCCEEDED or SEED_FAILED) keeps the
    # result.json surface area minimal for orchestrator consumption.
    if exceptions:
        result["trajectoryExceptions"] = exceptions

    write_json(result_uri, result)
    return result


def _build_parser_failure_result(
    *, run_id: str, task_index: int, master_seed: int,
    attempt_id, parser_issues,
) -> dict:
    """Result-shaped envelope when the parser rejects the snapshot. The
    orchestrator's §8.7 aggregation treats this the same as a missing
    task (0 candidates contributed); the embedded parser-issues block is
    for forensic replay."""
    return {
        "schemaVersion": _RESULT_SCHEMA_VERSION,
        "runId": run_id,
        "taskIndex": task_index,
        "masterSeed": master_seed,
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
    `--task-index` defaults to the `BATCH_TASK_INDEX` env var Cloud Batch
    sets per-task; explicit override is accepted for local maintainer
    invocation. Returns POSIX-shell exit codes (0 on success; 2 on
    worker-level failure)."""
    parser = argparse.ArgumentParser(
        description="Cloud Batch LAHC worker (M7 C2 Task 2D)"
    )
    parser.add_argument(
        "--run-id", required=True,
        help="runEnvelope.runId per docs/selector_contract.md v2 §9; "
             "MUST match the orchestrator-written snapshot/seeds key paths.",
    )
    default_task_index = os.environ.get(_BATCH_TASK_INDEX_ENV)
    parser.add_argument(
        "--task-index", type=int,
        default=int(default_task_index) if default_task_index is not None else None,
        help="Per-task index in [0, taskCount). Defaults to "
             + _BATCH_TASK_INDEX_ENV + " env var (Cloud Batch sets this).",
    )
    args = parser.parse_args(argv)

    if args.task_index is None:
        print(
            "ERROR: --task-index required (or set " + _BATCH_TASK_INDEX_ENV + ")",
            file=sys.stderr,
        )
        return 2

    bucket = os.environ.get(_BUCKET_ENV, _DEFAULT_BUCKET)
    log.info(
        "Worker starting: run_id=%s task_index=%d bucket=%s",
        args.run_id, args.task_index, bucket,
    )

    read_json, write_json = make_gcs_adapter(bucket)
    try:
        worker_main(
            args.run_id, args.task_index,
            read_json=read_json,
            write_json=write_json,
            bucket=bucket,
        )
    except Exception as e:
        log.exception("Worker raised; attempting best-effort error-result write")
        # Best-effort error result so the orchestrator's §8.7 aggregation
        # has something to read instead of silently treating the task as
        # missing. If THIS write also fails (e.g., GCS unreachable), fall
        # through to non-zero exit and rely on Cloud Batch's per-task
        # state machinery.
        error_uri = _gcs_uri(
            bucket, args.run_id, "task-" + str(args.task_index), "result.json",
        )
        try:
            write_json(error_uri, {
                "schemaVersion": _RESULT_SCHEMA_VERSION,
                "runId": args.run_id,
                "taskIndex": args.task_index,
                # attemptId unknown at this layer (worker_main raised
                # before reading seeds.json or after); orchestrator's
                # validation treats null attemptId as a stale-result
                # mismatch unless its expected attemptId is also null.
                "attemptId": None,
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

    log.info("Worker finished cleanly: run_id=%s task_index=%d", args.run_id, args.task_index)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    sys.exit(main())
