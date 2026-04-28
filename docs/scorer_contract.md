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
- `contractVersion: 3`

Version bump rule (normative):
- bump `contractVersion` only when scoring semantics, direction, component enumeration, or contract-level input/output shape changes.
- do **not** bump for weight-value tuning, wording cleanup, formatting, added examples, or clarification that does not change behavior.

### 2.1 Version history
- **v1 (2026-04-23, PR #63):** initial scorer contract closure per `docs/decision_log.md` D-0025. `ScoringConfig` shape `{weights, curves?}`.
- **v2 (2026-04-27, PR #81):** `ScoringConfig` shape grows a required `pointRules: {[(slotType: string, dateKey: string)]: number}` field carrying per-`(slotType, dateKey)` call-point weights derived from operator-edited per-day call-point cells per `docs/template_artifact_contract.md` §9. `pointBalance*` components MUST consume `pointRules` per §11 (the M2 C4 T2 placeholder of "1 point per call" is superseded). The bump is a required-fields-add — v1-targeted callers that supply only `weights` are non-compliant against v2 — and therefore takes a `contractVersion` bump per the rule above. See `docs/decision_log.md` D-0037.
- **v3 (2026-04-28, this PR):** `spacingPenalty` curve shape pinned per new normative §12A. Computational semantics tighten: per-pair contribution shape is now `weight / 2^(gap - 2)` for gap ∈ {2..6}, zero past gap = 7 — replacing the v2-era binary `gap < 3` count. v2-targeted callers supplying the same `ScoringConfig` see different `spacingPenalty.score` values for the same allocation, so consumers relying on the identifier `contractVersion: 2` for v2 ranking behavior need the version signal. The `ScoringConfig` public shape itself is unchanged (`weights[spacingPenalty]` stays a single scalar). See `docs/decision_log.md` D-0039.

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
- Downstream: selector consumes scored candidates and produces the final `AllocationResult`, applying retention policy per `docs/selector_contract.md` §13 (with sidecar artifacts under `FULL` retention per `docs/selector_contract.md` §14).

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
- `allocation` MUST be free of rule-engine hard-rule violations (`docs/rule_engine_contract.md` §11). An allocation with unfilled demand units (`AssignmentUnit` entries with `doctorId = null`) IS in scope; such units produce `unfilledPenalty` contributions per §11.2 and are the specific case the direction-guard invariant in §13 exercises. Scoring an allocation with rule-engine hard-rule violations is outside contract scope and MAY produce undefined output.

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
Proposed in this checkpoint (normative; updated under v2 per §2.1):

```
scoringConfig {
  weights: {
    [componentName: string]: number
  }
  pointRules: {
    [(slotType: string, dateKey: string)]: number
  }
  curves?: {
    crReward?: { /* curve-specific parameters */ }
    // additional curve blocks may appear for future components
  }
}
```

First-release rules:
- `weights` MUST include an entry for every first-release component identifier enumerated in §4 / `docs/domain_model.md` §11.2. Missing entries are a configuration defect.
- `weights` values are operator-tuneable at run-scope granularity per §15.
- `pointRules` carries per-`(slotType, dateKey)` call-point weights derived from the operator-facing per-day call-point cells declared in `docs/template_artifact_contract.md` §9 `pointRows` (the cells M1-generated rosters carry as `MICU Call Point` / `MHD Call Point` rows per `docs/sheet_generation_contract.md` §8). `pointBalance*` components MUST consume `pointRules` as the per-call point weight rather than a "1 point per call" placeholder. Coverage is total: producers MUST emit a `pointRules` entry for every `(slotType, dateKey)` pair where `slotType` is a call-slot per `slotTypes[].slotKind == "CALL"` and `dateKey` ranges over the period's `dayRecords`. Missing entries cause `score()` to raise — there is no silent fallback. The producer obligation lives on the parser overlay path per `docs/parser_normalizer_contract.md` §9; admission of a `scoringConfig` whose `pointRules` does not cover the cross-product is parser-side admission-blocking. Per-key fail-loud is the architectural mate of the construction-time required-pointRules rule (D-0037 sub-decision 9): once the scorer is invoked with a model + allocation + config, every call-allocation lookup is a direct dict lookup; absent keys signal a producer defect rather than a legitimate "no override" state. (D-0038 supersedes the original D-0037 sub-decision 5 silent-fallback rule.)
- `pointRules` values are operator-tuneable at run-scope granularity per §15 — operator edits to the per-day call-point cells flow into the scorer through the same overlay path that `weights` does (sheet wins; template defaults backstop), per `docs/decision_log.md` D-0037.
- Templates ship default weights AND default per-day call-point values (the latter via `pointRows.defaultRule` weekday/weekend mapping per `docs/template_artifact_contract.md` §9); operator-supplied values override both at run time.
- `curves.crReward` parameters, when present, configure the diminishing-marginal-utility curve referenced in §12. First-release implementations MAY ship a fixed curve shape with limited tuneable parameters; operator-tuneable curve parameters remain `docs/future_work.md` FW-0007 deferred.

## 12) `crReward` diminishing-marginal-utility property
Proposed in this checkpoint (normative):

`crReward` MUST implement **diminishing marginal utility per doctor**:
- For any doctor `d`, the kth honored `CR` request (where k ≥ 2) MUST contribute strictly less reward than the (k − 1)th honored `CR` request for the same doctor within the same roster period.
- The first honored `CR` for a doctor contributes the maximum reward magnitude per `CR` for that doctor within that period.
- Exact curve shape (linear-decreasing, geometric, logarithmic, etc.) is an implementation detail documented alongside the shipped scorer, subject to the strict-monotonic-decrease property above.

Rationale: a flat per-CR weight would be indifferent to whether a single doctor hoards all honored `CR` requests. A diminishing curve rewards spreading honored `CR`s across doctors while still preferring "more honored `CR`s is better" past the seeding floor delivered by the solver (see `docs/solver_contract.md`).

## 12A) `spacingPenalty` geometric-decay property (added under `docs/decision_log.md` D-0039)
Normative:

`spacingPenalty` MUST implement a **geometric-decay penalty across same-doctor call-pair gaps** with an explicit zero cutoff. The properties below are scoped explicitly by the operator-supplied `weights[spacingPenalty]` value because `0` is a valid weight (§10 / §15 — penalty components contribute non-positively, and `0` is non-positive; an operator who wants to disable spacingPenalty entirely supplies `0`).

- For any doctor `d` and any pair of `d`'s call-slot placements with gap `g` days (`g = 2` is the smallest soft-window gap; `g = 1` is hard-blocked by `BACK_TO_BACK_CALL` per `docs/rule_engine_contract.md` §11), the per-pair contribution to `spacingPenalty` MUST be:
  - **When `weights[spacingPenalty] < 0`**: non-zero with absolute magnitude strictly decreasing as `g` increases, for `g` in the soft-window range `[2, MAX_SOFT_GAP_DAYS]`; exactly zero for `g > MAX_SOFT_GAP_DAYS`.
  - **When `weights[spacingPenalty] = 0`**: exactly zero for every `g`. Component is effectively disabled; the strict-decrease and non-zero requirements below are vacuously satisfied.
- **Strict monotonic decrease across the soft window** (when `weights[spacingPenalty] < 0`): contribution at `g = k` MUST be strictly less in absolute magnitude than contribution at `g = k − 1`, for `k ∈ {3, …, MAX_SOFT_GAP_DAYS}`. When `weights[spacingPenalty] = 0` this property is vacuously satisfied (every contribution is zero, so no two consecutive-gap contributions are unequal).
- **Zero past cutoff**: contribution at `g ≥ MAX_SOFT_GAP_DAYS + 1` MUST be exactly zero (independent of weight; cutoff is part of the curve definition).
- The total `spacingPenalty.score` is the sum of per-pair contributions across all same-doctor call-pair combinations in the allocation. Sign-correctness comes from `weights[spacingPenalty]` (which is non-positive per §10 / §15) — the curve formula is sign-preserving, so a non-positive weight produces a non-positive total.

First-release fixed shape (per D-0039):
- `MAX_SOFT_GAP_DAYS = 6`. A 7-day gap corresponds to roughly once-per-week call cadence, the natural rhythm we neither encourage nor discourage; gaps `≥ 7` contribute zero so the penalty does not push the solver to spread calls beyond weekly.
- Per-pair contribution shape is **geometric / halving**: `weights[spacingPenalty] / 2^(g − 2)` for `g ∈ {2, 3, 4, 5, 6}`. At `g = 2` the contribution is the full per-pair weight; each additional day halves it.
- Concrete progression at `weights[spacingPenalty] = -2`: `g = 2 → -2.0`; `g = 3 → -1.0`; `g = 4 → -0.5`; `g = 5 → -0.25`; `g = 6 → -0.125`; `g ≥ 7 → 0.0`.

Operator-tuneable curve parameters (alternative `MAX_SOFT_GAP_DAYS`, alternative decay shapes such as linear or exponential with operator-supplied half-life, etc.) remain `docs/future_work.md` FW-0007 deferred, same discipline as `crReward`'s curve in §12.

Rationale: a binary count of "gap < 3" pairs (the v2-pre-D-0039 implementation) gives the solver no gradient between gap = 2 and gap = 6 — both contribute the same per pair, so the seeded tie-break in `SEEDED_RANDOM_BLIND` Phase 2 (`docs/solver_contract.md` §12) cannot distinguish "tightly spaced but legal" from "comfortably spaced". The geometric decay restores the v1-style continuous gradient: tighter gaps hurt more than wider gaps within the soft window, so the solver naturally prefers wider spacing among rule-valid options. Hard-pinning the shape in the contract (rather than leaving it as implementation detail like §12) is justified by v1 having pilot validation on the halving curve; deferring tunability to FW-0007 keeps the first-release surface tight.

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
Proposed in this checkpoint (normative; extended under v2 to cover per-day call-point weights alongside component weights):

- Scorer component weights are operator-tuneable in first release via sheet inputs, matching v1 behavior. Per-day call-point weights (the cells operators see and edit in the `MICU Call Point` / `MHD Call Point` rows per `docs/template_artifact_contract.md` §9 `pointRows`) are operator-tuneable through the same surface.
- Templates ship default weights AND default per-day call-point values (the latter via `pointRows.defaultRule` weekday/weekend mapping per `docs/template_artifact_contract.md` §9); operator-supplied values extracted from the sheet override template defaults at run time, individually per cell (the template default applies on cells the operator did not edit).
- Weight extraction happens at parser boundary per `docs/parser_normalizer_contract.md` §9 (the parser produces `scoringConfig` alongside `normalizedModel` on `CONSUMABLE` outputs); the extracted weights flow into the pipeline as part of `scoringConfig`, separate from the `normalizedModel` (so the model carries problem shape and the config carries ranking policy).
- Operator-supplied weights MUST preserve per-component sign orientation: a reward component remains a reward, a penalty component remains a penalty, regardless of the numeric weight the operator supplies. Mis-signed operator-edited weights are detected at parse time per `docs/parser_normalizer_contract.md` §14 and surfaced as `ValidationIssue` entries on `ParserResult.issues` with severity ERROR (driving NON_CONSUMABLE).
- Operator-facing surface for component weights is a separate Scorer Config tab generated by the launcher per `docs/sheet_generation_contract.md` (added under D-0037); per-day call-point cells stay on the request-entry sheet where they already live per M1 generation. Both surfaces extract through the snapshot via `scoringConfigRecords` per `docs/snapshot_contract.md`.
- Blueprint §16's current "routine variation" wording is narrower than this reality and was patched per `docs/decision_log.md` D-0028 to acknowledge component weights and the solver's `crFloor.manualValue`; D-0037 widens the operator-tuneable surface further to include per-day call-point cells, but blueprint §16's clarifying language already covers the broader principle.

## 16) Pure-function normative shape; streaming as permitted optimization
Proposed in this checkpoint (normative):
- The scorer's public contract is a pure function `score(allocation, normalizedModel, scoringConfig) → ScoreResult`.
- Implementations MAY internally compute scores incrementally or via streaming deltas when evaluating multiple candidates in a single scorer invocation (for example, reusing sub-computations across structurally-similar candidates within one `CandidateSet` pass), as an optimization. Search-time streaming — scoring deltas applied during solver search in response to `tryAdd`/`undo` operations — is out of first-release scope because the first-release solver is scoring-blind (`docs/solver_contract.md` §6, §11.1); search-time streaming becomes applicable only under a future score-aware solver strategy activated through the scoring-consultation extension clause declared in `docs/solver_contract.md`.
- Any streaming/delta implementation MUST produce `ScoreResult` values byte-identical to the pure-function evaluation over the same inputs within a single implementation on a single platform. Within one implementation on one platform, floating-point operations in the same order yield identical bit patterns; the byte-identical bar is both achievable and the single normative parity criterion under this contract.
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

### v2 follow-on (2026-04-27, this PR)
- `ScoringConfig` shape grows a required `pointRules: {[(slotType, dateKey)]: number}` field per §11; `pointBalance*` components MUST consume `pointRules` rather than the M2 C4 T2 placeholder of "1 point per call". Driven by `docs/decision_log.md` D-0037 (operator-tuneable scoring config surface — sheet → snapshot → parser → scorer flow).
- `contractVersion` bumped from `1` to `2` per §2.1; the bump is taken because `pointRules` is a required field (v1-targeted callers that supply only `weights` are non-compliant against v2), matching the selector v1 → v2 precedent (D-0032).
- §15 (Operator-tuneable weight surface) extended to acknowledge per-day call-point cells flow through the same operator-tuneable surface as component weights; both extract through the snapshot at parser boundary per `docs/parser_normalizer_contract.md` §9 (which now declares `scoringConfig` as a `ParserResult` output, closing the producer-consumer seam OD-0002 / D-0037 surfaced).
- §11 wording on missing `pointRules` keys revised under `docs/decision_log.md` D-0038 (post-D-0037 fail-loud follow-up): the original D-0037 sub-decision 5 said missing keys fall back to `1.0` per-call; D-0038 reverses that to "missing keys cause `score()` to raise" and lays a producer-coverage obligation on the parser overlay path (`docs/parser_normalizer_contract.md` §9). No `contractVersion` bump because the change tightens admission rather than computation — the set of valid configs shrinks, but valid configs that were already valid produce the same score.

### v3 follow-on (2026-04-28, this PR)
- New normative §12A pins the `spacingPenalty` curve shape: per-pair contribution `weight / 2^(gap - 2)` for `gap ∈ {2..6}`, zero for `gap ≥ 7`; strict-monotonic-decrease across the soft window for `weight < 0`. Replaces the v2-era binary `gap < 3` count. Driven by `docs/decision_log.md` D-0039 (port v1's geometric-decay reference shape).
- `contractVersion` bumped from `2` to `3` per §2.1. Unlike D-0038's tightening (which preserved scores for valid configs), D-0039 changes per-pair computational semantics: the same valid `ScoringConfig` produces different `spacingPenalty.score` under v3 vs v2 because gaps in `[3, 6]` now contribute non-zero where they previously contributed zero. v2-targeted ranking behavior is therefore not preserved, and consumers relying on the version signal need the bump.
- `ScoringConfig` public shape is unchanged — `weights[spacingPenalty]` stays a single scalar. Only the per-pair contribution formula tightens. Operator-tuneable curve parameters (alternative `MAX_SOFT_GAP_DAYS`, alternative decay shapes) remain `docs/future_work.md` FW-0007 deferred, same discipline as `crReward`'s curve in §12.

This document is a first-pass working draft checkpoint intended to unblock implementation planning without reopening broader architecture scope.
