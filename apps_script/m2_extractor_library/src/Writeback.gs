// Writeback.gs
// Pure adapter from `(finalResultEnvelope, snapshot, doctorIdMap)` to a
// new tab in the source spreadsheet, per `docs/writeback_contract.md` §6.2.
// Public entry: `applyWriteback(envelopeJsonString)` — invoked by the
// launcher's writeback route per `docs/decision_log.md` D-0046.
//
// Implements:
// - §11 always-new-tab branch-on-write semantics + tab-name discipline
// - §10 success-branch + failure-branch tab content
// - §12 doctor identity resolution via doctorIdMap → column-A cell value
// - §13 failure-branch tab minimum content
// - §14 atomicity: cleanup-on-failure, orphan-tab name surfaced if cleanup fails
// - §16 4-row visible traceability footer + 6-key hidden DeveloperMetadata
// - §10.3 + §13.4 whole-tab read-only protection
//
// Source-tab invariance (§11.2): writeback NEVER mutates the source tab
// `runEnvelope.sourceTabName`. Every invocation creates a new tab.

// Public API surface — invoked by the launcher's writeback route per
// D-0046 sub-decision 3. Parameter is the JSON string the operator
// uploaded (the writeback wrapper envelope per D-0045). Returns the
// 3-state diagnostic per §17 as a structured object.
function applyWriteback(envelopeJsonString) {
  var envelope;
  try {
    envelope = JSON.parse(envelopeJsonString);
  } catch (e) {
    return _writebackError_(
      'Could not parse uploaded JSON: ' + (e && e.message ? e.message : String(e))
    );
  }
  return _applyWritebackInner_(envelope);
}

// Internal orchestrator. Wrapped in try/catch by the public entry so any
// failure surfaces through §17.3 runtime-error state.
function _applyWritebackInner_(envelope) {
  var validationError = _validateWritebackEnvelopeShape_(envelope);
  if (validationError) {
    return _writebackError_(validationError);
  }

  var fre = envelope.finalResultEnvelope;
  var runEnv = fre.runEnvelope;
  var spreadsheetId = runEnv.sourceSpreadsheetId;
  var sourceTabName = runEnv.sourceTabName;

  var ss;
  try {
    ss = SpreadsheetApp.openById(spreadsheetId);
  } catch (e) {
    return _writebackError_(
      'Could not open source spreadsheet (sourceSpreadsheetId=' + spreadsheetId +
      '): ' + (e && e.message ? e.message : String(e)) +
      '. Verify the operator account has Drive Editor access to the spreadsheet.'
    );
  }

  // Tab-name build + tab creation MUST surface through the §17.3
  // RUNTIME_ERROR diagnostic, not the client's withFailureHandler
  // (which would deliver an unstructured infrastructure error).
  // `_buildWritebackTabName_` throws on pathological source-tab names
  // (§11.1.1 length-truncation impossible) or §11.1.2 collision-suffix
  // exhaustion; `ss.insertSheet` throws on Sheets-side failures (sheet
  // count limit, race-condition collision, invalid name characters).
  // No cleanup is needed — `insertSheet` either succeeds and returns
  // the sheet or throws without leaving an orphan tab.
  var newTabName, sheet;
  try {
    newTabName = _buildWritebackTabName_(ss, sourceTabName);
    sheet = ss.insertSheet(newTabName);
  } catch (e) {
    return _writebackError_(
      'Could not create writeback tab: ' +
      (e && e.message ? e.message : String(e))
    );
  }

  try {
    var isSuccess = _isAllocationResult_(fre.result);
    if (isSuccess) {
      _renderSuccessBranch_(sheet, envelope);
    } else {
      _renderFailureBranch_(sheet, envelope);
    }
    _attachTraceabilityFooter_(sheet, envelope, isSuccess);
    _attachTraceabilityMetadata_(sheet, envelope, isSuccess);
    _protectWritebackTab_(sheet);
    return _writebackSuccess_(sheet, isSuccess, ss);
  } catch (e) {
    var msg = (e && e.message) ? e.message : String(e);
    var orphan = null;
    try {
      ss.deleteSheet(sheet);
    } catch (cleanupErr) {
      orphan = newTabName;
    }
    if (orphan) {
      return _writebackError_(
        'Writeback failed mid-write and cleanup also failed; orphaned tab ' +
        '"' + orphan + '" remains and must be manually deleted. Underlying ' +
        'error: ' + msg
      );
    }
    return _writebackError_('Writeback failed mid-write: ' + msg);
  }
}

// --- envelope validation ---------------------------------------------------

