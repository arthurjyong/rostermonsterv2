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
