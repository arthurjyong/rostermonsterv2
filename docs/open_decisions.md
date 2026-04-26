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

### OD-0001 — Provenance field-shape standard across normalized entities
- **Surfaced:** M2 C3 T2 implementation (parser/normalizer normalizer side).
- **Question:** What is the long-term shape of the `provenance` field on
  snapshot-derived normalized entities? Current implementation uses the
  `rostermonster.snapshot` locator types directly (`Doctor.provenance:
  DoctorLocator`, `RosterDay.provenance: DayLocator`, `Request.provenance:
  RequestLocator`, `FixedAssignment.provenance: PrefilledAssignmentLocator`,
  `DailyEffectState.provenance: RequestLocator`, `SlotDemand.provenance:
  DayLocator`). `docs/parser_normalizer_contract.md` §16 declares the
  parser-stage traceability obligation but explicitly defers concrete
  field-shape standardization (§16 last paragraph + §19). Candidate
  alternative shapes include a uniform `ProvenanceTrace` wrapper class with
  `sourceRecordKind` + `locatorPath` fields, embedding `physicalSourceRef`
  alongside the logical locator, or a tuple-of-locators shape for entities
  whose origin spans multiple snapshot records.
- **Why deferred now:** The current shape satisfies the §16 traceability
  obligation. No downstream stage has yet been implemented to consume
  provenance. Picking a different shape later is a mechanical refactor —
  entities already know their origin via locator-typed fields regardless of
  how those fields are wrapped.
- **Trigger to close:** Any of the following materializes —
  (a) rule engine / scorer / solver / selector implementation surfaces a
  need for a uniform provenance API across stages,
  (b) writeback implementation needs provenance-driven diagnostics that the
  locator-direct shape doesn't easily support,
  (c) a benchmark-campaign or audit workflow wants stable provenance
  serialization across all normalized entity types,
  (d) a future entity has multi-record origin (for example, derived facts
  combining multiple requests) and the locator-direct shape becomes
  insufficient.
- **Affects:** Touches every snapshot-derived normalized type in
  `python/rostermonster/domain.py` if changed; locator types in
  `python/rostermonster/snapshot.py` stay unchanged regardless. No
  downstream stage is blocked by leaving this open.

## Maintenance
- Add an entry when implementation surfaces a real open decision — not when
  it surfaces an idea (which belongs in `docs/future_work.md`).
- Promote to `docs/decision_log.md` and delete here when closed.
- Keep entries terse; detail belongs in the eventual `decision_log.md` entry.
- This document is reviewed at checkpoint sign-off — any active checkpoint
  closure should pass over this document and confirm whether any entries
  block closure.
