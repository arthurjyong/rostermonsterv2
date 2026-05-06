# AGENTS.md

## Mission and current reality
Roster Monster v2 is building a reusable roster-allocation core with department-specific templates while keeping **Google Sheets** as the operational front end unless the repo explicitly changes that direction.

This repo is **not** a greenfield toy rewrite. It is an evolution/replacement path from the existing ICU/HD Google Sheets + Apps Script allocator.

Current repo reality:
- GitHub repo content is the source of truth.
- **ICU/HD** is the first concrete implementation target and first parity reference.
- The repo is still in an **architecture-first, contract-first** posture.
- Near-term work should follow the active milestone/checkpoint in `docs/delivery_plan.md`, not invent parallel tracks.
- Prefer refining existing repo documentation, contracts, and conventions over inventing new architecture, abstractions, or process.

## Read this first before making changes
Start with these files before proposing or making non-trivial changes:
1. `README.md`
2. `docs/blueprint.md`
3. `docs/delivery_plan.md`
4. `docs/roadmap.md`
5. `docs/decision_log.md`
6. the narrowest contract docs relevant to the boundary you are touching

If a proposed change is direction-changing, check `docs/decision_log.md` first.

## Active execution discipline
Unless the repo explicitly says otherwise, assume:
- there should normally be exactly **one active milestone**
- there should normally be exactly **one active checkpoint**

Read `docs/delivery_plan.md` before proposing non-trivial work.

Current active focus at time of writing:
- **Active milestone:** **M5 — Operator-side analysis & multi-roster delivery** *(activated 2026-05-04 per D-0055)*. Sibling-consumer architecture (Python analyzer engine + Apps Script renderer + upload portal) on top of the wrapper envelope; purely additive, no contract changes upstream of analysis. Sequencing rationale: analysis tooling first, solver-side score-aware search second (M6 territory).
- **Active checkpoint:** **M5 C4 — Live operator validation.** Awaits a real ICU/HD cycle's worth of data + operator availability. M5 C1 (analyzer engine) closed 2026-05-05 across PRs #110 + #111 + closure. M5 C2 (Apps Script renderer + launcher route + cross-page nav) closed 2026-05-06 across PRs #114 + #115 + #116 + closure; cloud deployment bumped to `@15`; operator runs `python -m rostermonster.analysis ...` locally then uploads via launcher `?action=analysis-render`. C3 dropped from the plan (absorbed into C2's launcher route — same discipline as M3 C2 dropped per D-0048). See `docs/delivery_plan.md` §7 / §9 / §11.
- **Next likely milestone:** M6 (or its successor) — provisionally framed around solver-side score-aware search (LAHC + cloud Deep Solve + email-notification architecture + cloud-side FULL retention promotion of FW-0030). Not pre-committed.
- **Closed-milestone trail:** D-0019..D-0054 (M1..M4); D-0055 activates M5; D-0056..D-0058 + M5 C1 closure cover M5 C1 (analysis contract + analyzer engine). Contracts settled through M5 C1 are listed in `docs/delivery_plan.md` §15.

If a task does not clearly support the active checkpoint, do not expand scope casually.

## Planning vocabulary
Use the repo’s planning vocabulary consistently:
- **Product**
- **Milestone**
- **Checkpoint**
- **Task**

Do not introduce replacement planning language in repo docs unless there is a strong repo-grounded reason.

## Default working style
Assume the following by default:
- one narrow, reviewable checkpoint at a time
- small, explicit diffs
- minimum file/doc set first
- refine existing repo conventions before inventing new structure
- preserve boundary clarity even when it feels slower
- keep changes implementation-facing and practical, not vague philosophy

Before major edits, identify the **minimum file/doc set** needed for the change.

## ICU/HD parity discipline
ICU/HD is the first concrete implementation target and first parity reference.

Do not casually introduce behavior divergence from ICU/HD assumptions or parity expectations. If behavior is meant to change, the authoritative repo docs and contracts should justify that change explicitly.

Do not smuggle behavior changes under the label of cleanup, simplification, or generalization.

