// DeleteSheetsById.gs (launcher headless-cleanup entrypoint)
// Maintainer-only entrypoint added alongside ExtractById.gs for symmetric
// `clasp run`-driven cleanup. Deletes a list of sheet (tab) IDs from a
// target spreadsheet. Useful for removing analyzer-render output tabs
// after dry-run experiments without forcing the operator into the
// spreadsheet UI.
//
// Returns a result dict:
//   { deleted: [{sheetId, name}, ...], notFound: [sheetId, ...] }
// notFound are silently skipped (no exception) so partial cleanup of
// already-deleted tabs is tolerated.
//
// Callable via:
//   clasp run deleteSheetsById --params '["<spreadsheetId>", [123, 456, ...]]'

function deleteSheetsById(spreadsheetId, sheetIdsArray) {
  if (!spreadsheetId) {
    throw new Error(
      'deleteSheetsById: spreadsheetId is required (1st argument).'
    );
  }
  if (!Array.isArray(sheetIdsArray) || sheetIdsArray.length === 0) {
    throw new Error(
      'deleteSheetsById: sheetIdsArray (2nd argument) must be a non-empty array.'
    );
  }
  var ss = SpreadsheetApp.openById(spreadsheetId);
  var allSheets = ss.getSheets();
  var byId = {};
  for (var i = 0; i < allSheets.length; i++) {
    byId[allSheets[i].getSheetId()] = allSheets[i];
  }
  var deleted = [];
  var notFound = [];
  for (var k = 0; k < sheetIdsArray.length; k++) {
    var requestedId = Number(sheetIdsArray[k]);
    var sheet = byId[requestedId];
    if (sheet) {
      var name = sheet.getName();
      ss.deleteSheet(sheet);
      deleted.push({ sheetId: requestedId, name: name });
    } else {
      notFound.push(requestedId);
    }
  }
  return { deleted: deleted, notFound: notFound };
}
