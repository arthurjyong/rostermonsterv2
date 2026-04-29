# Sheet Generation Contract (First-Release, Operator-Facing Shell)

## 1. Purpose and status
This document defines the first-release contract for **template-driven generation of the full operator-facing sheet shell** for ICU/HD-style workflows.

Status:
- Contract-first, implementation-facing checkpoint.
- Narrow and normative for generation requirements/boundaries.
- Not a generator procedure spec.

Boundary with adjacent concerns:
- **Template artifact contract** declares structural inputs used by generation.
- **This contract** declares what generation must produce and what edits are allowed after generation.
- **Parser contracts** govern how populated sheets are interpreted after operators enter data, including any later-populated lower roster/output shell cells.
- **Writer/orchestration mechanics** remain outside this document.

## 2. First-release generation goal
Generation must produce the **full operator-facing sheet shell** that is:
- template-driven,
- operator-facing,
- structurally close to the current ICU/HD workflow.

For first release:
- generation may emit this shell empty,
- the generated shell must already include the template-declared lower roster/output shell surfaces that operators may later prefill,
- structural fidelity is required,
- exact cosmetic/pixel-perfect fidelity is not required.

## 3. Generation inputs (operator-supplied)
Generation accepts:
- `department` (operator-facing selector; first-release label: `CGH ICU/HD Call`)
- `periodStartDate`
- `periodEndDate`
- `doctorCountByGroup`

Input ownership notes:
- Department selection resolves to the department-owned template identity/provenance behind the scenes.
- Period dates define generated day-axis span.
- `doctorCountByGroup` fixes placeholder row counts/manpower structure per template-declared ICU/HD group section for that generated roster using familiar operator-facing group labels.
- If manpower counts are wrong after generation, operators should generate a new empty roster (new file or new tab) rather than insert/delete rows inside generated sections.

## 3A. Generation output target
For first release, generation should support either operator-facing output mode:
- create a new spreadsheet file, or
- create a new tab/worksheet in a selected existing spreadsheet.

This is a workflow-level contract requirement, not an implementation-mechanics specification.

Spreadsheet reference input form:
- When the existing-spreadsheet mode is selected, the operator-supplied `spreadsheetId` input accepts either a bare Google Sheets spreadsheet ID or a full Google Sheets URL containing one (for example a URL copied from the browser address bar).
- Normalization from URL to bare ID is a shared concern in the generator's config helper, not a launcher-specific concern. The extraction rule is defined in §12.5.
- This widening is backward-compatible: existing callers passing a bare ID continue to work unchanged.

## 4. Template-owned generation facts
Generation must treat the following as template-owned declarations:
- which groups/sections exist,
- section and structural ordering,
- visible in-sheet title/header block content (including department-facing label),
- call-point row presence/default behavior,
- output-shell structural surfaces.

Generation must not invent alternative logical section orders outside template declaration.

## 5. Required generated structural surfaces
Generated shell must include at least:
1. visible in-sheet title/header block (including department-facing label),
2. date axis,
3. weekday row,
4. explicit section headers for grouped doctor-entry sections,
5. placeholder doctor rows with blank doctor-name cells,
6. request-entry cells,
7. call-point rows (including MICU and MHD point rows with defaults),
8. lower roster/output shell rows and cells (in template-declared slot order),
9. weekend/public holiday highlighting,
10. legend/Descriptions block (non-structural adjunct content).

These are required structural regions for first release.
The lower roster/output shell is part of the generated first-release sheet shell, not a downstream-only writeback target.

## 6. Operator-allowed edits after generation
After generation, operators may:
- fill doctor names in column A,
- enter request codes in editable request cells,
- edit call-point values,
- prefill lower roster/output shell cells before any later completion pass.

Parser-facing expectation:
- Names entered in column A become source doctor names for later parsing.
- The lower roster/output shell remains template-owned declared structure after generation.
- When operators prefill lower-shell cells, those populated cells become an allowed input surface for later partial-completion parsing contracts.
- Parser-side handling of those populated cells (including `prefilledAssignmentRecords`, parser-stage `NON_CONSUMABLE` boundaries, and fixed-assignment override admission boundaries) is defined in `docs/parser_normalizer_contract.md`.
- Parser robustness relies on template-declared section/segment structure.
- This contract does not define parser semantics for those populated lower-shell cells.
- If generated manpower sizing is wrong, operators should regenerate a new empty roster instead of mutating section row counts.

## 7. Disallowed structural drift
End users must not perform major structural rearrangement of template-owned logical regions, including:
- arbitrary reordering/moving of declared sections,
- adding rows within a declared section,
- deleting rows within a declared section,
- changes that break declared structural region boundaries,
- changes that invalidate template-declared logical ordering assumptions.

