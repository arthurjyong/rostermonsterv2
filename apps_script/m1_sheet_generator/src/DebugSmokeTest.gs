// DebugSmokeTest.gs
// Narrow smoke-test helpers for exercising the M1 ICU/HD generator core end-to-end
// from the Apps Script editor (Run dropdown) or `clasp run` without having to
// construct a config object by hand each time.
//
// Scope: development-only convenience. These helpers are NOT part of the generator
// contract and should not be used for real roster generation. They hard-code a
// fixed May–June 2026 ICU/HD config and a known public test spreadsheet ID.

// Public test spreadsheet ID. Intentionally committed: this is a shared, disposable
// testing target, not production data. Existing-mode smoke tests add a new tab to
// this spreadsheet; they do not modify any existing tab.
var SMOKE_TEST_EXISTING_SPREADSHEET_ID_ = '1fRsYCSSOyj4YtDme6-YAUqBO8kHXvgTZ3Ap9mdJ7RfM';

function smokeTestGenerateNewSpreadsheet_20260504_20260608() {
  var result = generateIntoNewSpreadsheet({
    department: 'CGH ICU/HD Call',
    periodStartDate: '2026-05-04',
    periodEndDate: '2026-06-08',
    doctorCountByGroup: { ICU_ONLY: 9, ICU_HD: 6, HD_ONLY: 6 },
  });
  Logger.log('smokeTestGenerateNewSpreadsheet_20260504_20260608 result:');
  Logger.log(JSON.stringify(result, null, 2));
  return result;
}

function smokeTestGenerateIntoExistingSpreadsheet_20260504_20260608() {
  var result = generateIntoExistingSpreadsheet({
    department: 'CGH ICU/HD Call',
    periodStartDate: '2026-05-04',
    periodEndDate: '2026-06-08',
    doctorCountByGroup: { ICU_ONLY: 9, ICU_HD: 6, HD_ONLY: 6 },
    spreadsheetId: SMOKE_TEST_EXISTING_SPREADSHEET_ID_,
  });
  Logger.log('smokeTestGenerateIntoExistingSpreadsheet_20260504_20260608 result:');
  Logger.log(JSON.stringify(result, null, 2));
  return result;
}

// May 2026 operator pilot shell. Xin Peng and Yee Sean are the monthly
// operators; HD_ONLY is bumped from 6 to 7 because a late email added one
// more MO to the HD call pool. This targets an operator-owned spreadsheet
// distinct from the generic disposable smoke-test target above — do not
// reuse this function or its spreadsheet ID for generic testing.
var MAY_2026_OPERATOR_SPREADSHEET_ID_ = '1VKR2ctzK5xIcx0T6UpL7Tet6Ur7xiU-KOJTd2iMPdzs';

function smokeTestGenerateMay2026OperatorShell() {
  var result = generateIntoExistingSpreadsheet({
    department: 'CGH ICU/HD Call',
    periodStartDate: '2026-05-04',
    periodEndDate: '2026-06-01',
    doctorCountByGroup: { ICU_ONLY: 9, ICU_HD: 6, HD_ONLY: 7 },
    spreadsheetId: MAY_2026_OPERATOR_SPREADSHEET_ID_,
  });
  Logger.log('smokeTestGenerateMay2026OperatorShell result:');
  Logger.log(JSON.stringify(result, null, 2));
  return result;
}

function smokeTestRunAll_20260504_20260608() {
  var newResult = smokeTestGenerateNewSpreadsheet_20260504_20260608();
  var existingResult = smokeTestGenerateIntoExistingSpreadsheet_20260504_20260608();
  var combined = {
    newSpreadsheet: newResult,
    existingSpreadsheet: existingResult,
  };
  Logger.log('smokeTestRunAll_20260504_20260608 combined result:');
  Logger.log(JSON.stringify(combined, null, 2));
  return combined;
}

// Zero-formatting smoke test. Creates a fresh empty spreadsheet and returns
// its identity only — no Layout, no ProtectionAndValidation, no
// TemplateArtifact. Isolates "can this caller create a sheet at all?" from
// any downstream formatting failures.
function smokeTestCreateEmptyOnly() {
  var name = 'smoke-empty-' + new Date().toISOString().replace(/[:.]/g, '-');
  var ss = SpreadsheetApp.create(name);
  var result = {
    spreadsheetId: ss.getId(),
    spreadsheetUrl: ss.getUrl(),
    spreadsheetName: ss.getName(),
  };
  Logger.log('smokeTestCreateEmptyOnly result:');
  Logger.log(JSON.stringify(result, null, 2));
  return result;
}
