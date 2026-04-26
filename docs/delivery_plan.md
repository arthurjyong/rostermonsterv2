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
- **Why it matters:** Immediate operational need; unblocks the next request sheet cycle and anchors downstream work.
- **Status:** **Completed** *(closed 2026-04-21 on operator delivery; see §11 and D-0019)*
- **Dependencies:** template/request/generation contract surfaces.
- **Exit criteria:** generation inputs, structural surfaces, operator edit boundaries, non-goals, and acceptance criteria are closed, and operator-ready ICU/HD sheet-shell generation is implemented for the empty-form use (new spreadsheet file or new tab in existing spreadsheet) with intended editable/protected behavior and practical validation in place.
- **Likely checkpoints:**
  - Close sheet-generation MVP boundary. *(C1, closed 2026-04-17)*
  - Align template artifact surfaces with generation needs. *(C2, closed 2026-04-18)*
  - Generation acceptance/handoff readiness. *(C3, closed 2026-04-18)*
  - Implement operator-ready sheet generation. *(C4, closed 2026-04-21)*

### M1.1 — Operator-facing launcher *(addendum to M1)*
- **Goal:** Provide a narrow operator-facing launcher so named monthly-rotation pilot operators can invoke empty ICU/HD request-sheet generation without running Apps Script by hand.
- **Why it matters:** Closes M1's operator-facing story end-to-end; turns a maintainer-only generator into a pilot-usable launcher without expanding M1's compute scope.
- **Status:** **Completed** *(closed 2026-04-22 on hands-on validation; addendum milestone; M1 itself stays Completed, not reopened; see §11)*
- **Dependencies:** M1 complete; `docs/sheet_generation_contract.md` §12 (launcher surface).
- **Exit criteria:** a non-maintainer test operator can, after one-time Google consent, load the launcher URL, submit the form, and receive a working generated sheet or tab in either output mode, validated hands-on.
- **Likely checkpoints:**
  - Implement operator launcher web app.
- **Addendum framing:** M1.1 is derivative of M1's operator-facing surface, not a compute-line milestone. Addendum numbering convention (`M<parent>.<n>` with integer `n`, no nested decimals) is recorded in D-0021.

### M2 — Minimal local compute pipeline
- **Goal:** Stand up deterministic local parse/normalize/solve flow against closed contracts.
- **Why it matters:** Establishes executable core path before scale/orchestration.
- **Status:** Active *(activated at milestone level on 2026-04-22 after M1.1 closure; first checkpoint to be scoped separately — see §8)*
- **Dependencies:** M1 complete; snapshot/parser/domain boundaries stable.
- **Exit criteria:** repeatable local run path with interpretable outputs for ICU/HD scenarios.
- **Likely checkpoints:** parser-normalizer implementation closure; minimal rule/scorer/solver integration; local run artifact basics.

### M3 — Safe result/output and writeback
- **Goal:** Define and implement safe output surfaces and writeback behavior.
- **Why it matters:** Operator trust depends on safe, clear result delivery.
- **Status:** Planned
- **Dependencies:** M2 complete; stable output/writeback contract surfaces.
- **Exit criteria:** controlled operator-safe writeback and explicit failure/unsatisfied-state handling.
- **Likely checkpoints:**
  - Writeback contract closure (drafted scope-ahead in this PR; see `docs/writeback_contract.md` and D-0031; remains the natural M3 C1 once M3 activates).
  - Writeback mapping validation; result safety checks.

### M4 — Parallel operational search and orchestration
- **Goal:** Add reliable external/parallel execution without changing core compute semantics.
- **Why it matters:** Needed for operational reliability and throughput.
- **Status:** Planned
- **Dependencies:** M3 complete; stable local semantics.
- **Exit criteria:** traceable external execution lifecycle with guarded retries/failure handling.
- **Likely checkpoints:** execution envelope boundaries; orchestration mechanics; idempotence/retry guardrails.

### M5 — Observability and benchmark hardening
- **Goal:** Harden diagnostics, benchmark workflow, and reliability posture.
- **Why it matters:** Long-term confidence requires measurable, repeatable behavior.
- **Status:** Planned
- **Dependencies:** M4 complete; stable execution/output surfaces.
- **Exit criteria:** practical observability coverage and benchmark baselines for regression control.
- **Likely checkpoints:** event/log surface hardening; benchmark campaign baselines; reliability hardening passes.

