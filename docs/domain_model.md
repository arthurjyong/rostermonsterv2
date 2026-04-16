# Domain Model

## 1. Purpose
- Define the normalized internal model used in v2 **after parser/normalizer** and **before solver, scorer, diagnostics, and writeback adapter**.
- Provide an implementation-facing contract that is conservative, practical, and grounded in confirmed v1 ICU/HD semantics where appropriate.
- Explicitly mark where v2 intentionally diverges from v1 so implementers do not accidentally regress semantics.
- Document first-release decisions that are considered settled, while explicitly listing controlled deferrals.

## 2. Scope
This document covers:
- Core domain entities and relationships.
- Identity/reference data needed by solver/scorer.
- Hard-constraint semantics and assignment invariants.
- Normalized request semantics and normalized machine effects.
- Allocation, scoring, validation, and search-diagnostics result objects.
- Candidate-retention policy options (default and optional deep modes).

This document does **not** cover:
- Solver algorithm or search heuristic design.
- Detailed policy tuning values (exact penalty magnitudes, weights).
- Google Sheets layout specifics or writeback range mapping.
- Worker/cloud execution architecture.

## 3. Key design principles
- **Sheet-layout independence where practical**: normalized objects should not depend on sheet row/column coordinates.
- **Explicit hard rules**: hard validity rules are first-class and machine-checkable.
- **Explicit penalty-bearing effects**: soft penalties are represented explicitly, not hidden in ad hoc scorer logic.
- **First-class search transparency**: non-winning search information must remain representable.
- **Retention flexibility**: support normal best-only retention plus optional top-K/full retention for debugging and benchmarking.
- **Generic core + template instantiation**: core concepts stay template-agnostic; ICU/HD values below are the current template instance, not a globally fixed v2 universe.
- **Traceability where snapshot-derived**: normalized entities/facts derived from snapshot records must remain traceable to source locators; universal provenance field-shape standard remains deferred.

## 4. v1 compatibility and intentional v2 differences

### 4.1 Preserve from v1 (current ICU/HD template-instance semantics)
- Runtime doctor identity is `doctorId`; display name is human-facing/output-facing.
- Current ICU/HD template doctor groups are:
  - `ICU_ONLY`
  - `ICU_HD`
  - `HD_ONLY`
- Current ICU/HD template slot types are:
  - `MICU_CALL`
  - `MICU_STANDBY`
  - `MHD_CALL`
  - `MHD_STANDBY`
- Standby remains an explicit `SlotType`.
- Request parsing remains split between raw request code and normalized machine effects.
- `CR` remains a soft preference signal and never overrides hard validity.

### 4.2 Intentional v2 differences
- Score direction is **`HIGHER_IS_BETTER`** (v1 was lower-is-better).
- Slot demand is explicit via `SlotDemand.requiredCount` (v1 core representation effectively assumed one demand unit per `(dateKey, slotType)`).
- Assignment representation is multiplicity-safe and does not depend on a fixed v1-style per-day slot map.
- Search/debug artifacts are first-class domain outputs.
- System supports optional deep retention (top-K/full candidate, including full chunk retention) while keeping best-only as default.

## 5. Pipeline position
- Input snapshot + template mapping enter parser/normalizer.
- Parser/normalizer emits this normalized domain model plus parse/normalization issues.
- Solver/rule-checker/scorer consume this model.
- Diagnostics/search artifacts are produced alongside solve/score outcomes.
- Writeback adapter consumes allocation/result objects and maps them to output format.

