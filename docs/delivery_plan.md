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
- **In scope:** generation inputs, generated structural surfaces, allowed operator edits, explicit non-goals, acceptance criteria.
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
- **Active checkpoint:** `Close sheet-generation MVP boundary`

Why this checkpoint is next:
- it closes the immediate ambiguity that can derail both planning and implementation sequencing
- it defines what must be true before generation work is considered operationally ready

What it must close:
- locked generation inputs
- locked generated structural surfaces
- locked allowed operator edits
- locked explicit non-goals
- locked acceptance criteria

Docs expected to be touched during this checkpoint:
- planning/guidance docs (`README.md`, `docs/roadmap.md`, `docs/delivery_plan.md`, `docs/decision_log.md`)
- only tightly bounded cross-reference consistency edits in contract docs if truly required

What must remain untouched for now:
- broad contract redesign
- implementation-level mechanics and code paths

## 9. Task list for the current checkpoint

### T1 — Lock generation inputs
- **Purpose:** finalize what inputs generation consumes for MVP scope.
- **Status:** Planned
- **Relevant files/docs:** `docs/sheet_generation_contract.md`, `docs/template_contract.md`, `docs/request_semantics_contract.md`
- **Done condition:** input surface is explicit, bounded, and consistent across referenced docs.

### T2 — Lock generated structural surfaces
- **Purpose:** define the exact generated structural shell expected for operator usage.
- **Status:** Planned
- **Relevant files/docs:** `docs/sheet_generation_contract.md`, `docs/template_contract.md`
- **Done condition:** generated structure boundaries are explicit and free from conflicting interpretations.

### T3 — Lock allowed operator edits
- **Purpose:** clarify which post-generation edits operators may perform within MVP boundaries.
- **Status:** Planned
- **Relevant files/docs:** `docs/sheet_generation_contract.md`, `docs/template_contract.md`
- **Done condition:** allowed vs disallowed edit classes are clearly documented.

### T4 — Lock explicit non-goals
- **Purpose:** prevent near-term scope expansion into non-MVP behavior.
- **Status:** Planned
- **Relevant files/docs:** `docs/delivery_plan.md`, `docs/roadmap.md`
- **Done condition:** non-goals are explicit and referenced in checkpoint acceptance framing.

### T5 — Define acceptance criteria
- **Purpose:** set objective closure conditions for the active checkpoint.
- **Status:** Planned
- **Relevant files/docs:** `docs/delivery_plan.md`, `docs/roadmap.md`, `docs/decision_log.md`
- **Done condition:** acceptance criteria are reviewable and sufficient for checkpoint sign-off.

## 10. Explicitly deferred for now
- Solver implementation details.
- Scorer implementation details.
- Local run implementation mechanics.
- Writeback implementation mechanics.
- Worker/orchestrator mechanics.
- Benchmark hardening depth beyond milestone-level framing.
- Broad multi-department generalization beyond ICU/HD-first sequencing.

## 11. Recently completed checkpoints
No prior delivery-plan checkpoints have yet been formally recorded in this document.

## 12. Change log for this delivery plan
- **2026-04-16:** Document created as the living execution guide.
- **2026-04-16:** Activated Milestone 1 (`Operator-ready request sheet generation`).
- **2026-04-16:** Activated Checkpoint 1 (`Close sheet-generation MVP boundary`).

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
- active checkpoint `Close sheet-generation MVP boundary`
- checkpoint tasks for inputs, structural surfaces, operator edits, non-goals, and acceptance criteria
- explicit deferrals to prevent near-term drift
