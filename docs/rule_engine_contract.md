# Rule Engine Contract (First-Pass Working Draft)

## 1) Contract status and scope
This document defines the rule engine boundary that sits between normalized parser/normalizer output (`docs/domain_model.md`, `docs/parser_normalizer_contract.md`) and the downstream solver/scorer layers.

It is intended to be concrete enough for implementation planning for rule engine work.

It explicitly separates:
- repo-settled anchors,
- rule-engine-boundary decisions adopted in this checkpoint,
- still-open items in this checkpoint,
- and explicit deferrals.

Scope is limited to rule-engine-stage hard-validity behavior and handoff shape. This is not a solver, scorer, writeback, or execution design document.

Soft-effect evaluation (including `prevDayCallSoftPenaltyTrigger` and `callPreferencePositive`) is **not** in rule-engine scope; those belong to the scorer and are governed by `docs/scorer_contract.md`.

## 2) Contract identity and versioning
Contract identity/version for binding:
- `contractId: RULE_ENGINE`
- `contractVersion: 1`

Version bump rule (normative):
- bump `contractVersion` only when hard-validity semantics or contract-level input/output shape changes.
- do **not** bump for wording cleanup, formatting, added examples, or clarification that does not change behavior.

## 3) Status discipline used in this document
Each normative statement is classified as one of:
- **Repo-settled**: already anchored by existing repo contracts/blueprint/decision log.
- **Proposed in this checkpoint**: adopted here as first-release rule-engine-boundary direction.
- **Still open in this checkpoint**: recognized as unresolved here and left explicit.
- **Deferred**: intentionally out of this checkpoint's decision scope.

## 4) Repo-settled architecture anchors
The following are treated as repo-settled anchors:
- Rule engine is the single runtime authority for hard-validity decisions (blueprint §7.4).
- Rule engine does not rank alternatives by preference and does not perform transport, orchestration, or sheet I/O (blueprint §7.4).
- Rule engine consumes normalized model + candidate assignment state and produces validity decisions + violation reasons (blueprint §7.4).
- Hard constraints override everything else; invalid candidates must never be assigned (blueprint §5).
- The first-release hard-invariant set is enumerated in `docs/domain_model.md` §9.2.
- Fixed assignments admitted at parser boundary carry a scoped parser-stage exception and are first-class normalized input, not allocation results (`docs/parser_normalizer_contract.md` §14; `docs/domain_model.md` §10.1).

## 5) Purpose
Repo-settled intent + checkpoint narrowing:
- Preserve a strict boundary between normalized input and downstream compute over that input.
- Provide a deterministic, auditable predicate the solver can query to keep its search space legal.
- Make hard validity the sole concern of this layer; do not entangle soft-preference or scoring logic.

## 6) Boundary position
Repo-settled:
- Upstream: parser/normalizer emits a `CONSUMABLE` `ParserResult` with `normalizedModel` populated.
- Boundary: rule engine evaluates candidate assignments against the normalized model.
- Downstream: solver/search queries the rule engine; scorer/selector consume valid candidates.

Proposed in this checkpoint:
- Rule engine presents a stateless contract surface to callers. Any internal caching or indexing is an implementation detail that MUST NOT leak into the contract (see §13).

## 7) What this contract governs
This contract governs:
- the shape of hard-validity queries accepted by the rule engine,
- the shape of hard-validity decisions returned,
- the canonical enumerated set of first-release hard-invariant rules,
- the canonical ordering and coding of violation reasons,
- the scoped handling of `FixedAssignment` facts inside the normalized model,
- the statelessness expectation on the public contract,
- the equivalence-test discipline required of any future non-stateless implementation.

## 8) What this contract does not govern
This contract does **not** govern:
- solver search strategy, fill-order policy, or seed/config interpretation (see `docs/solver_contract.md`),
- scoring, ranking, soft-effect evaluation, or objective aggregation (see `docs/scorer_contract.md`),
- writeback mapping, result artifact shape, or operator-facing presentation,
- parser/normalizer admission, snapshot ingestion, or raw sheet interpretation,
- observability transport, logging format, or run orchestration.

## 9) Input shape
Rule engine queries are evaluated against three inputs:
1. **`normalizedModel`** — the `CONSUMABLE` parser output (`docs/domain_model.md`).
2. **`ruleState`** — the set of assignments already present in the candidate under construction, including both `FixedAssignment` entries from the normalized model and any solver-placed `AssignmentUnit` entries accumulated so far.
3. **`proposedUnit`** — a `(dateKey, slotType, unitIndex, doctorId)` tuple the caller wants to evaluate for hard validity.

