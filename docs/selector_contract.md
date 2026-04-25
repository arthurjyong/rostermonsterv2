# Selector Contract (First-Pass Working Draft)

## 1) Contract status and scope
This document defines the selector boundary that sits between the scorer's per-candidate `ScoreResult` output (`docs/scorer_contract.md`) and the downstream result/writeback layer.

It is intended to be concrete enough for implementation planning for selector work.

It explicitly separates:
- repo-settled anchors,
- selector-boundary decisions adopted in this checkpoint,
- still-open items in this checkpoint,
- and explicit deferrals.

Scope is limited to selector-stage final-result construction, retention behavior, and handoff shape. This is not a rule engine, scorer, solver, writeback, or execution design document.

Hard validity is **not** in selector scope; the rule engine is the sole hard-validity authority (`docs/rule_engine_contract.md`). Scoring is **not** in selector scope; the scorer is the sole component-score authority (`docs/scorer_contract.md`). Search is **not** in selector scope; the solver is the sole candidate-generation authority (`docs/solver_contract.md`).

## 2) Contract identity and versioning
Contract identity/version for binding:
- `contractId: SELECTOR`
- `contractVersion: 1`

Version bump rule (normative):
- bump `contractVersion` only when selector-stage input/output shape, retention-mode semantics, sidecar artifact shape, determinism guarantees, or the strategy-interface contract changes.
- do **not** bump for wording cleanup, formatting, added examples, new strategy registrations that conform to the existing strategy-interface contract, additive run-level metadata fields on the run envelope, or clarification that does not change behavior.

## 3) Status discipline used in this document
Each normative statement is classified as one of:
- **Repo-settled**: already anchored by existing repo contracts/blueprint/decision log.
- **Proposed in this checkpoint**: adopted here as first-release selector-boundary direction.
- **Still open in this checkpoint**: recognized as unresolved here and left explicit.
- **Deferred**: intentionally out of this checkpoint's decision scope.

## 4) Repo-settled architecture anchors
The following are treated as repo-settled anchors:
- The pipeline is three-stage `solver → scorer → selector`; the selector is the final stage producing the operator-facing result (`docs/decision_log.md` D-0027).
- Retention is owned by the selector stage, not by the solver (`docs/decision_log.md` D-0027 sub-decision 2; `docs/solver_contract.md` §14).
- The solver does not populate `TrialBatchResult` best-candidate fields; those fields require scores and are populated retroactively by the selector after scoring (`docs/solver_contract.md` §14, §18.2).
- Score direction is `HIGHER_IS_BETTER` (`docs/scorer_contract.md` §10; `docs/domain_model.md` §4.2, §11.1); the selector ranks under this direction.
- `ScoreResult` carries `totalScore` plus a required component breakdown over every first-release component identifier from `docs/domain_model.md` §11.2 (`docs/scorer_contract.md` §10; `docs/decision_log.md` D-0025).
- First-release retention scope is `BEST_ONLY` as the default plus `FULL` as a per-run operator opt-in for ad-hoc auditability; `TOP_K`, `FULL_WITH_DIAGNOSTICS`, and per-batch artifact export formats are deferred to benchmark-campaign work (`docs/decision_log.md` D-0026 consequences, D-0027 sub-decision 2; `docs/future_work.md` FW-0013).
- `AllocationResult` is the canonical solved-allocation output object (`docs/domain_model.md` §10.3).

## 5) Purpose
Repo-settled intent + checkpoint narrowing:
- Pick the single winning candidate from a fully-scored `CandidateSet` and produce the operator-facing final result.
- Populate retroactive selector-owned fields on `TrialBatchResult` so search-stage diagnostics become decision-stage artifacts that operators can audit.
- Make retention an explicit, contract-governed surface so first-release `BEST_ONLY` and operator-opt-in `FULL` behavior is reviewable independently of search and scoring.

