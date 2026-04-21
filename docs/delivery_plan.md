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

### M2 — Minimal local compute pipeline
- **Goal:** Stand up deterministic local parse/normalize/solve flow against closed contracts.
- **Why it matters:** Establishes executable core path before scale/orchestration.
- **Status:** **Active** *(milestone-level, pending checkpoint activation)*
- **Dependencies:** M1 complete; snapshot/parser/domain boundaries stable.
- **Exit criteria:** repeatable local run path with interpretable outputs for ICU/HD scenarios.
- **Likely checkpoints:** parser-normalizer implementation closure; minimal rule/scorer/solver integration; local run artifact basics.

### M3 — Safe result/output and writeback
- **Goal:** Define and implement safe output surfaces and writeback behavior.
- **Why it matters:** Operator trust depends on safe, clear result delivery.
- **Status:** Planned
- **Dependencies:** M2 complete; stable output/writeback contract surfaces.
- **Exit criteria:** controlled operator-safe writeback and explicit failure/unsatisfied-state handling.
- **Likely checkpoints:** output contract closure; writeback mapping validation; result safety checks.

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
- M1 (`Operator-ready request sheet generation`) closed on 2026-04-21 with operator-delivered ICU/HD sheet-shell generation in both output modes, against the C3 acceptance checklist
- M2 is the next milestone per `docs/roadmap.md`: establish a deterministic local parse → normalize → rule/scoring/solve execution path using the closed M1 contracts as upstream
- no M2 checkpoint has been activated yet; the first M2 checkpoint (`Parser/normalizer implementation closure`) will activate when parser work begins, at which point its task list will be seeded in §9

## 7. Checkpoint plan for the active milestone

M2's checkpoints follow the roadmap sequence. None are active yet; they will be formalized in §8/§9 as each is kicked off.

### C1 — Parser/normalizer implementation closure *(planned)*
- **Goal:** implement parser/normalizer against the settled `docs/parser_normalizer_contract.md` boundary so raw sheet snapshots lower into normalized domain model instances.
- **Why it exists:** first narrow slice of M2; unblocks rule/scorer/solver work downstream.
- **Dependencies:** M1 complete; `docs/snapshot_contract.md`, `docs/parser_normalizer_contract.md`, `docs/domain_model.md`.

### C2 — Minimal rule/scorer/solver integration *(planned)*
- **Goal:** wire a deterministic rule-engine + minimal solver + scorer pass over a normalized model produced by C1 output.
- **Dependencies:** C1 closure.

### C3 — Local run artifact packaging *(planned)*
- **Goal:** package local run outputs for basic reviewability.
- **Dependencies:** C2 closure.

## 8. Current active checkpoint
- **Active checkpoint:** *(none — between milestones)*

M1's final checkpoint (C4 — `Implement operator-ready sheet generation`) closed on 2026-04-21. M2's first checkpoint (`Parser/normalizer implementation closure`) is teed up in §7 but has not been activated. Activating it is a deliberate decision that seeds §8 and §9 together.

The "one active checkpoint" working rule from §2 is intentionally relaxed during milestone handoff; it re-applies as soon as M2 C1 is formally activated.

## 9. Task list for the current checkpoint

*(No active checkpoint; no task list. This section repopulates when M2 C1 is activated.)*

## 10. Explicitly deferred for now
- Solver implementation details.
- Scorer implementation details.
- Local run implementation mechanics.
- Writeback implementation mechanics.
- Worker/orchestrator mechanics.
- Benchmark hardening depth beyond milestone-level framing.
- Broad multi-department generalization beyond ICU/HD-first sequencing.

## 11. Recently completed checkpoints
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
- **2026-04-21:** Activated Milestone 2 (`Minimal local compute pipeline`) at milestone level; M2 checkpoints listed but none yet activated (see §7 and §8).

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
This version reflects the 2026-04-21 closure of M1 on operator delivery and is seeded with:
- active milestone `Minimal local compute pipeline` (M2)
- no active checkpoint; M2 C1 (`Parser/normalizer implementation closure`) teed up but not yet activated
- closed-milestone trail for M1 in §11 with C4 sign-off note and D-0019/D-0020 anchors
- explicit deferrals retained to prevent near-term drift into M3/M4/M5 scope
