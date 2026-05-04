# Analysis Contract (First-Pass Working Draft)

## 1) Contract status and scope
This document defines the analyzer boundary that sits between today's CLI FULL-retention output (`docs/selector_contract.md` §13.2 + §14) and the downstream Apps Script analyzer renderer + upload portal that M5 C2 / C3 deliver.

It is intended to be concrete enough for implementation planning for M5 C1 analyzer-engine work.

It explicitly separates:
- repo-settled anchors,
- analyzer-boundary decisions adopted in this checkpoint,
- still-open items in this checkpoint,
- and explicit deferrals.

Scope is limited to analyzer-stage `(envelope, sidecars) → AnalyzerOutput` construction, top-K selection, and the comparison aggregates the renderer consumes. This is not a renderer, upload-portal, selector, scorer, solver, writeback, or cloud-compute design document.

The analyzer is **purely additive**. It introduces no contract changes upstream — selector, scorer, solver, rule_engine, writeback, snapshot_adapter, parser_normalizer, and cloud_compute contracts are unchanged by this contract's introduction (per `docs/decision_log.md` D-0055).

## 2) Contract identity and versioning
Contract identity/version for binding:
- `contractId: ANALYSIS`
- `contractVersion: 1`

Version bump rule (normative):
- bump `contractVersion` only when analyzer input shape, `AnalyzerOutput` shape in a way that breaks v1-targeted readers (per §14), top-K selection semantics, solver-agnostic property, or determinism guarantees change.
- do **not** bump for wording cleanup, formatting, added examples, additive optional output fields that v1-targeted readers can ignore (per §14), or clarification that does not change behavior.

### 2.1 Version history
- **v1 (2026-05-04, this PR):** initial analysis contract closure per `docs/decision_log.md` D-0056..D-0058. Input shape, `AnalyzerOutput` shape, pure top-K selection (no diversity heuristic), Tiers 1–6 emission scope.

## 3) Status discipline used in this document
Each normative statement is classified as one of:
- **Repo-settled**: already anchored by existing repo contracts/blueprint/decision log.
- **Proposed in this checkpoint**: adopted here as first-release analyzer-boundary direction.
- **Still open in this checkpoint**: recognized as unresolved here and left explicit.
- **Deferred**: intentionally out of this checkpoint's decision scope.

## 4) Repo-settled architecture anchors
The following are treated as repo-settled anchors:
- The pipeline is three-stage `solver → scorer → selector`; the selector is the final compute stage, and writeback/analyzer are downstream sibling consumers of its output (`docs/decision_log.md` D-0027, D-0055).
- Score direction is `HIGHER_IS_BETTER` (`docs/scorer_contract.md` §10; `docs/domain_model.md` §4.2, §11.1); analyzer ranks under this direction.
- `ScoreResult` carries `totalScore` plus a required component breakdown over every first-release component identifier from `docs/domain_model.md` §11.2 (`docs/scorer_contract.md` §10; `docs/decision_log.md` D-0025).
- `FinalResultEnvelope` shape under `FULL` retention carries `runEnvelope`, `winnerAssignment`, `winnerScore`, `searchDiagnostics`, and `candidatesSummaryPath` + `candidatesFullPath` pointers (`docs/selector_contract.md` §10 + §13.2).
- Sidecar shapes under `FULL` retention are `candidates_summary.csv` (one row per retained candidate, header invariant under `schemaVersion: 1`) and `candidates_full.json` (per-candidate full `AssignmentUnit[]` + full `ScoreResult`) (`docs/selector_contract.md` §14.1 + §14.2).
- The wrapper envelope from the writeback contract — `FinalResultEnvelope` plus snapshot subset (six categories per `docs/writeback_contract.md` §9) plus `doctorIdMap` — is the canonical artifact the CLI emits and that downstream consumers (writeback library, analyzer engine) read (`docs/decision_log.md` D-0044, D-0045).
- Top-K selection is the analyzer's responsibility, NOT the selector's. No new selector retention mode is introduced (`docs/decision_log.md` D-0055 sub-decision 4).
- Cloud-side FULL retention support is explicitly deferred to `docs/future_work.md` FW-0030. The analyzer engine in M5 is wired against today's CLI FULL retention output only.

