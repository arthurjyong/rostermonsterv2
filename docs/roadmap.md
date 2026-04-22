# Roadmap (Milestone Delivery Order)

This document defines **milestone-level delivery order** for Roster Monster v2. It is intentionally not a day-to-day execution tracker; active checkpoint/task truth lives in `docs/delivery_plan.md`.

## Milestone sequence

### 1) Operator-ready request sheet generation
- **Goal:** Deliver an operator-usable ICU/HD request sheet shell, backed by closed generation contract boundaries.
- **Why it matters:** This is the immediate operational unblocker and anchors upstream/downstream contract usage.
- **Likely checkpoints:**
  - Close sheet-generation MVP boundary.
  - Align template artifact surfaces with generation needs.
  - Finalize generation acceptance criteria and handoff readiness.
  - Implement operator-ready sheet generation.
- **Main dependencies:**
  - `docs/template_contract.md`
  - `docs/template_artifact_contract.md`
  - `docs/request_semantics_contract.md`
  - `docs/sheet_generation_contract.md`
- **Exit criteria:**
  - Generation inputs, structural output surfaces, allowed operator edits, explicit non-goals, and acceptance criteria are closed and reviewable, and
  - operator-ready ICU/HD sheet-shell generation is implemented for the empty-form use (new spreadsheet file or new tab in an existing spreadsheet), with intended editable/protected surfaces and practical validation in place.

### 1.1) Operator-facing launcher *(addendum to Milestone 1)*
- **Goal:** Provide a narrow operator-facing launcher so named monthly-rotation pilot operators can invoke empty ICU/HD request-sheet generation without running Apps Script by hand.
- **Why it matters:** Closes M1's operator-facing story end-to-end without expanding M1's compute scope.
- **Likely checkpoints:**
  - Implement operator launcher web app.
- **Main dependencies:**
  - Milestone 1 completion.
  - `docs/sheet_generation_contract.md` §3A (spreadsheet reference input) and §12 (launcher surface).
- **Exit criteria:**
  - A non-maintainer test operator can, after one-time Google consent, load the launcher URL, submit the form, and receive a working generated sheet or tab in either output mode.
- **Addendum framing:** Milestone 1.1 is the first addendum milestone under the `M<parent>.<n>` numbering convention (integer `n` only, no nested decimals) recorded in `docs/decision_log.md` D-0021. Milestone 1 itself stays `Completed`; Milestone 2 was returned to Planned while Milestone 1.1 was active and returned to active on Milestone 1.1 closure (2026-04-22). Milestone 1.1 itself closed on 2026-04-22 on hands-on validation — see `docs/delivery_plan.md` §11.

### 2) Minimal local compute pipeline
- **Goal:** Establish a deterministic local parse → normalize → rule/scoring/solve execution path using closed contracts.
- **Why it matters:** Enables end-to-end technical verification before external orchestration complexity.
- **Likely checkpoints:**
  - Parser/normalizer implementation against locked boundaries.
  - Minimal rule/scorer/solver integration with deterministic run envelope.
  - Local run artifact packaging for basic reviewability.
- **Main dependencies:**
  - Milestone 1 completion.
  - `docs/snapshot_contract.md`
  - `docs/parser_normalizer_contract.md`
  - `docs/domain_model.md`
- **Exit criteria:**
  - Repeatable local runs can produce explainable outputs/artifacts for ICU/HD scenarios.

### 3) Safe result/output and writeback
- **Goal:** Define and implement safe result surfaces and sheet writeback behavior for operator consumption.
- **Why it matters:** Output safety and clarity are required before routine operational use.
- **Likely checkpoints:**
  - Output/result surface definition for first release.
  - Writeback mapping validation against sheet structure.
  - Failure/unsatisfied-state handling in result delivery.
- **Main dependencies:**
  - Milestone 2 completion.
  - Stable output/writeback contracts and sheet mappings.
- **Exit criteria:**
  - Outputs and writeback behavior are consistent, reviewable, and safe for controlled operator use.

### 4) Parallel operational search and orchestration
- **Goal:** Introduce reliable external worker/orchestration flow without changing compute semantics.
- **Why it matters:** Supports operational reliability, throughput, and controlled scaling.
- **Likely checkpoints:**
  - Execution envelope and transport boundaries.
  - Retry/failure behavior and idempotence expectations.
  - Parallel run orchestration guardrails.
- **Main dependencies:**
  - Milestone 3 completion.
  - Stable local pipeline semantics to preserve in external execution.
- **Exit criteria:**
  - External/parallel execution can run safely with traceable lifecycle behavior.

### 5) Observability and benchmark hardening
- **Goal:** Strengthen diagnostics, benchmarking confidence, and operational hardening.
- **Why it matters:** Long-term reliability requires measurable behavior and regression discipline.
- **Likely checkpoints:**
  - Structured observability/event coverage.
  - Benchmark campaign baselines and comparison workflow.
  - Reliability hardening against expected failure classes.
- **Main dependencies:**
  - Milestone 4 completion.
  - Stable execution and output surfaces.
- **Exit criteria:**
  - Benchmark and observability workflows are sufficient for ongoing operational confidence.

## Intentional later work (not near-term)
The roadmap intentionally defers some work until core milestones are closed:
- Advanced optimization sophistication beyond first-release operational needs.
- Deep cloud hardening beyond initial external orchestration reliability.
- Broader benchmark hardening until core execution surfaces stabilize.
- Broad generalization to additional departments before ICU/HD-first learning is closed.
