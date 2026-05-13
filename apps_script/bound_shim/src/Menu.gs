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

// Multi-click guard: per-spreadsheet in-flight lock stored as a timestamp
// (ms since epoch) on DocumentProperties. Set just before we commit to the
// slow extract+POST path; cleared in `menuSolveRoster_`'s try/finally so
// the lock auto-releases on success, cloud-error, AND uncaught exception.
// The TTL is a safety net for the Apps-Script-crashed-mid-flow case where
// the finally block doesn't run (process killed); a fresh click after the
// TTL clears the stale lock and proceeds. TTL is set to 60s — comfortably
// longer than the worst observed click-to-prompt waterfall (~19s cold path
// + headroom for cloud RTT variance).
var _RM_INFLIGHT_LOCK_KEY = 'rm_solve_inflight_ts_ms';
var _RM_INFLIGHT_LOCK_TTL_MS = 60 * 1000;

// "Solve Roster" menu handler per `docs/decision_log.md` D-0049 +
// `docs/cloud_compute_contract.md`. Synchronously orchestrates the
// three pipeline stages and surfaces a single result dialog at the end:
//
//   1. Pre-flight validation (`_quickValidate_`) — cheap click-time
//      checks that catch the most common operator mistakes (wrong tab,
//      missing config, in-flight re-click) BEFORE the ~14s extract.
//   2. Show "Initializing snapshot" toast — narrates the slow extract
//      so the operator knows the click registered and roughly how long
//      to expect. Toast stays visible until the terminal modal replaces
//      it; the in-flight lock is set at the same time.
//   3. Extract snapshot in-memory via RMLib (no file boundary).
//   4. POST snapshot to Cloud Run /compute endpoint with an OIDC token
//      from `ScriptApp.getIdentityToken()` per D-0051 sub-decision 2.
//   5. Pass the returned writebackEnvelope to RMLib.applyWriteback()
//      per D-0052 to render the new writeback tab (sync path; the LAHC
//      async path returns SUBMITTED at step 4 and the actual writeback
//      lands via the launcher's `async-render-callback` route).
//
// Wall-clock budget: preflight (<1s) + extract (~14s) + cloud (~1-2s) +
// writeback (~3-5s on the deprecated sync path). Comfortably within
// Apps Script's 6 min per-execution limit per
// `docs/cloud_compute_contract.md` §8.4.
function menuSolveRoster_() {
  var ui = SpreadsheetApp.getUi();
  var t0 = Date.now();
  console.log('[timing] solve_roster_start ts_ms=' + t0);

  // Step 1: cheap preflight. Returns `{ok, error}` — `ok=false` aborts
  // immediately with a click-time alert (no toast, no lock acquired,
  // no slow extract).
  var pre = _quickValidate_();
  var tPreflight = Date.now();
  console.log('[timing] preflight_done delta_ms=' + (tPreflight - t0) +
    ' elapsed_ms=' + (tPreflight - t0));
  if (!pre.ok) {
    ui.alert('Solve Roster — cannot start', pre.error, ui.ButtonSet.OK);
    return;
  }

  // Step 2: acquire the in-flight lock + show the "Initializing" toast.
  // From here on we're committed to the slow path; lock release happens
  // in the finally block below.
  PropertiesService.getDocumentProperties().setProperty(
    _RM_INFLIGHT_LOCK_KEY, String(Date.now()));
  SpreadsheetApp.getActiveSpreadsheet().toast(
    'Initializing snapshot — please wait up to 1 minute for the next prompt.',
    'Roster Monster',
    -1
  );

  var result;
  try {
    result = _solveRoster_(t0, tPreflight);
  } catch (e) {
    ui.alert(
      'Solve Roster failed',
      _formatErrorForOperator_(e),
      ui.ButtonSet.OK
    );
    return;
  } finally {
    PropertiesService.getDocumentProperties().deleteProperty(
      _RM_INFLIGHT_LOCK_KEY);
  }
  _showSolveRosterResult_(result);
}