## 6) Boundary position
Repo-settled:
- Upstream: scorer emits one `ScoreResult` per `TrialCandidate` against the solver's `CandidateSet` (`docs/scorer_contract.md` §10), or the solver emits an `UnsatisfiedResult` (`docs/solver_contract.md` §10.2) on the failure branch.
- Boundary: selector consumes the fully-scored `CandidateSet` (or `UnsatisfiedResult`), an operator-supplied `retentionMode`, an execution-layer-supplied `runEnvelope`, and a `selectorStrategyId` (plus optional strategy-specific config), and produces a `FinalResultEnvelope`.
- Downstream: writeback adapter / operator-facing surfaces consume `FinalResultEnvelope` (`docs/domain_model.md` §14).

Proposed in this checkpoint:
- Selector is a pure function of its declared inputs. No solver coupling, no scorer coupling beyond consuming `ScoreResult` values, no lifecycle, and no side effects beyond optional sidecar-artifact emission under `FULL` retention (§14).
- Selector is a pluggable strategy behind a stable contract-level interface. See §11.

## 7) What this contract governs
This contract governs:
- the shape of selector input (the scored `CandidateSet`, retention mode, run envelope, strategy identity),
- the shape of selector output (the `FinalResultEnvelope`, including the `AllocationResult` success branch and the `UnsatisfiedResultEnvelope` failure branch),
- the selector strategy interface and the first-release strategy identity (§11),
- the first-release strategy `HIGHEST_SCORE_WITH_CASCADE` and its tie-break cascade (§12),
- retention mode enumeration and per-mode output behavior (§13),
- sidecar artifact shapes under `FULL` retention (§14),
- `UnsatisfiedResult` handling and the no-sidecar-on-failure rule (§15),
- the run envelope and the `(runId, candidateId)` traceability identity (§16),
- selector-owned retroactive population of `TrialBatchResult` fields (§17),
- determinism guarantees (§18),
- sidecar schema versioning (§19),
- the operator-facing retention opt-in surface.

## 8) What this contract does not govern
This contract does **not** govern:
- candidate generation, search strategy, fill-order policy, or seeded randomization (see `docs/solver_contract.md`),
- scoring, ranking weights, component definitions, or soft-effect evaluation (see `docs/scorer_contract.md`),
- hard-validity evaluation (see `docs/rule_engine_contract.md`),
- writeback mapping, result rendering, or operator-facing presentation,
- file-system paths, sidecar file naming, timestamp embedding, or where retained artifacts physically land on disk (execution-layer concern; see §14.3),
- observability transport, log format, or run lifecycle management,
- orchestration, worker/cloud transport, or campaign-level coordination,
- parser/normalizer admission, snapshot ingestion, or raw sheet interpretation.

## 9) Input shape
Selector invocations are evaluated against the following inputs:
1. **`scoredCandidateSet`** — a `CandidateSet` per `docs/solver_contract.md` §10.1 in which every `TrialCandidate.score` field has been populated by the scorer with a `ScoreResult` per `docs/scorer_contract.md` §10. We refer to this populated set as a `ScoredCandidateSet` for clarity within this contract; structurally it remains a `CandidateSet`. On the failure branch this input is replaced by an `UnsatisfiedResult` per `docs/solver_contract.md` §10.2 and is handled per §15.
2. **`retentionMode`** — first release: `"BEST_ONLY"` (default) or `"FULL"` (operator opt-in). See §13. `TOP_K` and `FULL_WITH_DIAGNOSTICS` are deferred to FW-0013 Phase 2.
3. **`runEnvelope`** — execution-layer-supplied run identity and provenance. Required fields: `runId` (stable string identifier), `snapshotRef`, `configRef`, `seed`, `fillOrderPolicy`, `crFloorMode`, `crFloorComputed`, `generationTimestamp`. See §16.
4. **`selectorStrategyId`** — first release ships exactly `"HIGHEST_SCORE_WITH_CASCADE"`. See §11 and §12.
5. **`selectorStrategyConfig`** (optional) — strategy-specific configuration. First-release `HIGHEST_SCORE_WITH_CASCADE` does not require any configuration fields; future strategies MAY declare them per their `StrategyDescriptor` (§11).

