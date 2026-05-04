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
- **v1 (2026-05-04, this PR):** initial analysis contract closure per `docs/decision_log.md` D-0056..D-0058. Input shape, `AnalyzerOutput` shape, pure top-K selection with selector-cascade tiebreak, Tiers 1–5 emission scope (Tier 6 deferred to FW-0032; Tier 7 renderer-derived).

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
- Upstream: the analyzer consumes (a) the full Snapshot JSON the CLI was given as `--snapshot` per `docs/snapshot_contract.md`, (b) the wrapper envelope `final_envelope.json` per `docs/decision_log.md` D-0044/D-0045, and (c) the FULL-retention sidecar `candidates_full.json` per `docs/selector_contract.md` §14.2. (b) and (c) are produced by the local CLI's `--retention FULL` + `--sidecar-dir` path (`python/rostermonster/run.py`); (a) is the same file the operator already has from the Apps Script extractor's browser-download flow per `docs/decision_log.md` D-0040.
- Boundary: the analyzer is a pure function `analyze(snapshot, envelope, fullSidecar, *, topK, generatedAt, analysisConfig=None) → AnalyzerOutput`.
- Downstream: the Apps Script analyzer renderer (M5 C2) consumes `AnalyzerOutput` and writes K roster tabs + 1 comparison tab. The upload portal (M5 C3) accepts a single `AnalyzerOutput` JSON file from the operator and hands it to the renderer.

The portal-side single-file-upload property per `docs/decision_log.md` D-0055 sub-decision 6 is preserved: the analyzer engine consumes three input files locally on the operator's machine, but the portal only ever sees the one `AnalyzerOutput` JSON the analyzer emits.

