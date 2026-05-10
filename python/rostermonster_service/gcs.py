"""GCS adapter shared by the M7 C2 worker (`worker.py` Task 2D) AND
orchestrator (`lahc_orchestrator.py` Task 2F).

`make_gcs_adapter(bucket)` returns a `(read_json, write_json)` pair of
closures bound to a single GCS bucket — both functions enforce that
incoming URIs start with `gs://{bucket}/` so cross-bucket access (a
common configuration drift) fails fast at the boundary rather than
silently writing to the wrong place.

Lazy-imports `google.cloud.storage` at adapter-construction time so test
environments without the SDK installed can still import the modules
that depend on this one (tests pass an in-memory adapter and never call
the factory).
"""

from __future__ import annotations

import json
from typing import Callable


# I/O port types — re-exported here so consumers don't need to define
# their own type aliases for an injected adapter.
ReadJsonFn = Callable[[str], dict]
WriteJsonFn = Callable[[str, dict], None]
DeletePrefixFn = Callable[[str], int]


def make_gcs_adapter(bucket: str) -> tuple[ReadJsonFn, WriteJsonFn]:
    """Production GCS adapter. Returns `(read_json, write_json)` closures
    bound to the supplied bucket. Both reject any URI not under
    `gs://{bucket}/...` to surface configuration drift at the boundary."""
    from google.cloud import storage  # local import per docstring rationale

    client = storage.Client()
    bkt = client.bucket(bucket)
    prefix = "gs://" + bucket + "/"

    def _check_uri(uri: str) -> str:
        if not uri.startswith(prefix):
            raise ValueError(
                "GCS URI '" + uri + "' does not start with expected prefix '"
                + prefix + "' (adapter is bound to bucket '" + bucket + "')"
            )
        return uri[len(prefix):]

    def read_json(uri: str) -> dict:
        key = _check_uri(uri)
        blob = bkt.blob(key)
        return json.loads(blob.download_as_text())

    def write_json(uri: str, data: dict) -> None:
        key = _check_uri(uri)
        blob = bkt.blob(key)
        blob.upload_from_string(
            json.dumps(data),
            content_type="application/json",
        )

    return read_json, write_json


def make_gcs_delete_prefix_fn(bucket: str) -> DeletePrefixFn:
    """Production prefix-delete adapter. Returns a `delete_prefix(uri)`
    closure that removes every blob whose key matches the supplied
    `gs://{bucket}/{prefix}` URI. Returns the count of blobs deleted.

    Used by the M7 C2 Task 2F orchestrator to clear stale per-task
    result.json files at `gs://{bucket}/{runId}/` BEFORE writing fresh
    snapshot/seeds for a replay attempt — the deterministic runId
    means a replay's new Batch job (with a unique job_id) writes to
    the same artifact prefix as the prior attempt; without
    invalidation, partial-failure aggregation would silently pick up
    the prior attempt's surviving result.jsons (Codex P1 finding on
    PR #143).

    Lazy-imports `google.cloud.storage` for parity with
    `make_gcs_adapter`."""
    from google.cloud import storage  # local import per docstring rationale

    client = storage.Client()
    bkt = client.bucket(bucket)
    bucket_uri_prefix = "gs://" + bucket + "/"

    def delete_prefix(uri: str) -> int:
        if not uri.startswith(bucket_uri_prefix):
            raise ValueError(
                "GCS URI '" + uri + "' does not start with expected prefix '"
                + bucket_uri_prefix + "' (adapter is bound to bucket '"
                + bucket + "')"
            )
        key_prefix = uri[len(bucket_uri_prefix):]
        if not key_prefix:
            # Refuse a bucket-wide wipe — caller almost certainly meant
            # a per-runId prefix and got the URI wrong.
            raise ValueError(
                "delete_prefix refuses empty prefix (bucket-wide wipe); "
                "got uri=" + repr(uri)
            )
        blobs = list(bkt.list_blobs(prefix=key_prefix))
        for blob in blobs:
            blob.delete()
        return len(blobs)

    return delete_prefix
