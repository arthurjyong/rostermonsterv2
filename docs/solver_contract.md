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
- The solver MUST NOT consume the scorer interface, any scoring configuration (`scoringConfig`), any soft-effect magnitude, or any objective signal — **except** when the active strategy opts into the §11.2 `scoringConsultation: "READ_ONLY_ORACLE"` extension clause, in which case the strategy MAY consume scoring as a read-only oracle subject to the read-only constraints in §11.2 (no mutation, no direction override, no scorer-owned-component alteration). The default — and the rule for strategies that do NOT opt in — is the unconditional prohibition. `SEEDED_RANDOM_BLIND` (§12) does not opt in and remains scoring-blind end-to-end. `LAHC` (§12A) does opt in per §12A.6.
- The solver MUST NOT read any state outside the declared inputs. No environment variables, no clocks, no filesystem.
- Strategies MAY declare additional strategy-specific inputs in their strategy descriptor (§11). Such additions MUST NOT override this contract's prohibitions, except via the explicit §11.2 extension-clause mechanism above. In particular, strategy-specific inputs MUST NOT smuggle scoring logic into a strategy that has not declared `scoringConsultation: "READ_ONLY_ORACLE"` (e.g., MUST NOT smuggle scoring into `SEEDED_RANDOM_BLIND`).

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

### 11.1 Registered strategies
The contract registers the following named strategies:
- `SEEDED_RANDOM_BLIND` — see §12. *(First-release strategy; registered at solver-contract closure 2026-04-25 per `docs/decision_log.md` D-0026.)*
- `LAHC` (Late Acceptance Hill Climbing) — see §12A. *(Registered M6 C1 per `docs/decision_log.md` D-0067; activates the §11.2 `scoringConsultation: "READ_ONLY_ORACLE"` extension clause.)*

Per §2 + §11.2, registering a new strategy that conforms to the §11 strategy-interface contract does NOT require a `contractVersion` bump; the strategy-interface itself is unchanged.

Callers that request an unregistered `strategyId` MUST be rejected at strategy-resolution time, **before** any §10 `CandidateSet` or `UnsatisfiedResult` construction begins. Such a rejection is not a §10 output value — it never enters the §10 output schema at all, and therefore does not require a slot inside the `CandidateSet | UnsatisfiedResult` branch discipline (§10.3). The concrete shape of the strategy-resolution failure (exception class, structured error object, return code) is an implementation concern outside this contract.

### 11.2 Future strategies (extension clause)
The contract anticipates future strategies — for example, hill-climbing, simulated annealing, beam search, parallel seeded-merge, constraint propagation, CP-SAT. Normative rules for future strategies:
- A future strategy MAY declare additional strategy-specific inputs in `additionalInputs` (for example, a neighborhood-size bound for hill climb, a temperature schedule for simulated annealing, a beam width for beam search, a scoring-oracle handle for score-aware search).
- A future strategy MAY set `scoringConsultation: "READ_ONLY_ORACLE"` to opt in to a read-only scoring-oracle handle. A strategy that opts in MUST NOT mutate scoring logic, MUST NOT override the scorer's direction, and MUST preserve scorer-owned component responsibility (`docs/scorer_contract.md`).
- No future strategy MAY override scorer-owned logic, rule-engine-owned logic, or retention-owned logic. The strategy-interface extension clause is additive only.
- Adding a future strategy that conforms to this extension clause does not require a `contractVersion` bump. Changes to the strategy-interface contract itself (for example, introducing a new mutation channel) do require a bump.

First release (M2 C1 closure 2026-04-25 per `docs/decision_log.md` D-0026) did not activate the `scoringConsultation: "READ_ONLY_ORACLE"` mode. M6 C1 (2026-05-07 per `docs/decision_log.md` D-0067) activated it for `LAHC`; see §12A.6.

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

## 12A) Registered strategy: `LAHC` (Late Acceptance Hill Climbing)
Proposed in this checkpoint (M6 C1 per `docs/decision_log.md` D-0067) (normative):

`LAHC` is a score-aware local-search strategy that escapes local optima via a history-list accept criterion. It is the second registered strategy alongside §12's `SEEDED_RANDOM_BLIND`. LAHC conforms to the §11 strategy-interface contract and activates the §11.2 `scoringConsultation: "READ_ONLY_ORACLE"` extension clause (no `contractVersion` bump per §2 + §11.2; the strategy-interface itself is unchanged).

