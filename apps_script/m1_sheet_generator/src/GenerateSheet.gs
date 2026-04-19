// GenerateSheet.gs
// Public entrypoints for generating the empty ICU/HD request sheet shell.
// Two modes are supported (docs/sheet_generation_contract.md section 3A):
//   - generateIntoNewSpreadsheet(config):        create a new spreadsheet file
//   - generateIntoExistingSpreadsheet(config):   create a new tab in an existing
//                                                spreadsheet identified by ID
//
// config shape:
//   {
//     department?: 'CGH ICU/HD Call',          // defaults to ICU/HD for first release
//     periodStartDate: 'YYYY-MM-DD',
//     periodEndDate:   'YYYY-MM-DD',
//     doctorCountByGroup: { ICU_ONLY: n, ICU_HD: n, HD_ONLY: n },
//     spreadsheetId?:  '<existing spreadsheet ID — required for existing-mode>'
//   }

function generateIntoNewSpreadsheet(config) {
  var normalized = normalizeAndValidateConfig_(config, /*needsSpreadsheetId=*/false);
  var template = loadTemplateArtifactByDepartment_(normalized.department);
  validateDoctorCountsAgainstTemplate_(normalized.doctorCountByGroup, template);
  var dateRange = buildDateRange_(normalized.periodStartDate, normalized.periodEndDate);

  var spreadsheetName = buildSpreadsheetName_(normalized);
  var ss = SpreadsheetApp.create(spreadsheetName);
  var tabName = buildVersionedTabName_(new Date());
  var sheet = ss.getActiveSheet();
  sheet.setName(tabName);

  var layoutInfo = buildLayout_(sheet, template, dateRange, normalized.doctorCountByGroup);
  applyValidations_(sheet, layoutInfo);
  applyProtections_(sheet, layoutInfo);

  return {
    mode: 'NEW_SPREADSHEET',
    spreadsheetId: ss.getId(),
    spreadsheetUrl: ss.getUrl(),
    spreadsheetName: ss.getName(),
    sheetName: sheet.getName(),
    periodStartDate: normalized.periodStartDate,
    periodEndDate: normalized.periodEndDate,
    doctorCountByGroup: normalized.doctorCountByGroup,
  };
}

function generateIntoExistingSpreadsheet(config) {
  var normalized = normalizeAndValidateConfig_(config, /*needsSpreadsheetId=*/true);
  var template = loadTemplateArtifactByDepartment_(normalized.department);
  validateDoctorCountsAgainstTemplate_(normalized.doctorCountByGroup, template);
  var dateRange = buildDateRange_(normalized.periodStartDate, normalized.periodEndDate);

  var ss;
  try {
    ss = SpreadsheetApp.openById(normalized.spreadsheetId);
  } catch (e) {
    throw new Error('Could not open spreadsheet by ID "' + normalized.spreadsheetId +
      '": ' + (e && e.message ? e.message : e));
  }

  var tabName = buildVersionedTabName_(new Date());
  if (ss.getSheetByName(tabName) !== null) {
    // Timestamped tab names make collision unlikely; fail loudly if it happens so
    // operators can retry rather than silently overwriting or auto-suffixing.
    throw new Error('Target spreadsheet already contains a tab named "' + tabName +
      '". Generation aborted; nothing was modified. Re-run to get a new timestamp.');
  }

  var sheet = ss.insertSheet(tabName);
  var layoutInfo = buildLayout_(sheet, template, dateRange, normalized.doctorCountByGroup);
  applyValidations_(sheet, layoutInfo);
  applyProtections_(sheet, layoutInfo);

  return {
    mode: 'EXISTING_SPREADSHEET',
    spreadsheetId: ss.getId(),
    spreadsheetUrl: ss.getUrl(),
    spreadsheetName: ss.getName(),
    sheetName: sheet.getName(),
    periodStartDate: normalized.periodStartDate,
    periodEndDate: normalized.periodEndDate,
    doctorCountByGroup: normalized.doctorCountByGroup,
  };
}

// ---------------------------------------------------------------------------
// Helpers (file-scoped; not part of the public entrypoint surface)
// ---------------------------------------------------------------------------

function normalizeAndValidateConfig_(config, needsSpreadsheetId) {
  if (!config || typeof config !== 'object') {
    throw new Error('Missing generation config object.');
  }
  var department = (config.department == null ? '' : String(config.department)).trim() ||
    'CGH ICU/HD Call';

  var start = coerceToIsoDate_(config.periodStartDate, 'periodStartDate');
  var end   = coerceToIsoDate_(config.periodEndDate,   'periodEndDate');
  // Strict ordering is re-checked inside buildDateRange_; check here too so the error
  // surfaces before any spreadsheet work.
  if (start > end) {
    throw new Error('periodStartDate (' + start + ') must be on or before periodEndDate (' + end + ').');
  }

  var counts = config.doctorCountByGroup;
  if (!counts || typeof counts !== 'object') {
    throw new Error('Missing doctorCountByGroup map.');
  }

  var spreadsheetId = null;
  if (needsSpreadsheetId) {
    spreadsheetId = (config.spreadsheetId == null ? '' : String(config.spreadsheetId)).trim();
    if (!spreadsheetId) {
      throw new Error('Existing-spreadsheet mode requires a non-empty spreadsheetId.');
    }
  }

  return {
    department: department,
    periodStartDate: start,
    periodEndDate: end,
    doctorCountByGroup: counts,
    spreadsheetId: spreadsheetId,
  };
}

function coerceToIsoDate_(value, fieldName) {
  if (value instanceof Date) {
    var tz = Session.getScriptTimeZone() || 'Asia/Singapore';
    return Utilities.formatDate(value, tz, 'yyyy-MM-dd');
  }
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return value;
  }
  throw new Error(fieldName + ' must be a YYYY-MM-DD string or a Date (got ' + JSON.stringify(value) + ').');
}

function validateDoctorCountsAgainstTemplate_(counts, template) {
  var groups = template.doctorGroups;
  for (var i = 0; i < groups.length; i++) {
    var g = groups[i];
    if (!Object.prototype.hasOwnProperty.call(counts, g.groupId)) {
      throw new Error('doctorCountByGroup is missing required group "' + g.groupId + '".');
    }
    var n = counts[g.groupId];
    if (typeof n !== 'number' || !isFinite(n) || n < 0 || Math.floor(n) !== n) {
      throw new Error('doctorCountByGroup["' + g.groupId +
        '"] must be a non-negative integer (got ' + JSON.stringify(n) + ').');
    }
  }
}

function buildSpreadsheetName_(normalized) {
  return 'CGH ICU/HD Roster ' + normalized.periodStartDate + ' - ' + normalized.periodEndDate;
}

function buildVersionedTabName_(now) {
  var tz = Session.getScriptTimeZone() || 'Asia/Singapore';
  return 'v' + Utilities.formatDate(now, tz, 'MMddHHmmss');
}