Normative properties:
- The selector MUST NOT consume the scorer interface, any scoring configuration, or any rule-engine handle. Scores arrive on `TrialCandidate.score` only.
- The selector MUST NOT read any state outside the declared inputs. No environment variables, no clocks, no filesystem reads.
- The selector MUST NOT synthesize `runId`. If `runId` is absent at selector entry, that is a contract-breaking defect on the caller side, not a selector responsibility to recover from.
- Strategies MAY declare additional strategy-specific inputs in their strategy descriptor (§11). Such additions MUST NOT override this contract's prohibitions on scorer/rule-engine logic mutation or determinism relaxation.

## 10) Output shape
Selector returns a `FinalResultEnvelope`:

```
FinalResultEnvelope {
  runEnvelope: RunEnvelope          // carried through unchanged from §9 input
  retentionMode: "BEST_ONLY" | "FULL"
  selectorStrategyId: string
  result: AllocationResult | UnsatisfiedResultEnvelope   // exactly one
}
```

### 10.1 `AllocationResult` — the success branch
The success branch is an `AllocationResult` per `docs/domain_model.md` §10.3, populated by the selector with at minimum:

```
AllocationResult {
  winnerAssignment: AssignmentUnit[]    // winning TrialCandidate's full roster
  winnerScore: ScoreResult              // winning TrialCandidate's ScoreResult, full component breakdown per docs/scorer_contract.md §10
  searchDiagnostics: SearchDiagnostics  // run-level transparency payload
  candidatesSummaryPath?: string        // FULL retention only; see §14
  candidatesFullPath?: string           // FULL retention only; see §14
}
```

Normative properties:
- `winnerAssignment` MUST be the full `AssignmentUnit[]` of the winning `TrialCandidate`, including `FixedAssignment`-derived entries inherited through the solver (`docs/solver_contract.md` §10.1).
- `winnerScore` MUST carry the full component breakdown per `docs/scorer_contract.md` §10 (every first-release component identifier, even when contributing zero). Returning only `totalScore` is a contract violation.
- `searchDiagnostics` MUST carry the run-level transparency payload defined in `docs/solver_contract.md` §18.1; the selector forwards solver-emitted fields and adds selector-owned aggregations per §17.
- `candidatesSummaryPath` and `candidatesFullPath` MUST be present under `FULL` retention and MUST be absent under `BEST_ONLY` retention. See §13 and §14.

### 10.2 `UnsatisfiedResultEnvelope` — the failure branch
The failure branch wraps the solver's `UnsatisfiedResult` (`docs/solver_contract.md` §10.2):

```
UnsatisfiedResultEnvelope {
  unfilledDemand: UnfilledDemandEntry[]   // forwarded from UnsatisfiedResult
  reasons: ValidationIssue[]              // forwarded from UnsatisfiedResult
  searchDiagnostics: SearchDiagnostics    // forwarded from UnsatisfiedResult.diagnostics
}
```

Normative properties:
- `UnsatisfiedResultEnvelope` is returned when the selector's input was an `UnsatisfiedResult` per `docs/solver_contract.md` §10.2. The selector does not invent failure conditions of its own at the contract level; it cannot reach this branch from a non-empty `scoredCandidateSet`.
- The failure branch MUST NOT carry `winnerAssignment`, `winnerScore`, `candidatesSummaryPath`, or `candidatesFullPath`. No candidate rosters and no sidecar files exist on the failure branch regardless of `retentionMode`. See §15.
- `searchDiagnostics` is the same payload the solver emitted on the failure branch, optionally enriched with selector-owned aggregations per §17 if applicable; selector aggregation MUST NOT alter solver-emitted fields.

### 10.3 Branch discipline
A single selector invocation MUST return exactly one of `AllocationResult` or `UnsatisfiedResultEnvelope` inside the `FinalResultEnvelope`. Mixed-mode returns are a contract-breaking defect.

## 11) Selector strategy interface
Proposed in this checkpoint (normative):

The selector is pluggable by named strategy. A strategy is identified by a stable `selectorStrategyId` and described by a `StrategyDescriptor`, mirroring the solver's pattern (`docs/solver_contract.md` §11):

```
StrategyDescriptor {
  selectorStrategyId: string         // e.g., "HIGHEST_SCORE_WITH_CASCADE"
  requiredInputs: string[]           // identifiers of contract-declared inputs the strategy consumes
  additionalInputs?: string[]        // strategy-specific inputs beyond §9
}
```

