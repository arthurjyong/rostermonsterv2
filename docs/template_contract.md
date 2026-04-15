# Department Template Contract (First-Release Normative)

## 1. Purpose
A department template is a **declarative artifact** that defines department-specific roster structure and binding/mapping surfaces so the reusable allocation core can operate correctly.

The template is the primary place where department policy is declared for first release.

## 2. Scope / non-scope

### In scope
A template may declare department-specific facts and mappings, including:
- slot model (slot types and slot definitions)
- doctor-group model
- first-release eligibility mapping (group-based only: `slot -> groups`)
- request-semantics binding surface at the template boundary
- sheet layout mapping
- output mapping
- scoring section presence (explicit minimal first-release stub)

### Out of scope
A template must **not** contain:
- Google Sheets I/O implementation logic
- parser implementation logic
- rule-engine implementation logic
- solver/search implementation logic
- execution/orchestration behavior
- arbitrary executable code

## 3. Contract role and boundary
The template contract defines **what the department declares**, not **how the engine implements compute**.

Normative boundary:
- Template = declarative structure, semantics, and mappings.
- Core layers (adapter/parser/rule/solver/writer) = implementation.

Department-specific policy should be expressed in the template whenever possible and must not be silently hidden in parser, writer, or sheet-adapter code outside declared template mappings.

## 4. Contract status and first-release posture
This contract is **normative** for first release and is intended to be depended on by parser, adapter, and downstream layers.

First-release posture:
- Maintainer-curated templates.
- No self-serve template onboarding.
- Prefer explicit, stable rules over flexible but ambiguous behavior.

## 5. Versioning and stability

### 5.1 Versioned object
The versioned object is the **department structural template**, not the monthly roster instance.

### 5.2 Stable parts of a released template
Within a released template version, the following are stable contract surfaces:
- slot definitions
- doctor groups
- group-based eligibility mapping
- request semantics binding
- sheet layout mapping contract
- output mapping contract
- scoring section shape

### 5.3 Changes that require a version bump
A version bump is required when structural or semantic behavior changes in ways that affect interpretation, validation, or code assumptions, including changes to:
- slot model
- template-declared slot demand counts (`requiredCountPerDay`)
- doctor-group model
- doctor-group derivation declarations (including section-level canonical `groupId` mappings)
- eligibility logic
- request semantics binding target (`contractId` / `contractVersion`)
- logical sheet/output mapping contract

### 5.4 Changes that do not require a version bump
Routine month-to-month variation does **not** require a version bump when the same approved structural template still applies, including:
- roster period/dates
- doctor list
- doctor count
- layout movement that is an expected consequence of operational data size changes, while preserving the same logical mapping contract

## 6. Required template sections
For first release, each template must define at minimum:

1. **Template identity**
   - template id / department id
   - template version

2. **Slot definitions**
   - template-local slot identifiers and labels
   - slot semantics used by eligibility, rules, and output mapping
   - template-declared fixed per-day demand per slot for first release (`requiredCountPerDay`)

3. **Doctor groups**
   - group identifiers
   - explicit group-membership derivation inputs
   - for ICU/HD first release, doctor-group derivation is section-based through declared input layout sections, where each section declares canonical `groupId`

4. **Eligibility mapping**
   - first-release group-based eligibility only: which groups are eligible for which slot types (`slot -> groups`)
   - no doctor-level override layer unless introduced by a future contract
   - deterministic resolution behavior with no hidden code-side overrides

5. **Request semantics mapping**
   - binding to the applicable request semantics contract via contract identity/version

   For ICU/HD first release, detailed request-language semantics (including raw grammar/tokens, raw-to-canonical mapping, machine-effect mapping, combinations/duplicates handling, and consumability outcomes) are defined in `docs/request_semantics_contract.md` and are bound through template request-semantics binding.
   Request-driven blocking / previous-day effects are also realized through that bound request semantics contract; template artifacts must not duplicate request-semantics tables solely to restate those effects.

6. **Sheet layout mapping**
   - logical anchors/sections and mapping assumptions required for parsing
   - enough information for adapter/parser to locate the declared logical regions

7. **Output mapping**
   - logical destination mapping from allocation outputs to sheet/output surfaces

8. **Scoring section**
   - explicit minimal first-release stub:
     - `scoring.templateKnobs: []`
   - richer scoring-knob surfaces are deferred unless introduced by a future contract checkpoint

### First-release determinism rules for required sections
- **Identifier policy:** slot and group identifiers must be explicit, stable within a template version, and unique within their section.
- **Overlapping groups:** allowed when explicitly declared; eligibility semantics must remain deterministic.
- **Eligibility precedence:** no implicit precedence; effective eligibility must be derivable directly from template declarations.
- **Request priority representation:** request semantics are represented through the bound request semantics contract plus explicit template declarations, not ad hoc procedural priority code.

## 7. Optional template sections
Optional sections are allowed only when they remain declarative and do not violate core boundary rules. Examples:
- additional metadata labels for reporting
- optional diagnostics-oriented mapping metadata

If an optional section is present, it becomes part of the released template’s stable contract for that version.

## 8. Governance and change control

### 8.1 Change authority
- **Operators** may change routine monthly roster data.
- **Maintainers** control template structural/semantic changes.

### 8.2 Review requirement
Structural and semantic template changes require maintainer review in first release.

### 8.3 Controlled change flow
Template changes must follow controlled change flow:
1. propose change and classify it (routine variation vs template change)
2. update template contract artifact
3. run validation checks
4. apply version bump where required
5. provide migration notes when interpretation or mapping behavior changes

## 9. Sheet layout drift and mapping compatibility
Absolute row/column movement alone does **not** automatically imply a template change.

Accepted as routine variation:
- sheet regions shift because doctor rows increase/decrease
- adapter/parser can still locate and interpret the same logical regions using the same mapping contract

Template/mapping change (not routine):
- logical anchors change
- expected sections change
- mapping assumptions change
- output region interpretation changes

Such mapping changes must be handled as template/mapping updates and must not be silently absorbed in implementation code.

## 10. Validation expectations
At minimum, first-release validation should confirm:
- required sections exist and are internally consistent
- identifiers satisfy uniqueness/stability rules
- eligibility mappings are deterministic and well-formed
- request semantics binding is present and points to an approved request semantics contract identity/version
- sheet/output mappings are structurally valid against declared logical anchors
- scoring section follows the explicit minimal first-release stub

Validation lifecycle expectation:
- routine roster data updates are operational checks
- structural/semantic template updates are maintainer-reviewed contract changes

## 11. First-release scope limits / notes
- This contract is intentionally strict for first release.
- Advanced flexibility that weakens determinism or boundary clarity is deferred.
- The goal is reliable curated template operation, not generalized self-serve template authoring.
