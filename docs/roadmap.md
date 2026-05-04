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

### 5) Operator-side analysis & multi-roster delivery — *Active (activated 2026-05-04)*
Give operators the tools to see what's actually in a roster and compare alternatives, without changing the solver. Three-piece architecture: Python analyzer engine + `AnalyzerOutput` + Apps Script analyzer renderer + upload portal — all sibling consumers of the wrapper envelope (writeback contract untouched, no new selector retention mode). Reframes the post-M4 priority by sequencing operator-side analysis tooling AHEAD of solver-side score-aware search, because analysis tooling is the calibration framework any future solver work needs to be measured against, AND it acts as the operator-side workaround for the weighted-sum scoring formulation pain (operator picks among K candidates with full component breakdowns rather than trusting a single scalar). M5 C1 active; subsequent checkpoints (Apps Script renderer, upload portal, live operator validation) outlined but not yet activated. D-0055.

### Next milestone slot — *Not yet activated*
M6 is provisionally framed around solver-side score-aware search (LAHC + cloud Deep Solve + email-notification architecture + cloud-side FULL retention promotion of FW-0030). Whether M6 is one milestone or split into multiple is left to its own framing decision and not pre-committed. Activation waits until M5 closes (or progresses far enough to surface concrete M6 drivers).

## Intentional later work (not near-term)
The roadmap intentionally defers some work until concrete drivers surface:
- Parallel operational search and orchestration (FW-0027) — re-promotable to a milestone when scale or reliability drivers surface.
- Observability and benchmark hardening (FW-0028) — re-promotable when long-term reliability or benchmark-comparison drivers surface. M5's analysis tooling overlaps the operator-facing slice but does not subsume the broader observability surface.
- Cloud-side FULL retention support (FW-0030) — prerequisite for M6's Deep Solve auto-included analyzer path; not in M5 scope.
- Broad generalization to additional departments before ICU/HD-first learning is closed.
- Pilot rollout to non-maintainer operators (broader pilot is a future milestone or operational rollout step, not currently scheduled).