### 11.1 First-release strategy set
First release ships exactly one strategy:
- `HIGHEST_SCORE_WITH_CASCADE` — see §12.

Callers that request an unregistered `selectorStrategyId` MUST be rejected at strategy-resolution time, **before** any §10 `FinalResultEnvelope` construction begins. Such a rejection is not a `FinalResultEnvelope.result` value — it never enters the §10 output schema at all, and therefore does not require a slot inside the `AllocationResult | UnsatisfiedResultEnvelope` branch discipline. The concrete shape of the strategy-resolution failure (exception class, structured error object, return code) is an implementation concern outside this contract.

### 11.2 Future strategies (extension clause)
The contract anticipates future strategies (for example, score-with-fairness-bias selection, multi-objective Pareto selection, operator-preferred-candidate selection). Normative rules for future strategies:
- A future strategy MAY declare additional strategy-specific inputs in `additionalInputs` (for example, a fairness-bias coefficient, a Pareto-front cardinality bound, an operator-preferred-candidate handle).
- A future strategy MUST NOT override scorer-component logic or direction (`docs/scorer_contract.md`), MUST NOT relax retention-mode semantics defined in §13, and MUST NOT relax determinism guarantees defined in §18.
- The strategy-interface extension clause is additive only. Adding a future strategy that conforms to this clause does not require a `contractVersion` bump. Changes to the strategy-interface contract itself (for example, introducing a new mutation channel that lets a strategy reach into scorer or rule-engine state) do require a bump.

## 12) First-release strategy: `HIGHEST_SCORE_WITH_CASCADE`
Proposed in this checkpoint (normative):

`HIGHEST_SCORE_WITH_CASCADE` selects the candidate with the highest `totalScore` from the `scoredCandidateSet` and applies a deterministic two-level cascade tie-break with a final `candidateId` fallback for full determinism.

### 12.1 Selection rule
Among all candidates in `scoredCandidateSet.candidates`, pick the candidate with the maximum `score.totalScore` value (`HIGHER_IS_BETTER` per `docs/scorer_contract.md` §10).

### 12.2 Tie-break cascade
When two or more candidates tie on `totalScore`, the strategy MUST apply the following cascade in order until exactly one candidate remains:
1. Prefer the candidate with the **higher `pointBalanceGlobal`** (less-negative penalty contribution).
2. Prefer the candidate with the **higher `crReward`** (more-positive reward contribution).
3. Final fallback: prefer the candidate with the **lowest `candidateId`**.

The cascade depth is exactly two (`pointBalanceGlobal`, then `crReward`); deeper components from `docs/domain_model.md` §11.2 are not consulted under this strategy. The `candidateId` fallback ensures full determinism in the (vanishingly rare) case of a total-cascade tie. `candidateId` ordering is well-defined because `candidateId` is a run-monotonic integer (§16).

### 12.3 Component-name dependency
The cascade names two specific component identifiers (`pointBalanceGlobal`, `crReward`) from `docs/domain_model.md` §11.2. Renaming or removing either component would be a breaking change for this strategy. Adding new components has no effect on this strategy. Strategies that consume different cascade components MUST register as distinct strategies under §11.

## 13) Retention modes
Proposed in this checkpoint (normative):

First-release `retentionMode` is one of:
- `"BEST_ONLY"` (default) — the operator-facing default; no per-candidate artifacts retained.
- `"FULL"` (opt-in audit) — operator opt-in for ad-hoc auditability of every emitted candidate.

`TOP_K` and `FULL_WITH_DIAGNOSTICS` modes are deferred to FW-0013 Phase 2 (benchmark-campaign work).

### 13.1 `BEST_ONLY` (default)
- No sidecar files are written.
- `AllocationResult` carries `winnerAssignment` + `winnerScore` + `searchDiagnostics` + the run envelope (via `FinalResultEnvelope.runEnvelope`).
- `winnerScore` already carries the full component breakdown by `docs/scorer_contract.md` §10 / D-0025, so audit at the winning-candidate granularity is preserved without requiring `FULL`.
- `candidatesSummaryPath` and `candidatesFullPath` MUST be absent.

