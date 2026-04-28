// CallPointAutoFill.gs
//
// FW-0024 — auto-repopulate empty per-day call-point cells on the
// operator-facing request-entry sheet.
//
// Architecture per `docs/parser_normalizer_contract.md` §9 + scoring
// overlay rule (D-0037): blank call-point cells fall back to the
// template default at parse time, so they're sign-correct without any
// auto-fill behavior. The UX gap this module closes is purely visual:
// an operator who clears a cell to "reset to default" sees a blank cell
// that visually reads as "no point / zero / inapplicable" — wrong, since
// the parser will treat it as the template default.
//
// FW-0024 closes this by: at sheet generation time, recording the
// call-point row layout per request-entry sheet name (DocumentProperties
// JSON blob); at edit time, the simple `onEdit(e)` trigger detects
// edits inside the call-point row block and re-fills cleared cells with
// the day-of-week-appropriate template default. Operator-supplied
// numeric values are preserved untouched.
//
// Why DocumentProperties (not DeveloperMetadata) — DocumentProperties
// gives us a single keyed lookup per sheet name, fast to read at edit
// time without iterating cell metadata. DeveloperMetadata would also
// work but adds per-cell overhead the trigger doesn't need.

var CALL_POINT_METADATA_PROPERTY_PREFIX_ = 'rosterMonster:callPointMetadata:';

// Persist call-point row layout for a freshly-generated request-entry
// sheet. Read by `onEdit` at each edit to find call-point cells and
// compute the right default.
//
// Schema (JSON-serialized):
//   {
//     "dateRow": <int>,                  // 1-indexed sheet row holding ISO dates
//     "firstDateCol": <int>,             // 1-indexed first date column
//     "lastDateCol": <int>,              // 1-indexed last date column (inclusive)
//     "callPointRows": [
//       {
//         "row": <int>,                  // 1-indexed sheet row of this call-point row
//         "rowKey": <string>,            // template-declared rowKey (e.g. "MICU_CALL_POINT")
//         "slotType": <string>,          // template-declared slotType binding (D-0037)
//         "defaultRule": {
//           "weekdayToWeekday": <number>,
//           "weekdayToWeekendOrPublicHoliday": <number>,
//           "weekendOrPublicHolidayToWeekendOrPublicHoliday": <number>,
//           "weekendOrPublicHolidayToWeekday": <number>
//         }
//       },
//       ...
//     ]
//   }
function saveCallPointMetadata_(requestSheetName, template, layoutInfo) {
  var rowsByKey = {};
  for (var i = 0; i < template.inputSheetLayout.pointRows.length; i++) {
    var pr = template.inputSheetLayout.pointRows[i];
    rowsByKey[pr.rowKey] = pr;
  }
  var callPointRows = [];
  for (var j = 0; j < layoutInfo.pointRowRanges.length; j++) {
    var range = layoutInfo.pointRowRanges[j];
    var templateRow = rowsByKey[range.rowKey];
    if (!templateRow) {
      // Layout produced a row whose rowKey isn't in template — would be
      // a generator-internal defect; surface rather than silently miss
      // it. The trigger would simply not refill these cells.
      throw new Error(
        'Layout pointRowRanges entry references rowKey "' + range.rowKey +
        '" not present in template.inputSheetLayout.pointRows; cannot ' +
        'persist FW-0024 metadata.'
      );
    }
    callPointRows.push({
      row: range.row,
      rowKey: range.rowKey,
      slotType: templateRow.slotType,
      defaultRule: {
        weekdayToWeekday: templateRow.defaultRule.weekdayToWeekday,
        weekdayToWeekendOrPublicHoliday:
          templateRow.defaultRule.weekdayToWeekendOrPublicHoliday,
        weekendOrPublicHolidayToWeekendOrPublicHoliday:
          templateRow.defaultRule.weekendOrPublicHolidayToWeekendOrPublicHoliday,
        weekendOrPublicHolidayToWeekday:
          templateRow.defaultRule.weekendOrPublicHolidayToWeekday,
      },
    });
  }
  var payload = {
    dateRow: layoutInfo.dateRow,
    firstDateCol: layoutInfo.firstDateCol,
    lastDateCol: layoutInfo.lastDateCol,
    callPointRows: callPointRows,
  };
  PropertiesService.getDocumentProperties().setProperty(
    CALL_POINT_METADATA_PROPERTY_PREFIX_ + requestSheetName,
    JSON.stringify(payload)
  );
}

