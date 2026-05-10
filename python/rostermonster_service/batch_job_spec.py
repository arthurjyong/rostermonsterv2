"""Cloud Batch job-spec builder for the M7 LAHC parallel-solver path per
`docs/cloud_compute_contract.md` §8.7 + `docs/delivery_plan.md` §9 M7 C2
Task 2E.

Pure function: takes `(run_id, K_approved, container_image_uri)` + the
§8.7 invariants (mostly defaulted to the contract-pinned values) and
returns the JSON-serializable dict the M7 C2 Task 2F orchestrator passes
to the Cloud Batch v1 `jobs.create` API. Kept as a separate module from
`app.py` so the spec assembly is independently testable + future tweaks
(e.g., bumping per-task `maxRunDuration` if M7 C3 measurement shows
headroom) live in one place.

Single-image discipline per `docs/decision_log.md` D-0050: the same
container image Cloud Run runs as a Flask service is dispatched here
into worker mode by overriding `taskSpec.runnables[0].container.commands[]`
to invoke `python -m rostermonster_service.worker --run-id <runId>`. Each
Batch task picks up its `BATCH_TASK_INDEX` from the env Cloud Batch sets
per-task (per the v1 worker contract); the worker reads
`gs://rostermonsterv2-lahc/{runId}/task-{n}/seeds.json` to get its
assigned seed slice the orchestrator pre-derived via
`derive_K_seeds(masterSeed, K_approved)` per §12A.10.

The 240s **orchestrator-side completion deadline** per §8.7 lives in M7
C2 Task 2F's polling loop, NOT in this spec — Cloud Batch's `Job` schema
has no job-level `maxRunDuration` field (only `TaskSpec.maxRunDuration`,
which is the per-task 180s pinned below).
"""

from __future__ import annotations

import math
from typing import Any

# §8.7 invariants — pinned to the contract-defined values. Edit here if
# the contract amends; never inline these in callers.
_DEFAULT_MACHINE_TYPE = "c3-highcpu-8"
_DEFAULT_REGION = "asia-southeast1"
_DEFAULT_BUCKET = "rostermonsterv2-lahc"
_DEFAULT_PROVISIONING_MODEL = "STANDARD"  # on-demand only per D-0070 sub-decision 4 (NOT Spot)
_DEFAULT_PER_TASK_MAX_RUN_DURATION = "180s"
_DEFAULT_PER_TASK_MAX_RETRY_COUNT = 1
# c3-highcpu-8 = 8 vCPU + 16 GB RAM. Pin cpuMilli + memoryMib to fully
# claim the VM so Cloud Batch's bin-packer keeps `taskCountPerNode=1`
# even if the field were ever removed by accident — same dense-pack
# safety belt. memoryMib leaves ~2 GB headroom for the OS / agent.
_DEFAULT_CPU_MILLI = 8000
_DEFAULT_MEMORY_MIB = 14000
# §8.7 dense-pack: 1 trajectory per vCPU on c3-highcpu-8 = 8 trajectories
# per task. Drift would change task count derivation downstream.
_TRAJECTORIES_PER_TASK = 8

# §8.7 single-image dispatch: the worker module entry that Cloud Batch
# overrides into via `commands[]`. Cloud Run keeps gunicorn (no override).
_WORKER_MODULE = "rostermonster_service.worker"

# Cloud Batch v1 logs destination per §8.7 (default; LOGGING infra is
# already enabled on the project from M4 C1).
_DEFAULT_LOGS_DESTINATION = "CLOUD_LOGGING"


def task_count_for_K(K_approved: int) -> int:
    """Per D-0070 sub-decision 7's three-quota rule: `taskCount =
    ceil(K_approved / 8)`. Current production K=104 → 13 fully-packed
    tasks; K=2,500 (full M7 quota) → 313 tasks where the final task
    carries 4 trajectories (cores 4..7 idle).

    The orchestrator's seed-partitioning step in M7 C2 Task 2F uses the
    same formula to slice the K-length seed list into per-task chunks,
    and the worker (T2D) caps its incoming seeds at
    `TRAJECTORIES_PER_TASK = 8` per `docs/cloud_compute_contract.md`
    §8.7.
    """
    if isinstance(K_approved, bool) or not isinstance(K_approved, int):
        raise ValueError(
            "K_approved must be a positive integer; got "
            + type(K_approved).__name__ + "=" + repr(K_approved)
        )
    if K_approved <= 0:
        raise ValueError(
            "K_approved must be a positive integer; got " + repr(K_approved)
        )
    return math.ceil(K_approved / _TRAJECTORIES_PER_TASK)