### 12A.1 Algorithm
Per LAHC trajectory, state variables are: `currentRoster`, `currentScore`, `historyList[L]`, `bestSoFar`, `idleIters`, `currentIter`. Steps:
1. **Seed roster.** Produce an initial valid roster via `SEEDED_RANDOM_BLIND`'s two-phase composite (§12 Phase 1 CR seeding + §12 Phase 2 most-constrained-first fill). Initialize `currentRoster := seedRoster`, `currentScore := score(seedRoster)` (via the read-only oracle, §12A.6), `bestSoFar := currentScore`, `idleIters := 0`, `currentIter := 0`.
2. **Initialize history list.** A queue of length `L` (default `1000` per §12A.5) initialized with `currentScore` in every slot.
3. **Inner loop.** Iterate per pass:
   - **a. Move generation.** Generate a candidate move via seeded random selection. Move types are strategy-internal — implementation-specific (e.g., pairwise doctor swap on the same date, single-doctor reassignment to a different date, section-aware swap). The move generator MUST: (i) be deterministic given `trajectorySeed_i` + iteration order, (ii) consult the rule engine to filter rule-engine-invalid moves before evaluation, (iii) be ergodic over the rule-engine-valid roster space (no unreachable configurations).
   - **b. Evaluation.** Compute `proposedScore := score(proposedRoster)` via the read-only scoring oracle (§12A.6).
   - **c. Accept criterion.** Accept iff `proposedScore >= historyList[currentIter mod L]`.
   - **d. State update.** If accepted, set `currentRoster := proposedRoster` AND `currentScore := proposedScore`; else leave `currentRoster` and `currentScore` unchanged. (Both must update together so steps e + f see the post-acceptance score.)
   - **e. History list update.** `historyList[currentIter mod L] := currentScore`. (Standard LAHC overwrite per Burke & Bykov 2008/2017. As the circular queue wraps every `L` iterations, old scores age out — which is what enables temporary worsening moves to be accepted later if they meet an older score floor. A `max(...)` update would make each slot a non-decreasing high-water mark, blocking late-acceptance behavior and degrading LAHC into greedy threshold search.)
   - **f. Best-so-far + idle counter.** If `currentScore > bestSoFar`, set `bestSoFar := currentScore` and reset `idleIters := 0`; else `idleIters += 1`. (`bestSoFar` advances only on strict improvement to keep the idle counter monotone in "no-improvement" iterations.)
   - **g. Increment.** `currentIter += 1`.
4. **Inner loop termination.** Stop when EITHER `idleIters >= idleThreshold` OR `currentIter >= maxIters` (§12A.3).
5. **Emit.** The trajectory's terminal `currentRoster` is emitted as a single `TrialCandidate`.

### 12A.2 K-candidate emission (D-0067 sub-decision 1)
LAHC emits K candidates via **K independent seeded trajectories** — NOT K observations along a single trajectory, NOT K parallel restarts:
- Outer loop: for `i` in `[0, terminationBounds.maxCandidates)`:
  - Compute `trajectorySeed_i = derive(seed, i)`, where `derive(...)` is a deterministic, documented seed-derivation function (e.g., `splitmix64(seed, i)`); the strategy implementation MUST document and pin the chosen derivation.
  - Run a full LAHC inner loop (§12A.1) with `trajectorySeed_i`.
  - Emit terminal roster as a `TrialCandidate`.
- Trajectories are independent — no information flows between them (no cross-trajectory pruning, no shared best-so-far). This preserves byte-identical determinism per §16 and the analyzer-side separation per `docs/decision_log.md` D-0056 ("solver IS the exploration mechanism"; analyzer is the passive observer).

Rejected alternative — K-observations-along-a-single-trajectory: would produce highly correlated near-clone candidates (consecutive trajectory points share most of their assignment matrix), defeating the K-candidate diagnostic role per D-0056.

### 12A.3 Termination (D-0067 sub-decision 2)
**Outer-loop termination**: `terminationBounds.maxCandidates` per §15. LAHC stops outer iteration once `K = maxCandidates` trajectories complete.

**Inner-loop termination per trajectory**:
- `idleThreshold` (default `5000` per §12A.5) — inner loop stops when no improvement in last `idleThreshold` iterations.
- `maxIters` (default `100,000` per §12A.5) — hard cap on inner-loop iterations per trajectory.
- **Wall-clock termination is NOT in v1 scope** per §15's existing rationale (breaks byte-identical determinism per §16).