Proposed in this checkpoint:
- The analyzer is a pure function of its declared inputs (§9). No solver coupling, no rule-engine coupling. The analyzer reads the snapshot's public surface, the wrapper envelope's `runEnvelope` ride-through, and the FULL sidecar's public surface. The wrapper envelope's `snapshot` sub-object (the writeback-only narrow subset per `docs/writeback_contract.md` §9) is NOT analyzer input — the analyzer reads the full snapshot directly to access fields the writeback subset does not project (e.g., the full `dayRecords` shape for weekend classification, the full `doctorRecords` shape for `displayName` resolution).
- **Parser-overlay module reuse is allowed.** The analyzer MAY (and for `cumulativeCallPoints` MUST per §10.6) import the parser overlay function (`python/rostermonster/parser/scoring_overlay.py`) and apply it to the snapshot to obtain the post-overlay scoring config — the same `pointRules` weights the scorer consumes. This is module reuse, not contract coupling: the parser overlay is itself a pure function of `(snapshot, template)` per `docs/parser_normalizer_contract.md` §9, so the analyzer remains a pure function of its declared inputs while internally delegating per-day weight resolution to the parser. The template-resolution path is the same one the rest of the pipeline uses (first release: ICU/HD only).
- The analyzer is **scorer-output-consuming but not scorer-internal-coupled**: it reads `score.totalScore` + `score.components` from each candidate in the FULL sidecar (the scorer's authoritative emission per `docs/scorer_contract.md` §10), but does NOT call `score()` itself.
- The analyzer is solver-agnostic by contract (§12). It MUST NOT inspect strategy-specific metadata such as `solverStrategyId` or strategy-specific `searchDiagnostics` fields to switch behavior.
- The analyzer engine has no Apps Script coupling. The upload portal and renderer consume `AnalyzerOutput` by file; the analyzer engine never imports Apps Script libraries.

## 7) What this contract governs
This contract governs:
- the shape of analyzer input (the full Snapshot JSON + the wrapper envelope + the FULL sidecar JSON + caller-supplied `topK` + `generatedAt`, §9),
- the shape of analyzer output (the `AnalyzerOutput` JSON, §10),
- the top-K selection rule and its tiebreaker (§11),
- the solver-agnostic property (§12),
- the comparison aggregates the analyzer emits — Tiers 1–5 of the M5 C1 emission set (§13; Tier 6 deferred to FW-0032; Tier 7 renderer-derived per §10.9),
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
- doctor-metadata + day-metadata extensions to the snapshot (seniority, leave history, rotation conflicts, public-holiday classification) — out of M5 scope per `docs/future_work.md` FW-0031.

## 9) Input shape
Analyzer invocations are evaluated against the following inputs:

1. **`snapshot`** — the full Snapshot JSON the CLI was given as `--snapshot`, conforming to `docs/snapshot_contract.md`. Required top-level fields the analyzer consumes: `doctorRecords` (for `displayName` resolution and per-doctor iteration), `dayRecords` (for date iteration; the analyzer derives weekend classification from `rawDateText` itself per §10.6), `scoringConfigRecords.callPointRecords` (for per-day call-point weights when computing per-doctor `cumulativeCallPoints`, §10.6 + §13). Other top-level snapshot fields are not consumed by the analyzer in v1.
2. **`envelope`** — the wrapper envelope produced by the local CLI's `--writeback-ready` flow per `docs/decision_log.md` D-0045. Required top-level fields the analyzer consumes:
   - `finalResultEnvelope` — a `FinalResultEnvelope` per `docs/selector_contract.md` §10 with `retentionMode == "FULL"` (§9.1 below). The analyzer reads `runEnvelope` (for `runId`, `seed`, `sourceSpreadsheetId`, `sourceTabName` ride-through into `AnalyzerOutput.source`) and `result.winnerAssignment` (only as a sanity check; the BEST_ONLY winner is also identifiable as the highest-`totalScore` candidate in the FULL sidecar — see §11.1 for the `recommended` flag derivation that does NOT require parsing `winnerAssignment`).
   - The wrapper envelope's nested `snapshot` sub-object (the writeback-only narrow subset per `docs/writeback_contract.md` §9 — `columnADoctorNames` / `requestCells` / `callPointCells` / `prefilledFixedAssignmentCells` / `outputAssignmentRows` / `shellParameters`) is NOT analyzer input. The analyzer reads the full snapshot (§9 input #1) for the data writeback's narrow subset does not project.
   - The wrapper envelope's `doctorIdMap` (a list of `{doctorId, sectionGroup, rowIndex}` records per `docs/decision_log.md` D-0044 sub-decision 5 — NOT a `{doctorId: name}` dict) is also NOT analyzer input. The analyzer constructs its own `doctorId → displayName` dict from the snapshot's `doctorRecords[*].displayName` and emits it as `AnalyzerOutput.doctorIdMap` per §10.
3. **`fullSidecar`** — the `candidates_full.json` sidecar per `docs/selector_contract.md` §14.2. Concrete top-level shape (matching the producer at `python/rostermonster/selector/sidecars.py`): `{schemaVersion, runId, generationTimestamp, candidates: [...]}` where `candidates` is a JSON **array** of per-candidate objects, each carrying its own `candidateId`, `assignments` (full `AssignmentUnit[]`: `{dateKey, slotType, unitIndex, doctorId}` records), and `score` (the full `ScoreResult` — `totalScore` + `direction` + `components`). Phase 2 implementations MUST treat `candidates` as a list and index by scanning, NOT as a `{candidateId → candidate}` dict — the producer does not emit a dict. The analyzer MAY internally rebuild a `{candidateId → candidate}` index after admission for O(1) lookup; that is implementation-level, not contract-shape.
4. **`topK`** — the operator-supplied K (§11). Default 5; bounds `[1, 20]` inclusive; values outside this range are a fail-loud caller defect.
5. **`generatedAt`** — caller-supplied ISO-8601 timestamp string. Echoed into `AnalyzerOutput.generatedAt` per §10. Caller-supplied (rather than analyzer-synthesized) for the same reason `runEnvelope.generationTimestamp` is execution-layer-supplied per `docs/selector_contract.md` §16.2: the analyzer MUST NOT consume clocks (§15), so any timestamp embedded in the output must arrive on the input rather than be synthesized at emit time. Required because byte-identical determinism (§15) requires `generatedAt` to be part of the explicit input tuple.
6. **(optional) `analysisConfig`** — reserved for future analyzer-strategy configuration; first release ships no required fields. Future additions MUST follow the additivity rule in §14.

### 9.1 FULL retention required
The analyzer MUST be invoked against a FULL-retention envelope. Analyzer behavior under `BEST_ONLY` is undefined: the FULL sidecar is absent, the candidate population is one, and there is no top-K to compute. Callers that invoke the analyzer against a `BEST_ONLY` envelope MUST receive a fail-loud rejection — the analyzer MUST NOT silently degrade to "K=1, return the winner."

### 9.2 Failure-branch handling
On the `UnsatisfiedResult` failure branch (`docs/selector_contract.md` §15), there is no scored-candidate set to analyze. Analyzer behavior on this input is also fail-loud: the analyzer MUST raise a structured rejection rather than emit a degenerate `AnalyzerOutput`. The operator workflow is "render the failure branch via writeback's diagnostic surface (`docs/writeback_contract.md` §17) — the analyzer is not in scope on the failure branch."

### 9.3 No filesystem reads beyond declared inputs
The analyzer MUST NOT read any state outside the declared inputs. No environment variables, no clocks, no filesystem reads beyond the `snapshot`, `envelope`, and `fullSidecar` files supplied by the caller.

### 9.4 CSV sidecar is NOT analyzer input
The `candidates_summary.csv` sidecar is operator-debug-only (spreadsheet-grade inspection, per `docs/selector_contract.md` §14.1). The analyzer engine does NOT consume it; passing a `candidates_summary.csv` path to the analyzer is a no-op at best and a contract violation at worst. This is `docs/decision_log.md` D-0057.

### 9.5 Snapshot–envelope–sidecar coherence (fail-loud admission)
Because the operator manually assembles the three input files locally, accidental cross-run mixes are realistic (e.g., yesterday's `final_envelope.json` paired with today's snapshot, or a sidecar from a different run). Without admission checks, the analyzer would emit a syntactically valid `AnalyzerOutput` with incorrect day classification and doctor labeling — silent corruption of comparison results.

The analyzer MUST enforce the following two coherence checks at admission time and MUST fail-loud (raise a structured rejection) on any mismatch:

1. **Snapshot ↔ envelope** — `envelope.finalResultEnvelope.runEnvelope.snapshotRef` MUST equal `snapshot.metadata.snapshotId` (per `docs/snapshot_contract.md` §6 — `SnapshotMetadata.snapshotId` is the canonical snapshot identity, conventionally `snapshot_<spreadsheetId>_<extractionTimestamp>` per `docs/decision_log.md` D-0042; the run envelope's `snapshotRef` is execution-layer-supplied at parser/normalizer ingestion and pinned by `docs/selector_contract.md` §9 / §16.2).
2. **Envelope ↔ sidecar** — `fullSidecar.runId` (from `candidates_full.json` top-level fields per `docs/selector_contract.md` §14.2) MUST equal `envelope.finalResultEnvelope.runEnvelope.runId`.

Both checks mirror the fail-loud admission discipline used at parser/normalizer per `docs/decision_log.md` D-0038 (missing `pointRules` keys fail-loud rather than silently fall back). The structured rejection MUST surface enough detail for the operator to identify which file is mismatched (e.g., "snapshot.metadata.snapshotId = X; envelope.runEnvelope.snapshotRef = Y") so they can re-run with the correct triple.

The analyzer MAY perform additional sanity checks (e.g., that every `candidateId` referenced in the FULL sidecar's `candidates` map is internally consistent, or that the sidecar's `generationTimestamp` matches the envelope's) but the two checks above are the minimum admission rule v1 implementations MUST enforce.

## 10) Output shape
The analyzer returns a single `AnalyzerOutput` JSON object. Concrete shape:

```
AnalyzerOutput {
  contractVersion: 1
  generatedAt: ISO-8601 string                 // ride-through from §9 input #5; caller-supplied
  source: {
    runId: string                              // from envelope.finalResultEnvelope.runEnvelope.runId
    seed: number | null                        // from envelope.finalResultEnvelope.runEnvelope.seed
    sourceSpreadsheetId: string                // ride-through from runEnvelope
    sourceTabName: string                      // ride-through from runEnvelope
  }
  topK: TopKResult
  comparison: ComparisonAggregates
  doctorIdMap: { [doctorId: string]: string }  // analyzer-constructed dict {doctorId → displayName} per the §10 doctorId-to-displayName mapping rule below; NOT a passthrough of envelope.doctorIdMap (which is a list-of-records, not a dict, and does not carry displayName)
}
```

### 10.0 `doctorId` ↔ `displayName` mapping rule
The FULL sidecar's `assignments[*].doctorId` and the analyzer's emitted `AnalyzerOutput.doctorIdMap` keys MUST resolve via the **first-release identity rule**: `doctorId == snapshot.doctorRecords[*].sourceDoctorKey`. The first-release parser passes `sourceDoctorKey` through unchanged as `Doctor.doctorId` per `docs/parser_normalizer_contract.md` (the same rule the existing `_build_doctor_id_map` helper at `python/rostermonster/run.py` / `pipeline.py` documents in-source: "First-release parser passes `sourceDoctorKey` through unchanged as `Doctor.doctorId`, so doctorId = sourceDoctorKey here"). The analyzer therefore builds `AnalyzerOutput.doctorIdMap` as `{ rec.sourceDoctorKey: rec.displayName for rec in snapshot.doctorRecords }`.

Concrete admission checks (fail-loud):
- Every `doctorId` referenced by any candidate's `assignments[*].doctorId` in the FULL sidecar MUST appear as a key in the analyzer's constructed `doctorIdMap`. If a sidecar `doctorId` is missing from `snapshot.doctorRecords`, that is a contract violation by the producer (snapshot ↔ sidecar doctor-identity drift) and the analyzer MUST raise a structured rejection — same fail-loud discipline as §9.5.
- Duplicate `displayName` values across distinct `sourceDoctorKey`s are tolerated: the dict's key is `doctorId` (not `displayName`), so duplicates collapse only at the rendering layer (M5 C2 territory). Renderer is responsible for any disambiguation policy on duplicate names.

Future extensions: if a future parser bump introduces a non-identity `sourceDoctorKey → doctorId` mapping (e.g., normalized doctor identity for cross-roster operator handling), that bump WILL require an additive analyzer-contract bump per §14 to update this rule. The first-release identity is locked here so Phase 2 implementations don't drift.

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
  recommended: boolean                         // true iff rankByTotalScore == 1 (the BEST_ONLY winner the selector would have picked); see §11.1
  totalScore: number
  scoreComponents: {
    [componentName: string]: ComponentBreakdown
  }
  fillStats: { slotsFilled: int, slotsTotal: int }
  perDoctor: { [doctorId: string]: PerDoctorAggregates }
  assignment: AssignmentRefShape               // §10.5
}
```

`scoreComponents` MUST include every first-release component identifier enumerated in `docs/domain_model.md` §11.2 (the nine ICU/HD components: `unfilledPenalty`, `pointBalanceWithinSection`, `pointBalanceGlobal`, `spacingPenalty`, `preLeavePenalty`, `crReward`, `dualEligibleIcuBonus`, `standbyAdjacencyPenalty`, `standbyCountFairnessPenalty`), even when a component contributes zero. This mirrors `docs/scorer_contract.md` §10 — analyzer cannot drop components the scorer was required to emit.

**Rule-violation breakdown (`ViolationSummary`) is NOT a v1 field.** The analyzer's declared inputs (snapshot + envelope + FULL sidecar) do not carry per-candidate hard/soft rule-firing detail — `candidates_full.json` per `docs/selector_contract.md` §14.2 carries only `candidateId`, `assignments`, and `score` (no per-rule violation counts). Computing `softCount` / `softByRule` / `hardByRule` would require either (a) extending the FULL sidecar to carry rule-violation detail per candidate, or (b) integrating rule-engine evaluation into the analyzer (coupling analyzer to `docs/rule_engine_contract.md`). Both expand scope beyond M5 first-release. v1 of this contract therefore omits `ruleViolations` from `AnalyzerCandidate` entirely; per-candidate rule-violation surface is parked as `docs/future_work.md` FW-0032 and lands via additive bump per §14 once one of the two upstream paths is chosen. (`hardCount` is 0 by construction for any candidate in `candidates_full.json` since the upstream pipeline filters hard violations before emission, so the omission has no v1 information loss on the hard-violation axis; the `softCount` axis is the genuine v1 gap.)

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

### 10.5 `AssignmentRefShape`
The renderer needs the per-day per-slot doctor assignment to write the K roster tabs. The analyzer rides this through from the FULL sidecar's `AssignmentUnit[]` shape (`{dateKey, slotType, unitIndex, doctorId}` per `python/rostermonster/selector/sidecars.py` and `docs/domain_model.md`). v1 ships the assignment as a list of records:

```
AssignmentRefShape = [
  { dateKey: string, slotType: string, unitIndex: int, doctorId: string }
]
```

`unitIndex` is the multiplicity key from `docs/domain_model.md` — when a template declares `requiredCount > 1` for a slot type on a given day (e.g., two MICU CALL slots on a single date), `(dateKey, slotType)` alone is not unique; `unitIndex` disambiguates the slot occurrences. The analyzer MUST preserve `unitIndex` from the sidecar so the renderer can correctly resolve which slot occurrence each doctor fills, and so cross-candidate Hamming distance per §10.7 compares `(dateKey, slotType, unitIndex)` triples rather than `(dateKey, slotType)` pairs (collapsing on the latter would miss legitimate cross-candidate disagreements when `requiredCount > 1`).

`doctorId` is the canonical sidecar identifier; the renderer translates to operator-facing names via `AnalyzerOutput.doctorIdMap`. v1 readers MUST tolerate the list-of-records shape.

### 10.6 `PerDoctorAggregates`
```
PerDoctorAggregates {
  callCount: int                          // count of CALL-slot assignments
  standbyCount: int                       // count of STANDBY-slot assignments
  weekendCallCount: int                   // count of CALL-slot assignments on weekend dates (analyzer-derived from snapshot.dayRecords[*].rawDateText)
  cumulativeCallPoints: number            // sum over the doctor's CALL assignments of the per-day call-point weight at (slotType, dayIndex), where the weight is derived from snapshot.scoringConfigRecords.callPointRecords after the parser overlay (D-0037)
  maxConsecutiveDaysOff: int              // longest run of consecutive snapshot.dayRecords with no assignment to this doctor
}
```

**Weekend-day source.** `snapshot.dayRecords[*]` carries `rawDateText` but NO precomputed `isWeekend` flag in the v1 snapshot shape (`docs/snapshot_contract.md`). The analyzer derives weekend classification by parsing `rawDateText` through Python's `datetime` library (Saturday + Sunday). Cross-region calendar variation is out of M5 first-release scope (ICU/HD pilots are Singapore-based and use the standard Saturday + Sunday weekend definition).

**Public-holiday metrics deferred (no v1 field).** `snapshot.dayRecords[*]` does NOT carry an `isPublicHoliday` flag in v1, and no public-holiday calendar is wired into the analyzer. Rather than emit a hardcoded zero (which would make "no PHs in period" indistinguishable from "PH classification unavailable" and silently corrupt operator-facing equity comparisons whenever the period actually contains a PH), v1 of this contract OMITS the field entirely from `PerDoctorAggregates` and `EquityScalars`. PH support is parked as `docs/future_work.md` FW-0031 (snapshot-extension analyzer fields). When a future snapshot extension surfaces real PH metadata, an additive analyzer-contract bump per §14 adds `publicHolidayCallCount` back to both shapes — v1-targeted readers will still parse the augmented output by ignoring the new field per §14's tolerance rule.

**Call-point source — uses parser overlay, NOT raw snapshot cells.** `cumulativeCallPoints` measures the load this candidate places on this doctor under the **post-overlay** per-day call-point weights — the same weights the scorer's `pointBalance*` components consume. Raw `snapshot.scoringConfigRecords.callPointRecords` cells are operator-editable and can be blank; scorer-equivalent weights require the parser overlay path per `docs/parser_normalizer_contract.md` §9 + `docs/decision_log.md` D-0037 (sheet-wins overlay on top of template defaults; D-0038's fail-loud `pointRules` cross-product cover applies). The analyzer MUST therefore compute `cumulativeCallPoints` against the post-overlay scoring config — concretely, by reusing the same parser overlay function the rest of the pipeline uses (`python/rostermonster/parser/scoring_overlay.py`) over the snapshot input — rather than over raw cell text. Computing against raw cells would silently disagree with the scorer whenever defaults or blank cells are involved, corrupting Tier 2/3 equity comparisons. The parser overlay's template dependency is satisfied by the same template-resolution path used elsewhere in the pipeline (first release: ICU/HD only); the analyzer is NOT required to take the template as a fourth `analyze()` argument. Carryover-from-prior-period or doctor-specific opening balances are NOT a v1 snapshot concept — `cumulativeCallPoints` is a within-cycle metric only. A future snapshot extension may introduce per-doctor opening balances; that would be an additive analyzer-contract bump under §14's rule.

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

`pairwiseHammingDistance[a][b]` is the count of `(dateKey, slotType, unitIndex)` cells (the full assignment-cell key per §10.5) where candidate `a` and candidate `b` assign different doctors. The matrix is symmetric; implementations MAY emit only the upper triangle (`b > a` lexicographically) and v1 readers MUST tolerate either symmetric or upper-triangle layout, looking up `[a][b]` by trying both keys.

`hotDays[*].distinctAssignments` is the count of distinct doctor-tuples assigned across the K candidates on that date. A locked day has `distinctAssignments == 1`. Hot days are the complement: `distinctAssignments > 1`. The list MUST include only `dateKey`s within the run's period.

`lockedDays` is the convenience inverse of `hotDays` for the renderer's default-collapsed tab UX. Renderer derives "% of days locked" from `lockedDays.length / period.length`.

### 10.8 `EquityScalars`
```
EquityScalars {
  callCount: { stdev: number, minMaxGap: int, gini: number }
  weekendCallCount: { stdev: number, minMaxGap: int, gini: number }
  cumulativeCallPoints: { stdev: number, minMaxGap: number, gini: number }
}
```

`publicHolidayCallCount` equity scalars are NOT emitted in v1 (paired with the §10.6 `PerDoctorAggregates` PH-deferral note). When a future snapshot extension surfaces real PH metadata, the additive bump adds the matching `publicHolidayCallCount: { stdev, minMaxGap, gini }` block here in lockstep with the §10.6 field.

Equity scalars are computed across the doctor population for a single candidate. Lower stdev / lower min-max gap / lower Gini == more equitable. Renderer surfaces these as comparison-tab summary scalars; the operator-facing semantic is "candidate A is more equitable on weekend calls than candidate B even though A's totalScore is lower."

### 10.9 Renderer-derivable Tier 7 fields are NOT emitted
Per `docs/decision_log.md` D-0058, the analyzer does NOT emit decision-support tags ("best on `pointBalance`", "lowest `spacingPenalty`", etc.). The renderer derives these from the raw fields above (`scoreComponents[*].rankAcrossTopK == 1` is the "best on dimension X" signal). This keeps the analyzer surface tight and lets the renderer iterate the tag UX without a contract bump.

## 11) Top-K selection — pure score-rank with selector-cascade tiebreak, no diversity heuristic
Proposed in this checkpoint (normative):

The analyzer selects the K returned candidates as follows:
1. Sort the FULL sidecar's candidates by `ScoreResult.totalScore` descending.
2. **Tiebreak ties on equal `totalScore` by mirroring `HIGHEST_SCORE_WITH_CASCADE`'s two-level cascade with `candidateId` fallback per `docs/selector_contract.md` §12.2 exactly:**
   - 2a. Prefer the candidate with the **higher `pointBalanceGlobal`** (less-negative penalty contribution; from `score.components.pointBalanceGlobal` in the FULL sidecar's per-candidate `ScoreResult`).
   - 2b. Then prefer the candidate with the **higher `crReward`** (more-positive reward contribution; from `score.components.crReward`).
   - 2c. Final fallback: prefer the candidate with the **numerically lowest `candidateId`** (`candidateId` is a run-monotonic dense integer per `docs/selector_contract.md` §16.1; numeric ordering, NOT lexicographic ASCII — `"10"` preceding `"2"` lexicographically would invert the intended order).
   The cascade depth is exactly two named components (`pointBalanceGlobal`, then `crReward`); deeper components from `docs/domain_model.md` §11.2 are not consulted, mirroring the selector's strategy-level §12.3 component-name dependency. Cascade alignment is the load-bearing reason §11.1's equivalence claim holds: any divergence between analyzer and selector cascade behavior would let the analyzer's rank-1 disagree with the selector's BEST_ONLY winner on equal-`totalScore` runs.
3. Take the first `min(requested, candidatesAvailable)` entries.
4. If `candidatesAvailable < requested`, set `topK.returned = candidatesAvailable` (the analyzer returns fewer than `requested` rather than padding or failing). v1 readers MUST tolerate `returned < requested`.
5. If `requested > 20`, the analyzer MUST raise a structured rejection ("K must be ≤ 20"). This is fail-loud per `docs/decision_log.md` D-0056.
6. If `requested < 1`, the analyzer MUST also raise a structured rejection.

**Cascade-component dependency.** The cascade names two specific component identifiers (`pointBalanceGlobal`, `crReward`) from `docs/domain_model.md` §11.2. Renaming or removing either component upstream would be a breaking change for both selector strategy `HIGHEST_SCORE_WITH_CASCADE` (per `docs/selector_contract.md` §12.3) AND this analyzer rule. Future strategies that change the cascade components (e.g., LAHC-style strategy registering with a different cascade per `docs/selector_contract.md` §11) would force a paired analyzer-contract bump unless the new strategy retains the same component-cascade for its BEST_ONLY pick — which is what §11.1's equivalence claim actually requires of any alternate strategy that wants to remain analyzer-compatible without an analyzer bump.

**No diversity heuristic.** Per `docs/decision_log.md` D-0056, the analyzer does NOT compute Hamming-distance thresholds, cluster grouping, or any other diversity-aware selection rule. If the K candidates are near-duplicates of each other, that is signal — the operator is meant to see "the solver thinks these are all equivalent" rather than have the analyzer fabricate spread the solver did not produce. Tier 5's `pairwiseHammingDistance` matrix (§10.7) is the operator's diagnostic for "are my K candidates actually different?"

This cleanly separates concerns: the solver is the exploration mechanism; the analyzer is the passive observer. Diversity-aware selection (DPPs, submodular maximization, max-min diversification) belongs in solver-strategy work (M6 territory), not at the analyzer stage.

### 11.1 `recommended` flag derivation
The `AnalyzerCandidate.recommended` boolean is `true` iff `rankByTotalScore == 1` — the rank-1 candidate after applying §11's full ordering (totalScore desc, then `pointBalanceGlobal` desc, then `crReward` desc, then numeric `candidateId` asc). This is equivalent to "the BEST_ONLY winner the selector would have picked" because the analyzer's full ordering exactly mirrors `HIGHEST_SCORE_WITH_CASCADE`'s tie-break cascade per `docs/selector_contract.md` §12.2 — both apply the same primary key (`totalScore` desc) AND the same two-level cascade (`pointBalanceGlobal` desc, `crReward` desc) AND the same final fallback (lowest numeric `candidateId`), so they converge on the same first-place candidate when applied to the same FULL sidecar.

The `FinalResultEnvelope.result.winnerAssignment` per `docs/selector_contract.md` §10.1 carries the winner's assignment-tuple shape but does NOT expose a separate `winnerCandidateId` field; the analyzer therefore derives the recommendation from rank rather than from a direct identifier match. Implementations MAY cross-check `winnerAssignment` content against the rank-1 candidate's `AssignmentUnit[]` for self-consistency and raise a structured rejection on mismatch (which would indicate selector ↔ FULL-sidecar drift — a defect upstream).

## 12) Solver-agnostic property
Proposed in this checkpoint (normative):

The analyzer MUST NOT inspect `solverStrategyId` or any strategy-specific metadata in `searchDiagnostics`, `runEnvelope`, or elsewhere on the envelope to switch behavior. Concretely:
- For any pair of analyzer invocations sharing identical `topK`, `generatedAt`, and `analysisConfig` (the caller-supplied tuple per §9 inputs #4–#6), where also `snapshot`, `finalResultEnvelope.winnerAssignment`, `finalResultEnvelope.runEnvelope`, and `fullSidecar.candidates` (content fields per §9 inputs #1–#3) are identical, the analyzer MUST produce the same `AnalyzerOutput` — regardless of which solver strategy produced the envelope/sidecar. (This preserves §15's byte-identical determinism tuple: behavior is a function of the full §9 input tuple, not just the content subset; the solver-agnostic property says no OTHER input — like `solverStrategyId` — is allowed to change behavior.)
- The analyzer MAY echo `runEnvelope` fields (e.g., `runId`, `seed`) into `AnalyzerOutput.source` for traceability, but MUST NOT branch on them.
- Future solver strategies (LAHC etc., parked for M6) that produce a contract-compliant `FinalResultEnvelope` + FULL sidecar are analyzable without analyzer code changes.

Strategy-aware diagnostics (e.g., LAHC iteration counts, simulated-annealing temperature curves) are explicitly out of analyzer scope. They belong in a separate strategy-aware diagnostic surface that future work may introduce.

## 13) Comparison emission scope — Tiers 1–5 in v1; Tier 6 deferred; Tier 7 renderer-derived
Proposed in this checkpoint (normative):

The analyzer's comparison emission set is partitioned into seven conceptual tiers (the M5 C1 design-thread organization). v1 emits Tiers 1–5; Tier 6 is parked as `docs/future_work.md` FW-0032 (data not reachable from declared inputs without scope expansion); Tier 7 is renderer-derived per §10.9.

- **Tier 1 — score decomposition** (`AnalyzerCandidate.totalScore` + `scoreComponents`): per-component weighted, raw, rank across K, gap to next-ranked.
- **Tier 2 — per-doctor equity** (`PerDoctorAggregates`): CALL / STANDBY / weekend-CALL counts; `cumulativeCallPoints` (within-cycle load per doctor under operator-overlaid call-point weights); `maxConsecutiveDaysOff`. (No per-doctor opening-balance / end-of-cycle / delta breakdown in v1; v1 snapshot has no per-doctor opening call-point balance — see §10.6 call-point source note. **No public-holiday metrics in v1** — §10.6 PH-deferral note; PH support parked as `docs/future_work.md` FW-0031.)
- **Tier 3 — equity scalars** (`EquityScalars`): per-candidate stdev / min-max gap / Gini for `callCount`, `weekendCallCount`, and `cumulativeCallPoints`. (`publicHolidayCallCount` equity scalars deferred in lockstep with the Tier 2 PH-field deferral.)
- **Tier 4 — day-level** (`hotDays`, `lockedDays` + per-candidate `assignment`): per-day disagreement count and the underlying assignment matrix.
- **Tier 5 — cross-candidate similarity** (`pairwiseHammingDistance`): pairwise cell-difference matrix.
- **Tier 6 — constraint satisfaction** (per-candidate hard/soft rule-violation breakdown): **NOT emitted in v1.** Per-candidate rule-violation detail is not reachable from the analyzer's declared inputs (`candidates_full.json` carries `candidateId`/`assignments`/`score` only — no rule-firing breakdown), and integrating rule-engine evaluation into the analyzer would expand scope beyond M5 first-release. Parked as `docs/future_work.md` FW-0032; lands via additive analyzer-contract bump per §14 once the upstream surface is chosen (selector-side sidecar extension carrying violation detail, OR analyzer-side rule-engine integration). The `hardCount` axis has no v1 information loss because successful candidates in `candidates_full.json` have already passed hard rules upstream by construction; the `softCount` axis is the genuine v1 gap.
- **Tier 7 — decision-support tags** (NOT emitted; renderer-derived per §10.9).

Snapshot-extension fields (senior-junior pairing, leave-history-aware analysis, rotation-conflict surfacing, public-holiday classification) are out of M5 scope per `docs/decision_log.md` D-0058 and `docs/future_work.md` FW-0031. They would require snapshot extensions to carry the underlying doctor-metadata or day-metadata; until those land, the analyzer cannot compute them from its declared inputs.

## 14) Schema versioning
Proposed in this checkpoint (normative):

`AnalyzerOutput.contractVersion` is the analyzer's schema version, mirroring `docs/selector_contract.md` §19's discipline.

Bump rule:
- bump `contractVersion` only when the `AnalyzerOutput` field set, top-K selection semantics, or per-field semantics change in a way that breaks a v1-targeted reader.
- additive changes that a v1-targeted reader can tolerate (for example, an additional optional top-level field on `AnalyzerOutput`, an additional optional `ComponentBreakdown` field, an additional Tier 7-style field that a v1 renderer can ignore) do NOT require a bump.
- removing or renaming a field, changing a field's semantic meaning, or tightening v1's "MAY tolerate" optionality into "MUST require" does require a bump.

## 15) Determinism
Proposed in this checkpoint (normative):

- Given identical `(snapshot, envelope, fullSidecar, topK, generatedAt, analysisConfig)` inputs (the full §9 input tuple), the analyzer MUST produce a byte-identical `AnalyzerOutput` JSON within a single implementation on a single platform. `generatedAt` is part of the input tuple (§9 input #5) precisely so the byte-identical guarantee holds — different `generatedAt` values produce different output bytes by construction, but identical inputs (including `generatedAt`) always produce identical bytes.
- Determinism is required within a single implementation on a single platform. Cross-implementation or cross-platform determinism is not required and is not guaranteed; serialization library choices, hash-map iteration order, and floating-point string formatting differ across runtimes (`docs/future_work.md` FW-0011).
- The analyzer MUST NOT consume clocks, environment variables, or filesystem state beyond reading the supplied input files. `AnalyzerOutput.generatedAt` is caller-supplied (typically the `python/rostermonster/run.py` analyzer subcommand or a future `--analyze` flag passes the timestamp in), the same way `runEnvelope.generationTimestamp` is supplied at selector entry per `docs/selector_contract.md` §16.2. The analyzer itself does not call `datetime.now()`.
- The analyzer MUST NOT perform side effects beyond returning the `AnalyzerOutput` JSON. File I/O is execution-layer-owned (§16).

## 16) Filesystem placement is execution-layer-owned
This contract does **not** govern:
- the directory or path the `AnalyzerOutput` JSON is written to,
- the file-naming convention (for example, timestamp embedding, run-prefix structure),
- the standard input / standard output policy (whether the analyzer writes to a file path argument, prints to stdout, or both).

Concrete file-emission decisions live in the M5 C1 implementation slice: the planned `python/rostermonster/run.py` analyzer subcommand (or `--analyze` flag) is the execution-layer surface. The contract requires only that the `AnalyzerOutput` content, when persisted, conforms to §10.

## 17) Consistency with adjacent contracts
- **Upstream snapshot** (`docs/snapshot_contract.md`): the analyzer reads the full Snapshot JSON the CLI was given as `--snapshot`. v1 of this contract is compatible with the v1 snapshot shape (`doctorRecords`, `dayRecords`, `scoringConfigRecords` as enumerated in §9 input #1). Future snapshot extensions (e.g., FW-0031's doctor-metadata fields; a future `dayRecords[*].isPublicHoliday` flag) are additive and do NOT require an analyzer bump unless the analyzer's emission set changes per §14.
- **Upstream selector** (`docs/selector_contract.md`): the analyzer reads the FULL-retention output declared in §13.2 + §14. v1 of this contract is compatible with selector `contractVersion: 2` and any future selector version that preserves the FULL-retention output shape (§14.1 + §14.2 fields) and the `runEnvelope` ride-through requirement (§16).
- **Upstream writeback** (`docs/writeback_contract.md`): the analyzer does NOT consume the wrapper envelope's writeback-specific fields (the nested `snapshot` narrow subset per §9, or `doctorIdMap` as a list-of-records). It reads only `finalResultEnvelope` from the wrapper envelope. v1 of this contract is therefore decoupled from the writeback contract's snapshot-subset shape — future writeback bumps that alter the §9 6-category subset do NOT trigger analyzer bumps.
- **Upstream parser/normalizer** (`docs/parser_normalizer_contract.md`): the analyzer **reuses the parser overlay function** (`python/rostermonster/parser/scoring_overlay.py`, per `docs/parser_normalizer_contract.md` §9 + `docs/decision_log.md` D-0037) to compute the post-overlay scoring config from `snapshot.scoringConfigRecords` + the template; this is module reuse, not contract coupling. The post-overlay `pointRules` weights are the per-day call-point weights `cumulativeCallPoints` (§10.6) consumes. v1 of this contract is compatible with the D-0037 + D-0038 fail-loud-on-missing-keys discipline.
- **Upstream scorer** (`docs/scorer_contract.md`): the analyzer reads `ScoreResult.components` whose first-release component identifiers are enumerated in §10 / `docs/domain_model.md` §11.2. v1 of this contract is compatible with scorer `contractVersion: 3`. Future scorer changes that alter the component-identifier set or break the `weighted / raw` correspondence MAY trigger an analyzer bump per §14.
- **Upstream cloud_compute** (`docs/cloud_compute_contract.md`): unaffected; cloud-side FULL retention is `docs/future_work.md` FW-0030 and not in M5 scope.
- **Downstream renderer** (M5 C2, future contract or library docstring): consumes `AnalyzerOutput` per §10. The renderer's tab layout, formatting, and comparison-tab UX are NOT governed by this contract.
- **Downstream upload portal** (M5 C3): consumes a single `AnalyzerOutput` JSON file per §10. The portal's form shape and operator UX are NOT governed by this contract.

## 18) Explicit deferrals
- **Diversity-aware top-K selection** (DPPs, submodular maximization, Hamming-distance thresholds, cluster grouping, max-min diversification): out of M5 scope per `docs/decision_log.md` D-0056. If C4 operator validation reveals top-K-by-score is consistently un-actionable (operator says "these K candidates are all the same"), that is signal to enrich solver-strategy exploration (M6 LAHC etc.), not to add diversity at the analyzer stage.
- **Cloud-side FULL retention support**: deferred to `docs/future_work.md` FW-0030. M5 ships analysis tooling on top of today's CLI FULL retention output only.
- **Snapshot-extension analyzer fields** (senior-junior pairing, leave-history-aware analysis, rotation-conflict surfacing, public-holiday classification + matching `publicHolidayCallCount` analyzer fields): deferred to `docs/future_work.md` FW-0031.
- **Per-candidate rule-violation breakdown** (Tier 6 — `softCount` / `softByRule` / `hardByRule` / `hardCount`): deferred to `docs/future_work.md` FW-0032. v1 inputs do not carry per-candidate rule-firing detail; emitting these would require either a selector-side sidecar extension carrying violation breakdown OR analyzer-side rule-engine integration. Both expand scope beyond M5 first-release.
- **Strategy-aware diagnostics** (LAHC iteration counts, simulated-annealing curves, etc.): out of analyzer scope by §12. Belongs in a separate strategy-aware diagnostic surface if future work surfaces a need.
- **Decision-support tags** (Tier 7): renderer-derived per §10.9, not analyzer-emitted.
- **Analyzer-side scoring-formulation rework** (lexicographic / threshold / Pareto ordering): explicitly NOT in M5 scope per `docs/decision_log.md` D-0055 sub-decision 9. If C4 surfaces that `totalScore`'s winner is consistently NOT the operator-preferred candidate, that opens an M5.5 or pre-M6 design thread on scoring formulation; the analyzer remains a passive consumer of whatever scoring discipline ships.
- **Streaming-style analyzer ingest** (process candidates as they are scored rather than loading the full FULL sidecar): not first-release. First-release retention volumes are within memory bounds at ICU/HD scale (low hundreds of candidates).
- **Operator-tuneable analyzer config surface**: `analysisConfig` is reserved (§9) but ships with no required fields. Future tuneable knobs (e.g., custom weight overrides for re-scoring at analysis time) would require additive `analysisConfig` fields under the §14 bump rule.

## 19) Current checkpoint status
- This document is M5 C1's first deliverable — the analysis contract draft per `docs/decision_log.md` D-0055 sub-decision 11. It pins the analyzer-engine input/output, top-K rule, solver-agnostic property, and comparison emission scope sufficiently for M5 C1 Phase 2 implementation work to land against a stable contract surface.
- The analyzer-engine implementation (`python/rostermonster/analysis/`) is M5 C1 Phase 2; the Apps Script analyzer renderer is M5 C2; the upload portal is M5 C3; live operator validation is M5 C4.
- D-0056 (pure score-rank top-K with selector-cascade tiebreak), D-0057 (input + output shape — full snapshot + envelope + FULL sidecar in, single `AnalyzerOutput` JSON out), and D-0058 (Tiers 1–5 v1 emission scope; Tier 6 → FW-0032; Tier 7 renderer-derived; snapshot-extension fields → FW-0031) are this contract's load-bearing direction-setting decisions and are recorded in `docs/decision_log.md`.
