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
- **Status:** Completed *(closed 2026-04-18)*
- **Dependencies:** template/request/generation contract surfaces.
- **Exit criteria:** generation inputs, structural surfaces, operator edit boundaries, non-goals, and acceptance criteria are closed.
- **Likely checkpoints:**
  - Close sheet-generation MVP boundary.
  - Align template artifact surfaces with generation needs.
  - Generation acceptance/handoff readiness.

### M2 — Minimal local compute pipeline
- **Goal:** Stand up deterministic local parse/normalize/solve flow against closed contracts.
- **Why it matters:** Establishes executable core path before scale/orchestration.
- **Status:** **Active**
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
- **Active milestone:** `Minimal local compute pipeline`

This is active now because:
- M1 sheet-generation contract boundary and handoff readiness are complete
- parser/normalize/solve local execution is the next dependency-gated milestone
- local deterministic execution now becomes the safest narrow implementation focus

## 7. Checkpoint plan for the active milestone

### C1 — Parser/normalizer implementation closure
- **Goal:** implement parser/normalizer behavior against the already-settled ICU/HD contracts.
- **Why it exists:** establishes the first executable M2 slice with deterministic contract adherence.
- **In scope:** parser/normalizer implementation, baseline fixtures, and contract-consistent outputs/issues.
- **Out of scope:** scoring/search optimization, writeback behavior, orchestration/runtime envelopes.
- **Dependencies:** M1 completion; `docs/parser_normalizer_contract.md`, `docs/snapshot_contract.md`, `docs/domain_model.md`.
- **Done criteria:** parser/normalizer path is executable and contract-consistent for baseline ICU/HD cases.

### C2 — Minimal rule/scorer/solver integration
- **Goal:** integrate minimal rule/scorer/solver flow on top of parser/normalizer outputs.
- **Why it exists:** converts parser-only execution into a constrained end-to-end local compute path.
- **In scope:** narrow integration needed for a deterministic first local compute pass.
- **Out of scope:** orchestration/worker behavior, writeback/output application hardening, benchmark expansion.
- **Dependencies:** C1 closure.
- **Done criteria:** local runs can produce valid candidate outcomes (or explicit unsatisfied states) with interpretable scoring direction.

### C3 — Local run artifact basics
- **Goal:** establish minimal local run artifact/output basics for reviewability.
- **Why it exists:** keeps M2 outputs inspectable before later safety/writeback/orchestration milestones.
- **In scope:** minimal local run outputs and diagnostics sufficient for implementation review.
- **Out of scope:** production-grade observability hardening and benchmark campaigns.
- **Dependencies:** C2 closure.
- **Done criteria:** local runs emit basic, reviewable artifacts that support repeatable ICU/HD-first validation.

## 8. Current active checkpoint
- **Active checkpoint:** `Parser/normalizer implementation closure`

Why this checkpoint is next:
- M1 is now closed with C1/C2/C3 complete and handoff-ready
- M2 needs a narrow first implementation checkpoint anchored to existing parser/normalizer contracts

What it must close:
- produce parser/normalizer implementation behavior consistent with settled contracts
- keep local compute scope narrow and deterministic for first executable M2 slice
- avoid reopening M1 generation boundary work

Docs expected to be touched during this checkpoint:
- `docs/parser_normalizer_contract.md`
- `docs/delivery_plan.md`

What must remain untouched for now:
- broad architecture redesign
- M1 generation contract boundary reopening

## 9. Task list for the current checkpoint

### T1 — Implement parser/normalizer against settled contract boundary
- **Purpose:** start M2 with a narrow implementation path that adheres to existing parser/normalizer contract expectations.
- **Status:** Planned
- **Relevant files/docs:** `docs/parser_normalizer_contract.md`, `docs/domain_model.md`, `docs/snapshot_contract.md`
- **Done condition:** parser/normalizer implementation can produce contract-consistent outputs for baseline ICU/HD fixtures.

### T2 — Establish minimal deterministic local run envelope (parser-first)
- **Purpose:** run parser/normalizer locally in a repeatable way before integrating broader rule/scorer/solver behavior.
- **Status:** Planned
- **Relevant files/docs:** `docs/delivery_plan.md`
- **Done condition:** local parser/normalizer runs are repeatable with interpretable success/failure outcomes.

### T3 — Preserve M2 scope discipline for first executable slice
- **Purpose:** keep initial M2 work bounded to parser/normalizer + deterministic local path without drifting into later milestones.
- **Status:** Planned
- **Relevant files/docs:** `docs/delivery_plan.md`
- **Done condition:** M2 implementation starts remain milestone-consistent and explicitly defer output/writeback/orchestration hardening work.

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
- **M1 — Operator-ready request sheet generation** *(closed 2026-04-18)*
  - Closed C1/C2/C3 with contract-aligned generation boundary, template/generation alignment, and implementation-handoff readiness.
  - Milestone closure confirms M1 exit criteria are met.

### M1 sign-off note
M1 is complete. Operator-ready request sheet generation is now contract-closed and handoff-ready; execution focus moves to M2 minimal local compute pipeline with a narrow parser/normalizer-first checkpoint.

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
- active milestone `Minimal local compute pipeline`
- active checkpoint `Parser/normalizer implementation closure`
- compact M2 parser-first starter tasks
- explicit deferrals to prevent near-term drift
