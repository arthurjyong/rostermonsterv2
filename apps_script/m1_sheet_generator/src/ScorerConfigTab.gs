// ScorerConfigTab.gs
//
// Generates the Scorer Config tab declared in
// `docs/sheet_generation_contract.md` §11A (added under
// `docs/decision_log.md` D-0037).
//
// One tab per launcher run, paired by version suffix to the request-entry
// tab generated in the same run (so the snapshot extractor — pinned to
// late-M2 per D-0036 — can match the two tabs by suffix).
//
// Layout (operator-facing):
//   row 1:    "Scorer Config" title (merged A1:C1, bold, large)
//   row 3:    column headers "Component" | "Weight" | "Notes"
//   rows 4-N: one row per first-release scorer component
//             (col A: friendly label; col B: numeric weight cell —
//             operator-editable, pre-populated from
//             template.scoring.componentWeights; col C: sign-orientation hint)
//
// Each data row carries `DeveloperMetadata` with key
// `rosterMonster:componentId` and the canonical component identifier
// (e.g. `unfilledPenalty`). The future snapshot-extraction Apps Script
// (D-0036) consumes this metadata as the stable lookup key, decoupling
// extractor robustness from row/column placement and operator-facing
// label wording. Friendly labels can be reworded in future template
// versions without breaking extraction.
//
// Cell C-column layout per row carries the sign-orientation hint:
//   "Penalty (must be ≤ 0)"  — for components in PENALTY_COMPONENTS
//   "Reward (must be ≥ 0)"   — for components in REWARD_COMPONENTS
// per `docs/scorer_contract.md` §10 / §15. The parser-side admission
// discipline (`docs/parser_normalizer_contract.md` §14) is the
// authoritative correctness layer; this hint is operator UX only.

// Sign-orientation classifications mirror scorer_contract §10 / §15 +
// the Python implementation's `PENALTY_COMPONENTS` / `REWARD_COMPONENTS`
// frozensets in `python/rostermonster/scorer/result.py`.
var SCORER_CONFIG_PENALTY_COMPONENTS_ = [
  'unfilledPenalty',
  'pointBalanceWithinSection',
  'pointBalanceGlobal',
  'spacingPenalty',
  'preLeavePenalty',
  'standbyAdjacencyPenalty',
  'standbyCountFairnessPenalty',
];
var SCORER_CONFIG_REWARD_COMPONENTS_ = [
  'crReward',
  'dualEligibleIcuBonus',
];

// Friendly operator-facing labels for the 9 first-release components.
// These are first-release UX wording only; the canonical componentId
// stays in DeveloperMetadata for extractor lookup.
var SCORER_CONFIG_COMPONENT_LABELS_ = {
  unfilledPenalty: 'Unfilled-slot penalty',
  pointBalanceWithinSection: 'Within-section point-balance penalty',
  pointBalanceGlobal: 'Global point-balance penalty',
  spacingPenalty: 'Call-spacing penalty',
  preLeavePenalty: 'Call-before-leave penalty',
  crReward: 'Honored CR reward',
  dualEligibleIcuBonus: 'Dual-eligible ICU bonus',
  standbyAdjacencyPenalty: 'Standby-adjacency penalty',
  standbyCountFairnessPenalty: 'Standby-count fairness penalty',
};

// Canonical iteration order for the 9 first-release components — matches
// `docs/domain_model.md` §11.2 + ALL_COMPONENTS in
// `python/rostermonster/scorer/result.py` so the row order on the tab
// matches the ordering downstream consumers already use.
var SCORER_CONFIG_ALL_COMPONENTS_ = [
  'unfilledPenalty',
  'pointBalanceWithinSection',
  'pointBalanceGlobal',
  'spacingPenalty',
  'preLeavePenalty',
  'crReward',
  'dualEligibleIcuBonus',
  'standbyAdjacencyPenalty',
  'standbyCountFairnessPenalty',
];

// Tab-name builder. Pairs the Scorer Config tab to its request-entry tab
// by sharing the version suffix (`vMMDDHHMMSS`); operators see two tabs
// with matching suffixes so the pairing is visible. Future M2 C8
// snapshot extractor matches by this suffix.
function buildScorerConfigTabName_(versionedRequestTabName) {
  return 'Scorer Config ' + versionedRequestTabName;
}

function _scorerConfigSignNotes_(componentId) {
  if (SCORER_CONFIG_PENALTY_COMPONENTS_.indexOf(componentId) >= 0) {
    return 'Penalty (must be ≤ 0)';
  }
  if (SCORER_CONFIG_REWARD_COMPONENTS_.indexOf(componentId) >= 0) {
    return 'Reward (must be ≥ 0)';
  }
  // Should not happen — every first-release component is classified — but
  // we surface defensively rather than silently emit a blank notes cell.
  return 'Unknown sign orientation';
}

