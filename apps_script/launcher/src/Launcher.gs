// Launcher.gs
// Operator-facing Web App launcher for the ICU/HD sheet generator.
//
// Thin front-end inside the sheet-adapter layer (blueprint §7 boundary #2). Wraps
// the existing `generateIntoNewSpreadsheet` / `generateIntoExistingSpreadsheet`
// entrypoints from GenerateSheet.gs without altering generation semantics.
// See docs/sheet_generation_contract.md §12 for the full surface contract.
//
// Access gating is external to this file (§12.3):
//   - appsscript.json `webapp` block deploys "Execute as: User accessing the
//     web app" + "Who has access: Anyone with Google Account".
//   - Authorization is granted by adding operator Google accounts to the GCP
//     OAuth consent screen's Test Users list for the script's GCP project.
//   - No in-app allowlist; no persisted per-operator state.

function doGet(e) {
  var params = (e && e.parameter) ? e.parameter : {};
  var action = (params.action == null ? '' : String(params.action)).trim().toLowerCase();
  // Each route's nav header (per the cross-page navigation UX) needs the
  // absolute Web App deployment URL — relative `?action=...` hrefs do
  // NOT work because Apps Script renders the HTML inside Google's
  // iframe, so a relative href would resolve against the iframe URL
  // and never reach this `doGet` dispatch. `ScriptApp.getService().getUrl()`
  // returns the `/exec` deployment URL of the currently-running script.
  var rootUrl = ScriptApp.getService().getUrl();

  // M7 C4 T2B deployment-URL gate per `docs/cloud_compute_contract.md`
  // §10A.3 (security-critical per Codex P1 round 5 finding 9). The
  // callback deployment runs under `executeAs: USER_DEPLOYING` +
  // `Access: ANYONE` — that grants script-owner privileges to anyone
  // hitting the callback URL. Operator-facing routes (`/exec`,
  // `?action=writeback`, `?action=analysis-render`) MUST be blocked
  // when the request comes in via the callback URL; otherwise an
  // operator's GET on the callback deployment URL would render the
  // sheet-gen form under script-owner identity. Callback deployment
  // is POST-only; reject ALL GETs.
  if (_isCallbackDeployment_()) {
    return ContentService
      .createTextOutput(JSON.stringify({
        state: 'INVALID_DEPLOYMENT',
        code: 'GET_NOT_ALLOWED_ON_CALLBACK_DEPLOYMENT',
      }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (action === 'writeback') {
    // M3 C1 writeback route per `docs/decision_log.md` D-0044 sub-decision 3.
    // Operator uploads the wrapper-envelope JSON file produced by the Python
    // CLI; client-side FileReader serializes the file content; server-side
    // entry point is `applyWriteback(envelopeJsonString)` in Writeback.gs.
    var wbTpl = HtmlService.createTemplateFromFile('WritebackForm');
    wbTpl.rootUrl = rootUrl;
    return wbTpl.evaluate()
      .setTitle('CGH ICU/HD Roster Writeback')
      .addMetaTag('viewport', 'width=device-width, initial-scale=1');
  }
  if (action === 'analysis-render') {
    // M5 C2 analysis renderer route per `docs/decision_log.md` D-0063.
    // Operator uploads the AnalyzerOutput JSON file produced by
    // `python -m rostermonster.analysis`; server-side entry point is
    // `renderAnalysis(outputJsonString)` (delegate shim → RMLib).
    var arTpl = HtmlService.createTemplateFromFile('AnalysisRendererForm');
    arTpl.rootUrl = rootUrl;
    return arTpl.evaluate()
      .setTitle('CGH ICU/HD Analysis Renderer')
      .addMetaTag('viewport', 'width=device-width, initial-scale=1');
  }
  var tpl = HtmlService.createTemplateFromFile('LauncherForm');
  tpl.rootUrl = rootUrl;
  return tpl.evaluate()
    .setTitle('CGH ICU/HD Roster Launcher')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

// M7 C4 T2B Web App POST dispatcher — added so the SECOND launcher
// deployment (callback deployment per `docs/cloud_compute_contract.md`
// §10A.5) can receive the Cloud Batch finalizer's POST. The Cloud Run
// thin front door does NOT POST through the launcher; only the Cloud
// Batch task's inline finalize step does (per §10A.3).
function doPost(e) {
  var params = (e && e.parameter) ? e.parameter : {};
  var action = (params.action == null ? '' : String(params.action)).trim().toLowerCase();

  // Deployment-URL gate per §10A.3 + Codex P1 round 5 finding 9. The
  // callback deployment MUST reject any POST whose action isn't
  // `async-render-callback`; otherwise a misrouted writeback /
  // analysis-render POST would execute under script-owner privileges.
  if (_isCallbackDeployment_()) {
    if (action !== 'async-render-callback') {
      return ContentService
        .createTextOutput(JSON.stringify({
          state: 'INVALID_DEPLOYMENT',
          code: 'NON_CALLBACK_ROUTE_REJECTED',
          action: action,
        }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    // Route to the async-render-callback handler in
    // `AsyncRenderCallback.gs`. The handler is responsible for auth
    // validation, idempotency, state dispatch, + email.
    return handleAsyncRenderCallback_(e);
  }

  // Operator-facing deployment — no POST routes are defined here
  // (operator submissions go through `google.script.run` not raw
  // HTTPS POST). Reject for parity with the callback deployment's
  // POST gate.
  return ContentService
    .createTextOutput(JSON.stringify({
      state: 'INVALID_ROUTE',
      code: 'POST_NOT_SUPPORTED_ON_OPERATOR_DEPLOYMENT',
    }))
    .setMimeType(ContentService.MimeType.JSON);
}

// `_isCallbackDeployment_` returns true when the current request is
// running under the SECOND launcher deployment (callback deployment)
// per §10A.5. The check compares `ScriptApp.getService().getUrl()`
// against the `CALLBACK_DEPLOYMENT_URL` ScriptProperty the maintainer
// sets at T2B deploy time. When the property is unset, treats the
// current deployment as operator-facing (default fail-open is safe
// because the callback handler still requires a valid OIDC token to
// run anything destructive — but the deployment-URL gate is the
// load-bearing isolation per Codex P1 round 5 finding 9 for the
// `Access: ANYONE` callback deployment).
function _isCallbackDeployment_() {
  var configuredCallbackUrl;
  try {
    configuredCallbackUrl = PropertiesService.getScriptProperties()
      .getProperty('CALLBACK_DEPLOYMENT_URL');
  } catch (err) {
    return false;
  }
  if (!configuredCallbackUrl) return false;
  var currentUrl = ScriptApp.getService().getUrl();
  return currentUrl === configuredCallbackUrl;
}

// Public server handler invoked by `google.script.run.submitLauncherForm()`
// from LauncherForm.html. Must not have a trailing underscore — google.script.run
// cannot reach private-suffixed functions.
//
// Returns one of:
//   { ok: true,  result: <generateInto*Spreadsheet return value> }
//   { ok: false, error:  '<operator-facing error message>' }
//
// Generation errors are caught and returned in the { ok: false } shape so the
// client can render them through a single success-handler path. The
// withFailureHandler branch remains the fallback for infrastructure-level errors
// (network, sandbox, etc.).
function submitLauncherForm(payload) {
  try {
    var mode = (payload && payload.outputMode) ? String(payload.outputMode).trim() : '';
    var config = buildConfigFromLauncherPayload_(payload, mode);
    var result;
    if (mode === 'existing') {
      result = generateIntoExistingSpreadsheet(config);
    } else if (mode === 'new') {
      result = generateIntoNewSpreadsheet(config);
    } else {
      throw new Error('Choose an output mode (new spreadsheet file or new tab in existing spreadsheet).');
    }
    return { ok: true, result: result };
  } catch (e) {
    return { ok: false, error: (e && e.message) ? e.message : String(e) };
  }
}

// HtmlService scriptlet helper used by LauncherForm.html to embed
// LauncherSuccess.html as an inert client-side template.
function include_(filename) {
  return HtmlService.createHtmlOutputFromFile(filename).getContent();
}

// ---------------------------------------------------------------------------
// Helpers (file-scoped; not invoked from google.script.run)
// ---------------------------------------------------------------------------

// Translate the flat form payload to the generator config shape. Payload-shape
// coercion only (string → number for counts, trimming the optional
// spreadsheetId); semantic validation continues to live in
// normalizeAndValidateConfig_ so there is a single source of truth for
// date-range and template-count rules.
function buildConfigFromLauncherPayload_(payload, mode) {
  if (!payload || typeof payload !== 'object') {
    throw new Error('Launcher submission was empty — please re-enter the form and submit again.');
  }
  var counts = {
    ICU_ONLY: toNonNegativeInteger_(payload.icuOnly, 'ICU only'),
    ICU_HD:   toNonNegativeInteger_(payload.icuHd,   'ICU + HD'),
    HD_ONLY:  toNonNegativeInteger_(payload.hdOnly,  'HD only'),
  };
  var config = {
    department: 'CGH ICU/HD Call',
    periodStartDate: readTrimmedString_(payload.periodStartDate),
    periodEndDate:   readTrimmedString_(payload.periodEndDate),
    doctorCountByGroup: counts,
  };
  if (mode === 'existing') {
    config.spreadsheetId = readTrimmedString_(payload.spreadsheetId);
  }
  return config;
}

function readTrimmedString_(value) {
  return (value == null ? '' : String(value)).trim();
}

function toNonNegativeInteger_(raw, label) {
  var text = readTrimmedString_(raw);
  if (text === '') {
    throw new Error('Doctor count for "' + label + '" is required.');
  }
  var n = Number(text);
  if (!isFinite(n) || n < 0 || Math.floor(n) !== n) {
    throw new Error('Doctor count for "' + label + '" must be a non-negative integer (got "' + text + '").');
  }
  return n;
}
