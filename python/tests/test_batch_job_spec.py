"""Tests for the M7 C2 Task 2E Cloud Batch job-spec builder per
`docs/cloud_compute_contract.md` §8.7 +
`python/rostermonster_service/batch_job_spec.py`.

Covers:
- Task-count derivation per D-0070 sub-decision 7's `ceil(K_approved/8)`
  rule (current production K=104 → 13 tasks; full M7 quota K=2,500 →
  313 tasks; small approvals must stay multiple-of-8 producing fully-
  packed task counts).
- §8.7 invariants: `c3-highcpu-8`, `taskCountPerNode=1`, on-demand
  (`STANDARD` provisioning), per-task `maxRunDuration: "180s"`, per-task
  `maxRetryCount: 1`, region `asia-southeast1`, logs to Cloud Logging.
- Single-image dispatch: `commands[]` invokes
  `python -m rostermonster_service.worker --run-id <runId>`; the worker
  module entry name must match `_WORKER_MODULE`.
- Container image URI flows through unchanged from the caller.
- Bucket name flows into the per-task env via `LAHC_BUCKET` so the
  worker's `_BUCKET_ENV` override path resolves to the right bucket.
- Boundary validation rejects empty / non-string `run_id`,
  `container_image_uri`, `bucket`, `region`; non-positive `K_approved`;
  negative `per_task_max_retry_count`; bool variants of int args.

Standalone runnable via `python3 python/tests/test_batch_job_spec.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rostermonster_service import batch_job_spec as bjs  # noqa: E402


_RUN_ID = "test-run-2026-05-10-001"
_IMAGE = "gcr.io/rostermonsterv2/roster-monster-compute:test-tag"


# --- Task-count derivation (D-0070 sub-decision 7) ----------------------


def test_task_count_for_K_104_is_13() -> None:
    """M7 C1 closure-K = 104 (per PR #137). Per the three-quota rule
    `taskCount = ceil(104/8) = 13`. All 13 tasks fully packed at 8
    trajectories each."""
    assert bjs.task_count_for_K(104) == 13


def test_task_count_for_K_2500_is_313() -> None:
    """Full M7 quota target K=2,500 → `ceil(2500/8) = 313`. The final
    task carries 4 trajectories per the §8.7 partial-pack note (cores
    4..7 idle on the final VM); the spec doesn't encode the per-task
    pack — that's the orchestrator's seed-partitioning concern (T2F)."""
    assert bjs.task_count_for_K(2500) == 313


def test_task_count_for_small_multiple_of_8() -> None:
    """K=8 → 1 task; K=16 → 2 tasks; K=296 → 37 tasks (the K=300 quota
    approval scenario from D-0070 sub-decision 7)."""
    assert bjs.task_count_for_K(8) == 1
    assert bjs.task_count_for_K(16) == 2
    assert bjs.task_count_for_K(296) == 37


def test_task_count_for_K_1_is_1() -> None:
    """Edge: K=1 → 1 task carrying 1 trajectory (cores 1..7 idle).
    Doesn't violate the dense-pack invariant — partial-pack is a
    legitimate state for the final task per §8.7."""
    assert bjs.task_count_for_K(1) == 1


def test_task_count_rejects_zero() -> None:
    for bad in (0, -1, -104):
        try:
            bjs.task_count_for_K(bad)
        except ValueError as e:
            assert "positive" in str(e).lower() or "K_approved" in str(e)
            continue
        raise AssertionError("task_count_for_K(" + repr(bad) + ") should have raised")


def test_task_count_rejects_non_int() -> None:
    for bad in (1.0, "104", None, [104]):
        try:
            bjs.task_count_for_K(bad)  # type: ignore[arg-type]
        except ValueError as e:
            assert "integer" in str(e).lower() or "K_approved" in str(e)
            continue
        raise AssertionError("task_count_for_K(" + repr(bad) + ") should have raised")


def test_task_count_rejects_bool() -> None:
    """`bool` is `int` subclass; reject `True`/`False` so they don't
    slip through as 1/0. Same boundary discipline as `solve()`."""
    for bad in (True, False):
        try:
            bjs.task_count_for_K(bad)  # type: ignore[arg-type]
        except ValueError as e:
            assert "integer" in str(e).lower()
            continue
        raise AssertionError("task_count_for_K(" + repr(bad) + ") should have raised")


# --- Spec shape (§8.7 invariants) ---------------------------------------


def _spec_for_K(K: int = 104) -> dict:
    return bjs.build_lahc_batch_job_spec(
        run_id=_RUN_ID, K_approved=K, container_image_uri=_IMAGE,
    )


def test_spec_has_one_task_group() -> None:
    spec = _spec_for_K()
    assert isinstance(spec["taskGroups"], list)
    assert len(spec["taskGroups"]) == 1


def test_spec_task_count_matches_K() -> None:
    spec = _spec_for_K(K=104)
    tg = spec["taskGroups"][0]
    assert tg["taskCount"] == 13
    assert tg["parallelism"] == 13, (
        "parallelism MUST equal taskCount per §8.7 — partial parallelism "
        "would serialize Batch task starts and miss the 240s wall budget."
    )


def test_spec_task_count_per_node_is_one() -> None:
    """§8.7 dense-pack invariant — one task per c3-highcpu-8 VM. Without
    this, Batch's bin-packer co-schedules tasks onto one VM, oversubscribing
    each VM whose multiprocessing.Pool(8) already saturates 8 vCPU."""
    spec = _spec_for_K()
    assert spec["taskGroups"][0]["taskCountPerNode"] == 1


def test_spec_machine_type_is_c3_highcpu_8() -> None:
    """§8.7: `c3-highcpu-8` (8 vCPU + 16 GB RAM, Sapphire Rapids) per
    D-0070 sub-decision 3."""
    spec = _spec_for_K()
    policy = spec["allocationPolicy"]["instances"][0]["policy"]
    assert policy["machineType"] == "c3-highcpu-8"


def test_spec_provisioning_model_is_standard() -> None:
    """§8.7: on-demand only per D-0070 sub-decision 4 — sync wall-time
    predictability. Spot pre-emption inside the 240s orchestrator
    deadline would silently fail jobs."""
    spec = _spec_for_K()
    policy = spec["allocationPolicy"]["instances"][0]["policy"]
    assert policy["provisioningModel"] == "STANDARD"


def test_spec_region_is_asia_southeast1() -> None:
    """§8.7: intra-region with Cloud Run Service + GCS bucket so egress
    is free. Drift would silently incur cross-region charges."""
    spec = _spec_for_K()
    locations = spec["allocationPolicy"]["location"]["allowedLocations"]
    assert locations == ["regions/asia-southeast1"]


def test_spec_per_task_max_run_duration_is_180s() -> None:
    """§8.7: 180s per-task wall covers VM provision ~30-60s + 8 parallel
    trajectories ~50-75s + GCS I/O ~5-10s + buffer ~5s. Drift past 180s
    blows the 240s orchestrator-side deadline budget."""
    spec = _spec_for_K()
    task_spec = spec["taskGroups"][0]["taskSpec"]
    assert task_spec["maxRunDuration"] == "180s"


def test_spec_per_task_max_retry_count_is_1() -> None:
    """§8.7: 1 retry on failure, fail-fast on second. Default Cloud
    Batch is 0; a single retry absorbs transient VM stalls without
    doubling worst-case wall on every run."""
    spec = _spec_for_K()
    task_spec = spec["taskGroups"][0]["taskSpec"]
    assert task_spec["maxRetryCount"] == 1


def test_spec_logs_destination_is_cloud_logging() -> None:
    """§8.7: logs to Cloud Logging (already enabled on the project from
    M4 C1). Maintainer reads job logs from the Cloud Logging UI."""
    spec = _spec_for_K()
    assert spec["logsPolicy"]["destination"] == "CLOUD_LOGGING"


def test_spec_compute_resource_claims_full_vm() -> None:
    """Defensive: cpuMilli=8000 + memoryMib=14000 fully claim the c3-highcpu-8
    so Batch's bin-packer keeps `taskCountPerNode=1` semantics even if the
    field were ever removed. memoryMib=14000 leaves ~2 GB headroom for OS +
    Batch agent on the 16 GB c3-highcpu-8."""
    spec = _spec_for_K()
    cr = spec["taskGroups"][0]["taskSpec"]["computeResource"]
    assert cr["cpuMilli"] == 8000
    assert cr["memoryMib"] == 14000


# --- Single-image dispatch ----------------------------------------------


def test_spec_commands_invoke_worker_module_with_run_id() -> None:
    """§8.7 single-image dispatch: `commands[]` runs the worker module
    entry with `--run-id`. Cloud Batch sets `BATCH_TASK_INDEX` per task
    automatically (worker reads it as `--task-index` default), so it
    doesn't need to appear in the override commands."""
    spec = _spec_for_K()
    runnable = spec["taskGroups"][0]["taskSpec"]["runnables"][0]
    cmds = runnable["container"]["commands"]
    assert cmds == [
        "python", "-m", "rostermonster_service.worker",
        "--run-id", _RUN_ID,
    ]


def test_spec_image_uri_passed_through() -> None:
    """The container image URI flows through unchanged. Same image as
    the deployed Cloud Run service (D-0050 single-image discipline)."""
    spec = _spec_for_K()
    runnable = spec["taskGroups"][0]["taskSpec"]["runnables"][0]
    assert runnable["container"]["imageUri"] == _IMAGE


def test_spec_carries_bucket_via_env() -> None:
    """The bucket name flows into the per-task env as `LAHC_BUCKET` so
    the worker's `_BUCKET_ENV` override path resolves to the right bucket
    (allows local-dev / staging buckets without re-baking the image)."""
    spec = bjs.build_lahc_batch_job_spec(
        run_id=_RUN_ID, K_approved=104,
        container_image_uri=_IMAGE,
        bucket="staging-lahc-bucket",
    )
    env = spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    assert env["LAHC_BUCKET"] == "staging-lahc-bucket"


def test_spec_default_bucket_is_production() -> None:
    """When `bucket` is omitted, defaults to the §8.7-pinned
    `rostermonsterv2-lahc` so production deploys don't need to thread
    the constant."""
    spec = _spec_for_K()
    env = spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    assert env["LAHC_BUCKET"] == "rostermonsterv2-lahc"


# --- Boundary validation ------------------------------------------------


def test_run_id_must_be_non_empty_string() -> None:
    for bad in ("", None, 42, ["a"]):
        try:
            bjs.build_lahc_batch_job_spec(
                run_id=bad,  # type: ignore[arg-type]
                K_approved=104, container_image_uri=_IMAGE,
            )
        except ValueError as e:
            assert "run_id" in str(e)
            continue
        raise AssertionError(
            "build_lahc_batch_job_spec(run_id=" + repr(bad)
            + ") should have raised"
        )


def test_container_image_uri_must_be_non_empty_string() -> None:
    for bad in ("", None, 42):
        try:
            bjs.build_lahc_batch_job_spec(
                run_id=_RUN_ID, K_approved=104,
                container_image_uri=bad,  # type: ignore[arg-type]
            )
        except ValueError as e:
            assert "container_image_uri" in str(e)
            continue
        raise AssertionError(
            "build_lahc_batch_job_spec(container_image_uri=" + repr(bad)
            + ") should have raised"
        )


def test_bucket_must_be_non_empty_string() -> None:
    for bad in ("", None, 42):
        try:
            bjs.build_lahc_batch_job_spec(
                run_id=_RUN_ID, K_approved=104, container_image_uri=_IMAGE,
                bucket=bad,  # type: ignore[arg-type]
            )
        except ValueError as e:
            assert "bucket" in str(e)
            continue
        raise AssertionError(
            "build_lahc_batch_job_spec(bucket=" + repr(bad)
            + ") should have raised"
        )


def test_K_approved_must_be_positive_int() -> None:
    """K_approved validation flows through to `task_count_for_K`."""
    for bad in (0, -1, "104", 1.5, None):
        try:
            bjs.build_lahc_batch_job_spec(
                run_id=_RUN_ID, K_approved=bad,  # type: ignore[arg-type]
                container_image_uri=_IMAGE,
            )
        except ValueError as e:
            assert "K_approved" in str(e) or "integer" in str(e).lower() or "positive" in str(e).lower()
            continue
        raise AssertionError(
            "build_lahc_batch_job_spec(K_approved=" + repr(bad)
            + ") should have raised"
        )


def test_per_task_max_retry_count_must_be_non_negative_int() -> None:
    """0 is valid (Batch default); negative + non-int reject."""
    # 0 is OK
    spec = bjs.build_lahc_batch_job_spec(
        run_id=_RUN_ID, K_approved=104, container_image_uri=_IMAGE,
        per_task_max_retry_count=0,
    )
    assert spec["taskGroups"][0]["taskSpec"]["maxRetryCount"] == 0
    # bad cases
    for bad in (-1, 1.0, True, "1"):
        try:
            bjs.build_lahc_batch_job_spec(
                run_id=_RUN_ID, K_approved=104, container_image_uri=_IMAGE,
                per_task_max_retry_count=bad,  # type: ignore[arg-type]
            )
        except ValueError as e:
            assert "per_task_max_retry_count" in str(e)
            continue
        raise AssertionError(
            "build_lahc_batch_job_spec(per_task_max_retry_count="
            + repr(bad) + ") should have raised"
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
