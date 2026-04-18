# Department Template Artifact Contract (Implementation-Facing First Pass)

## 1. Purpose and status
This document defines the **parser-consumable department template artifact** used by v2 for one department’s structural template and operator-facing sheet-shell declarations.

Status in this checkpoint:
- **Implementation-facing first pass**.
- Intended to become **normative quickly** once remaining limited deferrals are closed.
- Realizes `docs/template_contract.md` and does not replace it.

## 2. Boundary and non-goals

### In scope
The artifact covers department structural declarations needed for parser interpretation and future sheet-generation support:
- template identity and structural metadata
- slot definitions
- doctor-group definitions
- group-to-slot eligibility declarations
- request semantics binding surface (narrow)
- input request-form layout contract (`inputSheetLayout`), including template-owned visible labels and section headers used by generation
- output mapping contract (`outputMapping`) for operator-facing lower roster/output shell surfaces
- explicit minimal scoring stub

### Out of scope
This artifact must not redefine or embed:
- snapshot contract shape
- parser-result/output model shape
- request semantics contract details
- solver logic, scorer formulas, or allocator mechanics
- writer procedures or detailed sheet-generation procedures
- whole-sheet presentation/styling details (colors, borders, highlighting cosmetics)
- request-entry validation procedure/mechanics
- protection/locking implementation mechanics

## 3. Artifact posture (settled)
Settled for first release:
- One artifact describes one department structural template.
- Monthly doctor membership and monthly period data are not stored in this artifact.
- The artifact remains declarative.
- ICU/HD first-release structure targets one combined operator-facing sheet shell (not a split request-vs-roster specimen).
- Output mapping is included in the same artifact but remains a separate section from input layout.
- `outputMapping` is the declarative owner of lower roster/output shell structure used by generation, later operator-prefill parsing, and later writeback.
- Shape-level contract is primary; serialization format is secondary.

## 4. Required sections (shape-level)
The artifact must contain these top-level sections:
1. `identity`
2. `slots`
3. `doctorGroups`
4. `eligibility`
5. `requestSemanticsBinding`
6. `inputSheetLayout`
7. `outputMapping`
8. `scoring`

## 5. Slot definitions (settled)
Slots are first-class records.

Each slot record includes:
- `slotId`
- `label`
- `slotFamily`
- `slotKind`
- `requiredCountPerDay`

First-release ICU/HD slot identities:
- `MICU_CALL`
- `MICU_STANDBY`
- `MHD_CALL`
- `MHD_STANDBY`

Minimum explicit slot semantics:
- `slotFamily` (`MICU` or `MHD`)
- `slotKind` (`CALL` or `STANDBY`)
- `requiredCountPerDay` (template-declared fixed per-day demand for this slot within the template version)

## 6. Doctor-group definitions (settled)
Each doctor-group record includes:
- `groupId`
- `label`

First-release ICU/HD group identities:
- `ICU_ONLY`
- `ICU_HD`
- `HD_ONLY`

Settled constraints:
- Group vocabulary is template-owned.
- Monthly membership is external to this artifact.
- First release is group-based and does not include doctor-level override machinery.

## 7. Eligibility (settled)
First-release eligibility is represented as `slot -> groups`.

Settled explicit record-list shape:
- `slotId`
- `eligibleGroups`

Settled constraints:
- No doctor-level override layer in first release.
- Omission means ineligible unless a later settled field explicitly declares otherwise.
- Eligibility must be fully derivable from artifact declarations without hidden parser-side defaults.

## 8. Request semantics binding (narrow, settled)
This section binds template request parsing to the already-settled ICU/HD request semantics contract in `docs/request_semantics_contract.md`.

This section must stay narrow and does not restate:
- raw request tokens
- canonical classes
- machine effects
- propagation rules
- malformed/duplicate handling

Request-driven blocking and preceding-day effects are realized through the bound request semantics contract and are not duplicated in this artifact.

Field shape:
- `contractId`
- `contractVersion`

## 9. `inputSheetLayout` contract (settled)
`inputSheetLayout` declares template-owned generation/parsing surfaces for the operator-facing input shell, while remaining separate from lower-shell mapping in `outputMapping`.

