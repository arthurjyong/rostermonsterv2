# Department Template Artifact Contract (Implementation-Facing First Pass)

## 1. Purpose and status
This document defines the **parser-consumable department template artifact** used by v2 for one department’s structural template.

Status in this checkpoint:
- **Implementation-facing first pass**.
- Intended to become **normative quickly** once open field-shape questions are closed.
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
- minimal scoring posture (if present)

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
The top-level section names remain open (see Open Issues), but the artifact must contain these logical sections:
1. identity / version
2. slot definitions
3. doctor-group definitions
4. eligibility declarations
5. request semantics binding
6. `inputSheetLayout`
7. `outputMapping`
8. optional minimal scoring surface or explicit scoring deferral posture

## 5. Slot definitions (settled content, open field names)
Slots are first-class records.

First-release ICU/HD slot identities:
- `MICU_CALL`
- `MICU_STANDBY`
- `MHD_CALL`
- `MHD_STANDBY`

Minimum explicit slot semantics:
- service/family (`MICU` or `MHD`)
- slot kind (`CALL` or `STANDBY`)

Field names for these properties are intentionally left open in this pass.

## 6. Doctor-group definitions (settled content, open field names)
First-release ICU/HD group identities:
- `ICU_ONLY`
- `ICU_HD`
- `HD_ONLY`

Settled constraints:
- Group vocabulary is template-owned.
- Monthly membership is external to this artifact.
- First release is group-based and does not include doctor-level override machinery.

## 7. Eligibility (settled behavior, open direction)
First-release eligibility is group-to-slot only.

Settled constraints:
- No doctor-level override layer in first release.
- Omission means ineligible unless a later settled field explicitly declares otherwise.
- Eligibility must be fully derivable from artifact declarations without hidden parser-side defaults.

Open direction:
- representation direction remains unresolved (`group -> slots` vs `slot -> groups`).

## 8. Request semantics binding (narrow)
This section binds template request parsing to the already-settled ICU/HD request semantics contract in `docs/request_semantics_contract.md`.

This section must stay narrow and must not carry:
- propagation rules
- CR guarantee logic
- scorer behavior
- allocator behavior
- reward/penalty decay behavior

Open posture:
- whether this section is reference-only vs reference + limited bound vocabulary fields.

## 9. `inputSheetLayout` contract
`inputSheetLayout` defines the request-entry surface only.

Settled constraints:
- No backward-compatibility requirement for old v1 request form shape.
- v2 may declare a cleaner request-form shape.
- Use named logical blocks.
- Do not mix output mapping into this section.
- Use one named request-form sheet in first release.
- Day axis is rule-based, not hardcoded month-span coordinates.
- Section model is repeatable section definitions.
- Section height is variable by doctor count.
- Doctor-row shape is minimal: display name + request cells.
- `MICU Call Point` / `MHD Call Point` rows are not part of `inputSheetLayout`; they are template-owned defaults outside input layout blocks.
- Tolerate presentation drift, not structural drift.

Parser-facing intent:
- clean parsing of operator-entered requests
- support future generation of fresh empty request forms from the same declared layout contract
- allow operator adjustments to date range and section manpower without contract breakage

Open detail:
- exact anchor/placement field shape.

## 10. `outputMapping` contract
Settled constraints:
- Included in the same artifact as a dedicated section.
- Kept separate from `inputSheetLayout`.
- Declarative only.
- Must not include writer procedure or runtime write orchestration.

Open detail:
- how concrete mapping must be (logical-only vs logical + destination surfaces/anchors).

## 11. Scoring posture
Settled constraints:
- Do not mirror all v1 `SCORER_CONFIG` inside template artifact.
- Keep scoring surface minimal if present.
- Do not allow artifact to become runtime scorer-config dump.
- Day-level point rows are not part of `inputSheetLayout`.

Open posture:
- minimal optional section vs explicit stub vs largely deferred.

## 12. Hard artifact validity expectations
A template artifact is invalid if any of the following are true:
- required logical sections are missing
- slot IDs or group IDs are duplicated
- first-release ICU/HD required slot or group IDs are absent
- eligibility references unknown group/slot identities
- semantics needed for slot identity (service/family, slot kind) are missing
- input layout and output mapping content are mixed together
- forbidden runtime/procedural content appears in declarative sections

## 13. Parser-facing guarantees
If the artifact is valid, parser-facing consumers may assume:
- slot and group identity vocabulary is stable within the artifact version
- eligibility is explicit and deterministic from declared content
- request-layout parsing surface is structurally declared via `inputSheetLayout`
- request semantics binding points to the settled request semantics contract
- output mapping semantics are declared separately from input layout

## 14. Explicit deferrals
Deferred beyond this checkpoint:
- final top-level naming and metadata field-shape closure
- final eligibility orientation closure
- final concrete anchor schema closure for layout/mapping
- detailed scorer contract integration beyond minimal posture
- writer/generator mechanics

## 15. Open issues (must remain open in this pass)
1. Exact top-level section names.
2. Exact metadata shape.
3. Exact field names for slot definitions.
4. Exact field names for doctor-group definitions.
5. Eligibility representation direction (`group -> slots` vs `slot -> groups`).
6. Request binding thickness (`reference only` vs `reference + limited bound vocabulary fields`).
7. `outputMapping` concreteness (`logical only` vs `logical + declared destination surfaces/anchors`).
8. Scoring posture (`minimal optional section` vs `explicit stub` vs largely deferred).
9. Exact anchor/placement field shape inside `inputSheetLayout`.

## 16. ICU/HD skeletal specimen (non-normative field names)
The following is a shape illustration only. Field names are placeholders and not settled.

```yaml
identity:
  templateId: cgh_icu_hd
  templateVersion: v2-first-pass

slots:
  - id: MICU_CALL
    family: MICU
    kind: CALL
  - id: MICU_STANDBY
    family: MICU
    kind: STANDBY
  - id: MHD_CALL
    family: MHD
    kind: CALL
  - id: MHD_STANDBY
    family: MHD
    kind: STANDBY

doctorGroups:
  - id: ICU_ONLY
  - id: ICU_HD
  - id: HD_ONLY

eligibility: <OPEN_DIRECTION>
requestSemanticsBinding:
  contractRef: docs/request_semantics_contract.md
inputSheetLayout:
  requestFormSheet: <NAME>
  dayAxis: <RULE_BASED>
  sections: <REPEATABLE>
outputMapping:
  mapping: <DECLARATIVE>
scoring: <MINIMAL_OR_DEFERRED>
```
