# Department Template Contract (Conceptual)

## Purpose of the template contract
- Provide a consistent way for a department to define roster behavior.
- Isolate department-specific rules from reusable core logic.
- TODO: establish contract stability and versioning expectations.

## What a department must define
- Department identity and scope.
- Scheduling horizon assumptions.
- Required inputs and acceptable defaults.
- TODO: define mandatory vs optional sections.

## Slot definitions
- Department-specific slot catalog.
- Slot meaning, capacity intent, and scheduling context.
- TODO: clarify global vs department-local slot identifiers.

## Doctor groups
- Grouping model for doctors (e.g., role/track/team concepts).
- Group metadata used by eligibility and constraints.
- TODO: decide if group definitions can overlap.

## Eligibility mapping
- Mapping of which doctors/groups can fill which slots.
- Handling for conditional eligibility.
- TODO: define precedence when multiple eligibility rules apply.

## Request codes and semantics
- Department request codes and intended effects.
- Distinction between hard constraints and soft preferences.
- TODO: decide how request priorities are represented.

## Blocking / preceding-day rules
- Department-specific blocking and adjacency constraints.
- Rules that depend on previous-day assignments.
- TODO: define baseline rule vocabulary.

## Sheet layout mapping
- Mapping from sheet structure to normalized inputs.
- Required anchors/ranges and expected semantics.
- TODO: define tolerance for layout drift.

## Output mapping
- Mapping from internal allocation result to sheet outputs/artifacts.
- Required output fields for operations.
- TODO: define minimal output contract for first rollout.

## Scoring knobs
- Template-exposed scoring weights or toggles.
- Boundaries to prevent unsafe/invalid tuning.
- TODO: decide whether knobs are per-template or per-run.

## Validation expectations
- Contract validation before execution.
- Clear error/warning model for template issues.
- TODO: define who owns template validation lifecycle.

## Questions still undecided
- What must be immutable once a template version is released?
- How will template migrations be handled?
- What review process is required before template changes are accepted?