## 6. Core entity overview
- **`RosterPeriod`**: scope object for one roster run period (date range and related context).
- **`RosterDay`**: one date inside a period; supports ordering and date-local metadata.
- **`Doctor`**: assignable person identity and static attributes used by rules/scoring.
- **`DoctorGroup`**: template-defined group taxonomy used for slot eligibility.
- **`SlotType`**: template-defined duty category identity (includes standby categories when present).
- **`SlotTypeDefinition`**: normalized slot metadata for each slot type identity.
- **`SlotDemand`**: explicit demand units for `(date, slotType)` with `requiredCount`.
- **`FixedAssignment`**: explicit normalized input-side locked assignment fact admitted by parser/normalizer.
- **`Request`**: raw/parsed per-doctor per-day request facts.
- **`DailyEffectState`**: normalized day-level machine effects derived from requests.
- **`EligibilityRule`**: baseline eligibility mapping (for example, slot type to allowed groups).
- **`AssignmentUnit`**: smallest multiplicity-safe retained assignment unit.
- **`AllocationResult`**: solved allocation output, including unfilled demand and linked outputs.
- **`ScoreResult`**: total/component score with explicit score direction.
- **`ValidationIssue`**: structured issue object for parse/normalize/rule/allocation validation findings.
- **`SearchDiagnostics`**: aggregate transparency object for search behavior.
- **`TrialCandidate`**: one generated candidate roster with compact summary and score.
- **`TrialBatchResult`**: one batch/chunk search result, including best and optionally retained candidates.

## 7. Core identities and reference data

### 7.1 RosterPeriod
Represents one scheduling period under solve. Minimum useful fields:
- `periodId` (or equivalent stable run-local identity)
- `startDate`, `endDate`
- ordered list of `RosterDay` entries

### 7.2 RosterDay
Represents one date in-period. Minimum useful fields:
- `dateKey` (stable date identity)
- `dayIndex` (ordered index within `RosterPeriod`)
- optional metadata consumed by scoring/policy

### 7.3 Doctor
Represents one assignable doctor.
- Runtime identity: `doctorId`.
- Human-facing identity: `displayName`.
- Optional external/source identity may exist, but assignment internals remain `doctorId`-based.
- Group membership semantics are parser-resolved canonical membership (from snapshot doctor `sourceLocator.path.sectionKey` through `inputSheetLayout.sections[]` to section-level canonical `groupId`); storage shape may be direct field(s) or normalized mapping.

### 7.4 DoctorGroup
`DoctorGroup` is a normalized concept whose values are template-defined.

Current ICU/HD template values:
- `ICU_ONLY`
- `ICU_HD`
- `HD_ONLY`

### 7.5 SlotType
`SlotType` is a normalized concept whose values are template-defined.

Current ICU/HD template values:
- `MICU_CALL`
- `MICU_STANDBY`
- `MHD_CALL`
- `MHD_STANDBY`

Standby remains a normal `SlotType` identity, not a special global solver mode. In current ICU/HD semantics, standby has fill-order implications and soft-score implications, but no standby-only hard validity rule.

### 7.6 SlotTypeDefinition
Normalized metadata for each `SlotType`, referenced by solver/scorer/reporting.

First-release minimum required fields (aligned to upstream guaranteed slot facts):
- `slotType` (identity)
- `displayLabel`

Optional metadata (not first-release minimum requirements):
- optional fairness grouping/classification
- optional reporting semantics (for example, `countsAsCall`, `countsAsStandby`)

Deferred/optional enrichment:
- `workloadWeight` (or equivalent burden weight) is optional and deferred unless introduced by a future contract checkpoint.

Note: solver fill order is strategy/policy; it should not be encoded as core slot metadata beyond brief policy references.

### 7.7 SlotDemand
Demand is explicit per `(dateKey, slotType)`:
- `requiredCount` is mandatory and first-class.
- In current ICU/HD first release, parser instantiates this from template slot declarations (`requiredCountPerDay`) across normalized days.
- Demand instantiation is template-declared and day-normalized; it is not sourced from snapshot point rows or hidden parser defaults.
- v1 core representation effectively assumed one demand unit per `(dateKey, slotType)`.
- v2 intentionally generalizes this via `requiredCount`, which may be `0`, `1`, or greater than `1`.
- This is an intentional v2 divergence from v1 core representation assumptions.
- Downstream adapters/writers may flatten to one-slot-per-row outputs if a target template requires that shape.

### 7.8 FixedAssignment
`FixedAssignment` is a normalized input-side fact representing an operator-prefilled assignment that parser/normalizer admitted as locked.

Minimum useful fields:
- `dateKey`
- `slotType`
- `doctorId`
- optional run-local stable identity (for example, `fixedAssignmentId`)
- recoverable source trace to snapshot-origin prefilled record/cell

