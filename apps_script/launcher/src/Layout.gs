// Layout.gs
// Structural sheet generation for the first-release ICU/HD request sheet shell.
// Produces the required surfaces from docs/sheet_generation_contract.md section 5:
//   title/header block, date axis, weekday row, section headers, placeholder doctor
//   rows, request-entry cells, point rows, lower roster/output shell rows, legend,
//   and weekend/public-holiday highlighting.
// Returns a layoutInfo descriptor that ProtectionAndValidation.gs consumes.

var LAYOUT_COLORS_ = Object.freeze({
  titleBg:      '#1f4e78',
  titleFg:      '#ffffff',
  sectionBg:    '#d9d9d9',
  pointBg:      '#fff2cc',
  lowerBg:      '#c6e0b4',
  wephBg:       '#fce5cd',
  headerRowBg:  '#e7e6e6',
});

// Attach DeveloperMetadata to a single sheet row using A1 row notation. The
// Sheets API rejects "arbitrary range" scopes (e.g., partial-row ranges built
// via getRange(row, col, 1, n)), so per the M2 C7 PR #90 hotfix lesson
// recorded in `docs/decision_log.md` D-0043 sub-decision 1 + the inline
// comment in `ScorerConfigTab.gs`, all per-row anchors MUST be installed via
// the `<rowNum>:<rowNum>` row-scoped form.
function attachRowMetadata_(sheet, rowNum, key, value) {
  sheet.getRange(rowNum + ':' + rowNum).addDeveloperMetadata(key, String(value));
}

