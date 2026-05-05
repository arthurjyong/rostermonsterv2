// SnapshotBuilder.gs
// Translates the validated DeveloperMetadata anchor reads + cell content
// into a Snapshot-shape JS object per `docs/snapshot_contract.md` §5..§12.
// Cells are read at column offsets relative to the metadata-anchored row
// per `docs/snapshot_adapter_contract.md` §6 step 7. Raw text is preserved
// untrimmed per the adapter discipline in §3 of snapshot_contract.md.

// Public from Extractor.gs. Builds the top-level snapshot object.
function _buildSnapshotFromAnchors_(ss, requestSheet, scorerSheet, runId,
                                     requestAnchors, scorerAnchors) {
  var spreadsheetId = ss.getId();
  var extractionTimestamp = _isoFilenameSafeTimestamp_(new Date());
  var snapshotId = 'snapshot_' + spreadsheetId + '_' + extractionTimestamp;

  // Read the day axis row first; everything else is keyed on its column span.
  var dayRecords = _buildDayRecords_(requestSheet, requestAnchors.dayAxisRow,
    requestAnchors.expectedDayCount);
  var dayColumnByIndex = {}; // dayIndex → 1-indexed column number
  for (var i = 0; i < dayRecords.length; i++) {
    dayColumnByIndex[dayRecords[i].dayIndex] = dayRecords[i]._sourceColumn;
    delete dayRecords[i]._sourceColumn; // strip transient field before serializing
  }

  var doctorRecords = _buildDoctorRecords_(requestSheet, requestAnchors);
  var requestRecords = _buildRequestRecords_(
    requestSheet, requestAnchors, dayColumnByIndex);
  var prefilledAssignmentRecords = _buildPrefilledAssignmentRecords_(
    requestSheet, requestAnchors, dayColumnByIndex);
  var scoringConfigRecords = _buildScoringConfigRecords_(
    requestSheet, scorerSheet, requestAnchors, scorerAnchors,
    dayColumnByIndex);

  // templateId / templateVersion are read from sheet-level metadata
  // (templateVersion was attached at generation per D-0043 sub-decision 1).
  // First-release templateId is hard-coded `cgh_icu_hd` since the launcher
  // is single-template; future multi-template work surfaces this as a
  // sheet-level anchor.
  var templateVersion = parseInt(
    String(_readSingleSheetMeta_(requestSheet, 'rosterMonster:templateVersion') ||
      '1'), 10);

  return {
    metadata: {
      snapshotId: snapshotId,
      templateId: 'cgh_icu_hd',
      templateVersion: templateVersion,
      sourceSpreadsheetId: spreadsheetId,
      sourceTabName: requestSheet.getName(),
      generationTimestamp: new Date().toISOString(),
      periodRef: {
        // First-release periodId is the runId (matches launcher convention).
        // periodLabel left empty per `docs/snapshot_contract.md` §6.
        periodId: runId,
        periodLabel: '',
      },
      extractionSummary: {
        doctorRecordCount: doctorRecords.length,
        dayRecordCount: dayRecords.length,
        requestRecordCount: requestRecords.length,
        prefilledAssignmentRecordCount: prefilledAssignmentRecords.length,
        componentWeightRecordCount: scoringConfigRecords.componentWeightRecords.length,
        callPointRecordCount: scoringConfigRecords.callPointRecords.length,
      },
    },
    doctorRecords: doctorRecords,
    dayRecords: dayRecords,
    requestRecords: requestRecords,
    prefilledAssignmentRecords: prefilledAssignmentRecords,
    scoringConfigRecords: scoringConfigRecords,
  };
}

// Day records: read each populated date cell from the day-axis row,
// normalize to ISO 8601 per D-0033, emit one record per day.
function _buildDayRecords_(sheet, dayAxisRow, expectedDayCount) {
  // Day cells start at column 2 (column A is the row label).
  var firstCol = 2;
  var totalCols = sheet.getMaxColumns();
  var records = [];
  for (var col = firstCol; col <= totalCols; col++) {
    var cellValue = sheet.getRange(dayAxisRow, col).getValue();
    if (cellValue === '' || cellValue === null) continue;
    var isoDate = _normalizeToIsoDate_(cellValue);
    var dayIndex = records.length;
    records.push({
      dayIndex: dayIndex,
      rawDateText: isoDate, // ISO-normalized at adapter per D-0033
      sourceLocator: {
        surfaceKey: 'dayAxis',
        dayIndex: dayIndex,
      },
      physicalSourceRef: {
        sheetName: sheet.getName(),
        sheetGid: sheet.getSheetId(),
        a1Refs: [_a1Ref_(dayAxisRow, col)],
      },
      _sourceColumn: col, // transient — stripped by caller before serializing
    });
  }
  if (records.length !== expectedDayCount) {
    throw new Error(
      'EXTRACTION_ERROR: day-axis cardinality mismatch — expected ' +
      expectedDayCount + ', got ' + records.length + '. Sheet may have ' +
      'extra populated cells in the day-axis row, or the operator has ' +
      'modified the row beyond the launcher-locked column structure.'
    );
  }
  return records;
}

