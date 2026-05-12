// AsyncRenderCallback.gs
//
// M7 C4 T2B launcher-side handler for the async B-prime callback per
// `docs/cloud_compute_contract.md` §10A. The Cloud Batch task's
// finalize step (worker.py `_inline_finalize`, landed at M7 C4 T2A.2
// PR-A) POSTs the wrapper envelope + analyzerOutput to the launcher's
// SECOND Web App deployment ("USER_DEPLOYING" + Access:ANYONE +
// version-pinned per §10A.5); this handler validates the auth token,
// dispatches to `RMLib.applyWriteback` / `RMLib.renderAnalysis`, and
// emails the operator the outcome via `MailApp.sendEmail`.
//
// **Deployment posture (§10A.5):** this file lives in the SAME Apps
// Script project as the operator-facing launcher routes; the
// difference is the deployment URL the request hits. The
// `Launcher.gs::doPost(e)` dispatcher routes `action=async-render-
// callback` POSTs through `handleAsyncRenderCallback_` below. The
// deployment-URL gate in `Launcher.gs` blocks operator-facing routes
// from being reachable via the callback deployment URL (security-
// critical per Codex P1 round 5 finding 9).
//
// **Auth (§10A.5):** OIDC ID token rides in the POST body's `idToken`
// field (Apps Script `doPost(e)` cannot read HTTP request headers per
// the official `Event Object` docs). Validation goes through Google's
// tokeninfo endpoint (`https://oauth2.googleapis.com/tokeninfo?id_token=<token>`)
// with required claims `aud == callback deployment URL`, `email ==
// Compute SA email`, `email_verified == true`. The SA email is
// hardcoded here (project number doesn't change post-create); rotated
// at the GCP project level if the project is ever migrated.
//
// **Idempotency (§10A.6):** the launcher caches `(runId, attemptId)`
// tuples in `PropertiesService.getScriptProperties()` so duplicate
// callbacks (e.g., from the finalizer's retry-on-5xx) return HTTP 200
// with `{state: "DUPLICATE_IGNORED"}` without re-invoking writeback /
// renderAnalysis / email.
//
// **State dispatch (§10A.6 + §10A.7):**
//   - OK: applyWriteback + renderAnalysis; success email iff BOTH
//     return SUCCESS, else failure email with the failure's
//     structured `error` field.
//   - UNSATISFIED: applyWriteback only (analyzerOutput null per
//     §10A.6 finding 8 + §12A.8); unsatisfied email iff applyWriteback
//     returns SUCCESS, else failure email.
//   - COMPUTE_ERROR: skip writeback + renderAnalysis; failure email
//     with the `error.code` + `error.message` from the body.

// SA email for the Cloud Batch finalizer task — `{project_number}-
// compute@developer.gserviceaccount.com` per §10A.5. Hardcoded
// because the project number is stable for the lifetime of the GCP
// project; rotated only if the project itself is migrated. M7 C2
// deployment lives in `rostermonsterv2` project number 693837275969.
var FINALIZER_SA_EMAIL_ = '693837275969-compute@developer.gserviceaccount.com';

// Idempotency cache key prefix in `ScriptProperties`. Per §10A.6 the
// dedup tuple is `(runId, attemptId)`. Keys are stripped after
// `IDEMPOTENCY_TTL_MS_` to keep the property store size bounded.
var IDEMPOTENCY_PROP_PREFIX_ = 'rm_callback_dedup_';

// Idempotency TTL: 24h. Cloud Batch tasks complete within the 10-min
// operator-facing cap, so a 24h dedup window vastly exceeds any
// realistic retry-on-5xx loop. Keeps the ScriptProperties surface
// bounded — ~10 entries/day at pilot scale.
var IDEMPOTENCY_TTL_MS_ = 24 * 60 * 60 * 1000;

// `CALLBACK_DEPLOYMENT_URL` ScriptProperty holds the callback
// deployment's `/exec` URL — the deployment-URL gate in `Launcher.gs`
// reads this to determine whether the current request is running
// under the operator-facing deployment or the callback deployment.
// Set during M7 C4 T2B deploy via the Apps Script editor's
// `PropertiesService.getScriptProperties().setProperty(...)` REPL.
var CALLBACK_DEPLOYMENT_URL_PROP_ = 'CALLBACK_DEPLOYMENT_URL';


