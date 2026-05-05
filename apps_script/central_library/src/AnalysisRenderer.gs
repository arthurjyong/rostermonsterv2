// AnalysisRenderer.gs
// Pure adapter from `AnalyzerOutput` (per `docs/analysis_contract.md` §10)
// to K roster tabs + 1 comparison tab in the source spreadsheet, per
// `docs/analysis_renderer_contract.md`.
//
// Public entry: `renderAnalysis(outputJsonString)` — invoked by the
// launcher's analysis-render route per `docs/decision_log.md` D-0063.
//
// Implements:
// - §9.1 fail-loud admission (contractVersion, sourceSpreadsheetId,
//   non-empty topK, openById permission)
// - §10.1 K roster tabs + 1 comparison tab
// - §10.2 spreadsheetUrl presence rules
// - §11 source-spreadsheet target + co-existence with writeback's tab
// - §12 always-new-tab collision policy with `(2)` suffix
// - §13.1 roster tab content (header + per-day grid + per-doctor block
//   + per-component block + footer)
// - §13.2 comparison tab content (score-decomp matrix + equity scalars
//   + day-level + Hamming + footer)
// - §14 best-effort sequential SpreadsheetApp.flush per tab
// - §15 idempotent additive (re-render = `(2)` suffix, never overwrite)
// - §16 structured AnalysisRendererResult.error codes
// - §17 byte-identical determinism on identical input + state

// Public API surface — `RMLib.renderAnalysis(output)` per
// `docs/analysis_renderer_contract.md` §6 + §9. The contract boundary
// is an in-memory `AnalyzerOutput` object (§9 input #1); the launcher's
// delegate shim per `docs/analysis_renderer_contract.md` §11.3 is
// expected to `JSON.parse(...)` the operator-uploaded string before
// calling this function.
//
// Defensive resilience: callers that pass a JSON string instead of an
// object are accepted — the library parses internally and surfaces the
// same `AnalysisRendererResult` shape per §10. This keeps the contract
// intent (object boundary) authoritative while not breaking call sites
// that haven't yet been updated.
function renderAnalysis(output) {
  if (typeof output === 'string') {
    try {
      output = JSON.parse(output);
    } catch (e) {
      return _ar_failed_(
        'INVALID_INPUT_VERSION',
        'Could not parse uploaded JSON as AnalyzerOutput: ' +
        (e && e.message ? e.message : String(e))
      );
    }
  }
  return _renderAnalysisInner_(output);
}

