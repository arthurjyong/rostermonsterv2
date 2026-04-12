# Decision Log

## Purpose
- Record major product and architecture decisions.
- Preserve context, rationale, and expected impact.
- Keep a traceable history of directional choices.

## How decisions should be recorded
- Add a new entry when a decision changes product or architecture direction.
- Prefer concise entries with explicit date and status.
- Link affected documents when relevant.

## Entry template
- **Decision ID:**
- **Date:**
- **Status:** Proposed | Accepted | Superseded
- **Context:**
- **Decision:**
- **Rationale:**
- **Consequences:**
- **Follow-up actions:**
- **Related docs:**

## Current known decisions

### D-0001: New repository for v2
- **Date:** 2026-04-01
- **Status:** Accepted
- **Decision:** Roster Monster v2 work begins in a new repository.

### D-0002: Docs-first approach
- **Date:** 2026-04-01
- **Status:** Accepted
- **Decision:** Start with documentation and architecture scaffolding before implementation.

### D-0003: Reusable core + department templates
- **Date:** 2026-04-01
- **Status:** Accepted
- **Decision:** Build a reusable allocation core with department-specific templates.

### D-0004: Google Sheets retained as front end
- **Date:** 2026-04-01
- **Status:** Accepted
- **Decision:** Keep Google Sheets as operational UI/front-end.

### D-0005: ICU/HD as first department implementation
- **Date:** 2026-04-01
- **Status:** Accepted
- **Decision:** CGH ICU/HD is the first department implementation target.

### D-0006: Template vs snapshot vs normalized model are explicit boundaries
- **Date:** 2026-04-12
- **Status:** Accepted
- **Decision:** The architecture uses three distinct contracts: department template, per-run snapshot input, and normalized domain model output.

### D-0007: Template contract is normative and template-governed
- **Date:** 2026-04-12
- **Status:** Accepted
- **Decision:** `docs/template_contract.md` is the normative contract for first-release department templates and their governance.

### D-0008: Snapshot contract defines raw per-run parser input boundary
- **Date:** 2026-04-12
- **Status:** Accepted
- **Decision:** `docs/snapshot_contract.md` defines the raw, per-run input boundary before parser interpretation/normalization.

### D-0009: Normalized domain model is parser/normalizer-owned output
- **Date:** 2026-04-12
- **Status:** Accepted
- **Decision:** `docs/domain_model.md` defines parser/normalizer-owned normalized outputs consumed by downstream engine layers.

### D-0010: Sheets front end retained with reusable core intent
- **Date:** 2026-04-12
- **Status:** Accepted
- **Decision:** Google Sheets remains the operational front end while roster-allocation logic is designed as a reusable core.

### D-0011: ICU/HD is the concrete reference/parity target for first release
- **Date:** 2026-04-12
- **Status:** Accepted
- **Decision:** ICU/HD remains the concrete reference implementation and parity target for first-release behavior.