// Cheap click-time validation. Returns `{ok: true}` on pass; `{ok: false,
// error: <operator-facing message>}` on fail. Target latency: <1 second
// total (one DeveloperMetadata finder call dominates at ~50-200ms; the
// other checks are O(1) property reads). Intentionally does NOT duplicate
// the snapshot extractor's structural validation — the extractor is the
// authoritative validator for sheet structure, and we'd need the full
// 14s metadata sweep to replicate it. This function only catches the
// click-time mistakes that don't need the slow path:
//   1. In-flight re-click (multi-click guard).
//   2. Cloud Run URL not configured.
//   3. Operator email unavailable (OAuth scope issue).
//   4. Active tab is not a request-entry tab (the most common operator
//      mistake; currently surfaces ~14s late as `EXTRACTION_ERROR`).
// Anything more semantic (weird prefill names, malformed request cells,
// scorer-config drift) requires the slow path's full sweep — the toast
// covers the wait so the operator knows we're working.
function _quickValidate_() {
  // Check 1: in-flight lock. If a previous click is still mid-flow on
  // this spreadsheet (within the TTL), reject immediately so the
  // operator doesn't kick off a duplicate extract.
  var props = PropertiesService.getDocumentProperties();
  var inFlightTsStr = props.getProperty(_RM_INFLIGHT_LOCK_KEY);
  if (inFlightTsStr) {
    var elapsed = Date.now() - parseInt(inFlightTsStr, 10);
    if (elapsed >= 0 && elapsed < _RM_INFLIGHT_LOCK_TTL_MS) {
      return { ok: false, error:
        'A previous Solve Roster click is still in progress on this ' +
        'spreadsheet (started ' + Math.ceil(elapsed / 1000) + 's ago). ' +
        'Wait for the prompt — or, if you already saw the "Initializing ' +
        'snapshot" toast and dismissed the result, wait for the email.' };
    }
    // Stale lock (>TTL or clock-skew negative) — clear and proceed.
    // Crash-recovery path: covers the case where a prior `menuSolveRoster_`
    // was killed before its finally block ran.
    props.deleteProperty(_RM_INFLIGHT_LOCK_KEY);
  }

  // Check 2: Cloud Run URL configured on the central library. Same check
  // _solveRoster_ does internally — surfacing it here means the operator
  // gets a clear CONFIG_ERROR alert at click time instead of waiting ~14s
  // for the extract before the same error fires.
  var cloudUrl = RMLib.getCloudRunUrl();
  if (!cloudUrl) {
    return { ok: false, error:
      'CONFIG_ERROR: Cloud Run URL not configured. The maintainer needs ' +
      'to set the CLOUD_RUN_URL Script Property on the Roster Monster ' +
      'Central Library Apps Script project.' };
  }

  // Check 3: operator email available. Required for the LAHC async path's
  // operatorEmail field per `docs/cloud_compute_contract.md` §9.3 (the
  // Cloud Batch finalizer needs it for the always-email-on-every-outcome
  // path per §10A.7). Same defense as inside _solveRoster_; pulled forward
  // to click time.
  var operatorEmail = Session.getActiveUser().getEmail();
  if (!operatorEmail) {
    return { ok: false, error:
      'OPERATOR_EMAIL_UNAVAILABLE: Could not read your email address. ' +
      'Re-open the spreadsheet and re-authorize when prompted (verify ' +
      'the userinfo.email OAuth scope).' };
  }

  // Check 4: active tab is a request-entry tab. The single most common
  // operator mistake is clicking Solve Roster from a different tab (e.g.,
  // a writeback tab from a prior run, or a Scorer Config tab). Without
  // this preflight, the operator waits ~14s for the extract to fail with
  // "EXTRACTION_ERROR: not a request-entry tab". One `withKey()` finder
  // on the active sheet only — does NOT trigger the workbook-wide sweep
  // that the full extractor does.
  var activeSheet = SpreadsheetApp.getActiveSheet();
  var tabTypeMatches = activeSheet.createDeveloperMetadataFinder()
    .withKey('rosterMonster:tabType').find();
  if (tabTypeMatches.length !== 1 ||
      tabTypeMatches[0].getValue() !== 'requestEntry') {
    return { ok: false, error:
      'This tab ("' + activeSheet.getName() + '") is not a request-entry ' +
      'tab. Open the period\'s request-entry tab (usually named like ' +
      '"<Section> Requests <month>") and click Solve Roster from there.' };
  }

  return { ok: true };
}