Settled constraints:
- No backward-compatibility requirement for old v1 request form shape.
- v2 may declare a cleaner request-form shape.
- Use named logical blocks plus lightweight relative anchors.
- Do not mix output mapping into this section.
- Do not include generator procedure.
- Use one named request-form sheet in first release.
- Day axis is rule-based, not hardcoded month-span coordinates.
- Visible in-sheet title/header block and department label are template-owned declarations.
- Section model is repeatable section definitions.
- Section header text is explicitly declared per section.
- Section height is variable by doctor count.
- Doctor-row shape is minimal: display name + request cells.
- Point-row presence/labels/default-rule ownership are explicitly template-owned declarations.
- Legend/Descriptions block is template-owned adjunct content and remains non-structural.
- Surface ownership must minimally distinguish operator-input surfaces vs template-owned structural surfaces.
- Tolerate presentation drift, not structural drift.

Field vocabulary:
- `sheetName`
- `dayAxis.anchorCell`
- `dayAxis.direction`
- `sections`
- `sectionKey`
- `groupId`
- `headerLabel`
- `placement.anchorMode`
- `placement.blockRef`
- `doctorRows.nameColumn`
- `doctorRows.requestStartColumn`
- `headerBlock.title`
- `visibleLabels.departmentLabel`
- `pointRows`
- `pointRows[].rowKey`
- `pointRows[].label`
- `pointRows[].defaultRule`
- `legendBlock.present`
- `legendBlock.contentLines`
- `surfaceOwnership.operatorInput`
- `surfaceOwnership.templateOwnedStructural`

Section-based doctor-group derivation (first-release ICU/HD):
- each `inputSheetLayout.sections[]` record must declare canonical `groupId`
- `sectionKey` remains logical extraction/layout identity used to locate the section record
- `sectionKey` is not canonical group meaning by itself
- parser resolves doctor group by locating the declared section via `sectionKey` and reading that section’s canonical `groupId`

Parser-facing intent:
- clean parsing of operator-entered requests
- support first-release generation of the full operator-facing sheet shell, where `inputSheetLayout` declares request-entry regions and `outputMapping` declares lower roster/output shell structure (see `docs/sheet_generation_contract.md`)
- allow operator adjustments to date range and section manpower without contract breakage
- keep legend/Descriptions content outside structural parser dependency

## 10. `outputMapping` contract (settled)
`outputMapping` defines the template-owned operator-facing output shell surfaces, especially the lower roster/output shell that may be generated empty, later partially operator-prefilled, and later targeted for writeback.

Settled constraints:
- Included in the same artifact as a dedicated section.
- Kept separate from `inputSheetLayout`.
- Declarative only.
- Logical mapping plus declared destination surfaces/anchors and first-release lower-shell assignment-row structure.
- Lower roster/output shell surfaces are template-owned structure, not ad hoc writer-only coordinates.
- Declared lower-shell surfaces may be used across generation, later operator-prefill input, and later writeback.
- On surfaces marked `operatorPrefill: allowed`, populated cells are an allowed input surface for later snapshot/parser checkpoints.
- Must not include generator procedure, parser procedure, writer procedure, or runtime write orchestration.

Field vocabulary:
- `surfaces`
- `surfaceId`
- `surfaceRole`
- `sheetName`
- `anchorCell`
- `orientation`
- `operatorPrefill`
- `assignmentRows`
- `assignmentRows[].slotId`
- `assignmentRows[].rowOffset`

## 11. Scoring posture (settled)
Settled constraints:
- Keep an explicit minimal scoring stub.
- Do not mirror all v1 `SCORER_CONFIG` inside template artifact.
- Do not allow artifact to become runtime scorer-config dump.
- Day-level point rows are not part of `inputSheetLayout`.

First-release shape:
- `scoring.templateKnobs` (empty list allowed)

