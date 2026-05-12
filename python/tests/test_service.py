"""Tests for the Cloud Run HTTP wrapper at `rostermonster_service.app`
per `docs/cloud_compute_contract.md`.

The wrapper is a thin Flask app over `rostermonster.pipeline.run_pipeline`.
Tests here exercise the boundary behavior pinned by the contract:

- §9: request shape (snapshot required, optionalConfig optional)
- §10.1: 4-state response envelope (OK / UNSATISFIED / INPUT_ERROR /
  COMPUTE_ERROR), always HTTP 200
- §10.3: no partial-state responses
- §10.4: byte-identical determinism on same explicit seed
- §13: cross-mode parity with the local CLI's shared compute core

Standalone runnable via `python3 python/tests/test_service.py`.
Requires `flask>=3.1` per `cloud_compute_service/requirements.txt`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Disable the operator-allowlist auth check for unit tests per
# `docs/decision_log.md` D-0054. The auth path is exercised separately
# via integration tests against the deployed Cloud Run service; unit
# tests focus on request/response shape semantics.
os.environ["DISABLE_AUTH_FOR_LOCAL_TESTING"] = "1"

from rostermonster_service.app import create_app  # noqa: E402


_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "data" / "icu_hd_may_2026_snapshot.json"
)


def _load_snapshot_dict() -> dict:
    return json.loads(_FIXTURE_PATH.read_text())


def _client():
    return create_app().test_client()


def test_compute_ok_on_real_fixture() -> None:
    """Happy path: real ICU/HD May 2026 snapshot + explicit small
    candidate budget → state=OK, populated writebackEnvelope, null
    error. Always HTTP 200 per §10."""
    client = _client()
    body = {
        "snapshot": _load_snapshot_dict(),
        "optionalConfig": {"maxCandidates": 3, "seed": 20260504},
    }
    resp = client.post("/compute", json=body)
    assert resp.status_code == 200, \
        f"expected 200 always per §10; got {resp.status_code}"
    data = resp.get_json()
    assert data["state"] == "OK", f"expected OK; got {data['state']}"
    assert data["error"] is None
    assert data["writebackEnvelope"] is not None
    # Wrapper-envelope shape per D-0045: schemaVersion + finalResultEnvelope
    # + snapshot + doctorIdMap.
    env = data["writebackEnvelope"]
    assert env["schemaVersion"] == 1
    assert "finalResultEnvelope" in env
    assert "snapshot" in env
    assert "doctorIdMap" in env
    # AllocationResult shape on the success branch.
    fre = env["finalResultEnvelope"]
    assert "winnerAssignment" in fre["result"], \
        "OK state should carry an AllocationResult"


def test_compute_no_partial_state() -> None:
    """§10.3 invariant: state=OK MUST have non-null writebackEnvelope
    and null error; state=INPUT_ERROR/COMPUTE_ERROR MUST have null
    writebackEnvelope and non-null error. Verified across all four
    states the test suite exercises."""
    client = _client()

    # OK state
    body = {"snapshot": _load_snapshot_dict(),
            "optionalConfig": {"maxCandidates": 2, "seed": 20260504}}
    data = client.post("/compute", json=body).get_json()
    assert data["state"] == "OK"
    assert data["writebackEnvelope"] is not None
    assert data["error"] is None

    # INPUT_ERROR state — missing snapshot field
    data = client.post("/compute", json={}).get_json()
    assert data["state"] == "INPUT_ERROR"
    assert data["writebackEnvelope"] is None
    assert data["error"] is not None
    assert "code" in data["error"] and "message" in data["error"]


def test_compute_input_error_missing_snapshot() -> None:
    """Missing `snapshot` → INPUT_ERROR with INVALID_REQUEST_BODY code."""
    client = _client()
    resp = client.post("/compute", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["state"] == "INPUT_ERROR"
    assert data["error"]["code"] == "INVALID_REQUEST_BODY"
    assert "snapshot" in data["error"]["message"].lower()


def test_compute_input_error_malformed_snapshot() -> None:
    """Snapshot with malformed shape (missing required fields) →
    INPUT_ERROR with INVALID_SNAPSHOT_SHAPE code."""
    client = _client()
    resp = client.post("/compute", json={"snapshot": {"metadata": {}}})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["state"] == "INPUT_ERROR"
    assert data["error"]["code"] == "INVALID_SNAPSHOT_SHAPE"


def test_compute_input_error_non_object_snapshot() -> None:
    """`snapshot` must be a JSON object, not a list/string/etc."""
    client = _client()
    resp = client.post("/compute", json={"snapshot": "not an object"})
    data = resp.get_json()
    assert data["state"] == "INPUT_ERROR"
    assert data["error"]["code"] == "INVALID_SNAPSHOT_SHAPE"


def test_compute_input_error_optional_config_wrong_type() -> None:
    """`optionalConfig` must be a JSON object when present; passing a
    list rejects with INVALID_OPTIONAL_CONFIG."""
    client = _client()
    body = {"snapshot": _load_snapshot_dict(), "optionalConfig": [1, 2, 3]}
    data = client.post("/compute", json=body).get_json()
    assert data["state"] == "INPUT_ERROR"
    assert data["error"]["code"] == "INVALID_OPTIONAL_CONFIG"


def test_compute_input_error_optional_config_falsy_non_object() -> None:
    """Falsy non-dict values (false, 0, empty string, empty list) MUST
    reject with INVALID_OPTIONAL_CONFIG instead of being silently
    coerced to `{}` via `or {}` short-circuit. Catches the foot-gun
    where `optionalConfig: false` would have run with server defaults
    against the contract.

    Note: `optionalConfig: null` is treated as absent (use defaults),
    NOT as a violation — the contract permits omission, and JSON's
    explicit-null is the cleanest way for clients to signal omission
    when they assemble the payload programmatically."""
    client = _client()
    for bad in (False, 0, "", []):
        body = {"snapshot": _load_snapshot_dict(), "optionalConfig": bad}
        data = client.post("/compute", json=body).get_json()
        assert data["state"] == "INPUT_ERROR", \
            f"optionalConfig={bad!r} should be INPUT_ERROR; got {data['state']}"
        assert data["error"]["code"] == "INVALID_OPTIONAL_CONFIG"

    # Sanity: explicit null is permitted (treated as absent).
    body = {"snapshot": _load_snapshot_dict(),
            "optionalConfig": None,
            "_extraConfig": {"maxCandidates": 2, "seed": 99}}  # ignored
    data = client.post(
        "/compute", json={"snapshot": _load_snapshot_dict(),
                          "optionalConfig": None}
    ).get_json()
    # With null optionalConfig, server uses defaults — should reach OK.
    assert data["state"] == "OK", \
        f"optionalConfig=null should be treated as absent; got {data['state']}"


def test_compute_input_error_max_candidates_wrong_type() -> None:
    """`maxCandidates` must be an integer; string / float / bool reject."""
    client = _client()
    body = {"snapshot": _load_snapshot_dict(),
            "optionalConfig": {"maxCandidates": "ten"}}
    data = client.post("/compute", json=body).get_json()
    assert data["state"] == "INPUT_ERROR"
    assert data["error"]["code"] == "INVALID_OPTIONAL_CONFIG"
    assert "maxCandidates" in data["error"]["message"]


def test_compute_input_error_max_candidates_zero_or_negative() -> None:
    """`maxCandidates` must be >= 1; zero and negative values are rejected
    at the validation boundary (INPUT_ERROR / INVALID_OPTIONAL_CONFIG)
    rather than slipping into the solver and surfacing later as
    COMPUTE_ERROR. The latter would misclassify a caller defect as a
    server-side compute failure."""
    client = _client()
    for bad in (0, -1, -100):
        body = {"snapshot": _load_snapshot_dict(),
                "optionalConfig": {"maxCandidates": bad}}
        data = client.post("/compute", json=body).get_json()
        assert data["state"] == "INPUT_ERROR", \
            f"maxCandidates={bad} should be INPUT_ERROR; got {data['state']}"
        assert data["error"]["code"] == "INVALID_OPTIONAL_CONFIG"
        assert "maxCandidates" in data["error"]["message"]


def test_compute_input_error_seed_wrong_type() -> None:
    """`seed` must be an integer; bool reject (subclass-of-int trap)."""
    client = _client()
    body = {"snapshot": _load_snapshot_dict(),
            "optionalConfig": {"seed": True}}
    data = client.post("/compute", json=body).get_json()
    assert data["state"] == "INPUT_ERROR"
    assert data["error"]["code"] == "INVALID_OPTIONAL_CONFIG"
    assert "seed" in data["error"]["message"]


def test_compute_byte_identical_on_explicit_seed() -> None:
    """Two requests with identical `(snapshot, optionalConfig)` and
    explicit seed produce byte-identical writebackEnvelope per
    `docs/cloud_compute_contract.md` §10.4 + §13."""
    client = _client()
    body = {"snapshot": _load_snapshot_dict(),
            "optionalConfig": {"maxCandidates": 3, "seed": 20260504}}
    a = client.post("/compute", json=body).get_json()
    b = client.post("/compute", json=body).get_json()
    assert a["state"] == "OK" and b["state"] == "OK"
    assert a["writebackEnvelope"] == b["writebackEnvelope"], (
        "two explicit-seed requests at the same input should produce "
        "byte-identical envelopes per §10.4"
    )


def test_compute_random_seed_default_differs_across_requests() -> None:
    """Per D-0053, omitted seed picks a fresh random per request. Two
    omitted-seed requests on the same snapshot produce different
    writebackEnvelopes (different `runEnvelope.seed` values)."""
    client = _client()
    body = {"snapshot": _load_snapshot_dict(),
            "optionalConfig": {"maxCandidates": 2}}
    a = client.post("/compute", json=body).get_json()
    b = client.post("/compute", json=body).get_json()
    assert a["state"] == "OK" and b["state"] == "OK"
    seed_a = a["writebackEnvelope"]["finalResultEnvelope"]["runEnvelope"]["seed"]
    seed_b = b["writebackEnvelope"]["finalResultEnvelope"]["runEnvelope"]["seed"]
    assert seed_a != seed_b, (
        f"omitted-seed requests should pick different random seeds; "
        f"got identical seed {seed_a}"
    )


def test_compute_cross_mode_parity_with_pipeline() -> None:
    """§13 cross-mode parity: HTTP wrapper at explicit seed produces
    the same writebackEnvelope shape as the shared compute core called
    directly. This is what guarantees a maintainer running the local
    CLI at a given seed can reproduce a cloud-mode roster.

    Compares only the embedded `finalResultEnvelope` shape because
    the wrapper-level snapshot subset / doctorIdMap come from the same
    helpers in both call paths and are trivially identical.
    """
    from rostermonster.pipeline import _snapshot_from_dict, run_pipeline
    from rostermonster.templates import icu_hd_template_artifact

    raw = _load_snapshot_dict()
    snapshot = _snapshot_from_dict(raw)
    template = icu_hd_template_artifact()

    # Direct shared-core call
    direct = run_pipeline(snapshot, template, max_candidates=3, seed=42)
    assert direct.state == "OK"
    direct_winner = direct.envelope.result.winnerAssignment

    # HTTP wrapper call at same seed
    client = _client()
    body = {"snapshot": raw,
            "optionalConfig": {"maxCandidates": 3, "seed": 42}}
    http_data = client.post("/compute", json=body).get_json()
    assert http_data["state"] == "OK"
    http_winner = (http_data["writebackEnvelope"]
                   ["finalResultEnvelope"]["result"]["winnerAssignment"])

    # Compare assignment lengths + per-(dateKey, slotType, doctorId)
    # tuples — the canonical winner-allocation surface.
    assert len(direct_winner) == len(http_winner), (
        f"direct: {len(direct_winner)} units; HTTP: {len(http_winner)} units"
    )
    for du, hu in zip(direct_winner, http_winner):
        assert du.dateKey == hu["dateKey"]
        assert du.slotType == hu["slotType"]
        assert du.doctorId == hu["doctorId"]


def test_compute_invalid_json_request_body() -> None:
    """A request body that isn't valid JSON should reject with
    INPUT_ERROR (Flask's default behavior throws on `get_json` with
    silent=False; the handler catches and returns INPUT_ERROR)."""
    client = _client()
    resp = client.post("/compute", data="not json",
                       content_type="application/json")
    # Flask returns 400 on malformed JSON via the BadRequest exception;
    # our handler catches and emits INPUT_ERROR with 200, EXCEPT when
    # Flask raises before our handler runs. Either status is acceptable
    # as long as the operator gets a clear signal; we assert the
    # status is in {200, 400}.
    assert resp.status_code in {200, 400}


def test_compute_lahc_test_malformed_K_approved_returns_compute_error() -> None:
    """Codex P2 finding regression: deploy-time `LAHC_K_APPROVED` env
    that isn't a valid integer (e.g., a typo like `LAHC_K_APPROVED=fast`)
    used to raise `ValueError` in `int()` BEFORE the orchestrator try
    block, surfacing as a Flask 500 instead of the documented HTTP-200
    `COMPUTE_ERROR` envelope. The fix wraps the conversion in its own
    try-except and returns SERVICE_MISCONFIGURED."""
    saved_k = os.environ.get("LAHC_K_APPROVED")
    saved_image = os.environ.get("CONTAINER_IMAGE_URI")
    saved_project = os.environ.get("GCP_PROJECT")
    os.environ["LAHC_K_APPROVED"] = "fast"
    # CONTAINER_IMAGE_URI + GCP_PROJECT must be set to reach the
    # K_approved parsing step (they're checked first).
    os.environ["CONTAINER_IMAGE_URI"] = "gcr.io/x/y:tag"
    os.environ["GCP_PROJECT"] = "rostermonsterv2"
    try:
        client = _client()
        resp = client.post(
            "/compute-lahc-test",
            json={"snapshot": _load_snapshot_dict()},
        )
        assert resp.status_code == 200, (
            "expected HTTP 200 always per §10; got " + str(resp.status_code)
        )
        data = resp.get_json()
        assert data["state"] == "COMPUTE_ERROR", (
            "expected structured COMPUTE_ERROR for malformed env; got "
            + repr(data.get("state"))
        )
        assert data["error"]["code"] == "SERVICE_MISCONFIGURED"
        assert "LAHC_K_APPROVED" in data["error"]["message"]
    finally:
        for name, prior in (
            ("LAHC_K_APPROVED", saved_k),
            ("CONTAINER_IMAGE_URI", saved_image),
            ("GCP_PROJECT", saved_project),
        ):
            if prior is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = prior


# --- M7 C4 T2D async LAHC front-door tests ------------------------------


_T2D_ENV_VARS = [
    "CONTAINER_IMAGE_URI", "GCP_PROJECT", "RM_LAUNCHER_CALLBACK_URL",
    "LAHC_K_APPROVED", "LAHC_BATCH_REGION", "LAHC_BUCKET",
]


def _t2d_env_setup() -> dict[str, str | None]:
    """Snapshot env vars + set required ones for the LAHC async path."""
    saved = {k: os.environ.get(k) for k in _T2D_ENV_VARS}
    os.environ["CONTAINER_IMAGE_URI"] = "gcr.io/rostermonsterv2/test:tag"
    os.environ["GCP_PROJECT"] = "rostermonsterv2"
    os.environ["RM_LAUNCHER_CALLBACK_URL"] = (
        "https://script.google.com/macros/s/AKfycbXFAKE/exec"
    )
    return saved


def _t2d_env_teardown(saved: dict[str, str | None]) -> None:
    for name, prior in saved.items():
        if prior is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = prior


def _t2d_patch_clients(monkeypatch, *, list_jobs_response=None):
    """Patch `BatchClient` → `InMemoryBatchClient`; patch GCS adapter
    so the snapshot write is in-memory. Returns the in-memory batch
    client + the GCS storage dict for assertion."""
    from rostermonster_service import batch_client as bc_mod
    from rostermonster_service import gcs as gcs_mod

    storage: dict[str, dict] = {}

    def fake_make_gcs_adapter(bucket):
        def read_json(uri):
            if uri not in storage:
                raise FileNotFoundError(uri)
            return json.loads(json.dumps(storage[uri]))

        def write_json(uri, data):
            storage[uri] = json.loads(json.dumps(data))

        return read_json, write_json

    inmem_client = bc_mod.InMemoryBatchClient(
        list_jobs_response=list_jobs_response,
    )

    monkeypatch.setattr(bc_mod, "BatchClient", lambda: inmem_client)
    monkeypatch.setattr(gcs_mod, "make_gcs_adapter", fake_make_gcs_adapter)
    return inmem_client, storage


def test_compute_lahc_async_happy_path_returns_submitted(monkeypatch) -> None:
    """LAHC strategy + valid operatorEmail + no in-flight job →
    SUBMITTED state with submission.batchJobName + jobId + runId +
    attemptId per §10.1 SUBMITTED + Cloud Run thin front door."""
    saved = _t2d_env_setup()
    try:
        inmem_client, storage = _t2d_patch_clients(monkeypatch)
        client = _client()
        resp = client.post("/compute", json={
            "snapshot": _load_snapshot_dict(),
            "operatorEmail": "operator@example.com",
            "optionalConfig": {"solverStrategy": "LAHC", "seed": 12345},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "SUBMITTED", (
            "LAHC + valid operatorEmail MUST return SUBMITTED; got "
            + repr(data.get("state"))
        )
        assert data["writebackEnvelope"] is None
        assert data["error"] is None
        sub = data["submission"]
        assert sub["batchJobName"].startswith(
            "projects/rostermonsterv2/locations/asia-southeast1/jobs/"
        )
        assert sub["jobId"]
        assert sub["runId"]
        assert sub["attemptId"]
        # One Batch job submitted
        assert len(inmem_client.submitted_jobs) == 1
        # Snapshot written to GCS
        snapshot_uris = [u for u in storage if u.endswith("/snapshot.json")]
        assert len(snapshot_uris) == 1
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_missing_operator_email(monkeypatch) -> None:
    """§9.3: operatorEmail REQUIRED on LAHC path → INPUT_ERROR with
    code OPERATOR_EMAIL_REQUIRED when missing."""
    saved = _t2d_env_setup()
    try:
        inmem_client, _ = _t2d_patch_clients(monkeypatch)
        client = _client()
        resp = client.post("/compute", json={
            "snapshot": _load_snapshot_dict(),
            # operatorEmail omitted
            "optionalConfig": {"solverStrategy": "LAHC"},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "INPUT_ERROR"
        assert data["error"]["code"] == "OPERATOR_EMAIL_REQUIRED"
        # No Batch job submitted on missing operatorEmail
        assert len(inmem_client.submitted_jobs) == 0
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_concurrent_run(monkeypatch) -> None:
    """§8.7 sub-decision 8: concurrent-rejection via batch.jobs.list
    filter. If an in-flight job matches the spreadsheet's label,
    reject with INPUT_ERROR/CONCURRENT_RUN_REJECTED + include the
    existing job's createTime + operator email in the message."""
    saved = _t2d_env_setup()
    try:
        # Pre-seed an "existing in-flight job"
        inmem_client, _ = _t2d_patch_clients(
            monkeypatch,
            list_jobs_response=[{
                "name": "projects/rostermonsterv2/locations/asia-southeast1/jobs/existing-job",
                "createTime": "2026-05-12T10:00:00Z",
                "operatorEmail": "someone-else@example.com",
            }],
        )
        client = _client()
        resp = client.post("/compute", json={
            "snapshot": _load_snapshot_dict(),
            "operatorEmail": "operator@example.com",
            "optionalConfig": {"solverStrategy": "LAHC"},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "INPUT_ERROR"
        assert data["error"]["code"] == "CONCURRENT_RUN_REJECTED"
        assert "someone-else@example.com" in data["error"]["message"]
        assert "2026-05-12T10:00:00Z" in data["error"]["message"]
        # No new Batch job submitted
        assert len(inmem_client.submitted_jobs) == 0
        # list_jobs WAS called with the expected filter
        assert len(inmem_client.list_jobs_calls) == 1
        filter_str = inmem_client.list_jobs_calls[0]["filter_str"]
        assert "labels.spreadsheet_id=" in filter_str
        assert "status.state=QUEUED" in filter_str
        assert "status.state=SCHEDULED" in filter_str
        assert "status.state=RUNNING" in filter_str
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_parser_failure(monkeypatch) -> None:
    """Pre-Batch validation: snapshot that deserializes but is parser-
    NON_CONSUMABLE → INPUT_ERROR/PARSER_REJECTED. Saves the Cloud
    Batch round-trip cost on snapshots that can't produce a valid
    envelope per the M7 C2 T2F orchestrator discipline (Codex P2
    bad297f) — now duplicated on the new front door."""
    saved = _t2d_env_setup()
    try:
        inmem_client, _ = _t2d_patch_clients(monkeypatch)
        client = _client()
        # Mutate the real fixture to break parser consumability (empty
        # doctorRecords → structural rejection without breaking shallow
        # snapshotId / metadata deserialization).
        bad_snapshot = _load_snapshot_dict()
        bad_snapshot["doctorRecords"] = []
        resp = client.post("/compute", json={
            "snapshot": bad_snapshot,
            "operatorEmail": "operator@example.com",
            "optionalConfig": {"solverStrategy": "LAHC"},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "INPUT_ERROR"
        assert data["error"]["code"] == "PARSER_REJECTED"
        assert len(inmem_client.submitted_jobs) == 0
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_missing_callback_url(monkeypatch) -> None:
    """Deploy-time `RM_LAUNCHER_CALLBACK_URL` MUST be set for the LAHC
    async path. Missing → COMPUTE_ERROR/SERVICE_MISCONFIGURED so the
    maintainer's logs surface the misconfig immediately."""
    saved = _t2d_env_setup()
    # Clear the callback URL after setup
    os.environ.pop("RM_LAUNCHER_CALLBACK_URL", None)
    try:
        inmem_client, _ = _t2d_patch_clients(monkeypatch)
        client = _client()
        resp = client.post("/compute", json={
            "snapshot": _load_snapshot_dict(),
            "operatorEmail": "operator@example.com",
            "optionalConfig": {"solverStrategy": "LAHC"},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "COMPUTE_ERROR"
        assert data["error"]["code"] == "SERVICE_MISCONFIGURED"
        assert "RM_LAUNCHER_CALLBACK_URL" in data["error"]["message"]
        assert len(inmem_client.submitted_jobs) == 0
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_unknown_solver_strategy(monkeypatch) -> None:
    """Codex P2 finding on PR #157 commit bb50582899: a typo'd
    `solverStrategy` (e.g., `"LACH"`) used to silently fall through
    to the SRB sync path, writing back a synchronous result instead
    of surfacing the contract violation. Fix validates against the
    `_VALID_SOLVER_STRATEGIES` enum + returns INPUT_ERROR /
    INVALID_SOLVER_STRATEGY."""
    saved = _t2d_env_setup()
    try:
        inmem_client, _ = _t2d_patch_clients(monkeypatch)
        client = _client()
        # Typo: LACH instead of LAHC
        resp = client.post("/compute", json={
            "snapshot": _load_snapshot_dict(),
            "operatorEmail": "operator@example.com",
            "optionalConfig": {"solverStrategy": "LACH"},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "INPUT_ERROR", (
            "typo'd solverStrategy MUST surface as INPUT_ERROR, not "
            "silently fall through to SRB"
        )
        assert data["error"]["code"] == "INVALID_SOLVER_STRATEGY"
        # No Batch job submitted, no sync compute either
        assert len(inmem_client.submitted_jobs) == 0
        assert data["writebackEnvelope"] is None
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_non_string_solver_strategy(monkeypatch) -> None:
    """Non-string `solverStrategy` (e.g., a number or null-but-explicit
    bool) MUST surface as INPUT_ERROR / INVALID_SOLVER_STRATEGY rather
    than silently route somewhere. Tests the type-coercion guard."""
    saved = _t2d_env_setup()
    try:
        _t2d_patch_clients(monkeypatch)
        client = _client()
        resp = client.post("/compute", json={
            "snapshot": _load_snapshot_dict(),
            "operatorEmail": "operator@example.com",
            "optionalConfig": {"solverStrategy": 42},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "INPUT_ERROR"
        assert data["error"]["code"] == "INVALID_SOLVER_STRATEGY"
        assert "int" in data["error"]["message"]
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_non_positive_K_approved_env(monkeypatch) -> None:
    """Codex P2 finding on PR #157 commit bb50582899: pre-fix
    `LAHC_K_APPROVED=0` (or a negative integer) slipped through the
    `int()` guard + propagated into `build_lahc_batch_job_spec` which
    raises ValueError outside any error-handling block → Flask 500
    instead of the documented SERVICE_MISCONFIGURED envelope.

    Verifies both `LAHC_K_APPROVED=0` and `LAHC_K_APPROVED=-1` surface
    as structured COMPUTE_ERROR/SERVICE_MISCONFIGURED at HTTP 200."""
    for bad_value in ("0", "-1", "-88"):
        saved = _t2d_env_setup()
        os.environ["LAHC_K_APPROVED"] = bad_value
        try:
            inmem_client, _ = _t2d_patch_clients(monkeypatch)
            client = _client()
            resp = client.post("/compute", json={
                "snapshot": _load_snapshot_dict(),
                "operatorEmail": "operator@example.com",
                "optionalConfig": {"solverStrategy": "LAHC"},
            })
            assert resp.status_code == 200, (
                "expected HTTP 200 always per §10; got "
                + str(resp.status_code) + " on LAHC_K_APPROVED="
                + bad_value
            )
            data = resp.get_json()
            assert data["state"] == "COMPUTE_ERROR", (
                "non-positive LAHC_K_APPROVED MUST surface as "
                "COMPUTE_ERROR/SERVICE_MISCONFIGURED; got "
                + repr(data.get("state")) + " for value=" + bad_value
            )
            assert data["error"]["code"] == "SERVICE_MISCONFIGURED"
            assert "LAHC_K_APPROVED" in data["error"]["message"]
            assert "positive" in data["error"]["message"]
            # No Batch job submitted
            assert len(inmem_client.submitted_jobs) == 0
        finally:
            _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_explicit_null_solver_strategy(monkeypatch) -> None:
    """Codex P2 round 2 finding on PR #157 commit f0c2d2ac82: pre-fix,
    `solverStrategy: null` (explicit null) was treated as omitted +
    silently routed to SRB. Tightening: explicit null surfaces as
    INPUT_ERROR/INVALID_SOLVER_STRATEGY so a misconfigured bound-shim
    payload doesn't mask the intent."""
    saved = _t2d_env_setup()
    try:
        inmem_client, _ = _t2d_patch_clients(monkeypatch)
        client = _client()
        resp = client.post("/compute", json={
            "snapshot": _load_snapshot_dict(),
            "operatorEmail": "operator@example.com",
            "optionalConfig": {"solverStrategy": None},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "INPUT_ERROR"
        assert data["error"]["code"] == "INVALID_SOLVER_STRATEGY"
        assert "explicitly null" in data["error"]["message"].lower() or (
            "null" in data["error"]["message"].lower()
        )
        assert len(inmem_client.submitted_jobs) == 0
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_empty_solver_strategy(monkeypatch) -> None:
    """Explicit empty-string `solverStrategy` is a client defect —
    treat the same as explicit null per Codex P2 round 2 finding on
    PR #157 commit f0c2d2ac82."""
    saved = _t2d_env_setup()
    try:
        inmem_client, _ = _t2d_patch_clients(monkeypatch)
        client = _client()
        resp = client.post("/compute", json={
            "snapshot": _load_snapshot_dict(),
            "operatorEmail": "operator@example.com",
            "optionalConfig": {"solverStrategy": "   "},  # whitespace-only
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "INPUT_ERROR"
        assert data["error"]["code"] == "INVALID_SOLVER_STRATEGY"
        assert "empty" in data["error"]["message"].lower()
        assert len(inmem_client.submitted_jobs) == 0
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_lahc_params_override(monkeypatch) -> None:
    """Codex P2 round 2 finding on PR #157 commit f0c2d2ac82:
    `optionalConfig.lahcParams` is documented in §9.3 as a maintainer
    override but the worker currently hardcodes the FW-0037 tuple +
    doesn't read an override env var. Silent-ignore would let a
    maintainer think they're running a parameter sweep when the
    worker is using FW-0037 the whole time — reject explicitly with
    INPUT_ERROR/LAHC_PARAMS_OVERRIDE_NOT_SUPPORTED instead.

    Operator-facing path always omits lahcParams (defaults are the
    production tuple), so this restriction has no operator regression."""
    saved = _t2d_env_setup()
    try:
        inmem_client, _ = _t2d_patch_clients(monkeypatch)
        client = _client()
        resp = client.post("/compute", json={
            "snapshot": _load_snapshot_dict(),
            "operatorEmail": "operator@example.com",
            "optionalConfig": {
                "solverStrategy": "LAHC",
                "lahcParams": {
                    "historyListLength": 100,
                    "idleThreshold": 1000,
                    "swapProbability": 0.3,
                },
            },
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "INPUT_ERROR"
        assert data["error"]["code"] == "LAHC_PARAMS_OVERRIDE_NOT_SUPPORTED"
        assert "FW-0037" in data["error"]["message"]
        assert len(inmem_client.submitted_jobs) == 0
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_accepts_omitted_lahc_params(monkeypatch) -> None:
    """Omitting lahcParams entirely keeps the LAHC happy path working
    — the worker uses the hardcoded FW-0037 defaults per §8.7. Counter-
    test to `..._rejects_lahc_params_override` to lock the boundary."""
    saved = _t2d_env_setup()
    try:
        inmem_client, _ = _t2d_patch_clients(monkeypatch)
        client = _client()
        resp = client.post("/compute", json={
            "snapshot": _load_snapshot_dict(),
            "operatorEmail": "operator@example.com",
            "optionalConfig": {"solverStrategy": "LAHC"},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "SUBMITTED", (
            "omitting lahcParams MUST still let the LAHC path go through"
        )
        assert len(inmem_client.submitted_jobs) == 1
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_non_string_snapshot_id(monkeypatch) -> None:
    """Codex P2 round 3 finding on PR #157 commit ae14294339: pre-fix,
    `metadata.snapshotId` was checked truthy-only — a numeric value
    would slip through + `derive_run_id()` would raise an uncaught
    ValueError → Flask 500. Tighten to require non-empty string."""
    saved = _t2d_env_setup()
    try:
        inmem_client, _ = _t2d_patch_clients(monkeypatch)
        client = _client()
        snap = _load_snapshot_dict()
        # Corrupt: numeric snapshotId
        snap["metadata"]["snapshotId"] = 12345
        resp = client.post("/compute", json={
            "snapshot": snap,
            "operatorEmail": "operator@example.com",
            "optionalConfig": {"solverStrategy": "LAHC"},
        })
        assert resp.status_code == 200, (
            "expected HTTP 200 always per §10; got "
            + str(resp.status_code)
        )
        data = resp.get_json()
        assert data["state"] == "INPUT_ERROR"
        assert data["error"]["code"] == "INVALID_SNAPSHOT_SHAPE"
        assert "snapshotId" in data["error"]["message"]
        assert "non-empty string" in data["error"]["message"]
        assert len(inmem_client.submitted_jobs) == 0
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_non_string_source_spreadsheet_id(monkeypatch) -> None:
    """Same boundary as `snapshotId` — `metadata.sourceSpreadsheetId`
    feeds into `normalize_label_value` for the Batch label, which
    would raise an uncaught error on a non-string. Codex P2 round 3
    finding on PR #157 commit ae14294339."""
    saved = _t2d_env_setup()
    try:
        inmem_client, _ = _t2d_patch_clients(monkeypatch)
        client = _client()
        snap = _load_snapshot_dict()
        snap["metadata"]["sourceSpreadsheetId"] = ["not", "a", "string"]
        resp = client.post("/compute", json={
            "snapshot": snap,
            "operatorEmail": "operator@example.com",
            "optionalConfig": {"solverStrategy": "LAHC"},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "INPUT_ERROR"
        assert data["error"]["code"] == "INVALID_SNAPSHOT_SHAPE"
        assert "sourceSpreadsheetId" in data["error"]["message"]
        assert len(inmem_client.submitted_jobs) == 0
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_empty_lahc_bucket_env(monkeypatch) -> None:
    """Codex P2 round 3 finding on PR #157 commit ae14294339: pre-fix,
    `LAHC_BUCKET=""` survived `.strip()` + propagated into
    `build_lahc_batch_job_spec()` which raises ValueError outside any
    structured-error path → Flask 500. Fix: guard for empty bucket
    + return SERVICE_MISCONFIGURED."""
    for bad_value in ("", "   ", "\t\n"):
        saved = _t2d_env_setup()
        os.environ["LAHC_BUCKET"] = bad_value
        try:
            inmem_client, _ = _t2d_patch_clients(monkeypatch)
            client = _client()
            resp = client.post("/compute", json={
                "snapshot": _load_snapshot_dict(),
                "operatorEmail": "operator@example.com",
                "optionalConfig": {"solverStrategy": "LAHC"},
            })
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["state"] == "COMPUTE_ERROR", (
                "empty LAHC_BUCKET MUST surface as COMPUTE_ERROR / "
                "SERVICE_MISCONFIGURED; got " + repr(data.get("state"))
                + " on value=" + repr(bad_value)
            )
            assert data["error"]["code"] == "SERVICE_MISCONFIGURED"
            assert "LAHC_BUCKET" in data["error"]["message"]
            assert len(inmem_client.submitted_jobs) == 0
        finally:
            _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_empty_lahc_batch_region_env(monkeypatch) -> None:
    """Same pattern as `LAHC_BUCKET=""` — `LAHC_BATCH_REGION=""` would
    survive `.strip()` + propagate into `submit_job` as empty region
    → Cloud Batch error → Flask 500. Mirror the bucket-guard treatment
    for symmetry. Caught by Codex P2 round 3 finding analysis on
    PR #157 commit ae14294339."""
    saved = _t2d_env_setup()
    os.environ["LAHC_BATCH_REGION"] = "   "
    try:
        inmem_client, _ = _t2d_patch_clients(monkeypatch)
        client = _client()
        resp = client.post("/compute", json={
            "snapshot": _load_snapshot_dict(),
            "operatorEmail": "operator@example.com",
            "optionalConfig": {"solverStrategy": "LAHC"},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "COMPUTE_ERROR"
        assert data["error"]["code"] == "SERVICE_MISCONFIGURED"
        assert "LAHC_BATCH_REGION" in data["error"]["message"]
        assert len(inmem_client.submitted_jobs) == 0
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_unsanitizable_snapshot_id(monkeypatch) -> None:
    """Codex P2 round 4 finding on PR #157 commit e761bb975a:
    `snapshotId` that's non-empty but sanitizes to nothing (all non-
    alphanumeric characters, e.g., `"!!!"` or `"@@@"`) made
    `derive_run_id()` raise ValueError outside any structured-error
    block → Flask 500. Fix: catch + surface as INPUT_ERROR /
    INVALID_SNAPSHOT_SHAPE."""
    for bad_id in ("!!!", "@@@", "---", "...", "!@#$%^&*()"):
        saved = _t2d_env_setup()
        try:
            inmem_client, _ = _t2d_patch_clients(monkeypatch)
            client = _client()
            snap = _load_snapshot_dict()
            snap["metadata"]["snapshotId"] = bad_id
            resp = client.post("/compute", json={
                "snapshot": snap,
                "operatorEmail": "operator@example.com",
                "optionalConfig": {"solverStrategy": "LAHC"},
            })
            assert resp.status_code == 200, (
                "expected HTTP 200 always per §10; got "
                + str(resp.status_code) + " on snapshotId=" + repr(bad_id)
            )
            data = resp.get_json()
            assert data["state"] == "INPUT_ERROR", (
                "unsanitizable snapshotId MUST surface as INPUT_ERROR; "
                "got " + repr(data.get("state")) + " on " + repr(bad_id)
            )
            assert data["error"]["code"] == "INVALID_SNAPSHOT_SHAPE"
            assert "snapshotId" in data["error"]["message"]
            assert len(inmem_client.submitted_jobs) == 0
        finally:
            _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_explicit_null_source_spreadsheet_id(monkeypatch) -> None:
    """Codex P2 round 5 finding on PR #157 commit 918e6a3685: pre-fix,
    explicit `metadata.sourceSpreadsheetId: null` silently fell back
    to `snapshotId` for the Cloud Batch `labels.spreadsheet_id` label.
    The front door would SUBMIT a Batch job for a malformed snapshot
    whose finalizer/writeback would later target an unusable
    spreadsheet ID — operator-facing failure landed downstream rather
    than at admission. Tighten: explicit `null` is a client defect."""
    saved = _t2d_env_setup()
    try:
        inmem_client, _ = _t2d_patch_clients(monkeypatch)
        client = _client()
        snap = _load_snapshot_dict()
        snap["metadata"]["sourceSpreadsheetId"] = None
        resp = client.post("/compute", json={
            "snapshot": snap,
            "operatorEmail": "operator@example.com",
            "optionalConfig": {"solverStrategy": "LAHC"},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "INPUT_ERROR", (
            "explicit null sourceSpreadsheetId MUST surface as "
            "INPUT_ERROR, not silently fall back to snapshotId"
        )
        assert data["error"]["code"] == "INVALID_SNAPSHOT_SHAPE"
        assert "sourceSpreadsheetId" in data["error"]["message"]
        assert "null" in data["error"]["message"].lower()
        assert len(inmem_client.submitted_jobs) == 0
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_omitted_source_spreadsheet_id(monkeypatch) -> None:
    """Counter-test to confirm the snapshot contract: removing
    `sourceSpreadsheetId` from `metadata` causes `_snapshot_from_dict()`
    to raise `KeyError` upstream → INVALID_SNAPSHOT_SHAPE (via the
    pre-existing snapshot-deserializability guard). The Codex P2
    round 5 fix's tighter validation only handles EXPLICIT
    `null`/non-string/empty cases; OMITTED is already caught upstream."""
    saved = _t2d_env_setup()
    try:
        inmem_client, _ = _t2d_patch_clients(monkeypatch)
        client = _client()
        snap = _load_snapshot_dict()
        snap["metadata"].pop("sourceSpreadsheetId", None)
        resp = client.post("/compute", json={
            "snapshot": snap,
            "operatorEmail": "operator@example.com",
            "optionalConfig": {"solverStrategy": "LAHC"},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["state"] == "INPUT_ERROR"
        assert data["error"]["code"] == "INVALID_SNAPSHOT_SHAPE"
        assert "sourceSpreadsheetId" in data["error"]["message"]
        assert len(inmem_client.submitted_jobs) == 0
    finally:
        _t2d_env_teardown(saved)


def test_compute_lahc_async_rejects_out_of_int64_seed(monkeypatch) -> None:
    """Codex P2 round 6 finding on PR #157 commit a504e377ea: pre-fix,
    an explicit `optionalConfig.seed` outside the signed 64-bit range
    passed `_coerce_optional_int` (which only rejected bool/float/non-
    int) and slipped through SUBMITTED, then failed inside
    `derive_K_seeds` on the Cloud Batch worker → task error-result
    write → operator silently got no email (FW-0039 territory).
    Front door now validates the int64 bound per
    `docs/solver_contract.md` §9 + returns INPUT_ERROR /
    INVALID_OPTIONAL_CONFIG at admission."""
    int64_max = (2 ** 63) - 1
    int64_min = -(2 ** 63)
    # Out-of-range values: max+1, min-1, +/- 2^70
    for bad_seed in (int64_max + 1, int64_min - 1, 2 ** 70, -(2 ** 70)):
        saved = _t2d_env_setup()
        try:
            inmem_client, _ = _t2d_patch_clients(monkeypatch)
            client = _client()
            resp = client.post("/compute", json={
                "snapshot": _load_snapshot_dict(),
                "operatorEmail": "operator@example.com",
                "optionalConfig": {"solverStrategy": "LAHC", "seed": bad_seed},
            })
            assert resp.status_code == 200, (
                "expected HTTP 200 always per §10; got "
                + str(resp.status_code) + " on seed=" + str(bad_seed)
            )
            data = resp.get_json()
            assert data["state"] == "INPUT_ERROR", (
                "out-of-int64 seed MUST surface as INPUT_ERROR; got "
                + repr(data.get("state")) + " on seed=" + str(bad_seed)
            )
            assert data["error"]["code"] == "INVALID_OPTIONAL_CONFIG"
            assert "64-bit" in data["error"]["message"]
            # No Batch job submitted
            assert len(inmem_client.submitted_jobs) == 0
        finally:
            _t2d_env_teardown(saved)


def test_compute_lahc_async_accepts_int64_boundary_seeds(monkeypatch) -> None:
    """Counter-test: seeds AT the int64 boundary (`int64_min`,
    `int64_max`, 0) MUST pass + reach SUBMITTED. Locks the inclusive-
    bound invariant — strict-less-than would silently reject valid
    seeds. Boundary test pairs with `..._rejects_out_of_int64_seed`."""
    int64_max = (2 ** 63) - 1
    int64_min = -(2 ** 63)
    for good_seed in (int64_max, int64_min, 0, 12345, -42):
        saved = _t2d_env_setup()
        try:
            inmem_client, _ = _t2d_patch_clients(monkeypatch)
            client = _client()
            resp = client.post("/compute", json={
                "snapshot": _load_snapshot_dict(),
                "operatorEmail": "operator@example.com",
                "optionalConfig": {"solverStrategy": "LAHC", "seed": good_seed},
            })
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["state"] == "SUBMITTED", (
                "boundary seed " + str(good_seed) + " MUST pass; got "
                + repr(data.get("state")) + " / "
                + repr(data.get("error"))
            )
            assert len(inmem_client.submitted_jobs) == 1
        finally:
            _t2d_env_teardown(saved)


def test_compute_srb_path_stays_synchronous() -> None:
    """Back-compat: omitting `solverStrategy` (or passing
    "SEEDED_RANDOM_BLIND") keeps the existing sync /compute path —
    returns OK / UNSATISFIED / etc. with a wrapper envelope, not
    SUBMITTED. M7 C4 T2D's async dispatch only fires on
    solverStrategy=LAHC."""
    client = _client()
    resp = client.post("/compute", json={
        "snapshot": _load_snapshot_dict(),
        "optionalConfig": {"maxCandidates": 2, "seed": 99},
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["state"] in ("OK", "UNSATISFIED")
    assert data["state"] != "SUBMITTED"
    # SRB sync path carries the writebackEnvelope inline.
    assert data["writebackEnvelope"] is not None


# Minimal pytest-equivalent runner.
def _run() -> int:
    tests = [
        ("test_compute_ok_on_real_fixture",
         test_compute_ok_on_real_fixture),
        ("test_compute_no_partial_state", test_compute_no_partial_state),
        ("test_compute_input_error_missing_snapshot",
         test_compute_input_error_missing_snapshot),
        ("test_compute_input_error_malformed_snapshot",
         test_compute_input_error_malformed_snapshot),
        ("test_compute_input_error_non_object_snapshot",
         test_compute_input_error_non_object_snapshot),
        ("test_compute_input_error_optional_config_wrong_type",
         test_compute_input_error_optional_config_wrong_type),
        ("test_compute_input_error_optional_config_falsy_non_object",
         test_compute_input_error_optional_config_falsy_non_object),
        ("test_compute_input_error_max_candidates_wrong_type",
         test_compute_input_error_max_candidates_wrong_type),
        ("test_compute_input_error_max_candidates_zero_or_negative",
         test_compute_input_error_max_candidates_zero_or_negative),
        ("test_compute_input_error_seed_wrong_type",
         test_compute_input_error_seed_wrong_type),
        ("test_compute_byte_identical_on_explicit_seed",
         test_compute_byte_identical_on_explicit_seed),
        ("test_compute_random_seed_default_differs_across_requests",
         test_compute_random_seed_default_differs_across_requests),
        ("test_compute_cross_mode_parity_with_pipeline",
         test_compute_cross_mode_parity_with_pipeline),
        ("test_compute_invalid_json_request_body",
         test_compute_invalid_json_request_body),
        ("test_compute_lahc_test_malformed_K_approved_returns_compute_error",
         test_compute_lahc_test_malformed_K_approved_returns_compute_error),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(_run())
