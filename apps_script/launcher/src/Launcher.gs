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
  if (action === 'writeback') {
    // M3 C1 writeback route per `docs/decision_log.md` D-0044 sub-decision 3.
    // Operator uploads the wrapper-envelope JSON file produced by the Python
    // CLI; client-side FileReader serializes the file content; server-side
    // entry point is `applyWriteback(envelopeJsonString)` in Writeback.gs.
    return HtmlService.createTemplateFromFile('WritebackForm')
      .evaluate()
      .setTitle('CGH ICU/HD Roster Writeback')
      .addMetaTag('viewport', 'width=device-width, initial-scale=1');
  }
  if (action === 'analysis-render') {
    // M5 C2 analysis renderer route per `docs/decision_log.md` D-0063.
    // Operator uploads the AnalyzerOutput JSON file produced by
    // `python -m rostermonster.analysis`; server-side entry point is
    // `renderAnalysis(outputJsonString)` (delegate shim → RMLib).
    return HtmlService.createTemplateFromFile('AnalysisRendererForm')
      .evaluate()
      .setTitle('CGH ICU/HD Analysis Renderer')
      .addMetaTag('viewport', 'width=device-width, initial-scale=1');
  }
  return HtmlService.createTemplateFromFile('LauncherForm')
    .evaluate()
    .setTitle('CGH ICU/HD Roster Launcher')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
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
