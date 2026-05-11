# Roster Monster v2 Blueprint

## Planning vocabulary

- **Product**: the full end-to-end capability Roster Monster v2 is building.
- **Milestone**: a major delivery state that advances the product.
- **Checkpoint**: a bounded, reviewable step within a milestone.
- **Task**: a concrete work item used to close a checkpoint. Typical decomposition inside a checkpoint follows the **Task 1 (docs) → Task 2 (code, with optional Task 2A / 2B / 2C sub-letters when work has logically distinct chunks) → Task 3 (closure)** cadence per D-0064. Not a contract — a docs-only checkpoint may be just Task 1; an unusual checkpoint may have a different shape. Historical "Phase 1/2/3" labels in past PR titles and closed-milestone closure entries (M2..M5 C2) are preserved as-is.

This blueprint is the stable architecture truth; active execution status belongs in `docs/delivery_plan.md`.

## 1. Project definition

### What Roster Monster v2 is
Roster Monster v2 is a planning and execution architecture for doctor roster allocation, built as:
- a **reusable allocation core**
- plus **department-specific templates**
- with **Google Sheets retained as the operational front end**

### Who it is for
- Internal roster operations and engineering teams maintaining departmental roster workflows.
- Department stakeholders who need reliable roster generation using department-specific rules.

### What problem it solves
- Produces valid, explainable roster outputs from structured sheet inputs and department rules.
- Reduces one-off logic by centralizing reusable allocation behavior.
- Makes department adaptation repeatable through templates instead of ad hoc rewrites.

### What it is not
- Not a universal self-serve roster builder for all departments.
- Not a replacement UI for Google Sheets.
- Not an attempt to solve every department in the first release.

**Implementation anchor:** **CGH ICU/HD is the first department implementation**, not the full product scope.

## 2. Why v2 exists
v2 exists because v1 has structural limits that block reliability and reuse:
- Parser behavior is too rigid for evolving sheet inputs.
- Search / solver quality is not good enough for expected roster quality.
- Worker / cloud path is brittle and hard to trust operationally.
- Debugging and re-examination are too difficult.
- Boundaries between parsing, rules, solving, and output are not clean enough.
- v1 accumulated rushed AI-generated glue with insufficient human ownership and long-term maintainability.

## 3. Goals

### Functional goals
- Generate valid rosters that satisfy hard constraints.
- Support ICU/HD first, while preserving a path to additional departments via templates.
- Preserve Google Sheets as the operator-facing workflow.

### Engineering goals
- Enforce clean module boundaries with explicit contracts.
- Maintain deterministic, reproducible compute from the same snapshot + seed.
- Improve hardening of parser, solver, and execution paths.

### Operational goals
- Provide observable run progress and failure states.
- Produce artifacts that allow fast re-examination of any run.
- Support reliable local and external worker execution modes.

## 4. Non-goals
v2 is explicitly **not**:
- A universal self-serve builder for any department.
- A real-time live scheduling system.
- A day-1 solution for every department.
- A replacement for Google Sheets as the main operational UI.

## 5. Core invariants
These rules are non-negotiable and must never be violated:
- Hard constraints override everything else.
- Blocked means blocked.
- One doctor cannot hold more than one slot on the same date.
- Invalid candidates must never be assigned.
- Scoring direction must be consistent: **higher score = better roster**.
- If no valid candidate exists, the system must report that clearly (not silently degrade).

## 6. Product model
v2 follows a multi-layer model:
- **Department Template**: declares department-specific structure, mappings, and contract bindings.
- **Template-declared request form layout**, template `outputMapping`, and `docs/sheet_generation_contract.md` define first-release template-driven generation requirements for the full operator-facing sheet shell; the lower roster/output shell may be generated empty, later partially operator-prefilled, and later completed. Generation mechanics remain outside this blueprint checkpoint.
- **Sheet Adapter**: handles Google Sheets read/write integration.
- **Core Engine**: parses, normalizes, validates, solves, and scores.
- **Writer / Execution / Observability support layers**: package outputs, run compute in local/cloud modes, and emit diagnostics.

