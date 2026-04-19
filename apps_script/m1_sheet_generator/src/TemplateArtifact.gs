// TemplateArtifact.gs
// First-release ICU/HD department template artifact as a committed runtime constant.
// Shape follows docs/template_artifact_contract.md (section 4+ required sections).
// Top-level `var` so it is visible from other .gs files under the V8 runtime.

var ICU_HD_TEMPLATE_ARTIFACT = Object.freeze({
  identity: Object.freeze({
    templateId: 'cgh_icu_hd',
    templateVersion: 1,
    label: 'CGH ICU/HD Call',
  }),

  slots: Object.freeze([
    Object.freeze({ slotId: 'MICU_CALL',    label: 'MICU Call',    slotFamily: 'MICU', slotKind: 'CALL',    requiredCountPerDay: 1 }),
    Object.freeze({ slotId: 'MICU_STANDBY', label: 'MICU Standby', slotFamily: 'MICU', slotKind: 'STANDBY', requiredCountPerDay: 1 }),
    Object.freeze({ slotId: 'MHD_CALL',     label: 'MHD Call',     slotFamily: 'MHD',  slotKind: 'CALL',    requiredCountPerDay: 1 }),
    Object.freeze({ slotId: 'MHD_STANDBY',  label: 'MHD Standby',  slotFamily: 'MHD',  slotKind: 'STANDBY', requiredCountPerDay: 1 }),
  ]),

  doctorGroups: Object.freeze([
    Object.freeze({ groupId: 'ICU_ONLY', label: 'ICU only' }),
    Object.freeze({ groupId: 'ICU_HD',   label: 'ICU + HD' }),
    Object.freeze({ groupId: 'HD_ONLY',  label: 'HD only' }),
  ]),

  eligibility: Object.freeze([
    Object.freeze({ slotId: 'MICU_CALL',    eligibleGroups: Object.freeze(['ICU_ONLY', 'ICU_HD']) }),
    Object.freeze({ slotId: 'MICU_STANDBY', eligibleGroups: Object.freeze(['ICU_ONLY', 'ICU_HD']) }),
    Object.freeze({ slotId: 'MHD_CALL',     eligibleGroups: Object.freeze(['ICU_HD', 'HD_ONLY']) }),
    Object.freeze({ slotId: 'MHD_STANDBY',  eligibleGroups: Object.freeze(['ICU_HD', 'HD_ONLY']) }),
  ]),

  requestSemanticsBinding: Object.freeze({
    contractId: 'ICU_HD_REQUEST_SEMANTICS',
    contractVersion: 1,
  }),

  inputSheetLayout: Object.freeze({
    sheetName: 'CGH ICU/HD Call',
    headerBlock: Object.freeze({ title: 'CGH ICU/HD Call' }),
    visibleLabels: Object.freeze({ departmentLabel: 'CGH ICU/HD Call' }),
    dayAxis: Object.freeze({ anchorCell: 'B3', direction: 'horizontal' }),
    sections: Object.freeze([
      Object.freeze({
        sectionKey: 'MICU',
        groupId: 'ICU_ONLY',
        headerLabel: 'MICU',
        placement: Object.freeze({ anchorMode: 'belowBlock', blockRef: 'dayAxis' }),
        doctorRows: Object.freeze({ nameColumn: 'A', requestStartColumn: 'B' }),
      }),
      Object.freeze({
        sectionKey: 'MICU_HD',
        groupId: 'ICU_HD',
        headerLabel: 'ICU + HD',
        placement: Object.freeze({ anchorMode: 'belowBlock', blockRef: 'dayAxis' }),
        doctorRows: Object.freeze({ nameColumn: 'A', requestStartColumn: 'B' }),
      }),
      Object.freeze({
        sectionKey: 'MHD',
        groupId: 'HD_ONLY',
        headerLabel: 'MHD',
        placement: Object.freeze({ anchorMode: 'belowBlock', blockRef: 'dayAxis' }),
        doctorRows: Object.freeze({ nameColumn: 'A', requestStartColumn: 'B' }),
      }),
    ]),
    pointRows: Object.freeze([
      Object.freeze({
        rowKey: 'MICU_CALL_POINT',
        label: 'MICU Call Point',
        defaultRule: Object.freeze({
          weekdayToWeekday: 1,
          weekdayToWeekendOrPublicHoliday: 1.75,
          weekendOrPublicHolidayToWeekendOrPublicHoliday: 2,
          weekendOrPublicHolidayToWeekday: 1.5,
        }),
      }),
      Object.freeze({
        rowKey: 'MHD_CALL_POINT',
        label: 'MHD Call Point',
        defaultRule: Object.freeze({
          weekdayToWeekday: 1,
          weekdayToWeekendOrPublicHoliday: 1.75,
          weekendOrPublicHolidayToWeekendOrPublicHoliday: 2,
          weekendOrPublicHolidayToWeekday: 1.5,
        }),
      }),
    ]),
    legendBlock: Object.freeze({
      present: true,
      descriptionsHeading: 'Descriptions',
      descriptions: Object.freeze([
        'CR — Call Request',
        'NC — No Call / Call Block',
        'AL — Annual Leave',
        'TL — Training Leave',
        'SL or MC — Sick Leave / Medical Leave',
        'HL — Hospitalisation Leave',
        'NSL — National Service Leave',
        'OPL — Other Planned Leave',
        'EMCC — ED PM Training',
        'PM_OFF — PM Off',
        'EXAM — Exam day',
      ]),
      notesHeading: 'Roster Notes / FAQ',
      notes: Object.freeze([
        '1. Call points are currently experimental and remain subject to approval by the consultants / bosses. The current call weightage is not final.',
        '2. Please combine multiple requests using ", " (comma + space). Example: CR, EMCC',
        '3. By default, calls will be blocked on leave days, on the day before leave, and on any PM off (e.g. EMCC, PM_OFF), unless a call request has been made.',
      ]),
    }),
    surfaceOwnership: Object.freeze({
      operatorInput: Object.freeze([
        'doctorNameCells',
        'requestEntryCells',
        'callPointCells',
        'lowerShellAssignmentCells',
      ]),
      templateOwnedStructural: Object.freeze([
        'titleAndDepartmentHeader',
        'dayAxis',
        'weekdayRow',
        'sectionHeaders',
        'sectionRowStructure',
        'pointRowLabels',
        'lowerShellAssignmentRowLabels',
        'legendBlock',
      ]),
    }),
  }),

  outputMapping: Object.freeze({
    surfaces: Object.freeze([
      Object.freeze({
        surfaceId: 'lowerRosterAssignments',
        surfaceRole: 'LOWER_ROSTER_ASSIGNMENTS',
        sheetName: 'CGH ICU/HD Call',
        // anchorCell is a declarative reference; concrete coordinates are computed by
        // the generator based on doctorCountByGroup at generation time.
        anchorCell: 'B4',
        orientation: 'dateByColumn',
        operatorPrefill: 'allowed',
        assignmentRows: Object.freeze([
          Object.freeze({ slotId: 'MICU_CALL',    rowOffset: 0 }),
          Object.freeze({ slotId: 'MICU_STANDBY', rowOffset: 1 }),
          Object.freeze({ slotId: 'MHD_CALL',     rowOffset: 2 }),
          Object.freeze({ slotId: 'MHD_STANDBY',  rowOffset: 3 }),
        ]),
      }),
    ]),
  }),

  scoring: Object.freeze({
    templateKnobs: Object.freeze([]),
  }),
});