// Internal orchestrator. Wrapped in try/catch by the public entry so any
// failure surfaces through the structured AnalysisRendererResult per §16.
function _renderAnalysisInner_(output) {
  // §9.1 admission — version, sourceSpreadsheetId, topK presence
  if (!output || typeof output !== 'object') {
    return _ar_failed_('INVALID_INPUT_VERSION',
      'AnalyzerOutput is not a JSON object.');
  }
  if (output.contractVersion !== 1) {
    return _ar_failed_('INVALID_INPUT_VERSION',
      'AnalyzerOutput.contractVersion must be 1; got ' +
      JSON.stringify(output.contractVersion) + '.');
  }
  if (!output.source || !output.source.sourceSpreadsheetId) {
    return _ar_failed_('MISSING_SOURCE_SPREADSHEET_ID',
      'AnalyzerOutput.source.sourceSpreadsheetId is required.');
  }
  if (!output.topK || !Array.isArray(output.topK.candidates) ||
      output.topK.candidates.length === 0) {
    return _ar_failed_('EMPTY_TOPK',
      'AnalyzerOutput.topK.candidates is empty or missing.');
  }

  // §11 open the source spreadsheet
  var ss;
  try {
    ss = SpreadsheetApp.openById(output.source.sourceSpreadsheetId);
  } catch (e) {
    return _ar_failed_('OPEN_BY_ID_FAILED',
      'Could not open source spreadsheet (sourceSpreadsheetId=' +
      output.source.sourceSpreadsheetId + '): ' +
      (e && e.message ? e.message : String(e)) +
      '. Verify the operator has Editor access to the spreadsheet.');
  }
  var spreadsheetUrl = ss.getUrl();

  // §10 + §13 render
  var newTabIds = [];
  var newTabNames = [];
  var runShort = String(output.source.runId || '').substring(0, 6) || 'unknown';
  var k = output.topK.candidates.length;
  var rankPadWidth = (k >= 10) ? 2 : 1;

  try {
    // K roster tabs (rank 1 → rank K), then comparison tab last per §14
    for (var i = 0; i < k; i++) {
      var cand = output.topK.candidates[i];
      var rankStr = _ar_padRank_(cand.rankByTotalScore, rankPadWidth);
      var baseName = 'Analysis ' + runShort + ' ' + rankStr;
      var tabName = _ar_uniqueTabName_(ss, baseName);
      var sheet = ss.insertSheet(tabName);
      _ar_renderRosterTab_(sheet, output, cand, k);
      _ar_attachRendererFooter_(sheet, output, 'roster', cand.rankByTotalScore);
      _ar_attachRendererMetadata_(sheet, output, 'roster', cand.candidateId);
      _ar_protectRendererTab_(sheet);
      SpreadsheetApp.flush();
      newTabIds.push(String(sheet.getSheetId()));
      newTabNames.push(tabName);
    }

    var compBaseName = 'Analysis ' + runShort + ' Comparison';
    var compName = _ar_uniqueTabName_(ss, compBaseName);
    var compSheet = ss.insertSheet(compName);
    _ar_renderComparisonTab_(compSheet, output);
    _ar_attachRendererFooter_(compSheet, output, 'comparison', null);
    _ar_attachRendererMetadata_(compSheet, output, 'comparison', null);
    _ar_protectRendererTab_(compSheet);
    SpreadsheetApp.flush();
    newTabIds.push(String(compSheet.getSheetId()));
    newTabNames.push(compName);

    return {
      state: 'OK',
      newTabIds: newTabIds,
      newTabNames: newTabNames,
      spreadsheetUrl: spreadsheetUrl,
    };
  } catch (e) {
    var which = newTabNames.length;
    var msg = (e && e.message) ? e.message : String(e);
    // §14: do NOT delete already-written tabs — operator inspects partial
    // state via newTabIds + newTabNames + spreadsheetUrl.
    return {
      state: 'FAILED',
      newTabIds: newTabIds,
      newTabNames: newTabNames,
      spreadsheetUrl: spreadsheetUrl,
      error: {
        code: 'RENDER_EXCEPTION',
        message: 'Render failed at tab #' + (which + 1) + ': ' + msg,
      },
    };
  }
}

// --- admission failure shape (§10 + §16) -----------------------------------

// Failure result with no spreadsheetUrl (admission failed before openById,
// or openById itself failed). Per §10.2 presence rules, spreadsheetUrl is
// omitted on these paths rather than fabricated.
function _ar_failed_(code, message) {
  return {
    state: 'FAILED',
    newTabIds: [],
    newTabNames: [],
    error: { code: code, message: message },
  };
}

// --- tab name (§12) --------------------------------------------------------

function _ar_padRank_(rank, width) {
  var s = String(rank);
  while (s.length < width) s = '0' + s;
  return s;
}

// Always-new-tab per §12.2 — append `(2)`, `(3)`, ... suffix until unique.
function _ar_uniqueTabName_(ss, baseName) {
  var existingNames = {};
  var existing = ss.getSheets();
  for (var i = 0; i < existing.length; i++) {
    existingNames[existing[i].getName()] = true;
  }
  if (!existingNames[baseName]) return baseName;
  for (var k = 2; k <= 1000; k++) {
    var candidate = baseName + ' (' + k + ')';
    if (!existingNames[candidate]) return candidate;
  }
  throw new Error('Tab-name collision exhausted for "' + baseName +
    '" at k=1000; spreadsheet has too many same-name tabs.');
}

// --- visual palette --------------------------------------------------------

// Reuse the writeback color palette per `docs/analysis_renderer_contract.md`
// §13.1 ("shared formatting utilities") so analyzer roster tabs visually
// match writeback's roster tab.
var _AR_COLORS_ = Object.freeze({
  titleBg:        '#1f4e78',
  titleFg:        '#ffffff',
  sectionBg:      '#d9d9d9',
  recommendedBg:  '#c6e0b4',  // green tint for the rank-1 / recommended badge
  headerRowBg:    '#e7e6e6',
  bestCellBg:     '#c6e0b4',  // column-best in comparison tab (Tier 7-derived)
  worstCellBg:    '#fce5cd',  // column-worst in comparison tab
  footerBg:       '#f3f3f3',
});

