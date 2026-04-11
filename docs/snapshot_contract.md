# Snapshot/Input Contract (First-Pass Working Draft)

## Contract status and current scope
This is a **first-pass contract draft** for the snapshot/input boundary.

It is intended to be useful immediately for parser and adapter implementation work, while making unresolved decisions explicit. Some details are intentionally not finalized yet.

This draft separates:
- decisions already settled
- decisions deliberately deferred

## 1. Purpose of the snapshot contract
The snapshot contract defines what raw run-specific input facts are captured for one roster run period before parser interpretation.

The goal is to preserve what was extracted from source inputs in a traceable way, without embedding downstream semantics or normalized domain objects.

## 2. Boundary position in the v2 pipeline
The boundary is:
- **Template** = department structure and semantics.
- **Snapshot** = raw per-run/month input facts.
- **Domain model** = normalized post-parse representation.

Snapshot data is intentionally upstream of normalization and interpretation.

## 3. Core contract stance
Snapshot should contain raw run-specific facts, not template semantics and not normalized downstream objects.

**Snapshot records what was seen. Parser decides what it means.**

## 4. Adapter/parser split
### Adapter guarantees
The adapter is responsible for extraction fidelity and traceability:
- preserve extracted values as seen in source
- preserve extraction order where required (for period/day records)
- emit required trace/provenance metadata
- avoid semantic interpretation during extraction

### Parser-owned interpretation
The parser owns interpretation and structural judgment, including:
- mapping raw labels to template semantics
- normalization into domain-model objects
- semantic parse issues
- structural invalidation decisions defined at parser/domain boundary

## 5. Explicit exclusions from snapshot
Snapshot must not carry:
- slot definitions
- doctor-group taxonomy / eligibility policy
- request semantics
- per-date slot demand
- normalized domain objects
- solver/scorer/result/writeback artifacts

Settled boundary decisions:
- Per-date slot demand belongs to the template, not the snapshot.
- If slot demand changes, that is a template-level structural change, not a monthly snapshot override.
- Template owns doctor-group vocabulary and meaning.
- Snapshot may carry monthly raw doctor-group labels as operational input.

## 6. Required always-present minimal metadata
Small trace/debug metadata is always present (not optional).

Current agreed minimal identity/provenance metadata (exact field schema still open):
- snapshot identity
- template reference
- source identity
- generation timestamp
- period identity
- very small extraction summary

This section defines required metadata intent, not a finalized schema.

## 7. Doctor record contract (first-release scope)
This section is intentionally narrow.

### Mandatory doctor-record fields (current agreement)
- `sourceDoctorKey`
- `displayName`
- `rawGroupLabel`
- `sourceLocator`
- `physicalSourceRef`

### Mandatory doctor-record rules (current agreement)
- exactly one non-empty `sourceDoctorKey`
- non-empty `displayName`
- exactly one non-empty `rawGroupLabel`
- exactly one doctor group per doctor for ICU/HD first release
- missing / unknown / duplicated / conflicting group assignment = hard structural error
- exactly one non-empty `sourceLocator`
- exactly one non-empty `physicalSourceRef`

### Doctor-record forbidden content
Doctor records must not include:
- canonical `doctorId`
- canonical `doctorGroup`
- eligibility result
- interpreted semantics
- scorer/solver/writeback fields

### Trace-field nuance (settled intent, unresolved exact format)
- `sourceLocator` is a logical trace field.
- `physicalSourceRef` is a concrete Google Sheets extraction trace.

Exact formatting/shape for both fields is still open.

## 8. Request record contract (settled now)
Settled first-pass position:
- snapshot request records keep `rawRequestText`
- snapshot request records do not include:
  - `parsedCodeList`
  - canonical request codes
  - normalized daily effects
  - parse issues tied to semantic interpretation

Additional request-record fields beyond `rawRequestText` are not finalized yet.

## 9. Period/date records (settled now)
Settled first-pass position:
- snapshot contains explicit ordered day entries
- adapter preserves sheet order exactly as extracted
- adapter does not repair duplicates or broken ordering
- parser decides whether duplicate dates / broken ordering make the snapshot structurally invalid

Exact final day-entry shape is still open.

## 10. Open questions / deferred decisions
The following items are intentionally unresolved in this first-pass draft:
- exact field format of `sourceLocator`
- exact field format of `physicalSourceRef`
- full request-record field set beyond `rawRequestText`
- exact period/day entry shape
- exact top-level snapshot object shape
- exact whole-snapshot invalidation rules
- exact extraction summary fields

These are deferred decisions and should not be silently completed in implementation.