This model separates reusable allocation logic from department-specific behavior.
Implementation ownership note: sheet-native surface work is implemented in Google Apps Script — the narrowest Sheets-facing integration path — and today includes the M1 generator core, the M1.1 operator-facing launcher, the M2 bound shim + central extractor library (D-0041), the M3 writeback library hosted on the central library (D-0052), the M4 bound shim's `Roster Monster → Solve Roster` orchestration menu, and the M5 launcher's `?action=analysis-render` route + the central library's `AnalysisRenderer.gs` (D-0060). Compute-heavy core logic stays outside Apps Script and is realized as the dual-track Python architecture per `docs/decision_log.md` D-0050: a shared compute core (`python/rostermonster/pipeline.py`), a thin local CLI wrapper (`python/rostermonster/run.py`), and a thin HTTP wrapper (`python/rostermonster_service/app.py`) deployed to Cloud Run as `roster-monster-compute` per D-0051 / D-0054. Both wrappers call the same compute core and produce byte-identical envelopes at the same `(snapshot, optionalConfig)` input when seed is explicitly set per D-0053. M5 (closed 2026-05-07 per D-0065) added an analyzer subsystem as a **sibling consumer** of the wrapper envelope alongside writeback: a Python analyzer engine (`python/rostermonster/analysis/`) producing an `AnalyzerOutput`, plus an Apps Script analyzer renderer (`apps_script/central_library/src/AnalysisRenderer.gs` per D-0060) writing K roster tabs + 1 comparison tab into the source spreadsheet (D-0062), invoked via a route on the existing launcher Web App (D-0063 mirroring D-0046's writeback upload pattern). The analyzer subsystem is purely additive — writeback contract, selector contract, scorer contract, solver contract, and the wrapper-envelope shape stay unchanged. M6 (closed 2026-05-09 per D-0069) added **Late Acceptance Hill Climbing (LAHC)** as the first alternative solver search strategy alongside today's `SEEDED_RANDOM_BLIND` — strategy-internal-to-solver framing. M6 C1 closed 2026-05-07 per D-0067: `docs/solver_contract.md` §11.1 expanded to "Registered strategies" listing both `SEEDED_RANDOM_BLIND` and `LAHC`; new §12A pins the full LAHC algorithm spec (K-independent-seeds emission, idle/hard-iter inner termination, deterministic trajectory-seed derivation, history-list `L=1000` default, `scoringConsultation: "READ_ONLY_ORACLE"` extension-clause activation per §11.2). Solver contract bumped to `contractVersion: 2` — driven by §9 promoting `strategyId` to a required boundary input (input-shape change per §2); LAHC's strategy registration alone via §11.2 would NOT have required a bump. M6 C2 closed 2026-05-08: LAHC implemented end-to-end in `python/rostermonster/solver/` per §12A spec (Task 2A strategy abstraction in `strategy_registry.py` + `strategy.py`; Task 2B inner-loop in new `lahc.py`; Task 2C K-trajectory + determinism + ICU/HD fixture integration tests). M6 C3 closed 2026-05-08: envelope-shape additive bump in `docs/selector_contract.md` §16.5 (optional `solverStrategy` + `solverStrategyConfig` fields, no `contractVersion` bump per §16.3 additive-optional rule); CLI flags wired in `python/rostermonster/run.py` (`--strategy`, `--lahc-history-length`, `--lahc-iter-cap`, `--lahc-idle-threshold` per `docs/solver_contract.md` §12A.7); pipeline-level + analyzer-chain integration tests; **D-0068** narrows C3 to local-first; cloud-mode LAHC integration carved off to **FW-0035**. M6 C4 closed 2026-05-09 per D-0069: closure scope shifted from a live operator-cycle comparison-tab cross-reference to dev-copy empirical characterization because the dominance signal was already overwhelming on the May 2026 ICU/HD dev-copy fixture (paired t(4)=11.10, p≪0.001, mean Δ +53.85 score points across 5 seeds at comparable wall-time budgets). Cloud benchmarking on the SRB cloud baseline (the cloud wrapper ships `SEEDED_RANDOM_BLIND` only in v1 per D-0068 / FW-0035) surfaced a different load-bearing concern — single-thread bottleneck (4-vCPU bump only +10% throughput on the SRB baseline; signal generalizes to LAHC because both share GIL-bound pure-Python compute), captured as **FW-0038** (parallel solver — M7 candidate framing). PR #134 PR-A landed `LahcParams.swapProbability: float = 0.5` + `--lahc-swap-probability` CLI flag + `apps_script/launcher/src/DeleteSheetsById.gs` maintainer utility; resolved `swapProbability` value threads through audit surfaces (`SearchDiagnostics.lahcSwapProbability` per §12A.9, `LahcParamsRecord.swapProbability` per §16.5, `runEnvelope.solverStrategyConfig.lahcParams.swapProbability` per Codex P2 round-1 fix). Sweet-spot defaults `L=10` / `idleThreshold=2000` / `swapProbability=0.5` / `K=10–20` (per FW-0036 + FW-0037 dev-copy evidence) captured as override knobs but **not module-pinned** pending multi-fixture validation. Two strategy-aware fields cross the solver boundary at v2: (i) `strategyId` as a required input per `docs/solver_contract.md` §9 — callers MUST pass it explicitly; (ii) the wrapper envelope's `solverStrategy` enumerant as an output recording which strategy ran (envelope-shape additive bump location settled in M6 C3) so the M5 analyzer + ops trail can see what ran. Maintainer-only operator-tunable surface (Python module constants for cloud defaults + CLI flag overrides for local tuning; no operator-facing UI changes). Cloud Deep Solve + email-notification architecture + cloud-side FULL retention promotion (FW-0030) + scoring-formulation rework (FW-0033) explicitly carved off to FW or future milestones. Active milestone moves to *none* at M6 close, then **M7 (parallel solver, async UX) activates 2026-05-10 per D-0070** — Cloud Batch + intra-request K-fanout via dense pack (`c3-highcpu-8` VMs × `multiprocessing.Pool(8)` × 1 LAHC trajectory per vCPU; `taskCount = ceil(K_approved / 8)` derived from the approved-quota K). **UX pivoted sync → async on 2026-05-11 per D-0071** driven by M7 C2 perftest evidence: original M7 framing (D-0070) targeted a sync request inside a 250s Cloud Run timeout, but the M7 C2 wall-clock perftest on the real production roster at K_approved=104 returned 5/13 tasks unfinished at the 240s deadline (partial K'=64). D-0071 replaces that with an async architecture for M7 C3 onward, **amended at Codex P1.7 fix 2026-05-11** to single-VM with inline finalize step: Cloud Run thin front door (validate + submit + return SUBMITTED ~3-5s) + Cloud Batch single-task job (one `c3-highcpu-88` running `multiprocessing.Pool(88)` for K=88 LAHC trajectories; the same Cloud Batch task runs the inline finalize step in the same Python process after `Pool.close() + .join()` — aggregate + score + analyze + POST callback to launcher → launcher sends operator email) with a 10-min hard cap. Cloud Batch v1's `Job.taskGroups[]` is documented as "Only one TaskGroup is supported now" — the original D-0071 framing's "finalizer task group with `SUCCEEDED_OR_FAILED` dependency on the worker group" would fail `submitJob` validation. K reduces 104 → 88 (statistically equivalent — both 4-9× past best-of-K plateau per FW-0036). M7 escapes the GIL-bound single-thread bottleneck identified during M6 C4 cloud benchmarking. FW-0037 elbow tuple locked at the M7 production config: `L=50` / `idleThreshold=3500` / `swapProbability=0.5`; K_target=2,500 (smaller approvals acceptable; K=88 reflects current C3_CPUS=108 quota — FW-0040 dial unlocks K=176 on quota bump). On-demand pricing chosen over Spot for predictable wall-time. M7 C1 closed 2026-05-10 with asia-southeast1 quota approvals: CPUS=300 / INSTANCES=350 / C3_CPUS=108 (binding); historical closure-K=104 per D-0070 sub-decision 7's three-quota rule (recorded against the 13-VM design M7 C2 implemented). M7 C2 closed 2026-05-11 — full Cloud Batch parallel-LAHC chain delivered (worker module + orchestrator wiring + Batch job spec + GCS adapter + per-call attempt-id race closure across 7 PRs #138 → #144) with the §12A.4 byte-identity exit criterion proven (5/5 audit tests). M7 C3 (async architecture decision per D-0071 + Codex P1.7 single-VM amendment) is the active checkpoint — docs-only — locks the architecture: cloud_compute §9 gains `operatorEmail` required input + amends §10 to add a SUBMITTED state, plus a new async-callback contract section pinning the B-prime callback envelope shape (POST `{idToken, operatorEmail, state, writebackEnvelope?, analyzerOutput?, error?, diagnostics}` to a SECOND launcher Web App deployment with `executeAs: USER_DEPLOYING` for the callback route, GCP ID-token-in-body auth). Subsequent M7 C4 implements: Cloud Run shrinks to thin front door; Cloud Batch single-task job (one `c3-highcpu-88` + Pool(88) + inline finalize after Pool.join in `worker.py`); bound shim `Solve Roster` shows in-flight toast then returns; launcher gains async-render-callback route on the new USER_DEPLOYING deployment invoking existing `RMLib.applyWriteback + RMLib.renderAnalysis` + `MailApp.sendEmail`; always-email-on-success-or-failure with `[RosterMonsterV2]` subject prefix + AnalyzerOutput JSON attachment; concurrent-rejection by spreadsheet ID via Cloud Batch labels. M7 C5 live-operator validates + closes M7. FW-0035 (cloud-mode LAHC integration) + FW-0030 (cloud-side FULL retention support) co-promote with M7 closure. FW-0027 absorbed into M7 C3+C4 per D-0071. New FW-0039 (silent-operator-outcome watchdog gap) captured per D-0071 sub-decision 17 + Codex P1 fix — accepted-for-v1 covering both finalizer-crash AND callback-unreachable. New FW-0040 (K=88 → K=176 future quota-bump dial) per Codex P1.7 amendment.