Normative properties:
- `ruleState` MUST be a pure derivative of the `normalizedModel` plus solver-placed assignments. The rule engine MUST NOT read any state outside these three inputs.
- `proposedUnit.doctorId` MUST NOT be `null` for a hard-validity query. Unfilled-unit representation is a downstream concern, not a rule-engine input.

## 10) Output shape
Rule engine returns a `Decision` object:

```
Decision {
  valid: boolean
  reasons: ViolationReason[]   // non-empty if valid = false; empty if valid = true
}
```

Normative properties:
- When `valid = true`, `reasons` MUST be empty.
- When `valid = false`, `reasons` MUST contain at least one `ViolationReason` entry.
- `reasons` MUST be canonically ordered per §12.
- `reasons` MUST be a list (not a scalar), even when length is 1. This stabilizes the shape against future expansion.

## 11) First-release hard-invariant enumeration
Proposed in this checkpoint (normative, aligned to `docs/domain_model.md` §9.2):

The rule engine MUST enforce at least the following hard invariants for any `proposedUnit`:

1. **`BASELINE_ELIGIBILITY_FAIL`** — `proposedUnit.doctorId` must be a member of a `DoctorGroup` declared eligible for `proposedUnit.slotType` under `EligibilityRule` (template-declared baseline eligibility; `docs/domain_model.md` §9.1).
2. **`SAME_DAY_HARD_BLOCK`** — `proposedUnit.doctorId` must not have `sameDayHardBlock` set in `DailyEffectState` for `proposedUnit.dateKey` (`docs/request_semantics_contract.md` §10; `docs/domain_model.md` §8.2).
3. **`SAME_DAY_ALREADY_HELD`** — `proposedUnit.doctorId` must not already hold another `AssignmentUnit` with the same `dateKey` in `ruleState` (blueprint §5; `docs/domain_model.md` §9.2).
4. **`UNIT_ALREADY_FILLED`** — the `(dateKey, slotType, unitIndex)` identity in `proposedUnit` must not already be filled in `ruleState` (`docs/domain_model.md` §9.2 "one fill per demand unit").
5. **`BACK_TO_BACK_CALL`** — if `proposedUnit.slotType` is a call slot, `proposedUnit.doctorId` must not already hold a call-slot `AssignmentUnit` on `proposedUnit.dateKey - 1` or `proposedUnit.dateKey + 1` in `ruleState` (`docs/domain_model.md` §9.2). Call-slot identity is template-declared; for ICU/HD first release, call slots are `MICU_CALL` and `MHD_CALL`.

No soft-effect triggers, preference signals, or scoring concerns are evaluated by the rule engine under this contract.

## 12) Canonical violation ordering
Proposed in this checkpoint:

When `valid = false`, `reasons` MUST be ordered in the following canonical sequence (cheapest-first, table-lookup-first):

1. `BASELINE_ELIGIBILITY_FAIL`
2. `SAME_DAY_HARD_BLOCK`
3. `SAME_DAY_ALREADY_HELD`
4. `UNIT_ALREADY_FILLED`
5. `BACK_TO_BACK_CALL`

Normative consequences:
- When `valid = false`, `reasons` MUST include every applicable violation. Partial violation lists are non-compliant.
- Entries in `reasons` MUST appear in the canonical order above. Canonical ordering is normative regardless of list length.
- `reasons` MUST be non-empty when `valid = false` and MUST be empty when `valid = true`.
- Callers MAY use list membership for assertions. Because completeness is required, list length carries meaningful information (exactly the count of applicable violations) and is not an implementation-defined value.

## 13) Statelessness and optional internal caching
Proposed in this checkpoint (normative):
- The rule engine public contract is stateless. A query `(normalizedModel, ruleState, proposedUnit) → Decision` is a pure function of its three inputs and MUST produce identical `Decision` outputs for identical inputs across repeated invocations.
- Implementations MAY internally cache or index over `normalizedModel` and `ruleState` as an optimization, provided that cached results remain indistinguishable from a fresh evaluation.
- Implementations MUST NOT expose mutable session handles, "prepare-then-query" lifecycles, or out-of-band configuration channels through the public contract.

An implementation that violates any of these is contract-broken regardless of its observed performance characteristics.

## 14) Equivalence-test discipline for future non-stateless implementations
Proposed in this checkpoint (normative):

Any future rule engine implementation that deviates from a straightforward stateless evaluation — for example, an incremental-state implementation that maintains indexed occupancy and call-adjacency structures across solver `tryAdd`/`undo` operations — is permitted only under the following discipline:
1. A shared test corpus of `(normalizedModel, ruleState, proposedUnit) → expected Decision` fixtures MUST be maintained alongside this contract. The corpus is contract-owned, not implementation-owned.
2. The new implementation MUST produce byte-identical `Decision` outputs, including canonical violation ordering, across the entire corpus.
3. Any `Decision` divergence from the corpus is a contract-breaking defect in the new implementation; shipping it is prohibited until the divergence is closed.
4. The corpus MUST include at least one fixture per hard invariant enumerated in §11, plus fixtures covering the `FixedAssignment` scoped admission in §15.

