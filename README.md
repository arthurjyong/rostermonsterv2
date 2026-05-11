# Roster Monster v2

Roster Monster v2 is a reusable roster-allocation core with department-specific templates, keeping **Google Sheets** as the operational front end. The first concrete implementation target is **CGH ICU/HD**.

## Current state
- **Live end-to-end in two modes.** Operator-facing one-click cloud (`Roster Monster → Solve Roster` menu in the bound-template spreadsheet → Cloud Run service `roster-monster-compute` → writeback into a new tab) and maintainer-facing local CLI (Apps Script extracts a Snapshot JSON → `python -m rostermonster.run --snapshot file.json` → upload via the launcher's writeback form). Both modes share one Python compute core per D-0050 and produce byte-identical envelopes at the same input when seed is explicitly set per D-0053.
- **All milestones M1 / M1.1 / M2 / M3 / M4 / M5 / M6 closed** (M6 closed 2026-05-09 per D-0069). 249 Python tests pass (244 baseline at M6 C3 close + 5 swapProbability / audit-surface tests added in M6 C4 PR-A; pipeline 10/10, selector 23/23, run-CLI 12/12, solver 41/41 at M6 closure); 17 Apps Script writeback unit tests.
- **Active milestone: M7 — Parallel solver (Cloud Batch + intra-request K-fanout, async UX)** *(activated 2026-05-10 per D-0070; UX pivoted sync → async on 2026-05-11 per D-0071 driven by M7 C2 perftest evidence)*. M7 parallelizes K-trajectory LAHC via Cloud Batch + dense pack (`c3-highcpu-8` VMs × `multiprocessing.Pool(8)` × 1 LAHC trajectory per vCPU). Original M7 framing (D-0070) targeted sync UX inside a 250s Cloud Run timeout; **M7 C2 perftest evidence (real production roster at K_approved=104) showed 5/13 tasks unfinished at the 240s deadline**, returning partial K'=64. D-0071 pivots M7 C3 onward to async architecture: Cloud Run thin front door (validate + submit + return SUBMITTED ~3-5s) + Cloud Batch finalizer task group (aggregate + score + analyze + POST to launcher Web App callback + email operator) with 10-min hard cap. The architecture escapes the GIL-bound single-thread bottleneck identified during M6 C4 cloud benchmarking (4-vCPU bump only +10% throughput on the SRB cloud baseline; LAHC cloud projection at K=10 already overshoots the 5-min Cloud Run timeout at ~13 min before parallelism). FW-0037 elbow tuple locked: `L=50` / `idleThreshold=3500` / `swapProbability=0.5`. K=2,500 target (with smaller approvals acceptable since best-of-K plateau is K=10-20 per FW-0036). On-demand pricing chosen over Spot for predictable wall-time — cost is not a constraint at the doctor-time-comparison framing (~$2.20/run on-demand at K=2,500 vs $110-130 SGD/hr doctor admin time saved). **Active checkpoint: M7 C3 — Async architecture decision (D-0071)** *(activated 2026-05-11 on M7 C2 closure; scope pivoted from sync UX to async architecture decision on 2026-05-11 per the M7 C2 perftest evidence + D-0071)*. M7 C2 closed 2026-05-11 — full Cloud Batch parallel-LAHC chain delivered (worker + orchestrator + Batch job spec + GCS adapter + attempt-id race closure) with the §12A.4 byte-identity exit criterion proven (5/5 audit tests; local-CLI ↔ Cloud-Batch produce byte-identical writebackEnvelope at the same `(masterSeed, K)` including the negative-seed `_UINT64_MASK` case). M7 C1 closed 2026-05-10 with GCP quota approvals (asia-southeast1): CPUS=300 / INSTANCES=350 / C3_CPUS=108 (binding). Closure-K = 104 per D-0070 sub-decision 7's three-quota rule. M7 closure trail: D-0070 (M7 framing) → D-0071 (M7 C3 async pivot). M6 closure trail: D-0066 → D-0067 → D-0068 → D-0069. **M7 C2 perftest revealed sync-budget brittleness** (5/13 tasks unfinished at 240s deadline on real production roster at K=104); D-0071 pivots M7 C3 to async architecture: Cloud Run thin front door (validate + submit + return SUBMITTED ~3-5s) + Cloud Batch finalizer task group (aggregate + score + analyze + POST to launcher Web App callback `/exec?action=async-render-callback` + email operator) with 10-min hard cap, GCP ID-token auth, B-prime callback delivery (reuses existing `RMLib.applyWriteback + RMLib.renderAnalysis`), always-email-on-failure with `[RosterMonsterV2]` subject prefix + AnalyzerOutput JSON attachment, concurrent-rejection by spreadsheet ID via Cloud Batch labels. M7 C3 is docs-only (D-0071 + supporting sweeps). M7 C4 implements the architecture; M7 C5 lives-operator validates + closes M7. Cloud Run per-instance concurrency, threading, and Spot pricing explicitly excluded per D-0070 sub-decisions. FW-0035 (cloud-mode LAHC integration) + FW-0030 (cloud-side FULL retention support) co-promote with M7 closure (closure path now async per D-0071); FW-0027 absorbed into M7 C3+C4 per D-0071; new FW-0039 (finalizer-crash watchdog) added per D-0071 sub-decision 17 as accepted-gap-for-v1. End-to-end operator workflow live in cloud (currently `SEEDED_RANDOM_BLIND` strategy in v1; LAHC arrives via cloud at M7 C4 wiring + maintainer-only `/compute-lahc-test` route already live for end-to-end testing) and local (CLI with `--strategy LAHC` + analyzer + launcher upload form).

## Repo posture
- **Architecture-first and contract-first.** Core boundaries are pinned in explicit contract docs before broad implementation work. The docs-first cadence (Task 1 docs → Task 2 code, with optional Task 2A/2B/2C sub-letters when work has logically distinct chunks → Task 3 closure; per D-0064) held across M2..M5. Historical "Phase 1/2/3" labels in past PR titles and closed-milestone closure entries are preserved as-is — the cadence vocabulary applies forward from M5 closure onward.

## Planning vocabulary
**Product** → **Milestone** → **Checkpoint** → **Task**. Normally one active milestone and one active checkpoint at a time.

## Repo navigation
- `docs/blueprint.md` — Stable architecture truth (what the system is, boundary invariants).
- `docs/roadmap.md` — Milestone-level delivery order + closed-milestone trail.
- `docs/delivery_plan.md` — Active execution guide (active milestone/checkpoint/tasks, recently completed checkpoints).
- `docs/decision_log.md` — Accepted directional decisions (D-0001..D-0070).
- `docs/future_work.md` — Non-normative parking lot for ideas (FW-0001..FW-0038).
- `docs/open_decisions.md` — Pending decisions awaiting closure (empty as of 2026-05-10).
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
