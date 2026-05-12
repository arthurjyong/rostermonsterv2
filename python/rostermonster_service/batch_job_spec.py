"""Cloud Batch job-spec builder for the M7 LAHC parallel-solver path per
`docs/cloud_compute_contract.md` §8.7.

Pure function: takes `(run_id, container_image_uri, ...)` + the §8.7
invariants (mostly defaulted to the contract-pinned values) and returns
the JSON-serializable dict the M7 LAHC orchestrator passes to the Cloud
Batch v1 `jobs.create` API. Kept as a separate module from `app.py` so
the spec assembly is independently testable + future tweaks live in one
place.

**Amended at M7 C4 T2A.1 (2026-05-12) per the Codex P1.7 single-VM
amendment locked in PR #147 + the M7 C4 Task 1 plan in PR #148:**
collapsed from 13-VM dense pack (`c3-highcpu-8` × 13, K=104) to
single-VM dense pack (one `c3-highcpu-88` VM, `multiprocessing.Pool(88)`
× 1 task = K=88). Cloud Batch v1's `Job.taskGroups[]` is limited to one
task group (Codex P1.7 finding) — workers + finalizer must run on one
VM in one Python process. The inline finalize step itself lands at
M7 C4 T2A.2; this PR (T2A.1) keeps the per-task `result.json` output
schema so `/compute-lahc-test` continues to work end-to-end via the
existing M7 C2 orchestrator polling path.

Single-image discipline per `docs/decision_log.md` D-0050: the same
container image Cloud Run runs as a Flask service is dispatched here
into worker mode by overriding `taskSpec.runnables[0].container.commands[]`
to invoke `python -m rostermonster_service.worker --run-id <runId>`. The
worker derives all K seeds locally from the `RM_MASTER_SEED` env var
via `derive_K_seeds(masterSeed, K)` per §12A.10 (no per-task `seeds.json`
under single-task — there's only one task).

New env vars on the task spec (some plumbed in T2A.1 ahead of T2A.2's
inline finalize step using them):
  - `RM_MASTER_SEED`: int, the §9 input #3 master seed.
  - `RM_K_APPROVED`: int, K trajectories to run in Pool(K_APPROVED).
  - `RM_OPERATOR_EMAIL`: string, operator email (plumbed for T2A.2's
    finalize step; ignored by T2A.1 worker).
  - `RM_LAUNCHER_CALLBACK_URL`: string, launcher's USER_DEPLOYING
    callback URL (plumbed for T2A.2; ignored by T2A.1 worker; T2D's
    Cloud Run thin front door sets this).
  - `RM_SUBMIT_TIMESTAMP_MS`: int (epoch ms), set by Cloud Run at
    submitJob time (plumbed for T2A.2's 510s self-check; ignored by
    T2A.1 worker).
  - `LAHC_BUCKET`: string, the GCS bucket name (existing M7 C2 env).

Job labels per D-0071 sub-decision 8 + §8.7's concurrent-rejection
mechanic: `labels.spreadsheet_id` set to a normalized form of the
snapshot's `sourceSpreadsheetId` (lowercase + non-`[a-z0-9_-]` → `-`
+ truncate to 63 chars per Google Resource Manager label constraints).
Cloud Run's concurrent-rejection logic (lands at M7 C4 T2D) queries by
this label.
"""

from __future__ import annotations

import re
from typing import Any

