# Parser–Normalizer Contract (First-Pass Working Draft)

## 1) Contract status and scope
This document defines the parser–normalizer boundary that connects snapshot input (`docs/snapshot_contract.md`) to normalized domain output (`docs/domain_model.md`).

It is intended to be concrete enough for implementation planning for parser/normalizer work.

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
- Upstream: snapshot contract provides raw records and structural trace fields. The production Apps Script adapter that emits the snapshot is pinned in `docs/snapshot_adapter_contract.md` (added under `docs/decision_log.md` D-0036 / D-0040 / D-0041 / D-0042 / D-0043).
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
- reading `prefilledAssignmentRecords` at parser boundary,
- exact deterministic resolution of prefilled doctor text against names entered in doctor-entry sections,
- interpretation of template-declared lower-shell row/slot structure for populated prefilled cells,
- construction of normalized fixed-assignment facts for downstream use when prefilled assignments are resolvable,
- parser-stage issue emission with enough source context for loud failure reporting.

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

For this checkpoint, parser input explicitly includes snapshot `prefilledAssignmentRecords` and template-declared lower-shell parse surfaces used to interpret those records.

First-release ICU/HD template interpretation inputs used at this boundary include:
- section-based doctor-group derivation declarations on `inputSheetLayout.sections[]` (`sectionKey` + canonical `groupId`), interpreted from snapshot doctor `sourceLocator.path.sectionKey`,
- slot declarations with `requiredCountPerDay` for fixed per-day demand instantiation across the normalized day set,
- explicit baseline eligibility declarations (`slotId` + `eligibleGroups`).

### Proposed in this checkpoint
This contract defines no separate pre-parser rejection channel. Malformed or incomplete snapshot-shaped input is handled within parser result production.

Boundary rule:
- even malformed top-level snapshot input is handled through `ParserResult`, not through out-of-band rejection;
- parser may return `NON_CONSUMABLE` for malformed top-level input.

## 9) Parser outputs
### Proposed in this checkpoint (first-release decision; updated per `docs/decision_log.md` D-0037 to add `scoringConfig` output)
Parser handoff uses one top-level object:
- `ParserResult`

Proposed top-level components:
- `normalizedModel`
- `scoringConfig`
- `issues`
- `consumability`

Proposed first-release admission rule:
- `consumability = CONSUMABLE`: `normalizedModel` is present and downstream-consumable; `scoringConfig` is present and carries the parser's overlay of operator-edited sheet values onto template defaults. Overlay rule: **sheet wins where the cell is present and parseable; template defaults backstop where the sheet cell is absent or blank.** Malformed populated cells (operator-edited cells with non-numeric content, mis-signed values that violate `docs/scorer_contract.md` §10 / §15 sign orientation, etc.) are admission-blocking per §14 and force `NON_CONSUMABLE` rather than silently falling back to defaults — the §9 backstop applies only to absent / blank cells, not to malformed populated cells. `scoringConfig` shape matches `docs/scorer_contract.md` v3 §11 — `weights` (required), `pointRules` (required), `curves` (optional).
- `consumability = NON_CONSUMABLE`: `normalizedModel = null` AND `scoringConfig = null`; downstream receives no partial normalized handoff and no partial scoring config. The same admission discipline applies to both (an operator-edited sheet whose snapshot fails admission cannot be trusted for scoring policy either).
- for `NON_CONSUMABLE` request parses, any partially recognized subset detail may appear only in `ParserResult.issues[*].context` and must not be emitted as a normalized side payload.

`scoringConfig.pointRules` key derivation rule (added under `docs/decision_log.md` D-0037): the parser maps snapshot `callPointRecords` (keyed by `(callPointRowKey, dayIndex)` per `docs/snapshot_contract.md` §11A) onto `ScoringConfig.pointRules` (keyed by `(slotType, dateKey)` per `docs/scorer_contract.md` §11) using two template-anchored translations:
1. `callPointRowKey → slotType` via the `pointRows[].slotType` binding declared in `docs/template_artifact_contract.md` §9 (each point row declares the call slot it weights — for ICU/HD first release, `MICU_CALL_POINT` binds to `MICU_CALL`, `MHD_CALL_POINT` binds to `MHD_CALL`).
2. `dayIndex → dateKey` via the parser's already-established day-axis lookup from `dayRecords`.

`pointRules` covers only call-slot slotTypes (those with `slotKind == "CALL"` per `docs/template_artifact_contract.md` §5); standby and other non-call slots are not in `pointRules`, and `pointBalance*` components in `docs/scorer_contract.md` count only call-slot assignments per their existing scope.

**Producer-coverage requirement (added under `docs/decision_log.md` D-0038, revising D-0037 sub-decision 5).** `scoringConfig.pointRules` MUST cover the full cross-product of `(slotType, dateKey)` where `slotType` ranges over `slotTypes[]` filtered by `slotKind == "CALL"` and `dateKey` ranges over the period's `dayRecords`. Coverage is total — every call-slot × period-day pair has an entry. The parser builds completeness from sheet-derived populated cells plus template-derived defaults (the §9 overlay rule above): sheet cells overlay where present and parseable; template defaults backstop where the sheet cell is absent or blank; together the two sources span the cross-product. A `scoringConfig.pointRules` map that fails to cover the cross-product is admission-blocking per §14 and forces `NON_CONSUMABLE`, the same discipline that already applies to mis-signed component weights. The downstream scorer per `docs/scorer_contract.md` §11 raises on missing `(slotType, dateKey)` keys at score time — there is no silent fallback to `1.0`. Producer-coverage at parser admission and consumer fail-loud at score time together close the architectural gap that the original D-0037 sub-decision 5 silent-fallback rule had left open.

