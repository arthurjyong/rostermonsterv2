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

import time

from flask import Flask, Response, g, jsonify, request

from rostermonster.parser import Consumability, parse
from rostermonster.pipeline import (
    _assemble_writeback_wrapper,
    _snapshot_from_dict,
    run_pipeline,
)
from rostermonster.templates import icu_hd_template_artifact

# M7 C2 Task 2F maintainer-only LAHC test route — see `_compute_lahc_test`
# below + `cloud_compute_contract.md` §6.2.
_LAHC_K_APPROVED_ENV = "LAHC_K_APPROVED"
_LAHC_DEFAULT_K_APPROVED = 88  # M7 C4 T2A.1 single-VM Pool(K) on c3-highcpu-88 (was 104 under the M7 C1 13-VM dense-pack design — Codex P1.7 single-VM amendment in PR #147 dropped K to 88 to fit the c3-highcpu-88 vCPU count); future quota bump to C3_CPUS≥176 unlocks K=176 via FW-0040.
_CONTAINER_IMAGE_URI_ENV = "CONTAINER_IMAGE_URI"
_GCP_PROJECT_ENV = "GCP_PROJECT"
# M7 C4 T2D deploy-time env: URL of the launcher's SECOND Web App
# deployment (USER_DEPLOYING, version-pinned per §10A.5) where the
# Cloud Batch worker's inline finalize step POSTs the callback per
# §10A. Set at Cloud Run deploy time via
# `--set-env-vars RM_LAUNCHER_CALLBACK_URL=<url>`.
_LAUNCHER_CALLBACK_URL_ENV = "RM_LAUNCHER_CALLBACK_URL"
# §8.7 single-task Batch job region.
_LAHC_BATCH_REGION_ENV = "LAHC_BATCH_REGION"
_LAHC_DEFAULT_BATCH_REGION = "asia-southeast1"
# §8.7 GCS bucket holding all M7 LAHC run artifacts.
_LAHC_BUCKET_ENV = "LAHC_BUCKET"
_LAHC_DEFAULT_BUCKET = "rostermonsterv2-lahc"

# Solver-strategy enum per `docs/solver_contract.md` §11.2. Front door
# routes LAHC to the new async path (M7 C4 T2D); SRB stays on the
# existing sync run_pipeline path. Anything else surfaces as
# INVALID_SOLVER_STRATEGY per Codex P2 finding on PR #157 commit
# bb50582899.
_VALID_SOLVER_STRATEGIES = frozenset({"SEEDED_RANDOM_BLIND", "LAHC"})

# Signed 64-bit integer bounds for `optionalConfig.seed` per
# `docs/solver_contract.md` §9. The Cloud Batch worker's
# `derive_K_seeds(masterSeed, K)` enforces this bound on the
# compute side; pre-validating it at the front door surfaces bad
# seed values at admission as INPUT_ERROR (without this guard, an
# out-of-range seed slips through SUBMITTED + the worker errors
# out without emailing the operator per FW-0039). Codex P2 round
# 6 finding on PR #157 commit a504e377ea.
_INT64_SIGNED_MIN = -(2 ** 63)
_INT64_SIGNED_MAX = (2 ** 63) - 1


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

    @app.post("/compute-lahc-test")
    def compute_lahc_test() -> Response:
        """Maintainer-only LAHC Cloud Batch test route per
        `docs/cloud_compute_contract.md` §6.2 — added at M7 C2 Task 2F
        to let the maintainer trigger the parallel cloud LAHC compute
        pipeline before §9 is amended at M7 C3 to recognize
        `solverStrategy="LAHC"` as a public input value. Same auth as
        `/compute` (operator-allowlist gating restricts to maintainer
        emails by config). Removed when the §9 amendment lands at M7
        C3 — the operator path then carries the public
        `solverStrategy` switch and this test path is no longer needed.
        """
        auth_error = _check_operator_allowlist()
        if auth_error is not None:
            return auth_error
        return _compute_lahc_test_endpoint()

    return app


_TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


def _is_truthy_env(name: str) -> bool:
    """Strict-parse a string env var as a boolean. Only `1`/`true`/`yes`/`on`
    (case-insensitive) count as truthy; everything else (including
    `0`/`false`/`no`/`off`/empty/unset) is falsy. Prevents the silent-
    open-allowlist bug where `DISABLE_AUTH_FOR_LOCAL_TESTING=false` would
    have read as truthy under a naive `os.environ.get(name)` check."""
    raw = os.environ.get(name)
    if raw is None:
        return False
    return raw.strip().lower() in _TRUTHY_ENV_VALUES


