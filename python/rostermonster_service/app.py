"""Flask HTTP wrapper around `rostermonster.pipeline.run_pipeline()`.

Single endpoint per `docs/cloud_compute_contract.md` §6.2: `POST /compute`.

Request shape per §9.3:

    {
      "snapshot": { ...full Snapshot per docs/snapshot_contract.md... },
      "optionalConfig": { "maxCandidates": 32, "seed": 12345 }
    }

Response shape per §10.1: always HTTP 200 carrying a structured 4-state
envelope. Auth/infra failures (401/403/timeout/etc.) are surfaced by
Cloud Run before the service code runs, so we never emit those statuses
from this app.

Per `docs/decision_log.md` D-0051 sub-decision 1, this service is
intended to run on Cloud Run with scale-to-zero + max-5-instances. The
`if __name__ == "__main__"` block uses Flask's dev server only for
local testing; production deployment should use gunicorn (see
`cloud_compute_service/Dockerfile`).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from flask import Flask, Response, jsonify, request

from rostermonster.pipeline import (
    _assemble_writeback_wrapper,
    _snapshot_from_dict,
    run_pipeline,
)
from rostermonster.templates import icu_hd_template_artifact


log = logging.getLogger("rostermonster_service")

# Per `docs/decision_log.md` D-0054, Cloud Run runs as `--allow-unauthenticated`
# and the Flask app gates by validating the operator's Google ID token
# (sent via Authorization: Bearer <token> by the bound shim's
# `ScriptApp.getIdentityToken()`) and checking the email claim against
# the comma-separated `ALLOWED_EMAILS` env var. Operator-identity gating
# at app layer instead of platform-IAM layer because Apps Script's
# IdentityToken's `aud` claim doesn't match Cloud Run's expected service
# URL — the platform-IAM check would reject every request.
_ALLOWED_EMAILS_ENV = "ALLOWED_EMAILS"
# Skip allowlist enforcement entirely when this env var is unset. Used
# by the test_client harness (no Cloud Run env injection) so unit tests
# don't have to mock Google's token verification endpoint.
_DISABLE_AUTH_ENV = "DISABLE_AUTH_FOR_LOCAL_TESTING"


def create_app() -> Flask:
    """Application factory. Cloud Run / gunicorn / tests all use this."""
    app = Flask(__name__)

    # Body size limit per `docs/cloud_compute_contract.md` §9.5: HTTP/1.1
    # ceiling is Cloud Run's hard 32 MiB. We mirror that here so requests
    # past the ceiling fail fast with a 413 from Werkzeug rather than
    # consuming server resources.
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MiB

    @app.post("/compute")
    def compute() -> Response:
        # Stage 0: app-level operator-allowlist auth check per
        # `docs/decision_log.md` D-0054.
        auth_error = _check_operator_allowlist()
        if auth_error is not None:
            return auth_error
        return _compute_endpoint()

    return app


def _check_operator_allowlist() -> Response | None:
    """Validate the operator's ID token + check email allowlist per
    `docs/decision_log.md` D-0054. Returns a 200 INPUT_ERROR-shaped
    response on auth failure; returns None on success."""
    if os.environ.get(_DISABLE_AUTH_ENV):
        return None

    allowed = os.environ.get(_ALLOWED_EMAILS_ENV, "").strip()
    if not allowed:
        # Misconfiguration: Cloud Run service is public but allowlist
        # isn't set. Reject everything until the maintainer configures.
        log.error("ALLOWED_EMAILS env var not set; rejecting all requests")
        return jsonify({
            "state": "INPUT_ERROR",
            "writebackEnvelope": None,
            "error": {
                "code": "SERVICE_MISCONFIGURED",
                "message": "Cloud Run service has no ALLOWED_EMAILS env "
                           "var set. Maintainer must redeploy with "
                           "--set-env-vars ALLOWED_EMAILS=<comma-list>.",
            },
        })

    allowed_set = {e.strip().lower() for e in allowed.split(",") if e.strip()}

    # Per `docs/decision_log.md` D-0054, the operator's ID token is sent
    # in `X-Auth-Token`, NOT `Authorization`. Cloud Run drops the
    # standard `Authorization` header on `--allow-unauthenticated`
    # services to prevent token-leakage; using a custom header
    # bypasses that scrubbing.
    token = request.headers.get("X-Auth-Token", "").strip()
    if not token:
        return _auth_error(
            "MISSING_AUTH_TOKEN",
            "Request is missing the X-Auth-Token header carrying the "
            "operator's Google ID token.",
        )

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token
    except ImportError as e:
        log.exception("google-auth library not installed")
        return _auth_error(
            "AUTH_LIBRARY_UNAVAILABLE",
            f"Token verification library missing on the service. "
            f"Maintainer should redeploy. ({e})",
        )

    try:
        # `audience=None` means we don't enforce a specific audience —
        # the token's signature + expiry + email claim are still
        # verified by Google. Audience-mismatch was the original
        # blocker (D-0054); skipping the audience check is the
        # explicit decision recorded there.
        info = id_token.verify_oauth2_token(
            token, google_requests.Request(), audience=None,
        )
    except ValueError as e:
        return _auth_error(
            "INVALID_TOKEN",
            f"Token failed Google verification: {e}",
        )

    email = info.get("email", "").strip().lower()
    if not email:
        return _auth_error(
            "TOKEN_NO_EMAIL",
            "Token has no `email` claim. Bound shim must include "
            "`userinfo.email` in OAuth scopes per D-0051 sub-decision 3a.",
        )
    if not info.get("email_verified", False):
        return _auth_error(
            "EMAIL_NOT_VERIFIED",
            f"Token's email ({email}) is not verified by Google.",
        )
    if email not in allowed_set:
        log.warning(
            "Rejecting request from non-allowlisted email: %s "
            "(allowlist size: %d)", email, len(allowed_set),
        )
        return _auth_error(
            "EMAIL_NOT_ALLOWLISTED",
            f"Operator email '{email}' is not on the service's allowlist. "
            f"Maintainer must add it via Cloud Run env var ALLOWED_EMAILS.",
        )

    log.info("Authorized request from %s", email)
    return None


def _auth_error(code: str, message: str) -> Response:
    """Auth failures surface as INPUT_ERROR per
    `docs/cloud_compute_contract.md` §10.1 — the bound shim's UI
    dispatches on this state to show an error dialog."""
    return jsonify({
        "state": "INPUT_ERROR",
        "writebackEnvelope": None,
        "error": {"code": code, "message": message},
    })


def _compute_endpoint() -> Response:
    """POST /compute handler. Always returns HTTP 200 with a 4-state
    structured response per `docs/cloud_compute_contract.md` §10.1."""
    # --- Stage 1: parse request body --------------------------------------
    try:
        raw = request.get_json(silent=False)
    except Exception as e:
        return _input_error(
            "INVALID_REQUEST_BODY",
            f"Could not parse request body as JSON: {e}",
        )

    if raw is None or not isinstance(raw, dict):
        return _input_error(
            "INVALID_REQUEST_BODY",
            "Request body must be a JSON object with a `snapshot` field.",
        )

    if "snapshot" not in raw:
        return _input_error(
            "INVALID_REQUEST_BODY",
            "Request body is missing the required `snapshot` field "
            "per `docs/cloud_compute_contract.md` §9.3.",
        )

    snapshot_raw = raw["snapshot"]
    if not isinstance(snapshot_raw, dict):
        return _input_error(
            "INVALID_SNAPSHOT_SHAPE",
            "`snapshot` must be a JSON object.",
        )

    # --- Stage 2: deserialize snapshot ------------------------------------
    try:
        snapshot = _snapshot_from_dict(snapshot_raw)
    except (KeyError, TypeError, ValueError) as e:
        return _input_error(
            "INVALID_SNAPSHOT_SHAPE",
            f"Snapshot deserialization failed: {type(e).__name__}: {e}",
        )

    # --- Stage 3: validate optionalConfig ---------------------------------
    optional_raw = raw.get("optionalConfig", {}) or {}
    if not isinstance(optional_raw, dict):
        return _input_error(
            "INVALID_OPTIONAL_CONFIG",
            "`optionalConfig` must be a JSON object when present.",
        )

    try:
        max_candidates = _coerce_optional_int(
            optional_raw.get("maxCandidates"), "maxCandidates",
        )
        seed = _coerce_optional_int(
            optional_raw.get("seed"), "seed",
        )
    except _ConfigValidationError as e:
        return _input_error("INVALID_OPTIONAL_CONFIG", str(e))

    # --- Stage 4: run the shared compute core ----------------------------
    template = icu_hd_template_artifact()
    try:
        result = run_pipeline(
            snapshot,
            template,
            max_candidates=max_candidates,
            seed=seed,
        )
    except Exception as e:
        # Per `docs/cloud_compute_contract.md` §10.1, uncaught compute
        # exceptions surface as the structured COMPUTE_ERROR state, not
        # as a Flask 500. The traceback is logged server-side for
        # operator-facing debugging but NOT included in the response
        # body (no internal-only diagnostic content per §10.1 item 3).
        log.exception("compute pipeline raised an unexpected exception")
        return _compute_error(
            "COMPUTE_EXCEPTION",
            f"Compute pipeline raised an unexpected exception: "
            f"{type(e).__name__}: {e}",
        )

    # --- Stage 5: dispatch on PipelineResult.state -----------------------
    if result.state == "PARSER_NON_CONSUMABLE":
        # Parser rejected the snapshot at admission. Per §10.1 this maps
        # to INPUT_ERROR (parser-rejection is a request-content defect).
        issue_summary = "; ".join(
            f"[{i.severity}] {i.code}: {i.message}"
            for i in result.parser_issues[:5]
        )
        if len(result.parser_issues) > 5:
            issue_summary += (
                f" (+{len(result.parser_issues) - 5} more issues — "
                f"truncated for response brevity)"
            )
        return _input_error(
            "PARSER_REJECTED",
            f"Parser rejected the snapshot at admission with "
            f"{len(result.parser_issues)} issue(s): {issue_summary}",
        )

    # OK or UNSATISFIED — both populate `result.envelope`. Wrap with
    # snapshot subset + doctorIdMap so the bound shim hands the response
    # straight to `RMLib.applyWriteback(envelope)` per D-0052.
    assert result.envelope is not None
    wrapper_envelope = _assemble_writeback_wrapper(
        result.envelope, snapshot, template,
    )

    return jsonify({
        "state": "OK" if result.state == "OK" else "UNSATISFIED",
        "writebackEnvelope": wrapper_envelope,
        "error": None,
    })


def _input_error(code: str, message: str) -> Response:
    return jsonify({
        "state": "INPUT_ERROR",
        "writebackEnvelope": None,
        "error": {"code": code, "message": message},
    })


def _compute_error(code: str, message: str) -> Response:
    return jsonify({
        "state": "COMPUTE_ERROR",
        "writebackEnvelope": None,
        "error": {"code": code, "message": message},
    })


class _ConfigValidationError(ValueError):
    """Internal exception type for optionalConfig validation."""


def _coerce_optional_int(value: Any, field_name: str) -> int | None:
    """Coerce an optionalConfig field to int | None.

    None passes through (caller resolves to default). Booleans are
    rejected — `True`/`False` would coerce to 1/0 which is almost
    certainly a client bug. Strings, floats, dicts, lists, etc. are
    rejected.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # `bool` is a subclass of `int` in Python; reject explicitly.
        raise _ConfigValidationError(
            f"`{field_name}` must be an integer; got bool ({value!r})."
        )
    if isinstance(value, int):
        return value
    raise _ConfigValidationError(
        f"`{field_name}` must be an integer; got "
        f"{type(value).__name__} ({value!r})."
    )


# Module-level app for `flask --app rostermonster_service.app run` and
# for gunicorn (`gunicorn 'rostermonster_service.app:app'`).
app = create_app()


if __name__ == "__main__":
    # Cloud Run sets PORT in the container's env. Default to 8080 for
    # local development. The Flask dev server is for local testing
    # only — production deployment uses gunicorn (see Dockerfile).
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
