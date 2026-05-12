// Menu.gs
// Container-bound shim for launcher-generated operator spreadsheets per
// `docs/decision_log.md` D-0041 + `docs/snapshot_adapter_contract.md` §3.
//
// Stays intentionally thin (delegate-only). All extractor + writeback logic
// lives in the central Apps Script Library declared in `appsscript.json`
// under the symbol `RMLib`. Library is loaded at version `0` (HEAD per
// D-0041 sub-decision 3), so updates to the central library propagate to
// every operator sheet on next menu click without requiring a re-push of
// this bound shim.
//
// M4 C1 (per D-0049 / D-0052) adds a second menu item "Solve Roster" that
// orchestrates extract → cloud-compute → writeback inline, ending with a
// new writeback tab in the operator's source spreadsheet.
//
// Simple triggers MUST be declared here (NOT in the library) — Apps Script
// does not fire `onOpen` / `onEdit` on imported library functions per
// D-0041 sub-decision 9.

function onOpen(e) {
  SpreadsheetApp.getUi()
    .createMenu('Roster Monster')
    .addItem('Extract Snapshot', 'menuExtractSnapshot_')
    .addItem('Solve Roster', 'menuSolveRoster_')
    .addToUi();
}

function menuExtractSnapshot_() {
  // Delegate to the central library. The library returns an HtmlOutput
  // payload that triggers a browser download of the snapshot JSON file
  // per `docs/decision_log.md` D-0040.
  var html = RMLib.extractSnapshotForActiveSheet();
  SpreadsheetApp.getUi().showModalDialog(html, 'Snapshot ready');
}

// "Solve Roster" menu handler per `docs/decision_log.md` D-0049 +
// `docs/cloud_compute_contract.md`. Synchronously orchestrates the
// three pipeline stages and surfaces a single result dialog at the end:
//
//   1. Extract snapshot in-memory via RMLib (no file boundary).
//   2. POST snapshot to Cloud Run /compute endpoint with an OIDC token
//      from `ScriptApp.getIdentityToken()` per D-0051 sub-decision 2.
//   3. Pass the returned writebackEnvelope to RMLib.applyWriteback()
//      per D-0052 to render the new writeback tab.
//
// Wall-clock budget: extract (~1s) + cloud (~30-90s with cold start)
// + writeback (~3-5s). Comfortably within Apps Script's 6 min
// per-execution limit per `docs/cloud_compute_contract.md` §8.4.
function menuSolveRoster_() {
  var ui = SpreadsheetApp.getUi();
  var result;
  try {
    result = _solveRoster_();
  } catch (e) {
    ui.alert(
      'Solve Roster failed',
      _formatErrorForOperator_(e),
      ui.ButtonSet.OK
    );
    return;
  }
  _showSolveRosterResult_(result);
}

