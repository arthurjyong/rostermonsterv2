// DeleteSheetsByNamePrefix.gs (launcher headless-cleanup entrypoint)
// Companion to DeleteSheetsById.gs — deletes every sheet whose name
// matches one of the supplied prefixes. Useful for batch-cleaning
// analyzer renderer outputs (`Analysis snapsh *`, `Analysis combin *`,
// `Snapsh *`, `Combin *`) without enumerating sheet IDs first.
//
// Returns:
//   { deleted: [{sheetId, name}, ...], remaining: [name, ...] }
//
// Callable via:
//   clasp run deleteSheetsByNamePrefix --params '["<spreadsheetId>", ["Analysis ", "Snapsh ", "Combin "]]'

function deleteSheetsByNamePrefix(spreadsheetId, prefixes) {
  if (!spreadsheetId) {
    throw new Error(
      'deleteSheetsByNamePrefix: spreadsheetId is required (1st argument).'
    );
  }
  if (!Array.isArray(prefixes) || prefixes.length === 0) {
    throw new Error(
      'deleteSheetsByNamePrefix: prefixes (2nd argument) must be a non-empty array.'
    );
  }
  for (var v = 0; v < prefixes.length; v++) {
    if (typeof prefixes[v] !== 'string' || prefixes[v].length === 0) {
      // Empty/non-string prefix would match every sheet via indexOf("")===0
      // and silently wipe the spreadsheet — reject upfront.
      throw new Error(
        'deleteSheetsByNamePrefix: prefixes[' + v + '] must be a non-empty string; got ' + JSON.stringify(prefixes[v]) + '.'
      );
    }
  }
  var ss = SpreadsheetApp.openById(spreadsheetId);
  var sheets = ss.getSheets();
  var deleted = [];
  var remaining = [];
  for (var i = 0; i < sheets.length; i++) {
    var sheet = sheets[i];
    var name = sheet.getName();
    var matched = false;
    for (var p = 0; p < prefixes.length; p++) {
      if (name.indexOf(prefixes[p]) === 0) {
        matched = true;
        break;
      }
    }
    if (matched) {
      var sheetId = sheet.getSheetId();
      ss.deleteSheet(sheet);
      deleted.push({ sheetId: sheetId, name: name });
    } else {
      remaining.push(name);
    }
  }
  return { deleted: deleted, remaining: remaining };
}
