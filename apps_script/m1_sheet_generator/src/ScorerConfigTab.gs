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
//   row 1:    "Scorer Config" title (merged A1:D1, bold, large)
//   row 3:    column headers "Component" | "Weight" | "Description" | "Suggested Range"
//   rows 4-N: one row per first-release scorer component
//             (col A: friendly label; col B: numeric weight cell —
//             operator-editable, pre-populated from
//             template.scoring.componentWeights, with data validation
//             enforcing sign orientation; col C: 1-2 sentence description
//             of what the component scores; col D: suggested numeric range
//             with the sign discipline embedded)
//
// Each data row carries `DeveloperMetadata` with key
// `rosterMonster:componentId` and the canonical component identifier
// (e.g. `unfilledPenalty`). The future snapshot-extraction Apps Script
// (D-0036) consumes this metadata as the stable lookup key, decoupling
// extractor robustness from row/column placement and operator-facing
// label wording. Friendly labels can be reworded in future template
// versions without breaking extraction.
//
// Per-cell data validation enforces sign orientation at type-time:
//   - PENALTY_COMPONENTS rows: Number ≤ 0, setAllowInvalid(false)
//   - REWARD_COMPONENTS rows: Number ≥ 0, setAllowInvalid(false)
// per `docs/scorer_contract.md` §10 / §15. Operator typing a wrong-sign
// value gets an immediate Sheets popup; the parser-side admission
// discipline (`docs/parser_normalizer_contract.md` §14) remains the
// authoritative correctness layer at parse time.

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

// 1-2 sentence operator-facing descriptions per component. Aim is the
// operator who has never read the contracts can still understand what
// they're tuning. Sign discipline is in the Suggested Range column to
// keep this column descriptive rather than prescriptive.
var SCORER_CONFIG_COMPONENT_DESCRIPTIONS_ = {
  unfilledPenalty:
    'Fires once for every required slot that ends up without a doctor. ' +
    'Discourages rosters that leave any slots empty.',
  pointBalanceWithinSection:
    'Penalises uneven call-point load within each doctor group ' +
    '(ICU-only, ICU+HD, HD-only). Encourages fairness inside each ' +
    'cohort independently.',
  pointBalanceGlobal:
    'Penalises uneven call-point load across ALL doctors regardless ' +
    'of group. Cross-group fairness counterweight to the within-section ' +
    'measure.',
  spacingPenalty:
    'Fires when the same doctor has two call placements within the ' +
    '3-day minimum-gap window. Spreads call burden across the period.',
  preLeavePenalty:
    'Fires when a doctor is on call the day before a leave/absence ' +
    '(annual leave, EMCC PM-off, etc).',
  crReward:
    'Rewards rosters that honour call requests (CRs). Diminishes per ' +
    'doctor (1st CR weighted full, 2nd half, 3rd third…) to spread ' +
    'honored CRs across the team.',
  dualEligibleIcuBonus:
    'Bonus when an ICU+HD eligible (R3) doctor takes a MICU call. ' +
    'Encourages prioritising R3 doctors for MICU calls to prepare ' +
    'them for future registrar calls.',
  standbyAdjacencyPenalty:
    'Fires when the same doctor has standby on day N and call on ' +
    'day N+1 (or vice versa). Prevents "standby-then-call" double duty.',
  standbyCountFairnessPenalty:
    'Penalises uneven standby-count distribution across doctors. ' +
    'Standby-load fairness counterpart to the call-point fairness measures.',
};