function _loadCallPointMetadata_(sheetName) {
  var raw = PropertiesService.getDocumentProperties().getProperty(
    CALL_POINT_METADATA_PROPERTY_PREFIX_ + sheetName
  );
  if (raw === null) return null;
  try {
    return JSON.parse(raw);
  } catch (e) {
    // Corrupted property — surface to operator via the auto-fill being
    // a no-op rather than crashing the trigger.
    return null;
  }
}

// Simple `onEdit(e)` trigger — auto-installed by Apps Script for any
// function with this name. Fires on every cell edit; we filter by sheet
// name + row + column + value to find clear-edits on call-point cells.
//
// Trigger limitations to keep in mind:
//   - Simple triggers run with limited authorization scope; they can
//     modify the active spreadsheet but cannot make external API calls.
//   - They run synchronously after each edit; keep the work small.
//   - Cleared cells deliver `e.value === undefined` (NOT empty string).
//     A typed empty string also counts as "blank" per the parser overlay
//     rule, so we treat both cases the same way.
//
// Behavior: if the edited cell sits inside the call-point row block AND
// is now blank, write the template default for that day-of-week into
// the cell. Otherwise no-op (fast return; trigger is best-effort).
function onEdit(e) {
  // Defensive: this function is auto-invoked by Apps Script. A bad event
  // shape would be a platform regression — early-return rather than
  // crash a presumed-no-op trigger.
  if (!e || !e.range) return;

  var range = e.range;
  if (range.getNumRows() !== 1 || range.getNumColumns() !== 1) {
    // Operator pasted a multi-cell block; out of scope for first-release
    // FW-0024 — single-cell clear-edits are the documented use case.
    return;
  }

  var newValue = range.getValue();
  if (newValue !== '' && newValue !== null && newValue !== undefined) {
    // Operator typed something; nothing to refill.
    return;
  }

  var sheet = range.getSheet();
  var metadata = _loadCallPointMetadata_(sheet.getName());
  if (!metadata) return;  // Tab not generated by this launcher; skip.

  var editedRow = range.getRow();
  var editedCol = range.getColumn();
  if (editedCol < metadata.firstDateCol || editedCol > metadata.lastDateCol) {
    return;  // Edit is outside the day-axis columns.
  }

  var matchingRow = null;
  for (var i = 0; i < metadata.callPointRows.length; i++) {
    if (metadata.callPointRows[i].row === editedRow) {
      matchingRow = metadata.callPointRows[i];
      break;
    }
  }
  if (!matchingRow) return;  // Edit isn't in a call-point row.

  // Look up the date for this column from the day-axis row. Cell may
  // hold a Date object (most common) or an ISO string fallback; handle
  // both. If the value isn't parseable, skip — the trigger refuses to
  // guess at a default rather than write something wrong.
  var headerCell = sheet.getRange(metadata.dateRow, editedCol).getValue();
  var headerDate = _coerceCellToDate_(headerCell);
  if (!headerDate) return;

  var defaultValue = computeDefaultCallPoint_(headerDate, matchingRow.defaultRule);
  range.setValue(defaultValue);
}

// Best-effort coercion of a date-axis header cell value to a JS Date.
// The launcher writes Date objects (via setValues with day.date), but
// Apps Script may roundtrip those as strings depending on cell formatting.
function _coerceCellToDate_(cellValue) {
  if (cellValue instanceof Date) return cellValue;
  if (typeof cellValue === 'string') {
    // Try ISO format first; fall back to Date constructor.
    var s = cellValue.trim();
    if (!s) return null;
    var parsed = new Date(s);
    if (!isNaN(parsed.getTime())) return parsed;
  }
  return null;
}