### 13.2 `FULL` (opt-in audit)
- Sidecar files are written: `candidates_summary.csv` and `candidates_full.json` per §14.
- `AllocationResult` carries everything from `BEST_ONLY` plus `candidatesSummaryPath` and `candidatesFullPath` pointers and the full `searchDiagnostics` chain inline.
- Per-candidate retention covers up to `maxCandidates` candidates as bounded by the solver's `terminationBounds` (`docs/solver_contract.md` §15). Fewer entries are retained when fewer candidates were emitted by the solver. The selector MUST NOT artificially empty the retention set when at least one candidate exists in the input.

### 13.3 Mode semantics on the failure branch
On the `UnsatisfiedResult` failure branch, `retentionMode` has no behavioral effect: no sidecar files are written and no candidate rosters are emitted regardless of mode. See §15. The `retentionMode` value is still echoed in `FinalResultEnvelope.retentionMode` for run-artifact traceability.

## 14) Sidecar artifacts (under `FULL` retention)
Proposed in this checkpoint (normative):

Under `FULL` retention, the selector emits two sidecar files. Both files are cross-referenced by `candidateId` and both embed `runId` so retained artifacts are unambiguously traceable when found out of context.

### 14.1 `candidates_summary.csv`
Tabular per-candidate summary suitable for spreadsheet-grade inspection.
- One row per retained candidate.
- Header row required.
- Required columns:
  - `candidateId` — run-monotonic integer (§16),
  - `totalScore` — the candidate's `ScoreResult.totalScore`,
  - one column per first-release component identifier from `docs/domain_model.md` §11.2 (the nine ICU/HD components: `unfilledPenalty`, `pointBalanceWithinSection`, `pointBalanceGlobal`, `spacingPenalty`, `preLeavePenalty`, `crReward`, `dualEligibleIcuBonus`, `standbyAdjacencyPenalty`, `standbyCountFairnessPenalty`),
  - `runId`, `seed`, `batchId` (when batches were surfaced by the active solver strategy; see `docs/solver_contract.md` §18.2).
- `schemaVersion: 1` MUST be declared either in a top-of-file comment line (preferred where the CSV variant in use supports header comments) or as a first-row metadata block. The chosen mechanism MUST be uniform within an implementation so old tooling can detect a future bump (§19).

### 14.2 `candidates_full.json`
Full per-candidate payload suitable for programmatic round-trip.
- Top-level fields MUST include `runId`, `schemaVersion: 1`, and `generationTimestamp` (carried from `runEnvelope.generationTimestamp` per §16; execution-layer-supplied, never selector-synthesized, so byte-identical determinism per §18 holds across re-runs of identical inputs).
- The candidate payload MUST be indexed by `candidateId` and MUST include the full `AssignmentUnit[]` of each retained candidate.
- The candidate payload MUST include the full `ScoreResult` (total + components) for each retained candidate; `candidates_full.json` is the authoritative per-candidate scoring artifact under `FULL` retention.
- The serialization format details (key ordering, whitespace, Unicode normalization) are implementation-level concerns, but the selector MUST emit byte-identical files under identical inputs on a single implementation on a single platform. See §18.

### 14.3 Filesystem placement is execution-layer-owned
This contract does **not** govern:
- the directory or path the sidecar files are written to,
- the file-naming convention (for example, timestamp embedding, run-prefix structure),
- file-system permissions, retention period, or rotation policy.

Concrete `candidatesSummaryPath` and `candidatesFullPath` values returned by the selector are execution-layer outputs. The selector contract requires only that the returned paths point to files conforming to §14.1 and §14.2 respectively, and that both embed the `runId` from `runEnvelope`.

## 15) `UnsatisfiedResult` handling
Proposed in this checkpoint (normative):