## 5) Purpose
Repo-settled intent + checkpoint narrowing:
- Pick the top K candidates from a `FULL`-retention output by total score, and produce a renderer-consumable `AnalyzerOutput` that decomposes each candidate's score into operator-inspectable components and aggregates per-doctor / per-day distribution data so the operator can compare candidates side-by-side.
- Act as the operator-side workaround for the weighted-sum scoring formulation pain (`docs/decision_log.md` D-0055): instead of trusting `totalScore`, the operator picks among K candidates with full component breakdowns.
- Act as the calibration framework against which any future score-aware solver-strategy work will be measured (`docs/decision_log.md` D-0055).

## 6) Boundary position
Repo-settled:
- Upstream: the analyzer consumes the wrapper envelope (`final_envelope.json` per `docs/decision_log.md` D-0044/D-0045) plus the FULL-retention sidecar `candidates_full.json` (per `docs/selector_contract.md` §14.2). Both are produced by the local CLI's `--retention FULL` + `--sidecar-dir` path (`python/rostermonster/run.py`).
- Boundary: the analyzer is a pure function `analyze(envelope, fullSidecar, *, topK) → AnalyzerOutput`.
- Downstream: the Apps Script analyzer renderer (M5 C2) consumes `AnalyzerOutput` and writes K roster tabs + 1 comparison tab. The upload portal (M5 C3) accepts a single `AnalyzerOutput` JSON file from the operator and hands it to the renderer.

Proposed in this checkpoint:
- The analyzer is a pure function of its declared inputs (§9). No solver coupling, no scorer coupling, no rule-engine coupling. The analyzer reads the wrapper envelope's public surface and the FULL sidecar's public surface only.
- The analyzer is solver-agnostic by contract (§12). It MUST NOT inspect strategy-specific metadata such as `solverStrategyId` or strategy-specific `searchDiagnostics` fields to switch behavior.
- The analyzer engine has no Apps Script coupling. The upload portal and renderer consume `AnalyzerOutput` by file; the analyzer engine never imports Apps Script libraries.

## 7) What this contract governs
This contract governs:
- the shape of analyzer input (the wrapper envelope + the FULL sidecar JSON, §9),
- the shape of analyzer output (the `AnalyzerOutput` JSON, §10),
- the top-K selection rule and its tiebreaker (§11),
- the solver-agnostic property (§12),
- the comparison aggregates the analyzer emits — Tiers 1–6 of the M5 C1 emission set (§13),
- determinism guarantees (§15),
- schema versioning (§14),
- the analyzer engine's module placement at `python/rostermonster/analysis/`.

## 8) What this contract does not govern
This contract does **not** govern:
- candidate generation, search strategy, fill-order policy, or seeded randomization (see `docs/solver_contract.md`),
- scoring, ranking weights, component definitions, soft-effect evaluation, or scoring-formulation rework (see `docs/scorer_contract.md`),
- hard-validity evaluation (see `docs/rule_engine_contract.md`),
- selector retention modes, sidecar artifact shapes, or candidate identity (see `docs/selector_contract.md`),
- writeback mapping, writeback tab generation, or operator-facing roster-tab presentation (see `docs/writeback_contract.md`),
- cloud compute service shape, request envelope shape, or cloud-side FULL retention plumbing (see `docs/cloud_compute_contract.md`; cloud-side FULL retention support is `docs/future_work.md` FW-0030),
- the Apps Script analyzer renderer's tab layout, formatting, or comparison-tab UX (M5 C2 territory),
- the upload portal's form shape, file-size caps, or operator-facing UX (M5 C3 territory),
- file-system paths, output file naming, or where the `AnalyzerOutput` physically lands on disk (execution-layer concern; see §10.4),
- analyzer renderer invocations, log format, or run lifecycle management,
- broader observability, benchmarking, or campaign-level coordination (`docs/future_work.md` FW-0028),
- doctor-metadata extensions to the snapshot (seniority, leave history, rotation conflicts) — out of M5 scope per `docs/future_work.md` FW-0031.