// Doctor records: one per doctor row anchor. Field shape matches the live
// Python `DoctorRecord` dataclass (`python/rostermonster/snapshot.py`):
// `sourceDoctorKey` (raw extractor-generated key), `displayName` (column A
// content), `rawSectionText` (the section header row's column A text).
// `sourceLocator` is flattened (no `path` wrapper) — the contract describes
// the typed shape with `path = {...}` but the live JSON serialization the
// parser consumes inlines the locator fields.
function _buildDoctorRecords_(sheet, anchors) {
  // Index section header anchors by sectionKey so we can look up the header
  // row's column-A text per doctor record.
  var sectionHeaderRowBySectionKey = {};
  for (var s = 0; s < anchors.sectionRows.length; s++) {
    sectionHeaderRowBySectionKey[anchors.sectionRows[s].value] =
      anchors.sectionRows[s].rowIndex;
  }

  var records = [];
  for (var i = 0; i < anchors.doctorRows.length; i++) {
    var a = anchors.doctorRows[i];
    var v = a.value; // `<sectionKey>:<index>`
    var colonIdx = v.indexOf(':');
    var sectionKey = v.substring(0, colonIdx);
    var doctorIndexInSection = parseInt(v.substring(colonIdx + 1), 10);
    var displayName = sheet.getRange(a.rowIndex, 1).getValue();
    var sectionHeaderRow = sectionHeaderRowBySectionKey[sectionKey];
    var rawSectionText = sectionHeaderRow != null
      ? sheet.getRange(sectionHeaderRow, 1).getValue() : '';
    records.push({
      // sourceDoctorKey shape mirrors the existing test fixture convention
      // (`<lowercase-section>_dr_<idx>`) so the parser's downstream
      // matching is unaffected.
      sourceDoctorKey: sectionKey.toLowerCase() + '_dr_' +
        doctorIndexInSection,
      displayName: String(displayName == null ? '' : displayName),
      rawSectionText: String(rawSectionText == null ? '' : rawSectionText),
      sourceLocator: {
        surfaceKey: 'doctorRows',
        sectionKey: sectionKey,
        doctorIndexInSection: doctorIndexInSection,
      },
      physicalSourceRef: {
        sheetName: sheet.getName(),
        sheetGid: sheet.getSheetId(),
        a1Refs: [_a1Ref_(a.rowIndex, 1)],
      },
    });
  }
  return records;
}

// Request records: one per (doctor row × day column) cell in the request-
// entry grid. Includes blank cells (raw text preserved untrimmed per §3 of
// snapshot_contract.md).
function _buildRequestRecords_(sheet, anchors, dayColumnByIndex) {
  var records = [];
  var dayIndexes = Object.keys(dayColumnByIndex).map(Number).sort(
    function (a, b) { return a - b; });
  for (var i = 0; i < anchors.doctorRows.length; i++) {
    var docAnchor = anchors.doctorRows[i];
    var v = docAnchor.value;
    var colonIdx = v.indexOf(':');
    var sectionKey = v.substring(0, colonIdx);
    var doctorIndexInSection = parseInt(v.substring(colonIdx + 1), 10);
    // Same sourceDoctorKey shape as `_buildDoctorRecords_` — must agree so
    // the parser can match request records to their owning doctor records.
    var sourceDoctorKey = sectionKey.toLowerCase() + '_dr_' +
      doctorIndexInSection;
    for (var j = 0; j < dayIndexes.length; j++) {
      var dayIndex = dayIndexes[j];
      var col = dayColumnByIndex[dayIndex];
      var rawText = sheet.getRange(docAnchor.rowIndex, col).getValue();
      records.push({
        sourceDoctorKey: sourceDoctorKey,
        dayIndex: dayIndex,
        rawRequestText: String(rawText == null ? '' : rawText),
        sourceLocator: {
          surfaceKey: 'requestCells',
          sourceDoctorKey: sourceDoctorKey,
          dayIndex: dayIndex,
        },
        physicalSourceRef: {
          sheetName: sheet.getName(),
          sheetGid: sheet.getSheetId(),
          a1Refs: [_a1Ref_(docAnchor.rowIndex, col)],
        },
      });
    }
  }
  return records;
}

