# Open Decisions

## Purpose
Tracks decisions surfaced during implementation that need closure but are
deferred for batch handling later. Distinct from:
- `docs/decision_log.md` — accepted directional decisions (closed).
- `docs/future_work.md` — non-normative parking lot for ideas.
- contract docs (`docs/*_contract.md`) — normative technical boundaries.

Entries here are **specific decisions** that need a yes/no or choose-among-N
answer. When closed, an entry is promoted to `docs/decision_log.md` (with a
D-NNNN number) and deleted from here. When deliberately rejected, a short
rationale is recorded in `docs/decision_log.md` and the entry is deleted from
here.

This document must not drift into a parallel ideas/parking-lot doc. If an
entry is more idea than decision, it belongs in `docs/future_work.md`.

## Entry format
Each entry is short and concrete:
- **Title** (`OD-NNNN — short title`)
- **Surfaced:** when / where (PR or implementation context)
- **Question:** the specific decision needed
- **Why deferred now:** what makes closure unnecessary at surface time
- **Trigger to close:** what would make this worth resolving
- **Affects:** what's currently constrained by leaving this open

## Current entries

*(none currently open)*

Recently closed entries promote to `docs/decision_log.md`. Most recent
promotions:
- **OD-0002 → D-0037** on 2026-04-27 (point-row weighting integration —
  resolved as part of the broader operator-tuneable scoring config surface
  architecture per D-0037; `pointRules` flows through `ScoringConfig` and
  the scorer's `pointBalance*` components consume it).
- **OD-0001 → D-0035** on 2026-04-27 (provenance field-shape standard
  locked at locator-direct).

## Maintenance
- Add an entry when implementation surfaces a real open decision — not when
  it surfaces an idea (which belongs in `docs/future_work.md`).
- Promote to `docs/decision_log.md` and delete here when closed.
- Keep entries terse; detail belongs in the eventual `decision_log.md` entry.
- This document is reviewed at checkpoint sign-off — any active checkpoint
  closure should pass over this document and confirm whether any entries
  block closure.
