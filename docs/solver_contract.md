# Solver Contract (First-Pass Working Draft)

## 1) Contract status and scope
This document defines the solver boundary that sits between parser/normalizer output (`docs/domain_model.md`, `docs/parser_normalizer_contract.md`) and the downstream scorer/selector layers.

It is intended to be concrete enough for implementation planning for solver work.

It explicitly separates:
- repo-settled anchors,
- solver-boundary decisions adopted in this checkpoint,
- still-open items in this checkpoint,
- and explicit deferrals.

Scope is limited to solver-stage candidate generation and handoff shape. This is not a rule engine, scorer, selector, writeback, or execution design document.

Scoring, ranking, and retention are **not** in solver scope; scoring is owned by `docs/scorer_contract.md`, retention is owned by the selector stage (see §14).

## 2) Contract identity and versioning
Contract identity/version for binding:
- `contractId: SOLVER`
- `contractVersion: 1`

Version bump rule (normative):
- bump `contractVersion` only when solver-stage input/output shape, termination semantics, determinism guarantees, or the strategy-interface contract changes.
- do **not** bump for wording cleanup, formatting, added examples, new strategy registrations that conform to the existing strategy-interface contract, or clarification that does not change behavior.

## 3) Status discipline used in this document
Each normative statement is classified as one of:
- **Repo-settled**: already anchored by existing repo contracts/blueprint/decision log.
- **Proposed in this checkpoint**: adopted here as first-release solver-boundary direction.
- **Still open in this checkpoint**: recognized as unresolved here and left explicit.
- **Deferred**: intentionally out of this checkpoint's decision scope.

## 4) Repo-settled architecture anchors
The following are treated as repo-settled anchors:
- Solver performs pure compute search over possible assignments and uses the rule engine to keep the search space legal (blueprint §7.5).
- Solver does not define hard rules itself and does not perform writeback or transport (blueprint §7.5).
- First shipped search strategy is seeded randomized search, prioritizing simplicity, reproducibility, explainability, and validation ease over sophistication (blueprint §16).
- Reproducibility within the pipeline relies on deterministic solver candidate generation under a fixed seed (blueprint §5; `docs/scorer_contract.md` §17).
- Solver input is normalized model + rule engine interface + seed/config (blueprint §7.5).
- Fixed assignments are first-class normalized input and count directly toward slot demand; solver fills only residual unfilled demand after accounting for fixed assignments (`docs/domain_model.md` §10.1).
- `CR` is a soft preference signal and never overrides hard validity (`docs/domain_model.md` §4.1).

## 5) Purpose
Repo-settled intent + checkpoint narrowing:
- Produce valid roster candidates against the normalized model and rule engine, deterministically under a fixed seed.
- Preserve a strict boundary between candidate generation and candidate ranking: the solver does not consume scoring logic and does not rank its output.
- Support strategy plurality over time — the first-release strategy is seeded randomized search with a small set of well-defined sub-policies — without forcing contract-level change when future strategies land.

## 6) Boundary position
Repo-settled:
- Upstream: parser/normalizer emits a `CONSUMABLE` `ParserResult` with `normalizedModel` populated (`docs/parser_normalizer_contract.md` §9, §17). Fixed assignments are already present in the normalized model as first-class input facts.
- Boundary: solver consumes the normalized model + a rule-engine handle + a seed + run-scope solver configuration, and produces a `CandidateSet` or an `UnsatisfiedResult`.
- Downstream: scorer ranks every emitted candidate (`docs/scorer_contract.md`); selector applies retention policy over scored candidates and produces the final `AllocationResult` (see §14).

Proposed in this checkpoint:
- Solver is scoring-blind. It MUST NOT read, consult, or derive from any scoring component, soft-effect magnitude, or objective signal.
- Solver is a pluggable strategy behind a stable contract-level interface. See §11.

## 7) What this contract governs
This contract governs:
- the shape of solver input,
- the shape of solver output (including the `CandidateSet` / `UnsatisfiedResult` branch),
- the strategy-interface abstraction and the first-release strategy identity (§11),
- the first-release composite strategy (§12),
- the `crFloor` computation surface (§13),
- termination semantics (§15),
- determinism guarantees (§16),
- the boundary between solver candidate generation and downstream retention/scoring,
- the operator-tuneable surface owned by the solver (§17).