## 9) Input shape
Analyzer invocations are evaluated against the following inputs:

1. **`envelope`** — the wrapper envelope produced by the local CLI's `--writeback-ready` flow per `docs/decision_log.md` D-0045. Required top-level fields the analyzer consumes:
   - `finalResultEnvelope` — a `FinalResultEnvelope` per `docs/selector_contract.md` §10 with `retentionMode == "FULL"` (§9.1 below).
   - `snapshotSubset` — the six-category snapshot subset per `docs/writeback_contract.md` §9. The analyzer consumes `dayRecords` (for weekend / public-holiday classification per day), `slotTypes` (for `slotKind == "CALL"` vs `STANDBY` classification), `doctors` (for human-readable names), `pointRows` (for per-day call-point values when computing per-doctor cumulative weighted load, §13), and `outputAssignmentRows` (for `slotType ↔ rowOffset` binding the renderer needs to surface). The other categories are not consumed by the analyzer in v1.
   - `doctorIdMap` — the doctor-identity map per `docs/decision_log.md` D-0044 sub-decision 5. The analyzer consumes it to translate sidecar `doctorId` values back to operator-facing names for output.
2. **`fullSidecar`** — the `candidates_full.json` sidecar per `docs/selector_contract.md` §14.2. Required: indexed by `candidateId`, each entry carries the full `AssignmentUnit[]` and the full `ScoreResult` (total + components).
3. **`topK`** — the operator-supplied K (§11). Default 5; bounds `[1, 20]` inclusive; values outside this range are a fail-loud caller defect.
4. **(optional) `analysisConfig`** — reserved for future analyzer-strategy configuration; first release ships no required fields. Future additions MUST follow the additivity rule in §14.

### 9.1 FULL retention required
The analyzer MUST be invoked against a FULL-retention envelope. Analyzer behavior under `BEST_ONLY` is undefined: the FULL sidecar is absent, the candidate population is one, and there is no top-K to compute. Callers that invoke the analyzer against a `BEST_ONLY` envelope MUST receive a fail-loud rejection — the analyzer MUST NOT silently degrade to "K=1, return the winner."

### 9.2 Failure-branch handling
On the `UnsatisfiedResult` failure branch (`docs/selector_contract.md` §15), there is no scored-candidate set to analyze. Analyzer behavior on this input is also fail-loud: the analyzer MUST raise a structured rejection rather than emit a degenerate `AnalyzerOutput`. The operator workflow is "render the failure branch via writeback's diagnostic surface (`docs/writeback_contract.md` §17) — the analyzer is not in scope on the failure branch."

### 9.3 No filesystem reads beyond declared inputs
The analyzer MUST NOT read any state outside the declared inputs. No environment variables, no clocks, no filesystem reads beyond the `envelope` and `fullSidecar` files supplied by the caller.

### 9.4 CSV sidecar is NOT analyzer input
The `candidates_summary.csv` sidecar is operator-debug-only (spreadsheet-grade inspection, per `docs/selector_contract.md` §14.1). The analyzer engine does NOT consume it; passing a `candidates_summary.csv` path to the analyzer is a no-op at best and a contract violation at worst. This is `docs/decision_log.md` D-0057.

## 10) Output shape
The analyzer returns a single `AnalyzerOutput` JSON object. Concrete shape:

