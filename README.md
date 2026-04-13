# Roster Monster v2

Roster Monster v2 defines a reusable roster-allocation core with department-specific templates, while keeping Google Sheets as the operational front-end. The first implementation target is CGH ICU/HD.

## Current status
This repo is in a **contract-first and architecture-first pre-implementation phase**. Core documents now define boundaries and first-release contracts in enough detail to guide parser/input-contract work, but implementation has not started yet.

## Core documents
- `docs/blueprint.md` — High-level architecture, product boundaries, and layer responsibilities.
- `docs/template_contract.md` — First-release **normative** department template contract and governance rules.
- `docs/snapshot_contract.md` — Per-run raw snapshot input contract at the parser boundary.
- `docs/parser_normalizer_contract.md` — Explicit parser/normalizer boundary contract between snapshot input and normalized domain output.
- `docs/domain_model.md` — Implementation-facing normalized domain model contract for parser/normalizer outputs and downstream engine layers.
- `docs/roadmap.md` — Phased build sequence from docs/contracts through parser, solver, execution, and hardening.
- `docs/decision_log.md` — Ongoing record of key product and architecture decisions.

## Near-term next step
The parser–normalizer boundary is now defined in `docs/parser_normalizer_contract.md`.
The next checkpoint is to review remaining contract consistency and then move to the next narrow implementation-facing boundary.