function handleAsyncRenderCallback_(e) {
  // Top-level entry from Launcher.gs::doPost(e) when
  // `e.parameter.action === 'async-render-callback'`. Returns a
  // ContentService text response with the dispatch outcome; the
  // finalizer keys off the HTTP status (Apps Script returns 200 by
  // default on a successful return from doPost; thrown errors
  // become 500 to the caller). Per §10A.7 the finalizer retries on
  // 5xx and treats 4xx as terminal, so the handler MUST throw on
  // auth/validation failures (→ 5xx) ONLY when it's likely the
  // finalizer should retry; bad-request shapes return 4xx via an
  // explicit `_buildJsonResponse_(status=...)` helper below.

  if (!e || !e.postData) {
    return _buildJsonResponse_(400, {
      state: 'INVALID_CALLBACK',
      code: 'MISSING_POST_BODY',
    });
  }
  var bodyRaw;
  try {
    bodyRaw = e.postData.contents;
  } catch (err) {
    return _buildJsonResponse_(400, {
      state: 'INVALID_CALLBACK',
      code: 'BODY_READ_FAILED',
    });
  }
  if (!bodyRaw) {
    return _buildJsonResponse_(400, {
      state: 'INVALID_CALLBACK',
      code: 'EMPTY_BODY',
    });
  }
  var body;
  try {
    body = JSON.parse(bodyRaw);
  } catch (err) {
    return _buildJsonResponse_(400, {
      state: 'INVALID_CALLBACK',
      code: 'BODY_JSON_PARSE_FAILED',
    });
  }

  // Auth validation MUST run BEFORE any other field inspection per
  // §10A.5. Extract idToken + validate via tokeninfo + check claims.
  var idToken = body.idToken;
  if (!idToken || typeof idToken !== 'string') {
    return _buildJsonResponse_(401, {
      state: 'AUTH_REJECTED',
      code: 'ID_TOKEN_MISSING',
    });
  }
  var authResult = _validateIdToken_(idToken);
  if (!authResult.ok) {
    Logger.log(
      'Callback auth rejected: ' + authResult.code
      + ' (' + (authResult.detail || '') + ')'
    );
    return _buildJsonResponse_(401, {
      state: 'AUTH_REJECTED',
      code: authResult.code,
    });
  }

  // Strip idToken from the body before any logging / persistence per
  // §10A.5 — the token grants access for ~1h and shouldn't survive
  // in Cloud Logging or Properties Service.
  delete body.idToken;

  // Validate required body fields per §10A.6.
  var validationError = _validateCallbackBody_(body);
  if (validationError) {
    return _buildJsonResponse_(400, validationError);
  }

  // Idempotency check per §10A.6 — dedupe (runId, attemptId).
  var dedupKey = IDEMPOTENCY_PROP_PREFIX_ + body.runId + ':' + body.attemptId;
  var props = PropertiesService.getScriptProperties();
  var dedupEntry = props.getProperty(dedupKey);
  if (dedupEntry) {
    Logger.log(
      'Duplicate callback for runId=' + body.runId
      + ' attemptId=' + body.attemptId + ' — returning DUPLICATE_IGNORED'
    );
    return _buildJsonResponse_(200, {
      state: 'DUPLICATE_IGNORED',
      runId: body.runId,
      attemptId: body.attemptId,
    });
  }
  // Mark dedup tuple BEFORE dispatch so concurrent retries don't
  // double-dispatch. If dispatch fails the operator's email surfaces
  // the failure; the dedup entry stays so the finalizer's retry POST
  // doesn't double-render.
  props.setProperty(dedupKey, JSON.stringify({
    timestampMs: Date.now(),
    state: body.state,
  }));
  // Best-effort sweep of stale dedup entries on every callback —
  // keeps ScriptProperties bounded without a scheduled cleanup.
  _sweepStaleIdempotencyEntries_(props);

  // State dispatch per §10A.6.
  try {
    return _dispatchByState_(body);
  } catch (err) {
    Logger.log(
      'Callback dispatch raised for runId=' + body.runId
      + ' state=' + body.state + ': ' + err
    );
    // 500 → finalizer's retry-on-5xx kicks in. The dedup mark we set
    // above means the retry returns DUPLICATE_IGNORED if the failure
    // was transient (e.g., RMLib quota). Operator gets no email in
    // this path; falls into the FW-0039 silent-outcome gap.
    return _buildJsonResponse_(500, {
      state: 'DISPATCH_RAISED',
      code: 'INTERNAL_ERROR',
      message: String(err),
    });
  }
}