## Architecture boundaries that must be preserved
Keep these boundaries explicit and do not blur them casually:
- **template contract**
- **snapshot/input contract**
- **parser/normalizer**
- **normalized domain model**
- **rule engine**
- **solver/search**
- **scorer**
- **writeback/output adapters**
- **sheet-specific adapter / integration logic**

Specific rules:
- Keep SpreadsheetApp and sheet-specific logic out of reusable core where practical.
- Apps Script may own Google Sheets-facing surface work (for example generation/interface integration).
- Keep compute-heavy core logic (parser/normalizer, rule engine, solver/search, scorer) out of Apps Script.
- Preferred first implementation direction for compute-heavy core work is local-first Python; do not force cloud/server/orchestration decisions early.
- Do not hide department semantics in arbitrary parser/adapter/writer code when the repo expects them to be declared in contracts/templates.
- Hard constraints must stay explicit and must not be weakened into scoring/preferences.
- Rule validity must remain distinct from ranking/scoring.
- Do not silently collapse template-owned, snapshot-owned, parser-owned, and downstream runtime responsibilities.

## Documentation rules
Prefer updating the **narrowest authoritative doc** instead of restating the same meaning in multiple places.

Use repo docs according to their role:
- `README.md` = front-door orientation
- `docs/blueprint.md` = stable architecture truth
- `docs/roadmap.md` = milestone-level delivery order
- `docs/delivery_plan.md` = current active execution truth
- `docs/decision_log.md` = accepted directional decisions
- contract docs = normative or implementation-facing boundary definitions

When writing docs:
- distinguish clearly between **settled decisions**, **open questions**, **confirmed facts**, and **hypotheses**
- do not present a first-pass or deferred item as if it is fully closed
- do not fork contract meaning into side comments or random docs
- do not reopen settled contracts without a concrete inconsistency, active-checkpoint need, or explicit decision change
- do not silently restate contract meaning in multiple places when one authoritative source already exists

## Coding and patch expectations
When changing the repo:
- keep the patch narrow and reviewable
- avoid broad rewrites
- avoid unrelated cleanup in the same patch
- prefer implementation-facing wording over vague philosophy
- use actual repo paths, names, and commands
- do not pretend to have inspected files that are absent

If code is added later:
- follow existing contracts first
- do not bypass contract boundaries just because a shortcut seems easier
- do not move operational sheet behavior into reusable core casually
- do not introduce hidden architecture changes without updating the authoritative docs that justify them

## Mandatory workflow for non-trivial changes
For non-trivial changes:
1. inspect the relevant repo files first
2. identify the minimum file/doc set needed
3. state which files should change
4. state which files should not change
5. state why
6. keep the expected patch surface small
7. validate with the smallest real checks available in the repo

If a task does not clearly support the active milestone/checkpoint, treat it as suspect and say so.

## Validation expectations
Run the smallest relevant validation that actually exists.

For docs-only patches:
- run `git diff --check`
- inspect the changed files directly
- confirm no unintended files changed

For code patches:
- run only real repo commands, tests, scripts, or checks that actually exist
- if no automated test/build command exists, say that explicitly
- do not invent toolchains, packages, CI steps, or validation commands that are not in the repo

## What not to do
Do **not**:
- broad-rewrite the repo
- invent missing modules, files, tools, build systems, or repo structure
- restart from scratch when the repo is clearly iterative
- weaken hard constraints into soft preferences
- mix sheet-specific integration logic into reusable core without reason
- silently redefine architecture in code without matching authoritative docs
- touch many docs for wording alignment when one narrow doc change would do
- claim a file was inspected when it was not actually inspected
- present speculative ideas as settled repo truth

## File-scope discipline
Default to changing as few files as possible.

For each non-trivial patch, explicitly identify:
- which files should change
- which files should not change
- why
- expected patch surface
- validation plan

If the change cannot be explained that way, it is probably too broad.

## Holiday data rules
- Singapore public holiday dates must match official MOM gazetted dates.
- Holiday logic must never silently assume unsupported years are non-holidays.
- If a generation or adjacent-day lookup crosses outside supported holiday years, throw an explicit error.