## 7. Boundary definitions

### 1) Department Template layer
**Responsibilities**
- Define slot/group structure and first-release group-based eligibility declarations.
- Define request/input sheet layout mapping and output mapping.
- Bind to the appropriate request semantics contract used for request interpretation.
- Carry the scoring section as an explicit minimal first-release stub (`scoring.templateKnobs: []`).
- Act as declarative/configurational artifacts for department behavior.

**Must not do**
- Execute Google Sheets I/O directly.
- Contain solver implementation details.
- Embed arbitrary executable logic.

**Inputs / outputs**
- Input: template authoring data.
- Output: validated department template artifact.

### 2) Sheet Adapter layer
**Responsibilities**
- Read from and write to Google Sheets.
- Convert sheet structure into raw input payloads expected by parser.
- Implement Google Sheets-facing surface mechanics (including Apps Script-based integration when used).

**Must not do**
- Decide hard rule validity or scoring.
- Embed department logic outside declared template mappings.
- Own compute-heavy parser/normalizer, rule, solver, or scorer behavior.

**Inputs / outputs**
- Input: sheet identifiers/ranges + template mapping hints.
- Output: raw sheet snapshot data and writeback payloads.

### 3) Parser + Normalizer layer
**Responsibilities**
- Parse raw sheet + template into a common internal model.
- Interpret raw snapshot request content using template declarations plus the bound request semantics contract.
- Normalize values, detect structural issues, report parse/normalization outcomes.

