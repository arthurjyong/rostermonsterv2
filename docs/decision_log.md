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

### D-0016: Reopen Milestone 1 in place for operator implementation delivery
- **Date:** 2026-04-18
- **Status:** Accepted
- **Context:** On 2026-04-18, Milestone 1 (`Operator-ready request sheet generation`) was marked closed once C1/C2/C3 had fixed the generation contract boundary, template/generation alignment, and acceptance/handoff readiness. However, no operator-usable sheet shell had actually been generated — closure reflected contract closure only, not operator delivery.
- **Decision:** Reopen Milestone 1 in place rather than redefining its meaning silently. C1/C2/C3 remain completed contract-closure checkpoints. A new implementation checkpoint (C4 — `Implement operator-ready sheet generation`) is added under M1 and becomes the active checkpoint. Milestone 2 (`Minimal local compute pipeline`) returns to Planned.
- **Rationale:** The intent of M1 is an operational unblocker for ICU/HD. Declaring M1 closed on contract closure alone would misrepresent real delivery state and mask the remaining implementation slice. Reopening in place preserves history instead of rewriting it.
- **Consequences:** M1 exit criteria now explicitly require operator-ready ICU/HD sheet-shell generation, not just contract closure. One active milestone and one active checkpoint are maintained. M2 sequencing is unchanged in order but deferred in time until M1 implementation lands.
- **Follow-up actions:** Keep `README.md`, `AGENTS.md`, `docs/roadmap.md`, and `docs/delivery_plan.md` consistent with M1 reopen and C4 activation; avoid smuggling M2 scope into C4.
- **Related docs:** `README.md`, `AGENTS.md`, `docs/roadmap.md`, `docs/delivery_plan.md`

### D-0017: Narrow implementation stack for M1 sheet generation is Google Apps Script on Google Sheets
- **Date:** 2026-04-18
- **Status:** Accepted
- **Context:** M1 C4 requires an actual implementation of the ICU/HD request sheet shell. The repo has not yet chosen a long-term compute-core implementation stack, and should not pre-commit to one just to unblock the M1 generation slice.
- **Decision:** For the M1 generation slice only, operator-facing sheet generation is implemented in Google Apps Script targeting Google Sheets.
- **Rationale:** Google Sheets is already the repo-declared operational front end (see D-0004, D-0010). Apps Script is the narrowest path to generate and control a Google Sheets artifact (creation, tab insertion, protection ranges, data validation) without introducing new runtime infrastructure. This keeps M1 delivery bounded and operator-relevant.
- **Consequences:** This decision applies only to the M1 generation slice (C4). It does not decide the long-term compute-core implementation stack (parser/normalizer, rule engine, solver/scorer, writeback, orchestration), which remains deferred. Apps Script code introduced under this decision must stay within generation-shell scope and must not absorb downstream compute responsibilities.
- **Follow-up actions:** Record this narrow scope in `docs/delivery_plan.md` C4; explicitly defer the broader compute-core stack decision to a later milestone.
- **Related docs:** `docs/delivery_plan.md`, `docs/sheet_generation_contract.md`, `docs/template_artifact_contract.md`

### D-0018: Stack ownership split — Apps Script for sheet-facing surface, local-first Python direction for compute-heavy core
- **Date:** 2026-04-18
- **Status:** Accepted
- **Context:** D-0017 intentionally narrowed the M1 C4 implementation slice to Google Apps Script on Google Sheets so operator-ready sheet generation could proceed without forcing broader stack decisions. As C4 execution starts, the repo also needs an explicit cross-milestone ownership split so sheet-surface implementation does not drift into compute-core implementation inside Apps Script.
- **Decision:** Keep D-0017 fully valid for the M1 generation slice. Treat Google Apps Script as an acceptable implementation layer for Google Sheets-facing surface work (sheet generation/interface integration). Keep compute-heavy core-engine logic outside Apps Script. For compute-heavy core work, the first implementation direction is local-first Python. This decision does not yet choose cloud/server/orchestration runtime for compute-core execution.
- **Rationale:** This preserves operator-facing delivery speed for M1 while protecting architecture boundaries between sheet integration and reusable compute core. Local-first Python gives a practical path for deterministic development and iteration on parser/normalizer, rule engine, solver, and scorer without prematurely binding remote runtime topology.
- **Consequences:** Apps Script work in C4 remains bounded to sheet-facing generation/interface concerns. This decision does not authorize moving parser/normalizer, rule engine, scorer, solver, or other compute-brain responsibilities into Apps Script. Remote/cloud execution choices remain deferred to later orchestration-focused milestones/checkpoints.
- **Follow-up actions:** Reflect this ownership split in `docs/blueprint.md`, `docs/delivery_plan.md`, and `AGENTS.md`; keep M1/C4 scope narrow and avoid reopening milestone sequencing.
- **Related docs:** `docs/blueprint.md`, `docs/delivery_plan.md`, `AGENTS.md`

### D-0019: Close Milestone 1 on operator delivery
- **Date:** 2026-04-21
- **Status:** Accepted
- **Context:** M1 (`Operator-ready request sheet generation`) was reopened in place by D-0016 so milestone closure would align with real operator delivery rather than contract closure alone. Under that reopen, C4 (`Implement operator-ready sheet generation`) ran the Apps Script generator through both output modes and verified the produced shell against the C3 acceptance checklist using an operator-owned May 2026 ICU/HD cycle (2026-05-04 to 2026-06-01; 9/6/7 manpower).
- **Decision:** Close Milestone 1 with status `Completed` on 2026-04-21. C4 is the final M1 checkpoint, and its closure completes the M1 exit criteria as redefined under D-0016.
- **Rationale:** M1 exit criteria under D-0016 required both contract closure and operator-ready implementation. Both are now in place. Leaving M1 open past verified operator delivery would continue to block M2 kickoff without gaining boundary clarity.
- **Consequences:** Milestone 2 (`Minimal local compute pipeline`) becomes the active milestone at milestone level; M2 C1 is teed up in `docs/delivery_plan.md` §7 but not yet activated. Any future M1-scoped change (e.g., a second department) should be treated as a new milestone or a deliberate M1 reopen, not a quiet patch against a closed milestone.
- **Follow-up actions:** Update `README.md` current focus, `AGENTS.md` current-focus line, and `docs/delivery_plan.md` §5/§6/§7/§8/§9/§11/§12 to reflect closure; keep D-0016 valid as historical record of the reopen rather than marking it Superseded.
- **Related docs:** `README.md`, `AGENTS.md`, `docs/delivery_plan.md`, `docs/roadmap.md`

