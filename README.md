# Roster Monster v2

Roster Monster v2 is a reusable roster-allocation core with department-specific templates, keeping **Google Sheets** as the operational front end. The first concrete implementation target is **CGH ICU/HD**.

## Current state
- **Live end-to-end in two modes.** Operator-facing one-click cloud (`Roster Monster → Solve Roster` menu in the bound-template spreadsheet → Cloud Run service `roster-monster-compute` → writeback into a new tab) and maintainer-facing local CLI (Apps Script extracts a Snapshot JSON → `python -m rostermonster.run --snapshot file.json` → upload via the launcher's writeback form). Both modes share one Python compute core per D-0050 and produce byte-identical envelopes at the same input when seed is explicitly set per D-0053.
- **All milestones M1 / M1.1 / M2 / M3 / M4 / M5 / M6 closed** (M6 closed 2026-05-09 per D-0069). 249 Python tests pass (244 baseline at M6 C3 close + 5 swapProbability / audit-surface tests added in M6 C4 PR-A; pipeline 10/10, selector 23/23, run-CLI 12/12, solver 41/41 at M6 closure); 17 Apps Script writeback unit tests.
- **Active milestone: *none*** (M6 closed 2026-05-09 per D-0069 — LAHC empirically validated as superior to `SEEDED_RANDOM_BLIND` on the May 2026 ICU/HD dev-copy fixture; sweet-spot defaults `L=10` / `idleThreshold=2000` / `swapProbability=0.5` / `K=10–20` captured but NOT module-pinned pending multi-fixture validation per FW-0036/FW-0037; M7 — parallel solver — is the candidate next milestone but explicitly held in study before activation per FW-0038). Goal once M7 activates: 64 K-trajectory LAHC runs in <5 min on cloud; LAHC's K-trajectory independence per `docs/solver_contract.md` §12A.2 makes parallelism structurally permitted at the algorithm level; deployment shape (intra-request fanout shapes only — multiprocessing-spawn within the request, Cloud Run job parallelism, hybrid multi-process within Cloud Run; Cloud Run per-instance concurrency is excluded since it serves multiple operators rather than splitting one request) held for in-detail study before M7 activation. M6 closure trail: D-0066 (M6 framing — LAHC-only) → D-0067 (M6 C1 LAHC algorithm spec; solver contract `contractVersion: 1` → `2` for §9 input-shape change) → D-0068 (M6 C3 local-first scope narrowing; cloud-mode LAHC carved off to FW-0035) → D-0069 (M6 C4 + M6 milestone closure verdict; closure scope shifted from a live operator-cycle comparison-tab cross-reference to dev-copy empirical characterization because the dominance signal was already overwhelming on local LAHC-vs-SRB paired benchmarks and cloud benchmarking on the SRB cloud baseline — the cloud wrapper ships `SEEDED_RANDOM_BLIND` only in v1 per FW-0035 — surfaced a different load-bearing concern: single-thread bottleneck shared between both strategies under GIL-bound pure-Python compute). Cloud-mode LAHC integration (FW-0035) stays parked because pre-parallelization cloud rollout is less compelling than waiting on M7's parallel core. M6 C4 PR-A landed `LahcParams.swapProbability` + `--lahc-swap-probability` CLI flag + `apps_script/launcher/src/DeleteSheetsById.gs` maintainer utility; resolved value threads through audit surfaces (`SearchDiagnostics.lahcSwapProbability`, `LahcParamsRecord.swapProbability`, `runEnvelope.solverStrategyConfig.lahcParams.swapProbability` per Codex P2 round-1 fix). End-to-end operator workflow live in cloud (Quick Solve via `Roster Monster → Solve Roster` menu, `SEEDED_RANDOM_BLIND` strategy in v1 — LAHC stays maintainer-CLI-only until FW-0035 promotes) and local (CLI with `--strategy LAHC` + analyzer + launcher upload form).

## Repo posture
- **Architecture-first and contract-first.** Core boundaries are pinned in explicit contract docs before broad implementation work. The docs-first cadence (Task 1 docs → Task 2 code, with optional Task 2A/2B/2C sub-letters when work has logically distinct chunks → Task 3 closure; per D-0064) held across M2..M5. Historical "Phase 1/2/3" labels in past PR titles and closed-milestone closure entries are preserved as-is — the cadence vocabulary applies forward from M5 closure onward.

## Planning vocabulary
**Product** → **Milestone** → **Checkpoint** → **Task**. Normally one active milestone and one active checkpoint at a time.

## Repo navigation
- `docs/blueprint.md` — Stable architecture truth (what the system is, boundary invariants).
- `docs/roadmap.md` — Milestone-level delivery order + closed-milestone trail.
- `docs/delivery_plan.md` — Active execution guide (active milestone/checkpoint/tasks, recently completed checkpoints).
- `docs/decision_log.md` — Accepted directional decisions (D-0001..D-0069).
- `docs/future_work.md` — Non-normative parking lot for ideas (FW-0001..FW-0038).
- `docs/open_decisions.md` — Pending decisions awaiting closure (empty as of 2026-05-09).
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
