// ExtractById.gs (launcher headless-extract entrypoint)
// Maintainer-only entrypoint added under M6 follow-up work to enable
// `clasp run`-driven snapshot extraction for LAHC dry-run iteration.
// The bound-shim's existing "Extract Snapshot" menu requires the operator
// to be at the spreadsheet UI; this entrypoint bypasses that by opening
// the spreadsheet headlessly via `SpreadsheetApp.openById()` (the launcher
// has the full `auth/spreadsheets` scope per its appsscript.json) and
// delegating to the central library's
// `RMLib.extractSnapshotInMemoryForSheet(ss, requestSheet)`.
//
// Returns a JSON string (not the in-memory object). `clasp run` prints
// function returns via `console.log()`, which uses `util.inspect` for
// objects (producing unquoted-key + `[Object]`-elided output that is NOT
// valid JSON and not Python-loadable). Returning `JSON.stringify(...)`
// instead makes clasp run print the JSON content verbatim, which the
// caller can pipe to a file and feed straight into the Python CLI.
// Snapshot shape is byte-identical to the in-memory entrypoints; only
// the wire form changes.
//
// Callable via:
//   clasp run extractSnapshotById --params '["<spreadsheetId>", "<requestTabName>"]'
// Pipe to file:
//   clasp run ... > snapshot.json

function extractSnapshotById(spreadsheetId, requestTabName) {
  if (!spreadsheetId) {
    throw new Error(
      'extractSnapshotById: spreadsheetId is required (1st argument).'
    );
  }
  if (!requestTabName) {
    throw new Error(
      'extractSnapshotById: requestTabName is required (2nd argument).'
    );
  }
  var ss = SpreadsheetApp.openById(spreadsheetId);
  var requestSheet = ss.getSheetByName(requestTabName);
  if (!requestSheet) {
    var availableTabs = ss.getSheets().map(function (s) {
      return s.getName();
    });
    throw new Error(
      'extractSnapshotById: tab "' + requestTabName + '" not found in ' +
      'spreadsheet ' + spreadsheetId + '. Available tabs: ' +
      availableTabs.join(', ')
    );
  }
  var snapshot = RMLib.extractSnapshotInMemoryForSheet(ss, requestSheet);
  return JSON.stringify(snapshot);
}