When the selector's input is an `UnsatisfiedResult` per `docs/solver_contract.md` §10.2:
- The selector MUST return a `FinalResultEnvelope` whose `result` field is an `UnsatisfiedResultEnvelope` per §10.2.
- The selector MUST NOT write sidecar files regardless of `retentionMode`. There are no candidates to retain on the failure branch (the solver did not emit any), so output is identical between `BEST_ONLY` and `FULL`.
- The selector MUST forward `UnsatisfiedResult.unfilledDemand` and `UnsatisfiedResult.reasons` unchanged into `UnsatisfiedResultEnvelope`.
- The selector MUST forward `UnsatisfiedResult.diagnostics` into `UnsatisfiedResultEnvelope.searchDiagnostics`. Selector-owned aggregations per §17 MAY enrich `searchDiagnostics` with rejection counts, rule-firing histograms across attempts, and worst-case fill-progress snapshots, provided solver-emitted fields are preserved unchanged.
- `FinalResultEnvelope.runEnvelope` is still populated from §9 input. Run-level traceability is preserved across the failure branch.

Rationale: the failure branch is identical between retention modes by construction. There is no scored-candidate set to retain because the solver never reached one. Forcing a degenerate "empty `candidates_summary.csv`" under `FULL` would create operator-facing noise (an artifact promising candidate detail that contains none) and would not improve auditability over the failure-branch diagnostics already carried inline.

## 16) Run envelope and traceability
Proposed in this checkpoint (normative):

### 16.1 Identity composition
The full identity of any retained candidate is the pair `(runId, candidateId)`:
- `runId` is the execution-layer-supplied stable run identifier carried on `runEnvelope.runId` (§9). The selector MUST NOT synthesize `runId`.
- `candidateId` is a run-monotonic integer scoped to the run, assigned per `TrialCandidate` in solver-emission order. Candidate `1` is the first candidate emitted across all batches in the run; candidate `N` is the last. Within a single run, `candidateId` values are dense (no gaps) and stable under repeated invocations on identical inputs.

### 16.2 Run-level metadata flows once
All run-level metadata (`runId`, `snapshotRef`, `configRef`, `seed`, `fillOrderPolicy`, `crFloorMode`, `crFloorComputed`, `generationTimestamp`) flows once on the `runEnvelope` at the `FinalResultEnvelope` level. `generationTimestamp` is execution-layer-supplied for the same reason as `runId` (§16.4): the selector MUST NOT consume clocks (§18), so any timestamp embedded in retained artifacts must arrive on the run envelope rather than be synthesized at write time. Run-level metadata MUST NOT be repeated per candidate inside `candidates_summary.csv` or `candidates_full.json` beyond the explicit per-row `runId` reference and any explicitly-listed run-scope fields (for example, `seed` in `candidates_summary.csv` per §14.1). This avoids duplication that would silently drift if any field were updated mid-run.

### 16.3 Run envelope additivity
Future expansion of run-level metadata fields on `runEnvelope` is additive and does not require a `contractVersion` bump. Removing or renaming an existing field does require a bump.

### 16.4 Selector synthesizes nothing about identity
The selector MUST NOT generate `runId`, MUST NOT remap `candidateId` values from the solver's emission order, and MUST NOT alter `snapshotRef` / `configRef` / `seed` / `fillOrderPolicy` / `crFloorMode` / `crFloorComputed` / `generationTimestamp` values received on the run envelope. The selector is a propagator of identity, not an originator.

## 17) `TrialBatchResult` retroactive population
Proposed in this checkpoint (normative):

The selector retroactively populates the selector-owned fields of `TrialBatchResult` (`docs/domain_model.md` §12.4), operationalizing `docs/decision_log.md` D-0026 sub-decision 8.

### 17.1 Per-batch best-candidate field
For each `TrialBatchResult` surfaced by the active solver strategy (`docs/solver_contract.md` §18.2), the selector MUST populate the `bestCandidate` field with the highest-scoring candidate within that batch under the `HIGHEST_SCORE_WITH_CASCADE` selection rule (§12).

### 17.2 Per-batch score-distribution summary
The selector MUST populate a per-batch score-distribution summary on `TrialBatchResult`. The summary MUST include:
- For `totalScore`: `min`, `max`, `median`, `mean`, `stddev`.
- For each first-release component identifier in `docs/domain_model.md` §11.2 (the nine ICU/HD components): `min`, `max`, `median`.