This discipline anchors any faster implementation to the stateless reference's behavior without pretending the reference and its optimization are drop-in substitutes.

First-release scope: only a stateless implementation is required; no equivalence-test corpus fixture set is mandated to ship in first release beyond the minimum hard-invariant-per-rule coverage declared above when an incremental implementation is proposed.

## 15) Fixed assignment handling
Repo-settled anchor:
- `FixedAssignment` is admitted at the parser boundary under the scoped parser-stage override described in `docs/parser_normalizer_contract.md` §14.
- `FixedAssignment` is first-class normalized input, not an allocation result (`docs/domain_model.md` §10.1).

Proposed in this checkpoint (normative):
- The rule engine MUST NOT be asked to adjudicate the validity of a `FixedAssignment` against itself. Fixed assignments enter `ruleState` as facts; the scoped admission exception is already resolved upstream.
- The rule engine MUST apply downstream-validity checks for any `proposedUnit` in the normal way, including against fixed-assignment neighbors. For example, `BACK_TO_BACK_CALL` MUST fire against a fixed call on an adjacent date exactly as it would against a solver-placed call.
- The rule engine MUST NOT widen the scoped parser-stage exception to any `proposedUnit` other than the fixed assignment it was granted for.

## 16) Separation from soft-effect evaluation
Proposed in this checkpoint (normative):
- `prevDayCallSoftPenaltyTrigger`, `callPreferencePositive`, and any other soft effect MUST NOT be evaluated by the rule engine.
- Soft-effect reading is the scorer's responsibility; the scorer reads `DailyEffectState` directly from the normalized model (`docs/scorer_contract.md`).
- The rule engine MUST NOT expose a general "what triggers are active on this date" query. Callers that need soft-effect information MUST read `DailyEffectState` directly.

## 17) Determinism
Proposed in this checkpoint (normative):
- Given identical `(normalizedModel, ruleState, proposedUnit)` inputs, the rule engine MUST return byte-identical `Decision` outputs, including identical `reasons` ordering and content.
- Determinism is required within a single implementation on a single platform. Cross-implementation determinism is not required but is testable via the equivalence-test corpus per §14.

## 18) Consistency with adjacent contracts
Repo-settled alignments:
- Consistent with `docs/parser_normalizer_contract.md`: rule engine consumes `CONSUMABLE` `ParserResult` outputs only; rule engine does not recover lost parser meaning.
- Consistent with `docs/domain_model.md`: rule engine operates on `AssignmentUnit`, `DoctorGroup`, `SlotType`, `DailyEffectState`, `FixedAssignment`, and related normalized identities.
- Consistent with blueprint §5 and §7.4: rule engine is the single hard-validity authority and does not rank alternatives.

Proposed in this checkpoint:
- This contract formalizes the stateless evaluation surface and violation-reason canonical ordering while remaining aligned with parser/domain/blueprint boundaries.

## 19) Explicit deferrals
The following are explicitly deferred and not fixed by this document:
- concrete function/API signatures and language-specific shapes,
- internal module decomposition,
- incremental-state implementation design beyond the equivalence-test discipline in §14,
- cross-implementation equivalence-test fixture authoring cadence,
- extension beyond the first-release hard-invariant set,
- richer violation-reason subfields (such as referenced entity identities beyond the canonical code) beyond what `ValidationIssue` already allows.

## 20) Current checkpoint status
### Repo-settled in prior docs
- rule engine boundary role (blueprint §7.4),
- hard-invariant set (`docs/domain_model.md` §9.2),
- fixed-assignment parser-boundary admission (`docs/parser_normalizer_contract.md` §14).

### Proposed and adopted in this checkpoint
- stateless public contract with `(normalizedModel, ruleState, proposedUnit) → Decision` shape,
- full-violation-list return with canonical ordering (§12),
- first-release enumerated hard-rule set with stable codes (§11),
- scoped fixed-assignment handling (§15),
- explicit separation from soft-effect evaluation (§16),
- equivalence-test discipline for any future non-stateless implementation (§14).

### Still open / deferred
- concrete API signatures and module decomposition,
- first incremental-implementation test-corpus authoring (triggered only if an incremental implementation is proposed).

This document is a first-pass working draft checkpoint intended to unblock implementation planning without reopening broader architecture scope.
