# Parser–Normalizer Contract (First-Pass Working Draft)

## 1) Contract status and scope
This document defines the parser–normalizer boundary that connects snapshot input (`docs/snapshot_contract.md`) to normalized domain output (`docs/domain_model.md`).

It is intended to be concrete enough for implementation planning in Phase 2 parser/normalization work.

It explicitly separates:
- repo-settled anchors,
- parser-boundary decisions adopted in this checkpoint,
- still-open items in this checkpoint,
- and explicit deferrals.

Scope is limited to parser-stage boundary behavior and handoff shape. This is not a solver, scorer, writeback, or execution design document.

## 2) Status discipline used in this document
Each normative statement in this document is classified as one of:
- **Repo-settled**: already anchored by existing repo contracts/blueprint/decision log.
- **Proposed in this checkpoint**: adopted here as first-release parser-boundary direction.
- **Still open in this checkpoint**: recognized as unresolved here and left explicit.
- **Deferred**: intentionally out of this checkpoint’s decision scope.

No proposed checkpoint decision in this document is presented as already repo-settled unless an existing repo document already settles it.

## 3) Repo-settled architecture anchors
The following are treated as **repo-settled anchors**:
- Parser/normalizer sits between raw snapshot input and normalized domain output.
- Snapshot is pre-interpretation raw input.
- Parser owns interpretation, normalization, and structural judgment at the boundary.
- Domain model is post-parser/post-normalizer output for downstream layers.
- Rule engine is downstream of parser/normalizer and is the runtime hard-validity authority.
- Parser/normalizer is not solver, scorer, writer/writeback, or orchestration/worker layer.

## 4) Purpose
**Repo-settled intent + checkpoint narrowing**:
- Preserve a strict contract boundary between raw snapshot facts and downstream normalized runtime facts.
- Ensure parser-stage interpretation is deterministic enough for downstream legality evaluation.
- Emit parser outcomes in a shape that supports implementation, diagnostics, and downstream admission decisions.

## 5) Boundary position
**Repo-settled**:
- Upstream: snapshot contract provides raw records and structural trace fields.
- Boundary: parser/normalizer interprets and normalizes snapshot content into domain-model-consumable facts.
- Downstream: rule engine/solver/scorer operate on normalized model, not raw snapshot rows.

**Proposed in this checkpoint**:
- Parser boundary admission is explicit and represented in parser output (see Sections 9–14).

## 6) Parser-owned responsibilities
### Repo-settled
Parser owns:
- interpretation of raw snapshot facts into normalized semantics,
- normalization into domain-model objects,
- structural judgment for snapshot integrity at parser boundary,
- parser/normalization issue reporting.

### Proposed in this checkpoint
Parser additionally owns:
- explicit parser-stage admission decision for downstream consumption,
- explicit rejection when parser uncertainty affects downstream-governing facts.

**Parser-stage derivation of normalized hard effects is allowed.**

## 7) Parser-forbidden responsibilities
### Repo-settled
Parser must not:
- perform combinatorial allocation search,
- perform scoring/ranking policy evaluation,
- perform writeback mapping or transport/orchestration concerns,
- replace rule-engine runtime hard-validity authority.

### Proposed in this checkpoint
Parser must not adjudicate candidate assignment legality.

**Parser-stage adjudication of candidate assignment legality is forbidden.**

## 8) Parser inputs
### Repo-settled
Parser input boundary is:
- snapshot-shaped raw run data,
- template-governed interpretation context,
- trace/provenance metadata emitted by adapter/snapshot contract.

### Proposed in this checkpoint
First-release parser contract assumes parser input is admissible for parsing attempts when top-level snapshot object exists, then parser decides consumability through staged checks.

## 9) Parser outputs
### Proposed in this checkpoint (first-release decision)
Parser handoff uses one top-level object:
- `ParserResult`

Proposed top-level components:
- `normalizedModel`
- `issues`
- `consumability`

Proposed first-release admission rule:
- `consumability = CONSUMABLE`: `normalizedModel` is present and downstream-consumable.
- `consumability = NON_CONSUMABLE`: `normalizedModel = null`; downstream receives no partial normalized handoff.

This `ParserResult` shape is adopted in this checkpoint and is not claimed as previously repo-settled.

## 10) Issue schema vs issue channel vs admission decision
### Repo-settled anchor
- `ValidationIssue` exists in domain model as shared issue shape.

### Proposed in this checkpoint
These concerns are explicitly separate:
- **Issue schema**: shared `ValidationIssue` shape.
- **Issue channel**: `ParserResult.issues`.
- **Admission decision**: `ParserResult.consumability`.

Proposed channel decision:
- `ParserResult.issues` is the authoritative parser-stage issue channel.
- Entity-local issue detail may exist where domain model expects it.
- Entity-local issue detail must not replace the top-level parser-stage issue list.