## 12. Hard artifact validity expectations
A template artifact is invalid if any of the following are true:
- required top-level sections are missing (`identity`, `slots`, `doctorGroups`, `eligibility`, `requestSemanticsBinding`, `inputSheetLayout`, `outputMapping`, `scoring`)
- slot records contain duplicate `slotId`
- doctor-group records contain duplicate `groupId`
- first-release ICU/HD required slot or group IDs are absent
- eligibility references unknown `slotId` or unknown `groupId`
- required slot semantics (`slotFamily`, `slotKind`) are missing
- `requiredCountPerDay` is missing, non-integer, or negative on any slot record
- input layout and output mapping content are mixed together
- any `inputSheetLayout.sections[]` record is missing canonical `groupId`
- any `inputSheetLayout.sections[].groupId` is empty or otherwise invalid
- any `inputSheetLayout.sections[].groupId` references an unknown `doctorGroups[].groupId`
- any `inputSheetLayout.sections[]` record is missing `headerLabel`
- ICU/HD first-release artifact omits `inputSheetLayout.headerBlock.title` or `inputSheetLayout.visibleLabels.departmentLabel`
- ICU/HD first-release artifact omits required point-row declarations (`MICU_CALL_POINT`, `MHD_CALL_POINT`) with declared `label` + `defaultRule`
- any ICU/HD first-release point-row default rule differs from the settled default matrix (`weekday->weekday=1`, `weekday->weekend/publicHoliday=1.75`, `weekend/publicHoliday->weekend/publicHoliday=2`, `weekend/publicHoliday->weekday=1.5`)
- `inputSheetLayout.legendBlock.present` is true but `legendBlock.contentLines` is missing
- `inputSheetLayout.surfaceOwnership` omits either operator-input or template-owned structural declarations
- any first-release lower roster/output shell surface in `outputMapping.surfaces[]` omits required structural fields (`surfaceRole`, `operatorPrefill`, `assignmentRows`)
- any `outputMapping.surfaces[].assignmentRows[]` record references an unknown `slotId`
- any `outputMapping.surfaces[].assignmentRows[].rowOffset` is duplicated within the same surface
- forbidden procedural/runtime content appears in declarative sections (`inputSheetLayout`, `outputMapping`, `scoring`)

## 13. Parser-facing guarantees
If the artifact is valid, parser-facing consumers may assume:
- section names and core record shapes are stable for this contract checkpoint (`identity`, `slots`, `doctorGroups`, `eligibility`, `requestSemanticsBinding`, `inputSheetLayout`, `outputMapping`, `scoring`)
- `identity` includes `templateId`, `templateVersion`, and `label`
- each slot record includes `slotId`, `label`, `slotFamily`, and `slotKind`
- each slot record includes explicit `requiredCountPerDay`, enabling deterministic SlotDemand instantiation from normalized days + slot declarations
- each doctor-group record includes `groupId` and `label`
- eligibility is explicit and deterministic as `slotId` + `eligibleGroups`
- request-layout parsing surface is structurally declared via `inputSheetLayout`
- visible title/department labels, section-header labels, point-row declarations, and legend adjunct presence/content are template-owned declarations in `inputSheetLayout`
- doctor→group normalization is explicit and deterministic through `inputSheetLayout.sections[]` declarations (`sectionKey` lookup + section-level canonical `groupId`)
- request semantics binding points to the settled request semantics contract via `contractId` + `contractVersion`
- output mapping semantics are declared separately from input layout, and lower roster/output shell structure is template-owned rather than writer-only
- first-release lower-shell assignment row order is explicit through `outputMapping.surfaces[].assignmentRows[]`
- surfaces marked `operatorPrefill: allowed` may later be treated as allowed sheet input when populated by operators

## 14. Explicit deferrals
Deferred beyond this checkpoint:
- richer future scoring knob surface beyond the minimal stub
- future generator/writer mechanics
- future expansion beyond ICU/HD first release

## 15. Remaining deferrals
This contract checkpoint keeps only the explicit deferrals listed above. Previously open naming/shape questions in this document are now settled for this first-pass artifact contract.

## 16. ICU/HD skeletal specimen (non-normative)
The following is a non-normative shape illustration aligned to the settled first-pass field vocabulary.

