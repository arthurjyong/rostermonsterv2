# Snapshot/Input Contract (First-Pass Working Draft)

## Contract status and current scope
This is a **first-pass contract draft** for the snapshot/input boundary.

It is intended to be useful immediately for adapter and parser implementation work, while keeping only genuinely unresolved details explicit.

This draft separates:
- decisions already settled
- decisions deliberately deferred

## 1. Purpose of the snapshot contract
The snapshot contract defines what raw run-specific input facts are captured for one roster run period **before parser interpretation and normalization**.

The goal is to preserve what was extracted from source inputs in a traceable way, without embedding downstream semantics or normalized domain objects.

## 2. Boundary position in the v2 pipeline
The boundary is:
- **Template** = department structure and semantics.
- **Snapshot** = raw per-run/month input facts.
- **Domain model** = normalized post-parse representation.

Snapshot data is intentionally upstream of normalization and interpretation.

Settled boundary points:
- Snapshot records what was seen; parser decides what it means.
- Per-date slot demand belongs to the template, not the snapshot.
- Template owns doctor-group vocabulary and canonical meaning.
- Parser resolves canonical doctor-group semantics from upstream template-artifact declaration surfaces (not from snapshot doctor rows themselves).
- Parser instantiates normalized slot demand from template-declared `requiredCountPerDay` across normalized days (not from snapshot-side defaults).

## 3. Adapter/parser split
The production Apps Script adapter's responsibilities, placement, transport, and layout-drift handling are pinned in `docs/snapshot_adapter_contract.md` (added under `docs/decision_log.md` D-0036 / D-0040 / D-0041 / D-0042 / D-0043). This section pins the conceptual split; the adapter contract operationalizes it.

### Adapter guarantees
The adapter is responsible for extraction fidelity, traceability, and template-declared logical mapping resolution needed to build snapshot locators:
- preserve extracted values as seen in source
- preserve extracted day order exactly
- emit required trace/provenance metadata
- resolve template-declared logical mapping keys required for `sourceLocator` (including `sectionKey`)
- avoid semantic interpretation during extraction
- do **not** repair duplicate dates or broken day ordering

### Parser-owned interpretation and structural judgment
The parser owns interpretation and structural judgment, including:
- mapping raw snapshot facts into normalized template/domain semantics
- normalization into domain-model objects
- semantic parse issues
- deciding whether structural findings (for example duplicate dates or broken day order) invalidate the snapshot

## 4. Explicit exclusions from snapshot
Snapshot must not carry:
- slot definitions
- doctor-group taxonomy / eligibility policy
- request semantics
- per-date slot demand
- normalized domain objects
- solver/scorer/result/writeback artifacts
- parsed request-code lists or normalized daily effects

## 5. Top-level snapshot object shape (settled)
Use one top-level snapshot object with consistent naming style:
- `metadata`
- `doctorRecords`
- `dayRecords`
- `requestRecords`
- `prefilledAssignmentRecords`
- `scoringConfigRecords` *(added under `docs/decision_log.md` D-0037)*

Naming style should remain consistent as `...Records` collections.

## 6. Metadata and extraction summary (settled direction)
`metadata` is always present and should stay minimal and structural.

Always-present metadata intent:
- snapshot identity
- template reference
- source identity
- generation timestamp
- period identity
- small extraction summary

Extraction summary direction:
- keep it small (not a reporting object)
- keep it structural only
- align counts/coverage framing with `doctorRecords`, `dayRecords`, and `requestRecords`

### `periodRef` (settled first-release shape)
`metadata.periodRef` is always present with:
- `periodRef.periodId`
- `periodRef.periodLabel`

Rules:
- `periodRef` is always present
- `periodId` is mandatory and non-empty
- `periodLabel` is mandatory as a field but may be empty
- `periodId` is always adapter-generated
- do not assume calendar-month shape
- do not force year/month fields
- do not include normalized `startDate` / `endDate` in `metadata`

### Extraction summary (settled first-release shape)
Extraction summary is structural only (not a reporting object), and explicitly includes:
- `doctorRecordCount`
- `dayRecordCount`
- `requestRecordCount`
- `prefilledAssignmentRecordCount`
- `componentWeightRecordCount` *(added under `docs/decision_log.md` D-0037)*
- `callPointRecordCount` *(added under D-0037)*

## 7. Doctor record contract (first-release scope)
Doctor records stay raw and structural, not semantic.

### Mandatory doctor-record fields (current agreement)
- `sourceDoctorKey`
- `displayName`
- `rawSectionText`
- `sourceLocator`
- `physicalSourceRef`

### Mandatory doctor-record rules (current agreement)
- exactly one non-empty `sourceDoctorKey`
- non-empty `displayName`
- `rawSectionText` is mandatory but may be empty
- exactly one non-empty `sourceLocator`
- exactly one non-empty `physicalSourceRef`
- doctor records must be uniquely identifiable by (`sectionKey`, `doctorIndexInSection`)