Inner-loop bounds are LAHC-specific and live in `additionalInputs.lahcParams` per §11.2's strategy-specific input declaration; they are NOT part of `terminationBounds` (which §15 keeps narrow at `maxCandidates`-only).

### 12A.4 Determinism (D-0067 sub-decision 3)
Given identical `(normalizedModel, ruleEngine, seed, fillOrderPolicy, terminationBounds, preferenceSeeding, additionalInputs.lahcParams)` inputs, LAHC MUST produce byte-identical output per §16.

Determinism preservation requires:
- `derive(seed, i)` is a deterministic, documented, pinned function.
- Move-selection RNG within each trajectory derives exclusively from `trajectorySeed_i`.
- History list state is deterministic given iteration order and per-iteration acceptance.
- Scoring is deterministic per `docs/scorer_contract.md` §17; the read-only oracle preserves this.

Wall-clock termination is excluded for the same reason it's excluded in §15 — breaks determinism. Idle-iter and max-iter termination preserve determinism (count-based, not time-based).

### 12A.5 History-list and termination defaults (D-0067 sub-decision 4)
Default values for `additionalInputs.lahcParams`:
- `L = 1000` (history-list length).
- `idleThreshold = 5,000` (= 5 × `L`).
- `maxIters = 100,000`.

Rationale: `L = 1000` is a literature default for combinatorial problems at roster scale (Burke & Bykov 2017's LAHC study across NRP-like domains used `L ∈ [500, 10000]`). `idleThreshold = 5L` is a common LAHC convention — gives the algorithm a chance to escape multiple local optima before declaring convergence. `maxIters = 100k` fits within Cloud Run's `UrlFetchApp` 6-minute synchronous budget per `docs/decision_log.md` D-0051 at ICU/HD scale (~30-60s per trajectory empirically, K trajectories sequential). Defaults are tunable via the maintainer-only surface per §12A.7.

### 12A.6 Scoring oracle activation (D-0067 sub-decision 5)
LAHC opts into the §11.2 extension clause:
- `StrategyDescriptor.scoringConsultation: "READ_ONLY_ORACLE"`.
- `additionalInputs: ["scoringOracle", "lahcParams"]`.
- The scoring oracle is **read-only**: LAHC MUST NOT mutate scoring logic, MUST NOT override the scorer's `HIGHER_IS_BETTER` direction (per `docs/scorer_contract.md` §10), MUST NOT alter scorer-owned components.
- Score values consulted by LAHC's accept criterion (§12A.1 step 3) MUST come from `docs/scorer_contract.md`-conforming scorer invocations on each candidate roster (or its delta-evaluated equivalent — see FW-0010 for streaming/delta scoring as a possible M6 C2 follow-up).

Per §11.2 + §2, opting into the extension clause is additive only and does NOT require a `contractVersion` bump.

### 12A.7 Operator-tunable surface (LAHC params — maintainer only)
Per `docs/decision_log.md` D-0066 sub-decision 6 + D-0067 sub-decision 6, LAHC params are **maintainer only** for v1:
- **Cloud mode**: Python module constants (e.g., `python/rostermonster/solver/lahc.py`). The cloud service uses defaults baked at deployment time; no runtime override.
- **Local mode**: CLI flags override module defaults: `--strategy LAHC`, `--lahc-history-length`, `--lahc-iter-cap`, `--lahc-idle-threshold`.
- **NO scorer-config tab additions, NO operator-facing UI changes.** LAHC params do NOT extract from sheet inputs; they do NOT appear in the Scorer Config tab; they do NOT bump the parser/normalizer contract.
- The active `lahcParams` (effective values used) MUST be logged in `SearchDiagnostics` at run start per §12A.9.

### 12A.8 Failure semantics
- If the seed roster step (§12A.1 step 1) fails (`SEEDED_RANDOM_BLIND` returns `UnsatisfiedResult` because rule-engine-invalid demand cannot be filled), LAHC propagates that failure as `UnsatisfiedResult` per §10.2 — same discipline as `SEEDED_RANDOM_BLIND` standalone.
- If a LAHC trajectory's inner loop produces no improvement and terminates by `idleThreshold` or `maxIters`, the trajectory's terminal roster IS the seed roster (still rule-engine-valid; emitted as a `TrialCandidate`).
- LAHC trajectories are independent. A move-generator implementation defect that fails one trajectory's inner loop is a contract-breaking defect (§10.1's empty `CandidateSet` prohibition); it MUST fail loudly, NOT silently degrade other trajectories.
- Empty `CandidateSet` is a contract-breaking defect per §10.1. Since `terminationBounds.maxCandidates >= 1` per §9, LAHC MUST emit at least one `TrialCandidate` on the success branch. If all `K` trajectories' seed roster steps fail (every Phase 1+Phase 2 returns `UnsatisfiedResult`), LAHC returns `UnsatisfiedResult` per §10.3.

