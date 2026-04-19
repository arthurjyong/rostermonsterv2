// ProtectionAndValidation.gs
// Explicit whole-sheet protection + warning-only request validation.
//
// Protection model (docs/sheet_generation_contract.md section 9):
//   1. Protect the entire sheet, restrict to the script owner.
//   2. Whitelist only the explicit operator-editable ranges reported in layoutInfo:
//        - doctor-name cells, request-entry cells, call-point value cells,
//          lower-shell assignment cells.
//   3. Everything else (title, date axis, weekday row, section headers, point-row
//      labels, lower-shell labels, legend) stays non-editable.
//
// Validation model (docs/request_semantics_contract.md section 7):
//   Request-entry cells use warning-only custom-formula validation. Recognized
//   tokens are accepted alone or as comma-separated combinations. Blank is allowed.
//   Parser remains authoritative for downstream interpretation.

var REQUEST_TOKEN_VOCAB_ = Object.freeze([
  'CR', 'NC', 'AL', 'TL', 'SL', 'MC', 'HL', 'NSL', 'OPL', 'EXAM', 'EMCC', 'PM_OFF',
]);

function applyProtections_(sheet, layoutInfo) {
  var protection = sheet.protect()
    .setDescription('Roster Monster generated shell — structural surfaces locked');

  var me;
  try { me = Session.getEffectiveUser(); } catch (e) { me = null; }
  if (me) {
    protection.addEditor(me);
    var editors = protection.getEditors();
    for (var i = 0; i < editors.length; i++) {
      if (editors[i].getEmail() !== me.getEmail()) {
        protection.removeEditor(editors[i]);
      }
    }
  }
  if (protection.canDomainEdit && protection.canDomainEdit()) {
    try { protection.setDomainEdit(false); } catch (_) { /* non-domain sheet */ }
  }

  var unprotected = [];
  function pushRange(descriptor) {
    if (!descriptor || descriptor.numRows <= 0 || descriptor.numCols <= 0) return;
    unprotected.push(sheet.getRange(
      descriptor.row, descriptor.col, descriptor.numRows, descriptor.numCols));
  }

  layoutInfo.doctorNameRanges.forEach(pushRange);
  layoutInfo.requestEntryRanges.forEach(pushRange);
  layoutInfo.pointRowRanges.forEach(pushRange);
  layoutInfo.lowerShellRanges.forEach(pushRange);

  if (unprotected.length > 0) {
    protection.setUnprotectedRanges(unprotected);
  }
}

function applyValidations_(sheet, layoutInfo) {
  if (!layoutInfo.requestEntryRanges.length) return;

  var altToken = REQUEST_TOKEN_VOCAB_.join('|');
  var tokensList = REQUEST_TOKEN_VOCAB_.join(', ');

  for (var i = 0; i < layoutInfo.requestEntryRanges.length; i++) {
    var d = layoutInfo.requestEntryRanges[i];
    var range = sheet.getRange(d.row, d.col, d.numRows, d.numCols);
    var topLeftA1 = range.getCell(1, 1).getA1Notation();

    // Relative reference: Google Sheets shifts topLeftA1 per-cell across the range.
    // Pattern allows blank or one-or-more comma-separated recognized tokens.
    var formula =
      '=REGEXMATCH(UPPER(TRIM("" & ' + topLeftA1 + ')), ' +
      '"^((' + altToken + ')(\\s*,\\s*(' + altToken + '))*)?$")';

    var rule = SpreadsheetApp.newDataValidation()
      .requireFormulaSatisfied(formula)
      .setAllowInvalid(true) // warning-only, not rejection
      .setHelpText(
        'Recognized request codes: ' + tokensList + '. ' +
        'Combinations allowed (e.g. "CR, NC" or "EMCC, NC"). Blank is OK. ' +
        'Validation is warning-only; parser remains authoritative.')
      .build();

    range.setDataValidation(rule);
  }
}