```
AnalyzerOutput {
  contractVersion: 1
  generatedAt: ISO-8601 string                 // execution-layer-supplied; see §15
  source: {
    runId: string                              // from envelope.finalResultEnvelope.runEnvelope.runId
    seed: number | null                        // from envelope.finalResultEnvelope.runEnvelope.seed
    sourceSpreadsheetId: string                // ride-through from runEnvelope
    sourceTabName: string                      // ride-through from runEnvelope
  }
  topK: TopKResult
  comparison: ComparisonAggregates
  doctorIdMap: { [doctorId: string]: string }  // ride-through from envelope.doctorIdMap
}
```

### 10.1 `TopKResult`
```
TopKResult {
  requested: int                   // 1..20 inclusive
  returned: int                    // min(requested, candidatesAvailable); see §11
  candidates: [AnalyzerCandidate]  // length == returned; ordered by totalScore desc with §11 tiebreak
}
```

### 10.2 `AnalyzerCandidate`
```
AnalyzerCandidate {
  candidateId: string                          // matches sidecar candidateId
  rankByTotalScore: int                        // 1..returned; 1 == top
  recommended: boolean                         // true iff this candidate's candidateId == finalResultEnvelope.winnerCandidateId
  totalScore: number
  scoreComponents: {
    [componentName: string]: ComponentBreakdown
  }
  ruleViolations: ViolationSummary
  fillStats: { slotsFilled: int, slotsTotal: int }
  perDoctor: { [doctorId: string]: PerDoctorAggregates }
  assignment: AssignmentRefShape               // §10.5
}
```

`scoreComponents` MUST include every first-release component identifier enumerated in `docs/domain_model.md` §11.2 (the nine ICU/HD components: `unfilledPenalty`, `pointBalanceWithinSection`, `pointBalanceGlobal`, `spacingPenalty`, `preLeavePenalty`, `crReward`, `dualEligibleIcuBonus`, `standbyAdjacencyPenalty`, `standbyCountFairnessPenalty`), even when a component contributes zero. This mirrors `docs/scorer_contract.md` §10 — analyzer cannot drop components the scorer was required to emit.

### 10.3 `ComponentBreakdown`
```
ComponentBreakdown {
  weighted: number       // contribution to totalScore (already sign-correct per scorer §10)
  raw: number            // pre-weight magnitude (raw component value before weights[componentName] is applied)
  rankAcrossTopK: int    // 1..returned; 1 == best on this component within the K shown
  gapToNextRanked: number | null   // weighted gap to the next-best candidate on this component; null on rank == returned
}
```

The `raw` field's first-release semantics: implementations MAY emit `weighted / weights[componentName]` when `weights[componentName] != 0`, and MAY emit a sentinel (e.g., `0`) when the weight is zero. v1 readers MUST tolerate either. The `raw` field is a power-user convenience for operator re-prioritization mental math; it is NOT used by the renderer's default tab UX.

### 10.4 `ViolationSummary`
```
ViolationSummary {
  hardCount: int                                 // expected 0 for valid candidates; non-zero is a defect signal
  softCount: int
  softByRule: { [ruleId: string]: int }
  hardByRule: { [ruleId: string]: int }          // for completeness; usually empty
}
```

### 10.5 `AssignmentRefShape`
The renderer needs the per-day per-slot doctor assignment to write the K roster tabs. The analyzer rides this through from the FULL sidecar's `AssignmentUnit[]` shape. v1 ships the assignment as a list of records:

```
AssignmentRefShape = [
  { dateKey: string, slotType: string, doctorId: string }
]
```

`doctorId` is the canonical sidecar identifier; the renderer translates to operator-facing names via `AnalyzerOutput.doctorIdMap`. v1 readers MUST tolerate the list-of-records shape.

