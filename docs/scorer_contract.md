# Scorer Contract (First-Pass Working Draft)

## 1) Contract status and scope
This document defines the scorer boundary that sits between the solver's valid-candidate output and the downstream selector/retention layer.

It is intended to be concrete enough for implementation planning for scorer work.

It explicitly separates:
- repo-settled anchors,
- scorer-boundary decisions adopted in this checkpoint,
- still-open items in this checkpoint,
- and explicit deferrals.

Scope is limited to scorer-stage ranking behavior and handoff shape. This is not a solver, rule engine, writeback, or execution design document.

Hard validity is **not** in scorer scope; the rule engine is the sole hard-validity authority (`docs/rule_engine_contract.md`).

## 2) Contract identity and versioning
Contract identity/version for binding:
- `contractId: SCORER`
- `contractVersion: 1`

Version bump rule (normative):
- bump `contractVersion` only when scoring semantics, direction, component enumeration, or contract-level input/output shape changes.
- do **not** bump for weight-value tuning, wording cleanup, formatting, added examples, or clarification that does not change behavior.

## 3) Status discipline used in this document
Each normative statement is classified as one of:
- **Repo-settled**: already anchored by existing repo contracts/blueprint/decision log.
- **Proposed in this checkpoint**: adopted here as first-release scorer-boundary direction.
- **Still open in this checkpoint**: recognized as unresolved here and left explicit.
- **Deferred**: intentionally out of this checkpoint's decision scope.

## 4) Repo-settled architecture anchors
The following are treated as repo-settled anchors:
- Score direction is `HIGHER_IS_BETTER` (blueprint §5; `docs/domain_model.md` §4.2, §11.1).
- Scorer ranks valid rosters using explicit scoring logic and does not make invalid rosters acceptable (blueprint §7.6).
- First-release component identifiers follow v1-compatible naming: `unfilledPenalty`, `pointBalanceWithinSection`, `pointBalanceGlobal`, `spacingPenalty`, `preLeavePenalty`, `crReward`, `dualEligibleIcuBonus`, `standbyAdjacencyPenalty`, `standbyCountFairnessPenalty` (`docs/domain_model.md` §11.2).
- `CR` remains a soft preference signal and never overrides hard validity (`docs/domain_model.md` §4.1; `docs/request_semantics_contract.md` §10).
- `prevDayCallSoftPenaltyTrigger` is soft but penalty-bearing, with policy-controlled magnitude (`docs/domain_model.md` §11.3).

## 5) Purpose
Repo-settled intent + checkpoint narrowing:
- Rank valid rosters using explicit, stable, explainable scoring logic.
- Preserve the `HIGHER_IS_BETTER` direction invariant across all implementations.
- Produce a `ScoreResult` that is both a total and a component breakdown, so scores are auditable at component granularity.

## 6) Boundary position
Repo-settled:
- Upstream: solver emits a `CandidateSet` of valid rosters (or an `UnsatisfiedResult`; see `docs/solver_contract.md`).
- Boundary: scorer ranks every candidate in the `CandidateSet` by applying component-wise scoring against the normalized model and a scoring configuration.
- Downstream: selector + retention policy consume scored candidates and produce the final `AllocationResult` or persisted retention artifacts.

Proposed in this checkpoint:
- Scorer is a pure function of `(allocation, normalizedModel, scoringConfig)`. No solver coupling, no lifecycle, no side effects.

## 7) What this contract governs
This contract governs:
- the shape of scorer input,
- the shape of `ScoreResult` output (including required component breakdown),
- the `HIGHER_IS_BETTER` direction invariant,
- the `crReward` diminishing-marginal-utility curve property,
- the scorer's relationship to `DailyEffectState` for soft-effect reading,
- operator-tuneable weight surface semantics,
- the direction-guard invariant required of any implementation.

## 8) What this contract does not govern
This contract does **not** govern:
- solver search strategy, candidate generation, or fill-order policy (see `docs/solver_contract.md`),
- hard-validity evaluation (see `docs/rule_engine_contract.md`),
- retention policy or selector behavior,
- writeback mapping, result artifact shape, or operator-facing presentation,
- concrete weight values for ICU/HD first release (template-carried; v1-equivalent defaults pending implementation slice),
- parser/normalizer admission, snapshot ingestion, or raw sheet interpretation.

