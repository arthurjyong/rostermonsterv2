# Roadmap (Milestone Delivery Order)

This document defines **milestone-level delivery order** for Roster Monster v2. It is intentionally not a day-to-day execution tracker; active checkpoint/task truth lives in `docs/delivery_plan.md`.

## Milestone sequence

### 1) Operator-ready request sheet generation — *Completed 2026-04-21*
Deliver an operator-usable ICU/HD request sheet shell backed by closed generation contract boundaries. Closed via M1 C1..C4 (contract closure + implementation) on operator delivery. See `docs/delivery_plan.md` §11; D-0019.

### 1.1) Operator-facing launcher *(addendum to Milestone 1)* — *Completed 2026-04-22*
Narrow operator-facing launcher so named monthly-rotation pilot operators can invoke empty ICU/HD request-sheet generation without running Apps Script by hand. Closed via M1.1 C1 on hands-on validation. M1 itself stays Completed (not reopened) per the addendum-milestone convention (D-0021); launcher architecture in D-0022; auto-share scope in D-0023.

### 2) Minimal local compute pipeline — *Completed 2026-04-29*
Deterministic local parse → normalize → rule / scoring / solve execution path using closed contracts. Closed across nine checkpoints (M2 C1..C9): rule engine + scorer + solver + selector contracts (C1, C2); their Python implementations (C3, C4, C5); operator-tuneable scoring config surface end-to-end (C6, C7); v3 spacingPenalty geometric-decay curve (C8); production Apps Script snapshot extractor + Python CLI ingestion path (C9). D-0024..D-0043.

### 3) Safe result/output and writeback — *Completed 2026-04-30*
Safe result surfaces and sheet writeback behavior for operator consumption. Closed at M3 C1 (writeback library + launcher route + Python CLI extension); M3 C2 (live-operator demo) dropped per D-0048 — round-trip already proven on the dev-copy. D-0044..D-0047.

### 4) Cloud end-to-end pipeline + dual-track preservation — *Completed 2026-05-01*
Cloud-deployed end-to-end pipeline so operators can drive a one-click roster-generation flow without local Python tooling, while preserving the local CLI as a maintainer-side dev-velocity surface for solver-strategy experiments. Reframed from `Parallel operational search and orchestration` per D-0049; closed at M4 C1 as the only checkpoint (Cloud Run service + Apps Script library reorganization + bound shim's `Roster Monster → Solve Roster` menu). D-0048..D-0054. The original M4 framing (parallel orchestration) and original M5 framing (observability) parked as **FW-0027** + **FW-0028** — re-promotable to milestones when concrete drivers surface.

### 5) Operator-side analysis & multi-roster delivery — *Completed 2026-05-07*
Operator-side analysis tooling delivered — Python analyzer engine + `AnalyzerOutput` + Apps Script analyzer renderer + launcher Web App upload route, all as sibling consumers of the wrapper envelope (writeback contract untouched, no new selector retention mode). Reframed the post-M4 priority by sequencing operator-side analysis tooling AHEAD of solver-side score-aware search; M5 C4 live operator validation confirmed the analyzer's role as calibration framework — the comparison tab surfaced a load-bearing scoring-formulation insight (`pointBalanceGlobal` weight design) the operator would not have seen from `totalScore` alone, exactly the M5 thesis working as designed. Closed across M5 C1 (analyzer engine + analysis contract; D-0056..D-0058), M5 C2 (renderer + launcher route + cross-page nav; D-0060..D-0063; cloud deployment `@15`), and M5 C4 (live operator validation; D-0065). M5 C3 dropped per D-0063 — upload-portal scope was wholly absorbed into C2's launcher Web App route, same discipline as M3 C2 dropped per D-0048. Long-term scoring-formulation rework parked as FW-0033 (systematic weight elicitation / tuning), explicitly NOT rolled into M6 scope. D-0055..D-0065. Forward-going Task 1/2/3 cadence vocabulary (D-0064) also landed alongside the closure.

### 6) Solver-side score-aware search (LAHC) — *Active (activated 2026-05-07)*
Deliver Late Acceptance Hill Climbing (LAHC) as the first alternative solver search strategy alongside today's `SEEDED_RANDOM_BLIND` per `docs/solver_contract.md` §11.1, addressing FW-0003's empirical score plateau on `SEEDED_RANDOM_BLIND`. Strategy-internal-to-solver framing — extends `docs/solver_contract.md` with a "Search strategies" section + named strategy enum + LAHC algorithm spec; only the wrapper envelope's `solverStrategy` enumerant crosses the solver boundary so the M5 analyzer + ops trail can see what ran. Maintainer-only operator-tunable surface (Python module constants for cloud defaults; CLI flag overrides for local tuning; no operator-facing UI changes). Validation loop: M5 analyzer is the calibration framework — operator runs both strategies on the same snapshot, renders each `AnalyzerOutput` separately via the launcher (two comparison tabs land in the source spreadsheet per D-0062 always-new-tab discipline; per `docs/analysis_renderer_contract.md` §9/§10 single-output-per-render contract), and manually cross-references between them. Multi-run side-by-side renderer enhancement parked as FW-0034 — explicitly NOT in M6 scope. Cloud Deep Solve + email-notification + cloud-side FULL retention promotion (FW-0030) + scoring-formulation rework (FW-0033) also explicitly carved off to FW or future milestones. M6 C1 closed 2026-05-07 per D-0067 (solver-strategy contract extension + LAHC algorithm spec — `docs/solver_contract.md` §11.1 expanded + new §12A; solver contract stays at `contractVersion: 1` because §2 + §11.2 explicitly authorize new strategy registrations as additive only). M6 C2 (LAHC core impl in Python) active; C3..C4 outlined. D-0066 / D-0067.

## Intentional later work (not near-term)
The roadmap intentionally defers some work until concrete drivers surface:
- Parallel operational search and orchestration (FW-0027) — re-promotable to a milestone when scale or reliability drivers surface.
- Observability and benchmark hardening (FW-0028) — re-promotable when long-term reliability or benchmark-comparison drivers surface. M5's analysis tooling overlaps the operator-facing slice but does not subsume the broader observability surface.
- Cloud-side FULL retention support (FW-0030) — prerequisite for M6's Deep Solve auto-included analyzer path; not in M5 scope and explicitly carved off from M6 LAHC-only scope per the M5 closure thread.
- Systematic weight elicitation / tuning (FW-0033) — re-promotable when cycle-over-cycle weight churn or multi-operator priority disagreement surfaces concrete demand. M5 C4 verdict surfaced this thread but the maintainer's sequencing call was "search next, formulation rework later"; explicitly NOT in M6 scope.
- Broad generalization to additional departments before ICU/HD-first learning is closed.
- Pilot rollout to non-maintainer operators (broader pilot is a future milestone or operational rollout step, not currently scheduled).
