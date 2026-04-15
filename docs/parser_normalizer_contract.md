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

ICU/HD first-release request-language details (raw grammar, token vocabulary, raw/canonical/effect mappings, combinations, duplicates, and request-level consumability rules) are governed by `docs/request_semantics_contract.md`.

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

### Downstream-governing facts (normative definition)
For this contract, **downstream-governing facts** are normalized facts that downstream legality evaluation depends on. They include at minimum:
- normalized doctor identity,
- normalized day/date identity,
- request-derived hard/soft machine effects,
- instantiated eligibility facts needed by downstream legality evaluation,
- instantiated demand facts needed by downstream legality evaluation.

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

First-release ICU/HD template interpretation inputs used at this boundary include:
- section-based doctor-group derivation declarations on `inputSheetLayout.sections[]` (`sectionKey` + canonical `groupId`),
- slot declarations with `requiredCountPerDay` for fixed per-day demand instantiation.

### Proposed in this checkpoint
This contract defines no separate pre-parser rejection channel. Malformed or incomplete snapshot-shaped input is handled within parser result production.

Boundary rule:
- even malformed top-level snapshot input is handled through `ParserResult`, not through out-of-band rejection;
- parser may return `NON_CONSUMABLE` for malformed top-level input.

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
- for `NON_CONSUMABLE` request parses, any partially recognized subset detail may appear only in `ParserResult.issues[*].context` and must not be emitted as a normalized side payload.

This `ParserResult` shape is adopted in this checkpoint and is not claimed as previously repo-settled.

## 10) Issue schema vs issue channel vs admission decision
### Repo-settled anchor
- `ValidationIssue` exists in domain model as shared issue shape.

### Proposed in this checkpoint
These concerns are explicitly separate:
- **Issue schema**: shared `ValidationIssue` shape.
- **Issue channel**: `ParserResult.issues`.
- **Admission decision**: `ParserResult.consumability`.

Propagation and authority rule set (first-release decision):
1. `ParserResult.issues` is the complete authoritative list of parser-stage issues.
2. Every parser-stage issue affecting consumability must appear in `ParserResult.issues`.
3. Every parser-stage issue required for downstream diagnostics must appear in `ParserResult.issues`.
4. Request parse issues must also appear on the relevant normalized `Request` when a normalized `Request` exists in a `CONSUMABLE` output.
5. Other entity-local issue content is optional unless later standardized.
6. Entity-local issue content must never be the sole record of an admission-relevant parser-stage issue.

Contract consequence:
- entity-local issue detail is supplemental only and must not replace the top-level parser-stage issue channel.
- when `consumability = NON_CONSUMABLE` and `normalizedModel = null`, `ParserResult.issues` remains the only required issue record under this contract.

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

## 12) First-release ICU/HD request parsing policy
### Proposed in this checkpoint (normative)
- ICU/HD first-release request-language specifics are defined by `docs/request_semantics_contract.md`; this parser contract does not duplicate that specification.
- Parser must re-validate raw snapshot request text itself and must not blindly trust upstream sheet validation.
- Blank string is valid and means no request codes.
- Non-blank request text must be parsed under the declared request grammar.
- Parser must not guess meaning from malformed or uncertain request text.
- If parser cannot deterministically derive downstream-governing request facts, parser result must be `NON_CONSUMABLE`.

## 13) Structural non-consumability
### Proposed in this checkpoint
`NON_CONSUMABLE` is required when parser cannot safely trust structural shape or linkage of input. Typical examples:
- invalid top-level snapshot shape,
- missing required fields preventing deterministic interpretation,
- unresolved or ambiguous cross-record references,
- uniqueness/collision defects,
- ordering/coverage defects,
- missing required snapshot provenance fields where this contract/snapshot contract requires them.

## 14) Semantic / normalization non-consumability
### Proposed in this checkpoint
`NON_CONSUMABLE` is required when parser has records but cannot safely determine normalized downstream-governing meaning. Typical examples:
- request parsing ambiguity affecting hard-block or derived machine effects,
- parser cannot deterministically apply required template-declared semantics needed for this snapshot,
- unresolved ambiguity in normalized doctor/group identity,
- unresolved ambiguity in downstream-governing slot/demand/eligibility facts,
- normalized model assembly cannot produce complete internally consistent downstream input,
- parser cannot deterministically derive downstream-governing request facts under the declared request grammar.

