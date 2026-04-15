# Department Template Artifact Contract (Implementation-Facing First Pass)

## 1. Purpose and status
This document defines the **parser-consumable department template artifact** used by v2 for one department’s structural template.

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
- input request-form layout contract (`inputSheetLayout`)
- output mapping contract (`outputMapping`)
- explicit minimal scoring stub

### Out of scope
This artifact must not redefine or embed:
- snapshot contract shape
- parser-result/output model shape
- request semantics contract details
- solver logic, scorer formulas, or allocator mechanics
- writer procedures or sheet-generation procedures
- whole-sheet presentation details (styling, colors, borders, legends, FAQ text, narrative notes)

## 3. Artifact posture (settled)
Settled for first release:
- One artifact describes one department structural template.
- Monthly doctor membership and monthly period data are not stored in this artifact.
- The artifact remains declarative.
- Output mapping is included in the same artifact but remains a separate section from input layout.
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

First-release ICU/HD slot identities:
- `MICU_CALL`
- `MICU_STANDBY`
- `MHD_CALL`
- `MHD_STANDBY`

Minimum explicit slot semantics:
- `slotFamily` (`MICU` or `MHD`)
- `slotKind` (`CALL` or `STANDBY`)

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
`inputSheetLayout` defines the request-entry surface only.

Settled constraints:
- No backward-compatibility requirement for old v1 request form shape.
- v2 may declare a cleaner request-form shape.
- Use named logical blocks plus lightweight relative anchors.
- Do not mix output mapping into this section.
- Do not include generator procedure.
- Use one named request-form sheet in first release.
- Day axis is rule-based, not hardcoded month-span coordinates.
- Section model is repeatable section definitions.
- Section height is variable by doctor count.
- Doctor-row shape is minimal: display name + request cells.
- `MICU Call Point` / `MHD Call Point` rows are not part of `inputSheetLayout`; they are template-owned defaults outside input layout blocks.
- Tolerate presentation drift, not structural drift.

Field vocabulary:
- `sheetName`
- `dayAxis.anchorCell`
- `dayAxis.direction`
- `sections`
- `sectionKey`
- `placement.anchorMode`
- `placement.blockRef`
- `doctorRows.nameColumn`
- `doctorRows.requestStartColumn`

Parser-facing intent:
- clean parsing of operator-entered requests
- support future generation of fresh empty request forms from the same declared layout contract
- allow operator adjustments to date range and section manpower without contract breakage

## 10. `outputMapping` contract (settled)
Settled constraints:
- Included in the same artifact as a dedicated section.
- Kept separate from `inputSheetLayout`.
- Declarative only.
- Logical mapping plus declared destination surfaces/anchors.
- Must not include writer procedure or runtime write orchestration.

Field vocabulary:
- `surfaces`
- `surfaceId`
- `sheetName`
- `anchorCell`
- `orientation`

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
- input layout and output mapping content are mixed together
- forbidden procedural/runtime content appears in declarative sections (`inputSheetLayout`, `outputMapping`, `scoring`)

## 13. Parser-facing guarantees
If the artifact is valid, parser-facing consumers may assume:
- section names and core record shapes are stable for this contract checkpoint (`identity`, `slots`, `doctorGroups`, `eligibility`, `requestSemanticsBinding`, `inputSheetLayout`, `outputMapping`, `scoring`)
- `identity` includes `templateId`, `templateVersion`, and `label`
- each slot record includes `slotId`, `label`, `slotFamily`, and `slotKind`
- each doctor-group record includes `groupId` and `label`
- eligibility is explicit and deterministic as `slotId` + `eligibleGroups`
- request-layout parsing surface is structurally declared via `inputSheetLayout`
- request semantics binding points to the settled request semantics contract via `contractId` + `contractVersion`
- output mapping semantics are declared separately from input layout

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
  label: CGH ICU/HD

slots:
  - slotId: MICU_CALL
    label: MICU Call
    slotFamily: MICU
    slotKind: CALL
  - slotId: MICU_STANDBY
    label: MICU Standby
    slotFamily: MICU
    slotKind: STANDBY
  - slotId: MHD_CALL
    label: MHD Call
    slotFamily: MHD
    slotKind: CALL
  - slotId: MHD_STANDBY
    label: MHD Standby
    slotFamily: MHD
    slotKind: STANDBY

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
  sheetName: Requests
  dayAxis:
    anchorCell: B3
    direction: horizontal
  sections:
    - sectionKey: MICU
      placement:
        anchorMode: belowBlock
        blockRef: dayAxis
      doctorRows:
        nameColumn: A
        requestStartColumn: B

outputMapping:
  surfaces:
    - surfaceId: assignments
      sheetName: Roster
      anchorCell: B4
      orientation: dateByColumn

scoring:
  templateKnobs: []
```