## 8) What this contract does not govern
This contract does **not** govern:
- hard-validity evaluation (see `docs/rule_engine_contract.md`),
- scoring, ranking, or objective aggregation (see `docs/scorer_contract.md`),
- retention mode, top-K selection, or full-candidate export (owned by the selector stage; see §14),
- writeback mapping, result artifact shape, or operator-facing presentation,
- parser/normalizer admission, snapshot ingestion, or raw sheet interpretation,
- orchestration, worker/cloud transport, or run lifecycle management,
- observability transport or log format.

## 9) Input shape
Solver invocations are evaluated against the following inputs:
1. **`normalizedModel`** — the `CONSUMABLE` parser output (`docs/domain_model.md`), including `FixedAssignment[]`, `SlotDemand`, `DoctorGroup` membership, `SlotType` identities, `DailyEffectState`, `EligibilityRule`, and `Request` facts.
2. **`ruleEngine`** — a handle to the rule-engine interface governed by `docs/rule_engine_contract.md`. The solver MUST use this interface (and only this interface) to adjudicate hard validity of any candidate placement.
3. **`seed`** — a 64-bit signed integer used to initialize any randomized decision made by the active strategy. Under identical inputs including `seed`, the solver MUST produce identical outputs; see §16.
4. **`fillOrderPolicy`** — the fill-order policy descriptor used by the active strategy's fill phase. First-release default is `MOST_CONSTRAINED_FIRST`; see §12.
5. **`terminationBounds`** — termination configuration for the active strategy. First-release surface: `maxCandidates` (required). See §15.
6. **`preferenceSeeding`** (optional) — configuration for any preference-seeding phase the active strategy supports. First-release surface: `crFloor` (see §13).

Normative properties:
- The solver MUST NOT consume the scorer interface, any scoring configuration (`scoringConfig`), any soft-effect magnitude, or any objective signal.
- The solver MUST NOT read any state outside the declared inputs. No environment variables, no clocks, no filesystem.
- Strategies MAY declare additional strategy-specific inputs in their strategy descriptor (§11). Such additions MUST NOT override this contract's prohibitions (in particular, MUST NOT smuggle scoring logic into first-release `SEEDED_RANDOM_BLIND`).

## 10) Output shape
Solver returns one of the following two shapes:

### 10.1 `CandidateSet` — the success branch

```
CandidateSet {
  candidates: TrialCandidate[]
  diagnostics: SearchDiagnostics
}
```

Normative properties:
- `candidates` is a list of valid roster candidates emitted by the active strategy under its termination bounds.
- Each `TrialCandidate` carries `AssignmentUnit[]` covering the full roster — including `FixedAssignment` entries from the normalized model and all solver-placed `AssignmentUnit` entries. The `TrialCandidate` score-summary field (per `docs/domain_model.md` §12.3) is **unpopulated at solver-emission stage**; score presence is stage-dependent, and this field is populated downstream by the scorer (`docs/scorer_contract.md`). The solver MUST NOT populate the score field itself.
- Each candidate MUST be free of rule-engine hard-validity violations under `docs/rule_engine_contract.md`. Emitting an invalid candidate is a contract-breaking defect.
- `diagnostics` carries the solver's transparency payload; see §18.
- `candidates` MUST be non-empty on the success branch. Since `terminationBounds.maxCandidates` is a required positive integer (§15), a successful search always emits at least one candidate; emitting an empty `CandidateSet` is a contract-breaking defect. When no valid complete candidate is reachable under the active bounds, the solver MUST return `UnsatisfiedResult` (§10.2) instead.

### 10.2 `UnsatisfiedResult` — the whole-run failure branch

```
UnsatisfiedResult {
  unfilledDemand: UnfilledDemandEntry[]
  reasons: ValidationIssue[]
  diagnostics: SearchDiagnostics
}
```

