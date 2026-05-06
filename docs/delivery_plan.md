# Delivery Plan

## 1. Purpose of this document
This is the **living execution guide** for Roster Monster v2.

It defines what is actively being delivered now (active milestone, active checkpoint, and supporting tasks) and what is intentionally next.

It does **not** replace:
- architecture truth in `docs/blueprint.md`
- milestone-level sequencing in `docs/roadmap.md`
- normative technical boundaries in contract docs
- issue-level implementation tracking

## 2. Planning vocabulary
- **Product**: the full end-to-end capability being built.
- **Milestone**: a major delivery state that advances product readiness.
- **Checkpoint**: a bounded, reviewable step inside a milestone.
- **Task**: a concrete work item used to close a checkpoint.

Working rule: this repo should normally maintain **one active milestone** and **one active checkpoint** at a time.

## 3. Product definition
Roster Monster v2 builds a reusable roster-allocation core with department-specific template control, while preserving Google Sheets as the operational front end. ICU/HD is the first concrete implementation target.

## 4. Product-level delivery principles
- Preserve Google Sheets as the operational front end.
- Keep architecture-first and contract-first boundaries where needed.
- Prioritize work that directly unblocks real operator workflow.
- Avoid reopening settled contracts unless there is a strong consistency reason.
- Avoid spending effort on items that do not support the active checkpoint.

## 5. Milestone map

### M1 — Operator-ready request sheet generation
- **Goal:** Deliver an operator-usable ICU/HD request sheet shell, backed by closed generation contract boundaries.
- **Status:** **Completed** *(closed 2026-04-21 on operator delivery; D-0019)*
- **Checkpoints:** C1 sheet-generation MVP boundary (closed 2026-04-17), C2 template artifact ↔ generation alignment (closed 2026-04-18), C3 acceptance/handoff readiness (closed 2026-04-18), C4 implement operator-ready sheet generation (closed 2026-04-21).

### M1.1 — Operator-facing launcher *(addendum to M1)*
- **Goal:** Provide a narrow operator-facing launcher so named monthly-rotation pilot operators can invoke empty ICU/HD request-sheet generation without running Apps Script by hand.
- **Status:** **Completed** *(closed 2026-04-22 on hands-on validation; M1 itself stays Completed, not reopened)*
- **Checkpoints:** C1 implement operator launcher web app (closed 2026-04-22).
- **Addendum framing:** M1.1 is derivative of M1's operator-facing surface, not a compute-line milestone. Addendum numbering convention (`M<parent>.<n>`) recorded in D-0021.

### M2 — Minimal local compute pipeline
- **Goal:** Stand up deterministic local parse/normalize/solve flow against closed contracts.
- **Status:** **Completed** *(closed 2026-04-29 on M2 C9 closure; full sheet → snapshot → Python pipeline runs end-to-end on real ICU/HD May 2026 data)*
- **Checkpoints:** C1 rule/scorer/solver contract closure (closed 2026-04-25); C2 selector contract closure (closed 2026-04-26); C3 parser/normalizer implementation (closed 2026-04-27); C4 minimal rule/scorer/solver integration (closed 2026-04-27); C5 local run artifact basics (closed 2026-04-28); C6 parser overlay for scoring config (closed 2026-04-28); C7 Scorer Config tab — sheet-generator half (closed 2026-04-28); C8 spacingPenalty geometric-decay shape (closed 2026-04-28); C9 snapshot extraction Apps Script — D-0036 (closed 2026-04-29). All nine closed.

### M3 — Safe result/output and writeback
- **Goal:** Define and implement safe output surfaces and writeback behavior.
- **Status:** **Completed** *(closed 2026-04-30 on M3 C1 closure; M3 C2 dropped per D-0048 — round-trip already proven, live-operator demo no longer the right next investment per D-0049)*
- **Checkpoints:** C1 writeback library + launcher route + Python CLI extension (closed 2026-04-30).

### M4 — Cloud end-to-end pipeline + dual-track preservation
- **Goal:** Deliver a cloud-deployed end-to-end pipeline so operators can drive a one-click roster-generation flow without local Python tooling, while preserving the existing local CLI as a maintainer-side dev-velocity surface for solver-strategy experiments.
- **Why it matters:** Pre-pilot political/visibility goal — boss-clickable proof of concept. Dual-track preservation matters because solver-strategy work (the next priority) needs the fast local-CLI iteration loop.
- **Status:** **Completed** *(closed 2026-05-01 on M4 C1 closure as the only delivered checkpoint; solver-strategy optimization promotes to its own forthcoming milestone rather than M4 C2 — different in character)*
- **Checkpoints:** C1 cloud end-to-end pipeline (minimum demo) (closed 2026-05-01).

