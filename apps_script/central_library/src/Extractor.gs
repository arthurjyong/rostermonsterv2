// Extractor.gs
// Public entrypoint of the snapshot-extractor library per
// `docs/decision_log.md` D-0041 + `docs/snapshot_adapter_contract.md`.
//
// The bound shim (`apps_script/bound_shim/`) calls
// `extractSnapshotForActiveSheet()` from its menu handler. We:
//
//   1. Identify the active request-entry tab (§6 step 1).
//   2. Read the active tab's runId (§6 step 2).
//   3. Locate the paired Scorer Config tab (§6 step 3).
//   4. Read all per-row anchors via sheet-scoped finders (§6 step 4).
//   5. Validate cardinality / uniqueness / value-coverage (§6 step 5).
//   6. Read cells at column offsets and emit records (§6 steps 7 + 8).
//   7. Build the Snapshot top-level shape (§6 step 9).
//   8. Wrap as a downloadable JSON blob (§7) and return an HtmlOutput
//      that the bound shim can show via `showModalDialog`.
//
// ALL metadata-finder calls MUST be sheet-scoped per D-0043 sub-decision 2.
// Workbook-scoped finders silently mix anchors across multiple request-entry
// tabs (operator-duplicated history, regenerated periods).

function extractSnapshotForActiveSheet() {
  try {
    var snapshot = _buildSnapshotForActiveSheet_();
    var json = JSON.stringify(snapshot, null, 2);
    var filename = snapshot.metadata.snapshotId + '.json';
    return _buildDownloadHtml_(json, filename);
  } catch (e) {
    var msg = (e && e.message) ? e.message : String(e);
    return _buildErrorHtml_(msg);
  }
}

// In-memory snapshot extraction entrypoint per `docs/decision_log.md`
// D-0049 + D-0052 (M4 C1 cloud-mode dual track) + `docs/snapshot_adapter_contract.md`
// §7 in-memory addendum. Returns the Snapshot-shape JavaScript object
// directly (NOT wrapped in download HTML), so the bound shim's
// "Solve Roster" handler can ship it straight to Cloud Run via
// UrlFetchApp without a file boundary.
//
// Errors propagate as exceptions (caller catches and renders into the
// bound shim's error dialog) rather than being wrapped in error HTML
// like `extractSnapshotForActiveSheet` does — the bound shim path
// orchestrates extract + cloud + writeback as one operation, so the
// extract step's error surface is "throw and let orchestrator catch."
function extractSnapshotInMemoryForActiveSheet() {
  return _buildSnapshotForActiveSheet_();
}

// Internal: orchestrates §6 steps 1..9. Throws Error with a user-facing
// message on any extraction-blocking defect; the public entrypoint catches
// and renders the message into an error HtmlOutput.
function _buildSnapshotForActiveSheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var requestSheet = SpreadsheetApp.getActiveSheet();

  // §6 step 1: validate the active sheet is a request-entry tab.
  var activeTabType = _readSingleSheetMeta_(requestSheet, 'rosterMonster:tabType');
  if (activeTabType !== 'requestEntry') {
    throw new Error(
      'EXTRACTION_ERROR: not a request-entry tab — open the period\'s ' +
      'request-entry tab and retry.'
    );
  }

  // §6 step 2: read the active tab's runId.
  var runId = _readSingleSheetMeta_(requestSheet, 'rosterMonster:runId');
  if (!runId) {
    throw new Error(
      'EXTRACTION_ERROR: rosterMonster:runId not found on this request-entry ' +
      'tab — sheet may predate the M2 C9 metadata extension. Regenerate via ' +
      'the launcher.'
    );
  }

  // §6 step 3: locate the paired Scorer Config tab in the same spreadsheet.
  var scorerSheet = _locatePairedScorerConfigTab_(ss, runId);

  // §6 step 4..5: read per-row anchors + cardinality validation.
  var requestAnchors = _readAndValidateRequestAnchors_(requestSheet);
  var scorerAnchors = _readAndValidateScorerAnchors_(scorerSheet);

  // §6 step 7..9: emit records + build top-level snapshot.
  return _buildSnapshotFromAnchors_(
    ss, requestSheet, scorerSheet, runId, requestAnchors, scorerAnchors);
}

