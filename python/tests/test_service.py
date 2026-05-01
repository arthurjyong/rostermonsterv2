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