## 8. Weekend/public holiday highlighting and default call-point behavior
First release requires generated sheet behavior for:
- weekend classification/highlighting,
- Singapore public holiday classification/highlighting.

Holiday source requirement:
- use an authoritative Singapore public holiday source/reference in principle,
- remain source-agnostic at contract level (no mandatory lock to one specific live API in this document).

Default call-point rule (generation behavior):

| Day n classification | Day n+1 classification | Default call point |
|---|---|---:|
| Ordinary weekday | Ordinary weekday | 1 |
| Ordinary weekday | Weekend or public holiday | 1.75 |
| Weekend or public holiday | Weekend or public holiday | 2 |
| Weekend or public holiday | Ordinary weekday | 1.5 |

Notes:
- These defaults are generation-time behavior, not parser semantics.
- Manual operator override of generated call points is allowed after generation.

## 9. Editable surfaces, protected surfaces, and validation expectations
MVP generation must distinguish between editable operator-input surfaces and protected template-owned structural surfaces, where platform support exists. Generated sheets should be maximally locked except for explicit operator-input surfaces.

Editable surfaces for first release include:
- blank doctor-name cells in generated placeholder rows,
- doctor request-entry cells,
- call-point cells,
- lower-shell cells where operator prefill is allowed.

Protected/non-editable template-owned surfaces for first release include:
- date axis,
- weekday row,
- section headers,
- fixed structural layout regions,
- generated section row structure sized from `doctorCountByGroup`,
- lower-shell assignment-row structure.

Validation expectations:
- generation should apply constrained request-entry validation where practical,
- parser re-validation remains authoritative for all downstream interpretation and acceptance,
- protection posture should prevent section-level structural drift (including row insertion/deletion within sections) so manpower sizing remains fixed for that generated roster,
- implementation mechanics (for example exact Google Sheets protection/validation setup) remain outside this contract.

## 10. Structural vs cosmetic scope
Required in first release:
- structural surfaces listed in Section 5,
- unambiguous generated raw date text in date headers sufficient for downstream parser/date normalization work.

Not required in first release (optional/cosmetic):
- exact cosmetic styling for weekend/public holiday highlighting,
- cosmetic styling details for legend/Descriptions content,
- FAQ/help narrative blocks,
- pixel-perfect visual replication.

Legend/Descriptions note:
- legend/Descriptions content is included in first-release generation for operator familiarity, but remains non-structural adjunct content.
- parser/generation structural assumptions must not depend on legend/Descriptions presence or exact cosmetic form.

## 11. Relationship to adjacent docs
- `docs/template_artifact_contract.md`: source of template-owned structural declarations used by generation.
- `docs/blueprint.md`: architecture-level positioning that generation is part of first-release operator-facing workflow direction.
- `docs/roadmap.md`: sequencing intent that sheet generation is a planned first-release integration capability, not an unbounded distant optional add-on.

This contract intentionally does not redefine:
- parser semantics,
- snapshot schema,
- writer/orchestrator procedures,
- low-level external API integration mechanics.

## 11A. Scorer Config tab (added under `docs/decision_log.md` D-0037)
The launcher generates a separate **Scorer Config tab** in the source spreadsheet alongside the request-entry tab. The tab carries the operator-tuneable scoring component weight cells declared in `docs/scorer_contract.md` v3 §11 + §15 — one cell per first-release component identifier in `docs/domain_model.md` §11.2 (nine cells: `unfilledPenalty`, `pointBalanceWithinSection`, `pointBalanceGlobal`, `spacingPenalty`, `preLeavePenalty`, `crReward`, `dualEligibleIcuBonus`, `standbyAdjacencyPenalty`, `standbyCountFairnessPenalty`).

Settled constraints:
- Tab is generated alongside the request-entry tab in the same source spreadsheet (single-spreadsheet-multi-tab shape).
- Each component-weight cell is pre-populated from `docs/template_artifact_contract.md` §11 `scoring.componentWeights` defaults at generation time.
- Each component-weight cell is **operator-editable** post-generation; operator-supplied values override template defaults at run time per the parser overlay rule in `docs/parser_normalizer_contract.md` §9.
- The tab is template-owned structural in its layout (which cells exist, where they sit) but operator-input in its values; that classification mirrors `docs/template_artifact_contract.md` §9 `surfaceOwnership` discipline applied to this new surface.
- The per-day call-point cells (`MICU Call Point`, `MHD Call Point` rows) stay on the request-entry tab where they already live per `docs/sheet_generation_contract.md` §8 + the existing `pointRows` declaration in `docs/template_artifact_contract.md` §9. Both surfaces (component weights on the Scorer Config tab; per-day call-point cells on the request-entry tab) flow through the snapshot's `scoringConfigRecords` per `docs/snapshot_contract.md` §11A under the same uniform extraction discipline.
- Validation expectations (visible vs background-only validation, locking posture, format constraints) are implementation-slice concerns deferred to the launcher implementation pass.