First-release ICU/HD parser obligations within this semantic stage:
- resolve canonical doctor group by reading snapshot doctor `sourceLocator.path.sectionKey`, locating the declared template section, then reading that section’s canonical `groupId`,
- instantiate normalized slot demand by combining normalized day set + template slot declarations + each slot’s `requiredCountPerDay`,
- treat unresolved/ambiguous doctor-group derivation or unresolved/ambiguous demand instantiation as `NON_CONSUMABLE`.

**Parser uncertainty about downstream-governing facts is not a warning-only condition; it is a non-consumability condition.**

## 15) Consumable results with issues
### Proposed in this checkpoint
`CONSUMABLE` parser results may still include issues when issues do not block deterministic downstream-governing normalization.

First-release direction:
- admission decision is binary (`CONSUMABLE` / `NON_CONSUMABLE`),
- issue severity is not itself an admission surrogate,
- non-blocking issues remain visible via `ParserResult.issues`.

## 16) Provenance expectations in normalized outputs
### Proposed in this checkpoint
This contract imposes a **parser-stage traceability obligation**.

It does **not yet** impose a universal provenance field-shape standard across all normalized entities.

Minimum first-release expectation:
Normalized entities or facts whose origin includes one or more snapshot records must remain traceable to those origin records/locators in stable, recoverable form.

Required clarifications:
- template-only normalized definitions do not require snapshot provenance,
- this obligation requires recoverable linkage back to origin snapshot records/locators where applicable,
- this does not require copying physical sheet references into every normalized object,
- obligation is parser-stage traceability, not yet a universal provenance field-shape standard.

### Still open in this checkpoint
Exact concrete provenance field names/embedding patterns inside each normalized object remain open and are deferred from this contract (see Section 19).

## 17) Explicit handoff to rule engine
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

## 18) Consistency with adjacent contracts
### Repo-settled alignments
- Consistent with snapshot contract: snapshot remains raw, pre-interpretation, trace-preserving input.
- Consistent with domain model: normalized objects are parser/normalizer outputs consumed downstream.
- Consistent with blueprint and roadmap: parser/normalizer phase precedes rule engine and solver/scorer phases.

### Proposed in this checkpoint
- `ParserResult` formalizes parser-stage admission/handoff shape for first release while remaining aligned with snapshot/domain boundaries.

## 19) Explicit deferrals
The following are explicitly deferred and not fixed by this document:
- exact concrete field names for provenance storage inside normalized objects,
- internal implementation decomposition across files/modules,
- whether parser sub-stages are separate passes or merged passes internally,
- richer issue-taxonomy extensions beyond the shared minimum issue shape,
- parser-only diagnostic artifact shapes outside `ParserResult`,
- exact concrete parser function/API signature.

## 20) Current checkpoint status
### Repo-settled in prior docs
- boundary position and high-level role split (snapshot vs parser/normalizer vs domain vs downstream rule engine).

### Proposed and adopted in this checkpoint
- first-release `ParserResult` handoff shape (`normalizedModel`, `issues`, `consumability`),
- binary consumability decision,
- no partial normalized downstream handoff when non-consumable,
- explicit split of structural vs semantic/normalization non-consumability,
- explicit issue schema vs issue channel vs admission decision distinction,
- explicit parser-stage issue propagation authority (`ParserResult.issues` authoritative; request parse issues also carried on normalized `Request` for consumable outputs; entity-local issue detail supplemental only),
- explicit request parsing determinism policy (declared ICU/HD grammar; no guess-on-ambiguity; deterministic failure => `NON_CONSUMABLE`),
- explicit duplicate recognized request-token handling and `EMCC -> PM_OFF` normalization compatibility rule,
- explicit parser-to-rule-engine handoff assumptions and prohibitions.

### Still open / deferred
- internal representation/API details and provenance field-shape standardization beyond traceability obligation.

This document is a first-pass working draft checkpoint intended to unblock implementation planning without reopening broader architecture scope.
