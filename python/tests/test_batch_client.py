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


# --- InMemoryBatchClient ------------------------------------------------


def test_inmem_submit_records_job_metadata() -> None:
    """`submitted_jobs` exposes the (project, region, run_id, job_spec)
    tuple of every submitted job so tests can assert orchestrator
    dispatched the right thing."""
    client = InMemoryBatchClient()
    job_name = client.submit_job(
        project="rostermonsterv2", region="asia-southeast1",
        run_id="run-001", job_spec={"taskGroups": []},
    )
    assert client.submitted_jobs == [{
        "project": "rostermonsterv2",
        "region": "asia-southeast1",
        "run_id": "run-001",
        "job_spec": {"taskGroups": []},
    }]
    assert job_name == "projects/rostermonsterv2/locations/asia-southeast1/jobs/run-001"


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