def _check_operator_allowlist() -> Response | None:
    """Validate the operator's ID token + check email allowlist per
    `docs/decision_log.md` D-0054. Returns a 200 INPUT_ERROR-shaped
    response on auth failure; returns None on success."""
    if _is_truthy_env(_DISABLE_AUTH_ENV):
        # Tests + local dev — no token to extract email from. Set to
        # empty string so LAHC dispatcher's operatorEmail match has a
        # sentinel to compare against (tests inject the empty match
        # explicitly via the request body's `operatorEmail: ""`).
        g.operator_email = ""
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
        from google.auth import exceptions as google_auth_exceptions
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
    except google_auth_exceptions.GoogleAuthError as e:
        # Cert-fetch / transport / refresh failures from the google-auth
        # library — distinct from the malformed-token ValueError branch
        # above. These are typically transient (Google's JWKS endpoint
        # transiently unreachable, etc.). Surface as INPUT_ERROR with a
        # distinct code so the bound shim can offer a "retry" affordance
        # later if needed; the structured envelope is preserved per
        # `docs/cloud_compute_contract.md` §10.
        log.exception("google-auth raised a non-ValueError verification error")
        return _auth_error(
            "TOKEN_VERIFICATION_TRANSPORT_ERROR",
            f"Token verification backend failed (transient): "
            f"{type(e).__name__}: {e}",
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
    # M7 C4 T2D: stash the validated operator email on Flask's
    # request-local `g` so the LAHC async dispatcher can match it
    # against the request body's `operatorEmail` field per §9.3
    # (LAHC requires operatorEmail to match the OIDC `email` claim
    # to prevent a maintainer spoofing the operator address on a
    # behalf-of-someone-else solve).
    g.operator_email = email
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
    """POST /compute handler. Always returns HTTP 200 with a 5-state
    structured response per `docs/cloud_compute_contract.md` §10.1 —
    `SUBMITTED` was added at M7 C3 + wired in T2D for the LAHC async
    path; the existing 4-state surface (OK / UNSATISFIED /
    INPUT_ERROR / COMPUTE_ERROR) continues on the SRB sync path."""
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

    # --- Solver-strategy dispatch (M7 C4 T2D) -----------------------------
    # Read solverStrategy from optionalConfig per §9.3. LAHC routes
    # through the async front-door (validate + submit Batch + return
    # SUBMITTED ~3-5s); SRB stays on the existing sync compute path.
    # Unknown / non-string values → INPUT_ERROR (Codex P2 finding on
    # PR #157 commit bb50582899 — pre-fix a typo like `"LACH"` would
    # silently fall through to SRB and write back a synchronous SRB
    # result instead of surfacing the contract violation).
    optional_block = raw.get("optionalConfig")
    if isinstance(optional_block, dict) and "solverStrategy" in optional_block:
        solver_strategy_raw = optional_block["solverStrategy"]
        # Explicit null / empty-string is a client defect — the contract
        # convention is "omit the field to default", not "send null".
        # Codex P2 round 2 finding on PR #157 commit f0c2d2ac82 — pre-
        # fix treated explicit null/"" as omitted + silently routed
        # SRB, which would mask a misconfigured bound-shim payload.
        if solver_strategy_raw is None:
            return _input_error(
                "INVALID_SOLVER_STRATEGY",
                "`optionalConfig.solverStrategy` is explicitly null. Omit "
                "the field to default to SEEDED_RANDOM_BLIND, or pass a "
                "valid enum value (" + ", ".join(sorted(_VALID_SOLVER_STRATEGIES))
                + ").",
            )
        if not isinstance(solver_strategy_raw, str):
            return _input_error(
                "INVALID_SOLVER_STRATEGY",
                "`optionalConfig.solverStrategy` must be a string when "
                "present per `docs/cloud_compute_contract.md` §9.3; got "
                + type(solver_strategy_raw).__name__,
            )
        solver_strategy = solver_strategy_raw.strip().upper()
        if solver_strategy == "":
            return _input_error(
                "INVALID_SOLVER_STRATEGY",
                "`optionalConfig.solverStrategy` is empty. Omit the "
                "field to default to SEEDED_RANDOM_BLIND, or pass a "
                "valid enum value (" + ", ".join(sorted(_VALID_SOLVER_STRATEGIES))
                + ").",
            )
        if solver_strategy not in _VALID_SOLVER_STRATEGIES:
            return _input_error(
                "INVALID_SOLVER_STRATEGY",
                "`optionalConfig.solverStrategy=" + repr(solver_strategy_raw)
                + "` is not a known strategy. Valid values per "
                "`docs/solver_contract.md` §11.2: "
                + ", ".join(sorted(_VALID_SOLVER_STRATEGIES)) + ".",
            )
    else:
        solver_strategy = ""
    if solver_strategy == "LAHC":
        return _compute_lahc_async_endpoint(raw=raw, snapshot_raw=snapshot_raw)

    # --- Stage 2: deserialize snapshot ------------------------------------
    try:
        snapshot = _snapshot_from_dict(snapshot_raw)
    except (KeyError, TypeError, ValueError) as e:
        return _input_error(
            "INVALID_SNAPSHOT_SHAPE",
            f"Snapshot deserialization failed: {type(e).__name__}: {e}",
        )

    # --- Stage 3: validate optionalConfig ---------------------------------
    # Treat absent / explicit-null as "use server defaults"; reject any
    # other non-dict value (false, 0, "", [], etc.) at the validation
    # boundary so falsy-but-present payloads can't slip through with
    # `or {}` short-circuit semantics. The latter would silently coerce
    # `optionalConfig: false` to `{}` and run with defaults instead of
    # surfacing the contract violation as INVALID_OPTIONAL_CONFIG.
    if "optionalConfig" not in raw or raw["optionalConfig"] is None:
        optional_raw: dict[str, Any] = {}
    else:
        optional_raw = raw["optionalConfig"]
    if not isinstance(optional_raw, dict):
        return _input_error(
            "INVALID_OPTIONAL_CONFIG",
            "`optionalConfig` must be a JSON object when present "
            "(got " + type(optional_raw).__name__ + ").",
        )

    try:
        max_candidates = _coerce_optional_int(
            optional_raw.get("maxCandidates"), "maxCandidates",
            min_val=1,
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


def _coerce_optional_int(value: Any, field_name: str, *,
                          min_val: int | None = None) -> int | None:
    """Coerce an optionalConfig field to int | None.

    None passes through (caller resolves to default). Booleans are
    rejected — `True`/`False` would coerce to 1/0 which is almost
    certainly a client bug. Strings, floats, dicts, lists, etc. are
    rejected. When `min_val` is provided, integers below it are also
    rejected — this keeps contract-invalid values like
    `maxCandidates: 0` surfacing as `INPUT_ERROR` /
    `INVALID_OPTIONAL_CONFIG` rather than slipping through into the
    solver and surfacing later as `COMPUTE_ERROR` (which would
    mis-classify a caller defect as a server-side compute failure).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # `bool` is a subclass of `int` in Python; reject explicitly.
        raise _ConfigValidationError(
            f"`{field_name}` must be an integer; got bool ({value!r})."
        )
    if not isinstance(value, int):
        raise _ConfigValidationError(
            f"`{field_name}` must be an integer; got "
            f"{type(value).__name__} ({value!r})."
        )
    if min_val is not None and value < min_val:
        raise _ConfigValidationError(
            f"`{field_name}` must be >= {min_val}; got {value!r}."
        )
    return value


def _compute_lahc_async_endpoint(
    *, raw: dict, snapshot_raw: dict,
) -> Response:
    """M7 C4 T2D async LAHC front door. Validate input + concurrent-
    rejection + submit Cloud Batch job + return SUBMITTED in ~3-5s.
    The actual compute runs in the Cloud Batch task's inline finalize
    step (per `worker.py` `_inline_finalize` at T2A.2 PR-A); the
    launcher Web App callback per §10A delivers the writeback +
    analyzer tabs + operator email asynchronously.

    Per `docs/cloud_compute_contract.md` §9.3:
    - `operatorEmail` REQUIRED top-level field (vs optional for SRB).
    - Must match OIDC `email` claim (`g.operator_email` set by
      `_check_operator_allowlist`) — prevents a maintainer-token spoof
      of an operator's address on a behalf-of-someone-else solve.

    Per §8.7 sub-decision 8 + D-0071 sub-decision 8: concurrent-
    rejection via `batch.jobs.list --filter='labels.spreadsheet_id=<x>
    AND (status.state=QUEUED OR status.state=SCHEDULED OR
    status.state=RUNNING)'` BEFORE submitting; reject with
    INPUT_ERROR/CONCURRENT_RUN_REJECTED if any matching in-flight
    job exists.
    """
    # --- operatorEmail validation -----------------------------------------
    operator_email_raw = raw.get("operatorEmail")
    if (not isinstance(operator_email_raw, str)
            or not operator_email_raw.strip()):
        return _input_error(
            "OPERATOR_EMAIL_REQUIRED",
            "`operatorEmail` is required on the LAHC strategy path per "
            "`docs/cloud_compute_contract.md` §9.3 (the Cloud Batch "
            "finalizer needs it for the always-email-on-every-outcome "
            "per §10A.7). Missing on this request.",
        )
    operator_email = operator_email_raw.strip().lower()
    # Match against the OIDC token's `email` claim — empty string when
    # DISABLE_AUTH_FOR_LOCAL_TESTING is set (tests inject the empty
    # match explicitly via the request body's `operatorEmail: ""`).
    token_email = getattr(g, "operator_email", "")
    if token_email and operator_email != token_email:
        return _input_error(
            "OPERATOR_EMAIL_MISMATCH",
            "`operatorEmail` field ('" + operator_email + "') does not "
            "match the OIDC token's `email` claim ('" + token_email
            + "'). The LAHC async path requires these to match per "
            "§9.3 (prevents a maintainer-token spoof of an operator's "
            "email address).",
        )

    # --- Snapshot deserializability + parser consumability ---------------
    # Pre-Batch validation — saves the Cloud Batch round-trip cost on
    # a snapshot that can't produce a valid envelope per the orchestrator
    # discipline locked at M7 C2 T2F Codex P2 findings 80e0ceb + bad297f
    # (now duplicated here for the new front door).
    try:
        snapshot_obj = _snapshot_from_dict(snapshot_raw)
    except (KeyError, TypeError, ValueError) as e:
        return _input_error(
            "INVALID_SNAPSHOT_SHAPE",
            "Snapshot deserialization failed: "
            + type(e).__name__ + ": " + str(e),
        )
    template = icu_hd_template_artifact()
    # Codex P2 round 7 finding on PR #157 commit 3f62f8130e: pre-fix,
    # `parse()` could raise on malformed nested fields that
    # `_snapshot_from_dict()` accepted (e.g.,
    # `dayRecords[0].rawDateText: null` survives deserialization
    # but trips `_validate_structural` on `.strip()`). Uncaught
    # exception made the LAHC path return Flask 500 HTML instead of
    # the documented always-200 structured envelope. Wrap to surface
    # as INPUT_ERROR/INVALID_SNAPSHOT_SHAPE at admission.
    try:
        parser_result = parse(snapshot_obj, template)
    except (AttributeError, TypeError, ValueError, KeyError) as e:
        return _input_error(
            "INVALID_SNAPSHOT_SHAPE",
            "Snapshot has a structural defect that "
            "`parser.parse()` couldn't handle: "
            + type(e).__name__ + ": " + str(e)
            + ". The snapshot deserialized OK at the boundary but "
            "a nested field (e.g., `dayRecords[*].rawDateText`, "
            "`doctorRecords[*].displayName`) is malformed. Fix the "
            "snapshot generator before re-submitting.",
        )
    if parser_result.consumability is not Consumability.CONSUMABLE:
        issue_summary = "; ".join(
            "[" + getattr(i.severity, "name", str(i.severity)) + "] "
            + i.code + ": " + i.message
            for i in parser_result.issues[:5]
        )
        if len(parser_result.issues) > 5:
            issue_summary += (
                " (+" + str(len(parser_result.issues) - 5) + " more "
                "issues — truncated for response brevity)"
            )
        return _input_error(
            "PARSER_REJECTED",
            "Parser rejected the snapshot at admission with "
            + str(len(parser_result.issues)) + " issue(s): "
            + issue_summary,
        )

    # --- Snapshot metadata for runId derivation + labels -----------------
    metadata = snapshot_raw.get("metadata") if isinstance(snapshot_raw, dict) else None
    if not isinstance(metadata, dict) or not metadata.get("snapshotId"):
        return _input_error(
            "INVALID_SNAPSHOT_SHAPE",
            "`snapshot.metadata.snapshotId` is required for the LAHC "
            "async path (used to derive the deterministic runId per "
            "§8.7). Got snapshot.metadata=" + repr(metadata),
        )
    # Codex P2 round 3 finding on PR #157 commit ae14294339: pre-fix
    # `metadata.snapshotId` was checked truthy-only — a numeric or
    # boolean-ish value would slip through + `derive_run_id()` would
    # raise an uncaught ValueError (Flask 500). Tighten to require
    # non-empty STRING for both snapshotId + sourceSpreadsheetId
    # before they feed runId derivation + Batch label normalization.
    raw_snapshot_id = metadata["snapshotId"]
    if not isinstance(raw_snapshot_id, str) or not raw_snapshot_id.strip():
        return _input_error(
            "INVALID_SNAPSHOT_SHAPE",
            "`snapshot.metadata.snapshotId` must be a non-empty string "
            "for the LAHC async path (used to derive runId via "
            "`derive_run_id()` + the Cloud Batch `labels.spreadsheet_id` "
            "label per §8.7 sub-decision 8). Got "
            + type(raw_snapshot_id).__name__ + "=" + repr(raw_snapshot_id),
        )
    snapshot_id = raw_snapshot_id.strip()
    # Codex P2 round 5 finding on PR #157 commit 918e6a3685: pre-fix,
    # explicit `sourceSpreadsheetId: null` was treated as absent +
    # silently fell back to snapshotId. That let the front door
    # SUBMIT a Batch job for a malformed snapshot whose finalizer
    # would later target an unusable spreadsheet ID — operator-
    # facing failure landed downstream rather than failing fast at
    # admission. Tighten: explicit `null` / non-string / empty-string
    # are all client defects. Field-absent never reaches this code
    # because `_snapshot_from_dict()` raises `KeyError` upstream on
    # missing `sourceSpreadsheetId` (snapshot contract requires it),
    # so we don't need a fall-back branch here.
    raw_source_spreadsheet_id = metadata.get("sourceSpreadsheetId")
    if raw_source_spreadsheet_id is None:
        return _input_error(
            "INVALID_SNAPSHOT_SHAPE",
            "`snapshot.metadata.sourceSpreadsheetId` is explicitly null "
            "or absent. The field is required per "
            "`docs/snapshot_contract.md` + used for the Cloud Batch "
            "`labels.spreadsheet_id` label per §8.7 sub-decision 8 + "
            "the concurrent-rejection query.",
        )
    if (not isinstance(raw_source_spreadsheet_id, str)
            or not raw_source_spreadsheet_id.strip()):
        return _input_error(
            "INVALID_SNAPSHOT_SHAPE",
            "`snapshot.metadata.sourceSpreadsheetId` must be a non-empty "
            "string (used for the Cloud Batch `labels.spreadsheet_id` "
            "label per §8.7 sub-decision 8 + concurrent-rejection "
            "query). Got " + type(raw_source_spreadsheet_id).__name__
            + "=" + repr(raw_source_spreadsheet_id),
        )
    source_spreadsheet_id = raw_source_spreadsheet_id.strip()

    # --- optionalConfig.seed (master seed) -------------------------------
    optional_block = raw.get("optionalConfig") or {}
    if not isinstance(optional_block, dict):
        return _input_error(
            "INVALID_OPTIONAL_CONFIG",
            "`optionalConfig` must be a JSON object when present.",
        )
    # `optionalConfig.lahcParams` is documented in §9.3 as a maintainer
    # override of the FW-0037 elbow tuple defaults, but the worker
    # currently hardcodes the production tuple + doesn't read an
    # override env var. Reject explicit non-empty overrides with a
    # clear "deferred" message rather than silently ignoring the field
    # — silent-ignore would let a maintainer think they're running a
    # parameter sweep when the worker is actually using FW-0037 the
    # whole time. Codex P2 round 2 finding on PR #157 commit
    # f0c2d2ac82. Honor-the-override is queued as a focused follow-up
    # (need new env vars on the Batch task + corresponding worker.py
    # reads). Production operator path always uses defaults so no
    # operator-facing regression from this restriction.
    lahc_params_raw = optional_block.get("lahcParams")
    if (lahc_params_raw is not None
            and lahc_params_raw != {}
            and lahc_params_raw != ""):
        return _input_error(
            "LAHC_PARAMS_OVERRIDE_NOT_SUPPORTED",
            "`optionalConfig.lahcParams` maintainer override is "
            "documented in `docs/cloud_compute_contract.md` §9.3 but "
            "is NOT plumbed through to the M7 C4 worker yet — the "
            "worker hardcodes the FW-0037 elbow tuple (L=50, "
            "idleThreshold=3500, swapProbability=0.5) per §8.7. "
            "Honor-the-override is queued as a focused follow-up; "
            "until then, omit this field (the documented production "
            "defaults are the M7 elbow tuple). Got "
            + repr(lahc_params_raw) + ".",
        )
    try:
        master_seed = _coerce_optional_int(
            optional_block.get("seed"), "seed",
        )
    except _ConfigValidationError as e:
        return _input_error("INVALID_OPTIONAL_CONFIG", str(e))
    # Codex P2 round 6 finding on PR #157 commit a504e377ea: pre-fix,
    # an explicit `optionalConfig.seed` outside the signed 64-bit
    # range passed the front door (`_coerce_optional_int` only
    # rejected bool/float/non-int) but failed inside `derive_K_seeds`
    # on the Cloud Batch worker → task error-result write → operator
    # gets NO email (silent-outcome gap per FW-0039). Validate the
    # int64 bound here per `docs/solver_contract.md` §9 so a bad
    # seed value surfaces at admission with the structured
    # INPUT_ERROR envelope.
    if master_seed is not None and not (
            _INT64_SIGNED_MIN <= master_seed <= _INT64_SIGNED_MAX):
        return _input_error(
            "INVALID_OPTIONAL_CONFIG",
            "`optionalConfig.seed=" + repr(master_seed) + "` is outside "
            "the 64-bit signed integer range required by "
            "`docs/solver_contract.md` §9 (master seed bound). Valid "
            "range: [" + str(_INT64_SIGNED_MIN) + ", "
            + str(_INT64_SIGNED_MAX) + "]. Out-of-range seeds would "
            "fail inside `derive_K_seeds` on the Cloud Batch worker "
            "AFTER the front door returned SUBMITTED, leaving the "
            "operator without a completion email (FW-0039 silent-"
            "outcome gap).",
        )
    if master_seed is None:
        # Per D-0053 — pick a fresh random seed when omitted so each
        # operator click explores a fresh point in the search space.
        import random
        master_seed = random.randint(0, 2**31 - 1)

    # --- Deploy-time env vars + dependency wiring ------------------------
    container_image_uri = os.environ.get(_CONTAINER_IMAGE_URI_ENV, "").strip()
    if not container_image_uri:
        return _compute_error(
            "SERVICE_MISCONFIGURED",
            "Cloud Run service has no " + _CONTAINER_IMAGE_URI_ENV
            + " env var set. Maintainer must redeploy with "
            "--set-env-vars " + _CONTAINER_IMAGE_URI_ENV + "=<image-uri>.",
        )
    project = os.environ.get(_GCP_PROJECT_ENV, "").strip()
    if not project:
        return _compute_error(
            "SERVICE_MISCONFIGURED",
            "Cloud Run service has no " + _GCP_PROJECT_ENV
            + " env var set. Maintainer must redeploy with "
            "--set-env-vars " + _GCP_PROJECT_ENV + "=<project-id>.",
        )
    launcher_callback_url = os.environ.get(
        _LAUNCHER_CALLBACK_URL_ENV, "",
    ).strip()
    if not launcher_callback_url:
        return _compute_error(
            "SERVICE_MISCONFIGURED",
            "Cloud Run service has no " + _LAUNCHER_CALLBACK_URL_ENV
            + " env var set. Maintainer must redeploy with "
            "--set-env-vars " + _LAUNCHER_CALLBACK_URL_ENV
            + "=<launcher callback URL>. Required for the M7 C4 T2D "
            "async LAHC path so the Cloud Batch finalizer can POST "
            "to the launcher per §10A.5.",
        )
    region = os.environ.get(
        _LAHC_BATCH_REGION_ENV, _LAHC_DEFAULT_BATCH_REGION,
    ).strip()
    if not region:
        # `LAHC_BATCH_REGION=""` (or whitespace-only) would survive
        # the `.strip()` + propagate into `submit_job` as an empty
        # region → Cloud Batch raises an uncaught error → Flask 500.
        # Mirror the bucket-guard treatment below for symmetry.
        return _compute_error(
            "SERVICE_MISCONFIGURED",
            "Cloud Run service has " + _LAHC_BATCH_REGION_ENV
            + " set to an empty/whitespace value. Maintainer must "
            "redeploy with --set-env-vars " + _LAHC_BATCH_REGION_ENV
            + "=<region-id> (or unset to use the default "
            + _LAHC_DEFAULT_BATCH_REGION + ").",
        )
    bucket = os.environ.get(
        _LAHC_BUCKET_ENV, _LAHC_DEFAULT_BUCKET,
    ).strip()
    if not bucket:
        # Codex P2 round 3 finding on PR #157 commit ae14294339:
        # pre-fix `LAHC_BUCKET=""` (or whitespace-only) survived
        # `.strip()` + `build_lahc_batch_job_spec()` raised an
        # uncaught ValueError → Flask 500 instead of the documented
        # SERVICE_MISCONFIGURED envelope. The other deploy-time env
        # checks above (CONTAINER_IMAGE_URI, GCP_PROJECT,
        # RM_LAUNCHER_CALLBACK_URL) already follow this pattern;
        # extending it to LAHC_BUCKET for symmetry.
        return _compute_error(
            "SERVICE_MISCONFIGURED",
            "Cloud Run service has " + _LAHC_BUCKET_ENV
            + " set to an empty/whitespace value. Maintainer must "
            "redeploy with --set-env-vars " + _LAHC_BUCKET_ENV
            + "=<bucket-name> (or unset to use the default "
            + _LAHC_DEFAULT_BUCKET + ").",
        )
    K_approved_str = os.environ.get(_LAHC_K_APPROVED_ENV)
    if K_approved_str:
        try:
            K_approved = int(K_approved_str)
        except ValueError:
            return _compute_error(
                "SERVICE_MISCONFIGURED",
                "Cloud Run service has " + _LAHC_K_APPROVED_ENV + "="
                + repr(K_approved_str) + " which is not a valid integer. "
                "Maintainer must redeploy with --set-env-vars "
                + _LAHC_K_APPROVED_ENV + "=<positive integer>.",
            )
        # Codex P2 finding on PR #157 commit bb50582899: pre-fix,
        # `LAHC_K_APPROVED=0` or a negative integer slipped through
        # the int() guard + propagated into `build_lahc_batch_job_spec`
        # which raises ValueError outside any structured-error path
        # → Flask 500 instead of the documented SERVICE_MISCONFIGURED
        # envelope. Guard here too.
        if K_approved <= 0:
            return _compute_error(
                "SERVICE_MISCONFIGURED",
                "Cloud Run service has " + _LAHC_K_APPROVED_ENV + "="
                + repr(K_approved_str) + " which is not a positive "
                "integer (parsed to " + str(K_approved) + "). "
                "K_approved must be > 0 per `docs/cloud_compute_contract.md` "
                "§8.7 single-VM dense-pack (Pool size must be positive). "
                "Maintainer must redeploy with --set-env-vars "
                + _LAHC_K_APPROVED_ENV + "=<positive integer>.",
            )
    else:
        K_approved = _LAHC_DEFAULT_K_APPROVED

    # Codex P2 round 8 finding on PR #157 commit d1fdbf4ac6: pre-fix,
    # `optionalConfig.maxCandidates` was documented in §9.3 +
    # `docs/solver_contract.md` §12A.3 defines LAHC outer-loop
    # termination as `K = maxCandidates`, but the async LAHC path
    # silently ignored it + ran deploy-time K_approved (default 88).
    # A maintainer experiment requesting `maxCandidates: 5` got
    # SUBMITTED but ran 88 trajectories, skewing benchmark/cost
    # comparisons. Honor the override here: if present + valid,
    # overrides the deploy-time K_approved (capped at deploy-time
    # capacity per the round 9 fix below).
    try:
        max_candidates_override = _coerce_optional_int(
            optional_block.get("maxCandidates"), "maxCandidates",
            min_val=1,
        )
    except _ConfigValidationError as e:
        return _input_error("INVALID_OPTIONAL_CONFIG", str(e))
    if max_candidates_override is not None:
        # Codex P2 round 9 finding on PR #157 commit e60372d464: pre-
        # fix the override forwarded uncapped to `K_approved`, but
        # `K` becomes the Pool(K) size on the c3-highcpu-88 VM (88
        # vCPUs). A maintainer requesting `maxCandidates: 500` would
        # spawn 500 worker processes contending for 88 cores,
        # blowing past the §8.7 single-VM dense-pack invariant +
        # likely missing the 10-min operator-facing cap. Cap at the
        # deploy-time `K_approved` (VM capacity) + reject excess.
        # Maintainer wanting higher K must redeploy with a higher
        # `LAHC_K_APPROVED` env (and the matching VM size) first.
        if max_candidates_override > K_approved:
            return _input_error(
                "MAX_CANDIDATES_EXCEEDS_VM_CAPACITY",
                "`optionalConfig.maxCandidates=" + str(max_candidates_override)
                + "` exceeds the deploy-time `K_approved="
                + str(K_approved) + "` (the Pool size matching the "
                "c3-highcpu-88 VM's vCPU count per §8.7). To run more "
                "trajectories, redeploy with `LAHC_K_APPROVED=<higher>` "
                "+ a VM size that fits (e.g., `c3-highcpu-176` for "
                "K=176 once `C3_CPUS` quota allows it per FW-0040). "
                "Pre-cap, oversized K would over-subscribe the VM "
                "(processes contending for vCPUs) and likely blow "
                "the 10-min operator-facing cap.",
            )
        K_approved = max_candidates_override

    # --- Wire SDK deps + concurrent-rejection ----------------------------
    try:
        from rostermonster_service.batch_client import BatchClient
        from rostermonster_service.batch_job_spec import (
            build_lahc_batch_job_spec,
            normalize_label_value,
        )
        from rostermonster_service.lahc_orchestrator import derive_run_id
        batch_client = BatchClient()
    except ImportError as e:
        return _compute_error(
            "ORCHESTRATOR_DEPS_UNAVAILABLE",
            "Cloud Batch SDK missing on the service. Maintainer should "
            "redeploy. (" + str(e) + ")",
        )

    # Concurrent-rejection query per §8.7 sub-decision 8 + Codex P2
    # round 11 fix (Cloud Batch filter syntax doesn't support SQL `IN`;
    # explicit OR-joined disjunction).
    spreadsheet_id_label = normalize_label_value(source_spreadsheet_id)
    concurrent_filter = (
        "labels.spreadsheet_id=" + spreadsheet_id_label
        + " AND (status.state=QUEUED OR status.state=SCHEDULED"
        " OR status.state=RUNNING)"
    )
    try:
        in_flight_jobs = batch_client.list_jobs(
            project=project, region=region,
            filter_str=concurrent_filter,
        )
    except Exception as e:  # noqa: BLE001
        log.exception("Concurrent-rejection list_jobs raised")
        return _compute_error(
            "CONCURRENT_CHECK_FAILED",
            "Cloud Batch concurrent-rejection query failed: "
            + type(e).__name__ + ": " + str(e),
        )
    if in_flight_jobs:
        existing = in_flight_jobs[0]
        return _input_error(
            "CONCURRENT_RUN_REJECTED",
            "A solve is already running for this spreadsheet "
            "(started at " + existing.get("createTime", "<unknown>")
            + " by " + (existing.get("operatorEmail") or "<unknown>")
            + "). Wait for completion (you'll receive an email when "
            "done) before submitting again.",
        )

    # --- Build + submit Batch job ----------------------------------------
    # Codex P2 round 4 finding on PR #157 commit e761bb975a: pre-fix,
    # a non-empty `snapshotId` that sanitizes to nothing (e.g.,
    # `"!!!"` → all special chars → `derive_run_id` strips them all)
    # caused `derive_run_id()` to raise `ValueError` outside any
    # structured-error block → Flask 500 instead of the documented
    # always-200 INPUT_ERROR envelope. Catch + surface here so the
    # boundary fails loud + structured.
    try:
        run_id = derive_run_id(snapshot_id, master_seed)
    except ValueError as e:
        return _input_error(
            "INVALID_SNAPSHOT_SHAPE",
            "`snapshot.metadata.snapshotId=" + repr(snapshot_id)
            + "` is not a valid runId-derivation input "
            "(sanitizes to empty after removing non-alphanumeric "
            "characters per `lahc_orchestrator.derive_run_id`). "
            "snapshotId must contain at least one alphanumeric "
            "character. Detail: " + str(e),
        )
    import uuid
    attempt_id = uuid.uuid4().hex
    submit_timestamp_ms = int(time.time() * 1000)
    job_spec = build_lahc_batch_job_spec(
        run_id=run_id,
        container_image_uri=container_image_uri,
        master_seed=master_seed,
        source_spreadsheet_id=source_spreadsheet_id,
        attempt_id=attempt_id,
        submit_timestamp_ms=submit_timestamp_ms,
        K_approved=K_approved,
        bucket=bucket,
        region=region,
        operator_email=operator_email,
        launcher_callback_url=launcher_callback_url,
    )
    # Write the snapshot to GCS so the worker can read it (the §8.7
    # input contract: worker reads `gs://bucket/runId/snapshot.json`).
    try:
        from rostermonster_service.gcs import make_gcs_adapter
        _, write_json = make_gcs_adapter(bucket)
        snapshot_uri = (
            "gs://" + bucket + "/" + run_id + "/snapshot.json"
        )
        write_json(snapshot_uri, snapshot_raw)
    except Exception as e:  # noqa: BLE001
        log.exception("Snapshot GCS write failed")
        return _compute_error(
            "SNAPSHOT_WRITE_FAILED",
            "Could not write snapshot to GCS: "
            + type(e).__name__ + ": " + str(e),
        )

    try:
        job_name = batch_client.submit_job(
            project=project, region=region,
            run_id=run_id, job_spec=job_spec,
        )
    except Exception as e:  # noqa: BLE001
        log.exception("Cloud Batch submit_job raised")
        return _compute_error(
            "BATCH_SUBMIT_FAILED",
            "Cloud Batch submit_job failed: "
            + type(e).__name__ + ": " + str(e),
        )
    log.info(
        "LAHC Batch job submitted: %s (run_id=%s, operator=%s)",
        job_name, run_id, operator_email,
    )

    return _submitted_response(
        batch_job_name=job_name,
        run_id=run_id,
        attempt_id=attempt_id,
    )


def _submitted_response(
    *, batch_job_name: str, run_id: str, attempt_id: str,
) -> Response:
    """§10.1 SUBMITTED-state envelope. `submission.batchJobName`
    surfaces the full resource name; `runId` + `attemptId` are
    diagnostic IDs the operator's email body references."""
    # `submission.jobId` is the trailing segment of the batch job name
    # for convenience (operators rarely paste the full resource path).
    job_id = batch_job_name.rsplit("/", 1)[-1] if "/" in batch_job_name else batch_job_name
    return jsonify({
        "state": "SUBMITTED",
        "writebackEnvelope": None,
        "error": None,
        "submission": {
            "batchJobName": batch_job_name,
            "jobId": job_id,
            "runId": run_id,
            "attemptId": attempt_id,
        },
    })


def _compute_lahc_test_endpoint() -> Response:
    """POST /compute-lahc-test handler (M7 C2 Task 2F). Same body shape
    as `/compute` but routes through the LAHC Cloud Batch orchestrator
    instead of in-process direct compute. Always returns HTTP 200 with
    a structured response per the M7 C2 Task 2F orchestrator contract."""
    # --- Stage 1: parse body (mirrors /compute Stages 1-2) -------------
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
    if "snapshot" not in raw or not isinstance(raw["snapshot"], dict):
        return _input_error(
            "INVALID_REQUEST_BODY",
            "Request body is missing the required `snapshot` field "
            "(must be a JSON object) per `docs/cloud_compute_contract.md` §9.3.",
        )
    snapshot_dict = raw["snapshot"]

    # --- Stage 2: optionalConfig (subset of /compute) ------------------
    if "optionalConfig" not in raw or raw["optionalConfig"] is None:
        optional_raw: dict[str, Any] = {}
    else:
        optional_raw = raw["optionalConfig"]
        if not isinstance(optional_raw, dict):
            return _input_error(
                "INVALID_OPTIONAL_CONFIG",
                "`optionalConfig` must be a JSON object when present.",
            )
    try:
        master_seed = _coerce_optional_int(
            optional_raw.get("seed"), "seed",
        )
    except _ConfigValidationError as e:
        return _input_error("INVALID_OPTIONAL_CONFIG", str(e))
    if master_seed is None:
        # Per D-0053 — pick a fresh random seed when omitted.
        import random
        master_seed = random.randint(0, 2**31 - 1)

    # --- Stage 3: deploy-time env vars + dependency wiring ------------
    container_image_uri = os.environ.get(_CONTAINER_IMAGE_URI_ENV, "").strip()
    if not container_image_uri:
        return _compute_error(
            "SERVICE_MISCONFIGURED",
            "Cloud Run service has no " + _CONTAINER_IMAGE_URI_ENV
            + " env var set. Maintainer must redeploy with "
            "--set-env-vars " + _CONTAINER_IMAGE_URI_ENV + "=<image-uri>.",
        )
    project = os.environ.get(_GCP_PROJECT_ENV, "").strip()
    if not project:
        return _compute_error(
            "SERVICE_MISCONFIGURED",
            "Cloud Run service has no " + _GCP_PROJECT_ENV
            + " env var set. Maintainer must redeploy with "
            "--set-env-vars " + _GCP_PROJECT_ENV + "=<project-id>.",
        )
    K_approved_str = os.environ.get(_LAHC_K_APPROVED_ENV)
    if K_approved_str:
        # Wrap the int() conversion so a malformed deploy-time env value
        # (e.g., LAHC_K_APPROVED=fast) surfaces as the structured
        # COMPUTE_ERROR envelope this endpoint documents — without the
        # wrap, the conversion raises ValueError pre-orchestrator-try
        # and the endpoint returns a Flask 500 instead.
        try:
            K_approved = int(K_approved_str)
        except ValueError:
            return _compute_error(
                "SERVICE_MISCONFIGURED",
                "Cloud Run service has " + _LAHC_K_APPROVED_ENV + "="
                + repr(K_approved_str) + " which is not a valid integer. "
                "Maintainer must redeploy with --set-env-vars "
                + _LAHC_K_APPROVED_ENV + "=<positive integer>.",
            )
    else:
        K_approved = _LAHC_DEFAULT_K_APPROVED

    # --- Stage 4: dispatch to the orchestrator ------------------------
    # The rostermonster_service modules import cleanly at the top-level
    # `from`-import statements below — google-cloud-storage and
    # google-cloud-batch are lazy-imported INSIDE the constructors
    # (`make_gcs_adapter`, `make_gcs_delete_prefix_fn`, `BatchClient()`),
    # so a deploy missing those SDKs raises ImportError at construction
    # time, not at the import line. The try block wraps BOTH the
    # imports AND the constructor calls so either failure mode surfaces
    # as the documented `ORCHESTRATOR_DEPS_UNAVAILABLE` envelope rather
    # than a Flask 500.
    try:
        from rostermonster_service.batch_client import BatchClient
        from rostermonster_service.gcs import (
            make_gcs_adapter,
            make_gcs_delete_prefix_fn,
        )
        from rostermonster_service.lahc_orchestrator import (
            orchestrate_lahc_run,
            _DEFAULT_BUCKET,
        )
        bucket = os.environ.get("LAHC_BUCKET", _DEFAULT_BUCKET).strip()
        read_json, write_json = make_gcs_adapter(bucket)
        delete_prefix = make_gcs_delete_prefix_fn(bucket)
        batch_client = BatchClient()
    except ImportError as e:
        return _compute_error(
            "ORCHESTRATOR_DEPS_UNAVAILABLE",
            "Cloud Batch / Storage SDK missing on the service. "
            "Maintainer should redeploy. (" + str(e) + ")",
        )

    try:
        response_dict = orchestrate_lahc_run(
            snapshot_dict,
            master_seed=master_seed,
            K_approved=K_approved,
            container_image_uri=container_image_uri,
            batch_client=batch_client,
            gcs_read_json=read_json,
            gcs_write_json=write_json,
            gcs_delete_prefix=delete_prefix,
            project=project,
            bucket=bucket,
        )
    except Exception as e:
        log.exception("lahc orchestrator raised")
        return _compute_error(
            "ORCHESTRATOR_EXCEPTION",
            "Orchestrator raised: " + type(e).__name__ + ": " + str(e),
        )

    return jsonify(response_dict)


# Module-level app for `flask --app rostermonster_service.app run` and
# for gunicorn (`gunicorn 'rostermonster_service.app:app'`).
app = create_app()


if __name__ == "__main__":
    # Cloud Run sets PORT in the container's env. Default to 8080 for
    # local development. The Flask dev server is for local testing
    # only — production deployment uses gunicorn (see Dockerfile).
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
