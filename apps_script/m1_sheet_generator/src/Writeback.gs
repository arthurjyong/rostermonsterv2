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

  var newTabName = _buildWritebackTabName_(ss, sourceTabName);
  var sheet = ss.insertSheet(newTabName);
  // Track newly-created tab for cleanup-on-failure per §14.1.

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

// Render the success-branch writeback tab per §10.1. The tab carries:
// - reconstructed M1-style shell from snapshot bundle's shellParameters +
//   columnADoctorNames (operator-readable as a roster shell on its own),
// - requestCells / callPointCells / prefilledFixedAssignmentCells from
//   the snapshot bundle written into their cell positions,
// - winner allocation: every AssignmentUnit from
//   finalResultEnvelope.result.winnerAssignment rendered with the
//   column-A cell value of the resolved doctor (§12).
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

  // Title row
  var params = snap.shellParameters || {};
  var dept = params.department || '';
  var startDate = params.periodStartDate || (dayKeys[0] || '');
  var endDate = params.periodEndDate || (dayKeys[dayKeys.length - 1] || '');
  sheet.getRange(currentRow, nameCol).setValue(
    dept + '   (' + startDate + ' – ' + endDate + ')   [Writeback]'
  ).setFontWeight('bold').setFontSize(14);
  currentRow++;

  // Date row
  sheet.getRange(currentRow, nameCol).setValue('Date').setFontWeight('bold');
  if (dayKeys.length > 0) {
    sheet.getRange(currentRow, firstDateCol, 1, dayKeys.length)
      .setValues([dayKeys])
      .setFontWeight('bold')
      .setHorizontalAlignment('center');
  }
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
    sheet.getRange(currentRow, nameCol).setValue('Section: ' + sectionKey)
      .setFontWeight('bold').setBackground('#d9d9d9');
    sheet.getRange(currentRow, nameCol, 1, totalCols).setBackground('#d9d9d9');
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

  // surfaceId → sheet row number for the surface's anchor row. Filled as
  // we render call-point rows and lower-shell slot rows below; consumed
  // by the prefilled-cell pass which writes each prefilled value at
  // (surfaceIdToRow[surfaceId] + rowOffset, dayIndex column) so the
  // value lands in the same cell coordinates the source tab carried.
  var surfaceIdToRow = {};

  // Call-point rows (one per callPointRowKey). Group by rowKey.
  var callPointByKey = _groupCallPointsByRowKey_(snap.callPointCells || []);
  var callPointRowKeys = Object.keys(callPointByKey).sort();
  for (var cpi = 0; cpi < callPointRowKeys.length; cpi++) {
    var cpKey = callPointRowKeys[cpi];
    surfaceIdToRow[cpKey] = currentRow;
    sheet.getRange(currentRow, nameCol).setValue(cpKey)
      .setFontWeight('bold').setBackground('#fff2cc');
    var cpCells = callPointByKey[cpKey];
    for (var cpc = 0; cpc < cpCells.length; cpc++) {
      var cpCell = cpCells[cpc];
      var cpCol = dayIndexToCol[cpCell.dayIndex];
      if (cpCol) {
        sheet.getRange(currentRow, cpCol).setValue(cpCell.value)
          .setHorizontalAlignment('center');
      }
    }
    currentRow++;
  }
  currentRow++; // spacer

  // Lower assignment shell — one row per slotType, surfacing the winner
  // assignments. Render header.
  sheet.getRange(currentRow, nameCol).setValue('Roster / Assignments')
    .setFontWeight('bold').setBackground('#c6e0b4');
  sheet.getRange(currentRow, nameCol, 1, totalCols).setBackground('#c6e0b4');
  currentRow++;

  // Group winner assignments by slotType — each slotType gets one row.
  var winnerBySlot = {};
  for (var wi = 0; wi < winnerAssignments.length; wi++) {
    var au = winnerAssignments[wi];
    if (!winnerBySlot[au.slotType]) winnerBySlot[au.slotType] = [];
    winnerBySlot[au.slotType].push(au);
  }
  // Union slot types from winner assignments AND prefilled cells so a
  // prefilled-only surface (no winner row in this run) still gets its
  // anchor row rendered, preventing prefilled cells from being silently
  // dropped when no winner assignment shares the same slot type.
  var slotTypeSet = {};
  for (var wsk in winnerBySlot) {
    if (Object.prototype.hasOwnProperty.call(winnerBySlot, wsk)) {
      slotTypeSet[wsk] = true;
    }
  }
  var prefilled = snap.prefilledFixedAssignmentCells || [];
  for (var pix = 0; pix < prefilled.length; pix++) {
    var pfx = prefilled[pix];
    if (!surfaceIdToRow[pfx.surfaceId]) {
      // Reserve only slot-type-shaped surfaces here; call-point surfaces
      // were already anchored above. Treat any unknown surfaceId as a
      // slot-type-shaped row to render in the lower shell.
      slotTypeSet[pfx.surfaceId] = true;
    }
  }
  var slotTypes = Object.keys(slotTypeSet).sort();

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

  for (var st = 0; st < slotTypes.length; st++) {
    var slot = slotTypes[st];
    surfaceIdToRow[slot] = currentRow;
    sheet.getRange(currentRow, nameCol).setValue(slot).setFontWeight('bold');
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

  // Prefilled-assignment cells: write back into their original
  // (surfaceId, rowOffset) source-tab coordinates per writeback contract
  // §10.1 ("written into their cell positions"). Italic styling marks
  // these cells as solver-fixed inputs rather than solver-chosen
  // outputs. If a prefilled and a winner assignment land in the same
  // (slot, day) cell, prefilled is written second so the italic style
  // wins; the values must agree because prefilled is a solver
  // constraint that the winner must respect.
  for (var pi = 0; pi < prefilled.length; pi++) {
    var pf = prefilled[pi];
    var pfBaseRow = surfaceIdToRow[pf.surfaceId];
    if (pfBaseRow === undefined) {
      // Defensive: an unknown surfaceId would mean the prefilled cell
      // came from a surface we did not render. Skip rather than misplace
      // the value to a wrong cell. This should not occur in practice
      // because the loop above eagerly anchors a slot row for every
      // unknown surfaceId; the guard remains as a backstop.
      continue;
    }
    var pfRow = pfBaseRow + (pf.rowOffset || 0);
    var pfCol = dayIndexToCol[pf.dayIndex];
    if (pfCol) {
      sheet.getRange(pfRow, pfCol).setValue(pf.value)
        .setHorizontalAlignment('center').setFontStyle('italic');
    }
  }
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

function _protectWritebackTab_(sheet) {
  var protection = sheet.protect()
    .setDescription('Writeback tab — read-only')
    .setWarningOnly(false);
  protection.removeEditors(protection.getEditors());
  if (protection.canDomainEdit && protection.canDomainEdit()) {
    try { protection.setDomainEdit(false); } catch (_) { /* non-domain */ }
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
