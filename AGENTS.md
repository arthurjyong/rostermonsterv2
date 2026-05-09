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
- **Active milestone:** **M7 — Parallel solver (Cloud Batch + intra-request K-fanout)** *(activated 2026-05-10 per D-0070)*. M7 parallelizes K-trajectory LAHC via Cloud Batch + dense pack (`c3-highcpu-8` VMs × `multiprocessing.Pool(8)` × 1 LAHC trajectory per vCPU) inside a sync request with Cloud Run Service timeout 250s (lowered from default 300s per D-0070 sub-decision 5 — Apps Script script-execution wall-clock 360s is shared between extract + UrlFetchApp.fetch() + writeback + renderAnalysis in the bound shim's onClickHandler; tail-case budget 10+250+30+60+10=360s exactly fits the analyzer-integration-expanded scope; cloud_compute_contract §9 + §10 gain additive `solverStrategy` + `lahcParams` + OK-only `analyzerOutput` recognition at M7 C3). FW-0037 elbow tuple locked: `L=50` / `idleThreshold=3500` / `swapProbability=0.5`. K=2,500 target with smaller approvals acceptable since best-of-K plateau is K=10-20 per FW-0036. On-demand pricing chosen over Spot for sync-wall-time predictability (cost is not a constraint at the doctor-time-comparison framing per the M7 design conversation). Cloud Run per-instance concurrency, threading, and Spot pricing explicitly excluded per D-0070 sub-decisions. FW-0035 (cloud-mode LAHC integration) co-promotes with M7 closure since the parallel core is what makes cloud LAHC operationally viable at sync UX.
- **Active checkpoint:** **M7 C2 — Cloud Batch implementation** *(activated 2026-05-10 on M7 C1 closure)*. M7 C1 closed 2026-05-10 with GCP quota approvals: CPUS=300 / INSTANCES=350 / C3_CPUS=108 (binding constraint). **Closure-K = 104** per D-0070 sub-decision 7's three-quota rule. M7 C2 implements the parallel cloud LAHC path at K=104 (taskCount=13, all fully packed). Subsequent M7 C3 (sync UX + bound shim wiring + cloud_compute §9/§10 amendments + analyzer integration) / M7 C4 (live operator validation + closure) per `docs/delivery_plan.md` §7.
- **Closed-milestone trail:** D-0019..D-0054 (M1..M4); D-0055 activates M5; D-0056..D-0058 close M5 C1 (analyzer engine + analysis contract); D-0059 (apps_script directory rename); D-0060..D-0063 close M5 C2 (renderer + launcher route + cross-page nav; C3 dropped); D-0064 (forward-going Task 1/2/3 cadence vocabulary); D-0065 closes M5 (C4 live operator validation verdict); D-0066 activates M6 (LAHC-only scope); D-0067 closes M6 C1 (LAHC algorithm spec + solver_contract.md §12A; restates D-0066 sub-decision 10 — `contractVersion` bumps 1 → 2 driven by §9 promoting `strategyId` to a required boundary input; LAHC strategy registration alone via §11.2 would not have required a bump); D-0068 narrows M6 C3 to local-first (cloud-mode LAHC integration parked as FW-0035); D-0069 closes M6 C4 + M6 (LAHC empirically validated on dev-copy fixture; sweet-spot defaults captured but not module-pinned); D-0070 activates M7 (parallel solver via Cloud Batch + intra-request K-fanout per the design conversation). Contracts settled through M6 closure are listed in `docs/delivery_plan.md` §15.

If a task does not clearly support the active checkpoint, do not expand scope casually.

## Planning vocabulary
Use the repo’s planning vocabulary consistently:
- **Product**
- **Milestone**
- **Checkpoint**
- **Task** — typical decomposition inside a checkpoint follows the **Task 1 (docs) → Task 2 (code, with optional Task 2A / 2B / 2C sub-letters when work has logically distinct chunks) → Task 3 (closure)** cadence per D-0064. Not a contract: a docs-only checkpoint may be just Task 1; an unusual checkpoint may have a different shape. Historical "Phase 1/2/3" labels in past PR titles and closed-milestone closure entries are preserved as-is.

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