**Must not do**
- Perform combinatorial search.
- Override hard-rule decisions.

**Inputs / outputs**
- Input: sheet snapshot + department template.
- Output: normalized domain model + issues.

### 4) Rule Engine layer
**Responsibilities**
- Act as the single source of truth for hard validity.
- Determine whether candidate assignments are valid/invalid.

**Must not do**
- Rank alternatives by preference.
- Perform transport, orchestration, or sheet I/O.

**Inputs / outputs**
- Input: normalized model + candidate assignment state.
- Output: validity decisions + violation reasons.

### 5) Solver / Search layer
**Responsibilities**
- Perform pure compute search over possible assignments.
- Use rule engine validity checks to keep search space legal.

**Must not do**
- Define hard rules itself.
- Perform writeback or logging transport.

**Inputs / outputs**
- Input: normalized model + rule engine interface + seed/config.
- Output: one or more valid roster candidates (or explicit unsatisfied result).

### 6) Scorer layer
**Responsibilities**
- Rank valid rosters using explicit scoring logic.
- Keep score semantics stable and explainable.

**Must not do**
- Make invalid rosters appear acceptable.
- Implicitly change score direction.

**Inputs / outputs**
- Input: valid roster candidates + scoring knobs.
- Output: scored/ranked roster candidates.

