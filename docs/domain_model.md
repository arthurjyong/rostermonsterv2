# Domain Model Draft

## 1. Purpose
- Define the normalized internal model used by v2 after parsing and before solving, scoring, diagnostics, and writeback.
- Be conservative and v1-faithful where possible.
- Explicitly document where v2 intentionally diverges from v1.

## 2. Scope
- This document defines the main internal entities, relationships, invariants, result objects, and search/debug artifacts.
- This document does not define solver algorithm details, sheet UI details, or cloud deployment details.

## 3. Key design principles
- The normalized model should be independent of raw sheet row/column layout where practical.
- Hard validity rules must be modeled explicitly.
- Penalty-bearing effects must be modeled explicitly.
- Search transparency is a first-class requirement, not an optional extra.
- The system must support both normal best-only retention and optional deep candidate retention for debugging/benchmarking.

## 4. v1 compatibility and intentional v2 differences
### 4.1 Preserve from v1
- doctor/group/slot/request semantics should remain compatible with ICU/HD v1 unless explicitly changed
- standby remains a slot type
- request parsing still separates same-day hard block from previous-day penalty effect
- CR remains a soft preference, not a hard entitlement

### 4.2 Intentional v2 differences
- v2 adopts higher-is-better score direction
- slot demand is modeled explicitly with requiredCount
- search/debug artifacts become first-class modeled outputs
- the system may optionally retain all generated candidates in a batch/chunk

## 5. Pipeline position
- Sheet/template input
- Sheet adapter / parser
- Normalization into domain model
- Solver / scorer / search diagnostics consume this model
- Writeback adapter consumes result objects derived from this model

## 6. Core entity overview
- RosterPeriod
- RosterDay
- Doctor
- DoctorGroup
- SlotType
- SlotDemand
- RequestCodeDefinition
- Request
- AvailabilityState (or RequestEffect-derived daily state)
- EligibilityRule
- Assignment
- AllocationResult
- ScoreResult
- ValidationIssue
- SearchDiagnostics
- TrialCandidate
- TrialBatchResult

## 7. Core identities and reference data

### 7.1 RosterPeriod
- what it represents
- required fields
- identity/scoping

### 7.2 RosterDay
- dateKey
- ordering/index
- point-bearing metadata if relevant

### 7.3 Doctor
- runtime identity uses doctorId
- displayName is human-facing
- optional externalDoctorId may be supported later
- group membership belongs here or via separate mapping

### 7.4 DoctorGroup
- current ICU/HD example groups
- future templates may define their own groups

### 7.5 SlotType
- slot types are duty categories
- current ICU/HD example slot types
- standby is a slot type in the model, even if solver may fill it later

### 7.6 SlotDemand
- explicit per-date, per-slot demand
- requiredCount is first-class
- v1-compatible ICU/HD default is requiredCount = 1

## 8. Requests and normalized daily effects

### 8.1 RequestCodeDefinition
- raw code
- human label if available
- normalized machine effects

### 8.2 Request
- doctorId
- dateKey
- raw cell text
- parsed codes
- parse issues if relevant

### 8.3 Normalized daily effects
- same-day hard block
- previous-day penalty-bearing effect
- CR preference signal
- separate semantics from policy severity

### 8.4 Effect semantics vs policy severity
- some effects are intrinsically hard-validity effects
- some effects are penalty-bearing effects
- penalty magnitude is policy-defined, not hardcoded by the domain model

## 9. Eligibility and hard constraints

### 9.1 Baseline eligibility
- slotType to allowedGroups
- doctor/group eligibility is distinct from date-specific availability

### 9.2 Dynamic availability
- request-derived daily effects modify whether a doctor may or should be assigned

### 9.3 Core hard invariants
- no assignment to ineligible slot
- no same-day assignment when same-day hard-blocked
- at most one slot per doctor per date
- no back-to-back call where policy defines it as hard
- one fill per demand unit

## 10. Assignment and allocation result model

### 10.1 Assignment
- smallest assignment atom is dateKey + slotType + doctorId|null

### 10.2 AllocationResult
- assignments
- unfilled demand
- summary
- metadata
- linked score result
- linked validation issues
- linked diagnostics if retained

## 11. Score model

### 11.1 ScoreResult
- totalScore
- direction = HIGHER_IS_BETTER
- named component scores
- optional deeper breakdowns

### 11.2 Historical note
- v1 used lower-is-better
- v2 intentionally reverses score direction
- all v2 component definitions must remain consistent with higher-is-better semantics

### 11.3 Preference and penalty policy
- CR remains soft but may be strongly prioritized
- previous-day effects remain penalty-bearing, with policy-controlled severity

## 12. Search diagnostics and retained search artifacts

### 12.1 Why this exists
- v1 lost too much information from non-winning trials/candidates
- v2 requires first-class search transparency

### 12.2 SearchDiagnostics
- candidate pool summaries
- rejection counts by reason
- hard-constraint failure counts
- per-trial score summaries
- top-K near-miss summaries if retained

### 12.3 TrialCandidate
- one generated candidate roster within a trial/batch context
- compact assignment representation
- score summary
- optional component breakdown
- optional rejection/failure metadata

### 12.4 TrialBatchResult
- result of one batch/chunk of many generated candidates
- best candidate
- optional retained candidates
- retention metadata/policy

### 12.5 Retention policy
- default may retain only best candidate
- system must support optional full retention of all generated candidates in a batch/chunk for debugging/benchmarking/export

## 13. Validation issue model
- unified structured issue shape
- severity
- code
- message
- context/scope/path if useful

## 14. Writeback boundary
- writeback is adapter-specific
- domain model should remain mostly sheet-agnostic
- output adapters may resolve doctorId to displayName for sheet writing

## 15. Open questions / explicitly deferred choices
- exact naming of AvailabilityState vs RequestEffect-derived daily state
- default retention depth outside debug/benchmark mode
- exact compact shape of retained TrialCandidate payload
- exact score component list to standardize in first release