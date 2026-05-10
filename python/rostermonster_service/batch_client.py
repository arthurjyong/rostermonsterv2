"""Cloud Batch client adapter for the M7 C2 Task 2F orchestrator
(`lahc_orchestrator.py`). Wraps the google-cloud-batch v1 SDK behind a
narrow facade so the orchestrator can be tested against an in-memory
fake instead of real GCP.

`BatchClient` is the production class — lazy-imports `google.cloud.batch_v1`
at construction so test environments without the SDK installed can still
import this module (tests instantiate `InMemoryBatchClient` instead).

The orchestrator only needs three operations: submit a job, poll its
state, and cancel on the §8.7 240s orchestrator-side deadline overrun.
The full Batch v1 surface (job listing, deletion, task introspection)
is intentionally not wrapped here — the worker writes structured
result.json files to GCS, so the orchestrator never inspects per-task
state via the Batch API; it goes through GCS for everything except
job-level state polling.
"""

from __future__ import annotations

from typing import Any


# Terminal job states per the Cloud Batch v1 JobStatus.State enum. The
# orchestrator polls until one of these is reached (or the deadline
# elapses, in which case it issues a cancel + treats the run as a
# partial-task aggregation per §8.7).
JOB_STATE_SUCCEEDED = "SUCCEEDED"
JOB_STATE_FAILED = "FAILED"
JOB_STATE_CANCELLED = "CANCELLED"
TERMINAL_JOB_STATES = frozenset([
    JOB_STATE_SUCCEEDED, JOB_STATE_FAILED, JOB_STATE_CANCELLED,
])


class BatchClient:
    """Production Cloud Batch client. Wraps `google.cloud.batch_v1`
    behind submit/get/cancel methods the orchestrator calls.

    Lazy-imports the SDK at construction so importing this module in
    test environments without google-cloud-batch installed is safe
    (tests use `InMemoryBatchClient` and never construct this class)."""

    def __init__(self) -> None:
        from google.cloud import batch_v1  # local import per docstring rationale

        self._batch_v1 = batch_v1
        self._client = batch_v1.BatchServiceClient()

    def submit_job(
        self, *,
        project: str,
        region: str,
        run_id: str,
        job_spec: dict[str, Any],
    ) -> str:
        """Submit a Cloud Batch job using the dict spec from
        `batch_job_spec.build_lahc_batch_job_spec`. Returns the full job
        name (`projects/X/locations/Y/jobs/Z`) the caller passes to
        subsequent `get_job_state` / `cancel_job` calls."""
        from google.protobuf import json_format

        job = json_format.ParseDict(job_spec, self._batch_v1.Job())
        parent = "projects/" + project + "/locations/" + region
        # job_id MUST be unique per project+region; using run_id keeps it
        # deterministic + traceable. Cloud Batch accepts lowercase
        # alphanumerics + dashes only — orchestrator-side runId
        # construction MUST conform.
        result = self._client.create_job(
            parent=parent, job=job, job_id=run_id,
        )
        return result.name

    def get_job_state(self, *, job_name: str) -> str:
        """Poll the current state of a Batch job. Returns the string
        name of the `JobStatus.State` enum (e.g., `"RUNNING"`,
        `"SUCCEEDED"`)."""
        job = self._client.get_job(name=job_name)
        # JobStatus.State is an IntEnum; .name gives the readable string.
        return job.status.state.name

    def cancel_job(self, *, job_name: str) -> None:
        """Cancel a running Batch job. Returns the long-running operation
        handle from the SDK call but the orchestrator doesn't wait on it
        — partial-failure tolerance per §8.7 lets the orchestrator
        proceed to aggregation immediately + treat any incomplete task as
        contributing 0 candidates."""
        self._client.cancel_job(name=job_name)


class InMemoryBatchClient:
    """Test-only Batch client. Mirrors the `BatchClient` surface with
    deterministic state transitions controlled by the test harness.

    Tests configure a job's state trajectory at construction time:
    `InMemoryBatchClient(state_sequence=["QUEUED", "RUNNING", "SUCCEEDED"])`
    advances one step per `get_job_state` call. The default
    `state_sequence=["SUCCEEDED"]` makes the first poll terminal.

    `submitted_jobs` exposes the `(project, region, run_id, job_spec)`
    tuple of every submitted job for assertion in tests; `cancelled_jobs`
    exposes the names of cancelled jobs for assertion of the
    orchestrator's deadline-cancel path.
    """

    def __init__(
        self,
        state_sequence: list[str] | None = None,
    ) -> None:
        self._state_sequence = state_sequence or [JOB_STATE_SUCCEEDED]
        self._poll_count = 0
        self.submitted_jobs: list[dict[str, Any]] = []
        self.cancelled_jobs: list[str] = []

    def submit_job(
        self, *,
        project: str,
        region: str,
        run_id: str,
        job_spec: dict[str, Any],
    ) -> str:
        self.submitted_jobs.append({
            "project": project,
            "region": region,
            "run_id": run_id,
            "job_spec": job_spec,
        })
        return "projects/" + project + "/locations/" + region + "/jobs/" + run_id

    def get_job_state(self, *, job_name: str) -> str:
        # Advance through the configured sequence; clamp to the last
        # element once the sequence is exhausted (so further polls keep
        # returning the terminal state).
        if self._poll_count < len(self._state_sequence):
            state = self._state_sequence[self._poll_count]
        else:
            state = self._state_sequence[-1]
        self._poll_count += 1
        return state

    def cancel_job(self, *, job_name: str) -> None:
        self.cancelled_jobs.append(job_name)