// Locate the unique Scorer Config tab whose sheet-level rosterMonster:runId
// matches the active request-entry tab's runId. Per §6 step 3.
function _locatePairedScorerConfigTab_(ss, runId) {
  var sheets = ss.getSheets();
  var matches = [];
  for (var i = 0; i < sheets.length; i++) {
    var s = sheets[i];
    var tabType = _readSingleSheetMeta_(s, 'rosterMonster:tabType');
    if (tabType !== 'scorerConfig') continue;
    var sRunId = _readSingleSheetMeta_(s, 'rosterMonster:runId');
    if (sRunId === runId) matches.push(s);
  }
  if (matches.length === 0) {
    throw new Error(
      'EXTRACTION_ERROR: paired Scorer Config tab not found for runId ' +
      runId + '. Regenerate via the launcher to recover the missing tab.'
    );
  }
  if (matches.length > 1) {
    throw new Error(
      'EXTRACTION_ERROR: paired Scorer Config tab ambiguous for runId ' +
      runId + ' (' + matches.length + ' tabs match). Manually rename or ' +
      'delete duplicates and retry.'
    );
  }
  return matches[0];
}

// Read a single sheet-level DeveloperMetadata value by key. Returns null if
// no match found. Throws if more than one match is found (sheet-level
// metadata is supposed to be unique per key per generation).
function _readSingleSheetMeta_(sheet, key) {
  var matches = sheet.createDeveloperMetadataFinder().withKey(key).find();
  if (matches.length === 0) return null;
  if (matches.length > 1) {
    throw new Error(
      'EXTRACTION_ERROR: sheet-level metadata key ' + key + ' has ' +
      matches.length + ' matches on tab "' + sheet.getName() + '"; ' +
      'expected exactly one. Sheet may be corrupted; regenerate via the ' +
      'launcher.'
    );
  }
  return matches[0].getValue();
}

// Read all sheet-level DeveloperMetadata entries whose keys begin with a
// given prefix. Returns a map: { keySuffix → value }. Used for the variable-
// cardinality `expectedDoctorCount.<sectionKey>` lookup pattern.
function _readSheetMetaPrefix_(sheet, prefix) {
  var out = {};
  var sheetMetadata = sheet.getDeveloperMetadata();
  for (var i = 0; i < sheetMetadata.length; i++) {
    var key = sheetMetadata[i].getKey();
    if (key && key.indexOf(prefix) === 0) {
      out[key.substring(prefix.length)] = sheetMetadata[i].getValue();
    }
  }
  return out;
}