### 12A.9 Diagnostics
Per §18.1, LAHC's `SearchDiagnostics` MUST include strategy-specific transparency fields:
- `lahcHistoryListLength` — the `L` value used.
- `lahcMaxIters` — the per-trajectory iteration cap.
- `lahcIdleThreshold` — the per-trajectory idle-iteration cutoff.
- `seedDerivationFunction` — string identifier of the `derive(seed, i)` function used (e.g., `"splitmix64"`).
- `perTrajectoryIters[i]` — actual iteration count per trajectory `i` ∈ `[0, K)` (variable due to `idleThreshold` / `maxIters` termination).
- `perTrajectoryAcceptedMoves[i]` — count of accepted moves per trajectory.
- `perTrajectoryFinalScore[i]` — terminal score per trajectory (post-§12A.4 determinism check).

These fields support post-run analysis via the M5 analyzer per `docs/decision_log.md` D-0066 sub-decision 7 — operator runs LAHC and `SEEDED_RANDOM_BLIND`, renders each `AnalyzerOutput` separately via the launcher, and manually cross-references the two comparison tabs in the source spreadsheet.

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

Strategies that consult a read-only scoring oracle (e.g., `LAHC` per §12A.6) preserve determinism via deterministic trajectory-seed derivation and deterministic scoring per `docs/scorer_contract.md` §17. The scoring oracle returns identical scores for identical inputs, so byte-identical determinism extends to score-aware strategies as long as their RNG, history list, and acceptance logic are deterministic given seed + iteration order.

## 17) Operator-tuneable surface (v1 parity)
Proposed in this checkpoint (normative):

The solver's first-release operator-tuneable surface consists of:
- **`crFloor.manualValue`** (when `crFloor.mode = "MANUAL"`), extracted from sheet inputs at parser boundary in the same manner as scorer weights (`docs/scorer_contract.md` §15).
- The `SMART_MEDIAN` default mode MAY itself be selected by operator configuration as the alternative to `MANUAL`; the computed `X` remains data-derived.

Scorer component weights are also operator-tuneable and are governed by `docs/scorer_contract.md` §15.

Strategy-specific knobs declared via `additionalInputs` (per §11.2) are NOT necessarily part of the operator-tuneable surface at parser boundary. `LAHC`'s `lahcParams` per §12A.7 are **maintainer only** (Python module constants for cloud defaults; CLI flag overrides for local tuning) — they do NOT extract from sheet inputs, do NOT appear in the Scorer Config tab, and do NOT bump the parser/normalizer contract. This separation lets future score-aware strategies iterate on inner-loop tuning without forcing template-author churn.

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
- Consistent with `docs/scorer_contract.md`: `SEEDED_RANDOM_BLIND` emits unscored candidates and MUST NOT consult scoring; `LAHC` consults scoring **read-only** via the §12A.6 oracle and MUST NOT mutate scoring logic, override scorer direction, or alter scorer-owned components. Scorer ranks all emitted candidates (regardless of strategy) downstream.
- Consistent with `docs/domain_model.md` §10.1: fixed assignments are first-class normalized input, count toward demand, and are not movable by the solver.
- Consistent with `docs/parser_normalizer_contract.md`: solver consumes `CONSUMABLE` parser output only and does not recover lost parser meaning. LAHC's `lahcParams` are NOT parser-boundary inputs (per §17); they are maintainer-only knobs outside the parser/normalizer contract surface.
- Consistent with `docs/decision_log.md` D-0066 (M6 framing) + D-0067 (M6 C1 LAHC algorithm spec): LAHC registers via §11.2's extension clause without `contractVersion` bump; only the wrapper envelope's `solverStrategy` enumerant crosses the solver boundary so the M5 analyzer + ops trail can see what ran (envelope-shape additive bump location settled in M6 C3).

Proposed in this checkpoint:
- This contract formalizes the scoring-blind (default) / score-aware-via-read-only-oracle (extension) strategy-pluggable surface of the solver while remaining aligned with the rule-engine / scorer / parser / domain-model boundaries.

