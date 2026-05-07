# Roster Monster v2

Roster Monster v2 is a reusable roster-allocation core with department-specific templates, keeping **Google Sheets** as the operational front end. The first concrete implementation target is **CGH ICU/HD**.

## Current state
- **Live end-to-end in two modes.** Operator-facing one-click cloud (`Roster Monster → Solve Roster` menu in the bound-template spreadsheet → Cloud Run service `roster-monster-compute` → writeback into a new tab) and maintainer-facing local CLI (Apps Script extracts a Snapshot JSON → `python -m rostermonster.run --snapshot file.json` → upload via the launcher's writeback form). Both modes share one Python compute core per D-0050 and produce byte-identical envelopes at the same input when seed is explicitly set per D-0053.
- **All milestones M1 / M1.1 / M2 / M3 / M4 / M5 closed** (as of 2026-05-07; M5 closed today via M5 C4 live operator validation per D-0065). 225 Python tests pass (164 baseline + 52 analyzer unit + 9 analyzer integration); 17 Apps Script writeback unit tests.
- **Active milestone: none.** M5 closed today on the M5 C4 verdict per D-0065: the analyzer's role as calibration framework was validated — the comparison tab surfaced a load-bearing scoring-formulation insight (`pointBalanceGlobal` weight design) the operator would not have seen from `totalScore` alone, exactly the M5 thesis (operator picks among K candidates with full component breakdowns rather than trusting a single scalar) working as designed. Short-term lever: maintainer iterates weights cycle-over-cycle via the Scorer Config tab (D-0037 surface). Long-term direction — systematic weight elicitation / tuning — parked as FW-0033, explicitly NOT rolled into M6. M5 C3 dropped per D-0063 (upload-portal scope wholly absorbed into C2's launcher Web App route — same discipline as M3 C2 dropped per D-0048). Next milestone (M6) is provisionally framed as solver-side score-aware search scoped LAHC-only; activation lands in its own forthcoming direction-setting PR. End-to-end operator workflow live in cloud (Quick Solve via `Roster Monster → Solve Roster` menu) and local (CLI + analyzer + launcher upload form).

## Repo posture
- **Architecture-first and contract-first.** Core boundaries are pinned in explicit contract docs before broad implementation work. The docs-first cadence (Task 1 docs → Task 2 code, with optional Task 2A/2B/2C sub-letters when work has logically distinct chunks → Task 3 closure; per D-0064) held across M2..M5. Historical "Phase 1/2/3" labels in past PR titles and closed-milestone closure entries are preserved as-is — the cadence vocabulary applies forward from M5 closure onward.

## Planning vocabulary
**Product** → **Milestone** → **Checkpoint** → **Task**. Normally one active milestone and one active checkpoint at a time.

## Repo navigation
- `docs/blueprint.md` — Stable architecture truth (what the system is, boundary invariants).
- `docs/roadmap.md` — Milestone-level delivery order + closed-milestone trail.
- `docs/delivery_plan.md` — Active execution guide (active milestone/checkpoint/tasks, recently completed checkpoints).
- `docs/decision_log.md` — Accepted directional decisions (D-0001..D-0065).
- `docs/future_work.md` — Non-normative parking lot for ideas (FW-0001..FW-0033).
- `docs/open_decisions.md` — Pending decisions awaiting closure (empty as of 2026-05-07).
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