// Validate the writeback wrapper envelope's required-categories set per
// `docs/decision_log.md` D-0045 + writeback contract §9. Returns null if
// valid, or a string error message otherwise (caller wraps into the §17.3
// runtime-error state).
function _validateWritebackEnvelopeShape_(envelope) {
  if (!envelope || typeof envelope !== 'object') {
    return 'Uploaded JSON is not an object.';
  }
  if (!envelope.finalResultEnvelope) {
    return 'Uploaded JSON is missing the `finalResultEnvelope` field. ' +
      'Did you upload the bare result envelope by mistake? The writeback ' +
      'form expects the wrapper envelope produced by ' +
      '`python -m rostermonster.run` (which is the writeback envelope by ' +
      'default; pass --writeback-ready=true if you disabled it).';
  }
  if (!envelope.snapshot) {
    return 'Uploaded JSON is missing the `snapshot` subset.';
  }
  if (!envelope.doctorIdMap || !Array.isArray(envelope.doctorIdMap)) {
    return 'Uploaded JSON is missing the `doctorIdMap` array.';
  }
  var fre = envelope.finalResultEnvelope;
  if (!fre.runEnvelope) {
    return '`finalResultEnvelope.runEnvelope` is missing.';
  }
  if (!fre.runEnvelope.sourceSpreadsheetId) {
    return '`finalResultEnvelope.runEnvelope.sourceSpreadsheetId` is missing ' +
      '(required per `docs/selector_contract.md` v2 §9 item 3).';
  }
  if (!fre.runEnvelope.sourceTabName) {
    return '`finalResultEnvelope.runEnvelope.sourceTabName` is missing ' +
      '(required per `docs/selector_contract.md` v2 §9 item 3).';
  }
  if (fre.result === null || fre.result === undefined) {
    return '`finalResultEnvelope.result` is missing.';
  }
  return null;
}

// Branch detector: AllocationResult vs UnsatisfiedResultEnvelope per
// `docs/selector_contract.md` §10. AllocationResult has `winnerAssignment`;
// UnsatisfiedResultEnvelope has `unfilledDemand` + `reasons`.
function _isAllocationResult_(result) {
  return Object.prototype.hasOwnProperty.call(result, 'winnerAssignment');
}

// --- tab name (§11.1) ------------------------------------------------------

// Build the writeback tab name per §11.1: `<source-tab-prefix>_RM<YYMMDDHHMMSS>`
// with §11.1.1 length-limit truncation (max 100 chars; truncate prefix from
// the right) and §11.1.2 collision auto-suffix (`_2`, `_3`, ...). Timestamp
// is UTC second-resolution per the contract's locale-independence rule.
function _buildWritebackTabName_(ss, sourceTabName) {
  var ts = _utcWritebackTimestamp_();
  var suffix = '_RM' + ts;
  var maxLen = 100; // Google Sheets tab-name limit
  var existingNames = {};
  var existing = ss.getSheets();
  for (var i = 0; i < existing.length; i++) {
    existingNames[existing[i].getName()] = true;
  }
  // Try increasing collision suffixes (`_2`, `_3`, ...) until we land on a
  // name that fits AND is unique. Per §11.1.1 we truncate the prefix, not
  // the suffix.
  for (var k = 1; k <= 1000; k++) {
    var collisionSuffix = (k === 1) ? '' : ('_' + k);
    var totalSuffixLen = suffix.length + collisionSuffix.length;
    var maxPrefixLen = maxLen - totalSuffixLen;
    if (maxPrefixLen < 1) {
      // Pathological: someone passed a sourceTabName so weird that even the
      // fixed suffix doesn't fit. Surface as runtime error.
      throw new Error('Writeback tab name cannot fit within ' + maxLen +
        ' characters; suffix `' + suffix + collisionSuffix + '` already ' +
        'exceeds the limit. Source tab name: "' + sourceTabName + '".');
    }
    var prefix = sourceTabName.length > maxPrefixLen
      ? sourceTabName.substring(0, maxPrefixLen)
      : sourceTabName;
    var candidate = prefix + suffix + collisionSuffix;
    if (!existingNames[candidate]) {
      return candidate;
    }
  }
  throw new Error('Writeback tab-name collision exhausted at k=1000; ' +
    'spreadsheet has too many same-second writeback tabs.');
}

// UTC `YYMMDDHHMMSS` per §11.1. Locale-independent.
function _utcWritebackTimestamp_() {
  return Utilities.formatDate(new Date(), 'UTC', 'yyMMddHHmmss');
}

// --- success-branch rendering (§10.1) --------------------------------------

// M1.1 visual palette — identical hex values to
// `apps_script/m1_sheet_generator/src/Layout.gs` LAYOUT_COLORS_ so the
// writeback tab matches the operator-input shell aesthetically. ICU/HD-
// specific label maps below are first-release hardcodes per the M4 C1
// "minimum demo" quality bar (D-0049); template-aware label propagation
// is FW-0029 territory.
var _WB_COLORS_ = Object.freeze({
  titleBg:     '#1f4e78',
  titleFg:     '#ffffff',
  sectionBg:   '#d9d9d9',
  pointBg:     '#fff2cc',
  lowerBg:     '#c6e0b4',
  weekendBg:   '#fce5cd',
  headerRowBg: '#e7e6e6',
});