This `ParserResult` shape is adopted in this checkpoint and is not claimed as previously repo-settled. The `scoringConfig` field was added per `docs/decision_log.md` D-0037 to close the producer-consumer seam between this contract and `docs/scorer_contract.md` §15 — the scorer contract had declared since M2 C1 closure that operator-tuneable weights flow from the parser boundary as `scoringConfig`, but this contract had not previously declared `scoringConfig` as a parser output. The bidirectional contract-audit rule added to `docs/delivery_plan.md` §14 closes the audit-coverage gap that allowed this seam to remain open across multiple checkpoints.

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
- unresolved, invalid, or missing upstream doctor-group declaration linkage (snapshot `sourceLocator.path.sectionKey` → `inputSheetLayout.sections[]` → canonical `groupId`),
- unresolved, invalid, or missing upstream slot-demand declarations needed for deterministic instantiation (`slots[]`, `requiredCountPerDay`, normalized day set),
- unresolved, invalid, or missing upstream eligibility declarations needed for deterministic instantiation (`eligibility[]` as `slotId` + `eligibleGroups`),
- normalized model assembly cannot produce complete internally consistent downstream input,
- parser cannot deterministically derive downstream-governing request facts under the declared request grammar.

Scoring-config parser-stage non-consumability cases (added under `docs/decision_log.md` D-0037; coverage requirement added under D-0038):
- mis-signed operator-edited component weight (a penalty component supplied as positive, or a reward component supplied as negative — sign orientation is a property of the component, not the weight, per `docs/scorer_contract.md` §10 / §15),
- malformed or non-numeric operator-edited cell value where `scoringConfigRecords` carries a populated cell (parser must not silently substitute a default; an unparseable cell is an admission-blocking defect, not a fall-back-to-default condition),
- incomplete `scoringConfig.pointRules` coverage — any `(slotType, dateKey)` pair from the cross-product of call-slot `slotTypes` and the period's `dateKeys` not present as a `pointRules` entry is admission-blocking per the producer-coverage requirement in §9 (D-0038 reverses the original D-0037 sub-decision 5 silent-fallback rule; producer obligation is total coverage from sheet-cell overlay plus template-default backstop combined).

For populated `scoringConfigRecords` cells, parser must apply the same "do not silently ignore meaningful cell content" discipline as for prefilled assignments: parser must either deterministically interpret the value (sheet wins per the overlay rule in §9) or emit parser-stage issues and return `NON_CONSUMABLE`.

Prefilled-assignment parser-stage non-consumability cases (checkpoint 3):
- prefilled doctor name not found in doctor-entry section names,
- ambiguous doctor identity for prefilled doctor text,
- same doctor duplicated across groups such that identity is not uniquely resolvable,
- unresolved or broken date identity for a populated prefilled cell,
- populated prefilled cell inside declared lower-shell parse surfaces that cannot be mapped to declared slot/day structure,
- corrupted duplicate mapping for the same slot/day,
- same doctor fixed into two slots on the same date.

For populated prefilled cells inside declared parse surfaces, parser must not silently ignore meaningful cell content: parser must either deterministically normalize it or emit parser-stage issues and return `NON_CONSUMABLE`.

Allowed operator-priority fixed-assignment override at parser boundary (checkpoint 3):
- if a prefilled assignment is structurally and semantically resolvable at parser boundary, parser may admit and normalize that fixed assignment even when that specific fixed assignment would otherwise violate request-derived hard block, baseline eligibility, or ordinary back-to-back prohibition,
- this is not parser adjudication of full candidate legality,
- this override applies only to that fixed assignment itself,
- parser is not relaxing the general downstream rule set,
- downstream legality checking remains downstream.

Separation rule (checkpoint 3):
- parser ambiguity/unresolvability for prefilled assignments => `NON_CONSUMABLE`,
- allowed fixed-assignment override for a resolvable prefilled assignment => parsable/admitted and normalized as a real downstream-governing fact,
- legality evaluation beyond this parser-boundary exception model remains downstream.

First-release ICU/HD parser obligations within this semantic stage:
- resolve canonical doctor group by reading snapshot doctor `sourceLocator.path.sectionKey`, locating the declared template section in `inputSheetLayout.sections[]`, then reading that section’s canonical `groupId`,
- instantiate normalized slot demand by combining normalized day set + template slot declarations + each slot’s `requiredCountPerDay`,
- instantiate baseline eligibility from template artifact `eligibility[]` declarations (`slotId` + `eligibleGroups`),
- treat unresolved/invalid/ambiguous doctor-group derivation, demand instantiation, or eligibility instantiation as `NON_CONSUMABLE`.

Parser must not recover these downstream-governing facts through hidden defaults, guesswork, or silent inference when upstream declaration surfaces are unresolved or invalid.

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
- template-owned group/slot/eligibility/demand meaning from raw sheet structure or parser-internal fallback defaults,
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
