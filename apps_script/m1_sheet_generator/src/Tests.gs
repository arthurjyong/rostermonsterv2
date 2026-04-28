// Tests.gs
// Lightweight self-check harness for the pure date/holiday logic. Runs inside the
// Apps Script editor (Run → runAllTests_). These tests only exercise the pure JS
// helpers — they do not touch SpreadsheetApp — so they stay fast and deterministic.

function runAllTests_() {
  var tests = [
    testHariRayaPuasa2026MatchesMomGazette_,
    testHariRayaPuasa2026PriorDayNotHoliday_,
    testCallPointAroundHariRayaPuasa2026_,
    testIsPublicHolidayThrowsForUnsupportedYear_,
    testBuildDateRangeRejectsStartBeforeSupportedRange_,
    testBuildDateRangeRejectsEndAtSupportedBoundary_,
    testBuildDateRangeAllowsEndOneBeforeBoundary_,
    testComputeDefaultCallPointThrowsAcrossYearBoundary_,
    testExtractSpreadsheetIdAcceptsBareId_,
    testExtractSpreadsheetIdAcceptsPlainEditUrl_,
    testExtractSpreadsheetIdAcceptsAccountScopedUrl_,
    testExtractSpreadsheetIdRejectsUnrecognizedValue_,
    testExtractSpreadsheetIdRejectsPublishedLinkFalseMatch_,
    // M2 C7 — Scorer Config tab + FW-0024 (D-0037 producer-side wiring).
    testTemplatePointRowsAllCarrySlotType_,
    testTemplatePointRowsSlotTypeReferencesKnownCallSlot_,
    testTemplateComponentWeightsCoversAllNineFirstReleaseComponents_,
    testTemplateComponentWeightsAreSignCorrect_,
    testScorerConfigTabNamePairsWithRequestEntryTab_,
    testScorerConfigComponentRowOrderMatchesPythonAllComponents_,
  ];
  var failures = [];
  for (var i = 0; i < tests.length; i++) {
    try {
      tests[i]();
      Logger.log('PASS: ' + tests[i].name);
    } catch (e) {
      failures.push({ name: tests[i].name, message: (e && e.message) || String(e) });
      Logger.log('FAIL: ' + tests[i].name + ' — ' + ((e && e.message) || e));
    }
  }
  if (failures.length > 0) {
    throw new Error('Tests failed: ' + failures.length + ' of ' + tests.length +
      '. First failure: ' + failures[0].name + ' — ' + failures[0].message);
  }
  Logger.log('All ' + tests.length + ' tests passed.');
  return { total: tests.length, failures: [] };
}

function testHariRayaPuasa2026MatchesMomGazette_() {
  // MOM gazetted 2026 Hari Raya Puasa: 21 March 2026 (Saturday).
  var gazetted = parseYyyyMmDdToUtc_('2026-03-21');
  assertTrue_(isPublicHoliday_(gazetted), '2026-03-21 should be classified as a public holiday');
}

function testHariRayaPuasa2026PriorDayNotHoliday_() {
  // 2026-03-20 is a Friday and is not a gazetted public holiday.
  var priorDay = parseYyyyMmDdToUtc_('2026-03-20');
  assertFalse_(isPublicHoliday_(priorDay), '2026-03-20 should NOT be a public holiday');
  assertFalse_(isWeekend_(priorDay), '2026-03-20 should not be a weekend (Friday)');
}