// ICU/HD first-release section header labels per
// `apps_script/m1_sheet_generator/src/TemplateData.gs`'s sections. Falls
// back to the raw sectionKey if a key isn't in the map (defensive — the
// M2 C9 snapshot extractor and the M1.1 generator share the same
// sectionKey vocabulary, so all keys should be present).
var _WB_SECTION_LABELS_ = Object.freeze({
  MICU: 'MICU  (ICU_ONLY)',
  MICU_HD: 'ICU + HD  (ICU_HD)',
  MHD: 'MHD  (HD_ONLY)',
});

// Call-point row labels per `pointRows[i].label` in TemplateData.gs.
var _WB_POINT_ROW_LABELS_ = Object.freeze({
  MICU_CALL_POINT: 'MICU Call Point',
  MHD_CALL_POINT: 'MHD Call Point',
});

// Slot labels per `template.slots[i].label`. ICU/HD has 4 slot types.
var _WB_SLOT_LABELS_ = Object.freeze({
  MICU_CALL: 'MICU Call',
  MICU_STANDBY: 'MICU Standby',
  MHD_CALL: 'MHD Call',
  MHD_STANDBY: 'MHD Standby',
});

// Render the success-branch writeback tab per §10.1. The tab carries:
// - reconstructed M1-style shell from snapshot bundle's shellParameters +
//   columnADoctorNames (operator-readable as a roster shell on its own),
// - requestCells / callPointCells / prefilledFixedAssignmentCells from
//   the snapshot bundle written into their cell positions,
// - winner allocation: every AssignmentUnit from
//   finalResultEnvelope.result.winnerAssignment rendered with the
//   column-A cell value of the resolved doctor (§12).
//
// Visual styling matches `apps_script/m1_sheet_generator/src/Layout.gs`'s
// empty-shell generation per the M4 C1 Phase 2 polish pass — same color
// palette, same friendly labels, weekend column shading, frozen panes.
// Label maps live in `_WB_SECTION_LABELS_` / `_WB_POINT_ROW_LABELS_` /
// `_WB_SLOT_LABELS_` above (ICU/HD-specific hardcodes per FW-0029).
function _renderSuccessBranch_(sheet, envelope) {
  var fre = envelope.finalResultEnvelope;
  var snap = envelope.snapshot;
  var doctorIdMap = envelope.doctorIdMap;
  var winnerAssignments = fre.result.winnerAssignment || [];
  var dayKeys = _collectDayKeys_(snap);
  var nameCol = 1;
  var firstDateCol = 2;
  var totalCols = firstDateCol + dayKeys.length - 1;

  var currentRow = 1;
  // Track rows whose intentional bg color must "win" over weekend-column
  // shading (same pattern as `apps_script/m1_sheet_generator/src/Layout.gs`'s
  // bandedRows mechanism). Weekend shading is applied last per column,
  // then these row-level backgrounds are reapplied to overwrite.
  var bandedRows = [];

  // ---- Row 1: title (same navy bg + white bold 14pt as M1.1) ----
  var params = snap.shellParameters || {};
  var dept = params.department || '';
  var startDate = params.periodStartDate || (dayKeys[0] || '');
  var endDate = params.periodEndDate || (dayKeys[dayKeys.length - 1] || '');
  var titleRow = currentRow;
  sheet.getRange(titleRow, nameCol).setValue(
    dept + '   (' + startDate + ' – ' + endDate + ')   [Writeback]'
  ).setFontWeight('bold').setFontSize(14)
    .setFontColor(_WB_COLORS_.titleFg);
  sheet.getRange(titleRow, nameCol, 1, totalCols)
    .setBackground(_WB_COLORS_.titleBg);
  bandedRows.push({ row: titleRow, bg: _WB_COLORS_.titleBg });
  currentRow++;

  // ---- Row 2: date axis ----
  var dateRow = currentRow;
  sheet.getRange(dateRow, nameCol).setValue('Date')
    .setFontWeight('bold')
    .setBackground(_WB_COLORS_.headerRowBg);
  if (dayKeys.length > 0) {
    sheet.getRange(dateRow, firstDateCol, 1, dayKeys.length)
      .setValues([dayKeys])
      .setFontWeight('bold')
      .setHorizontalAlignment('center')
      .setBackground(_WB_COLORS_.headerRowBg);
  }
  bandedRows.push({ row: dateRow, bg: _WB_COLORS_.headerRowBg });
  currentRow++;

  // ---- Row 3: weekday axis (Mon/Tue/Wed) — derived from ISO dates ----
  var weekdayRow = currentRow;
  sheet.getRange(weekdayRow, nameCol).setValue('Day')
    .setFontWeight('bold')
    .setBackground(_WB_COLORS_.headerRowBg);
  if (dayKeys.length > 0) {
    var weekdayValues = dayKeys.map(_weekdayLabelForIso_);
    sheet.getRange(weekdayRow, firstDateCol, 1, dayKeys.length)
      .setValues([weekdayValues])
      .setFontWeight('bold')
      .setHorizontalAlignment('center')
      .setBackground(_WB_COLORS_.headerRowBg);
  }
  bandedRows.push({ row: weekdayRow, bg: _WB_COLORS_.headerRowBg });
  currentRow++;

  // Section + doctor rows. Group columnADoctorNames by sectionGroup,
  // preserving sectionGroup discovery order.
  var bySection = _groupColumnAByDoctorSection_(snap.columnADoctorNames || []);
  var sectionOrder = _orderedSectionKeys_(snap.columnADoctorNames || []);
  var doctorRowByKey = {}; // (sectionGroup + ':' + rowIndex) → sheet row number
  var doctorRowBySourceKey = {}; // sourceDoctorKey → sheet row number (for assignments lookup)
  // Map sourceDoctorKey → (sectionGroup, rowIndex) via doctorIdMap.
  var doctorIdToSection = {};
  for (var di = 0; di < doctorIdMap.length; di++) {
    var dim = doctorIdMap[di];
    doctorIdToSection[dim.doctorId] = {
      sectionGroup: dim.sectionGroup,
      rowIndex: dim.rowIndex,
    };
  }

  for (var s = 0; s < sectionOrder.length; s++) {
    var sectionKey = sectionOrder[s];
    var doctors = bySection[sectionKey];
    var sectionLabel = _WB_SECTION_LABELS_[sectionKey] || sectionKey;
    sheet.getRange(currentRow, nameCol).setValue(sectionLabel)
      .setFontWeight('bold');
    sheet.getRange(currentRow, nameCol, 1, totalCols)
      .setBackground(_WB_COLORS_.sectionBg);
    bandedRows.push({ row: currentRow, bg: _WB_COLORS_.sectionBg });
    currentRow++;
    // Sort doctors by rowIndex so the order is deterministic + stable.
    doctors.sort(function (a, b) { return a.rowIndex - b.rowIndex; });
    for (var d = 0; d < doctors.length; d++) {
      var doctor = doctors[d];
      sheet.getRange(currentRow, nameCol).setValue(doctor.value);
      doctorRowByKey[sectionKey + ':' + doctor.rowIndex] = currentRow;
      currentRow++;
    }
    currentRow++; // spacer
  }

  // Build sourceDoctorKey → sheet-row lookup via doctorIdToSection.
  for (var sk in doctorIdToSection) {
    if (Object.prototype.hasOwnProperty.call(doctorIdToSection, sk)) {
      var sec = doctorIdToSection[sk];
      var key = sec.sectionGroup + ':' + sec.rowIndex;
      if (doctorRowByKey[key] !== undefined) {
        doctorRowBySourceKey[sk] = doctorRowByKey[key];
      }
    }
  }

  // Render request cells (read-only roster snapshot — what the operator
  // typed at run-start). Sourced from snap.requestCells. Cells are written
  // into doctor rows × day columns.
  var dayIndexToCol = {};
  for (var dk = 0; dk < dayKeys.length; dk++) {
    dayIndexToCol[dk] = firstDateCol + dk;
  }
  var requestCells = snap.requestCells || [];
  for (var rc = 0; rc < requestCells.length; rc++) {
    var req = requestCells[rc];
    var rRow = doctorRowBySourceKey[req.sourceDoctorKey];
    var rCol = dayIndexToCol[req.dayIndex];
    if (rRow && rCol && req.value) {
      sheet.getRange(rRow, rCol).setValue(req.value)
        .setHorizontalAlignment('center');
    }
  }

  // (surfaceId, rowOffset) → sheet row number. Filled as we render the
  // lower-shell assignment rows below; consumed by the prefilled-cell
  // pass which writes each prefilled value at the row keyed by its
  // (surfaceId, rowOffset) so the value lands in the same slot row as
  // the source tab. Per writeback contract §10.1 "written into their
  // cell positions", the lower-shell assignment-row anchor mapping
  // comes from the snapshot's `outputAssignmentRows` field which
  // mirrors `template.outputSurfaces[].assignmentRows[]` per
  // template_artifact_contract.md §10 — this is the authoritative
  // slotType ↔ rowOffset binding the writeback library cannot derive
  // from winner assignments alone (winner units carry slotType but no
  // rowOffset).
  var assignmentRowToSheetRow = {};

  // Call-point rows (one per callPointRowKey). Group by rowKey.
  var callPointByKey = _groupCallPointsByRowKey_(snap.callPointCells || []);
  var callPointRowKeys = Object.keys(callPointByKey).sort();
  for (var cpi = 0; cpi < callPointRowKeys.length; cpi++) {
    var cpKey = callPointRowKeys[cpi];
    var cpLabel = _WB_POINT_ROW_LABELS_[cpKey] || cpKey;
    sheet.getRange(currentRow, nameCol).setValue(cpLabel)
      .setFontWeight('bold')
      .setBackground(_WB_COLORS_.pointBg);
    var cpCells = callPointByKey[cpKey];
    for (var cpc = 0; cpc < cpCells.length; cpc++) {
      var cpCell = cpCells[cpc];
      var cpCol = dayIndexToCol[cpCell.dayIndex];
      if (cpCol) {
        sheet.getRange(currentRow, cpCol).setValue(cpCell.value)
          .setHorizontalAlignment('center')
          .setBackground(_WB_COLORS_.pointBg);
      }
    }
    bandedRows.push({ row: currentRow, bg: _WB_COLORS_.pointBg });
    currentRow++;
  }
  currentRow++; // spacer

  // Lower assignment shell — one row per (surfaceId, rowOffset) per the
  // template's outputMapping. Render header.
  sheet.getRange(currentRow, nameCol).setValue('Roster / Assignments')
    .setFontWeight('bold').setBackground(_WB_COLORS_.lowerBg);
  sheet.getRange(currentRow, nameCol, 1, totalCols)
    .setBackground(_WB_COLORS_.lowerBg);
  bandedRows.push({ row: currentRow, bg: _WB_COLORS_.lowerBg });
  currentRow++;

  // Group winner assignments by slotType — each slotType gets one row.
  var winnerBySlot = {};
  for (var wi = 0; wi < winnerAssignments.length; wi++) {
    var au = winnerAssignments[wi];
    if (!winnerBySlot[au.slotType]) winnerBySlot[au.slotType] = [];
    winnerBySlot[au.slotType].push(au);
  }

  // Build dateKey → dayIndex map for assignment rendering (winner has
  // dateKey, snapshot has dayIndex; we need to map between them via
  // dayKeys order).
  var dateKeyToDayIndex = {};
  for (var dki = 0; dki < dayKeys.length; dki++) {
    dateKeyToDayIndex[dayKeys[dki]] = dki;
  }

  // Doctor display-name lookup: doctorId → column-A cell value.
  var doctorIdToDisplayName = _buildDoctorIdToDisplayName_(
    snap.columnADoctorNames || [], doctorIdMap);

  // Render lower-shell rows in the template-defined (surfaceId, rowOffset)
  // order. If `outputAssignmentRows` is missing or empty, fall back to
  // sorted slot keys from winner assignments — produces a roster-readable
  // tab even if the writeback contract §9 6th-category field is absent
  // (e.g., older wrapper envelopes). Prefilled cells in fallback mode
  // are best-effort positioned but cannot be guaranteed to align with
  // their source-tab slot row without the template binding.
  var outputAssignmentRows = _resolveOutputAssignmentRows_(
    snap, winnerBySlot);
  for (var st = 0; st < outputAssignmentRows.length; st++) {
    var rowDef = outputAssignmentRows[st];
    var slot = rowDef.slotType;
    assignmentRowToSheetRow[rowDef.surfaceId + ':' + rowDef.rowOffset] = currentRow;
    var slotLabel = _WB_SLOT_LABELS_[slot] || slot;
    sheet.getRange(currentRow, nameCol).setValue(slotLabel)
      .setFontWeight('bold');
    var assignments = winnerBySlot[slot] || [];
    for (var ai = 0; ai < assignments.length; ai++) {
      var a = assignments[ai];
      var aDayIndex = dateKeyToDayIndex[a.dateKey];
      var aCol = dayIndexToCol[aDayIndex];
      var displayName = a.doctorId
        ? (doctorIdToDisplayName[a.doctorId] || a.doctorId)
        : '';
      if (aCol) {
        sheet.getRange(currentRow, aCol).setValue(displayName)
          .setHorizontalAlignment('center');
      }
    }
    currentRow++;
  }

  // Prefilled-assignment cells: place each at the lower-shell row keyed
  // by its (surfaceId, rowOffset) per writeback contract §10.1 ("written
  // into their cell positions"). Italic styling marks the cell as a
  // solver-fixed input rather than a solver-chosen output; if a
  // prefilled and a winner assignment land in the same cell, prefilled
  // is written second so the italic style wins. Values must agree
  // because prefilled is a hard constraint the solver must respect.
  var prefilled = snap.prefilledFixedAssignmentCells || [];
  for (var pi = 0; pi < prefilled.length; pi++) {
    var pf = prefilled[pi];
    var pfRow = assignmentRowToSheetRow[pf.surfaceId + ':' + pf.rowOffset];
    if (pfRow === undefined) {
      // Defensive: a prefilled cell whose (surfaceId, rowOffset) does
      // not match any rendered assignment row implies a snapshot/template
      // mismatch. Skip rather than misplace the value to a wrong cell.
      continue;
    }
    var pfCol = dayIndexToCol[pf.dayIndex];
    if (pfCol) {
      sheet.getRange(pfRow, pfCol).setValue(pf.value)
        .setHorizontalAlignment('center').setFontStyle('italic');
    }
  }

  // ---- Weekend column shading ----
  // Apply weekend (Sat/Sun) salmon-bg shading to entire date columns
  // from the date row down to the last content row. Public-holiday
  // shading is intentionally OUT of scope per the M4 C1 Phase 2 polish
  // pass — the launcher's DatesAndHolidays helper isn't reachable from
  // the central library, and FW-0029 (template-aware label propagation)
  // would naturally pick up the holiday calendar too if needed later.
  // Track the last content row before applying.
  var lastContentRow = currentRow - 1;
  for (var wi = 0; wi < dayKeys.length; wi++) {
    if (!_isWeekendIso_(dayKeys[wi])) continue;
    var weCol = firstDateCol + wi;
    sheet.getRange(dateRow, weCol, lastContentRow - dateRow + 1, 1)
      .setBackground(_WB_COLORS_.weekendBg);
  }

  // ---- Re-apply banded row backgrounds so structural row colors win
  // ---- over the weekend column shading just applied.
  for (var b = 0; b < bandedRows.length; b++) {
    sheet.getRange(bandedRows[b].row, nameCol, 1, totalCols)
      .setBackground(bandedRows[b].bg);
  }

  // ---- Column widths + frozen panes (match M1.1 layout) ----
  sheet.setColumnWidth(nameCol, 200);
  for (var wci = 0; wci < dayKeys.length; wci++) {
    sheet.setColumnWidth(firstDateCol + wci, 100);
  }
  sheet.setFrozenRows(weekdayRow);
  sheet.setFrozenColumns(nameCol);
}

