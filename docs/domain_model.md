# Domain Model Draft

## 1. Purpose
- Define the normalized internal model used in v2 **after parser/normalizer** and **before solver, scorer, diagnostics, and writeback adapter**.
- Provide an implementation-facing contract that is conservative, practical, and grounded in known v1 behavior.
- Explicitly mark where v2 intentionally diverges from v1 so implementers do not accidentally regress semantics.

## 2. Scope
This document covers:
- Core domain entities and relationships.
- Identity/reference data needed by solver/scorer.
- Hard-constraint semantics and assignment invariants.
- Request-code semantics vs normalized machine effects.
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

## 4. v1 compatibility and intentional v2 differences

### 4.1 Preserve from v1
- Runtime doctor identity is `doctorId`; display name is human-facing/output-facing.
- Current concrete doctor groups remain:
  - `ICU_ONLY`
  - `ICU_HD`
  - `HD_ONLY`
- Current concrete slot types remain:
  - `MICU_CALL`
  - `MICU_STANDBY`
  - `MHD_CALL`
  - `MHD_STANDBY`
- Standby remains a real slot type in the normalized model.
- Request parsing remains split between raw request code and normalized machine effects.
- `CR` remains a soft preference signal and never overrides hard validity.

### 4.2 Intentional v2 differences
- Score direction is **`HIGHER_IS_BETTER`** (v1 was lower-is-better).
- Slot demand is explicit via `SlotDemand.requiredCount` (instead of implicit one-slot assumptions).
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
- **`DoctorGroup`**: group taxonomy used for slot eligibility.
- **`SlotType`**: duty category identity (includes standby categories).
- **`SlotDemand`**: explicit demand units for `(date, slotType)` with `requiredCount`.
- **`RequestCodeDefinition`**: mapping from raw request code to normalized effect semantics.
- **`Request`**: raw/parsed per-doctor per-day request facts.
- **`DailyEffectState`**: normalized day-level machine effects derived from requests.
- **`EligibilityRule`**: baseline eligibility mapping (for example, slot type to allowed groups).
- **`Assignment`**: smallest assignment atom for one demand unit.
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
- Group membership can be direct field(s) or normalized mapping; semantics must remain explicit.

### 7.4 DoctorGroup
Current v1-grounded values:
- `ICU_ONLY`
- `ICU_HD`
- `HD_ONLY`

### 7.5 SlotType
Current v1-grounded values:
- `MICU_CALL`
- `MICU_STANDBY`
- `MHD_CALL`
- `MHD_STANDBY`

Important: slot-type identity is domain semantics. Fill order (for example, call before standby) is solver strategy, not slot-type definition.

### 7.6 SlotDemand
Demand is explicit per `(dateKey, slotType)`:
- `requiredCount` is mandatory and first-class.
- v1-compatible ICU/HD default is often `requiredCount = 1`, but the model must not hardcode that assumption.

## 8. Requests and normalized daily effects

### 8.1 RequestCodeDefinition
Defines request-code semantics once:
- raw code identity (for example, `AL`, `TL`, `X`, `CR`)
- optional human label
- normalized machine effects produced by that code

### 8.2 Request
Captures per-doctor per-date request input:
- `doctorId`
- `dateKey`
- raw request text
- parsed code list
- parse issues (if any)

### 8.3 DailyEffectState (normalized effects)
Normalized effect state separates machine semantics from policy severity. Core effects include:
- **Hard same-day block**: doctor cannot be assigned on that date.
- **Previous-day leave/training-related effect**: penalty-bearing normalized effect on following day; not intrinsically hard-invalid.
- **`CR` preference signal**: soft preference marker for scoring/search prioritization.

### 8.4 Semantics vs severity policy
- Domain model stores **what effect exists**.
- Policy/scoring config determines **how strong the penalty/preference is**.
- Previous-day penalty severity may range from negligible to effectively prohibitive, but remains policy-defined unless explicitly promoted to hard rule.

## 9. Eligibility and hard constraints

### 9.1 Baseline eligibility vs dynamic availability
- Baseline eligibility: slot-type/group compatibility (`EligibilityRule`).
- Dynamic availability: day-specific effect state from requests (hard block and soft effects).
- These are separate concepts and should be evaluated separately.

### 9.2 Core hard invariants
The model must support enforcing at least these hard invariants:
- No assignment to an ineligible slot.
- No assignment when same-day hard-blocked.
- At most one slot per doctor per date.
- Back-to-back call hard rule where policy/template defines it as hard.
- One fill per demand unit (no double-fill of a single unit).

## 10. Assignment and allocation result model

### 10.1 Assignment atom
Smallest assignment unit:
- `(dateKey, slotType, doctorId | null)`

`null` supports explicit representation of unfilled demand units.

### 10.2 AllocationResult
Minimum useful contents:
- assignment set (including explicit unfilled units where applicable)
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

### 11.2 Historical note
- v1 scoring convention was lower-is-better.
- v2 intentionally reverses this.
- Component definitions must be sign-consistent with higher-is-better to avoid mixed semantics.

### 11.3 Soft preferences and penalties
- `CR` remains soft but can be strongly prioritized by scoring/search policy.
- Previous-day leave/training effect remains penalty-bearing by default, with policy-controlled magnitude.

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

## 15. Open questions / explicitly deferred choices
- [TBD] Exact retained payload shape in full-candidate retention mode (how verbose per candidate/chunk).
- [TBD] Final standardized score component list for first release.
- [TBD] Whether `DailyEffectState` remains final naming or is renamed before contract freeze.
