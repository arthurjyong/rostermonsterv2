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
- Template owns doctor-group vocabulary and meaning.

## 3. Adapter/parser split
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

### Explicitly open: period identity design
Still open (intentionally not finalized here):
- exact period identity representation inside `metadata`
- do not force calendar-month assumptions
- do not silently hard-code year/month shape

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

### Meaning of `rawSectionText`
- `rawSectionText` is the raw visible section/header text captured from the source sheet region used to place that doctor under a template-declared logical section
- `rawSectionText` is audit/debug only
- `rawSectionText` is never structural identity
- `rawSectionText` is never normalized doctor-group meaning
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

### Day-record requirements
- day records are explicit entries in `dayRecords`
- adapter preserves extracted day order exactly
- adapter does not repair duplicate dates or broken ordering
- parser decides whether duplicate dates / broken ordering make the snapshot structurally invalid
- for current ICU/HD template scope, keep `rawDateText` only
- do not introduce hybrid raw date parts at this stage

## 9. Request record contract (settled first-release position)
Request records remain raw and linked to day records.

### Mandatory request-record fields
- `sourceDoctorKey`
- `dayIndex`
- `rawRequestText`
- `sourceLocator`
- `physicalSourceRef`

### Request-record requirements
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
  - `surfaceKey = dayRecords`
  - `path = { dayIndex }`

- **Request record locator**
  - `surfaceKey = requestGrid`
  - `path = { sourceDoctorKey, dayIndex }`

Notes:
- `sectionKey` refers to template-declared logical section identity, not monthly operator input.
- `sectionKey` is a logical mapping key for traceability and is not normalized doctor-group meaning.

## 11. `physicalSourceRef` contract (settled direction)
`physicalSourceRef` is the concrete sheet-facing extraction trace and remains separate from `sourceLocator`.

Required contents:
- `sheetName` (mandatory)
- `sheetGid` (mandatory)
- `a1Refs` (ordered non-empty list)

Intent:
- preserve human-readable tab context (`sheetName`)
- preserve stable sheet-tab identity (`sheetGid`)
- preserve exact extracted source cells (`a1Refs`)

## 12. Whole-snapshot structural validation taxonomy
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

## 13. Open questions / deferred decisions (intentionally narrow)
Still open:
- exact period identity design inside `metadata` (without forcing calendar-month schema)

No other previously open items in this document should be treated as unresolved at this stage.