function _validateIdToken_(idToken) {
  // Validate via Google's tokeninfo endpoint per §10A.5. The endpoint
  // verifies the token's signature + expiry server-side; we then
  // check the `aud` / `email` / `email_verified` claims locally.
  var tokeninfoUrl = (
    'https://oauth2.googleapis.com/tokeninfo?id_token='
    + encodeURIComponent(idToken)
  );
  var response;
  try {
    response = UrlFetchApp.fetch(tokeninfoUrl, {
      method: 'get',
      muteHttpExceptions: true,
    });
  } catch (err) {
    return { ok: false, code: 'TOKENINFO_FETCH_FAILED', detail: String(err) };
  }
  if (response.getResponseCode() !== 200) {
    return {
      ok: false,
      code: 'TOKENINFO_REJECTED',
      detail: 'status=' + response.getResponseCode(),
    };
  }
  var claims;
  try {
    claims = JSON.parse(response.getContentText());
  } catch (err) {
    return { ok: false, code: 'TOKENINFO_PARSE_FAILED', detail: String(err) };
  }

  var expectedAud = PropertiesService.getScriptProperties().getProperty(
    CALLBACK_DEPLOYMENT_URL_PROP_
  );
  if (!expectedAud) {
    // Without the configured URL, we CAN'T validate `aud` — fail
    // closed (the maintainer must set CALLBACK_DEPLOYMENT_URL at
    // T2B deploy time).
    return {
      ok: false,
      code: 'CALLBACK_DEPLOYMENT_URL_UNCONFIGURED',
      detail: 'Maintainer must set the CALLBACK_DEPLOYMENT_URL script property',
    };
  }
  if (claims.aud !== expectedAud) {
    return {
      ok: false,
      code: 'AUD_MISMATCH',
      detail: 'expected=' + expectedAud + ' got=' + claims.aud,
    };
  }
  if (claims.email !== FINALIZER_SA_EMAIL_) {
    return {
      ok: false,
      code: 'EMAIL_MISMATCH',
      detail: 'expected=' + FINALIZER_SA_EMAIL_ + ' got=' + claims.email,
    };
  }
  // `email_verified` may come back as boolean true OR string "true"
  // depending on the token format — accept both per Google docs.
  if (claims.email_verified !== true && claims.email_verified !== 'true') {
    return {
      ok: false,
      code: 'EMAIL_NOT_VERIFIED',
      detail: 'email_verified=' + claims.email_verified,
    };
  }
  return { ok: true };
}


function _validateCallbackBody_(body) {
  // Verify §10A.6 required fields. Returns an error response object
  // or null if the body validates. Auth-related (idToken) is already
  // validated upstream; this checks the post-auth payload.
  if (body.schemaVersion !== 1) {
    return {
      state: 'INVALID_CALLBACK',
      code: 'UNSUPPORTED_SCHEMA_VERSION',
      message: 'expected schemaVersion=1, got ' + String(body.schemaVersion),
    };
  }
  if (!body.runId || typeof body.runId !== 'string') {
    return { state: 'INVALID_CALLBACK', code: 'RUN_ID_MISSING' };
  }
  if (!body.attemptId || typeof body.attemptId !== 'string') {
    return { state: 'INVALID_CALLBACK', code: 'ATTEMPT_ID_MISSING' };
  }
  if (!body.operatorEmail || typeof body.operatorEmail !== 'string') {
    // §10A.6 finding 5: launcher MUST reject with HTTP 400 +
    // OPERATOR_EMAIL_MISSING — no recipient to email otherwise.
    return { state: 'INVALID_CALLBACK', code: 'OPERATOR_EMAIL_MISSING' };
  }
  var validStates = { 'OK': true, 'UNSATISFIED': true, 'COMPUTE_ERROR': true };
  if (!validStates[body.state]) {
    return {
      state: 'INVALID_CALLBACK',
      code: 'INVALID_STATE',
      message: 'state must be OK / UNSATISFIED / COMPUTE_ERROR; got ' + String(body.state),
    };
  }
  return null;
}


