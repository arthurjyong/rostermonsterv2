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

### D-0012: Parser/normalizer boundary checkpoint is accepted
- **Date:** 2026-04-13
- **Status:** Accepted
- **Decision:** `docs/parser_normalizer_contract.md` is adopted as the explicit parser/normalizer boundary contract, with `ParserResult` as the parser-stage wrapper, binary consumability (`CONSUMABLE` / `NON_CONSUMABLE`), and no partial downstream handoff for `NON_CONSUMABLE` results.

### D-0013: Planning hierarchy is Product → Milestone → Checkpoint → Task
- **Date:** 2026-04-16
- **Status:** Accepted
- **Context:** Planning docs were drifting between phase language and mixed granularities, making it hard to keep product-level direction and active execution aligned.
- **Decision:** Adopt and standardize the planning hierarchy `Product → Milestone → Checkpoint → Task` across repo-level guidance docs.
- **Rationale:** A shared vocabulary reduces planning ambiguity and keeps roadmap, active execution, and architecture references consistent.
- **Consequences:** Existing and new planning docs should use the hierarchy consistently, and ad hoc planning terms should be minimized.
- **Follow-up actions:** Reflect this hierarchy in README orientation, roadmap framing, blueprint vocabulary, and delivery-plan maintenance rules.
- **Related docs:** `README.md`, `docs/blueprint.md`, `docs/roadmap.md`, `docs/delivery_plan.md`

### D-0014: Maintain one active milestone and one active checkpoint
- **Date:** 2026-04-16
- **Status:** Accepted
- **Context:** Parallel planning threads were creating fragmentation and making it unclear what work should be prioritized in the current period.
- **Decision:** Repository execution guidance should normally declare exactly one active milestone and one active checkpoint at a time.
- **Rationale:** Single-threaded active focus improves sequencing discipline and prevents near-term effort from scattering across unrelated work.
- **Consequences:** New tasks should be evaluated against the active checkpoint, and work outside it should be explicitly deferred or queued under later checkpoints.
- **Follow-up actions:** Encode this rule in `docs/delivery_plan.md` and keep README current-focus summary synchronized.
- **Related docs:** `README.md`, `docs/delivery_plan.md`, `docs/roadmap.md`

### D-0015: Near-term priority is operator-ready request sheet generation
- **Date:** 2026-04-16
- **Status:** Accepted
- **Context:** The project needs a concrete operationally relevant boundary before broad downstream implementation and orchestration work.
- **Decision:** Set `Operator-ready request sheet generation` as the current active milestone, with `Close sheet-generation MVP boundary` as the current active checkpoint.
- **Rationale:** Closing generation boundary clarity unblocks immediate operator workflow needs and creates a stable handoff point for subsequent pipeline milestones.
- **Consequences:** Near-term planning and task selection should prioritize generation-input, structural-surface, operator-edit, non-goal, and acceptance-criteria closure.
- **Follow-up actions:** Seed and maintain the active checkpoint tasks in `docs/delivery_plan.md`; keep roadmap and README alignment.
- **Related docs:** `README.md`, `docs/roadmap.md`, `docs/delivery_plan.md`