Explicitly out of scope at contract level:
- Concrete cell layout (rows, columns, labels, decoration). Layout choice is left to the launcher implementation slice; the contract pins **what cells must exist** (one per first-release component identifier), not where they sit.
- Validation behavior on operator edits (numeric-only enforcement, sign-orientation hints in the cell, etc.) — these are implementation-slice UX concerns; the parser-side admission discipline per `docs/parser_normalizer_contract.md` §14 is the normative correctness layer.

This section adds a new operator-facing structural surface to the existing M1 generation scope, but does not reopen any prior M1 generation decisions — the request-entry tab and lower-shell surfaces continue exactly as `docs/sheet_generation_contract.md` §5 / §6 / §8 / §9 declare them.

## 11B. Launcher-attached DeveloperMetadata (added under `docs/decision_log.md` D-0043)
The launcher attaches Apps Script `DeveloperMetadata` to specific spreadsheet locations at generation time so the snapshot extractor (`docs/snapshot_adapter_contract.md`) can locate sheet regions stably across operator edits. Cells inside an anchored row are located by column offset; metadata-anchored rows survive operator row inserts/deletes because Apps Script DeveloperMetadata follows the row.

**Sheet level** (existing M1.1 surface; pre-D-0043):
- `rosterMonster:tabType` — value `requestEntry` on the request-entry tab; value `scorerConfig` on the Scorer Config tab.
- `rosterMonster:templateVersion` — value matching the template artifact version.
- `rosterMonster:runId` — value matching the launcher's per-run identifier (used for tab-name pairing per §11A).

**Sheet level on the request-entry tab** (NEW under D-0043 sub-decision 1 — drives extractor cardinality validation per D-0043 sub-decision 3):
- `rosterMonster:expectedDoctorCount.<sectionKey>` per declared section, value = integer doctor-row count the launcher generated for that section (e.g., `expectedDoctorCount.MICU = 5`). Variable cardinality — depends on the operator-supplied doctor counts at launch time.
- `rosterMonster:expectedDayCount` — integer day-axis day count the launcher generated. Variable cardinality — depends on the period length.
- `rosterMonster:expectedAssignmentRowCount` — integer cross-product count of declared output surfaces × per-surface assignment rows (e.g., `4` for the ICU/HD first-release `lowerRosterAssignments` surface with 4 rows). Drives the partial-loss check on the assignmentRow anchor; absent this count, a deleted assignment row would silently omit its prefilled assignments from the snapshot.

**Per-row on the request-entry tab** (NEW under D-0043):
- `rosterMonster:section` on each section header row, value = template-declared `inputSheetSections.sectionKey` (`MICU` | `MICU_HD` | `MHD` for ICU/HD first release).
- `rosterMonster:dayAxis` on the day-axis row, value = `true` (single-row anchor).
- `rosterMonster:doctorRow` on each doctor row, value = `<sectionKey>:<doctorIndexInSection>` (zero-indexed within the section).
- `rosterMonster:callPointRow` on each call-point row, value = template-declared `pointRows.rowKey` (`MICU_CALL_POINT` | `MHD_CALL_POINT`).
- `rosterMonster:assignmentRow` on each prefilled-assignment shell row, value = `<surfaceId>:<rowOffset>` for output-mapping locator alignment per `docs/snapshot_contract.md` §10.

**Per-row on the Scorer Config tab** (existing under M2 C7 / D-0037):
- `rosterMonster:componentId` on each component-weight row, value = canonical `componentId` per `docs/domain_model.md` §11.2.

These metadata anchors are normative for sheets generated under D-0041 and onward (i.e., sheets carrying the bound shim per `docs/snapshot_adapter_contract.md` §3). Pre-D-0041 sheets do not carry the per-row anchors; per `docs/decision_log.md` D-0043 the snapshot extractor hard-fails on missing anchors rather than falling back to visible-text lookup, so pre-D-0041 sheets must be regenerated to be extractable.

Out-of-scope at contract level:
- Concrete metadata-finder query patterns and column-offset values. These are implementation-slice concerns owned by the snapshot adapter (`docs/snapshot_adapter_contract.md` §6).

## 12. Operator-facing launcher surface (M1.1)

