// ProtectionAndValidation.gs
// Explicit whole-sheet protection + hard-reject request/call-point validation.
//
// Protection model (docs/sheet_generation_contract.md section 9):
//   1. Protect the entire sheet, restrict to the script owner.
//   2. Whitelist only the explicit operator-editable ranges reported in layoutInfo:
//        - doctor-name cells, request-entry cells, call-point value cells,
//          lower-shell assignment cells.
//   3. Everything else (title, date axis, weekday row, section headers, point-row
//      labels, lower-shell labels, legend, and column A on non-doctor rows)
//      stays non-editable.
//
// Validation model:
//   Request-entry cells use hard-reject custom-formula validation. Recognized
//   tokens are accepted alone or as comma-separated combinations. Blank is
//   allowed. Invalid entries are rejected (setAllowInvalid(false)).
//   Call-point cells accept numbers only, also hard-reject.

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
      .setAllowInvalid(false) // hard reject: invalid entries refused on commit
      .setHelpText(
        'Allowed request codes: ' + tokensList + '. ' +
        'Single code or comma-separated combinations (e.g. "CR, NC"). ' +
        'Blank is OK. Invalid entries are rejected.')
      .build();

    range.setDataValidation(rule);
  }

  // Call-point cells: numbers only (hard reject). Defaults emitted by Layout
  // (1, 1.5, 1.75, 2 per the 4-case rule) are all valid.
  for (var j = 0; j < layoutInfo.pointRowRanges.length; j++) {
    var pr = layoutInfo.pointRowRanges[j];
    var prange = sheet.getRange(pr.row, pr.col, pr.numRows, pr.numCols);
    var prule = SpreadsheetApp.newDataValidation()
      .requireNumberGreaterThanOrEqualTo(0)
      .setAllowInvalid(false)
      .setHelpText('Call Point cells accept numbers only (non-negative).')
      .build();
    prange.setDataValidation(prule);
  }
}