// --- §13.1 roster tab rendering --------------------------------------------

// Render one candidate's roster tab. Per §13.1: header, per-day grid,
// per-doctor summary, per-component score block, footer.
function _ar_renderRosterTab_(sheet, output, cand, k) {
  var row = 1;
  row = _ar_writeRosterHeader_(sheet, output, cand, k, row);
  row += 1;  // blank spacer row
  row = _ar_writeAssignmentGrid_(sheet, output, cand, row);
  row += 1;
  row = _ar_writePerDoctorSummary_(sheet, output, cand, row);
  row += 1;
  row = _ar_writePerComponentScores_(sheet, output, cand, row);
  // Footer is added separately per §13.1 item 5 via _ar_attachRendererFooter_.
  sheet.setFrozenRows(1);
}

// §13.1 header — `Analysis Tab — Rank N of K`, totalScore, recommended
// badge (visually distinct if recommended), one-line "best on" tags.
function _ar_writeRosterHeader_(sheet, output, cand, k, startRow) {
  var titleText = 'Analysis Tab — Rank ' + cand.rankByTotalScore + ' of ' + k +
    '   (totalScore=' + _ar_fmtNumber_(cand.totalScore) + ')' +
    (cand.recommended ? '   ★ Recommended (selector winner)' : '');
  var titleRange = sheet.getRange(startRow, 1, 1, 6);
  titleRange.merge()
    .setValue(titleText)
    .setFontWeight('bold')
    .setFontSize(13)
    .setFontColor(_AR_COLORS_.titleFg)
    .setBackground(cand.recommended ? _AR_COLORS_.recommendedBg : _AR_COLORS_.titleBg);
  if (cand.recommended) {
    titleRange.setFontColor('#202124');
  }
  startRow++;

  // "Best on X" derived tags — Tier 7 renderer-derivation per §10.9 of
  // analysis_contract: components where rankAcrossTopK == 1.
  var bestOnTags = _ar_collectBestOnTags_(cand);
  if (bestOnTags.length > 0) {
    var subTitleRange = sheet.getRange(startRow, 1, 1, 6);
    subTitleRange.merge()
      .setValue('Best on: ' + bestOnTags.join(', '))
      .setFontStyle('italic')
      .setBackground(_AR_COLORS_.headerRowBg);
    startRow++;
  }
  return startRow;
}

function _ar_collectBestOnTags_(cand) {
  var tags = [];
  if (!cand.scoreComponents) return tags;
  var keys = Object.keys(cand.scoreComponents).sort();
  for (var i = 0; i < keys.length; i++) {
    var name = keys[i];
    var entry = cand.scoreComponents[name];
    if (entry && entry.rankAcrossTopK === 1) tags.push(name);
  }
  return tags;
}

// §13.1 item 2 — per-day assignment grid: rows = days, columns = slots,
// cells = doctor display names. Multi-unit slots collapse via comma-join
// per writeback's existing convention.
function _ar_writeAssignmentGrid_(sheet, output, cand, startRow) {
  // Collect unique slotTypes + dateKeys from this candidate's
  // assignment ride-through.
  var doctorIdMap = output.doctorIdMap || {};
  var assignments = cand.assignment || [];
  var slotTypeSet = {};
  var dateKeySet = {};
  for (var i = 0; i < assignments.length; i++) {
    slotTypeSet[assignments[i].slotType] = true;
    dateKeySet[assignments[i].dateKey] = true;
  }
  var slotTypes = Object.keys(slotTypeSet).sort();
  var dateKeys = Object.keys(dateKeySet).sort();
  if (slotTypes.length === 0 || dateKeys.length === 0) {
    return startRow;
  }

  // Header row — slot types
  sheet.getRange(startRow, 1).setValue('Date')
    .setFontWeight('bold').setBackground(_AR_COLORS_.headerRowBg);
  for (var s = 0; s < slotTypes.length; s++) {
    sheet.getRange(startRow, 2 + s)
      .setValue(slotTypes[s])
      .setFontWeight('bold')
      .setBackground(_AR_COLORS_.headerRowBg);
  }
  startRow++;

  // Index assignments by (dateKey, slotType) for O(1) lookup
  var byCell = {};
  for (var ai = 0; ai < assignments.length; ai++) {
    var a = assignments[ai];
    var key = a.dateKey + '|' + a.slotType;
    if (!byCell[key]) byCell[key] = [];
    byCell[key].push(a.doctorId);
  }

  for (var d = 0; d < dateKeys.length; d++) {
    var dk = dateKeys[d];
    var rowNum = startRow + d;
    sheet.getRange(rowNum, 1).setValue(dk).setFontWeight('bold');
    for (var s2 = 0; s2 < slotTypes.length; s2++) {
      var k = dk + '|' + slotTypes[s2];
      var doctorIds = byCell[k] || [];
      var names = [];
      for (var di = 0; di < doctorIds.length; di++) {
        var id = doctorIds[di];
        if (id == null) {
          names.push('(unfilled)');
        } else {
          names.push(doctorIdMap[id] || id);
        }
      }
      sheet.getRange(rowNum, 2 + s2).setValue(names.join(', '));
    }
  }
  return startRow + dateKeys.length;
}