### 10.6 `PerDoctorAggregates`
```
PerDoctorAggregates {
  callCount: int                          // count of CALL-slot assignments
  standbyCount: int                       // count of STANDBY-slot assignments
  weekendCallCount: int                   // count of CALL-slot assignments on dayRecords[*].isWeekend == true
  publicHolidayCallCount: int             // count of CALL-slot assignments on dayRecords[*].isPublicHoliday == true
  callPointInitial: number                // from envelope.snapshotSubset.* opening doctor call-point state
  callPointEndOfCycle: number             // initial + sum over CALL assignments of pointRules[(slotType, dateKey)]
  callPointDelta: number                  // callPointEndOfCycle - callPointInitial
  cumulativeWeightedLoad: number          // alias of callPointEndOfCycle for v1; reserved for future per-day weighting refinements
  maxConsecutiveDaysOff: int              // longest run of consecutive dayRecords with no assignment to this doctor
}
```

`callPointInitial` source: the analyzer reads the doctor's opening call-point value from the envelope's snapshot subset. The exact path is implementation-level (the snapshot subset projection from the snapshot is documented in `docs/snapshot_contract.md`); the analyzer MUST NOT synthesize this field.

`isPublicHoliday` source: `envelope.snapshotSubset.dayRecords[*].isPublicHoliday`. ICU/HD first-release pilots may not declare public holidays in the period; in that case `publicHolidayCallCount` is 0 for every doctor.

### 10.7 `ComparisonAggregates`
```
ComparisonAggregates {
  pairwiseHammingDistance: {
    [candidateIdA: string]: { [candidateIdB: string]: int }
  }
  hotDays: [
    { dateKey: string, distinctAssignments: int }
  ]
  lockedDays: [
    { dateKey: string }
  ]
  perCandidateEquity: {
    [candidateId: string]: EquityScalars
  }
}
```

`pairwiseHammingDistance[a][b]` is the count of `(dateKey, slotType)` cells where candidate `a` and candidate `b` assign different doctors. The matrix is symmetric; implementations MAY emit only the upper triangle (`b > a` lexicographically) and v1 readers MUST tolerate either symmetric or upper-triangle layout, looking up `[a][b]` by trying both keys.

`hotDays[*].distinctAssignments` is the count of distinct doctor-tuples assigned across the K candidates on that date. A locked day has `distinctAssignments == 1`. Hot days are the complement: `distinctAssignments > 1`. The list MUST include only `dateKey`s within the run's period.

`lockedDays` is the convenience inverse of `hotDays` for the renderer's default-collapsed tab UX. Renderer derives "% of days locked" from `lockedDays.length / period.length`.

### 10.8 `EquityScalars`
```
EquityScalars {
  callCount: { stdev: number, minMaxGap: int, gini: number }
  weekendCallCount: { stdev: number, minMaxGap: int, gini: number }
  publicHolidayCallCount: { stdev: number, minMaxGap: int, gini: number }
  callPointEndOfCycle: { stdev: number, minMaxGap: number, gini: number }
}
```

Equity scalars are computed across the doctor population for a single candidate. Lower stdev / lower min-max gap / lower Gini == more equitable. Renderer surfaces these as comparison-tab summary scalars; the operator-facing semantic is "candidate A is more equitable on weekend calls than candidate B even though A's totalScore is lower."

### 10.9 Renderer-derivable Tier 7 fields are NOT emitted
Per `docs/decision_log.md` D-0058, the analyzer does NOT emit decision-support tags ("best on `pointBalance`", "lowest `spacingPenalty`", etc.). The renderer derives these from the raw fields above (`scoreComponents[*].rankAcrossTopK == 1` is the "best on dimension X" signal). This keeps the analyzer surface tight and lets the renderer iterate the tag UX without a contract bump.

## 11) Top-K selection — pure score-rank, no diversity heuristic
Proposed in this checkpoint (normative):