# §8.7 invariants — pinned to the contract-defined values. Edit here if
# the contract amends; never inline these in callers.
_DEFAULT_MACHINE_TYPE = "c3-highcpu-88"
_DEFAULT_REGION = "asia-southeast1"
_DEFAULT_BUCKET = "rostermonsterv2-lahc"
_DEFAULT_PROVISIONING_MODEL = "STANDARD"  # on-demand only per D-0070 sub-decision 4 (NOT Spot)
# Per-task wall budget per §8.7 + Codex P1 round 10 amendment — 660s is
# INTENTIONALLY above the 600s operator-facing ceiling (enforced via
# the finalize-step self-check at 510s elapsed since RM_SUBMIT_TIMESTAMP_MS,
# reserving ~90s for finalize work). 660s is a safety net catching the
# degenerate case where the Pool hangs without raising.
_DEFAULT_PER_TASK_MAX_RUN_DURATION = "660s"
# Per Codex P2 round 8 amendment: NO retry. Per-attempt × 2 = 1320s
# would blow the 10-min hard cap; single-attempt + finalize-step
# self-check at 510s is what bounds the operator-facing wall.
_DEFAULT_PER_TASK_MAX_RETRY_COUNT = 0
# c3-highcpu-88 = 88 vCPU + 176 GB RAM. Pin cpuMilli + memoryMib to
# fully claim the VM so Cloud Batch's bin-packer keeps `taskCountPerNode=1`.
# memoryMib leaves ~16 GB headroom for the OS / agent on the 176 GB VM.
_DEFAULT_CPU_MILLI = 88000
_DEFAULT_MEMORY_MIB = 160000
# §8.7 single-VM dense pack (Codex P1.7 amendment): K=88 LAHC trajectories
# via `multiprocessing.Pool(88)` on one `c3-highcpu-88` VM, 1 trajectory
# per vCPU. K=88 reflects the largest c3-highcpu size that fits the current
# C3_CPUS=108 quota; future quota bump to ≥176 unlocks K=176 via FW-0040
# (parameterized as `K_approved` arg to this builder).
_DEFAULT_K_APPROVED = 88

# §8.7 single-image dispatch: the worker module entry that Cloud Batch
# overrides into via `commands[]`. Cloud Run keeps gunicorn (no override).
_WORKER_MODULE = "rostermonster_service.worker"

# Cloud Batch v1 logs destination per §8.7.
_DEFAULT_LOGS_DESTINATION = "CLOUD_LOGGING"

# Google Resource Manager label-value constraints per
# https://cloud.google.com/resource-manager/docs/creating-managing-labels:
# allowed chars `[a-z0-9_-]`, max length 63. Used to normalize the
# spreadsheet_id label per Codex P2 round 11 amendment.
_LABEL_VALUE_PATTERN = re.compile(r"[^a-z0-9_-]")
_LABEL_VALUE_MAX_LENGTH = 63


def normalize_label_value(raw: str) -> str:
    """Normalize a raw string into a Cloud Batch label-safe value per
    Google Resource Manager constraints (`[a-z0-9_-]{1,63}`). Used for
    the `spreadsheet_id` label on Cloud Batch jobs to support the
    `batch.jobs.list --filter=labels.spreadsheet_id=<normalized>` query
    that Cloud Run's concurrent-rejection check (T2D) makes.

    Steps: lowercase + non-`[a-z0-9_-]` → `-` + truncate to 63 chars.
    Drive spreadsheet IDs commonly carry uppercase characters (base64url-ish)
    which would fail label validation without normalization, blocking
    `submitJob` before the concurrent-run guard can ever run.
    """
    if not isinstance(raw, str):
        raise ValueError(
            "label-value input must be a string; got "
            + type(raw).__name__ + "=" + repr(raw)
        )
    lowered = raw.lower()
    sanitized = _LABEL_VALUE_PATTERN.sub("-", lowered)
    truncated = sanitized[:_LABEL_VALUE_MAX_LENGTH]
    if not truncated:
        raise ValueError(
            "label-value normalization produced an empty string from "
            + repr(raw)
        )
    return truncated