// §13.1 item 3 — per-doctor summary block: doctor → callCount, standby,
// weekendCall, cumulativeCallPoints, maxConsecutiveDaysOff.
function _ar_writePerDoctorSummary_(sheet, output, cand, startRow) {
  var doctorIdMap = output.doctorIdMap || {};
  var perDoctor = cand.perDoctor || {};
  var doctorIds = Object.keys(perDoctor).sort();
  if (doctorIds.length === 0) return startRow;

  var titleRange = sheet.getRange(startRow, 1, 1, 6);
  titleRange.merge()
    .setValue('Per-doctor summary (Tier 2)')
    .setFontWeight('bold')
    .setBackground(_AR_COLORS_.sectionBg);
  startRow++;

  var headers = ['Doctor', 'CALL', 'STANDBY', 'Weekend CALL',
                 'Cumulative call points', 'Max consecutive days off'];
  sheet.getRange(startRow, 1, 1, headers.length).setValues([headers])
    .setFontWeight('bold').setBackground(_AR_COLORS_.headerRowBg);
  startRow++;

  for (var i = 0; i < doctorIds.length; i++) {
    var id = doctorIds[i];
    var d = perDoctor[id];
    var displayName = doctorIdMap[id] || id;
    sheet.getRange(startRow + i, 1, 1, headers.length).setValues([[
      displayName,
      d.callCount,
      d.standbyCount,
      d.weekendCallCount,
      _ar_fmtNumber_(d.cumulativeCallPoints),
      d.maxConsecutiveDaysOff,
    ]]);
  }
  return startRow + doctorIds.length;
}

// §13.1 item 4 — per-component score block: component → weighted, raw,
// rankAcrossTopK, gapToNextRanked.
function _ar_writePerComponentScores_(sheet, output, cand, startRow) {
  var components = cand.scoreComponents || {};
  var compNames = Object.keys(components).sort();
  if (compNames.length === 0) return startRow;

  var titleRange = sheet.getRange(startRow, 1, 1, 5);
  titleRange.merge()
    .setValue('Per-component score breakdown (Tier 1)')
    .setFontWeight('bold')
    .setBackground(_AR_COLORS_.sectionBg);
  startRow++;

  var headers = ['Component', 'Weighted', 'Raw',
                 'Rank within K', 'Gap to next ranked'];
  sheet.getRange(startRow, 1, 1, headers.length).setValues([headers])
    .setFontWeight('bold').setBackground(_AR_COLORS_.headerRowBg);
  startRow++;

  for (var i = 0; i < compNames.length; i++) {
    var name = compNames[i];
    var c = components[name];
    sheet.getRange(startRow + i, 1, 1, headers.length).setValues([[
      name,
      _ar_fmtNumber_(c.weighted),
      _ar_fmtNumber_(c.raw),
      c.rankAcrossTopK,
      (c.gapToNextRanked == null) ? '(none)' : _ar_fmtNumber_(c.gapToNextRanked),
    ]]);
  }
  return startRow + compNames.length;
}

// --- §13.2 comparison tab rendering ----------------------------------------

function _ar_renderComparisonTab_(sheet, output) {
  var row = 1;
  row = _ar_writeComparisonHeader_(sheet, output, row);
  row += 1;
  row = _ar_writeScoreDecompMatrix_(sheet, output, row);
  row += 1;
  row = _ar_writeEquityScalars_(sheet, output, row);
  row += 1;
  row = _ar_writeHotAndLockedDays_(sheet, output, row);
  row += 1;
  row = _ar_writeHammingMatrix_(sheet, output, row);
  sheet.setFrozenRows(1);
}