// §6 step 4..5 for the request-entry tab: read per-row anchors via sheet-
// scoped finders, validate cardinality + uniqueness + value-coverage per
// D-0043 sub-decision 3.
function _readAndValidateRequestAnchors_(sheet) {
  var dayAxisRows = _findRowAnchors_(sheet, 'rosterMonster:dayAxis');
  _validateExactlyOne_(dayAxisRows, 'rosterMonster:dayAxis', sheet.getName());

  var sectionRows = _findRowAnchors_(sheet, 'rosterMonster:section');
  var doctorRows = _findRowAnchors_(sheet, 'rosterMonster:doctorRow');
  var callPointRows = _findRowAnchors_(sheet, 'rosterMonster:callPointRow');
  var assignmentRows = _findRowAnchors_(sheet, 'rosterMonster:assignmentRow');

  // Read expected-cardinality anchors (sheet-level).
  var expectedDoctorCounts = _readSheetMetaPrefix_(
    sheet, 'rosterMonster:expectedDoctorCount.');
  var expectedDayCount = _readSingleSheetMeta_(
    sheet, 'rosterMonster:expectedDayCount');
  if (expectedDayCount === null) {
    throw new Error(
      'EXTRACTION_ERROR: rosterMonster:expectedDayCount not found on tab ' +
      '"' + sheet.getName() + '" — sheet may predate the M2 C9 metadata ' +
      'extension. Regenerate via the launcher.'
    );
  }
  var expectedAssignmentRowCountStr = _readSingleSheetMeta_(
    sheet, 'rosterMonster:expectedAssignmentRowCount');
  if (expectedAssignmentRowCountStr === null) {
    throw new Error(
      'EXTRACTION_ERROR: rosterMonster:expectedAssignmentRowCount not found ' +
      'on tab "' + sheet.getName() + '" — sheet may predate the M2 C9 ' +
      'assignment-row coverage extension. Regenerate via the launcher.'
    );
  }
  var expectedAssignmentRowCount = parseInt(
    String(expectedAssignmentRowCountStr), 10);

  // Per D-0043 sub-decision 3: validate cardinality + uniqueness + coverage.
  _validateDoctorRowCoverage_(doctorRows, expectedDoctorCounts, sheet.getName());
  _validateSectionCoverage_(sectionRows, expectedDoctorCounts, sheet.getName());
  _validateCallPointRowCoverage_(callPointRows, sheet.getName());
  _validateAssignmentRowCoverage_(assignmentRows, expectedAssignmentRowCount,
    sheet.getName());
  // dayAxis is a single-row anchor; cardinality of the day cells is
  // validated at SnapshotBuilder time when we read the day-axis row.

  return {
    dayAxisRow: dayAxisRows[0].rowIndex,
    sectionRows: sectionRows,
    doctorRows: doctorRows,
    callPointRows: callPointRows,
    assignmentRows: assignmentRows,
    expectedDoctorCounts: expectedDoctorCounts,
    expectedDayCount: parseInt(String(expectedDayCount), 10),
    expectedAssignmentRowCount: expectedAssignmentRowCount,
  };
}

// §6 step 4..5 for the Scorer Config tab.
function _readAndValidateScorerAnchors_(sheet) {
  var componentRows = _findRowAnchors_(sheet, 'rosterMonster:componentId');
  _validateComponentIdCoverage_(componentRows, sheet.getName());
  return { componentRows: componentRows };
}

// Find all DeveloperMetadata anchors on `sheet` whose key matches `key`,
// scoped to the sheet (NOT spreadsheet) per D-0043 sub-decision 2. Returns
// an array of `{ rowIndex, value }` objects sorted by rowIndex.
function _findRowAnchors_(sheet, key) {
  var matches = sheet.createDeveloperMetadataFinder().withKey(key).find();
  var anchors = [];
  for (var i = 0; i < matches.length; i++) {
    var loc = matches[i].getLocation();
    var locType = loc.getLocationType();
    if (locType !== SpreadsheetApp.DeveloperMetadataLocationType.ROW) {
      // Defensive: anchors of this kind are supposed to be row-scoped per
      // the launcher's `attachRowMetadata_` helper. Wrong location type
      // indicates corruption or a launcher-generation bug.
      throw new Error(
        'EXTRACTION_ERROR: metadata key ' + key + ' on tab "' +
        sheet.getName() + '" is not row-scoped (got ' + locType + '). ' +
        'Sheet may be corrupted; regenerate via the launcher.'
      );
    }
    var rowRange = loc.getRow();
    anchors.push({
      rowIndex: rowRange.getRow(),
      value: matches[i].getValue(),
    });
  }
  anchors.sort(function (a, b) { return a.rowIndex - b.rowIndex; });
  return anchors;
}

function _validateExactlyOne_(anchors, key, tabName) {
  if (anchors.length !== 1) {
    throw new Error(
      'EXTRACTION_ERROR: ' + key + ' coverage mismatch on tab "' + tabName +
      '" — expected exactly 1, got ' + anchors.length + '.'
    );
  }
}
