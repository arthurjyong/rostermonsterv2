# Roster Monster v2

Roster Monster v2 is building a reusable roster-allocation core with department-specific templates, while keeping **Google Sheets** as the operational front end. The first concrete implementation target is **CGH ICU/HD**.

## Current repo posture
- **Architecture-first and contract-first:** core boundaries are defined in explicit docs and contracts before broad implementation work.
- **Planning / early implementation posture:** this repo is still prioritizing clear execution direction and bounded delivery sequencing over broad parallel buildout.

## Planning hierarchy
This repo uses a single planning vocabulary:
- **Product**: the full end-to-end capability being built.
- **Milestone**: a major delivery state that moves the product forward.
- **Checkpoint**: a bounded, reviewable step inside a milestone.
- **Task**: a concrete work item used to close a checkpoint.

## Current focus
- **Active milestone:** `Operator-ready request sheet generation`
- **Active checkpoint:** `Implement operator-ready sheet generation`

## Repo navigation
- `docs/blueprint.md` — Stable architecture truth (what the system is and how boundaries are defined).
- `docs/roadmap.md` — Medium-term milestone-level delivery order.
- `docs/delivery_plan.md` — Active execution guide (current milestone, checkpoint, and tasks).
- `docs/decision_log.md` — Accepted directional decisions and governance choices.

## How to use this repo
1. Start with this README for orientation.
2. Read `docs/blueprint.md` to understand architecture and boundary invariants.
3. Read `docs/roadmap.md` for milestone sequencing.
4. Use `docs/delivery_plan.md` for current execution truth.
5. Use contract docs when working on technical boundary details.