function _dispatchByState_(body) {
  // §10A.6 state dispatch — invoke RMLib + send email per state.
  // Return values from RMLib are CHECKED before sending success
  // emails per Codex P2 round 13 + round 15 fixes (operator MUST
  // NOT get a "success" email if the tab didn't actually write).
  if (body.state === 'OK') {
    return _dispatchOk_(body);
  }
  if (body.state === 'UNSATISFIED') {
    return _dispatchUnsatisfied_(body);
  }
  // COMPUTE_ERROR
  return _dispatchComputeError_(body);
}


function _dispatchOk_(body) {
  // §10A.6 OK path: applyWriteback + renderAnalysis + check BOTH
  // return values before sending success email. Either FAILED →
  // failure email.
  //
  // **State strings** (Codex P1 fix on PR #154 commit b5b3c970be):
  // `RMLib.applyWriteback` returns `state: 'SUCCESS'` when it writes
  // a success tab (this OK path), `state: 'FAILED'` when it writes a
  // failure-branch tab (the UNSATISFIED path — handled in
  // `_dispatchUnsatisfied_`), `state: 'RUNTIME_ERROR'` when an
  // exception bubbles up. `RMLib.renderAnalysis` returns
  // `state: 'OK'` on success, `state: 'FAILED'` on any failure
  // (validation rejection or render-time exception).
  var writebackResult, analysisResult;
  try {
    // RMLib.applyWriteback takes a JSON STRING per §10A.1 + the
    // central library's `apps_script/central_library/src/Writeback.gs`
    // contract — the launcher MUST re-stringify the envelope object.
    writebackResult = RMLib.applyWriteback(
      JSON.stringify(body.writebackEnvelope)
    );
  } catch (err) {
    _sendFailureEmail_(body, {
      code: 'WRITEBACK_RAISED',
      message: 'applyWriteback raised: ' + String(err),
    });
    return _buildJsonResponse_(200, {
      state: 'OK_WRITEBACK_RAISED',
      runId: body.runId,
    });
  }
  if (!_writebackWroteSuccessTab_(writebackResult)) {
    // Codex P2 round 13: failure-from-writeback MUST surface as
    // failure email (NOT success) with the structured error. Any
    // non-`SUCCESS` state on the OK path is a writeback defect —
    // `FAILED` here would mean the library somehow chose the failure-
    // branch tab on a success envelope (shouldn't happen); `RUNTIME_ERROR`
    // means the library couldn't write any tab.
    _sendFailureEmail_(body, _resultToError_(writebackResult, 'writeback'));
    return _buildJsonResponse_(200, {
      state: 'OK_WRITEBACK_FAILED',
      runId: body.runId,
    });
  }

  try {
    // RMLib.renderAnalysis takes a single AnalyzerOutput arg per
    // §10A.1 + the central library's `apps_script/central_library/src/AnalysisRenderer.gs`
    // contract (object or string; library auto-parses).
    analysisResult = RMLib.renderAnalysis(body.analyzerOutput);
  } catch (err) {
    _sendFailureEmail_(body, {
      code: 'ANALYSIS_RAISED',
      message: 'renderAnalysis raised: ' + String(err),
    });
    return _buildJsonResponse_(200, {
      state: 'OK_ANALYSIS_RAISED',
      runId: body.runId,
    });
  }
  if (!_analysisRendered_(analysisResult)) {
    _sendFailureEmail_(body, _resultToError_(analysisResult, 'analysis'));
    return _buildJsonResponse_(200, {
      state: 'OK_ANALYSIS_FAILED',
      runId: body.runId,
    });
  }

  // Both succeeded — operator-facing success email + 2xx to finalizer.
  _sendSuccessEmail_(body);
  return _buildJsonResponse_(200, {
    state: 'OK',
    runId: body.runId,
  });
}


