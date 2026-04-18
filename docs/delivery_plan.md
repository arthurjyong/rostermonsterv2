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
- **Status:** **Active** *(reopened 2026-04-18 for implementation delivery)*
- **Dependencies:** template/request/generation contract surfaces.
- **Exit criteria:** generation inputs, structural surfaces, operator edit boundaries, non-goals, and acceptance criteria are closed, and operator-ready ICU/HD sheet-shell generation is implemented for the empty-form use (new spreadsheet file or new tab in existing spreadsheet) with intended editable/protected behavior and practical validation in place.
- **Likely checkpoints:**
  - Close sheet-generation MVP boundary.
  - Align template artifact surfaces with generation needs.
  - Generation acceptance/handoff readiness.
  - Implement operator-ready sheet generation.

### M2 — Minimal local compute pipeline
- **Goal:** Stand up deterministic local parse/normalize/solve flow against closed contracts.
- **Why it matters:** Establishes executable core path before scale/orchestration.
- **Status:** Planned
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
- **Active milestone:** `Operator-ready request sheet generation`

This is active now because:
- M1 contract-closure checkpoints (C1/C2/C3) are complete, but no operator-usable sheet shell has actually been generated yet
- M1 is reopened in place so milestone closure aligns with real operator delivery, not contract closure alone
- implementation of the empty-form ICU/HD shell is the narrowest slice that unblocks immediate operator workflow

## 7. Checkpoint plan for the active milestone

### C1 — Close sheet-generation MVP boundary *(completed 2026-04-17)*
- Contract-closure checkpoint that fixed generation inputs, structural surfaces, allowed operator edits, editable/protected + validation boundary, explicit non-goals, and checkpoint acceptance framing.

### C2 — Align template artifact vs generation needs *(completed 2026-04-18)*
- Contract-closure checkpoint that aligned `docs/template_artifact_contract.md` and `docs/sheet_generation_contract.md` for first-release ICU/HD sheet-shell generation usage.

### C3 — Define generation acceptance/handoff readiness *(completed 2026-04-18)*
- Contract-closure checkpoint that locked the M1 implementation-ready checklist, declared the first allowed implementation slice, and declared explicit out-of-scope items to prevent scope drift during generation-slice start.

### C4 — Implement operator-ready sheet generation
- **Goal:** deliver an operator-usable ICU/HD request sheet shell consistent with the settled M1 generation contracts.
- **Why it exists:** C1/C2/C3 closed the contract boundary; an implementation slice is still required before M1 can be considered operator-delivered.
- **In scope:** template-driven ICU/HD shell generation for the empty-form use, both output modes (new spreadsheet file / new tab in an existing spreadsheet), locking/editable-surface/validation setup at a practical level, and reviewable operator-ready acceptance.
- **Out of scope:** parser/compute/solver/scorer work, writeback of computed rosters, orchestration/worker mechanics, benchmark hardening, broader multi-department generalization, and any long-term compute-core stack choice.
- **Dependencies:** C1/C2/C3 closure; `docs/sheet_generation_contract.md`, `docs/template_artifact_contract.md`, `docs/request_semantics_contract.md`.
- **Done criteria:** operators can generate the empty ICU/HD request sheet shell into either a new spreadsheet file or a new tab in an existing spreadsheet, with the intended editable/protected surfaces and practical validation behavior in place, reviewable against the C3 acceptance checklist.

## 8. Current active checkpoint
- **Active checkpoint:** `Implement operator-ready sheet generation`

Why this checkpoint is next:
- M1 contract surfaces are closed but no generated sheet has been produced for operator use
- this is the narrowest implementation slice that converts contract closure into an actual operator deliverable
- narrower than reopening M1 scope; broader than leaving M1 closed on paper only

What it must close:
- produce a working generated ICU/HD sheet shell consistent with settled M1 contracts
- support both output modes (new spreadsheet file, or new tab in an existing spreadsheet)
- apply intended locking/editable-surface/validation behavior at a practical level
- deliver a reviewable operator-ready acceptance against the existing C3 checklist

Docs expected to be touched during this checkpoint:
- `docs/delivery_plan.md`
- `docs/decision_log.md` (narrow implementation-stack decision)

What must remain untouched for now:
- parser/normalizer, compute-core, solver/scorer, writeback, and orchestration design
- long-term compute-core implementation stack decision
- broader roadmap/milestone redesign

## 9. Task list for the current checkpoint

### T1 — Record narrow implementation-stack decision for generation slice
- **Purpose:** capture the narrow decision that M1 generation is implemented in Google Apps Script targeting Google Sheets, without deciding the long-term compute-core stack.
- **Status:** Planned
- **Relevant files/docs:** `docs/decision_log.md`
- **Done condition:** decision log entry is recorded as Accepted with explicit narrow scope.

### T2 — Implement template-driven ICU/HD shell generation
- **Purpose:** generate the structural ICU/HD request sheet shell driven by the settled template/generation contract surfaces.
- **Status:** Planned
- **Relevant files/docs:** `docs/sheet_generation_contract.md`, `docs/template_artifact_contract.md`
- **Done condition:** generated sheet shell reflects declared structural surfaces for the empty-form ICU/HD case.

### T3 — Support both output modes (new spreadsheet file / new tab in existing spreadsheet)
- **Purpose:** let operators choose either destination without changing generated structural behavior.
- **Status:** Planned
- **Relevant files/docs:** `docs/sheet_generation_contract.md`
- **Done condition:** both output modes are usable and produce equivalent structural output.

### T4 — Apply locking / editable-surface / practical validation setup
- **Purpose:** apply intended editable/protected surfaces and practical validation on the generated shell so operator edits stay within contract-declared surfaces.
- **Status:** Planned
- **Relevant files/docs:** `docs/sheet_generation_contract.md`, `docs/template_artifact_contract.md`
- **Done condition:** generated shell exposes the intended editable regions and protects the rest at a practical level, with practical validation in place.

### T5 — Confirm operator-ready acceptance for empty-form use
- **Purpose:** confirm the generated shell is reviewable against the C3 acceptance checklist for the empty-form ICU/HD use.
- **Status:** Planned
- **Relevant files/docs:** `docs/delivery_plan.md`, `docs/sheet_generation_contract.md`
- **Done condition:** an operator can generate the empty ICU/HD form on demand and the result is accepted against the C3 checklist.

## 10. Explicitly deferred for now
- Solver implementation details.
- Scorer implementation details.
- Local run implementation mechanics.
- Writeback implementation mechanics.
- Worker/orchestrator mechanics.
- Benchmark hardening depth beyond milestone-level framing.
- Broad multi-department generalization beyond ICU/HD-first sequencing.

## 11. Recently completed checkpoints
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
- *(none — M1 was temporarily marked closed on 2026-04-18 but has since been reopened in place; see Section 6 and `docs/decision_log.md` D-0016.)*

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
This version reflects the 2026-04-18 reopen of M1 and is seeded with:
- active milestone `Operator-ready request sheet generation`
- active checkpoint `Implement operator-ready sheet generation`
- compact M1 implementation task list (T1–T5)
- explicit deferrals to prevent near-term drift into M2/M3/M4 scope