### D-0020: `clasp run` requires both GCP consent-screen scope allowlist and project-scope login
- **Date:** 2026-04-21
- **Status:** Accepted
- **Context:** During M1 C4 execution, a live `clasp run` attempt against the production Apps Script project surfaced `You do not have permission to call SpreadsheetApp.openById. Required permissions: https://www.googleapis.com/auth/spreadsheets`, even though steps 1–4 of the M1 README's "API executable / clasp run" prerequisite list had been satisfied (user-managed GCP project, Apps Script API enabled, `executionApi.access: MYSELF` in the manifest, API Executable deployment created, Desktop OAuth client created). The failure mode was not a configuration bug in the generator — it was two independent OAuth gates neither of which is visible at login time.
- **Decision:** Treat `clasp run` as requiring both of the following, in addition to the existing prerequisites, as a stable operator-facing operational requirement:
  1. Every scope declared in the Apps Script manifest's `oauthScopes` (including `https://www.googleapis.com/auth/spreadsheets`) must be added to the GCP OAuth consent screen's Data Access allowlist for the user-managed GCP project.
  2. `clasp login` must be run with `--use-project-scopes --include-clasp-scopes` (in addition to `--creds <path>`), so the resulting clasp token actually requests the manifest's declared scopes rather than clasp's baseline scopes alone.
- **Rationale:** The two gates are independent. Allowlisting a scope on the consent screen does nothing if the clasp token does not request that scope; requesting a scope at login does nothing if the consent screen disallows it. Omitting either gate fails at runtime with the same opaque "Required permissions" error, which is easy to misdiagnose as a manifest or deployment issue. Making this explicit in the README and decision log prevents the same failure recurring on future operator onboarding.
- **Consequences:** `apps_script/m1_sheet_generator/README.md` documents both gates in the "API executable / `clasp run`" section so operators do not have to rediscover this. Any future Apps Script project in this repo that declares additional scopes must extend both the consent-screen allowlist and the clasp login invocation, not only the manifest.
- **Follow-up actions:** Keep the README prerequisite list authoritative for per-operator setup. Do not fork this guidance into multiple places.
- **Related docs:** `apps_script/m1_sheet_generator/README.md`

### D-0021: Addendum-milestone convention and activation of Milestone 1.1
- **Date:** 2026-04-21
- **Status:** Accepted
- **Context:** After M1 closed on operator delivery (D-0019), it became clear that M1's operator-facing story was not fully complete: the generator remained maintainer-only, and the named monthly-rotation pilot operators could not invoke it without direct Apps Script execution. Extending the generator with a thin operator-facing launcher is derivative of M1's operator-facing surface, not a compute-line milestone like M2/M3/M4/M5. D-0019 had noted that any future M1-scoped change should be treated as a new milestone or a deliberate M1 reopen; neither of those quite fits an operator-facing addendum that does not alter generated-sheet semantics.
- **Decision:** Introduce an explicit **addendum-milestone** concept in the planning vocabulary.
  1. An addendum milestone extends a parent milestone's operator-facing story without reopening it. The parent milestone stays `Completed`; the addendum is a distinct milestone with its own checkpoints, tasks, and exit criteria.
  2. Addendum milestones are numbered `M<parent>.<n>`, where `n` is an integer counter starting at 1 (`M1.1`, `M1.2`, `M1.3` …). Nested decimal sub-numbering (for example `M1.1.1` or `M1.15`) is not used.
  3. Only one milestone is active at a time per the existing one-active-milestone rule; activating an addendum returns its siblings or later milestones to Planned until the addendum closes.
  4. Activate `M1.1` — `Operator-facing launcher` — as the first addendum milestone under this convention. M2 (`Minimal local compute pipeline`) returns to Planned while M1.1 is active.
- **Rationale:** Addendum framing is more honest than either option allowed by D-0019 for this specific slice. It preserves M1 closure integrity (M1 is genuinely Completed; the launcher is additive), keeps M2's compute-core direction untouched, and gives a reusable planning pattern for future operator-facing extensions that do not merit a full top-line milestone. Integer-only addendum numbering avoids the decimal-depth cliff (`M1.5` → `M1.75` → `M1.875`) that arises from ad-hoc decimal insertion.
- **Consequences:** `docs/delivery_plan.md`, `docs/roadmap.md`, `README.md`, and `AGENTS.md` reflect M1.1 as the active milestone and M2 as Planned. Any future addendum to any parent milestone uses the same `M<parent>.<n>` scheme. Addenda are normal milestones for execution-discipline purposes (checkpoints, tasks, sign-off) even though they are derivative in framing. A parent milestone must already be Closed before an addendum can be activated; addenda cannot be used to sneak a reopen past D-0019's guidance.
- **Follow-up actions:** Reflect the convention in `docs/delivery_plan.md` §5/§6/§12/§15, `docs/roadmap.md`, `README.md` current focus, and `AGENTS.md` current-focus-at-time-of-writing line. Keep D-0019 valid as historical record rather than marking it Superseded.
- **Related docs:** `README.md`, `AGENTS.md`, `docs/roadmap.md`, `docs/delivery_plan.md`