function buildLayout_(sheet, template, dateRange, doctorCountByGroup) {
  var numDays = dateRange.length;
  if (numDays < 1) {
    throw new Error('Empty date range — expected at least one day.');
  }
  var nameCol = 1;                       // column A
  var firstDateCol = 2;                  // column B
  var lastDateCol = firstDateCol + numDays - 1;
  var totalCols = lastDateCol;

  // Pre-expand the sheet so later getRange calls never run off the default grid
  // (a freshly created spreadsheet starts at 26 columns / 1000 rows).
  var estimatedRows = estimateTotalRows_(template, doctorCountByGroup);
  var curMaxCols = sheet.getMaxColumns();
  if (curMaxCols < totalCols) {
    sheet.insertColumnsAfter(curMaxCols, totalCols - curMaxCols);
  }
  var curMaxRows = sheet.getMaxRows();
  if (curMaxRows < estimatedRows) {
    sheet.insertRowsAfter(curMaxRows, estimatedRows - curMaxRows);
  }

  sheet.clear();
  sheet.clearNotes();

  // Decorative rows use no merges. Text in column A overflows into empty cells
  // to the right, producing the same visual banner without a merged range. This
  // keeps column A clear of merges so setFrozenColumns(nameCol) below does not
  // hit the "can't freeze columns which contain only part of a merged cell"
  // restriction. The department label is carried in the title prefix (per the
  // template's headerBlock.title), so no dedicated dept row is needed.

  // ---- Row 1: title (department name is the prefix of this title) ----
  var titleText =
    template.inputSheetLayout.headerBlock.title +
    '   (' + dateRange[0].isoDate + ' – ' + dateRange[numDays - 1].isoDate + ')';
  sheet.getRange(1, nameCol).setValue(titleText)
    .setFontWeight('bold')
    .setFontSize(14)
    .setFontColor(LAYOUT_COLORS_.titleFg);
  sheet.getRange(1, nameCol, 1, totalCols).setBackground(LAYOUT_COLORS_.titleBg);

  // ---- Row 2: date axis ----
  var dateRow = 2;
  sheet.getRange(dateRow, nameCol).setValue('Date')
    .setFontWeight('bold')
    .setBackground(LAYOUT_COLORS_.headerRowBg);
  var dateValues = [dateRange.map(function (d) { return d.isoDate; })];
  sheet.getRange(dateRow, firstDateCol, 1, numDays)
    .setValues(dateValues)
    .setFontWeight('bold')
    .setHorizontalAlignment('center')
    .setBackground(LAYOUT_COLORS_.headerRowBg);
  // D-0043 sub-decision 1 + sheet_generation_contract §11B: anchor the day-
  // axis row so the snapshot extractor can locate it via sheet-scoped
  // DeveloperMetadata finder. A1 row notation per the M2 C7 pattern in
  // `ScorerConfigTab.gs` — the API rejects arbitrary range scopes.
  attachRowMetadata_(sheet, dateRow, 'rosterMonster:dayAxis', 'true');

  // ---- Row 3: weekday row ----
  var weekdayRow = 3;
  sheet.getRange(weekdayRow, nameCol).setValue('Day')
    .setFontWeight('bold')
    .setBackground(LAYOUT_COLORS_.headerRowBg);
  var weekdayValues = [dateRange.map(function (d) { return d.weekdayLabel; })];
  sheet.getRange(weekdayRow, firstDateCol, 1, numDays)
    .setValues(weekdayValues)
    .setFontWeight('bold')
    .setHorizontalAlignment('center')
    .setBackground(LAYOUT_COLORS_.headerRowBg);

  // ---- Doctor sections ----
  var currentRow = weekdayRow + 1;
  var sections = template.inputSheetLayout.sections;
  var sectionInfos = [];
  var doctorNameRanges = [];
  var requestEntryRanges = [];
  var doctorRowNumbers = [];
  // Rows with a deliberate full-width banner color. Re-applied after weekend/PH
  // shading so the structural row color wins over the column-wise weekend paint.
  var bandedRows = [];

  for (var s = 0; s < sections.length; s++) {
    var sec = sections[s];
    var rawCount = doctorCountByGroup[sec.groupId];
    var count = rawCount | 0;

    sheet.getRange(currentRow, nameCol)
      .setValue(sec.headerLabel + '  (' + sec.groupId + ')')
      .setFontWeight('bold');
    sheet.getRange(currentRow, nameCol, 1, totalCols)
      .setBackground(LAYOUT_COLORS_.sectionBg);
    var sectionHeaderRow = currentRow;
    bandedRows.push({ row: sectionHeaderRow, bg: LAYOUT_COLORS_.sectionBg });
    // D-0043 sub-decision 1: section header row anchor.
    attachRowMetadata_(sheet, sectionHeaderRow, 'rosterMonster:section', sec.sectionKey);
    currentRow++;

    var firstDoctorRow = currentRow;
    for (var d = 0; d < count; d++) {
      doctorRowNumbers.push(currentRow);
      // D-0043 sub-decision 1: per-doctor row anchor with `<sectionKey>:<idx>`
      // value drives the snapshot extractor's per-section cardinality
      // validation against `expectedDoctorCount.<sectionKey>` (D-0043 §3).
      attachRowMetadata_(sheet, currentRow, 'rosterMonster:doctorRow',
        sec.sectionKey + ':' + d);
      currentRow++;
    }
    var lastDoctorRow = currentRow - 1;

    sectionInfos.push({
      sectionKey: sec.sectionKey,
      groupId: sec.groupId,
      headerRow: sectionHeaderRow,
      firstDoctorRow: firstDoctorRow,
      lastDoctorRow: lastDoctorRow,
      count: count,
    });
    if (count > 0) {
      doctorNameRanges.push({ row: firstDoctorRow, col: nameCol,       numRows: count, numCols: 1 });
      requestEntryRanges.push({ row: firstDoctorRow, col: firstDateCol, numRows: count, numCols: numDays });
    }

    // Blank separator row after each doctor group (requested: one blank line
    // after ICU only, ICU/HD, and HD only, before call-point rows).
    currentRow++;
  }

  // Center-align request-entry cells. Operator feedback: left-aligned
  // short codes (CR, AL, NC, EMCC, …) look ragged against the centered
  // date/weekday/point headers above them.
  for (var r = 0; r < requestEntryRanges.length; r++) {
    var rr = requestEntryRanges[r];
    sheet.getRange(rr.row, rr.col, rr.numRows, rr.numCols)
      .setHorizontalAlignment('center');
  }

  // ---- Point rows (MICU / MHD call point) ----
  var pointRows = template.inputSheetLayout.pointRows;
  var pointRowRanges = [];
  for (var p = 0; p < pointRows.length; p++) {
    var pr = pointRows[p];
    sheet.getRange(currentRow, nameCol).setValue(pr.label)
      .setFontWeight('bold')
      .setBackground(LAYOUT_COLORS_.pointBg);
    var pointValues = [dateRange.map(function (d) {
      return computeDefaultCallPoint_(d.date, pr.defaultRule);
    })];
    sheet.getRange(currentRow, firstDateCol, 1, numDays)
      .setValues(pointValues)
      .setHorizontalAlignment('center')
      .setBackground(LAYOUT_COLORS_.pointBg);
    pointRowRanges.push({
      rowKey: pr.rowKey,
      row: currentRow,
      col: firstDateCol,
      numRows: 1,
      numCols: numDays,
    });
    bandedRows.push({ row: currentRow, bg: LAYOUT_COLORS_.pointBg });
    // D-0043 sub-decision 1: per-call-point-row anchor.
    attachRowMetadata_(sheet, currentRow, 'rosterMonster:callPointRow', pr.rowKey);
    currentRow++;
  }

  // spacer row
  currentRow++;

  // ---- Lower roster / output shell header ----
  sheet.getRange(currentRow, nameCol)
    .setValue('Roster / Assignments')
    .setFontWeight('bold');
  sheet.getRange(currentRow, nameCol, 1, totalCols)
    .setBackground(LAYOUT_COLORS_.lowerBg);
  bandedRows.push({ row: currentRow, bg: LAYOUT_COLORS_.lowerBg });
  currentRow++;

  // ---- Lower roster / output shell assignment rows ----
  var outputSurface = template.outputMapping.surfaces[0];
  var slotById = {};
  for (var si = 0; si < template.slots.length; si++) {
    slotById[template.slots[si].slotId] = template.slots[si];
  }
  var lowerShellAnchorRow = currentRow;
  var lowerShellRanges = [];
  for (var a = 0; a < outputSurface.assignmentRows.length; a++) {
    var ar = outputSurface.assignmentRows[a];
    var row = lowerShellAnchorRow + ar.rowOffset;
    var slotLabel = (slotById[ar.slotId] && slotById[ar.slotId].label) || ar.slotId;
    sheet.getRange(row, nameCol).setValue(slotLabel).setFontWeight('bold');
    // D-0043 sub-decision 1: per-assignment-row anchor with `<surfaceId>:<rowOffset>`
    // value matches the snapshot's outputMapping locator path per
    // `docs/snapshot_contract.md` §10.
    attachRowMetadata_(sheet, row, 'rosterMonster:assignmentRow',
      outputSurface.surfaceId + ':' + ar.rowOffset);
    lowerShellRanges.push({
      slotId: ar.slotId,
      row: row,
      col: firstDateCol,
      numRows: 1,
      numCols: numDays,
    });
  }
  currentRow = lowerShellAnchorRow + outputSurface.assignmentRows.length;

  // spacer row
  currentRow++;

  // ---- Legend / Descriptions + Roster Notes ----
  // No merges anywhere in the legend block. Section headings sit in column A
  // with a row-wide background; content lines sit in column A with text
  // overflow into empty cells to the right.
  var legendStartRow = null;
  var legendEndRow = null;
  if (template.inputSheetLayout.legendBlock && template.inputSheetLayout.legendBlock.present) {
    var lb = template.inputSheetLayout.legendBlock;
    legendStartRow = currentRow;

    sheet.getRange(currentRow, nameCol).setValue(lb.descriptionsHeading).setFontWeight('bold');
    sheet.getRange(currentRow, nameCol, 1, totalCols).setBackground(LAYOUT_COLORS_.headerRowBg);
    bandedRows.push({ row: currentRow, bg: LAYOUT_COLORS_.headerRowBg });
    currentRow++;

    for (var l = 0; l < lb.descriptions.length; l++) {
      sheet.getRange(currentRow, nameCol).setValue(lb.descriptions[l]);
      currentRow++;
    }

    // blank separator between Descriptions and Roster Notes
    currentRow++;

    sheet.getRange(currentRow, nameCol).setValue(lb.notesHeading).setFontWeight('bold');
    sheet.getRange(currentRow, nameCol, 1, totalCols).setBackground(LAYOUT_COLORS_.headerRowBg);
    bandedRows.push({ row: currentRow, bg: LAYOUT_COLORS_.headerRowBg });
    currentRow++;

    for (var n = 0; n < lb.notes.length; n++) {
      sheet.getRange(currentRow, nameCol).setValue(lb.notes[n]);
      currentRow++;
    }
    legendEndRow = currentRow - 1;
  }

  var lastContentRow = currentRow - 1;

  // ---- Weekend/public-holiday highlighting on date-keyed columns ----
  var contentTopRow = dateRow;
  var contentBottomRow = Math.max(
    lastContentRow,
    (pointRowRanges.length ? pointRowRanges[pointRowRanges.length - 1].row : weekdayRow),
    (lowerShellRanges.length ? lowerShellRanges[lowerShellRanges.length - 1].row : weekdayRow));
  for (var i = 0; i < numDays; i++) {
    if (!dateRange[i].isWeph) continue;
    var col = firstDateCol + i;
    sheet.getRange(contentTopRow, col, contentBottomRow - contentTopRow + 1, 1)
      .setBackground(LAYOUT_COLORS_.wephBg);
  }

  // Re-apply banner backgrounds so intentional row colors win over weekend/PH shading.
  for (var b = 0; b < bandedRows.length; b++) {
    sheet.getRange(bandedRows[b].row, nameCol, 1, totalCols)
      .setBackground(bandedRows[b].bg);
  }

  // ---- Column widths / frozen panes ----
  sheet.setColumnWidth(nameCol, 200);
  // Date columns: wide enough to fit the ISO date "YYYY-MM-DD" by default.
  for (var i = 0; i < numDays; i++) {
    sheet.setColumnWidth(firstDateCol + i, 100);
  }
  sheet.setFrozenRows(weekdayRow);
  sheet.setFrozenColumns(nameCol);

  // ---- Trim unused columns/rows so protection semantics are bounded ----
  var maxCols = sheet.getMaxColumns();
  if (maxCols > totalCols) {
    sheet.deleteColumns(totalCols + 1, maxCols - totalCols);
  }
  var maxRows = sheet.getMaxRows();
  if (maxRows > lastContentRow) {
    sheet.deleteRows(lastContentRow + 1, maxRows - lastContentRow);
  }

  return {
    nameCol: nameCol,
    firstDateCol: firstDateCol,
    lastDateCol: lastDateCol,
    totalCols: totalCols,
    lastContentRow: lastContentRow,
    titleRow: 1,
    dateRow: dateRow,
    weekdayRow: weekdayRow,
    sectionInfos: sectionInfos,
    doctorRowNumbers: doctorRowNumbers,
    doctorNameRanges: doctorNameRanges,
    requestEntryRanges: requestEntryRanges,
    pointRowRanges: pointRowRanges,
    lowerShellAnchorRow: lowerShellAnchorRow,
    lowerShellRanges: lowerShellRanges,
    legendStartRow: legendStartRow,
    legendEndRow: legendEndRow,
  };
}