The analyzer selects the K returned candidates as follows:
1. Sort the FULL sidecar's candidates by `ScoreResult.totalScore` descending.
2. Tiebreak ties on equal `totalScore` by ascending `candidateId` (lexicographic ASCII order). `candidateId` is run-monotonic and dense per `docs/selector_contract.md` §16.1, so the tiebreak is well-defined for any equal-score pair.
3. Take the first `min(requested, candidatesAvailable)` entries.
4. If `candidatesAvailable < requested`, set `topK.returned = candidatesAvailable` (the analyzer returns fewer than `requested` rather than padding or failing). v1 readers MUST tolerate `returned < requested`.
5. If `requested > 20`, the analyzer MUST raise a structured rejection ("K must be ≤ 20"). This is fail-loud per `docs/decision_log.md` D-0056.
6. If `requested < 1`, the analyzer MUST also raise a structured rejection.

**No diversity heuristic.** Per `docs/decision_log.md` D-0056, the analyzer does NOT compute Hamming-distance thresholds, cluster grouping, or any other diversity-aware selection rule. If the K candidates are near-duplicates of each other, that is signal — the operator is meant to see "the solver thinks these are all equivalent" rather than have the analyzer fabricate spread the solver did not produce. Tier 5's `pairwiseHammingDistance` matrix (§10.7) is the operator's diagnostic for "are my K candidates actually different?"

This cleanly separates concerns: the solver is the exploration mechanism; the analyzer is the passive observer. Diversity-aware selection (DPPs, submodular maximization, max-min diversification) belongs in solver-strategy work (M6 territory), not at the analyzer stage.

### 11.1 `recommended` flag derivation
The `AnalyzerCandidate.recommended` boolean is `true` iff the candidate's `candidateId` matches the winner candidate identified in `envelope.finalResultEnvelope` (the BEST_ONLY pick). At most one candidate in `topK.candidates` carries `recommended: true` (and exactly one when `requested ≥ 1` AND the winner candidate is among the top K by score-rank — which it always is, since the winner is the highest-score candidate by `HIGHEST_SCORE_WITH_CASCADE` per `docs/selector_contract.md` §12). Implementations MAY assert this invariant.

## 12) Solver-agnostic property
Proposed in this checkpoint (normative):

The analyzer MUST NOT inspect `solverStrategyId` or any strategy-specific metadata in `searchDiagnostics`, `runEnvelope`, or elsewhere on the envelope to switch behavior. Concretely:
- The analyzer MUST produce the same `AnalyzerOutput` for any pair of envelopes whose `finalResultEnvelope.winnerAssignment`, `finalResultEnvelope.winnerScore`, `fullSidecar.candidates`, `snapshotSubset`, and `doctorIdMap` are identical, regardless of which solver strategy produced them.
- The analyzer MAY echo `runEnvelope` fields (e.g., `runId`, `seed`) into `AnalyzerOutput.source` for traceability, but MUST NOT branch on them.
- Future solver strategies (LAHC etc., parked for M6) that produce a contract-compliant `FinalResultEnvelope` + FULL sidecar are analyzable without analyzer code changes.

Strategy-aware diagnostics (e.g., LAHC iteration counts, simulated-annealing temperature curves) are explicitly out of analyzer scope. They belong in a separate strategy-aware diagnostic surface that future work may introduce.

## 13) Comparison emission scope — Tiers 1–6
Proposed in this checkpoint (normative):

The analyzer's comparison emission set is partitioned into seven conceptual tiers (the M5 C1 design-thread organization). v1 emits Tiers 1–6; Tier 7 is renderer-derived per §10.9.

