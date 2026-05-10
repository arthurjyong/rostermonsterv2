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

import time
from typing import Any, Callable


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

# Cloud Batch v1 job_id length cap.
_BATCH_JOB_ID_MAX_LEN = 63


def _derive_batch_job_id(run_id: str, *, unique_suffix: str) -> str:
    """Cloud Batch's `create_job` REJECTS duplicate job_id within a
    project + region (per its v1 docs — the maintainer's idempotent
    replay path would 409 on the second submission if we reused the
    artifact runId verbatim as the Batch job_id). We disambiguate by
    appending a per-call unique suffix while keeping the prefix
    derived from runId for traceability.

    Artifact GCS keys remain idempotent — they live under `runId/...`
    not `batch_job_id/...`, so re-runs of the same (snapshot, seed)
    overwrite the same GCS paths. Batch job IDs are an internal Batch
    namespace concern; they don't appear in the artifact layout.
    """
    suffix = "-" + unique_suffix
    prefix_room = _BATCH_JOB_ID_MAX_LEN - len(suffix)
    if prefix_room < 1:
        # Pathological — unique_suffix alone exceeds the cap. Truncate.
        return suffix[1:_BATCH_JOB_ID_MAX_LEN + 1]
    return run_id[:prefix_room] + suffix


class BatchClient:
    """Production Cloud Batch client. Wraps `google.cloud.batch_v1`
    behind submit/get/cancel methods the orchestrator calls.

    Lazy-imports the SDK at construction so importing this module in
    test environments without google-cloud-batch installed is safe
    (tests use `InMemoryBatchClient` and never construct this class).

    `time_fn` is injectable so deterministic Batch job_id derivation
    is testable (production defaults to `time.time`)."""

    def __init__(self, *, time_fn: Callable[[], float] = time.time) -> None:
        from google.cloud import batch_v1  # local import per docstring rationale

        self._batch_v1 = batch_v1
        self._client = batch_v1.BatchServiceClient()
        self._time_fn = time_fn

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
        subsequent `get_job_state` / `cancel_job` calls.

        The Batch job_id is derived as `<truncated-runId>-<ms-timestamp>`
        per `_derive_batch_job_id` so a maintainer replay of the same
        `(snapshot, seed)` doesn't 409 on Batch's "job_id already
        exists" rule. Artifact GCS keys (under `runId/...`) remain
        idempotent — only the Batch job ID namespace gets per-call
        uniqueness."""
        from google.protobuf import json_format

        job = json_format.ParseDict(job_spec, self._batch_v1.Job())
        parent = "projects/" + project + "/locations/" + region
        unique_suffix = str(int(self._time_fn() * 1000))
        job_id = _derive_batch_job_id(run_id, unique_suffix=unique_suffix)
        result = self._client.create_job(
            parent=parent, job=job, job_id=job_id,
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

    `submitted_jobs` exposes the `(project, region, run_id, job_id,
    job_spec)` tuple of every submitted job for assertion in tests;
    `cancelled_jobs` exposes the names of cancelled jobs for assertion
    of the orchestrator's deadline-cancel path.

    Mirrors `BatchClient`'s per-call unique Batch job_id derivation but
    uses a monotonic counter (vs `time.time()`) so test assertions
    don't have to mock clocks — the Nth submit always uses
    `<run_id>-call-N`.
    """

    def __init__(
        self,
        state_sequence: list[str] | None = None,
    ) -> None:
        self._state_sequence = state_sequence or [JOB_STATE_SUCCEEDED]
        self._poll_count = 0
        self._submit_count = 0
        self.submitted_jobs: list[dict[str, Any]] = []
        self.cancelled_jobs: list[str] = []

    def submit_job(
        self, *,
        project: str,
        region: str,
        run_id: str,
        job_spec: dict[str, Any],
    ) -> str:
        self._submit_count += 1
        unique_suffix = "call-" + str(self._submit_count)
        job_id = _derive_batch_job_id(run_id, unique_suffix=unique_suffix)
        self.submitted_jobs.append({
            "project": project,
            "region": region,
            "run_id": run_id,
            "job_id": job_id,
            "job_spec": job_spec,
        })
        return "projects/" + project + "/locations/" + region + "/jobs/" + job_id

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