### D-0022: Milestone 1.1 launcher architecture — stack, access model, and boundary placement
- **Date:** 2026-04-21
- **Status:** Accepted
- **Context:** M1.1 (activated under D-0021) requires a narrow operator-facing launcher that wraps the existing M1 generation entrypoints (`generateIntoNewSpreadsheet` / `generateIntoExistingSpreadsheet`). Architecture-first discussion for this thread settled a coherent set of decisions — implementation stack, access model, architectural boundary placement, and operator-rotation mechanics — that belong recorded together rather than scattered as individual entries.
- **Decision:** For the M1.1 pilot, accept the following as a single coherent architecture position.
  1. **Implementation stack:** Google Apps Script Web App, deployed with "Execute as: User accessing the web app" and "Who has access: Anyone with a Google Account." Launcher code lives in `apps_script/m1_sheet_generator/` alongside the existing generator.
  2. **Architectural boundary:** the launcher is a thin front-end inside the sheet-adapter layer (Blueprint §7 boundary #2). It is not a new architectural boundary. Launcher code must not absorb parser/normalizer/rule/solver/scorer logic, must not alter generated-sheet structure or semantics, and must not persist per-operator state beyond Google's OAuth session.
  3. **Access model:** identity is established by native Google OAuth under "Execute as user"; authorization is granted by adding the operator's Google account to the GCP OAuth consent screen's **Test Users** list for the launcher's GCP project. The launcher itself does not maintain or check a separate operator allowlist for pilot scope.
  4. **Operator rotation:** monthly operator rotation is handled by the maintainer editing the Test Users list between cycles. Rotation is not encoded in app logic.
  5. **Input normalization:** the operator-supplied spreadsheet reference accepts both a bare spreadsheet ID and a full Google Sheets URL containing one. Normalization happens centrally in `normalizeAndValidateConfig_`, not in the launcher. Extraction rule is recorded in `docs/sheet_generation_contract.md` §12.5.
- **Rationale:** Apps Script Web App is the narrowest launcher path that (a) reuses the existing Google-native deployment model for the generator, (b) gets OAuth identity for free under "Execute as user," (c) introduces no new runtime infrastructure, and (d) does not force a cross-service hosting choice during the pilot. Keeping access gating external to the app (Test Users list) avoids building a per-operator allowlist/role model before the pilot has justified one. Centralizing spreadsheet-reference normalization in the existing config helper keeps the launcher thin and lets future callers — including smoke tests — inherit the more forgiving input form at no extra cost.
- **Consequences:** Alternative launcher platforms (static page over Apps Script API Executable, Sheets workspace add-on, Cloud Run front-end) are deliberately deferred and recorded as deferred in `docs/delivery_plan.md` §10. If pilot usage outgrows the Apps Script HTML UI, the natural next step is to front-end the existing generator via API Executable without changing server-side generation code. The `spreadsheetId` field in `docs/sheet_generation_contract.md` §3A widens backward-compatibly to accept URL or bare ID; §12 adds the launcher surface as a narrow contract section rather than spawning a new contract doc. D-0018's ownership split (Apps Script for sheet-facing surface, compute-heavy core outside Apps Script) is preserved — the launcher is sheet-facing surface, not compute.
- **Follow-up actions:** Implementation-phase work lands in a follow-up code patch on `claude/oauth-roster-webapp-DCasP` (command-line CC session), tracked under M1.1 C1 tasks T1–T4 in `docs/delivery_plan.md` §9.
- **Related docs:** `docs/delivery_plan.md`, `docs/sheet_generation_contract.md`, `docs/blueprint.md`, `AGENTS.md`, `apps_script/m1_sheet_generator/README.md`

### D-0023: Auto-share new spreadsheets via Drive Advanced Service (v3), not `DriveApp.setSharing`
- **Date:** 2026-04-22
- **Status:** Accepted
- **Context:** The M1.1 launcher's new-spreadsheet mode creates the roster sheet inside the operator's own Drive (under `executeAs: USER_ACCESSING`). Without an explicit sharing step the file is private to the operator, forcing a per-cycle manual "click Share → Anyone with link → Editor" gesture before the URL is useful to doctors. Automating that one step was an obvious pilot-friction win, but the right way to do it turned out to require decision-level discipline after three implementation attempts converged.
- **Decision:** Auto-share is implemented via the Drive Advanced Service (REST v3): `Drive.Permissions.create({ type: 'anyone', role: 'writer' }, fileId)`, called right after `SpreadsheetApp.create` in `generateIntoNewSpreadsheet`. The call is wrapped in try/catch — on failure the sheet still generates, the response carries `autoShared: false` plus the underlying error text in `autoShareError`, and the success view renders a manual-share hint instead of faking success. On success the response carries `autoShared: true` and the success view confirms the sharing state. `DriveApp.setSharing` / `DriveApp.getFileById` are not used. The declared OAuth scopes are `spreadsheets`, `drive.file`, and `userinfo.email`; `dependencies.enabledAdvancedServices` declares Drive v3; the linked user-managed GCP project must have the Drive API turned on. Existing-spreadsheet mode is unchanged and does not auto-share (parent-file sharing is inherited).
- **Rationale:** Three paths were attempted in sequence during M1.1 pilot testing:
  1. **`DriveApp.setSharing` with `drive.file`** — failed at runtime. Apps Script's static scope analysis routes any `DriveApp.getFileById` call to the restricted full `drive` scope regardless of manifest declarations, so the narrow scope was effectively ignored and the call threw "Required permissions: drive.readonly || drive."
  2. **`DriveApp.setSharing` with full `drive`** — redeployed at version `@8` with the widened scope. Still failed with the same runtime permission error on both maintainer accounts, even after scope change + redeploy. Root cause was not pinned down, but OAuth grant caching interacting with Test-users mode is the most plausible explanation. Committing the project to the restricted `drive` scope would also have imposed a considerable verification cost (CASA assessment) if the app ever moves out of Testing.
  3. **Drive Advanced Service v3 with `drive.file`** — works cleanly. The Drive REST API's `permissions.create` accepts `type: 'anyone'` under `drive.file` for files the app itself created, which covers every new-mode generation by construction. Re-consent triggered correctly when the new scope was added to the manifest, and subsequent runs succeeded without OAuth friction.
- **Consequences:**
  - OAuth footprint stays on non-restricted scopes, preserving an easy path to future Google app verification.
  - The response object for `generateIntoNewSpreadsheet` gains two additive fields (`autoShared`, `autoShareError`); `generateIntoExistingSpreadsheet` is unchanged. `docs/sheet_generation_contract.md` §12 already describes the launcher contract surface and does not need structural changes to accommodate these additive fields — the auto-share behavior was in-scope there.
  - Operator onboarding gains one prerequisite: the linked GCP project must have the Drive API enabled. Recorded in `apps_script/m1_sheet_generator/README.md`.
  - Future features that need to read or modify files not created by the app (e.g. cross-cycle spreadsheet discovery, reading operator-attached files) cannot piggyback on `drive.file` alone and would need to revisit this decision.
- **Related docs:** `apps_script/m1_sheet_generator/README.md`, `docs/sheet_generation_contract.md` §12, `docs/delivery_plan.md` §9 M1.1 C1, `docs/blueprint.md` §6–§7

### D-0024: Rule engine architecture contract — stateless surface, full-violation canonical ordering, scoped fixed-assignment handling
- **Date:** 2026-04-23
- **Status:** Accepted
- **Context:** M2 (`Minimal local compute pipeline`) needed a normative rule-engine contract before parser/normalizer implementation closure, so downstream solver/scorer planning would rest on a fixed validity-evaluation boundary instead of an informal understanding drawn from blueprint §7.4 and `docs/domain_model.md` §9.2 alone. Several design questions were live: whether the rule engine's public surface should expose a prepare-then-query lifecycle (cheaper for incremental search but harder to reason about and test) or a stateless pure-predicate surface; whether the engine should return only the first-hit violation or the full list of applicable violations; how to handle `FixedAssignment` entries that the parser admitted under its scoped exception (`docs/parser_normalizer_contract.md` §14); and how a future incremental-state implementation should be allowed in without replacing the reference behavior. The scoring-awareness question was also live — specifically, whether soft-effect reading should sit in the rule engine alongside hard-validity checks or in the scorer — and the answer interacts with D-0025 and D-0027.
- **Decision:** Adopt `docs/rule_engine_contract.md` as the normative rule-engine boundary with the following coherent set of decisions:
  1. **Stateless public surface.** The rule engine is a pure function `(normalizedModel, ruleState, proposedUnit) → Decision`. Implementations MAY internally cache/index as an optimization but MUST NOT expose session handles or prepare-then-query lifecycles at the contract surface.
  2. **Full violation list with canonical ordering.** `Decision.reasons` is always a list ordered canonically cheapest-first (`BASELINE_ELIGIBILITY_FAIL`, `SAME_DAY_HARD_BLOCK`, `SAME_DAY_ALREADY_HELD`, `UNIT_ALREADY_FILLED`, `BACK_TO_BACK_CALL`). When `valid = false`, `reasons` MUST include every applicable violation; partial violation lists are non-compliant. List length carries meaningful information (exactly the applicable-violation count) and is not implementation-defined.
  3. **First-release hard-rule enumeration with stable codes** aligned to `docs/domain_model.md` §9.2.
  4. **Scoped fixed-assignment handling.** Fixed assignments admitted at parser boundary are facts in `ruleState`; the rule engine never re-adjudicates them against themselves, but downstream-validity checks (including `BACK_TO_BACK_CALL` against fixed neighbors) fire on any non-fixed `proposedUnit` exactly as they would against solver-placed assignments. The parser-stage exception does not widen to other placements.
  5. **Separation from soft-effect evaluation.** The rule engine handles hard validity only. Soft effects (`prevDayCallSoftPenaltyTrigger`, `callPreferencePositive`) are read by the scorer directly from `DailyEffectState`; the rule engine does not expose a "what triggers are active" query. See D-0025 and D-0027.
  6. **Equivalence-test discipline for future non-stateless implementations.** Any future incremental-state implementation MUST reproduce the stateless reference's `Decision` outputs byte-identically (including canonical ordering) against a contract-owned fixture corpus that covers at minimum each hard invariant and the `FixedAssignment` scoped admission cases. The corpus is contract-owned, not implementation-owned, and divergences are contract-breaking defects.
- **Rationale:** A stateless surface is the cheapest thing to review, test, and re-implement. Every prepare-then-query lifecycle the rule engine could expose would leak into solver strategy code and constrain future strategies. Full-list violations preserve the information operators and diagnostic tooling will eventually want (rejection-reason distributions for benchmark campaigns; cf. FW-0012); the per-rule checks are each O(1) or O(small) lookups against indexed state, so running the full rule set on every invalid probe is negligible at first-release scale — the design tradeoff that would have motivated a short-circuit optimization does not materialize. Pulling soft effects fully out of rule-engine scope prevents the subtle drift where "this trigger applies on this date" ends up with two authoritative sources — one in the rule engine's internal state and one in the scorer's `DailyEffectState` read — which is how v1-style hidden coupling happens. The equivalence-test discipline is the narrow gate that lets a faster implementation ship without the reference becoming a "legacy path nobody maintains."
- **Consequences:** `docs/rule_engine_contract.md` is accepted as the normative boundary. `docs/solver_contract.md` (D-0026) consumes the rule engine through this interface only; `docs/scorer_contract.md` (D-0025) reads `DailyEffectState` directly rather than routing soft-effect queries through the rule engine. Any first-release implementation ships the stateless reference; incremental-state work is parked in FW-0003 under the equivalence-test gate. The rule-engine contract does not yet prescribe concrete API signatures or module decomposition — those are implementation-slice concerns.
- **Follow-up actions:** During rule-engine implementation, author the minimum equivalence-test corpus (at least one fixture per hard invariant plus `FixedAssignment` scoped admission cases) so FW-0003 can be triggered later without scrambling to build the corpus. Keep `docs/rule_engine_contract.md` aligned with any future changes to `docs/domain_model.md` §9.2 invariant enumeration.
- **Related docs:** `docs/rule_engine_contract.md`, `docs/domain_model.md` §9.2, §10.1, `docs/parser_normalizer_contract.md` §14, `docs/blueprint.md` §5 and §7.4.

### D-0025: Scorer architecture contract — pure function, required component breakdown, direction-guard invariant, `crReward` diminishing marginal utility
- **Date:** 2026-04-23
- **Status:** Accepted
- **Context:** M2 needed a normative scorer contract before compute-pipeline implementation started, for two reasons. First, several scorer-shape questions were live in parallel with the rule-engine work: whether scoring should be a pure function of `(allocation, normalizedModel, scoringConfig)` or a stateful service; whether `ScoreResult` should carry only `totalScore` or mandate a component breakdown; how the `HIGHER_IS_BETTER` direction invariant should be enforceable as a property test rather than enforced by convention; how `crReward` should behave to avoid a single doctor hoarding all honored `CR` requests without bolting on a separate fairness component; and whether streaming/delta scoring should be permitted alongside the pure-function reference. Second, the scorer's relationship to soft effects interlocks with D-0024 and D-0027 — `prevDayCallSoftPenaltyTrigger` and `callPreferencePositive` could live either in the rule engine (validated alongside hard rules) or in the scorer (read directly from `DailyEffectState`), and the placement matters for whether "apply this soft effect" is a lookup or a delegation.
- **Decision:** Adopt `docs/scorer_contract.md` as the normative scorer boundary with the following coherent set of decisions:
  1. **Pure-function public surface.** Scorer is `score(allocation, normalizedModel, scoringConfig) → ScoreResult`. No lifecycle, no side effects, no reads outside declared inputs.
  2. **Required component breakdown on every `ScoreResult`.** Every first-release component identifier from `docs/domain_model.md` §11.2 (`unfilledPenalty`, `pointBalanceWithinSection`, `pointBalanceGlobal`, `spacingPenalty`, `preLeavePenalty`, `crReward`, `dualEligibleIcuBonus`, `standbyAdjacencyPenalty`, `standbyCountFairnessPenalty`) MUST appear in `ScoreResult.components`, even when it contributes zero. Returning only `totalScore` is a contract violation.
  3. **`HIGHER_IS_BETTER` direction-guard invariant.** For any valid allocation `A` with score `S1`, converting one filled `AssignmentUnit` to unfilled produces allocation `A'` with score `S2` where `S2.totalScore ≤ S1.totalScore`. This invariant is property-testable and MUST be exercised in any implementation's test suite. It guards against silent direction inversions that would otherwise pass integration tests.
  4. **`crReward` diminishing marginal utility per doctor.** For any doctor `d`, the kth honored `CR` (k ≥ 2) contributes strictly less reward than the (k−1)th. The first honored `CR` for a doctor contributes the maximum. Exact curve shape is an implementation detail; the strict-monotonic-decrease property is contractually fixed.
  5. **Scorer-owned soft-effect reading.** Scorer reads `DailyEffectState` directly. The rule engine does not mediate soft-effect reads (see D-0024 and D-0027).
  6. **Operator-tuneable weights via sheet (v1 parity).** Component weights are extracted at parser boundary and flow as `scoringConfig.weights`, overriding template defaults at run time. Operator values MUST preserve per-component sign orientation (a reward component stays a reward regardless of the numeric weight).
  7. **Streaming/delta scoring permitted as optimization.** Implementations MAY ship a streaming implementation provided it produces byte-identical `ScoreResult` values to the pure-function evaluation within a single implementation on a single platform, and does not leak lifecycle state into the public contract. Byte-identical is the single normative parity criterion; cross-implementation or cross-platform parity is not guaranteed (see FW-0011).
- **Rationale:** A pure-function contract is the scorer's equivalent of the rule engine's statelessness: it makes the scorer the easiest thing to review, test, and re-implement, and it keeps it safe to call from any solver strategy (including future score-aware ones via the `scoringConsultation` extension clause). Mandating the component breakdown on every result converts "what does this score mean" from oral tradition into a contract-enforced artifact, which is the only way benchmark campaigns (FW-0015) will be able to compare strategies meaningfully. The direction-guard invariant operationalizes `HIGHER_IS_BETTER` against the specific class of bugs — sign errors, accidental penalty inversions, component swaps — that cost real engineering hours in v1. The `crReward` diminishing-marginal-utility curve solves the "one doctor hoards all honored `CR`" failure mode with a single well-specified component property, rather than requiring a separate fairness component to hold the line; the solver's `CR_MINIMUM_PER_DOCTOR` seeding (D-0026) complements this from the generation side. Permitting streaming as an optimization leaves a clear path to FW-0010 without making first-release implementations pay for it.
- **Consequences:** `docs/scorer_contract.md` is accepted as the normative boundary. Concrete weight values and `crReward` curve shape are explicitly deferred to the scorer implementation slice (FW-0014 queues the v1 reference pass). Operator-tuneable curve parameters beyond weights are deferred to FW-0007. Per-unit-position fairness (`unitPositionFairnessPenalty`) and `workloadWeight` on `SlotTypeDefinition` are queued as FW-0008 and FW-0009 respectively. Blueprint §16's current "routine variation" wording is narrower than this reality and receives a clarifying patch in the same change round as this decision (D-0028).
- **Follow-up actions:** During scorer implementation, author a direction-guard property test and a component-breakdown schema test so the two contract-level invariants are machine-enforced from day one. Reference v1's effective weights as FW-0014 describes.
- **Related docs:** `docs/scorer_contract.md`, `docs/domain_model.md` §11, `docs/request_semantics_contract.md` §10, `docs/blueprint.md` §5, §7.6, §16.

### D-0026: Solver architecture contract — scoring-blind, strategy-pluggable, whole-run failure, `maxCandidates` termination, retention moved downstream
- **Date:** 2026-04-23
- **Status:** Accepted
- **Context:** M2 needs a normative solver boundary alongside the rule-engine and scorer contracts (D-0024, D-0025) so implementation planning for the minimal local compute pipeline can proceed against a stable search-stage shape. Several design questions were live. First, whether the solver should be scoring-aware from day one (cheaper path to quality but harder to reason about and benchmark) or scoring-blind (matches blueprint §16 and isolates candidate generation from ranking). Second, whether the contract should admit one strategy or define a strategy-pluggability surface that can absorb future score-aware strategies (hill-climb, simulated annealing, beam search, parallel seeded-merge, constraint propagation, CP-SAT) without a contract rewrite. Third, how `CR` seeding and fill order should be specified: v1's effective behavior was "prefer to honor `CR`s first, then fill tightest slot first," and the checkpoint needed to make that explicit in contract language rather than relying on implementation lore. Fourth, how to compute the `CR` floor `X` — a fixed operator input, a smart default derived from the input distribution, or both. Fifth, termination: whether the first release admits wall-clock bounds (convenient for long runs but breaks byte-identical determinism) or candidate-count bounds only. Sixth, what happens when a slot is unfillable — partial allocation with unfilled markers, or whole-run failure. Seventh, where retention lives: in the solver (as v1 did) or downstream at a selector stage (which is what `docs/domain_model.md` §12 already anticipates). The answers to these are not independent; they interact with D-0024, D-0025, and D-0027.
- **Decision:** Adopt `docs/solver_contract.md` as the normative solver boundary with the following coherent set of decisions:
  1. **Scoring-blind public surface.** Solver is `(normalizedModel, ruleEngine, seed, fillOrderPolicy, terminationBounds, preferenceSeeding) → CandidateSet | UnsatisfiedResult`. The solver MUST NOT consume scorer, scoring config, or any soft-effect magnitude. Emitted `TrialCandidate` entries carry no score.
  2. **Strategy-pluggable interface with additive extension clause.** A strategy is identified by `strategyId` and described by a `StrategyDescriptor`. First release ships exactly `SEEDED_RANDOM_BLIND`. Future strategies MAY declare additional strategy-specific inputs and MAY opt into a read-only scoring-oracle handle (`scoringConsultation: "READ_ONLY_ORACLE"`), but the extension is additive only and never overrides scorer/rule-engine/retention-owned logic.
  3. **First-release composite `SEEDED_RANDOM_BLIND`.** Two phases: `CR_MINIMUM_PER_DOCTOR` preference seeding (Phase 1; best-effort; below-floor outcomes accepted; CR-vs-fixed-assignment conflicts skip the CR) + `MOST_CONSTRAINED_FIRST` fill (Phase 2; tightest-slot-first; tie-breaking seeded-deterministic).
  4. **`crFloor` computation.** `mode ∈ {"SMART_MEDIAN", "MANUAL"}`. `SMART_MEDIAN` default computes `X = floor(median(CR-count-per-doctor))` over the full doctor set (including zero-CR doctors). `MANUAL` uses the operator-supplied non-negative integer. `X = 0` effectively disables Phase 1. Computed `X` MUST be logged in `SearchDiagnostics` at run start — required for audit because `SMART_MEDIAN`'s value depends on input data.
  5. **Whole-run failure on any unfillable slot.** When any non-fixed demand unit cannot be filled under rule-engine validity within the declared termination bounds, the solver returns `UnsatisfiedResult` (with `unfilledDemand` identifying the offending units and `reasons` giving structured explanations). No partial allocations are emitted.
  6. **`maxCandidates`-only termination.** First-release `terminationBounds` is exactly `maxCandidates` (required, positive integer). No time budget. Strategies MUST NOT consult wall-clock time.
  7. **Byte-identical determinism within a single implementation on a single platform.** Randomized decisions derive exclusively from `seed`. Cross-implementation determinism is not guaranteed (FW-0011).
  8. **Retention moved downstream to the selector stage.** Solver does not implement retention modes. It emits every valid candidate up to `maxCandidates`. `TrialBatchResult` best-candidate fields are populated retroactively by the selector after scoring.
  9. **Operator-tuneable surface.** `crFloor.manualValue` is operator-tuneable (v1 parity); the scorer's component weights (D-0025) are separately operator-tuneable.
- **Rationale:** A scoring-blind solver with a strategy-pluggable interface is the cleanest way to keep first-release search reviewable while leaving room for the full slate of future strategies listed in FW-0004 and FW-0005 without a contract rewrite. The additive extension clause is specifically narrower than "strategies can do whatever they want": future score-aware strategies get a read-only oracle handle but never take over scorer-component responsibility, which is the specific coupling v1 had that made it hard to swap strategies cleanly. `CR_MINIMUM_PER_DOCTOR` plus `MOST_CONSTRAINED_FIRST` is the direct specification of what v1's effective seeded search did in practice — the contract is catching up to observed behavior and making it testable. `SMART_MEDIAN` as the default `crFloor` lets most operator inputs be self-tuning without a `MANUAL` override, while keeping `MANUAL` available when an operator has an informed preference. Whole-run failure on any unfillable slot is stricter than v1's behavior; it trades late-discovered operator frustration for upfront failure clarity, which aligns with blueprint §5 ("If no valid candidate exists, the system must report that clearly (not silently degrade)."). `maxCandidates`-only termination matches the determinism discipline in §16 — wall-clock bounds would make byte-identical reproducibility impossible, which would undermine both D-0025's direction-guard invariant testing and FW-0015's benchmark-campaign intent. Moving retention downstream to the selector is the v2 departure that matters most here: in v1, retention entangled with search made it hard to benchmark strategies on candidate-generation quality alone, and factoring it out lets FW-0013's richer retention modes land without touching solver code.
- **Consequences:** `docs/solver_contract.md` is accepted as the normative boundary. First-release implementation plan is `SEEDED_RANDOM_BLIND` only; FW-0004 and FW-0005 queue score-aware and parallel strategies behind the extension clause. The selector stage is now an explicit contract-closure item whose contract is not yet drafted; its first-release scope is `BEST_ONLY` as the default retention mode plus `FULL` retention as a per-run operator opt-in for ad-hoc auditability, with `TOP_K`, `FULL_WITH_DIAGNOSTICS`, and per-batch artifact export deferred to FW-0013 benchmark-campaign work. Benchmark campaign mode interactions with the solver are deferred to FW-0015. Blueprint §16 receives a clarifying patch (D-0028) so the operator-tuneable surface wording reflects `crFloor` alongside scorer weights.
- **Follow-up actions:** During solver implementation, author seeded-determinism tests that confirm byte-identical outputs under identical `(seed, normalizedModel, ruleEngine, fillOrderPolicy, terminationBounds, preferenceSeeding)` inputs. Implement the `SearchDiagnostics` logging for `strategyId`, `fillOrderPolicy`, `crFloorComputed`, `crFloorMode`, and `seed` at run start.
- **Related docs:** `docs/solver_contract.md`, `docs/rule_engine_contract.md`, `docs/scorer_contract.md`, `docs/domain_model.md` §10.1, §12, `docs/blueprint.md` §5, §7.5, §16.

### D-0027: Pipeline stage separation — three-stage `solver → scorer → selector`, retention with selector, scorer reads soft effects directly
- **Date:** 2026-04-23
- **Status:** Accepted
- **Context:** D-0024, D-0025, and D-0026 each fix a stage boundary, but the overall pipeline composition is itself a decision that deserves its own record. Specifically: is the pipeline two-stage (solver emits ranked candidates; retention with solver) or three-stage (solver emits unranked candidates; scorer ranks; selector applies retention)? And where do soft effects get read — inside the rule engine (symmetric with hard rules) or inside the scorer (direct read from `DailyEffectState`)? These two questions are not independent of D-0024/D-0025/D-0026 — they close out the last piece of the first-release pipeline shape.
- **Decision:** Adopt the following pipeline-composition decisions:
  1. **Three-stage pipeline `solver → scorer → selector`.** Solver emits unscored `CandidateSet` (or `UnsatisfiedResult`). Scorer produces one `ScoreResult` per candidate. Selector applies retention policy over scored candidates and produces the final `AllocationResult` (plus any retained artifacts).
  2. **Retention is owned by the selector stage, not by the solver.** The solver's retention boundary (`docs/solver_contract.md` §14) is specifically about this: first release ships `BEST_ONLY` as the default retention mode at the selector plus `FULL` retention as a per-run operator opt-in for ad-hoc auditability. `TOP_K` and `FULL_WITH_DIAGNOSTICS` modes, and per-batch artifact export formats, are deferred to FW-0013 benchmark-campaign work.
  3. **Solver is scoring-blind.** It does not consult scorer, scoring config, or soft-effect magnitude. See D-0026.
  4. **Scorer reads `DailyEffectState` directly from `normalizedModel`.** The rule engine does not expose a "what soft triggers are active on this date" query. The rule engine handles hard validity only; soft effects (`prevDayCallSoftPenaltyTrigger`, `callPreferencePositive`) are the scorer's concern. See D-0024 and D-0025.
- **Rationale:** The three-stage composition is what lets each stage be a pure function of its inputs (see the statelessness / pure-function discipline in D-0024 and D-0025) without any one stage needing to reach across boundaries. The specific retention placement is the v2 correction to v1's search-retention entanglement: putting retention with the selector lets benchmark campaigns (FW-0015) compare strategies on candidate-generation quality alone and then compare retention modes on scoring quality alone. The direct soft-effect read by the scorer avoids the specific drift where "what triggers apply here" ends up with two authoritative sources — if the rule engine also surfaced soft-effect information, scorers would eventually call into that surface and soft-effect evaluation would drift into a de facto shared responsibility. One authoritative soft-effect reader (the scorer) prevents that drift by construction.
- **Consequences:** The selector stage is an explicit contract-closure item for a later checkpoint; its contract is not drafted in this round. First-release selector scope is `BEST_ONLY` default retention plus `FULL` retention as a per-run operator opt-in over scored candidates (`docs/domain_model.md` §12.5), with `TOP_K`, `FULL_WITH_DIAGNOSTICS`, and per-batch artifact export formats deferred to FW-0013 benchmark-campaign work. All three stages in this round commit to pure-function / stateless public surfaces, which composes cleanly and is individually easier to test. Soft-effect evaluation is not split across the rule engine and scorer, so adding a new soft effect (beyond `prevDayCallSoftPenaltyTrigger` and `callPreferencePositive`) is a scorer change only.
- **Follow-up actions:** Author `docs/selector_contract.md` when the selector stage is scoped for implementation closure (likely in a subsequent checkpoint of M2 or under M3). Keep this decision as the anchor for why the selector exists as a distinct stage rather than as a solver sub-component or scorer add-on.
- **Related docs:** `docs/rule_engine_contract.md`, `docs/scorer_contract.md`, `docs/solver_contract.md`, `docs/domain_model.md` §8.2, §11, §12.

### D-0028: Operator-tuneable surface in first release is broader than blueprint §16's current wording
- **Date:** 2026-04-23
- **Status:** Accepted
- **Context:** `docs/blueprint.md` §16 currently says "Routine variation within an approved template is mainly limited to roster period/dates, doctor list, and doctor count." That wording predates the scorer- and solver-contract closures in this change round and is narrower than the operator-tuneable surface first release will actually carry. v1 already lets operators tune scorer component weights via the sheet; D-0025 formalizes that as `scoringConfig.weights`, and D-0026 adds the solver's `crFloor.manualValue` as a second operator-tuneable knob. Leaving §16 unchanged would create a small but real contradiction between blueprint guidance and the two contracts, which is the kind of drift blueprint §16 is specifically written to prevent.
- **Decision:** Patch `docs/blueprint.md` §16 in this change round to acknowledge that:
  1. Scorer component weights are operator-tuneable in first release via sheet inputs (v1 parity), as governed by `docs/scorer_contract.md` §15.
  2. The solver's `crFloor.manualValue` (when `crFloor.mode = "MANUAL"`) is operator-tuneable, as governed by `docs/solver_contract.md` §17.
  Keep the rest of §16 as-is — the structural-mapping / slot-group / request-semantics / allocation-layer restrictions remain valid. The patch is additive (one clarifying line/bullet), not a rewrite.
- **Rationale:** This is a wording drift fix, not a policy change. Operators already tune scorer weights in v1. Formalizing that in the scorer contract was the new work; updating §16 to match is the alignment step. Leaving §16's "mainly limited to roster period/dates, doctor list, and doctor count" literal standing would force future readers to reconcile blueprint guidance against two contracts, which is exactly the cross-doc inconsistency the repo has been spending time avoiding.
- **Consequences:** `docs/blueprint.md` §16 gains a clarifying bullet/line covering scorer weights and the solver `crFloor` knob; the rest of §16 is preserved. No structural rewrites to adjacent blueprint sections. The clarification is explicitly anchored to `docs/scorer_contract.md` §15 and `docs/solver_contract.md` §17 so subsequent readers can see where the detail lives.
- **Follow-up actions:** If future operator-tuneable surface broadens further (for example, operator-tuneable `crReward` curve parameters per FW-0007), update §16 again rather than allowing contract-level surfaces to quietly overtake blueprint wording.
- **Related docs:** `docs/blueprint.md` §16, `docs/scorer_contract.md` §15, `docs/solver_contract.md` §17.

### D-0029: `unitIndex` operational-equivalence — same-`SlotType` units are equivalent in validity and baseline workload weight
- **Date:** 2026-04-23
- **Status:** Accepted
- **Context:** During M2 C1 contract design (D-0024 / D-0025 / D-0026), the question came up of how to model multi-unit demand for departments where one `(dateKey, slotType)` has `requiredCount > 1` (for example, a future department needing 10 medical-officer call slots per day, operationally numbered MO1..MO10 on the sheet). An earlier draft suggested that semantically-distinct positions could be modeled as distinct `unitIndex` values on the same `SlotType` with potentially differential weight ("MO1 is 10% heavier than MO5"). That suggestion was rejected on operational grounds: assigning differential per-position weight is arbitrary and unjustifiable in real rostering practice; what operators actually want is even *distribution* across positions over time, not per-position difficulty differentiation. ICU/HD first release does not exercise this case at all (`requiredCount = 1` everywhere), but the contract direction needs to be settled before any future multi-unit department lands so the architecture does not drift into per-position weighting on the way in.
- **Decision:** All `AssignmentUnit` entries that share the same `(dateKey, slotType)` pair (i.e., differ only by `unitIndex`) are **equivalent** for hard-validity rules (eligibility, blocks, back-to-back, uniqueness) and for baseline workload weight. `unitIndex` is a stable operational identity that supports writeback labeling (for example, "MO1", "MO2", "MO3" mapping to `unitIndex = 0, 1, 2`) but MUST NOT carry implicit difficulty or workload differentiation in any contract. Concretely:
  1. **Doctor-admissibility equivalence.** For any `(dateKey, slotType, doctorId)` triple and any `ruleState`, the rule engine's doctor-admissibility hard invariants — `BASELINE_ELIGIBILITY_FAIL`, `SAME_DAY_HARD_BLOCK`, `SAME_DAY_ALREADY_HELD`, `BACK_TO_BACK_CALL` (`docs/rule_engine_contract.md` §11) — MUST evaluate identically regardless of which `unitIndex` the `proposedUnit` refers to. These four rules govern whether a given doctor can be placed on a given `(dateKey, slotType)` at all; they do not branch on `unitIndex`. The fifth hard invariant, `UNIT_ALREADY_FILLED`, is NOT a doctor-admissibility rule — it is per-unit occupancy bookkeeping keyed on the full `(dateKey, slotType, unitIndex)` identity, and it correctly branches on `unitIndex` by construction (that is exactly how `requiredCount > 1` multiplicity is tracked). The equivalence property does not relax per-unit occupancy; a unit that is filled is filled, and its `unitIndex` identity is how that occupancy is recorded.
  2. **Baseline workload-weight equivalence.** The scorer MUST treat all units of the same `SlotType` as carrying identical baseline workload weight. Per-position fairness across `unitIndex` values is a future additive scoring component (FW-0008), not a `unitIndex` weight; per-`SlotType` burden weighting is a future additive `SlotTypeDefinition` field (FW-0009 / `docs/domain_model.md` §7.6).
  3. **Modeling boundary.** Departments that genuinely need semantically-differentiated roles MUST model them as distinct `SlotType` identities (for example, separate `MO_PRIMARY_CALL` and `MO_BACKUP_CALL` slot types), not as distinct `unitIndex` values of the same `SlotType`. Adding semantic meaning to `unitIndex` itself is contract-prohibited and would constitute a breaking shape change to `docs/domain_model.md` §10.2.
  4. **Solver canonical fill-order for multi-unit demand is deferred.** The first multi-unit department will need a canonical determinism rule for which unfilled `unitIndex` to fill first within a `(dateKey, slotType)` (FW-0017 captures this). The equivalence in this decision does not by itself fix the determinism rule; it only fixes that the rule does not turn on weight differentiation.
- **Rationale:** Operationally, when a department writes "MO1, MO2, MO3" on the roster, those numbered positions are operationally identifiable but architecturally interchangeable — the doctor on MO1 is not doing a heavier or lighter shift than the doctor on MO5; the numbers are sequencing labels, not workload signals. Trying to encode per-`unitIndex` weight would create unjustifiable knobs (what is the actual weight ratio between MO1 and MO5? nobody can defensibly say) and would push the rostering problem into per-position fairness logic that no operator is asking for. Distribution fairness — "doctor X has been MO5 six times this month while doctor Y has been MO5 zero times" — is a real operator concern, but it belongs in a fairness scoring component (FW-0008), not in baseline weight differentiation. Forcing genuinely-different roles to be distinct `SlotType` identities also keeps the eligibility / hard-rule surface honest: if MO_PRIMARY and MO_BACKUP have different eligibility groups or different rules, those differences live in the template's slot/group declarations, not buried inside `unitIndex` semantics.
- **Consequences:** `docs/domain_model.md` §10.2 is patched in the same change round as this decision to state the equivalence property in its Notes section. `docs/rule_engine_contract.md` §11 inherits the equivalence — its hard-invariant codes already do not branch on `unitIndex` — and does not require a contract change. `docs/scorer_contract.md` baseline workload-weight components inherit the equivalence and likewise do not require a contract change. FW-0008 (per-unit-position fairness) and FW-0009 (`workloadWeight` on `SlotTypeDefinition`) remain the future-work surfaces for multi-unit fairness and per-`SlotType` burden weighting respectively. FW-0017 is added in the same change round to capture the still-open canonical-fill-order question for multi-unit demand once it materializes. ICU/HD first release is unaffected operationally — `requiredCount = 1` everywhere means `unitIndex` is always 0 — but the architectural direction is settled so future multi-unit departments do not have to relitigate it.
- **Follow-up actions:** When the first multi-unit department template is being authored, point template authors at this decision and at FW-0017. If a department case ever emerges where per-`unitIndex` differentiation appears genuinely necessary, the right move is to revisit by splitting into distinct `SlotType` identities (or by introducing the `workloadWeight` extension per FW-0009), not by reopening this decision.
- **Related docs:** `docs/domain_model.md` §7.7, §10.2; `docs/rule_engine_contract.md` §11; `docs/scorer_contract.md` §10, §11; `docs/future_work.md` FW-0008, FW-0009, FW-0017.