function _ar_writeComparisonHeader_(sheet, output, startRow) {
  var k = output.topK.candidates.length;
  var titleText = 'Analysis Tab — Comparison   (K=' + k +
    ', requested=' + output.topK.requested + ', returned=' +
    output.topK.returned + ')';
  sheet.getRange(startRow, 1, 1, 8).merge()
    .setValue(titleText)
    .setFontWeight('bold')
    .setFontSize(13)
    .setFontColor(_AR_COLORS_.titleFg)
    .setBackground(_AR_COLORS_.titleBg);
  return startRow + 1;
}

// §13.2 item 2 — score-decomposition matrix.
function _ar_writeScoreDecompMatrix_(sheet, output, startRow) {
  var candidates = output.topK.candidates;
  if (candidates.length === 0) return startRow;

  // Collect component names (union across all candidates' scoreComponents).
  var compNameSet = {};
  for (var i = 0; i < candidates.length; i++) {
    var sc = candidates[i].scoreComponents || {};
    for (var k in sc) compNameSet[k] = true;
  }
  var compNames = Object.keys(compNameSet).sort();

  sheet.getRange(startRow, 1, 1, compNames.length + 2).merge()
    .setValue('Score decomposition matrix (Tier 1; weighted values; bold = column-best, italic = column-worst)')
    .setFontWeight('bold')
    .setBackground(_AR_COLORS_.sectionBg);
  startRow++;

  // Header: Candidate | totalScore | <component_1> | ... | <component_n>
  var header = ['Candidate', 'totalScore'].concat(compNames);
  sheet.getRange(startRow, 1, 1, header.length).setValues([header])
    .setFontWeight('bold').setBackground(_AR_COLORS_.headerRowBg);
  startRow++;

  // Identify column-best / column-worst per component for cell shading.
  var columnBest = {};
  var columnWorst = {};
  for (var c = 0; c < compNames.length; c++) {
    var name = compNames[c];
    var maxR = -1;
    var maxIdx = -1;
    var minR = -1;
    var minIdx = -1;
    for (var ci = 0; ci < candidates.length; ci++) {
      var sc2 = candidates[ci].scoreComponents || {};
      var entry = sc2[name];
      var r = entry ? entry.rankAcrossTopK : null;
      if (r == null) continue;
      if (maxR === -1 || r > maxR) { maxR = r; maxIdx = ci; }
      if (minR === -1 || r < minR) { minR = r; minIdx = ci; }
    }
    columnBest[name] = minIdx;   // rank 1 = best
    columnWorst[name] = maxIdx;  // highest rank = worst
  }

  for (var i = 0; i < candidates.length; i++) {
    var cand = candidates[i];
    var rowVals = [
      'Candidate ' + cand.candidateId +
        (cand.recommended ? ' ★' : '') +
        ' (rank ' + cand.rankByTotalScore + ')',
      _ar_fmtNumber_(cand.totalScore),
    ];
    for (var c2 = 0; c2 < compNames.length; c2++) {
      var entry2 = (cand.scoreComponents || {})[compNames[c2]];
      rowVals.push(entry2 ? _ar_fmtNumber_(entry2.weighted) : '');
    }
    sheet.getRange(startRow + i, 1, 1, rowVals.length).setValues([rowVals]);
    // Apply column-best / column-worst cell highlights for component columns.
    for (var c3 = 0; c3 < compNames.length; c3++) {
      var col = 3 + c3;
      var range = sheet.getRange(startRow + i, col);
      if (columnBest[compNames[c3]] === i) {
        range.setFontWeight('bold').setBackground(_AR_COLORS_.bestCellBg);
      } else if (columnWorst[compNames[c3]] === i &&
                 columnBest[compNames[c3]] !== columnWorst[compNames[c3]]) {
        range.setFontStyle('italic').setBackground(_AR_COLORS_.worstCellBg);
      }
    }
  }
  return startRow + candidates.length;
}