// Helper: derive 3-letter weekday label ('Mon', 'Tue', ...) from an ISO
// date string ('YYYY-MM-DD'). Used for the writeback tab's weekday axis
// row matching M1.1's pattern. Returns the original input on parse
// failure (defensive — should not occur in practice since dayKeys
// originate from `_collectDayKeys_` which produces ISO dates).
function _weekdayLabelForIso_(isoDate) {
  if (typeof isoDate !== 'string' || isoDate.length < 10) return isoDate;
  var d = new Date(isoDate + 'T00:00:00Z');
  if (isNaN(d.getTime())) return isoDate;
  return Utilities.formatDate(d, 'UTC', 'EEE');
}

// Helper: true if the given ISO date falls on a Saturday or Sunday.
// Public holidays are NOT detected — see M4 C1 Phase 2 polish-pass
// scoping note inside `_renderSuccessBranch_`.
function _isWeekendIso_(isoDate) {
  if (typeof isoDate !== 'string' || isoDate.length < 10) return false;
  var d = new Date(isoDate + 'T00:00:00Z');
  if (isNaN(d.getTime())) return false;
  var dow = d.getUTCDay(); // 0 = Sunday, 6 = Saturday
  return dow === 0 || dow === 6;
}

// Resolve the lower-shell assignment-row order. Primary source is the
// snapshot's `outputAssignmentRows` array (writeback contract §9 6th
// category). Fallback for legacy wrapper envelopes that omit the field
// is sorted slot keys from the winner-assignment grouping with
// rowOffset reconstructed positionally — this preserves a readable
// roster but loses prefilled-cell positional fidelity.
function _resolveOutputAssignmentRows_(snap, winnerBySlot) {
  var declared = snap.outputAssignmentRows;
  if (Array.isArray(declared) && declared.length > 0) {
    var copy = declared.slice();
    copy.sort(function (a, b) {
      var as = String(a.surfaceId);
      var bs = String(b.surfaceId);
      if (as < bs) return -1;
      if (as > bs) return 1;
      return (a.rowOffset || 0) - (b.rowOffset || 0);
    });
    return copy;
  }
  var slotTypes = Object.keys(winnerBySlot).sort();
  var fallback = [];
  for (var i = 0; i < slotTypes.length; i++) {
    fallback.push({
      surfaceId: 'lowerRosterAssignments',
      slotType: slotTypes[i],
      rowOffset: i,
    });
  }
  return fallback;
}