// Build a Scorer Config tab inside the given spreadsheet. Returns the
// concrete sheet handle plus the row indices for the 9 component rows
// (sheet-row, 1-indexed) keyed by componentId — useful for caller-side
// post-processing (e.g. attaching a Property entry per FW-0024 for the
// per-day call-point rows on the request-entry side).
function buildScorerConfigTab_(ss, requestEntryTabName, template) {
  var componentWeights = template.scoring.componentWeights;
  if (!componentWeights) {
    throw new Error(
      'template.scoring.componentWeights missing — cannot generate Scorer ' +
      'Config tab. Required per docs/template_artifact_contract.md §11.'
    );
  }

  var tabName = buildScorerConfigTabName_(requestEntryTabName);
  if (ss.getSheetByName(tabName) !== null) {
    throw new Error(
      'Target spreadsheet already contains a tab named "' + tabName +
      '". Generation aborted; nothing was modified. Re-run to get a new ' +
      'timestamp.'
    );
  }
  var sheet = ss.insertSheet(tabName);

  var titleRow = 1;
  var headerRow = 3;
  var firstDataRow = 4;
  var componentCount = SCORER_CONFIG_ALL_COMPONENTS_.length;
  var lastDataRow = firstDataRow + componentCount - 1;

  // Title cell, merged across all three columns.
  sheet.getRange(titleRow, 1, 1, 3).merge();
  sheet.getRange(titleRow, 1)
    .setValue('Scorer Config')
    .setFontSize(14)
    .setFontWeight('bold')
    .setHorizontalAlignment('center');

  // Header row.
  sheet.getRange(headerRow, 1, 1, 3).setValues([
    ['Component', 'Weight', 'Notes'],
  ]).setFontWeight('bold').setBackground('#e8e8e8');

  // 9 data rows.
  var dataValues = [];
  for (var i = 0; i < componentCount; i++) {
    var componentId = SCORER_CONFIG_ALL_COMPONENTS_[i];
    if (!Object.prototype.hasOwnProperty.call(componentWeights, componentId)) {
      throw new Error(
        'template.scoring.componentWeights missing default for "' +
        componentId + '"; required per docs/template_artifact_contract.md ' +
        '§11. Cannot generate Scorer Config tab without all 9 first-release ' +
        'defaults.'
      );
    }
    var defaultWeight = componentWeights[componentId];
    var label = SCORER_CONFIG_COMPONENT_LABELS_[componentId] || componentId;
    var notes = _scorerConfigSignNotes_(componentId);
    dataValues.push([label, defaultWeight, notes]);
  }
  sheet.getRange(firstDataRow, 1, componentCount, 3).setValues(dataValues);

  // Column widths — labels need most space; weight cells modest; notes
  // wide enough to fit "Penalty (must be ≤ 0)" without truncation.
  sheet.setColumnWidth(1, 280);
  sheet.setColumnWidth(2, 100);
  sheet.setColumnWidth(3, 200);

  // Trim unused columns / rows so protection semantics are bounded
  // (mirrors the request-entry tab discipline in Layout.gs).
  var maxCols = sheet.getMaxColumns();
  if (maxCols > 3) {
    sheet.deleteColumns(4, maxCols - 3);
  }
  var maxRows = sheet.getMaxRows();
  if (maxRows > lastDataRow) {
    sheet.deleteRows(lastDataRow + 1, maxRows - lastDataRow);
  }

  // Attach DeveloperMetadata to each data row carrying the canonical
  // componentId. Snapshot extractor (M2 C8) reads this as the stable
  // lookup key, decoupled from cell content / row order / label wording.
  for (var j = 0; j < componentCount; j++) {
    var rowRange = sheet.getRange(firstDataRow + j, 1, 1, 3);
    rowRange.addDeveloperMetadata(
      'rosterMonster:componentId',
      SCORER_CONFIG_ALL_COMPONENTS_[j]
    );
  }

  // Lock down the tab so only the weight cells (column B, rows 4-12) are
  // operator-editable. Title, headers, labels, notes are template-owned-
  // structural per `docs/sheet_generation_contract.md` §11A. Same
  // approach as ProtectionAndValidation.gs uses for the request-entry tab.
  var protection = sheet.protect()
    .setDescription('Scorer Config tab — all cells locked except weight column')
    .setWarningOnly(false);
  // Remove any default editor list and re-add only the script owner.
  protection.removeEditors(protection.getEditors());
  if (protection.canDomainEdit && protection.canDomainEdit()) {
    try { protection.setDomainEdit(false); } catch (_) { /* non-domain sheet */ }
  }
  // Operator-editable exception: weight cells in column B, rows 4-12.
  protection.setUnprotectedRanges([
    sheet.getRange(firstDataRow, 2, componentCount, 1),
  ]);

  // Frozen header so the operator can scroll long component lists in
  // future without losing the column headers (cheap polish; future-
  // proof for FW-0007 curve-parameter rows).
  sheet.setFrozenRows(headerRow);

  // Build the row-index lookup for callers / future extractor.
  var componentRowByComponentId = {};
  for (var k = 0; k < componentCount; k++) {
    componentRowByComponentId[SCORER_CONFIG_ALL_COMPONENTS_[k]] =
      firstDataRow + k;
  }

  return {
    sheet: sheet,
    tabName: tabName,
    componentRowByComponentId: componentRowByComponentId,
    weightColumn: 2,
    firstDataRow: firstDataRow,
    lastDataRow: lastDataRow,
  };
}
