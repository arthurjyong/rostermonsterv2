# Roster Monster v2

Roster Monster v2 is a reusable roster-allocation core with department-specific templates, keeping **Google Sheets** as the operational front end. The first concrete implementation target is **CGH ICU/HD**.

## Current state
- **Live end-to-end in two modes.** Operator-facing one-click cloud (`Roster Monster → Solve Roster` menu in the bound-template spreadsheet → Cloud Run service `roster-monster-compute` → writeback into a new tab) and maintainer-facing local CLI (Apps Script extracts a Snapshot JSON → `python -m rostermonster.run --snapshot file.json` → upload via the launcher's writeback form). Both modes share one Python compute core per D-0050 and produce byte-identical envelopes at the same input when seed is explicitly set per D-0053.
- **All milestones M1 / M1.1 / M2 / M3 / M4 closed** (as of 2026-05-01); **M5 C1 closed 2026-05-05** (Python analyzer engine + analysis contract); **M5 C2 closed 2026-05-06** (Apps Script renderer + launcher Web App route + cross-page nav; cloud deployment `@15`). 225 Python tests pass (164 baseline + 52 analyzer unit + 9 analyzer integration); 17 Apps Script writeback unit tests.
- **Active milestone: M5 — Operator-side analysis & multi-roster delivery** (activated 2026-05-04 per D-0055). Building a Python analyzer engine + Apps Script analyzer renderer as **sibling consumers** of the wrapper envelope — purely additive to the existing pipeline (no contract changes upstream of analysis). Rationale: analysis tooling first, solver-side score-aware search second, so future LAHC / score-aware strategy work has a calibration framework to be measured against. M5 also doubles as the operator-side workaround for the weighted-sum scoring formulation pain (operator picks among K candidates with full component breakdowns rather than trusting a single scalar). M5 C1 (analyzer engine) + M5 C2 (renderer + launcher route) both closed; **active checkpoint: M5 C4** — live operator validation on a real ICU/HD cycle. C3 dropped from the plan because the upload-portal scope was wholly absorbed into C2's launcher Web App route per D-0063. End-to-end operator workflow today: extract snapshot → `python -m rostermonster.run ... --retention FULL` → `python -m rostermonster.analysis ...` → upload `AnalyzerOutput` to launcher's `?action=analysis-render` route → see K roster tabs + 1 comparison tab in the source spreadsheet.

## Repo posture
- **Architecture-first and contract-first.** Core boundaries are pinned in explicit contract docs before broad implementation work. The docs-first phased delivery cadence (Phase 1 docs → Phase 2 code → Phase 3 closure) held across M2..M4.

## Planning vocabulary
**Product** → **Milestone** → **Checkpoint** → **Task**. Normally one active milestone and one active checkpoint at a time.

## Repo navigation
- `docs/blueprint.md` — Stable architecture truth (what the system is, boundary invariants).
- `docs/roadmap.md` — Milestone-level delivery order + closed-milestone trail.
- `docs/delivery_plan.md` — Active execution guide (active milestone/checkpoint/tasks, recently completed checkpoints).
- `docs/decision_log.md` — Accepted directional decisions (D-0001..D-0055).
- `docs/future_work.md` — Non-normative parking lot for ideas (FW-0001..FW-0030).
- `docs/open_decisions.md` — Pending decisions awaiting closure (empty as of 2026-05-04).
- `docs/*_contract.md` — Normative technical boundary definitions.

## Code layout
- `apps_script/launcher/` — Operator-facing launcher Web App (sheet generation + writeback form).
- `apps_script/bound_shim/` — Bound shim attached to the template spreadsheet (Extract Snapshot + Solve Roster menus).
- `apps_script/central_library/` — Central Apps Script library (snapshot extractor + writeback library + cloud-mode orchestration).
- `python/rostermonster/` — Shared Python compute core (parser, normalizer, rule engine, scorer, solver, selector, pipeline entrypoint).
- `python/rostermonster_service/` — Flask HTTP wrapper for Cloud Run (D-0050 dual-track).
- `cloud_compute_service/` — Dockerfile + deployment bundle for Cloud Run.

## How to use this repo
1. Read this README for orientation.
2. Read `docs/blueprint.md` for architecture and boundary invariants.
3. Use `docs/delivery_plan.md` for current execution truth.
4. Check `docs/decision_log.md` if a proposed change is direction-changing.
5. Read the narrowest relevant contract doc for technical boundary detail.