Contract meaning:
- `FixedAssignment` is first-class normalized input, not an allocation result object.
- `FixedAssignment` is not movable by solver.
- `FixedAssignment` may exist even when that specific assignment would otherwise violate request-derived hard block, baseline eligibility, or ordinary back-to-back prohibition; this is a fixed-assignment-only exception.
- That exception does **not** widen general downstream eligibility or admissibility for later generated assignments.

## 8. Requests and normalized daily effects

### 8.1 Request
Captures per-doctor per-date request input:
- `doctorId`
- `dateKey`
- raw request text
- recognized raw tokens
- canonical request classes
- resolved machine effects
- parse issues (if any)

ICU/HD first-release request-language details (accepted raw vocabulary, raw-to-canonical mapping, canonical request classes, machine-effect mapping, combinations, duplicates, and request-level consumability rules) are defined in `docs/request_semantics_contract.md`.

Parser-stage issue authority remains top-level at `ParserResult.issues` (`docs/parser_normalizer_contract.md`). Request parse issues are mirrored onto normalized `Request` only when a normalized `Request` exists in a `CONSUMABLE` parser output.

### 8.2 DailyEffectState (normalized effects)
Normalized effect state separates machine semantics from policy severity. In current ICU/HD template-instance semantics:
- `CR` produces `callPreferencePositive` only.
- Same-day hard block (`sameDayHardBlock`) applies for `NC`, `FULL_DAY_OFF`, and `PM_OFF` classes.
- Previous-day call soft-penalty trigger (`prevDayCallSoftPenaltyTrigger`) applies for `FULL_DAY_OFF` and `PM_OFF` classes.
- No next-day derived effect exists.

### 8.3 Semantics vs severity policy
- Domain model stores **what effect exists**.
- Policy/scoring config determines **how strong the penalty/preference is**.
- `prevDayCallSoftPenaltyTrigger` is soft in the current ICU/HD template; severity may be high, but conceptually it remains soft (not hard invalidity).
- Later templates may make severity template-configurable without changing normalized effect shape.
- `CR` never overrides hard validity.

## 9. Eligibility and hard constraints

### 9.1 Baseline eligibility vs dynamic availability
- Baseline eligibility: slot-type/group compatibility (`EligibilityRule`).
- Dynamic availability: day-specific effect state from requests (hard blocks and soft effects).
- These are separate concepts and should be evaluated separately.

### 9.2 Core hard invariants
The model must support enforcing at least these hard invariants:
- Doctor must be eligible for the slot type.
- Same-day hard block forbids assignment on that date.
- A doctor cannot hold more than one slot on the same date.
- Back-to-back prohibition applies to call slots only.
- No standby-specific hard rule exists.
- One fill per demand unit (no double-fill of a single unit).

Hard invalidity must remain distinct from soft-objective terms.

## 10. Assignment and allocation result model

### 10.1 FixedAssignment semantics in solve state
`FixedAssignment` is part of normalized downstream-governing input semantics for solving.

Demand relationship:
- Fixed assignments count directly toward slot demand.
- Solver fills only residual unfilled demand after accounting for fixed assignments.

Occupancy and downstream-state relationship:
- Fixed assignments count as real assignments in schedule state.
- A doctor fixed on `(dateKey, slotType)` is occupied on that date.
- Fixed assignments must be considered when evaluating later generated assignments, including adjacent-day consequences.

Admissibility-override boundary:
- The override applies only to the fixed assignment itself.
- The only allowed fixed-assignment exception scope is request-derived hard block, baseline eligibility, and ordinary back-to-back prohibition (matching parser-boundary admission contract).
- It does not relax general legality checks for non-fixed generated assignments.

Relationship to allocation atoms/results:
- `FixedAssignment` is an input-side normalized fact.
- `AssignmentUnit` remains the allocation/retained assignment atom in v2 core output modeling.
- Downstream adapters/results may still represent final allocations via `AssignmentUnit`, but domain semantics must keep fixed preassigned facts distinct from solver-produced fill decisions.

### 10.2 AssignmentUnit atom
Smallest retained assignment unit:
- `(dateKey, slotType, unitIndex, doctorId | null)`

Notes:
- `unitIndex` preserves multiplicity when `requiredCount > 1`.
- `unitIndex` also preserves multiple explicit unfilled units.
- `doctorId = null` supports explicit unfilled demand representation.
- This is the normalized v2 core; a v1-style fixed per-day slot map is a compatibility/view/writeback projection for current ICU/HD, not the core representation.