## 9) Input shape
Scorer queries are evaluated against three inputs:
1. **`allocation`** — a complete candidate `AllocationUnits` set (the full roster under evaluation, including `FixedAssignment` entries from the normalized model and all solver-placed `AssignmentUnit` entries).
2. **`normalizedModel`** — the `CONSUMABLE` parser output (`docs/domain_model.md`), including `DailyEffectState`, `DoctorGroup` membership, `SlotType` identities, and `Request` facts.
3. **`scoringConfig`** — the scoring configuration carrying component weights and curve parameters. See §11.

Normative properties:
- The scorer MUST NOT read any state outside these three inputs. No environment variables, no clocks, no filesystem.
- `allocation` MUST be a valid roster (no hard-validity violations). Scoring an invalid allocation is outside contract scope and MAY produce undefined output.

## 10) Output shape
Scorer returns a `ScoreResult` object:

```
ScoreResult {
  totalScore: number
  components: {
    [componentName: string]: number
  }
  direction: "HIGHER_IS_BETTER"   // constant; included for audit
}
```

Normative properties:
- `totalScore` MUST be the signed aggregate of component contributions under `HIGHER_IS_BETTER`.
- `components` MUST include every first-release component identifier enumerated in §4 / `docs/domain_model.md` §11.2, even when the component contributes zero.
- Reward components contribute non-negatively to `totalScore`; penalty components contribute non-positively. Sign orientation is a property of the component, not the weight.
- `direction` MUST be the literal string `"HIGHER_IS_BETTER"`. Implementations MUST NOT emit a different value.
- `ScoreResult` MUST be produced for every scored candidate. Omitting the component breakdown and returning only `totalScore` is a contract violation.

## 11) Scoring configuration shape
Proposed in this checkpoint (normative):

```
scoringConfig {
  weights: {
    [componentName: string]: number
  }
  curves?: {
    crReward?: { /* curve-specific parameters */ }
    // additional curve blocks may appear for future components
  }
}
```

First-release rules:
- `weights` MUST include an entry for every first-release component identifier enumerated in §4 / `docs/domain_model.md` §11.2. Missing entries are a configuration defect.
- `weights` values are operator-tuneable at run-scope granularity. See §15.
- Templates ship default weights; operator-supplied values override template defaults at run time.
- `curves.crReward` parameters, when present, configure the diminishing-marginal-utility curve referenced in §12. First-release implementations MAY ship a fixed curve shape with limited tuneable parameters.

## 12) `crReward` diminishing-marginal-utility property
Proposed in this checkpoint (normative):

`crReward` MUST implement **diminishing marginal utility per doctor**:
- For any doctor `d`, the kth honored `CR` request (where k ≥ 2) MUST contribute strictly less reward than the (k − 1)th honored `CR` request for the same doctor within the same roster period.
- The first honored `CR` for a doctor contributes the maximum reward magnitude per `CR` for that doctor within that period.
- Exact curve shape (linear-decreasing, geometric, logarithmic, etc.) is an implementation detail documented alongside the shipped scorer, subject to the strict-monotonic-decrease property above.

Rationale: a flat per-CR weight would be indifferent to whether a single doctor hoards all honored `CR` requests. A diminishing curve rewards spreading honored `CR`s across doctors while still preferring "more honored `CR`s is better" past the seeding floor delivered by the solver (see `docs/solver_contract.md`).

## 13) Direction-guard invariant
Proposed in this checkpoint (normative):

For any valid `allocation` with `ScoreResult S1`, consider an otherwise-identical `allocation'` constructed by converting one filled `AssignmentUnit` into an unfilled unit (`doctorId = null`). Let `S2` be the score of `allocation'`. The following invariant MUST hold:

```
S2.totalScore ≤ S1.totalScore
```

A scorer implementation that can produce `S2.totalScore > S1.totalScore` is contract-broken, independent of any other behavior. This invariant is testable as a property over generated inputs and MUST be exercised in any scorer implementation's test suite.

Rationale: the property operationalizes `HIGHER_IS_BETTER` against silent direction inversions (sign errors, accidental penalty inversions, component swaps) that might otherwise pass integration-level testing.

## 14) Soft-effect reading
Proposed in this checkpoint (normative):
- The scorer reads `DailyEffectState` (and, where relevant, normalized `Request` facts) directly from `normalizedModel`.
- The scorer MUST NOT delegate soft-effect evaluation to the rule engine. The rule engine handles hard validity only (`docs/rule_engine_contract.md` §16).
- First-release soft effects read by the scorer:
  - `prevDayCallSoftPenaltyTrigger` — drives `preLeavePenalty` when a doctor is on call the day before a trigger date,
  - `callPreferencePositive` — drives `crReward` for honored `CR` requests.
