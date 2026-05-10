"""Tests for the M7 C2 Task 2F BatchClient adapter per
`python/rostermonster_service/batch_client.py`.

Production `BatchClient` wraps `google.cloud.batch_v1` (lazy-imported);
these tests exercise the `InMemoryBatchClient` test double instead so
they run without the SDK installed and without real GCP. The protocol
contract (submit_job / get_job_state / cancel_job + state-string
constants) is what consumers depend on.

Standalone runnable via `python3 python/tests/test_batch_client.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rostermonster_service.batch_client import (  # noqa: E402
    JOB_STATE_CANCELLED,
    JOB_STATE_FAILED,
    JOB_STATE_SUCCEEDED,
    TERMINAL_JOB_STATES,
    InMemoryBatchClient,
)


# --- Protocol constants -------------------------------------------------


def test_terminal_job_states_set() -> None:
    """Orchestrator uses `TERMINAL_JOB_STATES` to decide when polling
    can stop. MUST contain exactly SUCCEEDED / FAILED / CANCELLED —
    transient states like RUNNING / SCHEDULED MUST NOT be in the set."""
    assert TERMINAL_JOB_STATES == frozenset([
        JOB_STATE_SUCCEEDED, JOB_STATE_FAILED, JOB_STATE_CANCELLED,
    ])


def test_state_constant_string_values() -> None:
    """Names match the Cloud Batch v1 JobStatus.State enum string forms
    (`.name` attribute)."""
    assert JOB_STATE_SUCCEEDED == "SUCCEEDED"
    assert JOB_STATE_FAILED == "FAILED"
    assert JOB_STATE_CANCELLED == "CANCELLED"


def test_derive_batch_job_id_appends_unique_suffix() -> None:
    """The Batch job_id MUST differ from the artifact runId so a
    maintainer replay of the same `(snapshot, seed)` doesn't 409 on
    Batch's "job_id already exists" rule."""
    from rostermonster_service.batch_client import _derive_batch_job_id

    out = _derive_batch_job_id("my-run-id-001", unique_suffix="call-3")
    assert out == "my-run-id-001-call-3"


def test_derive_batch_job_id_truncates_to_63_chars() -> None:
    """Cloud Batch v1 caps job_id at 63 chars; the prefix gets
    truncated as needed to keep the unique suffix intact."""
    from rostermonster_service.batch_client import _derive_batch_job_id

    long_run_id = "a" * 100
    out = _derive_batch_job_id(long_run_id, unique_suffix="call-7")
    assert len(out) <= 63
    assert out.endswith("-call-7")


# --- InMemoryBatchClient ------------------------------------------------


def test_inmem_submit_records_job_metadata() -> None:
    """`submitted_jobs` exposes the (project, region, run_id, job_id,
    job_spec) tuple of every submitted job so tests can assert
    orchestrator dispatched the right thing. The Batch `job_id`
    differs from `run_id` per the per-call uniqueness rule (Cloud
    Batch rejects duplicate job_ids)."""
    client = InMemoryBatchClient()
    job_name = client.submit_job(
        project="rostermonsterv2", region="asia-southeast1",
        run_id="run-001", job_spec={"taskGroups": []},
    )
    assert len(client.submitted_jobs) == 1
    submitted = client.submitted_jobs[0]
    assert submitted["project"] == "rostermonsterv2"
    assert submitted["region"] == "asia-southeast1"
    assert submitted["run_id"] == "run-001"
    assert submitted["job_id"] == "run-001-call-1"
    assert submitted["job_spec"] == {"taskGroups": []}
    assert job_name == (
        "projects/rostermonsterv2/locations/asia-southeast1/jobs/run-001-call-1"
    )


def test_inmem_submit_generates_unique_job_id_per_call() -> None:
    """Cloud Batch rejects duplicate job_id within a project/region.
    The per-call counter on `InMemoryBatchClient` mirrors production's
    timestamp-based suffix so the orchestrator's idempotent-replay
    path doesn't depend on Batch idempotency."""
    client = InMemoryBatchClient()
    name_1 = client.submit_job(
        project="p", region="r", run_id="x", job_spec={},
    )
    name_2 = client.submit_job(
        project="p", region="r", run_id="x", job_spec={},
    )
    assert name_1 != name_2
    assert "call-1" in name_1
    assert "call-2" in name_2


def test_inmem_get_job_state_advances_through_sequence() -> None:
    """State sequence advances one step per get_job_state call. Once
    exhausted, clamps to last element so further polls stay terminal."""
    client = InMemoryBatchClient(
        state_sequence=["QUEUED", "SCHEDULED", "RUNNING", JOB_STATE_SUCCEEDED],
    )
    states = [client.get_job_state(job_name="x") for _ in range(6)]
    assert states == [
        "QUEUED", "SCHEDULED", "RUNNING", JOB_STATE_SUCCEEDED,
        JOB_STATE_SUCCEEDED, JOB_STATE_SUCCEEDED,
    ]


def test_inmem_default_state_sequence_is_succeeded() -> None:
    """Default `state_sequence=None` defaults to a single SUCCEEDED so
    the simplest test path doesn't need to specify."""
    client = InMemoryBatchClient()
    assert client.get_job_state(job_name="x") == JOB_STATE_SUCCEEDED


def test_inmem_cancel_records_job_name() -> None:
    """`cancelled_jobs` exposes the names of cancelled jobs so tests
    can assert the orchestrator's deadline-cancel path actually fired."""
    client = InMemoryBatchClient()
    client.cancel_job(job_name="projects/p/locations/r/jobs/j1")
    client.cancel_job(job_name="projects/p/locations/r/jobs/j2")
    assert client.cancelled_jobs == [
        "projects/p/locations/r/jobs/j1",
        "projects/p/locations/r/jobs/j2",
    ]


# --- Standalone runner ---------------------------------------------------


if __name__ == "__main__":
    failures = 0
    funcs = [(n, f) for n, f in globals().items()
             if n.startswith("test_") and callable(f)]
    for name, fn in funcs:
        try:
            fn()
            print("ok   " + name)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print("FAIL " + name + ": " + repr(exc))
    if failures:
        sys.exit(1)