This is the "per-component min/max/median" option from the design conversation: heavier than `totalScore` alone, but rich enough to support per-component retention diagnostics without requiring `FULL` retention.

### 17.3 Full-set ingest
The selector consumes the full `scoredCandidateSet` at once. Streaming ingest (selector that processes candidates as they are scored rather than holding the full set in memory) is **deferred** to `docs/future_work.md` FW-0018; first-release retention volumes are within memory bounds at ICU/HD scale.

### 17.4 Strategies that do not surface batches
When the active solver strategy does not surface batches (`docs/solver_contract.md` §18.2 permits omitting `TrialBatchResult` emissions), the selector has no `TrialBatchResult` to populate. This is not a failure; the run-level `searchDiagnostics` payload is sufficient on its own.

## 18) Determinism
Proposed in this checkpoint (normative):
- Given identical `(scoredCandidateSet, retentionMode, runEnvelope, selectorStrategyId, selectorStrategyConfig)` inputs, the selector MUST produce byte-identical outputs — identical `FinalResultEnvelope` content and, under `FULL` retention, byte-identical `candidates_summary.csv` and `candidates_full.json` files — within a single implementation on a single platform.
- Determinism is required within a single implementation on a single platform. Cross-implementation or cross-platform determinism is not required and is not guaranteed; serialization library choices, hash-map iteration order, and floating-point string formatting differ across runtimes (see `docs/future_work.md` FW-0011).
- The selector MUST NOT consume clocks, environment variables, or filesystem state. Sidecar-file emission is the only side effect the selector is permitted to perform under `FULL` retention.
- A selector implementation that produces non-byte-identical outputs under identical inputs on a single platform is contract-broken regardless of its observed selection quality.

## 19) Schema versioning
Proposed in this checkpoint (normative):

Both sidecar artifacts (`candidates_summary.csv`, `candidates_full.json`) carry `schemaVersion: 1` per §14.

Bump rule:
- bump `schemaVersion` only when the artifact's column set, field set, or per-cell semantics change in a way that breaks a v1-targeted reader.
- additive changes that a v1-targeted reader can tolerate (for example, appended optional columns at the end of `candidates_summary.csv`, additional optional top-level fields in `candidates_full.json` that v1 readers can ignore) do not require a bump.
- removing or renaming a column/field, changing a column's semantic meaning, or reordering existing columns in a way a positional reader would notice does require a bump.

A `schemaVersion` bump on either sidecar artifact is a `contractVersion` bump on the selector contract itself per §2.

## 20) Consistency with adjacent contracts
Repo-settled alignments:
- Consistent with `docs/decision_log.md` D-0027: the selector is the third stage of `solver → scorer → selector`; it owns retention; it does not consult rule engine or scorer interfaces directly beyond consuming `ScoreResult` values on `TrialCandidate`.
- Consistent with `docs/solver_contract.md` §10, §14, §18: the selector consumes `CandidateSet` or `UnsatisfiedResult`, emits the `AllocationResult` / `UnsatisfiedResultEnvelope` final shape, and populates `TrialBatchResult` selector-owned fields the solver explicitly leaves unpopulated.
- Consistent with `docs/scorer_contract.md` §10: `ScoreResult` carries the full first-release component breakdown, which the selector preserves into `winnerScore` and into `candidates_summary.csv` columns.
- Consistent with `docs/rule_engine_contract.md`: the selector never adjudicates hard validity; rule-engine validity is already established upstream by the solver per `docs/solver_contract.md` §10.1.
- Consistent with `docs/domain_model.md` §10.3 (`AllocationResult`), §12.4 (`TrialBatchResult`), §12.5 (retention policy options): the selector populates the canonical result/diagnostic objects rather than redefining them.

Proposed in this checkpoint:
- This contract formalizes the pluggable strategy interface, the `HIGHEST_SCORE_WITH_CASCADE` first-release strategy with two-level cascade + `candidateId` fallback, the `BEST_ONLY` / `FULL` retention surface, the sidecar artifact shapes under `FULL`, and the no-sidecar-on-failure rule, while remaining aligned with rule-engine / scorer / solver / domain-model boundaries.