def build_lahc_batch_job_spec(
    *,
    run_id: str,
    K_approved: int,
    container_image_uri: str,
    bucket: str = _DEFAULT_BUCKET,
    region: str = _DEFAULT_REGION,
    machine_type: str = _DEFAULT_MACHINE_TYPE,
    per_task_max_run_duration: str = _DEFAULT_PER_TASK_MAX_RUN_DURATION,
    per_task_max_retry_count: int = _DEFAULT_PER_TASK_MAX_RETRY_COUNT,
    provisioning_model: str = _DEFAULT_PROVISIONING_MODEL,
) -> dict[str, Any]:
    """Build the Cloud Batch v1 `Job` spec dict the M7 C2 Task 2F
    orchestrator passes to `jobs.create` per `docs/cloud_compute_contract.md`
    §8.7.

    `run_id`: `runEnvelope.runId` per `docs/selector_contract.md` v2 §9 —
    flows into the worker's `--run-id` arg + into the GCS key paths the
    worker reads.

    `K_approved`: total trajectory count per the M7 C1 closure-K math.
    Determines `taskCount = parallelism = ceil(K_approved / 8)`.

    `container_image_uri`: full image URI of the deployed Cloud Run
    container (e.g., `gcr.io/rostermonsterv2/roster-monster-compute:<tag>`).
    Must be the same image the Cloud Run service runs — the §8.7 single-
    image discipline pins one image per deployment to keep both surfaces
    in sync.

    Other args default to the §8.7-pinned values; pass overrides only
    when the contract is amended (test harnesses also pass overrides to
    exercise alternate shapes).
    """
    # --- Boundary validation -----------------------------------------
    if not isinstance(run_id, str) or not run_id:
        raise ValueError(
            "run_id must be a non-empty string; got "
            + type(run_id).__name__ + "=" + repr(run_id)
        )
    if not isinstance(container_image_uri, str) or not container_image_uri:
        raise ValueError(
            "container_image_uri must be a non-empty string; got "
            + type(container_image_uri).__name__ + "="
            + repr(container_image_uri)
        )
    if not isinstance(bucket, str) or not bucket:
        raise ValueError(
            "bucket must be a non-empty string; got "
            + type(bucket).__name__ + "=" + repr(bucket)
        )
    if not isinstance(region, str) or not region:
        raise ValueError(
            "region must be a non-empty string; got "
            + type(region).__name__ + "=" + repr(region)
        )
    if (isinstance(per_task_max_retry_count, bool)
            or not isinstance(per_task_max_retry_count, int)
            or per_task_max_retry_count < 0):
        raise ValueError(
            "per_task_max_retry_count must be a non-negative integer; got "
            + type(per_task_max_retry_count).__name__ + "="
            + repr(per_task_max_retry_count)
        )

    task_count = task_count_for_K(K_approved)

    return {
        "taskGroups": [
            {
                "taskSpec": {
                    "runnables": [
                        {
                            "container": {
                                "imageUri": container_image_uri,
                                # Single-image dispatch: Cloud Batch overrides
                                # the container's CMD via `commands[]` to run
                                # the worker module entry. `BATCH_TASK_INDEX`
                                # is set on each task by Cloud Batch per its
                                # v1 worker contract; the worker module reads
                                # it as the default for `--task-index`.
                                "commands": [
                                    "python", "-m", _WORKER_MODULE,
                                    "--run-id", run_id,
                                ],
                            }
                        }
                    ],
                    # Pin the full c3-highcpu-8 to one task per the §8.7
                    # dense-pack invariant. Without this + taskCountPerNode=1,
                    # Batch's bin-packer could co-schedule and oversubscribe
                    # the VM that already runs multiprocessing.Pool(8).
                    "computeResource": {
                        "cpuMilli": _DEFAULT_CPU_MILLI,
                        "memoryMib": _DEFAULT_MEMORY_MIB,
                    },
                    # Per-task wall budget per §8.7. Covers VM provisioning
                    # ~30-60s + 8 parallel trajectories ~50-75s + GCS I/O
                    # ~5-10s + buffer ~5s. Budget is not a job-level field
                    # in Cloud Batch v1; the 240s orchestrator-side
                    # completion deadline lives in T2F's polling loop.
                    "maxRunDuration": per_task_max_run_duration,
                    # Per-task retry per §8.7: 1 retry on failure, fail-fast
                    # on second. Default Cloud Batch is 0; a single retry
                    # absorbs transient VM stalls without doubling worst-
                    # case wall on every run.
                    "maxRetryCount": per_task_max_retry_count,
                    # Carry the bucket name into worker env so a deploy-
                    # time override (LAHC_BUCKET env var on the worker)
                    # can flow through; default tracks _DEFAULT_BUCKET.
                    "environment": {
                        "variables": {
                            "LAHC_BUCKET": bucket,
                        },
                    },
                },
                "taskCount": task_count,
                "parallelism": task_count,
                # 1 task per VM per §8.7. The dense-pack math (8
                # trajectories × N VMs = K_approved) only holds when
                # Cloud Batch provisions exactly one task per c3-highcpu-8.
                "taskCountPerNode": 1,
            }
        ],
        "allocationPolicy": {
            "instances": [
                {
                    "policy": {
                        "machineType": machine_type,
                        # On-demand only per D-0070 sub-decision 4 — sync
                        # wall-time predictability. Spot would shave cost
                        # at the price of pre-emption risk inside the 240s
                        # orchestrator deadline.
                        "provisioningModel": provisioning_model,
                    }
                }
            ],
            "location": {
                "allowedLocations": ["regions/" + region],
            },
        },
        "logsPolicy": {
            "destination": _DEFAULT_LOGS_DESTINATION,
        },
    }
