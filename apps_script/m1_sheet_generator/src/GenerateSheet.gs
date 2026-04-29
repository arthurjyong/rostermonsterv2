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
  // Per `docs/decision_log.md` D-0041: copy the bound-template spreadsheet so
  // every operator sheet inherits the bound shim + central library dependency.
  // Falls back to the legacy `SpreadsheetApp.create()` path only if no template
  // is configured (clear setup error rather than silent regression).
  var ss = createSpreadsheetFromTemplate_(spreadsheetName);
  var tabName = buildVersionedTabName_(new Date());
  var runId = tabName; // tabName IS the runId per `docs/sheet_generation_contract.md` §11A
  var sheet = ss.getActiveSheet();
  sheet.setName(tabName);

  // Drop any tabs the template carries beyond the active one (e.g., placeholder
  // sheets from manual template setup). Keeps the post-generation surface clean.
  removeNonActiveSheets_(ss, sheet);

  var layoutInfo = buildLayout_(sheet, template, dateRange, normalized.doctorCountByGroup);
  applyValidations_(sheet, layoutInfo);
  applyProtections_(sheet, layoutInfo);

  // Per `docs/sheet_generation_contract.md` §11B + D-0043 sub-decision 1:
  // attach launcher-side DeveloperMetadata anchors at the request-entry sheet
  // level so the snapshot extractor can locate per-tab identity, period
  // identity, and expected cardinalities for the §6 completeness validation.
  attachRequestEntrySheetLevelMetadata_(sheet, template, runId,
    normalized.doctorCountByGroup, dateRange.length);

  // Generate the paired Scorer Config tab per
  // `docs/sheet_generation_contract.md` §11A (D-0037). Operator-editable
  // weight cells pre-populated from template.scoring.componentWeights;
  // tab name shares the request-entry tab's version suffix so the snapshot
  // extractor can match the two by `runId`.
  var scorerConfigInfo = buildScorerConfigTab_(ss, sheet.getName(), template);

  var shareResult = tryAutoShareAnyoneWithLink_(ss.getId());

  return {
    mode: 'NEW_SPREADSHEET',
    spreadsheetId: ss.getId(),
    spreadsheetUrl: ss.getUrl(),
    spreadsheetName: ss.getName(),
    sheetName: sheet.getName(),
    scorerConfigSheetName: scorerConfigInfo.tabName,
    periodStartDate: normalized.periodStartDate,
    periodEndDate: normalized.periodEndDate,
    doctorCountByGroup: normalized.doctorCountByGroup,
    autoShared: shareResult.ok,
    autoShareError: shareResult.ok ? null : shareResult.reason,
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
  var runId = tabName; // tabName IS the runId per §11A
  var layoutInfo = buildLayout_(sheet, template, dateRange, normalized.doctorCountByGroup);
  applyValidations_(sheet, layoutInfo);
  applyProtections_(sheet, layoutInfo);

  // Existing-spreadsheet path: per D-0041 sub-decision 8, the resulting tab
  // does NOT receive the bound shim (no in-sheet menu, no operator-driven
  // extraction). Per-row + sheet-level DeveloperMetadata is still attached so
  // the surface remains structurally extractor-ready if a maintainer-driven
  // path is wired in the future.
  attachRequestEntrySheetLevelMetadata_(sheet, template, runId,
    normalized.doctorCountByGroup, dateRange.length);

  // Same Scorer Config tab generation as the new-spreadsheet path. The
  // tab name shares the version suffix of THIS request-entry tab, so
  // multi-period spreadsheets keep each (request-entry, scorer-config)
  // pair grouped by suffix.
  var scorerConfigInfo = buildScorerConfigTab_(ss, sheet.getName(), template);

  return {
    mode: 'EXISTING_SPREADSHEET',
    spreadsheetId: ss.getId(),
    spreadsheetUrl: ss.getUrl(),
    spreadsheetName: ss.getName(),
    sheetName: sheet.getName(),
    scorerConfigSheetName: scorerConfigInfo.tabName,
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
    var rawReference = (config.spreadsheetId == null ? '' : String(config.spreadsheetId)).trim();
    if (!rawReference) {
      throw new Error('Existing-spreadsheet mode requires a non-empty spreadsheetId.');
    }
    spreadsheetId = extractSpreadsheetId_(rawReference);
  }

  return {
    department: department,
    periodStartDate: start,
    periodEndDate: end,
    doctorCountByGroup: counts,
    spreadsheetId: spreadsheetId,
  };
}

// Normalize an operator-supplied spreadsheet reference to a bare spreadsheet ID.
// Accepts either a bare ID or a full Google Sheets URL, per
// docs/sheet_generation_contract.md §12.5. The caller has already trimmed the
// value and ruled out the empty-string case.
function extractSpreadsheetId_(value) {
  var urlMatch = value.match(/https?:\/\/docs\.google\.com\/spreadsheets\/(?:u\/\d+\/)?d\/([a-zA-Z0-9_-]{20,})/);
  if (urlMatch) {
    return urlMatch[1];
  }
  if (/^[a-zA-Z0-9_-]{20,}$/.test(value)) {
    return value;
  }
  throw new Error(
    'Could not recognize spreadsheet reference — paste the full link from the browser bar, or the spreadsheet ID.'
  );
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
  return 'CGH ICU/HD Roster ' + normalized.periodStartDate + ' to ' + normalized.periodEndDate;
}