- **Tier 1 — score decomposition** (`AnalyzerCandidate.totalScore` + `scoreComponents`): per-component weighted, raw, rank across K, gap to next-ranked.
- **Tier 2 — per-doctor equity** (`PerDoctorAggregates`): CALL / STANDBY / weekend-CALL / public-holiday-CALL counts; call-point initial / end-of-cycle / delta; cumulative weighted load; max consecutive days-off.
- **Tier 3 — equity scalars** (`EquityScalars`): per-candidate stdev / min-max gap / Gini for call counts, weekend calls, public-holiday calls, and call-point end-of-cycle.
- **Tier 4 — day-level** (`hotDays`, `lockedDays` + per-candidate `assignment`): per-day disagreement count and the underlying assignment matrix.
- **Tier 5 — cross-candidate similarity** (`pairwiseHammingDistance`): pairwise cell-difference matrix.
- **Tier 6 — constraint satisfaction** (`ViolationSummary`): hard / soft violation counts and per-rule rollups.
- **Tier 7 — decision-support tags** (NOT emitted; renderer-derived per §10.9).

Snapshot-extension fields (senior-junior pairing, leave-history-aware analysis, rotation-conflict surfacing) are out of M5 scope per `docs/decision_log.md` D-0058 and `docs/future_work.md` FW-0031. They would require snapshot extensions to carry the underlying doctor metadata; until those land, the analyzer cannot compute them from its declared inputs.

## 14) Schema versioning
Proposed in this checkpoint (normative):

`AnalyzerOutput.contractVersion` is the analyzer's schema version, mirroring `docs/selector_contract.md` §19's discipline.

Bump rule:
- bump `contractVersion` only when the `AnalyzerOutput` field set, top-K selection semantics, or per-field semantics change in a way that breaks a v1-targeted reader.
- additive changes that a v1-targeted reader can tolerate (for example, an additional optional top-level field on `AnalyzerOutput`, an additional optional `ComponentBreakdown` field, an additional Tier 7-style field that a v1 renderer can ignore) do NOT require a bump.
- removing or renaming a field, changing a field's semantic meaning, or tightening v1's "MAY tolerate" optionality into "MUST require" does require a bump.

## 15) Determinism
Proposed in this checkpoint (normative):

- Given identical `(envelope, fullSidecar, topK, analysisConfig)` inputs, the analyzer MUST produce a byte-identical `AnalyzerOutput` JSON within a single implementation on a single platform.
- Determinism is required within a single implementation on a single platform. Cross-implementation or cross-platform determinism is not required and is not guaranteed; serialization library choices, hash-map iteration order, and floating-point string formatting differ across runtimes (`docs/future_work.md` FW-0011).
- The analyzer MUST NOT consume clocks, environment variables, or filesystem state beyond reading the supplied input files. `AnalyzerOutput.generatedAt` is execution-layer-supplied (the caller — typically the `python/rostermonster/run.py` analyzer subcommand or a future `--analyze` flag — passes the timestamp in), the same way `runEnvelope.generationTimestamp` is supplied at selector entry per `docs/selector_contract.md` §16.2. The analyzer itself does not call `datetime.now()`.
- The analyzer MUST NOT perform side effects beyond returning the `AnalyzerOutput` JSON. File I/O is execution-layer-owned (§16).

## 16) Filesystem placement is execution-layer-owned
This contract does **not** govern:
- the directory or path the `AnalyzerOutput` JSON is written to,
- the file-naming convention (for example, timestamp embedding, run-prefix structure),
- the standard input / standard output policy (whether the analyzer writes to a file path argument, prints to stdout, or both).

Concrete file-emission decisions live in the M5 C1 implementation slice: the planned `python/rostermonster/run.py` analyzer subcommand (or `--analyze` flag) is the execution-layer surface. The contract requires only that the `AnalyzerOutput` content, when persisted, conforms to §10.

