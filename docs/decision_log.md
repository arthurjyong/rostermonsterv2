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