Normative properties:
- `UnsatisfiedResult` is returned when any slot cannot be filled under the active strategy's constraints, for any reason (eligibility exhaustion, hard-block saturation, fixed-assignment adjacency collisions).
- When `UnsatisfiedResult` is returned, no partial `CandidateSet` is emitted. See §14 for the whole-run-failure discipline.
- `unfilledDemand` MUST identify the `(dateKey, slotType, unitIndex)` tuples that could not be filled by at least one attempted candidate construction under the declared termination bounds.
- `reasons` carries structured explanations using the shared `ValidationIssue` shape (`docs/domain_model.md` §13).
- `diagnostics` is still emitted on the failure branch so the run is auditable.

### 10.3 Branch discipline
A single solver invocation MUST return exactly one of `CandidateSet` or `UnsatisfiedResult`. Mixed-mode returns (for example, a `CandidateSet` with partial candidates plus an `unfilledDemand` sidecar) are a contract-breaking defect.

## 11) Strategy interface
Proposed in this checkpoint (normative):

The solver is pluggable by named strategy. A strategy is identified by a stable `strategyId` and described by a `StrategyDescriptor`:

```
StrategyDescriptor {
  strategyId: string                 // e.g., "SEEDED_RANDOM_BLIND"
  requiredInputs: string[]           // identifiers of contract-declared inputs the strategy consumes
  additionalInputs?: string[]        // strategy-specific inputs beyond §9
  scoringConsultation: false | "READ_ONLY_ORACLE"   // see §11.2
}
```

### 11.1 First-release strategy set
First release ships exactly one strategy:
- `SEEDED_RANDOM_BLIND` — see §12.

Callers that request an unregistered `strategyId` MUST receive a structured failure (not a silent fallback). First-release failure handling for unregistered strategies is an implementation concern outside this contract.

### 11.2 Future strategies (extension clause)
The contract anticipates future strategies — for example, hill-climbing, simulated annealing, beam search, parallel seeded-merge, constraint propagation, CP-SAT. Normative rules for future strategies:
- A future strategy MAY declare additional strategy-specific inputs in `additionalInputs` (for example, a neighborhood-size bound for hill climb, a temperature schedule for simulated annealing, a beam width for beam search, a scoring-oracle handle for score-aware search).
- A future strategy MAY set `scoringConsultation: "READ_ONLY_ORACLE"` to opt in to a read-only scoring-oracle handle. A strategy that opts in MUST NOT mutate scoring logic, MUST NOT override the scorer's direction, and MUST preserve scorer-owned component responsibility (`docs/scorer_contract.md`).
- No future strategy MAY override scorer-owned logic, rule-engine-owned logic, or retention-owned logic. The strategy-interface extension clause is additive only.
- Adding a future strategy that conforms to this extension clause does not require a `contractVersion` bump. Changes to the strategy-interface contract itself (for example, introducing a new mutation channel) do require a bump.

First release does not activate the `scoringConsultation: "READ_ONLY_ORACLE"` mode; see `docs/future_work.md`.

## 12) First-release composite strategy: `SEEDED_RANDOM_BLIND`
Proposed in this checkpoint (normative):

`SEEDED_RANDOM_BLIND` is a two-phase composite:
1. **Phase 1 — `CR_MINIMUM_PER_DOCTOR` preference seeding.** For each doctor `d` with one or more honored-eligible `CR` requests in the normalized model, attempt to place up to `X` of `d`'s `CR` requests into the candidate roster, subject to rule-engine validity at placement time and to the edge cases enumerated below. `X` is computed per §13.
2. **Phase 2 — `MOST_CONSTRAINED_FIRST` fill.** For all remaining unfilled demand units, fill tightest-slot-first: iterate in an order that prioritizes demand units with the fewest eligible-and-available doctors remaining, breaking ties deterministically under the active `seed` (see §16).

Both phases consult the rule engine for every proposed placement. `SEEDED_RANDOM_BLIND` is scoring-blind end-to-end; Phase 1 prefers `CR` not because honored `CR` has higher scorer reward (the solver does not see scoring), but because Phase 1 is specified to seed `CR` placements up to the `crFloor` before Phase 2 runs.