### 7) Writer / Result layer
**Responsibilities**
- Convert solved output into roster artifacts and writeback forms.
- Emit run outputs for audit and downstream handling.

**Must not do**
- Re-solve or reinterpret hard validity.
- Hide unresolved-slot failures.

**Inputs / outputs**
- Input: selected roster result + metadata.
- Output: final result artifacts + writeback payload.

### 8) Execution / Worker layer
**Responsibilities**
- Run pipeline locally or on external worker/cloud path.
- Manage job transport, retries, and execution envelopes.

**Must not do**
- Redefine parser/rule/scoring behavior.
- Own department business logic.

**Inputs / outputs**
- Input: run request + snapshot/config references.
- Output: run completion status + artifacts/events.

### 9) Observability layer
**Responsibilities**
- Emit structured logs, progress events, failures, metrics.
- Preserve traceability across parsing, solving, scoring, and writeback.

**Must not do**
- Mutate core compute behavior.
- Replace explicit contracts with implicit diagnostics.

**Inputs / outputs**
- Input: events from all runtime layers.
- Output: log/event streams, run summaries, and diagnostic artifacts.

## 8. Contracts that must exist
The architecture requires explicit contracts (to be defined in dedicated docs/specs):
- Department template contract.
- Normalized domain model contract.
- Snapshot/input contract.
- Parser / normalizer contract defining the boundary between snapshot input and normalized domain output.
- Result/output contract.
- Log/event contract.
- Writeback contract.
- Cloud compute contract defining the HTTP wrapper boundary (`docs/cloud_compute_contract.md`).
- Analysis contract defining the analyzer engine boundary (`docs/analysis_contract.md`).
- Analysis renderer contract defining the Apps Script renderer ↔ source spreadsheet boundary (`docs/analysis_renderer_contract.md`).

## 9. Features to retain from v1
- Google Sheets as the operational front end.
- Snapshot-driven compute model.
- Explicit scorer as a distinct concept.
- Benchmarking/campaign concept for comparative runs.
- Artifact-based debugging workflow.
- External worker execution option.
- Seed-based reproducibility.

## 10. Features to redesign
- Parser architecture and maintainability.
- Normalization behavior and issue reporting clarity.
- Search strategy quality/performance.
- Worker/cloud hardening and reliability.
- Observability depth and run traceability.
- Writeback safety and failure handling.
- Repository/module structure for clear ownership.

## 11. Execution modes
Intended modes:
- **Local mode**: development, validation, and deterministic replay.
- **External worker / cloud mode**: operational scale and remote execution.
- **Benchmark campaign mode**: repeated controlled runs for strategy/scoring comparison.

## 12. Observability philosophy
Observability is first-class, not optional. v2 should include:
- Structured JSON logs.
- Stable run identifiers (e.g., `runId`, `campaignId`, `chunkIndex`).
- Clear progress visibility for long-running search.
- Score and quality metrics for decision transparency.
- Failure taxonomy with actionable categories.
- Artifact trail for re-examination.