// --- failure-branch rendering (§13.1) --------------------------------------

// Per §13.1 + §13.2: failure-branch tab is intentionally minimum content.
// Header + unfilledDemand rows + reasons rows + traceability footer (added
// later in the orchestrator). NO reconstructed shell, NO rich formatting.
function _renderFailureBranch_(sheet, envelope) {
  var fre = envelope.finalResultEnvelope;
  var result = fre.result;
  var unfilledDemand = result.unfilledDemand || [];
  var reasons = result.reasons || [];

  var row = 1;
  sheet.getRange(row, 1).setValue('FAILED')
    .setFontWeight('bold').setFontSize(14).setFontColor('#a40000');
  row += 2;

  sheet.getRange(row, 1).setValue('Unfilled Demand:').setFontWeight('bold');
  row++;
  for (var i = 0; i < unfilledDemand.length; i++) {
    sheet.getRange(row, 1).setValue(JSON.stringify(unfilledDemand[i]));
    row++;
  }
  row++;

  sheet.getRange(row, 1).setValue('Reasons:').setFontWeight('bold');
  row++;
  for (var j = 0; j < reasons.length; j++) {
    sheet.getRange(row, 1).setValue(String(reasons[j]));
    row++;
  }
}

// --- traceability (§16) ----------------------------------------------------