### 12.1 Phase 1 edge cases (normative)
- **Doctor with fewer than `X` honored-eligible `CR` requests**: Phase 1 places all of that doctor's honored-eligible `CR` requests it can place validly; it does not reach `X` for that doctor. This is expected and not a failure.
- **Doctor with zero honored-eligible `CR` requests**: Phase 1 skips that doctor entirely.
- **`CR` request that conflicts with a fixed assignment**: Phase 1 skips that specific `CR` placement (fixed assignments win; see `docs/domain_model.md` §10.1) and attempts the next `CR` in the doctor's `CR` list. A `CR`-vs-fixed conflict is not a whole-run failure.
- **`CR` request that conflicts with a prior-phase-1 placement or with another doctor's placement**: Phase 1 skips that placement and attempts the next `CR` in the doctor's `CR` list, in strategy-internal deterministic order under `seed`.
- **`CR` request whose placement would be rule-engine-invalid** (for example, same-day hard block on a different slot, back-to-back call adjacency against a fixed-assignment neighbor): Phase 1 skips that placement.

Phase 1 is best-effort. Below-floor outcomes are accepted. Phase 1 MUST NOT fail the whole run on its own account; only Phase 2's inability to fill remaining demand drives `UnsatisfiedResult`.

### 12.2 Phase 2 tie-breaking (normative)
When multiple demand units share the tightest eligibility count, the strategy MUST break ties in a deterministic order under the active `seed`. When multiple eligible-and-available doctors tie for a chosen demand unit, the strategy MUST likewise break ties deterministically under `seed`. Implementation of tie-breaking (for example, seeded shuffle vs. seeded priority queue) is strategy-internal; the contract only requires determinism under §16.

### 12.3 Fill-order policy visibility
The active `fillOrderPolicy` MUST be logged in `SearchDiagnostics` at run start (§18). First-release `fillOrderPolicy` default is `MOST_CONSTRAINED_FIRST`; the contract does not currently register alternative first-release fill-order policies.

## 13) CR floor computation
Proposed in this checkpoint (normative):

The Phase 1 CR floor `X` is configured via `preferenceSeeding.crFloor`:

```
crFloor {
  mode: "SMART_MEDIAN" | "MANUAL"
  manualValue?: integer    // required when mode = "MANUAL"; must be >= 0
}
```

### 13.1 `SMART_MEDIAN` (default)
- `X = floor(median(CR-count-per-doctor))`, where the median is taken over the roster period and over the full set of doctors in the normalized model (including doctors with zero `CR` requests; those contribute `0` to the median distribution).
- This is the default mode when `preferenceSeeding` is omitted or when `preferenceSeeding.crFloor` is omitted.

### 13.2 `MANUAL`
- `X = manualValue`. The operator supplies a non-negative integer directly.

### 13.3 `X = 0` disables Phase 1
When `X = 0` (either because `SMART_MEDIAN` evaluates to zero on the input distribution, or because `manualValue = 0`), Phase 1 is effectively a no-op and the strategy behaves as `MOST_CONSTRAINED_FIRST` fill only.

### 13.4 Logging
The computed `X` MUST be logged in `SearchDiagnostics` at run start (§18). This is a normative audit requirement because:
- under `SMART_MEDIAN`, `X` depends on run-input doctor/`CR` distribution, so reconstructing run behavior without the logged `X` requires re-deriving it from the input,
- under `MANUAL`, `X` was set by the operator and must be recoverable from the run artifact without reaching back into the launcher invocation.

### 13.5 Interaction with fixed assignments
A doctor with one or more fixed assignments on their `CR`-target dates still has `X` attempted for their remaining honored-eligible `CR` placements per §12.1. Fixed assignments are not counted as `CR` placements toward `X`; they are normalized input facts, not preference-seeded placements.

## 14) Whole-run failure and retention boundary
Proposed in this checkpoint (normative):