// Internal orchestrator. Throws Error on any unrecoverable failure;
// caller (`menuSolveRoster_`) catches and renders the message into the
// error dialog.
function _solveRoster_() {
  // Stage 0: resolve Cloud Run URL from the central library's script
  // properties. Library-level properties are shared across all consumers
  // (one source of truth) and don't get nulled-out by makeCopy() of
  // operator spreadsheets.
  var cloudUrl = RMLib.getCloudRunUrl();
  if (!cloudUrl) {
    throw new Error(
      'CONFIG_ERROR: Cloud Run URL not configured. Maintainer should ' +
      'open the Roster Monster Extractor Library Apps Script project, ' +
      'navigate to Project Settings → Script Properties, and add ' +
      '"CLOUD_RUN_URL" with the deployed service URL ' +
      '(e.g., https://roster-monster-compute-...run.app). See ' +
      'cloud_compute_service/README.md.'
    );
  }

  // Stage 1: extract snapshot in-memory via the central library.
  var snapshot;
  try {
    snapshot = RMLib.extractSnapshotInMemoryForActiveSheet();
  } catch (e) {
    throw new Error(
      'EXTRACT_FAILED: ' + ((e && e.message) ? e.message : String(e))
    );
  }

  // Stage 2: acquire an OIDC token for Cloud Run IAM auth.
  var token = ScriptApp.getIdentityToken();
  if (!token) {
    throw new Error(
      'AUTH_ERROR: ScriptApp.getIdentityToken() returned no token. ' +
      'Verify the bound shim manifest declares the openid + ' +
      'userinfo.email OAuth scopes per `docs/decision_log.md` D-0051 ' +
      'sub-decision 3a.'
    );
  }

  // Stage 3: POST to Cloud Run /compute. Note `muteHttpExceptions: true`
  // is required so we can dispatch on HTTP status codes (401/403 for
  // auth failures per `docs/cloud_compute_contract.md` §7.5; 200 for
  // application-level state per §10) rather than have UrlFetchApp throw
  // on every non-2xx response.
  //
  // M7 C4 T2D: bound shim is LAHC-only on the operator path per D-0071
  // sub-decision 13 (SRB stays in code for benchmarks but no operator-
  // facing menu item). `solverStrategy: 'LAHC'` activates the Cloud Run
  // thin front door at app.py: validate + concurrent-rejection + submit
  // Batch + return SUBMITTED in ~3-5s. `operatorEmail` is REQUIRED on
  // the LAHC path per §9.3 (the Cloud Batch finalizer needs it for the
  // always-email-on-every-outcome path); sourced from
  // `Session.getActiveUser().getEmail()` per D-0071 sub-decision 6.
  var endpoint = cloudUrl.replace(/\/+$/, '') + '/compute';
  var operatorEmail = Session.getActiveUser().getEmail();
  if (!operatorEmail) {
    throw new Error(
      'OPERATOR_EMAIL_UNAVAILABLE: Session.getActiveUser().getEmail() ' +
      'returned empty. Verify the bound shim manifest declares the ' +
      'userinfo.email OAuth scope per `docs/decision_log.md` D-0051 ' +
      'sub-decision 3a (the LAHC async path requires operatorEmail ' +
      'to receive the completion email per §10A.7).'
    );
  }
  var requestBody = JSON.stringify({
    snapshot: snapshot,
    operatorEmail: operatorEmail,
    optionalConfig: {
      solverStrategy: 'LAHC',
    },
  });

  var response;
  try {
    response = UrlFetchApp.fetch(endpoint, {
      method: 'post',
      // Per `docs/decision_log.md` D-0054, the operator's ID token
      // travels via `X-Auth-Token` (not `Authorization`). Cloud Run
      // strips the standard `Authorization` header from public
      // services to prevent token leakage; using a custom header
      // bypasses that scrubbing while keeping the Flask-side
      // operator-allowlist auth path functional.
      headers: { 'X-Auth-Token': token },
      contentType: 'application/json',
      payload: requestBody,
      muteHttpExceptions: true,
    });
  } catch (e) {
    // Pre-response transport failure (DNS, network, etc).
    throw new Error(
      'NETWORK_ERROR: Could not reach Cloud Run at ' + endpoint + '. ' +
      ((e && e.message) ? e.message : String(e))
    );
  }

  var statusCode = response.getResponseCode();
  if (statusCode === 401 || statusCode === 403) {
    throw new Error(
      'AUTH_REJECTED: Cloud Run rejected the request (HTTP ' + statusCode +
      '). Verify your account is on the OAuth Test Users list AND has ' +
      'roles/run.invoker on the roster-monster-compute service.'
    );
  }
  if (statusCode !== 200) {
    throw new Error(
      'CLOUD_HTTP_' + statusCode + ': ' +
      String(response.getContentText() || '').substring(0, 500)
    );
  }

  var body;
  try {
    body = JSON.parse(response.getContentText());
  } catch (e) {
    throw new Error(
      'CLOUD_RESPONSE_NOT_JSON: ' + String(response.getContentText() || '').substring(0, 500)
    );
  }

  // Stage 4: dispatch on cloud-side state.
  if (body.state === 'INPUT_ERROR' || body.state === 'COMPUTE_ERROR') {
    return {
      kind: 'CLOUD_ERROR',
      cloudState: body.state,
      errorCode: body.error && body.error.code,
      errorMessage: body.error && body.error.message,
    };
  }
  // M7 C4 T2B defensive-async handler per `docs/delivery_plan.md` §9
  // T2C scope: accept the new `SUBMITTED` enum value (added in M7 C3
  // per D-0071 sub-decision 2 + Codex P2 round 1 ordering fix). When
  // Cloud Run cuts over to the async LAHC path at T2D, the operator
  // path returns `SUBMITTED` immediately + the actual outcome lands
  // asynchronously via the launcher's `async-render-callback` route.
  // Pre-T2C the bound shim would have thrown `CLOUD_UNEXPECTED_STATE`
  // on every operator click between Cloud Run cutover and bound shim
  // re-deploy; T2C lands FIRST to close that window. NO request-body
  // change here — bound shim still sends the SRB shape; T2D flips
  // the strategy to LAHC + threads operatorEmail through (so this
  // SUBMITTED handler only fires once T2D's request-shape change
  // also lands).
  if (body.state === 'SUBMITTED') {
    return {
      kind: 'SUBMITTED_ASYNC',
      cloudState: 'SUBMITTED',
      submission: body.submission || {},
    };
  }
  if (body.state !== 'OK' && body.state !== 'UNSATISFIED') {
    throw new Error(
      'CLOUD_UNEXPECTED_STATE: ' + JSON.stringify(body.state)
    );
  }
  if (!body.writebackEnvelope) {
    throw new Error(
      'CLOUD_MISSING_ENVELOPE: state=' + body.state + ' but writebackEnvelope is null'
    );
  }

  // Stage 5: hand the writeback envelope to the central library's
  // writeback adapter. The library parses, opens the source spreadsheet
  // (which is the active one), writes the new tab, returns the
  // 3-state diagnostic per writeback contract §17.
  var writebackResult = RMLib.applyWriteback(
    JSON.stringify(body.writebackEnvelope)
  );

  return {
    kind: 'WRITEBACK_DONE',
    cloudState: body.state,
    writebackState: writebackResult.state,
    writebackTabName: writebackResult.tabName,
    writebackUrl: writebackResult.spreadsheetUrl,
    writebackError: writebackResult.error,
  };
}