### 10.3 AllocationResult
Minimum useful contents:
- multiplicity-safe collection (typically array/list) of `AssignmentUnit`
- unfilled-demand summary (by date/slot type)
- linkage to `ScoreResult`
- linkage to `ValidationIssue` list
- linkage to `SearchDiagnostics` / `TrialBatchResult` where retained
- run metadata needed for reproducibility/audit (for example, seed, run identifiers)

## 11. Score model

### 11.1 Direction and structure
- Score direction is fixed to **`HIGHER_IS_BETTER`**.
- `ScoreResult` includes:
  - `totalScore`
  - named component scores
  - optional deeper breakdowns for diagnostics/explainability

### 11.2 First-release component identifiers (v1-compatible naming)
For first release, keep current v1-derived component identifiers for compatibility:
- `unfilledPenalty`
- `pointBalanceWithinSection`
- `pointBalanceGlobal`
- `spacingPenalty`
- `preLeavePenalty`
- `crReward`
- `dualEligibleIcuBonus`
- `standbyAdjacencyPenalty`
- `standbyCountFairnessPenalty`

Clarifications:
- First-release naming follows current v1 names for compatibility.
- Future nomenclature cleanup is allowed later without changing underlying score concepts.
- Under `HIGHER_IS_BETTER`, reward terms contribute positively and penalty terms contribute negatively.
- `preLeavePenalty` is a legacy label; its trigger set is broader than leave-only codes.
- `pointBalanceWithinSection` and `pointBalanceGlobal` are both retained in first release even though their intents partially overlap.

### 11.3 Soft preferences and penalties
- `CR` remains soft but can be strongly prioritized by scoring/search policy.
- `prevDayCallSoftPenaltyTrigger` remains soft but penalty-bearing, with policy-controlled magnitude.

## 12. Search diagnostics and retained search artifacts

### 12.1 Why this exists
v1 lost too much information from non-winning trials. v2 keeps concise, structured search artifacts so outcomes are explainable and reproducible.

### 12.2 SearchDiagnostics
Aggregate transparency object, typically including:
- candidate counts and validity funnel summaries
- rejection/failure counts by reason
- score distribution summaries (at least for retained candidates)
- near-miss/top-K summaries when enabled

### 12.3 TrialCandidate
Represents one generated candidate:
- compact assignment summary
- validity status / failure metadata (if invalid during exploration)
- score summary (and optional component breakdown)
- minimal identifiers tying candidate to batch/chunk/run

### 12.4 TrialBatchResult
Represents one search batch/chunk:
- batch/chunk identifier
- best candidate in batch
- optional retained candidates per retention policy
- retention metadata (mode, limits, truncation flags)

### 12.5 Retention policy
- **Default**: best-only retention.
- **Optional**: top-K retained candidates.
- **Optional**: full candidate retention for a batch/chunk.
- **Optional (debug/benchmark/export)**: retain all chunk results and associated diagnostics payloads.

## 13. Validation issue model
Use one unified structured issue shape across parsing, normalization, validation, and solve outputs.

Minimum fields:
- `severity`
- `code`
- `message`
- `context` (for example, entity references/path/date/doctor/slot)

Keep shape simple and stable; richer subfields can be layered later without changing the core contract.

## 14. Writeback boundary
- Writeback formatting/mapping is an adapter concern, not a core domain concern.
- Core allocation remains `doctorId`-based.
- Writer may resolve `doctorId` to display names or sheet-specific cells at the boundary.
- Adapters may project normalized `AssignmentUnit` collections into template-specific shapes.

## 15. First-release deferred extensions
The following items are intentionally deferred and are not required to change first-release model semantics:
- **Retention payload depth extension**: finalize exact retained payload shape for full-candidate retention mode (per-candidate/per-chunk verbosity).
- **Naming refinement follow-up**: confirm whether `DailyEffectState` remains the long-term label or receives a naming-only refinement in a later revision.
- **Scoring nomenclature follow-up**: evaluate future naming cleanup beyond first-release v1-compatible component identifiers, without changing underlying score concepts.