function testCallPointAroundHariRayaPuasa2026_() {
  // Rule values pulled directly from the settled defaultRule matrix.
  var rule = {
    weekdayToWeekday: 1,
    weekdayToWeekendOrPublicHoliday: 1.75,
    weekendOrPublicHolidayToWeekendOrPublicHoliday: 2,
    weekendOrPublicHolidayToWeekday: 1.5,
  };
  // 2026-03-20 (Fri, non-PH) → 2026-03-21 (Sat, PH) => 1.75
  var fri = parseYyyyMmDdToUtc_('2026-03-20');
  assertEqualNumber_(computeDefaultCallPoint_(fri, rule), 1.75,
    'weekday-to-WEPH transition across 20→21 Mar 2026');
  // 2026-03-21 (Sat/PH) → 2026-03-22 (Sun) => 2
  var sat = parseYyyyMmDdToUtc_('2026-03-21');
  assertEqualNumber_(computeDefaultCallPoint_(sat, rule), 2,
    'WEPH-to-WEPH transition across 21→22 Mar 2026');
  // 2026-03-22 (Sun) → 2026-03-23 (Mon, non-PH) => 1.5
  var sun = parseYyyyMmDdToUtc_('2026-03-22');
  assertEqualNumber_(computeDefaultCallPoint_(sun, rule), 1.5,
    'WEPH-to-weekday transition across 22→23 Mar 2026');
}

function testIsPublicHolidayThrowsForUnsupportedYear_() {
  var outOfRange = parseYyyyMmDdToUtc_('2027-01-01');
  assertThrows_(function () { isPublicHoliday_(outOfRange); },
    'isPublicHoliday_ must throw for years outside the supported range');
}

function testBuildDateRangeRejectsStartBeforeSupportedRange_() {
  assertThrows_(function () { buildDateRange_('2024-12-15', '2025-01-10'); },
    'buildDateRange_ must throw when periodStartDate is before supported range');
}

function testBuildDateRangeRejectsEndAtSupportedBoundary_() {
  // end == 2026-12-31 forces the next-day lookup (2027-01-01) outside the supported
  // range, which must fail fast rather than silently treat the year as non-holiday.
  assertThrows_(function () { buildDateRange_('2026-12-01', '2026-12-31'); },
    'buildDateRange_ must throw when the next-day lookup crosses the supported-year boundary');
}

function testBuildDateRangeAllowsEndOneBeforeBoundary_() {
  // end == 2026-12-30 → next-day lookup is 2026-12-31, still in range. Must succeed.
  var days = buildDateRange_('2026-12-01', '2026-12-30');
  assertEqualNumber_(days.length, 30, 'buildDateRange_ should return 30 descriptors for 1–30 Dec 2026');
}

function testComputeDefaultCallPointThrowsAcrossYearBoundary_() {
  var rule = {
    weekdayToWeekday: 1,
    weekdayToWeekendOrPublicHoliday: 1.75,
    weekendOrPublicHolidayToWeekendOrPublicHoliday: 2,
    weekendOrPublicHolidayToWeekday: 1.5,
  };
  // Day N = 2026-12-31 means day N+1 = 2027-01-01, which is outside the supported
  // holiday-data range. The classification must throw rather than silently default.
  var lastDay = parseYyyyMmDdToUtc_('2026-12-31');
  assertThrows_(function () { computeDefaultCallPoint_(lastDay, rule); },
    'computeDefaultCallPoint_ must throw when the next-day lookup crosses years');
}

function testExtractSpreadsheetIdAcceptsBareId_() {
  var bare = '1VKR2ctzK5xIcx0T6UpL7Tet6Ur7xiU-KOJTd2iMPdzs';
  var out = extractSpreadsheetId_(bare);
  assertTrue_(out === bare, 'bare ID should round-trip through extractor');
}

function testExtractSpreadsheetIdAcceptsPlainEditUrl_() {
  var id = '1VKR2ctzK5xIcx0T6UpL7Tet6Ur7xiU-KOJTd2iMPdzs';
  var out = extractSpreadsheetId_('https://docs.google.com/spreadsheets/d/' + id + '/edit');
  assertTrue_(out === id, 'plain edit URL should extract to bare ID; got ' + JSON.stringify(out));
}

function testExtractSpreadsheetIdAcceptsAccountScopedUrl_() {
  var id = '1VKR2ctzK5xIcx0T6UpL7Tet6Ur7xiU-KOJTd2iMPdzs';
  var out = extractSpreadsheetId_('https://docs.google.com/spreadsheets/u/1/d/' + id + '/edit#gid=0');
  assertTrue_(out === id, 'account-scoped URL should extract to bare ID; got ' + JSON.stringify(out));
}