## 20) Explicit deferrals
The following are explicitly deferred and not fixed by this document:
- concrete function/API signatures and language-specific shapes,
- internal module decomposition within the solver,
- third and subsequent strategy implementations (simulated annealing, beam search, parallel seeded-merge, constraint propagation, CP-SAT, tabu search); see `docs/future_work.md` FW-0004. *(Second strategy `LAHC` registered M6 C1 per D-0067; see §12A.)*
- ~~activation of the `scoringConsultation: "READ_ONLY_ORACLE"` extension clause for score-aware strategies; see `docs/future_work.md`~~ — *(activated M6 C1 per D-0067; LAHC opts in per §12A.6.)*
- parallel execution transport, worker coordination, and cross-worker merge semantics for parallel seeded-merge strategies; see FW-0005,
- retention-stage re-emergence under scoring-aware solvers (for example, mid-search retention decisions informed by scoring); see `docs/future_work.md`,
- alternative fill-order policies beyond `MOST_CONSTRAINED_FIRST`,
- alternative `crFloor` computations beyond `SMART_MEDIAN` and `MANUAL`,
- time-budget termination (excluded from both `SEEDED_RANDOM_BLIND`'s `terminationBounds` per §15 AND `LAHC`'s `lahcParams` inner-loop termination per §12A.3 — wall-clock termination breaks byte-identical determinism per §16),
- cross-implementation determinism.

## 21) Current checkpoint status
### Repo-settled in prior docs
- solver boundary role (blueprint §7.5),
- first-release strategy direction (seeded randomized; blueprint §16),
- reproducibility anchor (blueprint §5; `docs/scorer_contract.md` §17),
- fixed-assignment normalized-input semantics (`docs/domain_model.md` §10.1; `docs/parser_normalizer_contract.md` §14).

### Proposed and adopted in M2 C1 closure (2026-04-25 per `docs/decision_log.md` D-0024..D-0029)
- scoring-blind public contract with `(normalizedModel, ruleEngine, seed, fillOrderPolicy, terminationBounds, preferenceSeeding) → CandidateSet | UnsatisfiedResult` shape,
- `CandidateSet` / `UnsatisfiedResult` branch discipline with whole-run failure on any unfillable slot,
- named-strategy pluggability with stable `StrategyDescriptor` shape and additive extension clause for future strategies,
- first-release `SEEDED_RANDOM_BLIND` composite (`CR_MINIMUM_PER_DOCTOR` Phase 1 + `MOST_CONSTRAINED_FIRST` Phase 2),
- `crFloor` computation with `SMART_MEDIAN` default and `MANUAL` override, with `X` logged in diagnostics at run start,
- `maxCandidates`-only termination at the boundary surface,
- byte-identical determinism within a single implementation on a single platform,
- retention boundary moved downstream to the selector stage; solver emits every valid candidate up to `maxCandidates`,
- diagnostics surface (`SearchDiagnostics` + optional `TrialBatchResult`) with solver-owned fields and unpopulated selector-owned fields.

### Adopted in M6 C1 closure (2026-05-07 per `docs/decision_log.md` D-0067)
- registered second strategy `LAHC` per §11.1, registered via §11.2's extension clause without `contractVersion` bump,
- `LAHC` algorithm spec per §12A (K-independent-seeds emission, idle/hard-iter inner termination, history-list `L=1000` default, `maxIters=100,000` default, `idleThreshold=5,000` default, deterministic trajectory-seed derivation),
- activated §11.2's `scoringConsultation: "READ_ONLY_ORACLE"` extension clause for score-aware strategies (`LAHC` opts in per §12A.6),
- `LAHC`'s `lahcParams` declared as strategy-specific via `additionalInputs.lahcParams` (NOT part of `terminationBounds` boundary surface; maintainer-only operator surface per §12A.7 — Python module constants for cloud defaults, CLI flag overrides for local tuning; no scorer-config tab additions).

### Still open / deferred
- concrete API signatures and module decomposition,
- third and subsequent strategy implementations (see §20 + FW-0004),
- parallel-strategy transport and merge semantics (FW-0005),
- alternative fill-order policies, alternative `crFloor` computations, time-budget termination, cross-implementation determinism (see §20).

This document is a first-pass working draft checkpoint intended to unblock implementation planning without reopening broader architecture scope. M6 C1 (per D-0067) extends it with `LAHC` strategy registration via the §11.2 extension clause; the document remains at `contractVersion: 1` because the strategy-interface contract itself is unchanged.