## 6. Current active milestone
- **Active milestone:** `Minimal local compute pipeline` (M2)

This is active now because:
- M1 (`Operator-ready request sheet generation`) closed on 2026-04-21 and M1.1 (`Operator-facing launcher`) closed on 2026-04-22, so the operator-facing request-sheet story is complete end-to-end; see §11
- M2 was returned to Planned while M1.1 was active under the one-active-milestone rule and was activated at milestone level after M1.1 closure, mirroring the 2026-04-21 "activate at milestone level, checkpoint to follow" pattern
- M2 C1 (`Rule engine + scorer + solver contract closure`) has since been scoped and activated as the first M2 checkpoint on 2026-04-23; see §7 and §8

## 7. Checkpoint plan for the active milestone

M2 (`Minimal local compute pipeline`) has the following declared checkpoint plan:
- **C1 — Rule engine + scorer + solver contract closure.** *(closed 2026-04-23 → 2026-04-25 as PR #63 + PR #64 + their post-merge audit follow-ups; see §11)* Locked the three interlocking contract boundaries (rule engine, scorer, solver) plus supporting updates (future-work entries, decision-log entries D-0024..D-0029, blueprint §16 clarifying patch).
- **C2 — Selector contract closure.** *(active; see §8)* Lock the selector-stage contract boundary (`docs/selector_contract.md`) plus supporting updates (future-work entries, decision-log entry D-0030, delivery-plan updates) so the third pipeline stage named in D-0027 has a normative home and downstream implementation work rests on fixed boundaries. No executable code lands in C2; it is docs-only contract closure.
- Subsequent M2 checkpoints remain candidate-ordered from §5 (parser/normalizer implementation closure; minimal rule/scorer/solver integration; local run artifact basics) and will be scoped individually after C2 closes.

## 8. Current active checkpoint
- **Active checkpoint:** `Selector contract closure` (M2 C2)

M2 C2 was activated on 2026-04-25 and is the current execution focus. It is a docs-only checkpoint that closes the selector-stage contract boundary deferred by D-0027 to a subsequent checkpoint after M2 C1 wrapped up. Closing the selector contract here gives the three-stage `solver → scorer → selector` pipeline a complete contract surface before any implementation work begins, and it operationalizes D-0026 sub-decision 8 (selector retroactively populates `TrialBatchResult` best-candidate fields). The parser/normalizer implementation closure originally nominated as the likely first M2 candidate in §5 remains re-sequenced behind contract closure for the same reason it was sequenced behind C1: closing the compute-pipeline contract boundaries first gives subsequent implementation checkpoints fixed surfaces to build against.

## 9. Task list for the current checkpoint

M2 C2 — `Selector contract closure` (active).

- **T1 — Draft `docs/selector_contract.md`.** Normative selector boundary: pure-function public surface with `(scoredCandidateSet, retentionMode, runEnvelope, selectorStrategyId, selectorStrategyConfig) → FinalResultEnvelope` shape; `AllocationResult` success branch and `UnsatisfiedResultEnvelope` failure branch; pluggable strategy interface mirroring the solver's `StrategyDescriptor` pattern; first-release `HIGHEST_SCORE_WITH_CASCADE` strategy with `pointBalanceGlobal` → `crReward` → lowest `candidateId` cascade; retention modes `BEST_ONLY` (default) and `FULL` (operator opt-in) with per-mode output behavior; sidecar artifacts `candidates_summary.csv` and `candidates_full.json` cross-referenced by `candidateId` and embedding `runId`; no-sidecar-on-failure rule; run envelope and `(runId, candidateId)` traceability identity; selector-owned retroactive population of per-batch best-candidate field plus per-batch score-distribution summary; byte-identical determinism within a single implementation on a single platform; sidecar `schemaVersion: 1`. *(Will be Done when commit lands.)*
- **T2 — Append `docs/decision_log.md` D-0030.** Selector architecture contract decision enumerating the ten locked sub-decisions (pluggable strategy interface, `HIGHEST_SCORE_WITH_CASCADE` first release, retention modes, per-mode output shapes, sidecar file shapes, `UnsatisfiedResult` handling, run envelope and traceability, `TrialBatchResult` retroactive population, full-set ingest, additive strategy registry). Cross-references D-0024..D-0027 as the M2 C1 architectural anchors and operationalizes D-0026 sub-decision 8. *(Done with commit.)*
- **T3 — Update `docs/future_work.md`.** Update FW-0013 to cross-reference `docs/selector_contract.md` and mark Phase 1 as locked-by-contract (Phase 2 — `TOP_K`, `FULL_WITH_DIAGNOSTICS`, per-batch artifact export — remains deferred to benchmark-campaign work). Append FW-0018 — Streaming-selector implementation — with trigger conditions and related-surfaces cross-references. *(Done with commit.)*
- **T4 — Update `docs/delivery_plan.md`.** Update §7 (add C2 to the checkpoint plan and mark C1 closed), §8 (switch active checkpoint to C2), §9 (this task list), §11 (record M2 C1 sign-off as recently completed), §12 (change-log entries for 2026-04-25), §15 (initial-seed paragraph refresh). *(Done with commit.)*

C2 closes when all four tasks are Done and the branch PR merges. Sign-off note is recorded in §11 at that point.

## 10. Explicitly deferred for now
- Solver implementation details.
- Scorer implementation details.
- Local run implementation mechanics.
- Writeback implementation mechanics. The writeback contract is now drafted scope-ahead per D-0031 (`docs/writeback_contract.md`); implementation mechanics remain deferred until M3 activates.
- Worker/orchestrator mechanics.
- Benchmark hardening depth beyond milestone-level framing.
- Broad multi-department generalization beyond ICU/HD-first sequencing.
- Public or open-signup operator access for the launcher; first-release scope is named monthly-rotation pilot operators only, gated via GCP OAuth consent-screen Test Users.
- In-app operator allowlist / role model inside the launcher; access gating stays external to the app for pilot scope.
- Operator-editable template or structural mapping; template stays maintainer-owned.
- Persisted per-operator state beyond Google's OAuth session.
- Alternative launcher platforms (for example a static page over the Apps Script API Executable); the pilot sticks with Apps Script Web App per D-0022.

## 11. Recently completed checkpoints
- **M2 C1 — Rule engine + scorer + solver contract closure** *(closed 2026-04-25)*
  - Closed the three interlocking M2 compute-pipeline contract boundaries: `docs/rule_engine_contract.md` (stateless surface, full-violation canonical ordering, scoped fixed-assignment handling, equivalence-test discipline for future non-stateless implementations), `docs/scorer_contract.md` (pure-function surface, required component breakdown, `HIGHER_IS_BETTER` direction-guard invariant, `crReward` diminishing-marginal-utility property, scorer-owned soft-effect reading, operator-tuneable weight surface, streaming/delta scoring as permitted optimization), and `docs/solver_contract.md` (scoring-blind surface, strategy-pluggable interface with additive extension clause, `SEEDED_RANDOM_BLIND` first-release composite, `crFloor` computation, whole-run failure on any unfillable slot, `maxCandidates`-only termination, byte-identical determinism, retention moved downstream to the selector stage).
  - Locked architectural decisions: D-0024 (rule engine contract), D-0025 (scorer contract), D-0026 (solver contract), D-0027 (pipeline-stage separation `solver → scorer → selector`), D-0028 (operator-tuneable surface broader than blueprint §16), D-0029 (`unitIndex` operational-equivalence — same-`SlotType` units are equivalent in doctor admissibility and baseline workload weight, with per-unit occupancy via `UNIT_ALREADY_FILLED` explicitly carved out).
  - Delivered as PR #63 (rule-engine + scorer + solver contracts plus supporting future-work / decision-log / blueprint patches) and PR #64 (M2 C1 follow-ups closing post-merge audit flags: `unitIndex` equivalence narrowing to doctor-admissibility per D-0029 sub-decision 1, retention opt-in clarifications, byte-identical parity wording propagation, contract fixes into FW-0010 and FW-0012).
  - Task closure status: T1 Done, T2 Done, T3 Done, T4 Done.
  - Main affected surfaces: `docs/rule_engine_contract.md` (new), `docs/scorer_contract.md` (new), `docs/solver_contract.md` (new), `docs/decision_log.md` (D-0024..D-0029 appended), `docs/future_work.md` (FW-0003..FW-0017 appended), `docs/blueprint.md` §16 (clarifying patch), `docs/domain_model.md` §10.2 (D-0029 equivalence note), `docs/delivery_plan.md` (active-checkpoint and change-log updates).

### M2 C1 sign-off note
M2 C1 is complete. The three M2 compute-pipeline contract boundaries (rule engine, scorer, solver) are now normative and consistent with one another and with the surrounding domain-model / blueprint anchors. The pipeline-stage separation `solver → scorer → selector` (D-0027) is committed; D-0026 sub-decision 8 (selector retroactively populates `TrialBatchResult` best-candidate fields) is named but its operationalization is deferred to M2 C2 (selector contract closure), now active per §8. PR #64's post-merge audit follow-ups closed the consistency-propagation flags surfaced by Codex review across the M2 C1 surfaces, leaving the C1 contract set self-consistent at the time of M2 C2 activation.

- **M1.1 C1 — Implement operator launcher web app** *(closed 2026-04-22)*
  - Delivered the M1.1 operator-facing launcher: Apps Script web-app (`doGet()` HTML form + `submitLauncherForm` wiring) against the existing `generateIntoNewSpreadsheet` / `generateIntoExistingSpreadsheet` entrypoints, shared spreadsheet-reference normalization (URL or bare ID) per `docs/sheet_generation_contract.md` §12.5, deployed at a stable `/exec` behind the operator-facing `https://tinyurl.com/cghicuhdlauncherv1` redirect with GCP OAuth consent-screen Test Users curated for the pilot operators.
  - Auto-share of newly-created spreadsheets to "anyone with the link (Editor)" landed during C1 as additive operational polish on top of T1–T4; the directional decision, the three-attempt sequence (`DriveApp` under `drive.file` → `DriveApp` under full `drive` → Drive Advanced Service v3 under `drive.file`), and the additive response-field surface (`autoShared`, `autoShareError`) are recorded in **D-0023**. No contract structural change was required — the additive fields sit within the `docs/sheet_generation_contract.md` §12 launcher surface already described there.
  - Verified end-to-end through the non-maintainer Test-User consent + generation path on a separate Google account and device; both output modes (new spreadsheet file, new tab in existing spreadsheet) exercised successfully, with negative-case input handling confirmed via an out-of-range 2027 request date. Pilot operator self-report independently confirms the end-to-end flow; pilot operators were not pushed through a recorded demo to avoid forcing OAuth consent for a maintainer-authored Test-User app.
  - Task closure status: T1 Done, T2 Done, T3 Done, T4 Done.
  - Main affected surfaces: `apps_script/m1_sheet_generator/` (launcher module, HTML, README); `docs/sheet_generation_contract.md` §12 launcher surface; no authoritative contract changes beyond the §12 addendum already in place.

### M1.1 C1 sign-off note
M1.1 C1 is complete. The operator-facing launcher delivers pilot-usable empty-form ICU/HD request-sheet generation in both output modes, with the non-maintainer OAuth consent path validated hands-on on a separate Google account and device. Pilot operator self-report independently confirms the end-to-end flow works; pilot operators were not pushed through a recorded demo to avoid forcing consent for a maintainer-authored Test-User app, consistent with the first-release access model in D-0022. M1.1's stated exit criteria are met and the launcher is the current pilot-operator entrypoint to ICU/HD request-sheet generation.

- **C4 — Implement operator-ready sheet generation** *(closed 2026-04-21)*
  - Delivered the ICU/HD request sheet shell end-to-end through Google Apps Script in `apps_script/m1_sheet_generator/`, covering both output modes (new spreadsheet file, new tab in existing spreadsheet).
  - Applied whole-sheet protection restricted to the script owner with unprotected exceptions for operator-editable surfaces (doctor-name cells, request-entry cells, call-point cells, lower-shell assignment cells) and warning-only regex validation on request-entry cells.
  - Verified against the C3 acceptance checklist for an operator-owned May 2026 cycle (CGH ICU/HD Call, 2026-05-04 to 2026-06-01, 9/6/7 manpower) via `clasp run` execution against a user-managed GCP project.
  - Operator-facing operational lesson recorded as D-0020: `clasp run` requires both (a) GCP OAuth consent-screen scope allowlist and (b) `clasp login --use-project-scopes --include-clasp-scopes`.
  - Task closure status: T1 Done, T2 Done, T3 Done, T4 Done, T5 Done.
  - Main affected surfaces: `apps_script/m1_sheet_generator/` (code + README); no authoritative contract changes required.

### C4 sign-off note
C4 is complete. M1 is now delivered on operator terms, not just contract closure: the generator produces an operator-usable ICU/HD request sheet shell against settled M1 contracts, in both output modes, with intended editable/protected surfaces and practical validation in place, and has been exercised hands-on against an operator-owned May 2026 spreadsheet.

- **C3 — Define generation acceptance/handoff readiness** *(closed 2026-04-18)*
  - Locked M1 implementation-ready checklist for ICU/HD first-release generation handoff without reopening C1/C2.
  - Declared the first allowed implementation slice (template read + operator inputs + shell generation + output-mode support + practical locking/validation).
  - Declared explicit out-of-scope items to prevent parser/compute/writeback/orchestration/benchmark scope drift during generation-slice start.
  - Task closure status: T1 Done, T2 Done, T3 Done.
  - Main affected docs: `docs/delivery_plan.md`.

### C3 sign-off note
C3 is complete. M1 generation boundary is now implementation-handoff ready: acceptance assumptions, immediate generation-slice start scope, out-of-scope guardrails, and final contract-to-implementation notes are explicit and sufficient for execution without reopening milestone-level scope.

- **C2 — Align template artifact vs generation needs** *(closed 2026-04-18)*
  - Closed remaining cross-doc alignment between `docs/template_artifact_contract.md` and `docs/sheet_generation_contract.md`, including first-release visible title/header generated-surface alignment.
  - Confirmed ICU/HD first-release combined-shell generation declarations remain consistency-aligned and non-redesign.
  - Task closure status: T1 Done, T2 Done, T3 Done.
  - Main affected docs: `docs/template_artifact_contract.md`, `docs/sheet_generation_contract.md`, `docs/delivery_plan.md`.

### C2 sign-off note
C2 is complete. Template artifact and generation contract surfaces are now sufficiently aligned for ICU/HD first-release sheet-shell generation usage, with no material remaining ambiguity requiring checkpoint-level redesign before C3 handoff-readiness framing.

- **C1 — Close sheet-generation MVP boundary** *(closed 2026-04-17)*
  - Closed generation inputs, generated structural surfaces, allowed operator edits, editable/protected + validation boundary, explicit non-goals, and acceptance framing at contract/planning level.
  - Task closure status: T1 Done, T2 Done, T3 Done, T4 Done, T5 Done, T6 Done.
  - Main affected docs: `docs/sheet_generation_contract.md`, `docs/delivery_plan.md`.

### C1 sign-off note
C1 is complete. The sheet-generation MVP boundary is now closed for execution: generation inputs, structural surfaces, allowed operator edits, editable/protected + validation expectations, explicit non-goals, and checkpoint acceptance framing are sufficiently fixed to proceed to C2 without reopening milestone-level scope.

### Recently completed milestones
- **M1.1 — Operator-facing launcher** *(closed 2026-04-22)*
  - Closed on hands-on validation via M1.1 C1 against the M1.1 exit criteria. The non-maintainer Test-User consent + generation path was exercised on a separate Google account and device across both output modes, and pilot operator self-report independently confirms the end-to-end flow. Addendum-milestone framing preserved: M1 itself was not reopened; see D-0021 for the addendum convention and D-0022 for the launcher architecture. Auto-share additive operational polish captured in D-0023.
- **M1 — Operator-ready request sheet generation** *(closed 2026-04-21)*
  - Closed on operator delivery via C4, against settled contract surfaces fixed in C1/C2/C3. See D-0019 for the formal closure decision and D-0020 for the operator-facing clasp OAuth operational lesson surfaced during M1 execution.

## 12. Change log for this delivery plan
- **2026-04-16:** Document created as the living execution guide.
- **2026-04-16:** Activated Milestone 1 (`Operator-ready request sheet generation`).
- **2026-04-16:** Activated Checkpoint 1 (`Close sheet-generation MVP boundary`).
- **2026-04-17:** Closed Checkpoint 1 (`Close sheet-generation MVP boundary`) and recorded formal sign-off in this plan.
- **2026-04-17:** Activated Checkpoint 2 (`Align template artifact vs generation needs`) as current execution focus.
- **2026-04-18:** Closed Checkpoint 2 (`Align template artifact vs generation needs`) and recorded formal sign-off in this plan.
- **2026-04-18:** Activated Checkpoint 3 (`Define generation acceptance/handoff readiness`) as current execution focus.
- **2026-04-18:** Closed Checkpoint 3 (`Define generation acceptance/handoff readiness`) with explicit M1 implementation-ready checklist, allowed first implementation slice, out-of-scope guardrails, and contract-to-implementation handoff notes.
- **2026-04-18:** Closed Milestone 1 (`Operator-ready request sheet generation`) and activated Milestone 2 (`Minimal local compute pipeline`).
- **2026-04-18:** Seeded M2 active checkpoint (`Parser/normalizer implementation closure`) with narrow parser-first task framing.
- **2026-04-18:** Reopened Milestone 1 in place so milestone closure aligns with operator delivery rather than contract closure alone; returned Milestone 2 to Planned.
- **2026-04-18:** Activated Checkpoint 4 (`Implement operator-ready sheet generation`) as the current M1 implementation checkpoint; seeded compact task list T1–T5.
- **2026-04-21:** Closed Checkpoint 4 (`Implement operator-ready sheet generation`) with T1–T5 Done; verified the generated shell against the C3 acceptance checklist against an operator-owned May 2026 cycle.
- **2026-04-21:** Closed Milestone 1 (`Operator-ready request sheet generation`) on operator delivery; see D-0019.
- **2026-04-21:** Activated Milestone 2 (`Minimal local compute pipeline`) at milestone level; M2 checkpoints listed but none yet activated.
- **2026-04-21:** Activated Milestone 1.1 (`Operator-facing launcher`) as an addendum to closed Milestone 1; returned Milestone 2 to Planned under the one-active-milestone rule. See D-0021 (addendum-milestone convention) and D-0022 (launcher architecture).
- **2026-04-21:** Activated Checkpoint 1 (`Implement operator launcher web app`) as the M1.1 execution focus; seeded compact task list T1–T4.
- **2026-04-22:** Reconciled §9 C1 task status against shipped code (T1/T2/T3 Done, T4 remains the only pending gate) and captured the auto-share additive scope (D-0023) that landed during C1 without retroactively inserting new tasks. Reconciliation is documentation-only; C1 stays active pending T4 sign-off.
- **2026-04-22:** Closed Task T4 (`Verify end-to-end with a non-maintainer test operator`) on hands-on validation of the non-maintainer Test-User consent + generation path across both output modes on a separate Google account and device, with pilot operator self-report as independent confirmation and a negative-case 2027 request-date check.
- **2026-04-22:** Closed Checkpoint 1 (`Implement operator launcher web app`) under M1.1 with T1–T4 Done; sign-off recorded in §11.
- **2026-04-22:** Closed Milestone 1.1 (`Operator-facing launcher`) on hands-on validation; see §11.
- **2026-04-22:** Activated Milestone 2 (`Minimal local compute pipeline`) at milestone level; first checkpoint to be scoped separately (§8), mirroring the 2026-04-21 "activate at milestone level, checkpoint to follow" pattern.
- **2026-04-23:** Activated M2 Checkpoint 1 (`Rule engine + scorer + solver contract closure`) as the current execution focus; seeded compact task list T1–T4 (T1/T2/T3 already Done on-branch; T4 in progress). C1 is docs-only contract closure and does not itself ship executable code.
- **2026-04-25:** Closed M2 Checkpoint 1 (`Rule engine + scorer + solver contract closure`) on operator audit and merge of PR #63 + PR #64; sign-off recorded in §11. Locked architectural decisions span D-0024..D-0029.
- **2026-04-25:** Activated M2 Checkpoint 2 (`Selector contract closure`) as the current execution focus; seeded compact task list T1–T4. C2 is docs-only contract closure and does not itself ship executable code; it operationalizes D-0026 sub-decision 8 (selector retroactively populates `TrialBatchResult` best-candidate fields) and locks the selector-stage boundary deferred by D-0027 sub-decision 2.
- **2026-04-26:** Drafted writeback contract (`docs/writeback_contract.md`) scope-ahead of M3 activation; recorded D-0031 with all eleven sub-decisions; appended FW-0019..FW-0023 for deferred richer-mode surfaces. During PR #66 codex review, surfaced a contract-seam consistency gap between the writeback contract's required `runEnvelope.sourceSpreadsheetId` / `runEnvelope.sourceTabName` and the selector contract v1's required-fields list; resolved by bumping `docs/selector_contract.md` from v1 to v2 with both fields added to §9 item 3 (D-0032). Selector compliance under v2 implies writeback input compatibility on the source-sheet-identity surface. Active milestone (M2) and active checkpoint state (M2 C2 — still the active checkpoint per §8; the selector v2 bump lands inside the still-active checkpoint rather than after sign-off) unchanged; no new active checkpoint added; M3 stays `Planned`.
- **2026-04-26:** Polish sweep across the M2 contract surfaces and the writeback scope-ahead contract resolving wording-only consistency findings from a self-audit pass: stale `docs/solver_contract.md` §13 anchor in `docs/scorer_contract.md` §16 corrected to §6/§11.1 (the actual scoring-blind anchors); stale "(not yet created)" qualifier in FW-0016 dropped with selector anchors pinned (`docs/selector_contract.md` §13, §21); "additive" misnomer in `docs/writeback_contract.md` §9 item 1 corrected to "required per selector v2 §9 item 3" (matching the §4/§18/§20/§23 wording, since selector §16.3 reserves "additive" for optional-additive only); rule_engine §6 / scorer §6 boundary blocks tightened so scorer/selector are framed as consuming the solver's `CandidateSet` per the D-0027 three-stage separation rather than reading directly from rule engine or pairing with a separate retention-policy stage; selector §11 strategy-descriptor framing notes the deliberate `selectorStrategyId` (vs solver's `strategyId`) namespacing; writeback §6.2 acknowledges the §11.1 wall-clock carve-out named in §9 normative properties. No contract semantics change. Active milestone (M2) and active checkpoint state (M2 C2 — polish lands inside the still-active checkpoint per the same-day selector v2 precedent) unchanged; no new active checkpoint added; M3 stays `Planned`.

