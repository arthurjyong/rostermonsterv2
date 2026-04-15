# Sheet Generation Contract (First-Release, Operator-Facing Shell)

## 1. Purpose and status
This document defines the first-release contract for **template-driven generation of an empty operator-facing sheet shell** for ICU/HD-style workflows.

Status:
- Contract-first, implementation-facing checkpoint.
- Narrow and normative for generation requirements/boundaries.
- Not a generator procedure spec.

Boundary with adjacent concerns:
- **Template artifact contract** declares structural inputs used by generation.
- **This contract** declares what generation must produce and what edits are allowed after generation.
- **Parser contracts** govern how populated sheets are interpreted after operators enter data.
- **Writer/orchestration mechanics** remain outside this document.

## 2. First-release generation goal
Generation must produce an **empty request-form shell** that is:
- template-driven,
- operator-facing,
- structurally close to the current ICU/HD workflow.

For first release:
- structural fidelity is required,
- exact cosmetic/pixel-perfect fidelity is not required.

## 3. Generation inputs (operator-supplied)
Generation accepts:
- `templateId`
- `templateVersion`
- `periodStartDate`
- `periodEndDate`
- `doctorCountByGroup`

Input ownership notes:
- Template identity/version selects the department-owned structure.
- Period dates define generated day-axis span.
- `doctorCountByGroup` determines initial placeholder row counts per template-declared group section.

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
3. grouped doctor-entry sections,
4. placeholder doctor rows,
5. call-point rows,
6. lower empty roster/output shell rows.

These are required structural regions for first release.

## 6. Operator-allowed edits after generation
After generation, operators may:
- fill doctor names in column A,
- add rows within a section,
- delete rows within a section,
- edit call-point values.

Parser-facing expectation:
- Names entered in column A become source doctor names for later parsing.
- Parser robustness relies on section/segment structure, not fixed hardcoded row counts.

## 7. Disallowed structural drift
End users must not perform major structural rearrangement of template-owned logical regions, including:
- arbitrary reordering/moving of declared sections,
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

## 9. Structural vs cosmetic scope
Required in first release:
- structural surfaces listed in Section 5,
- unambiguous generated raw date text in date headers sufficient for downstream parser/date normalization work.

Not required in first release (optional/cosmetic):
- legend blocks,
- description blocks,
- FAQ/help narrative blocks,
- pixel-perfect visual replication.

## 10. Relationship to adjacent docs
- `docs/template_artifact_contract.md`: source of template-owned structural declarations used by generation.
- `docs/blueprint.md`: architecture-level positioning that generation is part of first-release operator-facing workflow direction.
- `docs/roadmap.md`: sequencing intent that sheet generation is a planned first-release integration capability, not an unbounded distant optional add-on.

This contract intentionally does not redefine:
- parser semantics,
- snapshot schema,
- writer/orchestrator procedures,
- low-level external API integration mechanics.
