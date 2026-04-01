# Blueprint (Skeleton)

## Purpose
- Define the high-level architecture direction for Roster Monster v2.
- Keep scope explicit before implementation.
- TODO: tighten into an actionable build plan after contracts are drafted.

## Why v2 exists
- v1 constraints and coupling limit reuse.
- Need a reusable roster allocation core.
- Need department-specific behavior without rebuilding everything.
- TODO: document concrete pain points from v1.

## Goals
- Build a reusable allocation core.
- Support department template packs for customization.
- Keep Google Sheets as operational UI.
- Deliver CGH ICU/HD as the first implementation.

## Non-goals
- No universal self-serve template builder in this phase.
- No attempt to solve every department upfront.
- No premature cloud/platform commitments.

## Core invariants
- Core logic should be department-agnostic where possible.
- Department rules should be expressed via template contract.
- Input/output flow must be auditable and deterministic.
- TODO: define minimum determinism guarantees.

## System boundaries / layers
- Google Sheets front-end layer.
- Template/contract definition layer.
- Normalization and core allocation layer.
- Output/artifact layer.
- TODO: finalize responsibility boundary between layers.

## Features to retain from v1
- Existing operational workflow centered on Sheets.
- Domain-specific request semantics where still valid.
- Practical roster output expectations for stakeholders.
- TODO: enumerate exact retained behaviors.

## Features to redesign
- Internal model normalization.
- Rule/scoring separations.
- Execution architecture for local and external modes.
- TODO: identify v1 behaviors to explicitly deprecate.

## Department-template concept
- Each department provides a structured template/spec.
- Core engine consumes template + normalized input.
- Template captures department-specific slots, groups, and rules.
- TODO: define versioning strategy for templates.

## Execution modes
- Local execution mode for development and validation.
- External worker mode for scale/hardening later.
- TODO: decide parity requirements between modes.

## Observability philosophy
- Make allocation outcomes explainable.
- Preserve traceability from inputs to outputs.
- Surface actionable diagnostics, not raw logs only.
- TODO: define minimum observability artifacts for first release.

## Validation philosophy
- Validate inputs early and explicitly.
- Separate hard errors from warnings.
- Fail clearly on contract violations.
- TODO: define validation stages and ownership.

## Build order
- Docs and architecture alignment.
- Contracts and domain model.
- Parser/normalization and rule/scoring foundations.
- Solver, execution modes, and integration.
- TODO: map build order to roadmap checkpoints.

## Open design questions
- What is the minimum stable contract for first department rollout?
- Which rules are core vs template-defined?
- What score transparency is required for operations users?
- How strict should backward compatibility be between template versions?