## 17) Consistency with adjacent contracts
- **Upstream selector** (`docs/selector_contract.md`): the analyzer reads the FULL-retention output declared in §13.2 + §14. v1 of this contract is compatible with selector `contractVersion: 2` and any future selector version that preserves the FULL-retention output shape (§14.1 + §14.2 fields) and the `runEnvelope` ride-through requirement (§16).
- **Upstream writeback** (`docs/writeback_contract.md`): the analyzer reads the wrapper envelope's `snapshotSubset` whose six categories are declared in §9. v1 of this contract is compatible with writeback `contractVersion: 1` (with the §9 6-category shape).
- **Upstream scorer** (`docs/scorer_contract.md`): the analyzer reads `ScoreResult.components` whose first-release component identifiers are enumerated in §10 / `docs/domain_model.md` §11.2. v1 of this contract is compatible with scorer `contractVersion: 3`. Future scorer changes that alter the component-identifier set or break the `weighted / raw` correspondence MAY trigger an analyzer bump per §14.
- **Upstream cloud_compute** (`docs/cloud_compute_contract.md`): unaffected; cloud-side FULL retention is `docs/future_work.md` FW-0030 and not in M5 scope.
- **Downstream renderer** (M5 C2, future contract or library docstring): consumes `AnalyzerOutput` per §10. The renderer's tab layout, formatting, and comparison-tab UX are NOT governed by this contract.
- **Downstream upload portal** (M5 C3): consumes a single `AnalyzerOutput` JSON file per §10. The portal's form shape and operator UX are NOT governed by this contract.

## 18) Explicit deferrals
- **Diversity-aware top-K selection** (DPPs, submodular maximization, Hamming-distance thresholds, cluster grouping, max-min diversification): out of M5 scope per `docs/decision_log.md` D-0056. If C4 operator validation reveals top-K-by-score is consistently un-actionable (operator says "these K candidates are all the same"), that is signal to enrich solver-strategy exploration (M6 LAHC etc.), not to add diversity at the analyzer stage.
- **Cloud-side FULL retention support**: deferred to `docs/future_work.md` FW-0030. M5 ships analysis tooling on top of today's CLI FULL retention output only.
- **Snapshot-extension analyzer fields** (senior-junior pairing, leave-history-aware analysis, rotation-conflict surfacing): deferred to `docs/future_work.md` FW-0031.
- **Strategy-aware diagnostics** (LAHC iteration counts, simulated-annealing curves, etc.): out of analyzer scope by §12. Belongs in a separate strategy-aware diagnostic surface if future work surfaces a need.
- **Decision-support tags** (Tier 7): renderer-derived per §10.9, not analyzer-emitted.
- **Analyzer-side scoring-formulation rework** (lexicographic / threshold / Pareto ordering): explicitly NOT in M5 scope per `docs/decision_log.md` D-0055 sub-decision 9. If C4 surfaces that `totalScore`'s winner is consistently NOT the operator-preferred candidate, that opens an M5.5 or pre-M6 design thread on scoring formulation; the analyzer remains a passive consumer of whatever scoring discipline ships.
- **Streaming-style analyzer ingest** (process candidates as they are scored rather than loading the full FULL sidecar): not first-release. First-release retention volumes are within memory bounds at ICU/HD scale (low hundreds of candidates).
- **Operator-tuneable analyzer config surface**: `analysisConfig` is reserved (§9) but ships with no required fields. Future tuneable knobs (e.g., custom weight overrides for re-scoring at analysis time) would require additive `analysisConfig` fields under the §14 bump rule.

## 19) Current checkpoint status
- This document is M5 C1's first deliverable — the analysis contract draft per `docs/decision_log.md` D-0055 sub-decision 11. It pins the analyzer-engine input/output, top-K rule, solver-agnostic property, and comparison emission scope sufficiently for M5 C1 Phase 2 implementation work to land against a stable contract surface.
- The analyzer-engine implementation (`python/rostermonster/analysis/`) is M5 C1 Phase 2; the Apps Script analyzer renderer is M5 C2; the upload portal is M5 C3; live operator validation is M5 C4.
- D-0056 (pure score-rank top-K), D-0057 (input + output shape), and D-0058 (Tiers 1–6 emission scope) are this contract's load-bearing direction-setting decisions and are recorded in `docs/decision_log.md`.