- Additional soft-effect classes are deferred.

## 15) Operator-tuneable weight surface (v1 parity)
Proposed in this checkpoint (normative):

- Scorer component weights are operator-tuneable in first release via sheet inputs, matching v1 behavior.
- Templates ship default weights; operator-supplied values extracted from the sheet override template defaults at run time.
- Weight extraction happens at parser boundary; the extracted weights flow into the pipeline as part of `scoringConfig`, separate from the `normalizedModel` (so the model carries problem shape and the config carries ranking policy).
- Operator-supplied weights MUST preserve per-component sign orientation: a reward component remains a reward, a penalty component remains a penalty, regardless of the numeric weight the operator supplies.
- Blueprint §16's current "routine variation" wording is narrower than this reality and is scheduled for a clarifying patch consistent with this contract.

## 16) Pure-function normative shape; streaming as permitted optimization
Proposed in this checkpoint (normative):
- The scorer's public contract is a pure function `score(allocation, normalizedModel, scoringConfig) → ScoreResult`.
- Implementations MAY internally compute scores incrementally or via streaming deltas applied during solver search, as an optimization.
- Any streaming/delta implementation MUST produce `ScoreResult` values byte-identical (within floating-point reproducibility bounds declared by the implementation) to the pure-function evaluation over the same inputs.
- Streaming implementations MUST NOT leak lifecycle state into the public contract; callers MUST be able to invoke the scorer as a stateless service.

## 17) Determinism
Proposed in this checkpoint (normative):
- Given identical `(allocation, normalizedModel, scoringConfig)` inputs, the scorer MUST return identical `ScoreResult` outputs within a single implementation on a single platform.
- Cross-language/cross-platform determinism is not guaranteed; floating-point ordering and RNG choices differ across runtimes.
- Reproducibility within the pipeline relies on (a) deterministic solver candidate generation under a fixed seed, and (b) deterministic scorer evaluation per this section.

## 18) Consistency with adjacent contracts
Repo-settled alignments:
- Consistent with `docs/domain_model.md` §11: component identifiers and direction match §11.2 exactly.
- Consistent with `docs/rule_engine_contract.md`: scorer never adjudicates hard validity; rule engine never ranks.
- Consistent with blueprint §7.6: scorer does not make invalid rosters appear acceptable and does not implicitly change score direction.

Proposed in this checkpoint:
- This contract formalizes the pure-function shape, required component breakdown, direction-guard invariant, and `crReward` diminishing-marginal-utility property while remaining aligned with domain-model / rule-engine boundaries.

## 19) Explicit deferrals
The following are explicitly deferred and not fixed by this document:
- concrete weight values for ICU/HD first release (reference v1 during implementation slice),
- exact `crReward` curve shape beyond the strict-monotonic-decrease property,
- additional soft-effect classes beyond `prevDayCallSoftPenaltyTrigger` and `callPreferencePositive`,
- operator-tuneable surface beyond component weights (for example, tuneable CR-curve parameters exposed to operators),
- per-unit-position fairness components (required only when a future department has `requiredCount > 1`; see `docs/future_work.md`),
- `workloadWeight` on `SlotTypeDefinition` (`docs/domain_model.md` §7.6 deferred enrichment),
- cross-period scoring concerns (multi-month fairness, campaign-level normalization).

## 20) Current checkpoint status
### Repo-settled in prior docs
- scorer boundary role (blueprint §7.6),
- score direction (blueprint §5; `docs/domain_model.md` §4.2, §11.1),
- first-release component identifier set (`docs/domain_model.md` §11.2),
- soft preference / soft penalty semantics (`docs/domain_model.md` §11.3).

### Proposed and adopted in this checkpoint
- pure-function public contract with `(allocation, normalizedModel, scoringConfig) → ScoreResult` shape,
- required component breakdown in every `ScoreResult`,
- `crReward` diminishing-marginal-utility property,
- scorer-owned soft-effect reading (separation from rule engine),
- operator-tuneable weight surface (v1 parity),
- direction-guard invariant (§13) as contract-level property test,
- streaming/delta scoring permitted as optimization under identical-output discipline.

### Still open / deferred
- concrete weight defaults and `crReward` curve shape,
- operator-tuneable curve parameters beyond weights,
- per-unit-position fairness and cross-period scoring.

This document is a first-pass working draft checkpoint intended to unblock implementation planning without reopening broader architecture scope.