function _dispatchUnsatisfied_(body) {
  // §10A.6 UNSATISFIED path: applyWriteback only (failure-branch
  // envelope per §10.3 — bound shim's applyWriteback handles the
  // UnsatisfiedResultEnvelope shape + writes a FAILURE-BRANCH tab).
  // SKIP renderAnalysis per §10A.6 finding 8 + §12A.8 (analyzerOutput
  // is null on the failure branch).
  //
  // **Success criterion** (Codex P1 fix on PR #154 commit b5b3c970be):
  // for an UNSATISFIED envelope, `applyWriteback` returns
  // `state: 'FAILED'` on the SUCCESS path (= it successfully wrote
  // the failure-branch tab). `state: 'RUNTIME_ERROR'` is the
  // actually-failed-to-write surface; `state: 'SUCCESS'` would mean
  // the library wrote a success tab on a failure envelope (defect).
  // Codex P2 round 15: writeback return value MUST be checked before
  // sending the unsatisfied email.
  var writebackResult;
  try {
    writebackResult = RMLib.applyWriteback(
      JSON.stringify(body.writebackEnvelope)
    );
  } catch (err) {
    _sendFailureEmail_(body, {
      code: 'WRITEBACK_RAISED',
      message: 'applyWriteback (UNSATISFIED branch) raised: ' + String(err),
    });
    return _buildJsonResponse_(200, {
      state: 'UNSATISFIED_WRITEBACK_RAISED',
      runId: body.runId,
    });
  }
  if (!_writebackWroteFailureTab_(writebackResult)) {
    _sendFailureEmail_(body, _resultToError_(writebackResult, 'writeback'));
    return _buildJsonResponse_(200, {
      state: 'UNSATISFIED_WRITEBACK_FAILED',
      runId: body.runId,
    });
  }
  _sendUnsatisfiedEmail_(body);
  return _buildJsonResponse_(200, {
    state: 'UNSATISFIED',
    runId: body.runId,
  });
}


function _dispatchComputeError_(body) {
  // §10A.6 COMPUTE_ERROR path: skip applyWriteback + renderAnalysis
  // (both null per §10A.6); failure email only.
  _sendFailureEmail_(body, body.error || {
    code: 'COMPUTE_ERROR_UNKNOWN',
    message: 'COMPUTE_ERROR state with empty error block',
  });
  return _buildJsonResponse_(200, {
    state: 'COMPUTE_ERROR',
    runId: body.runId,
  });
}


function _writebackWroteSuccessTab_(result) {
  // `RMLib.applyWriteback` returns `state: 'SUCCESS'` when it wrote a
  // success tab (per `apps_script/central_library/src/Writeback.gs`
  // §17). Use ONLY on the OK callback path — on the UNSATISFIED
  // path, `state: 'FAILED'` is the success outcome (failure-branch
  // tab was written). Codex P1 fix on PR #154 commit b5b3c970be.
  if (!result || typeof result !== 'object') return false;
  return result.state === 'SUCCESS';
}


function _writebackWroteFailureTab_(result) {
  // `RMLib.applyWriteback` returns `state: 'FAILED'` when it wrote a
  // failure-branch tab (= success outcome on the UNSATISFIED
  // callback path). The library's diagnostic surface treats failure-
  // tab-written + failure-tab-not-written-due-to-RUNTIME_ERROR as
  // distinct states; only the former is a successful UNSATISFIED
  // dispatch. Codex P1 fix on PR #154 commit b5b3c970be.
  if (!result || typeof result !== 'object') return false;
  return result.state === 'FAILED';
}


function _analysisRendered_(result) {
  // `RMLib.renderAnalysis` returns `state: 'OK'` on success per
  // `apps_script/central_library/src/AnalysisRenderer.gs` §10
  // (NOT `state: 'SUCCESS'`; surface diverges from writeback's
  // success tag for historical reasons — the contracts evolved
  // separately). Any other state is a render failure.
  if (!result || typeof result !== 'object') return false;
  return result.state === 'OK';
}


