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
// Returned shape is the same Snapshot object the bound-shim cloud-mode
// path emits per `docs/snapshot_adapter_contract.md` §7. Callable via
// `clasp run extractSnapshotById --params '["<spreadsheetId>", "<requestTabName>"]'`.

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
  return RMLib.extractSnapshotInMemoryForSheet(ss, requestSheet);
}