// Internal orchestrator. Throws Error on any unrecoverable failure;
// caller (`menuSolveRoster_`) catches and renders the message into the
// error dialog. `_timing_t0` and `_timing_t_preflight` are passed in
// from the caller so the timing waterfall stays continuous from the
// click instant — `_timing_t0` is the menu-click anchor (used for
// `elapsed_ms`); `_timing_t_preflight` is the previous marker (used
// for `config_resolved`'s `delta_ms`).
function _solveRoster_(_timing_t0, _timing_t_preflight) {
  // Timing instrumentation per the M7 closure UX-improvement thread —
  // captures click → first-prompt latency so we can identify the
  // dominant bottleneck (extract vs Cloud Run cold-start vs Batch
  // submit). console.log() writes to Cloud Logging when the Apps Script
  // project is linked to a GCP project (verify via Apps Script editor →
  // Project Settings → Google Cloud Platform). Format: `[timing] stage
  // delta_ms=N elapsed_ms=N` so the dry-run analysis script can parse it.
  // The `solve_roster_start` and `preflight_done` markers are emitted
  // by the caller (`menuSolveRoster_`) before this function runs.

  // Stage 0: resolve Cloud Run URL from the central library's script
  // properties. Library-level properties are shared across all consumers
  // (one source of truth) and don't get nulled-out by makeCopy() of
  // operator spreadsheets. Note this duplicates the preflight check —
  // intentional: keeps `_solveRoster_` self-contained for testing /
  // direct invocation paths that bypass the menu handler.
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
  var _timing_t1 = Date.now();
  console.log(
    '[timing] config_resolved delta_ms=' + (_timing_t1 - _timing_t_preflight) +
    ' elapsed_ms=' + (_timing_t1 - _timing_t0)
  );
  var snapshot;
  try {
    snapshot = RMLib.extractSnapshotInMemoryForActiveSheet();
  } catch (e) {
    throw new Error(
      'EXTRACT_FAILED: ' + ((e && e.message) ? e.message : String(e))
    );
  }
  var _timing_t2 = Date.now();
  console.log(
    '[timing] snapshot_extracted delta_ms=' + (_timing_t2 - _timing_t1) +
    ' elapsed_ms=' + (_timing_t2 - _timing_t0)
  );

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

  var _timing_t3 = Date.now();
  console.log(
    '[timing] request_prepared delta_ms=' + (_timing_t3 - _timing_t2) +
    ' elapsed_ms=' + (_timing_t3 - _timing_t0)
  );
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
  var _timing_t4 = Date.now();
  console.log(
    '[timing] cloud_response_received delta_ms=' + (_timing_t4 - _timing_t3) +
    ' elapsed_ms=' + (_timing_t4 - _timing_t0) +
    ' http_status=' + response.getResponseCode()
  );

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
    var _timing_t5 = Date.now();
    console.log(
      '[timing] submitted_state_returned delta_ms=' + (_timing_t5 - _timing_t4) +
      ' elapsed_ms=' + (_timing_t5 - _timing_t0) +
      ' run_id=' + ((body.submission || {}).runId || 'unknown')
    );
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
    // M7 C4 T2C async UX per D-0071 sub-decision 9: post-submit
    // notification. The actual writeback + analyzer tabs land
    // asynchronously when the launcher Web App receives the §10A
    // callback POST from the Cloud Batch worker's inline finalize
    // step. Operator gets an email when complete (per §10A.7
    // always-email-on-every-outcome).
    //
    // **Switched from `.toast()` (bottom-right, non-blocking) to
    // `ui.alert()` (centered modal, requires OK click) on
    // 2026-05-13** per operator feedback that the small bottom-
    // right notification was easy to miss. The modal is more
    // intrusive but acknowledges-by-default — operator must click
    // OK to confirm they've seen "wait for email", which is the
    // right signal for an async flow where nothing else changes
    // on-screen for ~5-10 minutes.
    ui.alert(
      'Solve Roster — Submitted',
      'We’ll email you when the roster is ready '
        + '— can take up to 10 minutes.',
      ui.ButtonSet.OK
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