## 13. Relationship to other repo docs
- `README.md` = front door orientation.
- `docs/blueprint.md` = stable architecture truth.
- `docs/roadmap.md` = milestone-level delivery order.
- `docs/delivery_plan.md` = active execution guide.
- `docs/decision_log.md` = accepted directional decisions.
- Contract docs = normative technical boundary definitions.

## 14. Maintenance rules for this document
- Keep exactly one active milestone unless there is a deliberate exception.
- Keep exactly one active checkpoint unless there is a deliberate exception.
- Update this document whenever execution focus changes.
- Do not duplicate normative contract wording here.
- Do not turn this document into a full issue tracker.
- If a task does not support the active checkpoint, it likely does not belong here.

## 15. Initial seed content
This version reflects the 2026-04-25 activation of M2 C2 (`Selector contract closure`) on top of the 2026-04-25 closure of M2 C1 (`Rule engine + scorer + solver contract closure`) and the 2026-04-22 closure of M1.1 (`Operator-facing launcher`), and is currently in the following state:
- active milestone `Minimal local compute pipeline` (M2)
- active checkpoint `Selector contract closure` (M2 C2), a docs-only contract-closure checkpoint covering the selector contract draft (`docs/selector_contract.md`) plus supporting updates to `docs/decision_log.md` (D-0030), `docs/future_work.md` (FW-0013 cross-reference + new FW-0018), and this delivery plan
- closed-checkpoint trail for M2 C1 in §11 (sign-off note included), anchored by D-0024..D-0029 across the rule-engine / scorer / solver contracts and the `unitIndex` doctor-admissibility equivalence
- closed-milestone trail for M1 (C1–C4 with C4 sign-off note) and M1.1 (C1 with sign-off note) in §11, with D-0019/D-0020/D-0021/D-0022/D-0023 anchors
- explicit deferrals retained from the M1.1 scope (public signup, in-app allowlist, operator-editable template, persisted per-operator state, alternative launcher platforms)
