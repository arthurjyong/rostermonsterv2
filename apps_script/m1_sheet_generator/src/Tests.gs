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