function testExtractSpreadsheetIdRejectsUnrecognizedValue_() {
  assertThrows_(function () { extractSpreadsheetId_('not a sheet'); },
    'extractor must throw on unrecognized references');
}

function testExtractSpreadsheetIdRejectsPublishedLinkFalseMatch_() {
  // Published-link shape uses /d/e/<published-id>/pubhtml. The §12.5 matcher must not
  // capture "e" as the ID; the 20-char minimum and trailing character-class guard
  // against that. Such a value is not a valid bare ID either, so the extractor throws.
  assertThrows_(function () {
    extractSpreadsheetId_('https://docs.google.com/spreadsheets/d/e/2PACX-1vShortPubId/pubhtml');
  }, 'published-link URL with a single-char e/ segment must not be mis-extracted');
}

// ---------------------------------------------------------------------------
// M2 C7 — Scorer Config tab + FW-0024 (D-0037 producer-side wiring)
// ---------------------------------------------------------------------------

function testTemplatePointRowsAllCarrySlotType_() {
  // Per `docs/decision_log.md` D-0037 + template_artifact_contract.md §9:
  // every pointRow MUST declare slotType. Without it, the parser overlay
  // cannot derive ScoringConfig.pointRules per parser_normalizer §9.
  var template = loadTemplateArtifactByDepartment_('CGH ICU/HD Call');
  var pointRows = template.inputSheetLayout.pointRows;
  assertTrue_(pointRows.length > 0, 'template must declare at least one pointRow');
  for (var i = 0; i < pointRows.length; i++) {
    var pr = pointRows[i];
    assertTrue_(typeof pr.slotType === 'string' && pr.slotType.length > 0,
      'pointRow ' + JSON.stringify(pr.rowKey) + ' missing slotType binding (D-0037)');
  }
}

function testTemplatePointRowsSlotTypeReferencesKnownCallSlot_() {
  // Per template_artifact_contract.md §9: pointRows[].slotType MUST
  // reference a slots[].slotId whose slotKind == 'CALL'.
  var template = loadTemplateArtifactByDepartment_('CGH ICU/HD Call');
  var callSlotIds = {};
  for (var i = 0; i < template.slots.length; i++) {
    if (template.slots[i].slotKind === 'CALL') {
      callSlotIds[template.slots[i].slotId] = true;
    }
  }
  var pointRows = template.inputSheetLayout.pointRows;
  for (var j = 0; j < pointRows.length; j++) {
    var pr = pointRows[j];
    assertTrue_(callSlotIds[pr.slotType] === true,
      'pointRow rowKey=' + pr.rowKey + ' binds slotType=' + pr.slotType +
      ' which is not a known CALL slot');
  }
}

