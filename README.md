# Roster Monster v2

Roster Monster v2 is a reusable roster-allocation core with department-specific templates, keeping **Google Sheets** as the operational front end. The first concrete implementation target is **CGH ICU/HD**.

## Current state
- **Live end-to-end in two modes.** Operator-facing one-click cloud (`Roster Monster → Solve Roster` menu in the bound-template spreadsheet → Cloud Run service `roster-monster-compute` → writeback into a new tab) and maintainer-facing local CLI (Apps Script extracts a Snapshot JSON → `python -m rostermonster.run --snapshot file.json` → upload via the launcher's writeback form). Both modes share one Python compute core per D-0050 and produce byte-identical envelopes at the same input when seed is explicitly set per D-0053.
- **All milestones M1 / M1.1 / M2 / M3 / M4 / M5 / M6 / M7 closed** (M7 closed 2026-05-13 per D-0072 — live async UX validated end-to-end on real ICU + HD operator cycles). Default `pytest python/tests` collects **444 tests (9 slow deselected)** at M7 closure (44 added across M7 C2's worker / orchestrator / batch job spec / GCS adapter / determinism audit modules; 30+ added in M7 C4 T2D's `test_service.py` thin-front-door coverage; further additions across T2A.2 worker inline finalize + T2B AsyncRenderCallback handler). 9 slow tests opt-in via `pytest -m slow` (end-to-end audit at K=88 + full orchestrator integration + real-solver paths). 17 Apps Script writeback unit tests.
- **Active milestone: none** *(M7 closed 2026-05-13 per D-0072 — full async UX validated end-to-end on both real live ICU and HD operator cycles; all four §7 C5 exit criteria passed: bound shim's SUBMITTED toast → `[RosterMonsterV2] Success: <tab>` email with AnalyzerOutput JSON attachment → writeback + 5 roster tabs → **analyzer comparison tab** which closes the D-0069-deferred operator-cycle cross-reference pathway as a natural side-effect of M7 C4's inline-finalize-step analyzer plumbing)*. M7 closure trail: **D-0070 → D-0071 → D-0072**. M7 delivered async cloud LAHC via Cloud Batch single-VM dense pack (one `c3-highcpu-88` running `multiprocessing.Pool(88)` for K=88 LAHC trajectories + inline finalize step in `worker.py` after `Pool.close() + .join()`). Production operator flow: click `Roster Monster → Solve Roster` → toast appears → 3-10 min later receive email → open spreadsheet → see all expected tabs. FW-0037 elbow tuple locked at the M7 production config: `L=50` / `idleThreshold=3500` / `swapProbability=0.5`. K=88 reflects current C3_CPUS=108 quota; future quota bump unlocks K=176 (FW-0040 dial, stays parked). **FW-0027 (parallel operational search and orchestration), FW-0030 (cloud-side FULL retention support), FW-0035 (cloud-mode LAHC integration), and FW-0038 (parallel solver) all DELIVERED via M7 per D-0072**. FW-0039 (silent-operator-outcome watchdog) and FW-0040 (K=88 → K=176 single-VM dial) stay parked with their existing revisit triggers. **Active checkpoint: none** *(M7 C5 closed 2026-05-13 per D-0072; M7 milestone closed same day)*. Post-M7 deliberate study window mirrors the post-M4 (2026-05-01) / post-M6 (2026-05-09) cadence — no successor pre-decided. Candidate next-work threads: FW-0033 (scoring-weight elicitation), FW-0036/FW-0037 multi-fixture promotion (LAHC K-default + L-tuning protocol module-pinning waits for 2+ additional cycles), FW-0028 (observability hardening), FW-0031/FW-0032 (analyzer extensions), operational broadening beyond ICU/HD-first. End-to-end operator workflow live in cloud (LAHC at K=88 via `solverStrategy=LAHC` in the bound shim's POST body; legacy `SEEDED_RANDOM_BLIND` path stays sync for back-compat, hidden from operator menu per D-0071 sub-decision 13) and local (CLI with `--strategy LAHC` + analyzer + launcher upload form).

## Repo posture
- **Architecture-first and contract-first.** Core boundaries are pinned in explicit contract docs before broad implementation work. The docs-first cadence (Task 1 docs → Task 2 code, with optional Task 2A/2B/2C sub-letters when work has logically distinct chunks → Task 3 closure; per D-0064) held across M2..M5. Historical "Phase 1/2/3" labels in past PR titles and closed-milestone closure entries are preserved as-is — the cadence vocabulary applies forward from M5 closure onward.

## Planning vocabulary
**Product** → **Milestone** → **Checkpoint** → **Task**. Normally one active milestone and one active checkpoint at a time.

## Repo navigation
- `docs/blueprint.md` — Stable architecture truth (what the system is, boundary invariants).
- `docs/roadmap.md` — Milestone-level delivery order + closed-milestone trail.
- `docs/delivery_plan.md` — Active execution guide (active milestone/checkpoint/tasks, recently completed checkpoints).
- `docs/decision_log.md` — Accepted directional decisions (D-0001..D-0072).
- `docs/future_work.md` — Non-normative parking lot for ideas (FW-0001..FW-0040).
- `docs/open_decisions.md` — Pending decisions awaiting closure (empty as of 2026-05-13).
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