### Meaning of `rawSectionText`
- `rawSectionText` is the raw visible section/header text captured from the source sheet region used to place that doctor under a template-declared logical section
- `rawSectionText` is audit/debug only
- `rawSectionText` is never structural identity
- `rawSectionText` is never normalized doctor-group meaning
- canonical doctor-group meaning is resolved by parser from template-declared section/group surfaces, not from snapshot text fields
- grouping remains a template decision, not routine monthly operational input

### Doctor-record forbidden content
Doctor records must not include:
- canonical `doctorId`
- canonical doctor-group semantics
- eligibility result
- interpreted semantics
- scorer/solver/writeback fields

## 8. Day record contract (settled first-release position)
Snapshot uses explicit ordered day records.

### Mandatory day-record fields
- `dayIndex`
- `rawDateText`
- `sourceLocator`
- `physicalSourceRef`

### Day-record rules
- `dayIndex` is mandatory
- `dayIndex` is a non-negative integer
- `dayIndex` is unique within `dayRecords`
- `dayRecords` preserve extracted order
- `dayIndex` must form a contiguous emitted sequence starting from `0`
- keep `rawDateText` only for current ICU/HD scope
- adapter does not repair duplicate dates or broken ordering
- parser decides whether duplicate dates / broken ordering make the snapshot structurally invalid

## 9. Request record contract (settled first-release position)
Request records remain raw and linked to both doctor records and day records.

### Mandatory request-record fields
- `sourceDoctorKey`
- `dayIndex`
- `rawRequestText`
- `sourceLocator`
- `physicalSourceRef`

### Request-record rules
- include raw request content as `rawRequestText` only
- `rawRequestText` preserves exact raw cell text (not trimmed or normalized)
- blank request cells still emit request records
- exactly one request record exists for each extracted doctor-day request cell (including blank cells)
- request records must be uniquely identifiable by (`sourceDoctorKey`, `dayIndex`)
- request records link to doctor records by `sourceDoctorKey` and to day records by `dayIndex`

### Request-record forbidden content
Request records must not include:
- `parsedCodeList`
- canonical request codes
- normalized daily effects
- semantic parse issues

## 10. `sourceLocator` contract (settled direction)
`sourceLocator` is a logical/template-facing trace field. It is not a generic loose key/value blob.

Use stricter typed shape by record kind, with consistent naming (`doctorIndexInSection`, not `doctorOrdinalInSection`):

- **Doctor record locator**
  - `surfaceKey = doctorRows`
  - `path = { sectionKey, doctorIndexInSection }`

- **Day record locator**
  - `surfaceKey = dayAxis`
  - `path = { dayIndex }`

- **Request record locator**
  - `surfaceKey = requestCells`
  - `path = { sourceDoctorKey, dayIndex }`

- **Prefilled-assignment record locator**
  - `surfaceKey = outputMapping`
  - `path = { surfaceId, rowOffset, dayIndex }`

- **Component-weight record locator** *(added under `docs/decision_log.md` D-0037)*
  - `surfaceKey = scorerConfigCells`
  - `path = { componentId }`

- **Call-point record locator** *(added under `docs/decision_log.md` D-0037)*
  - `surfaceKey = callPointCells`
  - `path = { callPointRowKey, dayIndex }`

Notes:
- `sectionKey` refers to template-declared logical section identity, not monthly operator input.
- `sectionKey` is a logical mapping key for traceability and is not normalized doctor-group meaning by itself.
- `dayAxis` aligns directly with template `inputSheetLayout.dayAxis`.
- `requestCells` is the single derived logical extraction surface retained for first release, spanning section-scoped doctor rows against the template day axis; this keeps locator naming close to template vocabulary without introducing parallel locator surface names.
- `outputMapping` locator paths for prefilled assignments must stay aligned to template-declared lower-shell surfaces and assignment-row offsets, and remain raw/trace-focused rather than semantic.
- canonical doctor-group semantics are resolved by parser via template artifact declarations keyed by `sectionKey`.
- uniqueness constraints tied to locator paths are:
  - (`sectionKey`, `doctorIndexInSection`) unique within `doctorRecords`
  - `dayIndex` unique within `dayRecords`
  - (`sourceDoctorKey`, `dayIndex`) unique within `requestRecords`
  - (`surfaceId`, `rowOffset`, `dayIndex`) unique within `prefilledAssignmentRecords`
  - `componentId` unique within `scoringConfigRecords.componentWeightRecords`
  - (`callPointRowKey`, `dayIndex`) unique within `scoringConfigRecords.callPointRecords`

## 11. Prefilled assignment record contract (checkpoint 2 raw snapshot scope)
`prefilledAssignmentRecords` preserve operator-populated lower roster/output-shell cell contents as raw input facts seen in declared parse surfaces.

These records are:
- upstream of parser interpretation
- distinct from `requestRecords`
- raw trace data only (no normalized assignment meaning at snapshot layer)

### Mandatory prefilled-assignment-record fields
- `dayIndex`
- `rawAssignedDoctorText`
- `surfaceId`
- `rowOffset`
- `sourceLocator`
- `physicalSourceRef`