// §13.2 item 3 — equity scalars block.
function _ar_writeEquityScalars_(sheet, output, startRow) {
  var perCandEquity = (output.comparison || {}).perCandidateEquity || {};
  var candidates = output.topK.candidates;
  if (candidates.length === 0) return startRow;

  sheet.getRange(startRow, 1, 1, 11).merge()
    .setValue('Equity scalars (Tier 3; lower stdev / minMaxGap / Gini = more equitable)')
    .setFontWeight('bold')
    .setBackground(_AR_COLORS_.sectionBg);
  startRow++;

  var headers = [
    'Candidate',
    'callCount stdev', 'callCount minMaxGap', 'callCount Gini',
    'weekendCallCount stdev', 'weekendCallCount minMaxGap', 'weekendCallCount Gini',
    'cumulativeCallPoints stdev', 'cumulativeCallPoints minMaxGap', 'cumulativeCallPoints Gini',
  ];
  sheet.getRange(startRow, 1, 1, headers.length).setValues([headers])
    .setFontWeight('bold').setBackground(_AR_COLORS_.headerRowBg);
  startRow++;

  for (var i = 0; i < candidates.length; i++) {
    var cand = candidates[i];
    var eq = perCandEquity[cand.candidateId] || perCandEquity[String(cand.candidateId)] || {};
    var cc = eq.callCount || {};
    var wc = eq.weekendCallCount || {};
    var cp = eq.cumulativeCallPoints || {};
    var rowVals = [
      'Candidate ' + cand.candidateId + (cand.recommended ? ' ★' : ''),
      _ar_fmtNumber_(cc.stdev), _ar_fmtNumber_(cc.minMaxGap), _ar_fmtNumber_(cc.gini),
      _ar_fmtNumber_(wc.stdev), _ar_fmtNumber_(wc.minMaxGap), _ar_fmtNumber_(wc.gini),
      _ar_fmtNumber_(cp.stdev), _ar_fmtNumber_(cp.minMaxGap), _ar_fmtNumber_(cp.gini),
    ];
    sheet.getRange(startRow + i, 1, 1, rowVals.length).setValues([rowVals]);
  }
  return startRow + candidates.length;
}

// §13.2 item 4 — hot days + locked days.
function _ar_writeHotAndLockedDays_(sheet, output, startRow) {
  var comp = output.comparison || {};
  var hot = comp.hotDays || [];
  var locked = comp.lockedDays || [];

  sheet.getRange(startRow, 1, 1, 4).merge()
    .setValue('Day-level disagreement (Tier 4)')
    .setFontWeight('bold')
    .setBackground(_AR_COLORS_.sectionBg);
  startRow++;

  sheet.getRange(startRow, 1).setValue('Hot days (' + hot.length + '):')
    .setFontWeight('bold');
  sheet.getRange(startRow, 2).setValue('Date');
  sheet.getRange(startRow, 3).setValue('Distinct assignments').setFontWeight('bold');
  sheet.getRange(startRow, 1, 1, 3).setBackground(_AR_COLORS_.headerRowBg);
  startRow++;
  for (var i = 0; i < hot.length; i++) {
    sheet.getRange(startRow + i, 2).setValue(hot[i].dateKey);
    sheet.getRange(startRow + i, 3).setValue(hot[i].distinctAssignments);
  }
  startRow += hot.length;

  sheet.getRange(startRow, 1).setValue('Locked days (' + locked.length + '):')
    .setFontWeight('bold').setBackground(_AR_COLORS_.headerRowBg);
  sheet.getRange(startRow, 2).setBackground(_AR_COLORS_.headerRowBg);
  startRow++;
  if (locked.length === 0) {
    sheet.getRange(startRow, 2).setValue('(none — all dates have disagreement across the K candidates)')
      .setFontStyle('italic');
    startRow++;
  } else {
    for (var j = 0; j < locked.length; j++) {
      sheet.getRange(startRow + j, 2).setValue(locked[j].dateKey);
    }
    startRow += locked.length;
  }
  return startRow;
}