## 11) Transformation stages
### Proposed in this checkpoint (ordered first-release contract shape)
1. input admission
2. structural snapshot validation
3. cross-record reference resolution
4. template interpretation and base normalization
5. request parsing and effect derivation
6. normalized model assembly and internal consistency checks
7. final parser result decision

Implementation note (still compatible with this contract): internal code may merge adjacent stages, but boundary intent and ordering semantics must remain intact.

## 12) Structural non-consumability
### Proposed in this checkpoint
`NON_CONSUMABLE` is required when structural conditions prevent deterministic parser output. Examples:
- invalid top-level snapshot shape,
- missing required fields breaking deterministic interpretation,
- unresolved/ambiguous references,
- uniqueness/collision defects,
- ordering/coverage defects,
- missing required provenance fields from snapshot contract where relevant.

## 13) Semantic / normalization non-consumability
### Proposed in this checkpoint
`NON_CONSUMABLE` is also required when semantic/normalization interpretation cannot produce deterministic downstream-governing facts. Examples:
- request parsing ambiguity affecting hard-block or derived machine effects,
- parser cannot deterministically apply required template-declared semantics needed for this snapshot,
- normalized model assembly cannot produce complete internally consistent downstream input,
- unresolved ambiguity in normalized doctor/group identity or downstream-governing slot/demand/eligibility facts.

**Parser uncertainty about downstream-governing facts is not a warning-only condition; it is a non-consumability condition.**

## 14) Consumable results with issues
### Proposed in this checkpoint
`CONSUMABLE` parser results may still include issues when issues do not block deterministic downstream-governing normalization.

First-release direction:
- admission decision is binary (`CONSUMABLE` / `NON_CONSUMABLE`),
- issue severity is not itself an admission surrogate,
- non-blocking issues remain visible via `ParserResult.issues`.

## 15) Provenance expectations in normalized outputs
### Proposed in this checkpoint
This contract imposes a **parser-stage traceability obligation**.

It does **not yet** impose a universal provenance field-shape standard across all normalized entities.

Minimum first-release expectation:
Any normalized entity or normalized fact derived from snapshot content must remain traceable back to:
- relevant snapshot record kind,
- relevant logical locator,
- relevant physical source reference where applicable.

### Still open in this checkpoint
Exact concrete provenance field names/embedding patterns inside each normalized object remain open and are deferred from this contract (see Section 18).

## 16) Explicit handoff to rule engine
### Repo-settled anchor
Rule engine is downstream runtime hard-validity authority.

### Proposed in this checkpoint
For admitted parser output (`ParserResult.consumability = CONSUMABLE`), rule engine may assume:
- normalized identities required downstream are already resolved,
- normalized references are internally consistent,
- request text has already been interpreted into normalized request/effect facts,
- downstream-governing eligibility and demand facts required by runtime validity are already instantiated in normalized form,
- parser-stage ambiguity affecting downstream-governing facts has already been rejected.

Rule engine must never reconstruct from raw snapshot state:
- doctor identity from raw doctor rows,
- date identity from raw day records,
- request semantics from raw request text,
- same-day hard-block or derived effect semantics from unparsed codes,
- template-owned group/slot/eligibility/demand meaning from raw sheet structure,
- parser-stage structural validity from raw snapshot linkage/provenance defects.

**The rule engine evaluates normalized legality; it does not recover lost parser meaning.**

## 17) Consistency with adjacent contracts
### Repo-settled alignments
- Consistent with snapshot contract: snapshot remains raw, pre-interpretation, trace-preserving input.
- Consistent with domain model: normalized objects are parser/normalizer outputs consumed downstream.
- Consistent with blueprint and roadmap: parser/normalizer phase precedes rule engine and solver/scorer phases.

### Proposed in this checkpoint
- `ParserResult` formalizes parser-stage admission/handoff shape for first release while remaining aligned with snapshot/domain boundaries.

## 18) Explicit deferrals
The following are explicitly deferred and not fixed by this document:
- exact concrete field names for provenance storage inside normalized objects,
- internal implementation decomposition across files/modules,
- whether parser sub-stages are separate passes or merged passes internally,
- richer issue-taxonomy extensions beyond the shared minimum issue shape,
- parser-only diagnostic artifact shapes outside `ParserResult`,
- exact concrete parser function/API signature.

## 19) Current checkpoint status
### Repo-settled in prior docs
- boundary position and high-level role split (snapshot vs parser/normalizer vs domain vs downstream rule engine).

### Proposed and adopted in this checkpoint
- first-release `ParserResult` handoff shape (`normalizedModel`, `issues`, `consumability`),
- binary consumability decision,
- no partial normalized downstream handoff when non-consumable,
- explicit split of structural vs semantic/normalization non-consumability,
- explicit issue schema vs issue channel vs admission decision distinction,
- explicit parser-to-rule-engine handoff assumptions and prohibitions.

### Still open / deferred
- internal representation/API details and provenance field-shape standardization beyond traceability obligation.

This document is a first-pass working draft checkpoint intended to unblock implementation planning without reopening broader architecture scope.