### 12.1 Purpose and status
This section adds the first-release operator-facing launcher surface on top of the existing generation entrypoints. It is a narrow operator-facing addendum and does not alter generation semantics.

Status:
- Operator-facing surface contract, narrow.
- Does not introduce new generation semantics — it wraps the existing `generateIntoNewSpreadsheet` / `generateIntoExistingSpreadsheet` entrypoints without altering their output.
- Pilot-scope (named monthly-rotation operators only); not a public-launcher specification.

### 12.2 Architectural placement
The launcher is a thin front-end inside the sheet-adapter layer (Blueprint §7 boundary #2). It is not a new architectural boundary. The launcher must not:
- absorb parser/normalizer/rule/solver/scorer logic,
- alter generated sheet structure, semantics, or the 10 structural surfaces required by §5,
- persist per-operator state beyond Google's own OAuth session.

### 12.3 Operator access model
Access gating is external to the launcher:
- Identity is established by Google OAuth, with the launcher deployed "Execute as: User accessing the web app" so generation runs in the operator's own Drive under their account.
- Authorization is granted by adding the operator's Google account to the GCP OAuth consent screen's **Test Users** list for the launcher's GCP project.
- Monthly operator rotation is handled by the maintainer editing the Test Users list between cycles; it is not encoded in app logic.

The launcher itself does not maintain or check a separate operator allowlist for first-release pilot scope.

### 12.4 Operator input fields
The launcher form collects only the fields already required by the existing generation entrypoints:
- `department` — single-option selector, fixed to `CGH ICU/HD Call` for first release. The selector is kept visible rather than hidden, so multi-department future direction remains obvious to operators and reviewers.
- `periodStartDate`, `periodEndDate` — date inputs in the template-declared year handling window.
- `doctorCountByGroup` — three non-negative integer inputs corresponding to the template-declared groups in order (for ICU/HD first release: `ICU_ONLY`, `ICU_HD`, `HD_ONLY`).
- Output mode — radio selector: "New spreadsheet file" or "New tab in an existing spreadsheet," mapped to §3A's two modes.
- `spreadsheetId` — a single combined text field shown only when the "new tab in existing spreadsheet" mode is selected. The field accepts either a bare spreadsheet ID or a full Google Sheets URL containing one (see §3A and §12.5).

### 12.5 Spreadsheet reference extraction rule
Normalization runs centrally in the generator config helper (not in the launcher). The shared rule, applied in order:
1. Trim whitespace from the supplied value.
2. If the value matches `https?://docs\.google\.com/spreadsheets/(?:u/\d+/)?d/([a-zA-Z0-9_-]{20,})`, take capture group 1 as the bare spreadsheet ID. The optional `u/<n>/` segment covers account-scoped browser-bar URLs that Google emits when a user has multiple signed-in Google accounts (for example `https://docs.google.com/spreadsheets/u/1/d/<id>/edit`). The `docs.google.com` host anchor and the `{20,}` minimum-length capture are both deliberate: they prevent false matches on non-Google hosts sharing the same path shape, and on published-link URLs of the form `/spreadsheets/d/e/<published-id>/pubhtml` where a naive regex would otherwise capture a single-character `e` segment and then fail opaquely at `openById`.
3. Else, if the value itself matches the bare-ID shape `^[a-zA-Z0-9_-]{20,}$`, accept as-is.
4. Else, throw an operator-facing error along the lines of: "Could not recognize spreadsheet reference — paste the full link from the browser bar, or the spreadsheet ID."

Downstream errors from `SpreadsheetApp.openById` (missing access, deleted sheet, or a syntactically valid but wrong ID) continue to surface the existing human-readable error from the generation entrypoint; the extraction rule above is input-shape normalization only.

### 12.6 Operator output surface
- On success, the operator is shown a clickable link to the generated spreadsheet or new tab, plus an echo of the parameters used for the run.
- On failure, the operator is shown the human-readable error produced by config validation, reference extraction (§12.5), or the existing generation code path. No partial-state commit is made that the operator would need to clean up by hand.

### 12.7 Statelessness
The launcher is stateless per submission. Each form submission flows through `doGet()` → `google.script.run` → an existing generation entrypoint → a single result surface. No per-operator data is persisted by the launcher beyond what Google's own OAuth session already retains.

### 12.8 Non-goals (pilot)
First-release launcher scope explicitly excludes:
- public signup or open enrollment,
- operator-editable template or structural mapping — template remains maintainer-owned,
- persisted per-operator state beyond Google's OAuth session,
- compute-core work moving into Apps Script,
- multi-department selector exposing departments other than ICU/HD,
- acting as a prerequisite for, or blocker of, Milestone 2.