// Pre-build row-count estimate — upper bound on how many rows we are about to
// write. Used only to pre-expand the sheet grid; any unused rows at the tail are
// trimmed after build.
function estimateTotalRows_(template, doctorCountByGroup) {
  var sections = template.inputSheetLayout.sections;
  var doctorRowsTotal = 0;
  for (var s = 0; s < sections.length; s++) {
    doctorRowsTotal += (doctorCountByGroup[sections[s].groupId] | 0);
  }
  var pointRowCount = template.inputSheetLayout.pointRows.length;
  var lowerRowCount = template.outputMapping.surfaces[0].assignmentRows.length;
  var legend = template.inputSheetLayout.legendBlock;
  var legendRowCount = 0;
  if (legend && legend.present) {
    legendRowCount =
      1 /* descriptions heading */ +
      (legend.descriptions ? legend.descriptions.length : 0) +
      1 /* blank separator */ +
      1 /* notes heading */ +
      (legend.notes ? legend.notes.length : 0);
  }
  return (
    1 /* title */ +
    2 /* date + weekday */ +
    sections.length /* section headers */ +
    doctorRowsTotal +
    sections.length /* blank row after each doctor group */ +
    pointRowCount +
    1 /* spacer */ + 1 /* lower header */ + lowerRowCount +
    1 /* spacer */ + legendRowCount
  );
}