def build_lahc_batch_job_spec(
    *,
    run_id: str,
    container_image_uri: str,
    master_seed: int,
    source_spreadsheet_id: str,
    attempt_id: str = "",
    operator_email: str = "",
    submit_timestamp_ms: int = 0,
    launcher_callback_url: str = "",
    K_approved: int = _DEFAULT_K_APPROVED,
    bucket: str = _DEFAULT_BUCKET,
    region: str = _DEFAULT_REGION,
    machine_type: str = _DEFAULT_MACHINE_TYPE,
    per_task_max_run_duration: str = _DEFAULT_PER_TASK_MAX_RUN_DURATION,
    per_task_max_retry_count: int = _DEFAULT_PER_TASK_MAX_RETRY_COUNT,
    provisioning_model: str = _DEFAULT_PROVISIONING_MODEL,
) -> dict[str, Any]:
    """Build the Cloud Batch v1 `Job` spec dict for the M7 LAHC single-VM
    dense-pack path per `docs/cloud_compute_contract.md` §8.7.

    `run_id`: `runEnvelope.runId` per `docs/selector_contract.md` v2 §9 —
    flows into the worker's `--run-id` arg.

    `container_image_uri`: full image URI of the deployed Cloud Run
    container. Single-image discipline pins both surfaces.

    `master_seed`: §9 input #3 master seed. The worker derives K
    trajectory seeds locally from this via `derive_K_seeds()` per §12A.10
    (no per-task seeds.json under single-task).

    `operator_email`: the operator's email address sourced from
    `Session.getActiveUser().getEmail()` in the bound shim. Plumbed via
    env to the worker; used by T2A.2's inline finalize step (T2A.1
    worker ignores it).

    `source_spreadsheet_id`: raw `snapshot.metadata.sourceSpreadsheetId`.
    Normalized via `normalize_label_value()` before being attached as
    `labels.spreadsheet_id` for the concurrent-rejection query.

    `submit_timestamp_ms`: epoch milliseconds at submitJob time, used by
    T2A.2's finalize-step self-check at 510s elapsed (T2A.1 worker
    ignores it; plumbed now to avoid a follow-up spec change in T2A.2).

    `launcher_callback_url`: the launcher's USER_DEPLOYING callback URL
    set by T2D's Cloud Run thin front door. Empty string for
    `/compute-lahc-test` maintainer testing (skips POST callback in
    T2A.2's finalize step). T2A.1 worker ignores this entirely.

    `K_approved`: total trajectory count, defaults to 88 (the M7
    production config for `c3-highcpu-88` within the current C3_CPUS=108
    quota; future quota bump to ≥176 unlocks K=176 via FW-0040).
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
    if isinstance(master_seed, bool) or not isinstance(master_seed, int):
        raise ValueError(
            "master_seed must be an integer; got "
            + type(master_seed).__name__ + "=" + repr(master_seed)
        )
    if not isinstance(operator_email, str):
        raise ValueError(
            "operator_email must be a string (may be empty for "
            "/compute-lahc-test maintainer testing); got "
            + type(operator_email).__name__ + "=" + repr(operator_email)
        )
    if not isinstance(source_spreadsheet_id, str) or not source_spreadsheet_id:
        raise ValueError(
            "source_spreadsheet_id must be a non-empty string; got "
            + type(source_spreadsheet_id).__name__ + "="
            + repr(source_spreadsheet_id)
        )
    if (isinstance(submit_timestamp_ms, bool)
            or not isinstance(submit_timestamp_ms, int)
            or submit_timestamp_ms < 0):
        raise ValueError(
            "submit_timestamp_ms must be a non-negative integer (0 sentinel "
            "for /compute-lahc-test which doesn't use the 510s self-check); "
            "got " + type(submit_timestamp_ms).__name__ + "="
            + repr(submit_timestamp_ms)
        )
    if not isinstance(launcher_callback_url, str):
        raise ValueError(
            "launcher_callback_url must be a string (may be empty for "
            "/compute-lahc-test); got "
            + type(launcher_callback_url).__name__ + "="
            + repr(launcher_callback_url)
        )
    if not isinstance(attempt_id, str):
        raise ValueError(
            "attempt_id must be a string (may be empty when caller "
            "doesn't need replay-collision protection); got "
            + type(attempt_id).__name__ + "=" + repr(attempt_id)
        )
    if (isinstance(K_approved, bool)
            or not isinstance(K_approved, int)
            or K_approved <= 0):
        raise ValueError(
            "K_approved must be a positive integer; got "
            + type(K_approved).__name__ + "=" + repr(K_approved)
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

    normalized_spreadsheet_id = normalize_label_value(source_spreadsheet_id)

    return {
        "labels": {
            # D-0071 sub-decision 8 — concurrent-rejection query target.
            # Operator email is NOT a label (emails contain @/. which
            # fail GRM label validation); the in-flight job's
            # RM_OPERATOR_EMAIL env var is read at rejection-time
            # (T2D's Cloud Run thin front door).
            "spreadsheet_id": normalized_spreadsheet_id,
        },
        "taskGroups": [
            {
                "taskSpec": {
                    "runnables": [
                        {
                            "container": {
                                "imageUri": container_image_uri,
                                # Single-image dispatch: Cloud Batch overrides
                                # the container's CMD via `commands[]` to run
                                # the worker module entry. The worker module
                                # reads env vars set below.
                                "commands": [
                                    "python", "-m", _WORKER_MODULE,
                                    "--run-id", run_id,
                                ],
                            }
                        }
                    ],
                    # Pin the full c3-highcpu-88 to one task per the §8.7
                    # single-VM dense-pack invariant (Codex P1.7 amendment).
                    # cpuMilli + memoryMib claim the whole VM so Cloud Batch's
                    # bin-packer doesn't co-schedule another task here.
                    "computeResource": {
                        "cpuMilli": _DEFAULT_CPU_MILLI,
                        "memoryMib": _DEFAULT_MEMORY_MIB,
                    },
                    # Per-task wall budget — 660s safety net per Codex P1
                    # round 10 amendment. Operator-facing 600s ceiling is
                    # enforced via finalize-step self-check at 510s elapsed
                    # since RM_SUBMIT_TIMESTAMP_MS (T2A.2; T2A.1 doesn't
                    # implement the self-check yet — the per-task budget
                    # alone bounds wall time for the T2A.1 intermediate state).
                    "maxRunDuration": per_task_max_run_duration,
                    # Per Codex P2 round 8 amendment: NO retry. Per-attempt
                    # × 2 would blow the 10-min cap; single-attempt + the
                    # finalize-step self-check is what bounds wall time.
                    "maxRetryCount": per_task_max_retry_count,
                    # Env vars: worker.py reads RM_MASTER_SEED + RM_K_APPROVED
                    # in T2A.1; reads RM_OPERATOR_EMAIL + RM_LAUNCHER_CALLBACK_URL
                    # + RM_SUBMIT_TIMESTAMP_MS in T2A.2's inline finalize step.
                    # LAHC_BUCKET stays from M7 C2 for GCS adapter wiring.
                    "environment": {
                        "variables": {
                            "RM_MASTER_SEED": str(master_seed),
                            "RM_K_APPROVED": str(K_approved),
                            "RM_ATTEMPT_ID": attempt_id,
                            "RM_OPERATOR_EMAIL": operator_email,
                            "RM_LAUNCHER_CALLBACK_URL": launcher_callback_url,
                            "RM_SUBMIT_TIMESTAMP_MS": str(submit_timestamp_ms),
                            "LAHC_BUCKET": bucket,
                        },
                    },
                },
                # Single-VM dense pack: ONE task on ONE VM per Codex P1.7
                # amendment. Cloud Batch v1 only supports one task group;
                # workers + finalizer run on one VM in one Python process.
                "taskCount": 1,
                "parallelism": 1,
                "taskCountPerNode": 1,
            }
        ],
        "allocationPolicy": {
            "instances": [
                {
                    "policy": {
                        "machineType": machine_type,
                        # On-demand only per D-0070 sub-decision 4.
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
