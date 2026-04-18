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
- **Goal:** Close a clear, reviewable MVP boundary for operator-ready request sheet generation.
- **Why it matters:** Immediate operational need; unblocks next request sheet cycle and anchors downstream work.
- **Status:** **Active**
- **Dependencies:** template/request/generation contract surfaces.
- **Exit criteria:** generation inputs, structural surfaces, operator edit boundaries, non-goals, and acceptance criteria are closed.
- **Likely checkpoints:**
  - Close sheet-generation MVP boundary.
  - Align template artifact surfaces with generation needs.
  - Generation acceptance/handoff readiness.

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
- operator workflow urgency requires a near-term request sheet path
- the next request sheet cycle needs a clear boundary quickly
- downstream implementation is safer once generation boundaries are closed

## 7. Checkpoint plan for the active milestone

### C1 — Close sheet-generation MVP boundary
- **Goal:** close the MVP planning/contract boundary for first operationally usable generation behavior.
- **Why it exists:** prevents scope creep and clarifies what “ready” means for milestone completion.
- **In scope:** generation inputs, generated structural surfaces, allowed operator edits, editable/protected surface and validation boundary, explicit non-goals, acceptance criteria.
- **Out of scope:** implementation mechanics, solver/scorer behavior, orchestration/runtime concerns.
- **Dependencies:** existing template/request/generation contract docs.
- **Done criteria:** boundary items are explicit, internally consistent, and reviewable across relevant docs.

### C2 — Align template artifact vs generation needs
- **Goal:** verify template artifact surfaces are sufficient and aligned for generation usage.
- **Why it exists:** avoid downstream mismatch between template declarations and generation expectations.
- **In scope:** cross-doc consistency checks and narrowly scoped clarification edits.
- **Out of scope:** broad redesign of template or request semantics contracts.
- **Dependencies:** C1 closure.
- **Done criteria:** no material ambiguity remains about template artifact fields required for generation.

### C3 — Define generation acceptance/handoff readiness
- **Goal:** establish handoff-ready acceptance framing for implementation work.
- **Why it exists:** implementation should begin from a closed, testable planning boundary.
- **In scope:** acceptance framing, handoff notes, readiness criteria.
- **Out of scope:** writing implementation tickets or introducing new process systems.
- **Dependencies:** C1 and C2 closure.
- **Done criteria:** implementation-facing teams can proceed without reopening milestone-level scope.

## 8. Current active checkpoint
- **Active checkpoint:** `Define generation acceptance/handoff readiness`

Why this checkpoint is next:
- C1 and C2 are formally closed with generation/template surfaces now aligned for ICU/HD first release
- remaining near-term risk is unclear handoff expectations for implementation start without reopening milestone scope

What it must close:
- define compact, implementation-facing acceptance conditions for generation handoff
- state what implementation can begin immediately under closed M1 scope
- capture final handoff notes from generation/template contracts without introducing implementation mechanics

Docs expected to be touched during this checkpoint:
- `docs/sheet_generation_contract.md`
- `docs/template_artifact_contract.md`
- `docs/delivery_plan.md` (status/coordination updates only)

What must remain untouched for now:
- broad contract redesign
- implementation-level mechanics and code paths

## 9. Task list for the current checkpoint

### T1 — Define generation handoff acceptance conditions
- **Purpose:** lock concise acceptance conditions that indicate generation-contract handoff readiness for implementation.
- **Status:** Planned
- **Relevant files/docs:** `docs/delivery_plan.md`, `docs/sheet_generation_contract.md`, `docs/template_artifact_contract.md`
- **Done condition:** acceptance conditions are explicit enough to start implementation without milestone-boundary reinterpretation.

### T2 — State implementation-start scope under closed M1 boundary
- **Purpose:** clarify what implementation work may begin now without reopening C1/C2 contract scope.
- **Status:** Planned
- **Relevant files/docs:** `docs/delivery_plan.md`
- **Done condition:** immediate implementation-start scope is explicit and milestone-consistent.

### T3 — Capture final contract-to-implementation handoff notes
- **Purpose:** summarize any final contract notes that implementation teams must observe while mechanics remain out of scope.
- **Status:** Planned
- **Relevant files/docs:** `docs/delivery_plan.md`, `docs/sheet_generation_contract.md`, `docs/template_artifact_contract.md`
- **Done condition:** handoff notes are compact, practical, and avoid introducing implementation procedures.

## 10. Explicitly deferred for now
- Solver implementation details.
- Scorer implementation details.
- Local run implementation mechanics.
- Writeback implementation mechanics.
- Worker/orchestrator mechanics.
- Benchmark hardening depth beyond milestone-level framing.
- Broad multi-department generalization beyond ICU/HD-first sequencing.

## 11. Recently completed checkpoints
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

## 12. Change log for this delivery plan
- **2026-04-16:** Document created as the living execution guide.
- **2026-04-16:** Activated Milestone 1 (`Operator-ready request sheet generation`).
- **2026-04-16:** Activated Checkpoint 1 (`Close sheet-generation MVP boundary`).
- **2026-04-17:** Closed Checkpoint 1 (`Close sheet-generation MVP boundary`) and recorded formal sign-off in this plan.
- **2026-04-17:** Activated Checkpoint 2 (`Align template artifact vs generation needs`) as current execution focus.
- **2026-04-18:** Closed Checkpoint 2 (`Align template artifact vs generation needs`) and recorded formal sign-off in this plan.
- **2026-04-18:** Activated Checkpoint 3 (`Define generation acceptance/handoff readiness`) as current execution focus.

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
This initial version is seeded with:
- active milestone `Operator-ready request sheet generation`
- active checkpoint `Define generation acceptance/handoff readiness`
- compact C3 starter tasks focused on generation handoff acceptance/readiness framing
- explicit deferrals to prevent near-term drift