## 13. Validation philosophy
v2 correctness should be proven through layered validation:
- Parser fixtures covering known sheet patterns and malformed inputs.
- Edge-case snapshots for department-specific corner cases.
- Rule validation tests on hard constraints and blocking behavior.
- Scorer consistency checks (including score-direction invariants).
- Reproducibility checks across identical snapshot + seed runs.
- Local vs cloud parity checks on equivalent run requests.
- Shadow comparison against v1 behavior where appropriate.

## 14. Build order
Planned implementation sequence:
1. Docs.
2. Contracts.
3. Parser / normalizer.
4. Rule engine.
5. Scorer.
6. Solver.
7. Local execution.
8. Writer / artifacts.
9. Cloud worker.
10. Sheet integration.
11. Observability hardening.

## 15. Migration strategy
- Keep v1 live during v2 development.
- Build v2 in parallel with clear isolation.
- Use ICU/HD template as first proof case.
- Avoid early cutover; promote only after parity and reliability confidence.

## 16. Initial working decisions for first release
- Department templates are curated by maintainers for first release onboarding, not end-user self-serve.
- Routine variation within an approved template is mainly limited to roster period/dates, doctor list, and doctor count, plus operator-tuneable scorer component weights and the solver's `crFloor.manualValue` knob in first release (v1 parity for scorer weights; see `docs/scorer_contract.md` §15 and `docs/solver_contract.md` §17 for the full tuneable surface).
- Structural and mapping changes are not end-user configurable in first release and require maintainer-reviewed template updates. This includes slot/group structure, group-based eligibility declarations, and logical input/output mapping surfaces.
- Request meaning and request-effect changes are handled in the request semantics contract (or rebinding to a different contract version), not by silently restating semantics inside template-layer docs/artifacts.
- Allocation/search/scorer implementation changes are core-layer changes, not template-layer changes.
- The first normalized domain model covers minimum common allocation concepts for ICU/HD and near-term similar departments: roster period, dates, doctors, doctor groups, slot types, per-date slot demand, requests, blocking rules, and eligibility mappings. Scoring is critical, but this blueprint does not claim a closed first-release scoring-configuration contract; writeback targeting remains downstream adapter/result-contract scope (not normalized-core contract scope).
- The normalized model is independent of raw Google Sheets row/column layout, while template + sheet-adapter mappings handle department sheet specifics.
- Slot demand is modeled as required assignment count per date per slot type.
- Standby is normally represented as a slot type with its own demand/rules semantics (with any writeback mapping handled downstream), not as a separate solver mode, unless a future department proves otherwise.
- First shipped search strategy is seeded randomized search (in the same spirit as v1), prioritizing simplicity, reproducibility, explainability, and validation ease over sophistication.
- For ICU first release, operator-facing workflow should stay as close as practical to the current sheet experience, while internal compute normalizes away fixed row/column assumptions, merged-cell assumptions, and ICU-specific formatting quirks.
- For ICU/HD, parity with v1 means preserving hard-constraint behavior, main request semantics, operator-facing workflow, and acceptable writeback/output behavior; parity does not require identical internal architecture or implementation.

## 17. Assumptions / scope limits
- Current ICU sheet is the initial reference point.
- Near-term ICU/HD templates will likely remain highly similar, with changes mainly in dates and doctor names.
- Department onboarding remains curated by our team, not self-serve.
- First-release operator scope is a small, named monthly-rotation pilot per department: operators have generate-only access to the maintainer-owned template via an OAuth-gated launcher, and cannot author or modify template structure, mappings, or eligibility declarations.
- Leave/request legends are expected to be largely reusable across departments, even when templates declare them explicitly.
- Hard constraints are expected to be largely universal across departments; department-specific variation mainly sits in slot/group structure, group-based eligibility declarations, sheet mapping, request semantics binding choice, and minimal scoring stub presence.
- This blueprint intentionally stays high-level where contracts are not yet finalized.
