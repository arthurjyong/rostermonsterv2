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

### OD-0002 — Point-row weighting integration into point-balance scoring
- **Surfaced:** M2 C4 T2 implementation (scorer side).
- **Question:** Should the scorer's `pointBalanceWithinSection` /
  `pointBalanceGlobal` components use the operator-facing point-row
  weighting from `docs/template_artifact_contract.md` §9 (`weekdayToWeekday=1.0`,
  `weekdayToWeekendOrPublicHoliday=1.75`,
  `weekendOrPublicHolidayToWeekendOrPublicHoliday=2.0`,
  `weekendOrPublicHolidayToWeekday=1.5`), or stay at the simpler
  "1 point per call" first-release approximation?
- **Why deferred now:** Implementing point-row weighting requires extending
  the parser-consumable template artifact subset
  (`python/rostermonster/template_artifact.py`) to carry `pointRows`
  declarations and threading them through the scorer. The v1 reference pass
  (FW-0014) will tell us whether v1's effective scoring actually uses
  pointRows or treats them as display-only on the operator-facing sheet.
  Shipping the simpler version proves the pipeline works end-to-end without
  speculative work; if the v1 pass shows pointRows are scoring-relevant,
  the upgrade is mechanical (add fields + multiply by weight in
  `_call_count_per_doctor`).
- **Trigger to close:** Either (a) the FW-0014 v1 reference pass reveals
  whether v1's effective `pointBalance*` scoring uses pointRows weighting
  or not; or (b) a benchmark-campaign or operator-feedback signal shows
  1-point-per-call gives non-realistic point-balance results vs operator
  expectations.
- **Affects:** `python/rostermonster/template_artifact.py` (would gain
  `pointRows` data); `python/rostermonster/scorer/components.py`
  (`point_balance_within_section`, `point_balance_global`,
  `_call_count_per_doctor`); scorer tests.

Recently closed entries promote to `docs/decision_log.md`. The most recent
promotion: **OD-0001 → D-0035** on 2026-04-27 (provenance field-shape standard
locked at locator-direct).

## Maintenance
- Add an entry when implementation surfaces a real open decision — not when
  it surfaces an idea (which belongs in `docs/future_work.md`).
- Promote to `docs/decision_log.md` and delete here when closed.
- Keep entries terse; detail belongs in the eventual `decision_log.md` entry.
- This document is reviewed at checkpoint sign-off — any active checkpoint
  closure should pass over this document and confirm whether any entries
  block closure.