function testTemplateComponentWeightsCoversAllNineFirstReleaseComponents_() {
  // Per template_artifact_contract.md §11 (D-0037): scoring.componentWeights
  // MUST have one entry per first-release component identifier.
  var template = loadTemplateArtifactByDepartment_('CGH ICU/HD Call');
  var weights = template.scoring.componentWeights;
  assertTrue_(typeof weights === 'object' && weights !== null,
    'scoring.componentWeights missing or not an object');
  var required = [
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
  for (var i = 0; i < required.length; i++) {
    var componentId = required[i];
    assertTrue_(
      Object.prototype.hasOwnProperty.call(weights, componentId),
      'scoring.componentWeights missing required component: ' + componentId
    );
    assertTrue_(typeof weights[componentId] === 'number' && isFinite(weights[componentId]),
      'scoring.componentWeights.' + componentId + ' must be a finite number');
  }
}

function testTemplateComponentWeightsAreSignCorrect_() {
  // Per scorer_contract.md §10 / §15 + template_artifact_contract.md §11:
  // template defaults MUST preserve sign orientation. Penalty components
  // contribute non-positively; reward components contribute non-negatively.
  var template = loadTemplateArtifactByDepartment_('CGH ICU/HD Call');
  var w = template.scoring.componentWeights;
  // Penalties — all <= 0.
  assertTrue_(w.unfilledPenalty <= 0,
    'unfilledPenalty must be <= 0; got ' + w.unfilledPenalty);
  assertTrue_(w.pointBalanceWithinSection <= 0,
    'pointBalanceWithinSection must be <= 0');
  assertTrue_(w.pointBalanceGlobal <= 0,
    'pointBalanceGlobal must be <= 0');
  assertTrue_(w.spacingPenalty <= 0, 'spacingPenalty must be <= 0');
  assertTrue_(w.preLeavePenalty <= 0, 'preLeavePenalty must be <= 0');
  assertTrue_(w.standbyAdjacencyPenalty <= 0,
    'standbyAdjacencyPenalty must be <= 0');
  assertTrue_(w.standbyCountFairnessPenalty <= 0,
    'standbyCountFairnessPenalty must be <= 0');
  // Rewards — all >= 0.
  assertTrue_(w.crReward >= 0, 'crReward must be >= 0; got ' + w.crReward);
  assertTrue_(w.dualEligibleIcuBonus >= 0,
    'dualEligibleIcuBonus must be >= 0');
}

function testScorerConfigTabNamePairsWithRequestEntryTab_() {
  // The Scorer Config tab name MUST share the request-entry tab's
  // version suffix so the future snapshot extractor (M2 C8) can match
  // them by suffix. Implementation detail: prefix "Scorer Config " +
  // request tab name.
  var requestTabName = 'v0428123045';
  var scorerTabName = buildScorerConfigTabName_(requestTabName);
  assertTrue_(scorerTabName.indexOf(requestTabName) >= 0,
    'Scorer Config tab name must embed the request-entry tab name; got ' +
    JSON.stringify(scorerTabName));
}

function testScorerConfigComponentRowOrderMatchesPythonAllComponents_() {
  // The 9 component rows on the Scorer Config tab MUST be in the
  // canonical order published in `python/rostermonster/scorer/result.py`'s
  // ALL_COMPONENTS tuple (= docs/domain_model.md §11.2). Stable order
  // gives the snapshot extractor a fallback if DeveloperMetadata read
  // ever fails — extractor can fall back to row-index lookup.
  var expected = [
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
  assertEqualNumber_(SCORER_CONFIG_ALL_COMPONENTS_.length, expected.length,
    'SCORER_CONFIG_ALL_COMPONENTS_ length mismatch');
  for (var i = 0; i < expected.length; i++) {
    assertTrue_(SCORER_CONFIG_ALL_COMPONENTS_[i] === expected[i],
      'SCORER_CONFIG_ALL_COMPONENTS_[' + i + '] expected ' + expected[i] +
      ' got ' + SCORER_CONFIG_ALL_COMPONENTS_[i]);
  }
}

// ---------------------------------------------------------------------------
// Tiny assertion helpers
// ---------------------------------------------------------------------------

function assertTrue_(value, message) {
  if (value !== true) {
    throw new Error('assertTrue_ failed: ' + (message || '(no message)') + ' — got ' + JSON.stringify(value));
  }
}

function assertFalse_(value, message) {
  if (value !== false) {
    throw new Error('assertFalse_ failed: ' + (message || '(no message)') + ' — got ' + JSON.stringify(value));
  }
}

function assertEqualNumber_(actual, expected, message) {
  if (typeof actual !== 'number' || typeof expected !== 'number' || actual !== expected) {
    throw new Error('assertEqualNumber_ failed: ' + (message || '(no message)') +
      ' — expected ' + JSON.stringify(expected) + ', got ' + JSON.stringify(actual));
  }
}

function assertThrows_(fn, message) {
  var threw = false;
  try { fn(); } catch (e) { threw = true; }
  if (!threw) {
    throw new Error('assertThrows_ failed: ' + (message || '(no message)'));
  }
}
