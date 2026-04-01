# Domain Model (Draft Skeleton)

## Purpose
- Outline the future normalized internal model for allocation.
- Align terminology across contracts, parser, engine, and outputs.
- TODO: lock terminology before implementation.

## Design principles
- Keep model explicit and composable.
- Separate input representation from internal normalized form.
- Preserve traceability between source data and derived entities.
- TODO: define minimal required identity keys per entity.

## Core entities
- Doctor
- Slot
- Date/Day
- Request/Effect
- Department Template
- Snapshot/Input Bundle
- Allocation Result
- Score Result
- Issue/Validation Object

## Doctor
- Represents assignable person/resource.
- High-level attributes include identity and grouping context.
- TODO: define which attributes are core vs template-derived.

## Slot
- Represents a schedulable assignment target.
- Includes slot identity and assignment intent.
- TODO: clarify whether slot capacity is modeled directly or via rules.

## Date / day
- Represents scheduling unit within horizon.
- Supports day-level reasoning for adjacency and sequence rules.
- TODO: define timezone/calendar assumptions.

## Request / effect
- Represents request signal and its intended scheduling impact.
- Distinguishes hard constraints from soft effects.
- TODO: define canonical effect taxonomy.

## Department template
- Represents department contract metadata consumed by core.
- Provides rule/eligibility/scoring context.
- TODO: define minimal template metadata set.

## Snapshot / input bundle
- Represents a versioned run input package.
- Combines normalized entities plus source references.
- TODO: define reproducibility metadata requirements.

## Allocation result
- Represents final (or candidate) assignments.
- Includes assignment provenance for explainability.
- TODO: decide how alternate candidates are represented.

## Score result
- Represents scoring breakdown and totals.
- Designed to support diagnostics and tradeoff review.
- TODO: define required granularity for score components.

## Issue / validation object
- Represents structured warnings/errors across stages.
- Includes context needed for troubleshooting.
- TODO: standardize severity and category model.

## Open modeling questions
- Which entities are globally stable versus template-scoped?
- How strict should entity immutability be during pipeline stages?
- What is the minimum provenance metadata needed for auditability?