## 21) Explicit deferrals
The following are explicitly deferred and not fixed by this document:
- concrete sidecar file paths and where files land on disk (execution-layer concern; §14.3),
- sidecar file naming convention, including timestamp embedding and run-prefix structure (execution-layer concern),
- `TOP_K` and `FULL_WITH_DIAGNOSTICS` retention modes, and per-batch artifact export formats for benchmark campaigns (`docs/future_work.md` FW-0013 Phase 2),
- streaming-selector implementation that processes candidates as they are scored rather than holding the full set in memory (`docs/future_work.md` FW-0018),
- alternative selector strategies beyond `HIGHEST_SCORE_WITH_CASCADE` (future strategy registrations under §11.2),
- cross-implementation and cross-platform determinism for selector outputs and sidecar artifacts (`docs/future_work.md` FW-0011),
- concrete function/API signatures, language-specific shapes, and module decomposition within the selector,
- mid-search retention re-emergence under future score-aware solver strategies (`docs/future_work.md` FW-0016 covers the solver side; selector-side changes would land alongside).

## 22) Current checkpoint status
### Repo-settled in prior docs
- pipeline-stage separation `solver → scorer → selector` and selector ownership of retention (`docs/decision_log.md` D-0027; `docs/solver_contract.md` §14),
- first-release retention scope (`BEST_ONLY` default + `FULL` opt-in; `TOP_K` / `FULL_WITH_DIAGNOSTICS` deferred) (`docs/decision_log.md` D-0026 consequences, D-0027 sub-decision 2; `docs/future_work.md` FW-0013),
- `ScoreResult` shape and required component breakdown (`docs/scorer_contract.md` §10; `docs/decision_log.md` D-0025),
- `AllocationResult`, `TrialBatchResult`, and retention-policy enumeration (`docs/domain_model.md` §10.3, §12.4, §12.5),
- selector-side retroactive population of `TrialBatchResult` best-candidate fields (`docs/decision_log.md` D-0026 sub-decision 8; `docs/solver_contract.md` §14, §18.2).

### Proposed and adopted in this checkpoint
- pure-function public contract with `(scoredCandidateSet, retentionMode, runEnvelope, selectorStrategyId, selectorStrategyConfig) → FinalResultEnvelope` shape,
- `FinalResultEnvelope` branch discipline with `AllocationResult` success branch and `UnsatisfiedResultEnvelope` failure branch,
- pluggable strategy interface mirroring the solver's `StrategyDescriptor` pattern, with additive extension clause for future strategies,
- first-release `HIGHEST_SCORE_WITH_CASCADE` strategy with `pointBalanceGlobal` → `crReward` → lowest `candidateId` cascade,
- retention modes `BEST_ONLY` (default) and `FULL` (opt-in) with per-mode output behavior, and the no-sidecar-on-failure rule,
- sidecar artifacts `candidates_summary.csv` (per `docs/domain_model.md` §11.2 columns + run-level metadata) and `candidates_full.json` (full `AssignmentUnit[]` and `ScoreResult` per candidate) cross-referenced by `candidateId` and embedding `runId`,
- run envelope and `(runId, candidateId)` traceability identity, with execution-layer-supplied `runId` and run-monotonic integer `candidateId`,
- selector-owned retroactive population of per-batch best-candidate field plus per-batch score-distribution summary (per-component min/max/median for every first-release component),
- byte-identical determinism within a single implementation on a single platform,
- sidecar `schemaVersion: 1` with explicit additive-vs-breaking bump rule.

### Still open / deferred
- concrete API signatures, language-specific shapes, and module decomposition,
- streaming-selector implementation (`docs/future_work.md` FW-0018),
- richer retention modes and artifact export formats (`docs/future_work.md` FW-0013 Phase 2),
- cross-implementation and cross-platform determinism (`docs/future_work.md` FW-0011),
- alternative selector strategies beyond `HIGHEST_SCORE_WITH_CASCADE`.

This document is a first-pass working draft checkpoint intended to unblock implementation planning without reopening broader architecture scope.