### Prefilled-assignment-record rules
- include one raw record for each extracted populated operator-prefilled assignment cell within declared parse surfaces
- do not emit records for random populated content outside declared parse surfaces
- records link to `dayRecords` by `dayIndex`
- records link to template-declared output-shell structure by (`surfaceId`, `rowOffset`)
- `rawAssignedDoctorText` preserves exact raw cell text (not trimmed or normalized)
- records must be uniquely identifiable by (`surfaceId`, `rowOffset`, `dayIndex`)
- do not silently merge records or normalize meaning at snapshot layer
- snapshot layer does not decide whether a populated prefilled cell is valid/consumable; parser decides interpretation later

### Prefilled-assignment-record forbidden content
Prefilled assignment records must not include:
- canonical doctor identity
- normalized slot semantics beyond declared locator identity (`surfaceId`, `rowOffset`)
- fixed/locked assignment meaning
- legality judgments
- solver/scorer/writeback semantics

## 11A. Scoring-config record contract (added under `docs/decision_log.md` D-0037)
`scoringConfigRecords` carries the operator-edited cell values that drive the scorer's `ScoringConfig` per `docs/scorer_contract.md` v3 §11. Records are raw snapshot facts — no parser-stage interpretation at snapshot layer. Two record kinds in first release:

### `componentWeightRecords[]`
One record per first-release component identifier (per `docs/domain_model.md` §11.2) carrying the operator-edited weight value from the launcher-generated Scorer Config tab declared in `docs/sheet_generation_contract.md`.

Mandatory `componentWeightRecord` fields:
- `componentId` — one of the nine first-release component identifiers (`unfilledPenalty`, `pointBalanceWithinSection`, `pointBalanceGlobal`, `spacingPenalty`, `preLeavePenalty`, `crReward`, `dualEligibleIcuBonus`, `standbyAdjacencyPenalty`, `standbyCountFairnessPenalty`),
- `rawValue` — exact raw cell text from the Scorer Config tab (no trimming or normalization at snapshot layer; parser interprets per `docs/parser_normalizer_contract.md` §9 / §14),
- `sourceLocator` (see §10),
- `physicalSourceRef` (see §12).

`componentWeightRecord` rules:
- one record per component identifier when the operator has any value in the corresponding cell (blank cells produce records with empty `rawValue`, matching `requestRecords` blank-cell discipline per §9),
- records must be uniquely identifiable by `componentId`,
- records do not carry sign-orientation classification (parser knows from `docs/scorer_contract.md` §10 / §15 which components are penalties vs rewards).

### `callPointRecords[]`
One record per `(callPointRowKey, dayIndex)` pair carrying the operator-editable per-day call-point cell value from the request-entry sheet. The row identities are template-declared per `docs/template_artifact_contract.md` §9 (`pointRows.rowKey`); for ICU/HD first release these are `MICU_CALL_POINT` and `MHD_CALL_POINT`.

Mandatory `callPointRecord` fields:
- `callPointRowKey` — template-declared row key (e.g., `MICU_CALL_POINT`),
- `dayIndex` — column-axis day index (links to `dayRecords` by `dayIndex`),
- `rawValue` — exact raw cell text (no trimming or normalization at snapshot layer),
- `sourceLocator` (see §10),
- `physicalSourceRef` (see §12).

`callPointRecord` rules:
- include one record for each template-declared `(pointRowKey, dayIndex)` pair across the period (blank cells emit records with empty `rawValue`, same discipline as `requestRecords` per §9),
- records must be uniquely identifiable by `(callPointRowKey, dayIndex)`,
- records link to `dayRecords` by `dayIndex` and to template-declared point rows by `callPointRowKey`.

### Scoring-config record forbidden content
Scoring-config records must not include:
- parsed numeric values,
- sign-orientation classification (penalty vs reward — that's parser-stage knowledge),
- normalized `ScoringConfig` shapes (parser builds those during overlay onto template defaults),
- legality / direction-guard validation outcomes.

## 12. `physicalSourceRef` contract (settled direction)
`physicalSourceRef` is the concrete sheet-facing extraction trace and remains separate from `sourceLocator`.

Required contents:
- `sheetName` (mandatory)
- `sheetGid` (mandatory)
- `a1Refs` (ordered non-empty list)

Intent:
- preserve human-readable tab context (`sheetName`)
- preserve stable sheet-tab identity (`sheetGid`)
- preserve exact extracted source cells (`a1Refs`)
- do not collapse multiple true source cells into a fake single reference

## 13. Whole-snapshot structural validation taxonomy
Validation taxonomy here classifies **structural snapshot findings** only.

Categories:
- top-level shape
- record-shape integrity
- reference integrity
- uniqueness / collision
- ordering / coverage
- provenance integrity

Clarifications:
- this taxonomy does not carry request semantics, doctor-group semantics, solver/scorer issues, or downstream normalized-domain validity
- category is not the same as severity
- parser owns structural invalidation decisions

## 14. Open questions / deferred decisions (intentionally narrow)
No additional open structural questions are introduced in this document.

Any future changes to shape or semantics should be treated as explicit contract/version updates in the relevant contract docs, not implicit reopenings here.