function buildVersionedTabName_(now) {
  var tz = Session.getScriptTimeZone() || 'Asia/Singapore';
  return 'v' + Utilities.formatDate(now, tz, 'MMddHHmmss');
}

// Attempts to flip the newly-created spreadsheet to anyone-with-link = Editor
// via the Drive Advanced Service (REST v3). Uses the narrower `drive.file`
// scope, which covers files the app itself just created — unlike
// `DriveApp.setSharing`, which forces the restricted full `drive` scope.
// Returns { ok: true } on success; swallows the error and returns
// { ok: false, reason: <message> } on failure so the sheet still renders
// with a truthful hint on the success page.
function tryAutoShareAnyoneWithLink_(fileId) {
  try {
    Drive.Permissions.create({ type: 'anyone', role: 'writer' }, fileId);
    return { ok: true };
  } catch (e) {
    var message = (e && e.message) ? e.message : String(e);
    Logger.log('Auto-share failed: ' + message);
    return { ok: false, reason: message };
  }
}

// Per `docs/decision_log.md` D-0041 sub-decision 4: every operator sheet must
// inherit the bound shim attached to the maintainer-owned template
// spreadsheet. Replaces `SpreadsheetApp.create()` so simple onOpen / onEdit
// triggers fire on each generated sheet (the architectural gap that reverted
// FW-0024 in PR #89).
//
// Reads `TEMPLATE_FILE_ID` from Script Properties — set once during M2 C9
// one-time setup per `docs/snapshot_adapter_contract.md` §3 step 5.
//
// OAuth-scope requirement: `auth/drive` is required because `getFileById`
// against a file the app did NOT create cannot piggyback on `drive.file`.
// The launcher manifest declares the broader scope per D-0041 sub-decision 4.
function createSpreadsheetFromTemplate_(spreadsheetName) {
  var props = PropertiesService.getScriptProperties();
  var templateId = props.getProperty('TEMPLATE_FILE_ID');
  if (!templateId) {
    throw new Error(
      'Script Property TEMPLATE_FILE_ID is not set. Complete the one-time ' +
      'setup steps in docs/snapshot_adapter_contract.md §3 (create the ' +
      '[INTERNAL] Roster Monster Template spreadsheet and record its File ID).'
    );
  }
  var copy;
  try {
    copy = DriveApp.getFileById(templateId).makeCopy(spreadsheetName);
  } catch (e) {
    var msg = (e && e.message) ? e.message : String(e);
    throw new Error(
      'Could not copy template (TEMPLATE_FILE_ID=' + templateId + '): ' + msg +
      '. Verify the operator account has Drive Viewer access to the template ' +
      'per docs/decision_log.md D-0041 sub-decision 4 + setup step (a).'
    );
  }
  return SpreadsheetApp.openById(copy.getId());
}

// Drop any tabs the template carries beyond the active sheet. Manual template
// setup (Extensions → Apps Script bound shim creation) often leaves a default
// "Sheet1" plus the bound shim's own associated sheet; we want each generated
// spreadsheet to start with exactly the active sheet that buildLayout_ will
// populate. Skips the active sheet itself.
function removeNonActiveSheets_(ss, keepSheet) {
  var keepGid = keepSheet.getSheetId();
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() !== keepGid) {
      ss.deleteSheet(sheets[i]);
    }
  }
}

// Per `docs/sheet_generation_contract.md` §11B + `docs/decision_log.md` D-0043
// sub-decision 1: attach DeveloperMetadata at the sheet level so the snapshot
// extractor (`docs/snapshot_adapter_contract.md` §6) can identify the active
// request-entry tab, pair it with its Scorer Config tab via `runId`, and run
// the per-anchor cardinality validation (D-0043 sub-decision 3).
function attachRequestEntrySheetLevelMetadata_(sheet, template, runId,
                                                doctorCountByGroup, dayCount) {
  sheet.addDeveloperMetadata('rosterMonster:tabType', 'requestEntry');
  sheet.addDeveloperMetadata('rosterMonster:templateVersion',
    String(template.templateVersion || 'unknown'));
  sheet.addDeveloperMetadata('rosterMonster:runId', String(runId));

  // Expected-cardinality anchors driving D-0043 sub-decision 3.
  var sections = template.inputSheetLayout.sections;
  for (var s = 0; s < sections.length; s++) {
    var sec = sections[s];
    var n = doctorCountByGroup[sec.groupId] | 0;
    sheet.addDeveloperMetadata(
      'rosterMonster:expectedDoctorCount.' + sec.sectionKey,
      String(n));
  }
  sheet.addDeveloperMetadata('rosterMonster:expectedDayCount', String(dayCount));
}