// 4-row visible footer per §16.1.
function _attachTraceabilityFooter_(sheet, envelope, isSuccess) {
  var fre = envelope.finalResultEnvelope;
  var runEnv = fre.runEnvelope;
  var lastRow = sheet.getLastRow();
  var footerStart = lastRow + 2; // one blank row separator
  sheet.getRange(footerStart, 1).setValue(
    'Run ID: ' + runEnv.runId
  ).setFontStyle('italic');
  sheet.getRange(footerStart + 1, 1).setValue(
    'Generated: ' + (runEnv.generationTimestamp || '')
  ).setFontStyle('italic');
  sheet.getRange(footerStart + 2, 1).setValue(
    'Source: ' + runEnv.sourceTabName
  ).setFontStyle('italic');
  sheet.getRange(footerStart + 3, 1).setValue(
    'Status: ' + (isSuccess ? 'SUCCESS' : 'FAILED')
  ).setFontStyle('italic').setFontWeight('bold');
}

// 6-key hidden DeveloperMetadata per §16.2.
function _attachTraceabilityMetadata_(sheet, envelope, isSuccess) {
  var fre = envelope.finalResultEnvelope;
  var runEnv = fre.runEnvelope;
  sheet.addDeveloperMetadata('runId', String(runEnv.runId));
  sheet.addDeveloperMetadata(
    'generationTimestamp', String(runEnv.generationTimestamp || ''));
  sheet.addDeveloperMetadata('sourceTabName', String(runEnv.sourceTabName));
  sheet.addDeveloperMetadata(
    'sourceSpreadsheetId', String(runEnv.sourceSpreadsheetId));
  sheet.addDeveloperMetadata('contractVersion', '1');
  sheet.addDeveloperMetadata('status', isSuccess ? 'SUCCESS' : 'FAILED');
}