```yaml
identity:
  templateId: cgh_icu_hd
  templateVersion: 1
  label: CGH ICU/HD Call

slots:
  - slotId: MICU_CALL
    label: MICU Call
    slotFamily: MICU
    slotKind: CALL
    requiredCountPerDay: 1
  - slotId: MICU_STANDBY
    label: MICU Standby
    slotFamily: MICU
    slotKind: STANDBY
    requiredCountPerDay: 1
  - slotId: MHD_CALL
    label: MHD Call
    slotFamily: MHD
    slotKind: CALL
    requiredCountPerDay: 1
  - slotId: MHD_STANDBY
    label: MHD Standby
    slotFamily: MHD
    slotKind: STANDBY
    requiredCountPerDay: 1

doctorGroups:
  - groupId: ICU_ONLY
    label: ICU only
  - groupId: ICU_HD
    label: ICU + HD
  - groupId: HD_ONLY
    label: HD only

eligibility:
  - slotId: MICU_CALL
    eligibleGroups: [ICU_ONLY, ICU_HD]
  - slotId: MICU_STANDBY
    eligibleGroups: [ICU_ONLY, ICU_HD]
  - slotId: MHD_CALL
    eligibleGroups: [ICU_HD, HD_ONLY]
  - slotId: MHD_STANDBY
    eligibleGroups: [ICU_HD, HD_ONLY]

requestSemanticsBinding:
  contractId: ICU_HD_REQUEST_SEMANTICS
  contractVersion: 1

inputSheetLayout:
  sheetName: CGH ICU/HD Call
  headerBlock:
    title: CGH ICU/HD Call
  visibleLabels:
    departmentLabel: CGH ICU/HD Call
  dayAxis:
    anchorCell: B3
    direction: horizontal
  sections:
    - sectionKey: MICU
      groupId: ICU_ONLY
      headerLabel: MICU
      placement:
        anchorMode: belowBlock
        blockRef: dayAxis
      doctorRows:
        nameColumn: A
        requestStartColumn: B
    - sectionKey: MICU_HD
      groupId: ICU_HD
      headerLabel: ICU + HD
      placement:
        anchorMode: belowBlock
        blockRef: dayAxis
      doctorRows:
        nameColumn: A
        requestStartColumn: B
    - sectionKey: MHD
      groupId: HD_ONLY
      headerLabel: MHD
      placement:
        anchorMode: belowBlock
        blockRef: dayAxis
      doctorRows:
        nameColumn: A
        requestStartColumn: B
  pointRows:
    - rowKey: MICU_CALL_POINT
      label: MICU Call Point
      defaultRule:
        weekdayToWeekday: 1
        weekdayToWeekendOrPublicHoliday: 1.75
        weekendOrPublicHolidayToWeekendOrPublicHoliday: 2
        weekendOrPublicHolidayToWeekday: 1.5
    - rowKey: MHD_CALL_POINT
      label: MHD Call Point
      defaultRule:
        weekdayToWeekday: 1
        weekdayToWeekendOrPublicHoliday: 1.75
        weekendOrPublicHolidayToWeekendOrPublicHoliday: 2
        weekendOrPublicHolidayToWeekday: 1.5
  legendBlock:
    present: true
    contentLines:
      - "WKD = weekday"
      - "WEPH = weekend/public holiday"
  surfaceOwnership:
    operatorInput:
      - doctorNameCells
      - requestEntryCells
      - callPointCells
    templateOwnedStructural:
      - titleAndDepartmentHeader
      - dayAxis
      - sectionHeaders
      - sectionRowStructure

outputMapping:
  surfaces:
    - surfaceId: lowerRosterAssignments
      surfaceRole: LOWER_ROSTER_ASSIGNMENTS
      sheetName: CGH ICU/HD Call
      anchorCell: B4
      orientation: dateByColumn
      operatorPrefill: allowed
      assignmentRows:
        - slotId: MICU_CALL
          rowOffset: 0
        - slotId: MICU_STANDBY
          rowOffset: 1
        - slotId: MHD_CALL
          rowOffset: 2
        - slotId: MHD_STANDBY
          rowOffset: 3

scoring:
  templateKnobs: []
```