// §13.2 item 5 — pairwise Hamming matrix.
function _ar_writeHammingMatrix_(sheet, output, startRow) {
  var pairwise = (output.comparison || {}).pairwiseHammingDistance || {};
  var candidates = output.topK.candidates;
  if (candidates.length === 0) return startRow;

  sheet.getRange(startRow, 1, 1, candidates.length + 1).merge()
    .setValue('Pairwise Hamming distance (Tier 5; lower = more similar; diagonal is 0)')
    .setFontWeight('bold')
    .setBackground(_AR_COLORS_.sectionBg);
  startRow++;

  // Header: blank | Candidate id columns
  sheet.getRange(startRow, 1).setValue('').setBackground(_AR_COLORS_.headerRowBg);
  for (var c = 0; c < candidates.length; c++) {
    sheet.getRange(startRow, 2 + c)
      .setValue('Cand ' + candidates[c].candidateId)
      .setFontWeight('bold').setBackground(_AR_COLORS_.headerRowBg);
  }
  startRow++;

  for (var r = 0; r < candidates.length; r++) {
    var rowCand = candidates[r];
    sheet.getRange(startRow + r, 1)
      .setValue('Cand ' + rowCand.candidateId)
      .setFontWeight('bold').setBackground(_AR_COLORS_.headerRowBg);
    var rowMap = pairwise[rowCand.candidateId] ||
                 pairwise[String(rowCand.candidateId)] || {};
    for (var c2 = 0; c2 < candidates.length; c2++) {
      var colCand = candidates[c2];
      var v;
      if (r === c2) {
        v = 0;
      } else {
        v = rowMap[colCand.candidateId];
        if (v == null) v = rowMap[String(colCand.candidateId)];
        // Symmetric fallback: try `[colCand][rowCand]` if upper-triangle only
        if (v == null) {
          var colMap = pairwise[colCand.candidateId] ||
                       pairwise[String(colCand.candidateId)] || {};
          v = colMap[rowCand.candidateId];
          if (v == null) v = colMap[String(rowCand.candidateId)];
        }
        if (v == null) v = '';
      }
      sheet.getRange(startRow + r, 2 + c2).setValue(v);
    }
  }
  return startRow + candidates.length;
}

// --- traceability footer + DeveloperMetadata (§13.1 item 5 / §13.2 item 7) -

function _ar_attachRendererFooter_(sheet, output, kind, rank) {
  var lastRow = sheet.getLastRow();
  var footerRow = lastRow + 2;  // one blank spacer
  var fields = [
    ['Kind', kind + (rank != null ? (' (rank ' + rank + ')') : '')],
    ['runId', String(output.source.runId || '')],
    ['seed', String(output.source.seed != null ? output.source.seed : '')],
    ['generatedAt', String(output.generatedAt || '')],
    ['sourceSpreadsheetId', String(output.source.sourceSpreadsheetId || '')],
    ['sourceTabName', String(output.source.sourceTabName || '')],
    ['analysis_contract.contractVersion', String(output.contractVersion)],
    ['analysis_renderer_contract.contractVersion', '1'],
  ];
  for (var i = 0; i < fields.length; i++) {
    sheet.getRange(footerRow + i, 1).setValue(fields[i][0])
      .setFontWeight('bold').setBackground(_AR_COLORS_.footerBg);
    sheet.getRange(footerRow + i, 2).setValue(fields[i][1])
      .setBackground(_AR_COLORS_.footerBg);
  }
}

function _ar_attachRendererMetadata_(sheet, output, kind, candidateId) {
  sheet.addDeveloperMetadata('runId', String(output.source.runId || ''));
  sheet.addDeveloperMetadata(
    'generatedAt', String(output.generatedAt || ''));
  sheet.addDeveloperMetadata('kind', kind);
  if (candidateId != null) {
    sheet.addDeveloperMetadata('candidateId', String(candidateId));
  }
  sheet.addDeveloperMetadata(
    'sourceSpreadsheetId', String(output.source.sourceSpreadsheetId || ''));
  sheet.addDeveloperMetadata(
    'analysis_contract.contractVersion', String(output.contractVersion));
  sheet.addDeveloperMetadata(
    'analysis_renderer_contract.contractVersion', '1');
}

// --- protection (mirrors writeback's _protectWritebackTab_) ----------------

function _ar_protectRendererTab_(sheet) {
  var protection = sheet.protect()
    .setDescription('Analysis renderer tab — read-only')
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
    throw e;
  }
}

// --- formatting helpers ----------------------------------------------------

// Format a numeric value with 4 decimal places of precision, returning ''
// for null/undefined/NaN. Determinism per §17 — fixed digit count, no
// locale-dependent formatting.
function _ar_fmtNumber_(value) {
  if (value == null) return '';
  var n = Number(value);
  if (!isFinite(n)) return String(value);
  // Render integers as integers; floats with 4 decimals.
  if (Math.floor(n) === n) return String(n);
  return n.toFixed(4);
}