### M5 — Operator-side analysis & multi-roster delivery
- **Goal:** Give operators the tools to see what's actually in a roster and compare alternatives, without changing the solver. Three-piece architecture (Python analyzer engine + `AnalyzerOutput` + Apps Script analyzer renderer) as a sibling consumer of the wrapper envelope, additive to the existing pipeline.
- **Why it matters:** Without analysis tooling, "did a future score-aware strategy improve quality" is unmeasurable from the operator's seat — today's only operator-facing signal is `totalScore` and the writeback tab. Analysis tooling is also the operator-side workaround for the weighted-sum scoring formulation pain (operator picks among K candidates with full component breakdowns rather than trusting a single scalar). Sequencing analysis BEFORE solver-side score-aware search (LAHC etc., parked in M6) means the calibration framework exists when the search-strategy work needs to be evaluated.
- **Status:** **Active** *(activated 2026-05-04 alongside M5 C1 per D-0055)*
- **Checkpoints:** C1 Python analyzer engine + analysis contract draft (closed 2026-05-05; PR #110 contract draft + PR #111 implementation); C2 Apps Script analyzer renderer (closed 2026-05-06; PRs #114 contract draft + #115 implementation + #116 launcher nav header — C3 upload-portal scope was wholly absorbed into C2's launcher Web App route per D-0063, so C3 is dropped from the plan); C4 live operator validation (active).
- **Dependencies:** M4 closed (cloud end-to-end live; CLI FULL retention already supported per M2 C5 closure).
- **Exit criteria:** All planned checkpoints closed; analyzer-engine + renderer + upload-portal triad runs end-to-end on a real ICU/HD cycle; operator validation confirms the comparison-tab decision-support workflow.

## 6. Current active milestone
- **Active milestone:** **M5 — Operator-side analysis & multi-roster delivery**

M5 activated 2026-05-04 per D-0055 alongside M5 C1. M5 is purely additive — no contract changes to solver / scorer / selector / writeback / cloud_compute / wrapper envelope. New surface: `docs/analysis_contract.md` (drafted in M5 C1), Python `rostermonster.analysis` module, Apps Script analyzer renderer, upload portal. Forward-pointer: M6 (LAHC + cloud Deep Solve + email-notification architecture) is parked but not pre-committed.

## 7. Checkpoint plan for the active milestone

- **C1 — Python analyzer engine + analysis contract draft.** *Closed 2026-05-05.* `docs/analysis_contract.md` pinned (`contractVersion: 1`) and `python/rostermonster/analysis/` engine + 61 analyzer tests (52 unit + 9 integration) landed across PR #110 (contract draft) and PR #111 (implementation). See §11 closure entry.
- **C2 — Apps Script analyzer renderer.** *Closed 2026-05-06.* Contract `docs/analysis_renderer_contract.md` pinned (`contractVersion: 1`); `apps_script/central_library/src/AnalysisRenderer.gs` + launcher Web App route at `?action=analysis-render` + `AnalysisRendererForm.html` + cross-page nav header all landed across PR #114 (contract draft) + PR #115 (implementation) + PR #116 (nav). Operator-facing tinyurl now serves the renderer at deployment `@15`. See §11 closure entry.
- **C3 — Upload portal.** *Dropped.* Originally framed as a thin separate Apps Script form, but C2's launcher Web App route per D-0063 + the C2 nav header per PR #116 wholly covered the upload-portal scope (operator uploads `AnalyzerOutput` JSON via `?action=analysis-render`; route deserializes; renderer paints K + 1 tabs; nav lets operator move between Generate / Writeback / Render Analysis). Drawing a separate checkpoint boundary added no value — discipline matches the precedent of dropping M3 C2 (D-0048) when C1 already met exit criteria.
- **C4 — Live operator validation.** Run the analyzer + renderer triad on a real ICU/HD cycle. Confirm comparison-tab fields actually drive operator decisions vs. are noise. Decision point: if scoring-formulation issues surface (e.g., `totalScore` winner consistently NOT the operator-preferred candidate), open M5.5 / pre-M6 thread on lexicographic / threshold / Pareto direction. **Active.**

## 8. Current active checkpoint
- **Active checkpoint:** **M5 C4 — Live operator validation**

## 9. Task list for the current checkpoint

M5 C4 (live operator validation) requires a real ICU/HD cycle's worth of data plus operator availability — not a code task. Concretely:

- Operator runs the M5 analyzer pipeline end-to-end on a real upcoming ICU/HD month: extract snapshot → run Python CLI with `--retention FULL` → run `python -m rostermonster.analysis` → upload `AnalyzerOutput` to launcher's `?action=analysis-render` route → review K + 1 tabs in the source spreadsheet.
- Decision-support evaluation: does the operator find the comparison tab's score-decomposition + equity scalars + Hamming matrix actually drive the choice between candidates, or are they noise? Capture qualitative feedback.
- Tier 7 derivation review: does the renderer's "best on dimension X" highlighting (column-best/worst in §13.2 score-decomp matrix) match operator intuition?
- Scoring-formulation pivot point per `docs/decision_log.md` D-0055 sub-decision 9: if `totalScore` winner is consistently NOT the operator-preferred candidate, opens M5.5 / pre-M6 thread on lexicographic / threshold / Pareto direction. If it usually IS the preferred candidate, the analyzer's role as calibration framework holds and M6 (LAHC + cloud Deep Solve) becomes the natural next milestone.

C4 closure unblocks M5 milestone closure and the decision on M6 framing.

## 10. Explicitly deferred for now
- Solver implementation details.
- Scorer implementation details.
- Local run implementation mechanics.
- Worker/orchestrator mechanics.
- Benchmark hardening depth beyond milestone-level framing.
- Broad multi-department generalization beyond ICU/HD-first sequencing.
- Public or open-signup operator access for the launcher; first-release scope is named monthly-rotation pilot operators only, gated via GCP OAuth consent-screen Test Users.
- In-app operator allowlist / role model inside the launcher; access gating stays external to the app for pilot scope.
- Operator-editable template or structural mapping; template stays maintainer-owned.
- Persisted per-operator state beyond Google's OAuth session.
- Alternative launcher platforms (for example a static page over the Apps Script API Executable); the pilot sticks with Apps Script Web App per D-0022.

## 11. Recently completed checkpoints

> Closure entries are intentionally short — what closed, when, with which PRs and decisions, plus a one-line summary of what works now. Full audit detail (phase-by-phase narrative, Codex findings, implementation files, test counts, "Main affected surfaces" lists) lives in the merged PR descriptions and git history; one-time setup steps live in operator READMEs and project memory.

### M5 activation note
M5 (`Operator-side analysis & multi-roster delivery`) activated 2026-05-04 alongside M5 C1 per D-0055. The decision frames M5 as a purely additive milestone that builds an analyzer engine + Apps Script renderer + upload portal as **sibling consumers** of the wrapper envelope (per D-0045) — writeback contract stays untouched, no new selector retention mode, top-K + diversity is the analyzer's responsibility (not the selector's). Cloud-side FULL retention is explicitly deferred to FW-0030 (prerequisite for M6's eventual Deep Solve auto-included analyzer path). M5 ships analysis tooling on top of today's CLI FULL retention output (no upstream contract changes); the cloud-side route remains Quick-Solve-only / BEST_ONLY in M5. Forward-pointer: M6 picks up LAHC + cloud Deep Solve + email-notification architecture; sequencing rationale is "analysis-first as the calibration framework + multi-objective workaround" (without analysis tooling, future score-aware solver gains are unmeasurable from the operator's seat). No code changes in this activation PR — direction-setting docs only, mirroring the D-0049 pattern.

- **M5 C2 — Apps Script analyzer renderer** *(closed 2026-05-06; PRs #114 contract draft, #115 implementation, #116 launcher nav header, plus this closure PR)*
  - Operator-facing analyzer renderer live end-to-end: launcher Web App at `?action=analysis-render` accepts an `AnalyzerOutput` JSON file, hands it to `RMLib.renderAnalysis(...)` in the central library, which writes K roster tabs + 1 comparison tab into the source spreadsheet identified by `output.source.sourceSpreadsheetId`. Cross-page nav header on all three operator pages (Generate sheet / Apply writeback / Render analysis) so operators can navigate between functions without manual `?action=...` URL surgery.
  - Decisions: D-0060 (renderer module placement = central library, file `apps_script/central_library/src/AnalysisRenderer.gs`), D-0061 (separate `docs/analysis_renderer_contract.md` rather than extending `docs/analysis_contract.md`), D-0062 (target spreadsheet = source spreadsheet, accepting tab-bloat trade-off; always-new-tab collision policy mirrors writeback §11), D-0063 (invocation surface = route on the existing launcher Web App, mirroring D-0046's writeback upload pattern; direct-from-bound-shim deferred).
  - New contract `docs/analysis_renderer_contract.md` (`contractVersion: 1`); analyzer engine contract surface (PR #110) unchanged. Launcher cloud-side deployment bumped from `@14` → `@15` ("M5 C2: analysis-render route + cross-page nav") so the operator-facing tinyurl serves the new content; deployment ID + URL stable.
  - C3 dropped from M5 plan — the upload-portal scope was wholly absorbed into C2's launcher Web App route; same discipline as M3 C2 dropped per D-0048 when C1 already met exit criteria. Active checkpoint pointer moves M5 C2 → M5 C4. M5 milestone stays Active pending C4 live-operator validation.
  - 225/225 Python tests still pass — C2 was Apps Script-side only, no Python changes. Apps Script unit-test coverage remains a separate cleanup (existing Tests.gs writeback helpers reference private library functions post-D-0052 that aren't reachable at runtime; outside M5 C2 scope). M5 C4 operator validation will exercise the renderer end-to-end on real data.

- **M5 C1 — Python analyzer engine + analysis contract draft** *(closed 2026-05-05; PRs #110 contract draft, #111 implementation, plus this closure PR)*
  - Operator can now run `python -m rostermonster.analysis --snapshot S.json --envelope E.json --full-sidecar F.json --output A.json --top-k 5` against any FULL-retention CLI run output and get a single `AnalyzerOutput` JSON with Tier 1–5 comparison data over the top K candidates.
  - Decisions: D-0056 (analyzer top-K = pure score-rank with selector-cascade tiebreak — `pointBalanceGlobal` desc → `crReward` desc → numerically lowest `candidateId` per `docs/selector_contract.md` §12.2; no diversity heuristic at the analyzer stage — diversity belongs in solver-strategy work), D-0057 (analyzer I/O shape — full snapshot + wrapper envelope + `candidates_full.json` in, single `AnalyzerOutput` JSON out; CSV sidecar explicitly excluded), D-0058 (Tiers 1–5 v1 emission scope; Tier 6 deferred to FW-0032; Tier 7 renderer-derived; snapshot-extension fields parked as FW-0031).
  - New contract `docs/analysis_contract.md` (`contractVersion: 1`); cross-contract amendment to `docs/selector_contract.md` §14.2 wording (clarified `candidates` array shape — no `schemaVersion` bump, editorial only). New future-work entries FW-0031 (snapshot-extension analyzer fields incl. PH classification) + FW-0032 (per-candidate rule-violation surface for analyzer Tier 6).
  - PR #110 ran 17 Codex review rounds (16 patches before thumbs); PR #111 ran 7 rounds (6 patches before thumbs). Substantive findings landed across both PRs. 225/225 Python tests pass: 164 baseline + 52 analyzer unit + 9 analyzer integration.
  - Live demo deferred to M5 C4 per the M5 sequencing — engine is ready; renderer (M5 C2) + portal (M5 C3) make the operator-facing surface complete.

### M4 milestone closure note
M4 (`Cloud end-to-end pipeline + dual-track preservation`) closed on 2026-05-01 with M4 C1 closure as its only delivered checkpoint. M4 was reframed from `Parallel operational search and orchestration` per D-0049 to prioritize a boss-clickable proof of concept and preserve the local CLI for forthcoming solver-strategy work. The reframing parked the original M4 scope (parallel orchestration) and the original M5 scope (observability) as future-work entries FW-0027 + FW-0028. Solver-strategy optimization is materially different in character (changes core compute semantics rather than adding a delivery vehicle) and lands as its own forthcoming milestone slot rather than an M4 C2. M3 stays Completed; M2 stays Completed.

- **M4 C1 — Cloud end-to-end pipeline (minimum demo)** *(closed 2026-05-01; PRs #103 docs, #104 amendment, #105 code, #106 closure)*
  - Operator-facing one-click cloud-mode pipeline live: bound shim's `Roster Monster → Solve Roster` menu orchestrates extract → Cloud Run compute → in-memory writeback within one Apps Script invocation. Local CLI preserved unchanged per D-0050's dual-track discipline.
  - Decisions: D-0048 (close M3 early), D-0049 (reframe M4), D-0050 (dual-track Python — shared core + thin CLI + thin HTTP wrapper), D-0051 (Cloud Run + consolidated `RosterMonsterV2` GCP project), D-0052 (Apps Script library reorg — writeback moves into central library), D-0053 (random seed default), D-0054 (Cloud Run auth = public service + Flask-side `X-Auth-Token` + `ALLOWED_EMAILS` — amends D-0051 sub-2 after `aud`-mismatch live-test failure).
  - New contract `docs/cloud_compute_contract.md` (`contractVersion: 1`); cross-contract additive updates to `docs/snapshot_adapter_contract.md` §7/§11 + `docs/writeback_contract.md` §6.3.
  - Phase 2 also broadened bound-shim manifest scopes (`spreadsheets.currentonly` → `spreadsheets`) and applied Path 2-Lite visual polish to writeback tab (FW-0029 captures template-aware label propagation when a second template enters scope). 164/164 Python tests pass.
  - Live demo confirmed end-to-end on dev-copy 2026-05-01.

### M3 milestone closure note
M3 (`Safe result/output and writeback`) closed on 2026-04-30 with M3 C1 closure as its only delivered checkpoint. M3 C2 (`End-to-end demo on a real ICU/HD operator cycle`) was dropped per D-0048 — exit criteria (writeback round-trip with traceability + 3-state diagnostic + no silent partial-state) already met by C1 closure on the dev-copy round-trip. Architectural decisions D-0044..D-0047 plus the M3 C1 Phase 2 contract amendment that grew `docs/writeback_contract.md` §9 from 5 to 6 snapshot categories (closing D-0045 Follow-up #2). Active milestone moved to M4 same-day per D-0049.

- **M3 C1 — Writeback library implementation + launcher route + Python CLI extension** *(closed 2026-04-30; PRs #100 docs, #101 code, #102 closure)*
  - Production writeback path live end-to-end: Python CLI emits wrapper envelope (`FinalResultEnvelope` + snapshot subset + `doctorIdMap`); launcher Web App's `?action=writeback` route accepts upload via file-input form + `FileReader` + `google.script.run.applyWriteback`; Apps Script writeback library writes a new tab with prefilled cells at source-tab `(surfaceId, rowOffset)` coordinates, traceability footer + DeveloperMetadata + read-only protection; 3-state launcher diagnostic per writeback §17.
  - Decisions: D-0044 (transport = file upload via launcher form), D-0045 (envelope shape = single JSON wrapper), D-0046 (placement = launcher Web App route, not bound shim), D-0047 (Python CLI standard output IS the writeback envelope, controlled by `--writeback-ready` flag).
  - Phase 2 contract amendment: writeback §9 grew a 6th category `outputAssignmentRows` carrying the template's `slotType ↔ rowOffset` binding (closes D-0045 Follow-up #2). 143/143 Python pass; 17 Apps Script writeback unit tests.
  - Live demo confirmed on real ICU/HD May 2026 dev-copy snapshot 2026-04-30 (100 candidates, 116/116 filled, score -2199.97).

### M2 milestone closure note
M2 closed 2026-04-29. Across nine checkpoints (C1..C9), the milestone delivered: rule engine + scorer + solver + selector contracts (C1, C2); their Python implementations (C3, C4, C5); the operator-tuneable scoring config surface end-to-end across snapshot + parser + scorer + sheet-generator (C6, C7); the v3 spacingPenalty geometric-decay curve (C8); and the production Apps Script snapshot extractor + Python CLI ingestion path (C9). Architectural decisions span D-0024..D-0043 (twenty decisions). 141 Python tests + Apps Script tests via `clasp run runAllTests_`. Remaining gap to a fully operational pilot is the one-time Drive setup the maintainer performs once per environment per the M2 C9 setup recorded in project memory.

- **M2 C9 — Snapshot extraction (Apps Script) — D-0036 implementation** *(closed 2026-04-29; PRs #95 docs, #96 code, #97 closure)*
  - Production Apps Script extractor live: launcher generates operator sheets via `DriveApp.makeCopy(template)`; bound shim's `onOpen` installs the "Extract Snapshot" menu; central library at HEAD reads the sheet via DeveloperMetadata anchors with sheet-scoped finder + runId-paired tab discovery + per-anchor cardinality validation; Python CLI ingests the JSON.
  - Decisions: D-0040 (transport = browser-download), D-0041 (placement = bound template + central library; resolves FW-0024 architectural blocker as a side effect), D-0042 (snapshot identity = `snapshot_<spreadsheetId>_<extractionTimestamp>`), D-0043 (layout drift = DeveloperMetadata-anchored hard-fail).
  - New contract `docs/snapshot_adapter_contract.md`; cross-contract updates to writeback §6.3, sheet_generation §11B, and parser/snapshot forward-pointers. FW-0025 (per-email Drive sharing tightening) deferred with four explicit revisit triggers. 141/141 Python tests pass (end-to-end CLI run: 116/116 filled, score -21.534).
  - One-time Drive setup steps recorded in project memory `project_m2_c9_setup_ids.md`; per-project READMEs walk through each step.

- **M2 C8 — `spacingPenalty` geometric-decay shape (port v1)** *(closed 2026-04-28; PRs #92 docs, #93 code, closure PR)*
  - Replaced v2's binary `gap < 3` count with v1's geometric-decay curve (`weight / 2^(gap - 2)` for `gap ∈ {2..6}`, zero past `gap = 7`). 7-day cutoff embeds the once-per-week call cadence as the natural rhythm. Restores the continuous gradient the solver's `SEEDED_RANDOM_BLIND` Phase 2 tie-break needs.
  - **Scorer `contractVersion` bumped 2 → 3** per §2 (scoring-semantics change for valid configs); public `ScoringConfig` shape unchanged. Operator-tuneable curve parameters remain FW-0007 deferred.
  - Decision: D-0039. New normative subsection scorer §12A. 4 stale `v2` cross-refs caught by §14 bidirectional audit + fixed in-PR. 136/136 Python tests pass.

- **M2 C7 — Scorer Config tab (D-0037 sheet-generator half)** *(closed 2026-04-28; closure PR + hotfix #90 + UX-polish #91)*
  - Apps Script launcher generates the Scorer Config tab declared in `docs/sheet_generation_contract.md` §11A (D-0037 producer-side complement to M2 C6's consumer-side overlay). Each data row carries `DeveloperMetadata` keyed by canonical componentId; weight column operator-editable, rest locked. 4-column shape (Component / Weight / Description / Sign) with per-row sign-validation.
  - **FW-0024 attempted but reverted on Codex review** (PR #89): simple `onEdit` triggers don't fire on launcher-generated standalone-Web-App spreadsheets; deferred with the trigger-architecture finding captured in the FW-0024 entry.
  - No new architectural decisions — closes the D-0037 producer-side gap M2 C6 left open.

- **M2 C6 — Parser overlay for scoring config** *(closed 2026-04-28)*
  - Wired the Python consumer-side of D-0037 (operator-tuneable scoring config). New `parser/scoring_overlay.py` implements the §9 sheet-wins / template-defaults-backstop overlay; admission cases per parser_normalizer §14 (mis-signed / malformed weights, incomplete pointRules cross-product per D-0038, etc.). Weekday/weekend defaults applied via calendar-based today/tomorrow classification (no public-holiday calendar in first release).
  - Producer-side (Apps Script Scorer Config tab + production extractor) deferred to D-0036's late-M2 checkpoint. Test-only xlsx → snapshot bridge extended to emit empty `scoringConfigRecords`.
  - No new architectural decisions — tracks D-0037 + D-0038 contract semantics. 124/124 Python tests pass.

- **M2 C5 — Local run artifact basics** *(closed 2026-04-28)*
  - Implemented the selector stage (`HIGHEST_SCORE_WITH_CASCADE` per `docs/selector_contract.md` §11.1 + §12) and the `BEST_ONLY` / `FULL` retention surface with sidecar artifacts (`candidates_summary.csv`, `candidates_full.json`) under `FULL`. Closes the contract → implementation gap selector_contract.md has carried since M2 C2 closure.
  - Public entry: `select(scoredCandidateSet, *, retentionMode, runEnvelope, selectorStrategyId, selectorStrategyConfig=None, sidecarTargetDir=None) → FinalResultEnvelope`. Branch discipline (§10.3); failure-branch forwarding (§15); envelope passthrough (§16.4); byte-identical determinism (§18).
  - Architectural import-boundary check in tests confirms selector module does not consume `score(...)` or `evaluate(...)` per §9. No new architectural decisions. 115/115 Python tests pass.

- **M2 C4 — Minimal rule/scorer/solver integration** *(closed 2026-04-27; PRs #78..#86)*
  - Shipped the three remaining M2 compute-pipeline stages (rule engine + scorer + solver) wired onto the parser/normalizer's CONSUMABLE `NormalizedModel` from M2 C3, plus an integration smoke test exercising parser → solver → scorer end-to-end on the real ICU/HD May 2026 fixture.
  - Decisions: D-0037 (operator-tuneable scoring config — scorer v1 → v2 across 5 contracts), D-0038 (`pointRules` fail-loud on missing keys, supersedes D-0037 sub-decision 5).
  - Bidirectional contract-audit rule added to delivery_plan §14 (recurrence prevention for the M2 C2 audit miss D-0037 ultimately closed). FW-0024 surfaced and parked. 92/92 Python tests pass.

- **M2 C3 — Parser/normalizer implementation closure** *(closed 2026-04-27; PRs #70..#75)*
  - First executable code under M2 — the local-first Python parser/normalizer module (`python/rostermonster/`) implementing parser_normalizer_contract §6/§8/§10/§11/§13/§14/§15 + request_semantics §6..§15, with §17 explicit-handoff defense layer + provenance fields + `displayLabel` on `SlotTypeDefinition`.
  - Real-data hand-test against ICU/HD May 2026 dev-copy source via test-only xlsx → snapshot bridge (22 doctors, 29 days, 638 request records, 0 prefilled assignments).
  - Decisions: D-0033 (dateKey adapter normalization), D-0034 (doctor-name matching algorithm: trim + collapse internal whitespace + casefold), D-0035 (provenance shape locked, closes OD-0001), D-0036 (snapshot-extraction Apps Script pinned to late-M2 before M3 activation; transport jointly scoped with writeback §6.3). 24/24 Python tests pass.

- **M2 C2 — Selector contract closure** *(closed 2026-04-26; PRs #65, #66, #67)*
  - Closed the selector-stage contract boundary with `docs/selector_contract.md` covering pure-function surface, pluggable strategy interface mirroring solver's `StrategyDescriptor`, `HIGHEST_SCORE_WITH_CASCADE` first-release strategy, retention modes (`BEST_ONLY` / `FULL`), sidecar artifacts cross-referenced by `candidateId`, byte-identical determinism, sidecar `schemaVersion: 1`.
  - Decisions: D-0030 (selector at v1), D-0032 (selector v1 → v2 in-checkpoint to close contract-seam consistency gap with the writeback scope-ahead contract — added `runEnvelope.sourceSpreadsheetId` + `sourceTabName` to §9 item 3). Selector compliance under v2 implies writeback input compatibility on the source-sheet-identity surface.
  - Writeback contract drafted scope-ahead in PR #66 per D-0031 (M3 territory, not C2 scope).

- **M2 C1 — Rule engine + scorer + solver contract closure** *(closed 2026-04-25; PRs #63, #64)*
  - Closed the three interlocking M2 compute-pipeline contract boundaries: `docs/rule_engine_contract.md` (stateless, full-violation canonical ordering, scoped FixedAssignment handling), `docs/scorer_contract.md` (pure-function, required component breakdown, `HIGHER_IS_BETTER` direction-guard, `crReward` diminishing-marginal-utility), `docs/solver_contract.md` (scoring-blind, strategy-pluggable, `SEEDED_RANDOM_BLIND` first-release, `crFloor`, whole-run failure on unfillable slot, byte-identical determinism).
  - Decisions: D-0024..D-0029 (rule engine, scorer, solver, pipeline-stage separation `solver → scorer → selector`, operator-tuneable surface, `unitIndex` operational-equivalence narrowed to doctor admissibility per D-0029 sub-decision 1).

- **M1.1 C1 — Implement operator launcher web app** *(closed 2026-04-22)*
  - Apps Script web-app (`doGet()` HTML form + `submitLauncherForm` wiring) against `generateIntoNewSpreadsheet` / `generateIntoExistingSpreadsheet` entrypoints, deployed at a stable `/exec` behind `https://tinyurl.com/cghicuhdlauncherv1`. Auto-share of newly-created spreadsheets to "anyone with the link (Editor)" landed as additive operational polish per D-0023 (three-attempt sequence: `DriveApp` under `drive.file` → full `drive` → Drive Advanced Service v3).
  - Verified end-to-end through non-maintainer Test-User consent + generation path on a separate Google account and device; both output modes exercised; pilot-operator self-report independently confirms.

- **C4 — Implement operator-ready sheet generation** *(closed 2026-04-21)*
  - Delivered the ICU/HD request sheet shell end-to-end through Google Apps Script in `apps_script/launcher/`, covering both output modes (new spreadsheet file, new tab in existing spreadsheet). Whole-sheet protection restricted to the script owner with unprotected exceptions for operator-editable surfaces, warning-only regex validation on request-entry cells.
  - Verified against the C3 acceptance checklist for an operator-owned May 2026 cycle via `clasp run` against a user-managed GCP project. `clasp run` OAuth lesson recorded as D-0020.

- **C3 — Define generation acceptance/handoff readiness** *(closed 2026-04-18)*
  - Locked M1 implementation-ready checklist for ICU/HD first-release generation handoff without reopening C1/C2. Declared the first allowed implementation slice (template read + operator inputs + shell generation + output-mode support + practical locking/validation) and explicit out-of-scope items.

- **C2 — Align template artifact vs generation needs** *(closed 2026-04-18)*
  - Closed remaining cross-doc alignment between `docs/template_artifact_contract.md` and `docs/sheet_generation_contract.md`, including first-release visible title/header generated-surface alignment.

- **C1 — Close sheet-generation MVP boundary** *(closed 2026-04-17)*
  - Closed generation inputs, generated structural surfaces, allowed operator edits, editable/protected + validation boundary, explicit non-goals, and acceptance framing at contract/planning level.

### Recently completed milestones
- **M1.1 — Operator-facing launcher** *(closed 2026-04-22)* — closed on hands-on validation via M1.1 C1; addendum-milestone framing preserved (M1 not reopened); D-0021 / D-0022 / D-0023.
- **M1 — Operator-ready request sheet generation** *(closed 2026-04-21)* — closed on operator delivery via C4 against settled C1/C2/C3 contracts. D-0019 (closure), D-0020 (clasp OAuth lesson).

## 12. Change log for this delivery plan

> One line per closure (or material in-flight architectural event). Milestone-level activations / closures are bundled with the relevant checkpoint line. Day-by-day phase mechanics live in PR descriptions and git history.

- **2026-04-16:** Document created. Activated M1 + M1 C1.
- **2026-04-17:** Closed M1 C1 (sheet-generation MVP boundary). Activated M1 C2.
- **2026-04-18:** Closed M1 C2 (template artifact ↔ generation alignment). Activated and closed M1 C3 (acceptance/handoff readiness). Briefly closed M1 + activated M2; reverted same-day so M1 closure aligns with operator delivery rather than contract closure alone. Activated M1 C4 (implement operator-ready sheet generation).
- **2026-04-21:** Closed M1 C4 + closed M1 (operator delivery; D-0019). Activated M1.1 (operator-facing launcher addendum) + M1.1 C1; D-0021 (addendum convention) + D-0022 (launcher architecture).
- **2026-04-22:** Closed M1.1 C1 + closed M1.1 (hands-on validation). Activated M2 at milestone level.
- **2026-04-23:** Activated M2 C1 (rule engine + scorer + solver contract closure).
- **2026-04-25:** Closed M2 C1 (PRs #63, #64; D-0024..D-0029). Activated M2 C2 (selector contract closure).
- **2026-04-26:** During M2 C2, drafted writeback contract scope-ahead of M3 (D-0031 with eleven sub-decisions; FW-0019..FW-0023). Bumped selector v1 → v2 inside the still-active checkpoint to close contract-seam consistency gap with writeback (D-0032). Polish sweep across M2 contracts (PR #67) — wording-only, no semantics change. Closed M2 C2; activated M2 C3 (parser/normalizer implementation).
- **2026-04-26 to 2026-04-27 (M2 C3 in flight):** D-0033 (dateKey adapter normalization) + D-0034 (doctor-name matching) closed alongside T1; D-0035 (provenance shape locked; closes OD-0001) + D-0036 (Apps Script extractor pinned to late-M2 before M3) closed at T3.
- **2026-04-27:** Closed M2 C3 (PRs #70..#75). Activated M2 C4. Added bidirectional contract-audit rule to §14 (recurrence prevention for the M2 C2 audit miss). D-0037 (operator-tuneable scoring config — scorer v1 → v2 across 5 contracts) + D-0038 (`pointRules` fail-loud on missing keys, supersedes D-0037 sub-5) closed mid-checkpoint. FW-0024 added. Closed M2 C4 (PRs #78..#86).
- **2026-04-28:** Activated and closed M2 C5 (local run artifact basics — selector implementation + sidecars). Activated and closed M2 C6 (parser overlay for scoring config). Activated and closed M2 C7 (Scorer Config tab — D-0037 sheet-generator half; FW-0024 attempted but reverted on Codex review). Activated M2 C8 (spacingPenalty geometric-decay shape; D-0039; scorer v2 → v3) and closed it.
- **2026-04-29:** Activated M2 C9 (snapshot extraction Apps Script — D-0036 implementation; D-0040..D-0043; new contract `docs/snapshot_adapter_contract.md`). Closed M2 C9 + closed M2 (PRs #95, #96, #97). The `m1_template_bound_script/` and `m1_extractor_library/` directories created in Phase 2 were renamed to `m2_*` in the closure round to match the milestone-prefix-by-introduction convention.
- **2026-04-30:** Activated M3 + M3 C1 same-day (writeback library + launcher route + Python CLI extension; D-0044..D-0047). Closed M3 C1 (PRs #100, #101, #102) — Phase 2 surfaced contract amendment growing writeback §9 from 5 to 6 categories (closes D-0045 Follow-up #2). Closed M3 at milestone level (M3 C2 dropped per D-0048 — round-trip already proven); activated M4 same-day per D-0049 reframing M4 to `Cloud end-to-end pipeline + dual-track preservation`; old M4/M5 → FW-0027 + FW-0028. Activated M4 C1.
- **2026-05-01:** Closed M4 C1 + closed M4 (PRs #103, #104, #105, #106; D-0048..D-0054). D-0053 (random-seed default) and D-0054 (Cloud Run public-service + Flask-side X-Auth-Token allowlist; amends D-0051 sub-2 after `aud`-mismatch live-test failure) settled in-flight as accepted decisions. FW-0029 (template-aware label propagation in writeback library) added. Active milestone moves to *none*; solver-strategy optimization (D-0049's forward-pointer) lands as its own forthcoming milestone slot rather than M4 C2.
- **2026-05-04:** Activated M5 (`Operator-side analysis & multi-roster delivery`) + M5 C1 same-day (D-0055). M5 reframes the post-M4 priority by sequencing operator-side analysis tooling AHEAD of solver-side score-aware search (LAHC etc., parked for M6) — analysis tooling acts as the calibration framework + multi-objective workaround. Three-piece architecture: Python analyzer engine + `AnalyzerOutput` + Apps Script analyzer renderer, sibling consumer of the wrapper envelope (writeback contract untouched, no new selector retention mode, top-K + diversity is analyzer's responsibility). FW-0030 (cloud-side FULL retention support) added as M6 prerequisite. M5 C1 detailed scope (`AnalyzerOutput` schema, aggregates, diversity criterion, comparison-tab UX) deferred to dedicated design thread that opens after this activation PR merges. No code changes in this PR — direction-setting docs only, mirroring the D-0049 pattern.
- **2026-05-04 (M5 C1 contract draft):** Drafted new contract `docs/analysis_contract.md` (`contractVersion: 1`) closing D-0055's deferred concrete-shape items. D-0056 (analyzer top-K = pure score-rank, no diversity heuristic — operator-tunable `--top-k N`, default 5, bounds `[1, 20]`, fail-loud out of range; tiebreak mirrors `HIGHEST_SCORE_WITH_CASCADE`'s two-level cascade per `docs/selector_contract.md` §12.2: higher `pointBalanceGlobal`, then higher `crReward`, then numerically lowest `candidateId`; promotes Tier 5 `pairwiseHammingDistance` from optional flavor to load-bearing operator diagnostic). D-0057 (analyzer I/O shape — input = full snapshot + wrapper envelope + `candidates_full.json`; CSV explicitly excluded; the wrapper envelope's writeback-narrow `snapshot` sub-object is also explicitly NOT analyzer input — analyzer reads the full snapshot directly because the writeback subset doesn't carry per-doctor `displayName` / full `dayRecords` / post-overlay `scoringConfigRecords`; output = single `AnalyzerOutput` JSON file symmetric with D-0044/D-0045 wrapper-envelope pattern; amended in-PR after Codex review surfaced the wrapper-snapshot-shape mismatch in the original draft). D-0058 (Tiers 1–5 v1 emission scope; Tier 6 per-candidate rule-violation breakdown deferred to FW-0032 because not reachable from declared analyzer inputs without rule-engine coupling or selector-side sidecar extension; Tier 7 decision-support tags renderer-derived; snapshot-extension fields parked as FW-0031). FW-0031 (snapshot-extension analyzer fields — senior-junior pairing, leave-history-aware analysis, rotation-conflict surfacing, public-holiday classification — added with five explicit revisit triggers including the round-3 PH amendment). FW-0032 (per-candidate rule-violation surface for analyzer Tier 6 — added in round-9 amendment; lands via additive analyzer-contract bump per §14 once one of two upstream paths chosen — selector-side sidecar extension carrying violation breakdown, OR analyzer-side rule-engine integration). No code changes in this PR — contract draft only, mirroring the M2/M3/M4 docs-first cadence; analyzer-engine implementation lands as a separate sub-PR.
- **2026-05-05 (M5 C1 implementation):** Implemented the analyzer engine in new `python/rostermonster/analysis/` module per the contract pinned in PR #110 (PR #111). Module split into `output.py` (AnalyzerOutput dataclasses + JSON renderer with byte-identical determinism per §15), `admission.py` (fail-loud admission per §9.1 / §9.2 / §9.5 / §10.0 / §11), `selection.py` (top-K with full selector-cascade tiebreak per §11), `aggregates.py` (Tier 1–5 computations; cumulativeCallPoints reuses `parser/scoring_overlay.py` per §10.6), `__init__.py` (orchestrator), `__main__.py` (`python -m rostermonster.analysis ...` CLI per §16). 52 unit tests + 9 integration tests on the May 2026 ICU/HD fixture. 225/225 Python tests pass.
- **2026-05-05 (M5 C1 closure):** M5 C1 closes; active checkpoint pointer moves M5 C1 → M5 C2 (Apps Script analyzer renderer). M5 itself remains Active — C2/C3/C4 outstanding. Terminology fix: dropped the "Phase 1 / Phase 2 / Phase 3" labels for sub-PR cadence in favor of describing each sub-PR by what it accomplishes (contract draft / implementation / closure). The canonical planning vocabulary stays Product → Milestone → Checkpoint → Task per `docs/blueprint.md` §"Planning vocabulary"; "Phase" was an informal cadence convention from M2/M3/M4 PR titles that wasn't part of the canonical vocab.
- **2026-05-05 (Apps Script directory rename):** Renamed three Apps Script directories from milestone-prefixed to role-based names per D-0059: `apps_script/m1_sheet_generator/` → `apps_script/launcher/`, `apps_script/m2_template_bound_script/` → `apps_script/bound_shim/`, `apps_script/m2_extractor_library/` → `apps_script/central_library/`. Cloud-side Apps Script project name `Roster Monster Extractor Library` correspondingly renamed to `Roster Monster Central Library` (maintainer one-time step — Script ID stable). Cross-doc sweep updates 13 docs/source files + project memory. Supersedes the M2 C9 closure note's "milestone-prefix-by-introduction" convention.
- **2026-05-05 (M5 C2 contract draft):** Drafted new contract `docs/analysis_renderer_contract.md` (`contractVersion: 1`) closing M5 C2's deferred design items. D-0060 (renderer module placement = central library, file `apps_script/central_library/src/AnalysisRenderer.gs` per the `Writeback.gs` precedent in D-0052). D-0061 (separate renderer contract document rather than extending `docs/analysis_contract.md`; mirrors writeback's separate downstream-consumer contract precedent). D-0062 (target spreadsheet = source spreadsheet identified by `output.source.sourceSpreadsheetId`, accepting tab-bloat trade-off — operator workflow simplicity wins; co-exists with writeback's roster tab; always-new-tab collision policy mirrors `docs/writeback_contract.md` §11). D-0063 (invocation surface = route on the existing launcher Web App, mirroring D-0046's writeback upload pattern; direct-from-bound-shim and other surfaces deferred). No code changes in this PR — contract draft only, mirroring the contract-first cadence.
- **2026-05-06 (M5 C2 implementation):** Implemented `apps_script/central_library/src/AnalysisRenderer.gs` per the contract pinned in PR #114 (PR #115). Public `RMLib.renderAnalysis(output)` returns `AnalysisRendererResult` per `analysis_renderer_contract.md` §10. Implements §9.1 fail-loud admission (contractVersion + sourceSpreadsheetId + non-empty topK + duplicate candidateId rejection + openById permission), §10.2 spreadsheetUrl presence rules, §11 source-spreadsheet target, §12 always-new-tab `(N)` collision policy, §13 K roster tabs (header + per-day grid + per-doctor + per-component) + 1 comparison tab (score-decomp matrix with column-best/worst highlighting + equity scalars + hot/locked days + Hamming matrix), §14 best-effort sequential `SpreadsheetApp.flush` per tab, §16 structured `error.code` codes. Reuses writeback's color palette + footer/metadata/protection patterns. Duplicate doctor display names disambiguated per §10.0 (post-Codex-round-2 fix). Partial-state surface lists tabs as soon as `insertSheet` succeeds (post-Codex-round-3 fix). Launcher delegate shim `apps_script/launcher/src/AnalysisRenderer.gs` does the JSON-string deserialize before calling `RMLib.renderAnalysis(output)` (post-Codex-round-1 fix; library boundary is in-memory object per §6 + §9). New `?action=analysis-render` route in `Launcher.gs` `doGet`; `AnalysisRendererForm.html` upload form mirrors `WritebackForm.html`.
- **2026-05-06 (Launcher Web App nav header):** Added cross-page navigation (Generate sheet / Apply writeback / Render analysis) to all three launcher Web App forms (PR #116). Active item rendered as inert `<span>`; inactive items render as absolute-href `<a>` tags using `<?= rootUrl ?>` populated from `ScriptApp.getService().getUrl()` server-side (relative hrefs don't survive Apps Script's iframe sandbox; post-Codex-round-1 fix). Visual style mirrors the existing launcher palette. CSS duplicated across the three forms — Apps Script HtmlService templating doesn't expose clean per-form parameters. No new manifest scopes.
- **2026-05-06 (Cloud rollout):** Pushed `apps_script/central_library/` (8 files including new `AnalysisRenderer.gs`) and `apps_script/launcher/` (18 files including new `AnalysisRenderer.gs`, `AnalysisRendererForm.html`, updated `Launcher.gs` `doGet`, updated `LauncherForm.html`/`WritebackForm.html`/`AnalysisRendererForm.html` with nav). Bumped launcher deployment `AKfycbwCOsci...` from `@14` → `@15` ("M5 C2: analysis-render route + cross-page nav"); deployment ID + tinyurl URL stable. Operator-facing renderer live.
- **2026-05-06 (M5 C2 closure, this PR):** M5 C2 closes; active checkpoint pointer moves M5 C2 → M5 C4 (live operator validation). C3 dropped from the milestone plan — the upload-portal scope was wholly absorbed into C2's launcher Web App route per D-0063 + the cross-page nav per PR #116, so a separate C3 added no value (same discipline as M3 C2 dropped per D-0048 when C1 already met exit criteria). M5 milestone stays Active pending C4 live-operator validation; C4 is operator-availability-bounded, not code-bounded.

## 13. Relationship to other repo docs
- `README.md` = front door orientation.
- `docs/blueprint.md` = stable architecture truth.
- `docs/roadmap.md` = milestone-level delivery order.
- `docs/delivery_plan.md` = active execution guide.
- `docs/decision_log.md` = accepted directional decisions.
- `docs/open_decisions.md` = pending decisions surfaced by implementation, awaiting closure.
- `docs/future_work.md` = non-normative parking lot for ideas.
- Contract docs = normative technical boundary definitions.

## 14. Maintenance rules for this document
- Keep exactly one active milestone unless there is a deliberate exception.
- Keep exactly one active checkpoint unless there is a deliberate exception.
- Update this document whenever execution focus changes.
- Do not duplicate normative contract wording here.
- Do not turn this document into a full issue tracker.
- If a task does not support the active checkpoint, it likely does not belong here.
- Cross-contract consistency audits MUST trace every producer-consumer seam in BOTH directions. Forward: when contract X says it consumes Y, verify Y's producer contract declares Y as a normative output. Reverse: when contract X references producing Y for a downstream consumer, verify the consumer's contract declares Y in its input shape. The reverse direction is the harder one to remember (the M2 C2 contract-surface audit missed `scorer_contract.md` §15 ↔ `parser_normalizer_contract.md` §9 because of it; the gap surfaced four contract-touches later, during M2 C4 T2 implementation, instead of at the C2 audit window).

## 15. Initial seed content
Reflects the 2026-05-06 closure of **M5 C2** (Apps Script analyzer renderer; renderer + launcher Web App route + nav header live in cloud at deployment `@15`) and the active-checkpoint pointer moving to **M5 C4** (live operator validation; C3 dropped because the upload-portal scope was wholly absorbed into C2 — same discipline as M3 C2 dropped per D-0048). On top of the 2026-05-05 closure of M5 C1, on top of the 2026-05-04 activation of M5 per D-0055, on top of the 2026-05-01 closure of M4 on M4 C1.

- active milestone **M5**; active checkpoint **M5 C4**.
- closed milestones: **M1 (C1–C4) + M1.1 (C1) + M2 (C1–C9) + M3 (C1) + M4 (C1)**, anchored by **D-0019..D-0054** with closure entries in §11.
- closed checkpoints inside the active milestone: **M5 C1** (analyzer engine + contract draft; PRs #110, #111), **M5 C2** (Apps Script renderer + launcher Web App route + cross-page nav; PRs #114, #115, #116, plus closure PR; cloud deployment `@15`). M5 C3 dropped from the plan.
- M5 activation: **D-0055** (M5 framing — operator-side analysis & multi-roster delivery; Python analyzer engine + Apps Script renderer + upload portal as sibling consumer of the wrapper envelope; purely additive, no upstream contract changes).
- M4 architectural surface: **D-0048..D-0054** (close M3 early; reframe M4; dual-track Python; Cloud Run + consolidated GCP project; Apps Script library reorg; random-seed default; public-service auth via X-Auth-Token allowlist). New contract `docs/cloud_compute_contract.md` (`contractVersion: 1`).
- Full **sheet → snapshot → Python compute → writeback** round-trip runs end-to-end on real ICU/HD data in **both modes**: local (browser-download Snapshot JSON → Python CLI → file upload via launcher form → writeback tab) and cloud (bound shim's `Roster Monster → Solve Roster` menu → POST to Cloud Run → in-memory writeback within one Apps Script invocation, ~30-90s sync wait). Both modes share the same Python compute core per D-0050 and produce byte-identical wrapper envelopes at same `(snapshot, optionalConfig)` when seed is explicitly set per D-0053's parity precondition.
- **225/225 Python tests pass** via standalone runners (164 baseline + 52 analyzer unit + 9 analyzer integration added in M5 C1). Apps Script tests run via `clasp run runAllTests_` on the launcher project (17 writeback-helper unit tests added under M3 C1).
- scorer contract is at `contractVersion: 3` per D-0039; `ScoringConfig` public shape unchanged from v2. Writeback contract `contractVersion: 1`, §9 6 categories. Selector v2.
- contracts settled across M2 + M3 + M4 + M5 C1 + M5 C2: snapshot, snapshot_adapter, parser_normalizer, template_artifact, sheet_generation, rule_engine, scorer (v3), solver, selector (v2), writeback (`contractVersion: 1`, §9 6 categories), cloud_compute (`contractVersion: 1`), analysis (`contractVersion: 1`, drafted + implemented under M5 C1 per D-0056 / D-0057 / D-0058), analysis_renderer (`contractVersion: 1`, drafted + implemented + deployed under M5 C2 per D-0060 / D-0061 / D-0062 / D-0063).
- transport: **local mode** — inbound = browser-download per D-0040; outbound = file upload via launcher form per D-0044 (no new OAuth scopes). **Cloud mode** — inbound = in-memory snapshot via central library entrypoint; outbound = HTTP request body + structured-response envelope per `docs/cloud_compute_contract.md`. Cloud mode required four bound-shim manifest scopes per D-0051 sub-3a + D-0054: `script.external_request`, `openid`, `userinfo.email`, and `spreadsheets` (broadened from `currentonly`). Cloud Run runs `--allow-unauthenticated`; operator-identity gating is via Flask-side `ALLOWED_EMAILS` per D-0054.
- `docs/open_decisions.md` is empty.
- explicit deferrals retained from M1.1 + M4 + M5: public signup, in-app allowlist, operator-editable template, persisted per-operator state, alternative launcher platforms; parallel orchestration → FW-0027; observability → FW-0028; template-aware label propagation in writeback library → FW-0029; service-account-based Cloud Run auth → D-0054 §7.6; cloud-side FULL retention support → FW-0030 (prerequisite for M6's eventual Deep Solve auto-included analyzer path); snapshot-extension analyzer fields (senior-junior pairing, leave history, rotation conflicts, public-holiday classification) → FW-0031 (added in M5 C1 contract-draft PR #110; PH support added in the round-3 in-PR amendment after Codex flagged hardcoded-zero PH counts as silently corrupting); per-candidate rule-violation breakdown (Tier 6 — `softCount` / `softByRule` / `hardByRule`) → FW-0032 (added in M5 C1 contract-draft PR #110 round-9 amendment after Codex flagged that v1 declared inputs don't carry per-rule firing detail); diversity-aware top-K selection at the analyzer stage → explicitly out of scope per D-0056 (diversity belongs in solver-strategy work, not analyzer); LAHC and any score-aware solver strategy → M6 (parked, not pre-committed).