// --- protection (§10.3 / §13.4) --------------------------------------------

// Apply whole-tab read-only protection to the writeback tab. The
// effective user (the operator who triggered the writeback Web App) is
// preserved as an editor before removing the others so Apps Script's
// protection API does not throw when edit access is inherited via
// Google Group / domain settings — Apps Script disallows
// `removeEditors` from removing the script-running user, and group-
// based editors raise an exception on removal unless the effective
// user is explicitly added first. Without this guard, writeback would
// fail for valid operator accounts whose access path is group/domain-
// inherited, the new tab would be deleted by the cleanup-on-failure
// path (§14), and the operator would see a runtime error for a
// successfully-written roster.
function _protectWritebackTab_(sheet) {
  var protection = sheet.protect()
    .setDescription('Writeback tab — read-only')
    .setWarningOnly(false);
  try {
    var me = Session.getEffectiveUser();
    protection.addEditor(me);
    var meEmail = me.getEmail();
    var editors = protection.getEditors();
    for (var i = 0; i < editors.length; i++) {
      var ed = editors[i];
      if (ed.getEmail() !== meEmail) {
        protection.removeEditor(ed);
      }
    }
    if (protection.canDomainEdit && protection.canDomainEdit()) {
      try { protection.setDomainEdit(false); } catch (_) { /* non-domain */ }
    }
  } catch (e) {
    // Surface protection-stage failures via the orchestrator's outer
    // try/catch → cleanup-on-failure path (§14). Re-throwing here keeps
    // the SUCCESS / RUNTIME_ERROR diagnostic invariant intact (§17.4):
    // we never claim success on a half-protected tab.
    throw e;
  }
}