- **Whole-run failure**: if the active strategy cannot fill every non-fixed demand unit under rule-engine validity within the active termination bounds, the solver MUST return `UnsatisfiedResult` (§10.2). No partial allocations are emitted. Partial-fill candidates MUST NOT leak into `CandidateSet`.
- **Retention boundary**: the solver does not implement retention modes (best-only, top-K, full-candidate). Retention is owned by the selector stage, which sits downstream of the scorer. The solver emits every valid candidate it generates under the active strategy, up to `terminationBounds.maxCandidates`, without per-candidate retention filtering.
- `TrialBatchResult` "best candidate" fields (`docs/domain_model.md` §12.4) are populated retroactively by the selector after scoring. The solver MUST NOT populate best-candidate fields; those fields require scores, which the solver does not have.

Rationale: in v1, retention was entangled with search, which made it hard to run a benchmark campaign that compared strategies by score distribution without also comparing their retention side effects. v2 factors retention out of the solver so solver behavior can be evaluated on candidate-generation quality alone.

## 15) Termination
Proposed in this checkpoint (normative):

- First-release `terminationBounds` surface is exactly one field: `maxCandidates` (required, positive integer).
- The active strategy MUST stop generating new candidates once `candidates.length == maxCandidates`, even if more valid candidates are reachable under the current seed.
- There is no time budget in the first-release surface. Strategies MUST NOT consult wall-clock time as a termination input.
- `maxCandidates` MUST be set by the caller. Defaulting `maxCandidates` at the solver boundary is not in first-release contract scope.

Rationale: a single candidate-count bound keeps the first-release termination surface auditable and reproducible. Wall-clock termination is deliberately excluded because it breaks byte-identical determinism across runs.