function _resultToError_(result, surface) {
  // Coerce a RMLib failure result into the `error: {code, message}`
  // shape the failure email body expects. Surface ("writeback" /
  // "analysis") prefixes the code so the operator can tell which
  // step failed.
  var code = (result && result.error && result.error.code)
    ? String(result.error.code) : 'UNKNOWN';
  var message = (result && result.error && result.error.message)
    ? String(result.error.message)
    : (result && result.state)
      ? 'state=' + String(result.state)
      : 'no diagnostic available';
  return {
    code: surface.toUpperCase() + '_' + code,
    message: message,
  };
}


function _sendSuccessEmail_(body) {
  // §10A.7 success-path email body. Attaches the full AnalyzerOutput
  // JSON for forensic recovery per D-0071 sub-decision 5 + Codex P2
  // round 17 fix.
  var runIdShort = String(body.runId).substring(0, 24);
  var subject = '[RosterMonsterV2] Roster solve complete — runId ' + runIdShort;
  var lines = [
    'Hello,',
    '',
    'Your roster solve completed successfully.',
    '',
    'runId: ' + body.runId,
    'attemptId: ' + body.attemptId,
    'Trajectories: K\'=' + (body.diagnostics && body.diagnostics.kPrime)
      + ' of K=' + (body.diagnostics && body.diagnostics.kApproved)
      + ' (' + (body.diagnostics && body.diagnostics.droppedCount) + ' dropped)',
    'Wall time: '
      + ((body.diagnostics && body.diagnostics.wallTimeSeconds)
         ? body.diagnostics.wallTimeSeconds + 's'
         : '<unknown>'),
    '',
    'The writeback tab and analysis sheets have been written to the source spreadsheet.',
    '',
    'Cloud Batch job: '
      + ((body.diagnostics && body.diagnostics.batchJobName) || '<unknown>'),
  ];
  var options = {};
  if (body.analyzerOutput) {
    options.attachments = [_buildAnalyzerOutputBlob_(body, runIdShort)];
  }
  MailApp.sendEmail(body.operatorEmail, subject, lines.join('\n'), options);
}


function _sendUnsatisfiedEmail_(body) {
  var runIdShort = String(body.runId).substring(0, 24);
  var subject = '[RosterMonsterV2] Roster solve unsatisfied — runId ' + runIdShort;
  var unfilledSummary = '<unavailable>';
  try {
    var envelope = body.writebackEnvelope;
    if (envelope && envelope.finalResultEnvelope
        && envelope.finalResultEnvelope.result
        && envelope.finalResultEnvelope.result.unfilledDemand) {
      var count = envelope.finalResultEnvelope.result.unfilledDemand.length;
      unfilledSummary = String(count) + ' unfilled demand entries';
    }
  } catch (err) {
    // Swallow — keep going with the email send.
  }
  var lines = [
    'Hello,',
    '',
    'No valid roster was found under the request constraints.',
    '',
    'runId: ' + body.runId,
    'attemptId: ' + body.attemptId,
    'Unfilled: ' + unfilledSummary,
    'Wall time: '
      + ((body.diagnostics && body.diagnostics.wallTimeSeconds)
         ? body.diagnostics.wallTimeSeconds + 's'
         : '<unknown>'),
    '',
    'The failure-branch writeback tab has been written; check it for the unfilled-demand details.',
    '',
    'Cloud Batch job: '
      + ((body.diagnostics && body.diagnostics.batchJobName) || '<unknown>'),
  ];
  MailApp.sendEmail(body.operatorEmail, subject, lines.join('\n'));
}