// Prefilled-assignment records: one per (assignment shell row × day column)
// cell in the lower-shell roster grid. Only emit records for populated cells
// per `docs/snapshot_contract.md` §11 — blank cells are not pre-filled and
// don't generate trace records.
function _buildPrefilledAssignmentRecords_(sheet, anchors, dayColumnByIndex) {
  var records = [];
  var dayIndexes = Object.keys(dayColumnByIndex).map(Number).sort(
    function (a, b) { return a - b; });
  for (var i = 0; i < anchors.assignmentRows.length; i++) {
    var rowAnchor = anchors.assignmentRows[i];
    var v = rowAnchor.value; // `<surfaceId>:<rowOffset>`
    var colonIdx = v.indexOf(':');
    var surfaceId = v.substring(0, colonIdx);
    var rowOffset = parseInt(v.substring(colonIdx + 1), 10);
    for (var j = 0; j < dayIndexes.length; j++) {
      var dayIndex = dayIndexes[j];
      var col = dayColumnByIndex[dayIndex];
      var rawText = sheet.getRange(rowAnchor.rowIndex, col).getValue();
      if (rawText === '' || rawText === null) continue; // skip blanks
      records.push({
        dayIndex: dayIndex,
        rawAssignedDoctorText: String(rawText),
        surfaceId: surfaceId,
        rowOffset: rowOffset,
        sourceLocator: {
          surfaceKey: 'outputMapping',
          surfaceId: surfaceId,
          rowOffset: rowOffset,
          dayIndex: dayIndex,
        },
        physicalSourceRef: {
          sheetName: sheet.getName(),
          sheetGid: sheet.getSheetId(),
          a1Refs: [_a1Ref_(rowAnchor.rowIndex, col)],
        },
      });
    }
  }
  return records;
}

// Scoring-config records per `docs/snapshot_contract.md` §11A: two kinds.
// componentWeightRecords come from the Scorer Config tab; callPointRecords
// come from the call-point rows on the request-entry tab.
function _buildScoringConfigRecords_(requestSheet, scorerSheet,
                                       requestAnchors, scorerAnchors,
                                       dayColumnByIndex) {
  var componentWeightRecords = [];
  var WEIGHT_COL = 2;
  for (var i = 0; i < scorerAnchors.componentRows.length; i++) {
    var row = scorerAnchors.componentRows[i];
    var rawValue = scorerSheet.getRange(row.rowIndex, WEIGHT_COL).getValue();
    componentWeightRecords.push({
      componentId: row.value,
      rawValue: String(rawValue == null ? '' : rawValue),
      sourceLocator: {
        surfaceKey: 'scorerConfigCells',
        componentId: row.value,
      },
      physicalSourceRef: {
        sheetName: scorerSheet.getName(),
        sheetGid: scorerSheet.getSheetId(),
        a1Refs: [_a1Ref_(row.rowIndex, WEIGHT_COL)],
      },
    });
  }

  var callPointRecords = [];
  var dayIndexes = Object.keys(dayColumnByIndex).map(Number).sort(
    function (a, b) { return a - b; });
  for (var p = 0; p < requestAnchors.callPointRows.length; p++) {
    var pAnchor = requestAnchors.callPointRows[p];
    for (var d = 0; d < dayIndexes.length; d++) {
      var dayIndex = dayIndexes[d];
      var col = dayColumnByIndex[dayIndex];
      var rawText = requestSheet.getRange(pAnchor.rowIndex, col).getValue();
      callPointRecords.push({
        callPointRowKey: pAnchor.value,
        dayIndex: dayIndex,
        rawValue: String(rawText == null ? '' : rawText),
        sourceLocator: {
          surfaceKey: 'callPointCells',
          callPointRowKey: pAnchor.value,
          dayIndex: dayIndex,
        },
        physicalSourceRef: {
          sheetName: requestSheet.getName(),
          sheetGid: requestSheet.getSheetId(),
          a1Refs: [_a1Ref_(pAnchor.rowIndex, col)],
        },
      });
    }
  }

  return {
    componentWeightRecords: componentWeightRecords,
    callPointRecords: callPointRecords,
  };
}

// ---- helpers --------------------------------------------------------------

// Convert (1-indexed row, 1-indexed col) to A1 notation (e.g., (2, 3) → "C2").
function _a1Ref_(row, col) {
  var letters = '';
  var n = col;
  while (n > 0) {
    var rem = (n - 1) % 26;
    letters = String.fromCharCode(65 + rem) + letters;
    n = Math.floor((n - 1) / 26);
  }
  return letters + row;
}

// Normalize a date cell value to ISO 8601 `YYYY-MM-DD` per D-0033. Apps
// Script returns Date objects for date-formatted cells and strings
// otherwise. We accept either.
function _normalizeToIsoDate_(value) {
  if (value instanceof Date) {
    var tz = Session.getScriptTimeZone() || 'Asia/Singapore';
    return Utilities.formatDate(value, tz, 'yyyy-MM-dd');
  }
  var s = String(value).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  // Try to parse other shapes; fail loudly if we can't.
  var d = new Date(s);
  if (isFinite(d.getTime())) {
    var tz2 = Session.getScriptTimeZone() || 'Asia/Singapore';
    return Utilities.formatDate(d, tz2, 'yyyy-MM-dd');
  }
  throw new Error(
    'EXTRACTION_ERROR: day-axis cell value "' + value + '" is not a ' +
    'recognizable date — extractor cannot normalize per D-0033. ' +
    'Sheet may be corrupted; regenerate via the launcher.'
  );
}

// Filename-safe ISO 8601 timestamp (`YYYY-MM-DDTHH-MM-SS`) per D-0042 sub-1.
function _isoFilenameSafeTimestamp_(date) {
  var tz = Session.getScriptTimeZone() || 'Asia/Singapore';
  return Utilities.formatDate(date, tz, "yyyy-MM-dd'T'HH-mm-ss");
}