function _showSolveRosterResult_(result) {
  var ui = SpreadsheetApp.getUi();
  if (result.kind === 'CLOUD_ERROR') {
    ui.alert(
      'Solve Roster — ' + result.cloudState,
      'Cloud compute returned ' + result.cloudState + ' (' +
      (result.errorCode || 'no code') + '): ' +
      (result.errorMessage || '(no message)'),
      ui.ButtonSet.OK
    );
    return;
  }

  if (result.kind === 'SUBMITTED_ASYNC') {
    // M7 C4 T2C async UX per D-0071 sub-decision 9: one-time non-
    // blocking toast post-submit. The actual writeback + analyzer
    // tabs land asynchronously when the launcher Web App receives
    // the §10A callback POST from the Cloud Batch worker's inline
    // finalize step. Operator gets an email when complete (per
    // §10A.7 always-email-on-every-outcome).
    //
    // `toast(message, title, timeoutSeconds)` — sticky-ish at 10s
    // so the operator has time to read but the toast doesn't
    // linger. Sheets dismisses on its own; non-blocking returns
    // immediately from menuSolveRoster_.
    SpreadsheetApp.getActiveSpreadsheet().toast(
      'We’ll email you when the roster is ready — can take up '
        + 'to 10 minutes.',
      'Submitted',
      10
    );
    return;
  }

  // WRITEBACK_DONE
  if (result.writebackState === 'SUCCESS' ||
      result.writebackState === 'FAILED') {
    var heading = (result.writebackState === 'SUCCESS')
      ? 'Roster written to new tab'
      : 'No allocation possible — failure tab written';
    var detail = (result.writebackState === 'SUCCESS')
      ? 'A new tab "' + (result.writebackTabName || '?') +
        '" was added to this spreadsheet with the winner allocation, ' +
        'traceability footer, and read-only protection.'
      : 'A new tab "' + (result.writebackTabName || '?') +
        '" was added to this spreadsheet describing what could not be ' +
        'filled (see the new tab for unfilledDemand + reasons).';
    if (result.writebackUrl) {
      detail += '\n\nLink: ' + result.writebackUrl;
    }
    ui.alert(heading, detail, ui.ButtonSet.OK);
    return;
  }

  // RUNTIME_ERROR from the writeback library — extract succeeded, cloud
  // succeeded, but writeback itself errored mid-write.
  ui.alert(
    'Writeback runtime error',
    String(result.writebackError || '(no message)'),
    ui.ButtonSet.OK
  );
}

function _formatErrorForOperator_(e) {
  var msg = (e && e.message) ? String(e.message) : String(e);
  // Trim Apps Script's stack-trace prefix if present.
  return msg;
}