// Sign-orientation constraints per component per
// `docs/scorer_contract.md` §10 / §15. We deliberately do NOT publish
// "typical magnitude" guidance here — the v1 reference-pass tuning
// (FW-0014) hasn't completed and any numeric ranges shipped now would
// be uncalibrated guesswork. Operators get the sign rule (which the
// data-validation rule enforces at type-time) and decide magnitudes
// from pilot experience.
var SCORER_CONFIG_COMPONENT_SIGN_RULES_ = {
  unfilledPenalty: 'Must be ≤ 0',
  pointBalanceWithinSection: 'Must be ≤ 0',
  pointBalanceGlobal: 'Must be ≤ 0',
  spacingPenalty: 'Must be ≤ 0',
  preLeavePenalty: 'Must be ≤ 0',
  crReward: 'Must be ≥ 0',
  dualEligibleIcuBonus: 'Must be ≥ 0',
  standbyAdjacencyPenalty: 'Must be ≤ 0',
  standbyCountFairnessPenalty: 'Must be ≤ 0',
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

function _scorerConfigBuildDataValidation_(componentId) {
  // Sign-orientation enforcement at type-time per
  // `docs/scorer_contract.md` §10 / §15. setAllowInvalid(false) makes
  // Sheets reject the input with a popup rather than warn-and-allow.
  // Help text shows in the popup so the operator immediately understands
  // why their value was rejected.
  if (SCORER_CONFIG_PENALTY_COMPONENTS_.indexOf(componentId) >= 0) {
    return SpreadsheetApp.newDataValidation()
      .requireNumberLessThanOrEqualTo(0)
      .setHelpText(
        SCORER_CONFIG_COMPONENT_LABELS_[componentId] +
        ' is a penalty component — its weight MUST be ≤ 0 ' +
        '(non-positive contribution to total score).'
      )
      .setAllowInvalid(false)
      .build();
  }
  if (SCORER_CONFIG_REWARD_COMPONENTS_.indexOf(componentId) >= 0) {
    return SpreadsheetApp.newDataValidation()
      .requireNumberGreaterThanOrEqualTo(0)
      .setHelpText(
        SCORER_CONFIG_COMPONENT_LABELS_[componentId] +
        ' is a reward component — its weight MUST be ≥ 0 ' +
        '(non-negative contribution to total score).'
      )
      .setAllowInvalid(false)
      .build();
  }
  // Should not happen — every first-release component is classified.
  return null;
}

// Build a Scorer Config tab inside the given spreadsheet. Returns the
// concrete sheet handle plus the row indices for the 9 component rows
// (sheet-row, 1-indexed) keyed by componentId — useful for caller-side
// post-processing (e.g. attaching a Property entry per FW-0024 for the
// per-day call-point rows on the request-entry side).
// runId is parsed off the request-entry tab name (`vMMddHHmmss`) so the
// snapshot extractor's runId-paired tab discovery (per
// `docs/snapshot_adapter_contract.md` §6 step 3) can locate this tab from
// the active request-entry tab without ambiguity. Returned to the caller via
// the result object for tests + downstream callers that want the value.
function _scorerConfigParseRunId_(versionedRequestTabName) {
  // tab name shape is `v<MMddHHmmss>` per `buildVersionedTabName_` in
  // GenerateSheet.gs; the runId IS that exact string.
  return String(versionedRequestTabName);
}

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
  var totalCols = 4;

  // Title cell, merged across all four columns.
  sheet.getRange(titleRow, 1, 1, totalCols).merge();
  sheet.getRange(titleRow, 1)
    .setValue('Scorer Config')
    .setFontSize(14)
    .setFontWeight('bold')
    .setHorizontalAlignment('center');

  // Header row.
  sheet.getRange(headerRow, 1, 1, totalCols).setValues([
    ['Component', 'Weight', 'Description', 'Sign'],
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
    var description = SCORER_CONFIG_COMPONENT_DESCRIPTIONS_[componentId] || '';
    var signRule = SCORER_CONFIG_COMPONENT_SIGN_RULES_[componentId] || '';
    dataValues.push([label, defaultWeight, description, signRule]);
  }
  sheet.getRange(firstDataRow, 1, componentCount, totalCols).setValues(dataValues);

  // Wrap text only in the description column; the sign column is short
  // single-line text that doesn't benefit from wrapping.
  sheet.getRange(firstDataRow, 3, componentCount, 1).setWrap(true);
  sheet.getRange(firstDataRow, 1, componentCount, 4).setVerticalAlignment('top');

  // Column widths — label modest, weight narrow, description generous
  // for multi-sentence content, sign cell narrow (just "Must be ≤ 0").
  sheet.setColumnWidth(1, 240);
  sheet.setColumnWidth(2, 90);
  sheet.setColumnWidth(3, 420);
  sheet.setColumnWidth(4, 110);

  // Trim unused columns / rows so protection semantics are bounded
  // (mirrors the request-entry tab discipline in Layout.gs).
  var maxCols = sheet.getMaxColumns();
  if (maxCols > totalCols) {
    sheet.deleteColumns(totalCols + 1, maxCols - totalCols);
  }
  var maxRows = sheet.getMaxRows();
  if (maxRows > lastDataRow) {
    sheet.deleteRows(lastDataRow + 1, maxRows - lastDataRow);
  }

  // Attach DeveloperMetadata to each data row carrying the canonical
  // componentId. Snapshot extractor (M2 C8) reads this as the stable
  // lookup key, decoupled from cell content / row order / label wording.
  //
  // The Sheets API only allows DeveloperMetadata at sheet / row / column /
  // spreadsheet scope — not arbitrary cell ranges. A range constructed
  // with explicit numRows/numCols (even when it covers the whole row
  // width post-trim) is treated as an "arbitrary range" and rejected
  // with "Adding developer metadata to arbitrary ranges is not currently
  // supported." Use A1 row notation ("4:4") so the range is recognized
  // as row-scoped.
  //
  // Per-row data validation enforces sign orientation at type-time.
  // The parser-side admission (parser_normalizer §14) remains the
  // authoritative correctness layer at parse time, but the operator
  // gets immediate feedback here without round-tripping through the
  // Python pipeline.
  for (var j = 0; j < componentCount; j++) {
    var componentIdJ = SCORER_CONFIG_ALL_COMPONENTS_[j];
    var rowNum = firstDataRow + j;
    var rowRange = sheet.getRange(rowNum + ':' + rowNum);
    rowRange.addDeveloperMetadata(
      'rosterMonster:componentId',
      componentIdJ
    );
    var validation = _scorerConfigBuildDataValidation_(componentIdJ);
    if (validation !== null) {
      sheet.getRange(rowNum, 2).setDataValidation(validation);
    }
  }

  // Lock down the tab so only the weight cells (column B, rows 4-12) are
  // operator-editable. Title, headers, labels, descriptions, suggested
  // ranges are template-owned-structural per
  // `docs/sheet_generation_contract.md` §11A. Same approach as
  // ProtectionAndValidation.gs uses for the request-entry tab.
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

  // Per `docs/sheet_generation_contract.md` §11B + `docs/decision_log.md`
  // D-0043 sub-decision 1: attach sheet-level DeveloperMetadata so the
  // snapshot extractor's runId-paired tab discovery (per
  // `docs/snapshot_adapter_contract.md` §6 step 3) can locate this tab as
  // the unique `tabType=scorerConfig` sheet whose `runId` matches the
  // active request-entry tab's `runId`.
  var runId = _scorerConfigParseRunId_(requestEntryTabName);
  sheet.addDeveloperMetadata('rosterMonster:tabType', 'scorerConfig');
  sheet.addDeveloperMetadata('rosterMonster:templateVersion',
    String(template.templateVersion || 'unknown'));
  sheet.addDeveloperMetadata('rosterMonster:runId', runId);

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
