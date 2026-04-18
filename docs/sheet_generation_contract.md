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

## 4. Template-owned generation facts
Generation must treat the following as template-owned declarations:
- which groups/sections exist,
- section and structural ordering,
- call-point row presence/default behavior,
- output-shell structural surfaces.

Generation must not invent alternative logical section orders outside template declaration.

## 5. Required generated structural surfaces
Generated shell must include at least:
1. date axis,
2. weekday row,
3. explicit section headers for grouped doctor-entry sections,
4. placeholder doctor rows with blank doctor-name cells,
5. request-entry cells,
6. call-point rows (including MICU and MHD point rows with defaults),
7. lower roster/output shell rows and cells (in template-declared slot order),
8. weekend/public holiday highlighting,
9. legend/Descriptions block (non-structural adjunct content).

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