## 16) Determinism
Proposed in this checkpoint (normative):
- Given identical `(normalizedModel, ruleEngine, seed, fillOrderPolicy, terminationBounds, preferenceSeeding)` inputs, the solver MUST return byte-identical outputs — identical `CandidateSet.candidates` ordering and content, or identical `UnsatisfiedResult.unfilledDemand` and `reasons` — within a single implementation on a single platform.
- Determinism is required within a single implementation on a single platform. Cross-implementation determinism is not required and is not guaranteed; RNG choices, floating-point ordering, and container iteration order differ across runtimes.
- Any randomized decision the strategy makes (for example, tie-break selection under `MOST_CONSTRAINED_FIRST`, `CR` ordering within a doctor's seed list) MUST derive exclusively from `seed`. Strategies MUST NOT consult ambient entropy sources.

An implementation that produces non-byte-identical outputs under identical inputs on a single platform is contract-broken regardless of its observed search quality.

## 17) Operator-tuneable surface (v1 parity)
Proposed in this checkpoint (normative):

The solver's first-release operator-tuneable surface consists of:
- **`crFloor.manualValue`** (when `crFloor.mode = "MANUAL"`), extracted from sheet inputs at parser boundary in the same manner as scorer weights (`docs/scorer_contract.md` §15).
- The `SMART_MEDIAN` default mode MAY itself be selected by operator configuration as the alternative to `MANUAL`; the computed `X` remains data-derived.

Scorer component weights are also operator-tuneable and are governed by `docs/scorer_contract.md` §15.

Blueprint §16's current "routine variation" wording is narrower than this combined surface and is scheduled for a clarifying patch in this contract-closure round.

## 18) Diagnostics
Proposed in this checkpoint (normative):

The solver emits two diagnostic shapes:

### 18.1 `SearchDiagnostics` (per solver invocation)
Run-level transparency payload (`docs/domain_model.md` §12.2). Solver-owned fields populated at run start or over the course of the run:
- `strategyId` — the active strategy identifier,
- `fillOrderPolicy` — the active fill-order policy,
- `crFloorComputed` — the `X` value used by Phase 1 (§13.4),
- `crFloorMode` — `"SMART_MEDIAN"` or `"MANUAL"`,
- `seed` — the input seed used for this invocation,
- candidate-generation funnel counts (attempts, rule-engine rejections by reason, candidate-emit count, unfilled-demand count on the failure branch),
- any strategy-specific transparency fields declared by the active `StrategyDescriptor`.

### 18.2 `TrialBatchResult` (per batch)
If the active strategy surfaces candidate generation in batches, each batch MUST carry a `TrialBatchResult` per `docs/domain_model.md` §12.4 with:
- `batchId`,
- the batch's `TrialCandidate[]`,
- retention metadata fields **unpopulated** by the solver (retention is selector-owned; see §14),
- the best-candidate field **unpopulated** by the solver (requires scoring; populated retroactively by the selector).

A first-release implementation that does not surface batches MAY omit `TrialBatchResult` emissions entirely. The solver MUST NOT emit a `TrialBatchResult` that carries a best-candidate field populated without downstream scoring.

## 19) Consistency with adjacent contracts
Repo-settled alignments:
- Consistent with blueprint §5 and §7.5: solver performs pure compute search against the rule engine and does not own hard-rule definition, transport, or sheet I/O.
- Consistent with `docs/rule_engine_contract.md`: solver uses the rule engine as the sole hard-validity authority; solver does not re-derive validity from raw normalized facts.
- Consistent with `docs/scorer_contract.md`: solver emits unscored candidates; scorer ranks them; the solver MUST NOT consult scoring.
- Consistent with `docs/domain_model.md` §10.1: fixed assignments are first-class normalized input, count toward demand, and are not movable by the solver.
- Consistent with `docs/parser_normalizer_contract.md`: solver consumes `CONSUMABLE` parser output only and does not recover lost parser meaning.

Proposed in this checkpoint:
- This contract formalizes the scoring-blind, strategy-pluggable, whole-run-failure surface of the solver while remaining aligned with the rule-engine / scorer / parser / domain-model boundaries.

## 20) Explicit deferrals
The following are explicitly deferred and not fixed by this document:
- concrete function/API signatures and language-specific shapes,
- internal module decomposition within the solver,
- second and subsequent strategy implementations (hill-climb, simulated annealing, beam search, parallel seeded-merge, constraint propagation, CP-SAT); see `docs/future_work.md`,
- activation of the `scoringConsultation: "READ_ONLY_ORACLE"` extension clause for score-aware strategies; see `docs/future_work.md`,
- parallel execution transport, worker coordination, and cross-worker merge semantics for parallel seeded-merge strategies,
- retention-stage re-emergence under scoring-aware solvers (for example, mid-search retention decisions informed by scoring); see `docs/future_work.md`,
- alternative fill-order policies beyond `MOST_CONSTRAINED_FIRST`,
- alternative `crFloor` computations beyond `SMART_MEDIAN` and `MANUAL`,
- time-budget termination,
- cross-implementation determinism.

## 21) Current checkpoint status
### Repo-settled in prior docs
- solver boundary role (blueprint §7.5),
- first-release strategy direction (seeded randomized; blueprint §16),
- reproducibility anchor (blueprint §5; `docs/scorer_contract.md` §17),
- fixed-assignment normalized-input semantics (`docs/domain_model.md` §10.1; `docs/parser_normalizer_contract.md` §14).

### Proposed and adopted in this checkpoint
- scoring-blind public contract with `(normalizedModel, ruleEngine, seed, fillOrderPolicy, terminationBounds, preferenceSeeding) → CandidateSet | UnsatisfiedResult` shape,
- `CandidateSet` / `UnsatisfiedResult` branch discipline with whole-run failure on any unfillable slot,
- named-strategy pluggability with stable `StrategyDescriptor` shape and additive extension clause for future strategies,
- first-release `SEEDED_RANDOM_BLIND` composite (`CR_MINIMUM_PER_DOCTOR` Phase 1 + `MOST_CONSTRAINED_FIRST` Phase 2),
- `crFloor` computation with `SMART_MEDIAN` default and `MANUAL` override, with `X` logged in diagnostics at run start,
- `maxCandidates`-only termination,
- byte-identical determinism within a single implementation on a single platform,
- retention boundary moved downstream to the selector stage; solver emits every valid candidate up to `maxCandidates`,
- diagnostics surface (`SearchDiagnostics` + optional `TrialBatchResult`) with solver-owned fields and unpopulated selector-owned fields.

### Still open / deferred
- concrete API signatures and module decomposition,
- second and subsequent strategy implementations,
- scoring-oracle extension-clause activation for score-aware strategies,
- parallel-strategy transport and merge semantics.

This document is a first-pass working draft checkpoint intended to unblock implementation planning without reopening broader architecture scope.
