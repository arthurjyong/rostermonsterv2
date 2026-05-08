# Roster Monster v2

Roster Monster v2 is a reusable roster-allocation core with department-specific templates, keeping **Google Sheets** as the operational front end. The first concrete implementation target is **CGH ICU/HD**.

## Current state
- **Live end-to-end in two modes.** Operator-facing one-click cloud (`Roster Monster → Solve Roster` menu in the bound-template spreadsheet → Cloud Run service `roster-monster-compute` → writeback into a new tab) and maintainer-facing local CLI (Apps Script extracts a Snapshot JSON → `python -m rostermonster.run --snapshot file.json` → upload via the launcher's writeback form). Both modes share one Python compute core per D-0050 and produce byte-identical envelopes at the same input when seed is explicitly set per D-0053.
- **All milestones M1 / M1.1 / M2 / M3 / M4 / M5 closed** (as of 2026-05-07; M5 closed via M5 C4 live operator validation per D-0065). 244 Python tests pass (228 baseline including LAHC implementation + 5 LAHC integration tests added in M6 C2 Task 2C + 11 LAHC + envelope tests added across M6 C3 Tasks 2A/2B); 17 Apps Script writeback unit tests.
- **Active milestone: M6 — Solver-side score-aware search (LAHC)** (activated 2026-05-07 same-day as M5 closure per D-0066). Deliver Late Acceptance Hill Climbing as the first alternative solver search strategy alongside today's `SEEDED_RANDOM_BLIND`, addressing FW-0003's empirical score plateau. Two strategy-aware fields cross the solver boundary at v2: (i) `strategyId` as a required input — callers MUST pass it explicitly per `docs/solver_contract.md` §9; (ii) the wrapper envelope's `solverStrategy` + `solverStrategyConfig` optional additive fields per `docs/selector_contract.md` §16.5 recording which strategy ran (post-M6 C3 producers MUST populate both together) so the M5 analyzer + ops trail can see what ran. Maintainer-only operator-tunable surface (Python module constants for cloud defaults; CLI flag overrides for local tuning per `docs/solver_contract.md` §12A.7 — `--strategy`, `--lahc-history-length`, `--lahc-iter-cap`, `--lahc-idle-threshold`; no operator-facing UI changes). **Active checkpoint: M6 C4** — Live operator validation via M5 analyzer. M6 C1 closed 2026-05-07 per D-0067 (solver-strategy contract extension + LAHC algorithm spec; solver contract bumped to `contractVersion: 2` for the §9 input-shape change). M6 C2 closed 2026-05-08 (LAHC implemented end-to-end per §12A spec; PRs #126/#127/#128). M6 C3 closed 2026-05-08 (envelope additive bump + CLI flags + integration tests; PRs #129/#130/#131; characterization runs surfaced **FW-0036** — LAHC operator-cycle K defaults). **Pre-validation empirical signal**: paired comparable-budget benchmark on the May 2026 ICU/HD dev-copy showed SRB-K=100 ≈ LAHC-K=10 in wall time but LAHC dominates score by ~+50 mean points (paired t(4)=11.10, p≪0.001 across 5 seeds). Cloud Deep Solve + email-notification + cloud-side FULL retention promotion (FW-0030) + scoring-formulation rework (FW-0033) explicitly carved off to FW or future milestones — they are NOT in M6 scope. Cloud-mode LAHC integration parked as FW-0035 per D-0068 (cloud HTTP wrapper continues to ship `SEEDED_RANDOM_BLIND`-only in v1 until local LAHC is empirically validated on 3+ real cycles). Validation loop: M5 analyzer (operator runs both strategies on the same snapshot, renders each `AnalyzerOutput` separately, manually cross-references the two resulting comparison tabs; single-tab side-by-side enhancement parked as FW-0034). End-to-end operator workflow live in cloud (Quick Solve via `Roster Monster → Solve Roster` menu) and local (CLI with `--strategy LAHC` + analyzer + launcher upload form).

## Repo posture
- **Architecture-first and contract-first.** Core boundaries are pinned in explicit contract docs before broad implementation work. The docs-first cadence (Task 1 docs → Task 2 code, with optional Task 2A/2B/2C sub-letters when work has logically distinct chunks → Task 3 closure; per D-0064) held across M2..M5. Historical "Phase 1/2/3" labels in past PR titles and closed-milestone closure entries are preserved as-is — the cadence vocabulary applies forward from M5 closure onward.

## Planning vocabulary
**Product** → **Milestone** → **Checkpoint** → **Task**. Normally one active milestone and one active checkpoint at a time.

## Repo navigation
- `docs/blueprint.md` — Stable architecture truth (what the system is, boundary invariants).
- `docs/roadmap.md` — Milestone-level delivery order + closed-milestone trail.
- `docs/delivery_plan.md` — Active execution guide (active milestone/checkpoint/tasks, recently completed checkpoints).
- `docs/decision_log.md` — Accepted directional decisions (D-0001..D-0068).
- `docs/future_work.md` — Non-normative parking lot for ideas (FW-0001..FW-0035).
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
