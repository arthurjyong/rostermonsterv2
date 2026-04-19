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

  // ---- Row 1: title ----
  var titleRange = sheet.getRange(1, 1, 1, totalCols);
  titleRange.merge();
  var titleText =
    template.inputSheetLayout.headerBlock.title +
    '   (' + dateRange[0].isoDate + ' – ' + dateRange[numDays - 1].isoDate + ')';
  titleRange.setValue(titleText)
    .setFontWeight('bold')
    .setFontSize(14)
    .setHorizontalAlignment('center')
    .setBackground(LAYOUT_COLORS_.titleBg)
    .setFontColor(LAYOUT_COLORS_.titleFg);

  // ---- Row 2: department label ----
  var deptRange = sheet.getRange(2, 1, 1, totalCols);
  deptRange.merge();
  deptRange.setValue(template.inputSheetLayout.visibleLabels.departmentLabel)
    .setFontStyle('italic')
    .setHorizontalAlignment('center')
    .setBackground(LAYOUT_COLORS_.headerRowBg);

  // ---- Row 3: date axis ----
  var dateRow = 3;
  sheet.getRange(dateRow, nameCol).setValue('Date')
    .setFontWeight('bold')
    .setBackground(LAYOUT_COLORS_.headerRowBg);
  var dateValues = [dateRange.map(function (d) { return d.isoDate; })];
  sheet.getRange(dateRow, firstDateCol, 1, numDays)
    .setValues(dateValues)
    .setFontWeight('bold')
    .setHorizontalAlignment('center')
    .setBackground(LAYOUT_COLORS_.headerRowBg);

  // ---- Row 4: weekday row ----
  var weekdayRow = 4;
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

  for (var s = 0; s < sections.length; s++) {
    var sec = sections[s];
    var rawCount = doctorCountByGroup[sec.groupId];
    var count = rawCount | 0;

    var headerRange = sheet.getRange(currentRow, 1, 1, totalCols);
    headerRange.merge();
    headerRange.setValue(sec.headerLabel + '  (' + sec.groupId + ')')
      .setFontWeight('bold')
      .setBackground(LAYOUT_COLORS_.sectionBg)
      .setHorizontalAlignment('left');
    var sectionHeaderRow = currentRow;
    currentRow++;

    var firstDoctorRow = currentRow;
    for (var d = 0; d < count; d++) {
      doctorRowNumbers.push(currentRow);
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
    currentRow++;
  }

  // spacer row
  currentRow++;

  // ---- Lower roster / output shell header ----
  var lowerHeaderRange = sheet.getRange(currentRow, 1, 1, totalCols);
  lowerHeaderRange.merge();
  lowerHeaderRange.setValue('Roster / Assignments')
    .setFontWeight('bold')
    .setBackground(LAYOUT_COLORS_.lowerBg)
    .setHorizontalAlignment('left');
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

  // ---- Legend / Descriptions ----
  var legendStartRow = null;
  var legendEndRow = null;
  if (template.inputSheetLayout.legendBlock && template.inputSheetLayout.legendBlock.present) {
    legendStartRow = currentRow;
    var legendHeader = sheet.getRange(currentRow, 1, 1, totalCols);
    legendHeader.merge();
    legendHeader.setValue('Descriptions')
      .setFontWeight('bold')
      .setBackground(LAYOUT_COLORS_.headerRowBg);
    currentRow++;

    var lines = template.inputSheetLayout.legendBlock.contentLines;
    for (var l = 0; l < lines.length; l++) {
      var lineRange = sheet.getRange(currentRow, 1, 1, totalCols);
      lineRange.merge();
      lineRange.setValue(lines[l]);
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

  // ---- Column widths / frozen panes ----
  sheet.setColumnWidth(nameCol, 200);
  for (var i = 0; i < numDays; i++) {
    sheet.setColumnWidth(firstDateCol + i, 58);
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
    deptRow: 2,
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
  var legendRowCount = (legend && legend.present && legend.contentLines)
    ? 1 + legend.contentLines.length
    : 0;
  return (
    2 /* title + dept */ +
    2 /* date + weekday */ +
    sections.length + doctorRowsTotal +
    pointRowCount +
    1 /* spacer */ + 1 /* lower header */ + lowerRowCount +
    1 /* spacer */ + legendRowCount
  );
}