function _sendFailureEmail_(body, error) {
  var runIdShort = String(body.runId).substring(0, 24);
  var subject = '[RosterMonsterV2] Roster solve failed — '
    + (error && error.code ? error.code : 'UNKNOWN');
  var lines = [
    'Hello,',
    '',
    'Your roster solve did not complete successfully.',
    '',
    'runId: ' + body.runId,
    'attemptId: ' + body.attemptId,
    'Error code: ' + (error && error.code ? error.code : '<unknown>'),
    'Error: ' + (error && error.message ? error.message : '<no detail>'),
    'Wall time: '
      + ((body.diagnostics && body.diagnostics.wallTimeSeconds)
         ? body.diagnostics.wallTimeSeconds + 's'
         : '<unknown>'),
    '',
    'Cloud Batch job: '
      + ((body.diagnostics && body.diagnostics.batchJobName) || '<unknown>'),
    '',
    'Please retry by clicking "Solve Roster" in the bound spreadsheet again. '
      + 'If the error persists, contact the maintainer with the runId above.',
  ];
  // Failure path may still carry an AnalyzerOutput if the defect
  // happened post-analyzer (rare; e.g., callback POST gymnastic).
  // Attach if present per §10A.7's failure-path attachment rule.
  var options = {};
  if (body.analyzerOutput) {
    options.attachments = [_buildAnalyzerOutputBlob_(body, runIdShort)];
  }
  MailApp.sendEmail(body.operatorEmail, subject, lines.join('\n'), options);
}


function _buildAnalyzerOutputBlob_(body, runIdShort) {
  // `MailApp.sendEmail` `attachments` option requires `BlobSource[]`
  // (https://developers.google.com/apps-script/reference/mail/mail-app)
  // — NOT plain `{fileName, mimeType, content}` dicts. Pre-fix passed
  // a plain object which made `sendEmail` throw AFTER the writeback +
  // analyzer tabs had already been written; the outer try/catch
  // returned 500 + the dedup key was already recorded → the
  // finalizer's retry-on-5xx returned `DUPLICATE_IGNORED` → operator
  // never received the completion email. Real production defect
  // surfaced as a P1 by Codex on PR #154 commit ad6bdd0e75 AFTER
  // initial merge; followed up here.
  //
  // `Utilities.newBlob(data, mimeType, fileName)` constructs a real
  // Blob (a `BlobSource` per the GAS docs) that MailApp accepts.
  return Utilities.newBlob(
    JSON.stringify(body.analyzerOutput, null, 2),
    'application/json',
    'analyzerOutput-' + runIdShort + '.json'
  );
}


function _buildJsonResponse_(httpStatus, payload) {
  // ContentService doesn't expose an HTTP status setter — Apps Script
  // Web Apps always return 2xx unless the handler throws (which
  // becomes 500). Per §10A.7 the finalizer keys off 2xx vs 5xx for
  // retry decisions; this helper returns the response object the
  // handler shapes regardless of `httpStatus` (Apps Script will emit
  // 200), with the structured state in the body so logs are
  // diagnosable. Auth/validation rejections that need 4xx/5xx
  // semantics from the finalizer's POV must throw + be caught at the
  // top of doPost so Apps Script's runtime emits 500.
  if (httpStatus >= 500) {
    // Force a 5xx by throwing — finalizer's retry-on-5xx will fire
    // per §10A.7. The thrown message includes the structured payload
    // so Cloud Logging captures the dispatch outcome.
    throw new Error('DISPATCH_5XX:' + JSON.stringify(payload));
  }
  return ContentService.createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}


function _sweepStaleIdempotencyEntries_(props) {
  // Drop dedup entries older than `IDEMPOTENCY_TTL_MS_`. Runs on
  // every callback as a cheap O(N) pass; at pilot scale N << 100 so
  // wall-cost is negligible. Bounded ScriptProperties is the goal.
  var allKeys = props.getKeys();
  var now = Date.now();
  for (var i = 0; i < allKeys.length; i++) {
    var key = allKeys[i];
    if (key.indexOf(IDEMPOTENCY_PROP_PREFIX_) !== 0) continue;
    var raw = props.getProperty(key);
    if (!raw) continue;
    try {
      var entry = JSON.parse(raw);
      if ((now - entry.timestampMs) > IDEMPOTENCY_TTL_MS_) {
        props.deleteProperty(key);
      }
    } catch (err) {
      // Malformed entry — drop it rather than carry it forever.
      props.deleteProperty(key);
    }
  }
}