// --- diagnostic surface (§17) ----------------------------------------------

function _writebackSuccess_(sheet, isSuccess, ss) {
  return {
    state: isSuccess ? 'SUCCESS' : 'FAILED',
    tabName: sheet.getName(),
    spreadsheetUrl: _anchorSpreadsheetUrlToSheet_(ss, sheet),
  };
}

// Construct a spreadsheet URL anchored to the writeback tab so the
// operator lands directly on the new tab (not the spreadsheet's default
// tab) per writeback contract §17.1 / §17.2 ("anchored to the new tab
// where the platform supports tab anchoring"). Google Sheets uses the
// `#gid=<sheetId>` URL fragment for tab targeting.
function _anchorSpreadsheetUrlToSheet_(ss, sheet) {
  return _composeSpreadsheetUrlWithGid_(ss.getUrl(), sheet.getSheetId());
}

// Pure URL composition: replace any existing `#...` fragment on the
// spreadsheet URL with `#gid=<sheetId>`. Extracted as a helper so the
// fragment-replacement logic is unit-testable without spinning up
// SpreadsheetApp.
function _composeSpreadsheetUrlWithGid_(baseUrl, sheetId) {
  var hashIdx = baseUrl.indexOf('#');
  var trimmedBase = hashIdx >= 0 ? baseUrl.substring(0, hashIdx) : baseUrl;
  return trimmedBase + '#gid=' + sheetId;
}

function _writebackError_(message) {
  return { state: 'RUNTIME_ERROR', error: String(message) };
}

// --- helpers ---------------------------------------------------------------

function _collectDayKeys_(snap) {
  // Day keys come from request cells' dayIndex range (or fall back to
  // call-point cells' dayIndex range if requests are empty). We need
  // ordered ISO date strings to render as date headers; the snapshot
  // subset doesn't carry per-day raw text on its own, so we use the
  // shell parameters' periodStart/periodEnd to derive ordered keys.
  // For first release simplicity: use period bounds + count from
  // request cells / call-point cells / prefilled cells.
  var dayIndexes = {};
  var arrs = [
    snap.requestCells || [],
    snap.callPointCells || [],
    snap.prefilledFixedAssignmentCells || [],
  ];
  for (var ai = 0; ai < arrs.length; ai++) {
    var arr = arrs[ai];
    for (var i = 0; i < arr.length; i++) {
      dayIndexes[arr[i].dayIndex] = true;
    }
  }
  var sorted = Object.keys(dayIndexes)
    .map(function (k) { return parseInt(k, 10); })
    .sort(function (a, b) { return a - b; });
  // Map dayIndex → ISO date by computing from periodStartDate.
  var startStr = (snap.shellParameters || {}).periodStartDate;
  if (!startStr) {
    return sorted.map(function (i) { return 'day_' + i; });
  }
  var start = new Date(startStr + 'T00:00:00Z');
  return sorted.map(function (idx) {
    var d = new Date(start.getTime() + idx * 86400000);
    return Utilities.formatDate(d, 'UTC', 'yyyy-MM-dd');
  });
}

function _groupColumnAByDoctorSection_(columnA) {
  var by = {};
  for (var i = 0; i < columnA.length; i++) {
    var entry = columnA[i];
    if (!by[entry.sectionGroup]) by[entry.sectionGroup] = [];
    by[entry.sectionGroup].push(entry);
  }
  return by;
}

function _orderedSectionKeys_(columnA) {
  var seen = {};
  var order = [];
  for (var i = 0; i < columnA.length; i++) {
    var sk = columnA[i].sectionGroup;
    if (!seen[sk]) {
      seen[sk] = true;
      order.push(sk);
    }
  }
  return order;
}

function _groupCallPointsByRowKey_(callPointCells) {
  var by = {};
  for (var i = 0; i < callPointCells.length; i++) {
    var c = callPointCells[i];
    if (!by[c.callPointRowKey]) by[c.callPointRowKey] = [];
    by[c.callPointRowKey].push(c);
  }
  return by;
}

function _buildDoctorIdToDisplayName_(columnA, doctorIdMap) {
  // Build (sectionGroup + ':' + rowIndex) → value lookup from columnA.
  var byKey = {};
  for (var i = 0; i < columnA.length; i++) {
    var e = columnA[i];
    byKey[e.sectionGroup + ':' + e.rowIndex] = e.value;
  }
  // Walk doctorIdMap to produce doctorId → cell value.
  var out = {};
  for (var j = 0; j < doctorIdMap.length; j++) {
    var dim = doctorIdMap[j];
    out[dim.doctorId] = byKey[dim.sectionGroup + ':' + dim.rowIndex] || '';
  }
  return out;
}
