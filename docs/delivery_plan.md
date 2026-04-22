# Delivery Plan

## 1. Purpose of this document
This is the **living execution guide** for Roster Monster v2.

It defines what is actively being delivered now (active milestone, active checkpoint, and supporting tasks) and what is intentionally next.

It does **not** replace:
- architecture truth in `docs/blueprint.md`
- milestone-level sequencing in `docs/roadmap.md`
- normative technical boundaries in contract docs
- issue-level implementation tracking

## 2. Planning vocabulary
- **Product**: the full end-to-end capability being built.
- **Milestone**: a major delivery state that advances product readiness.
- **Checkpoint**: a bounded, reviewable step inside a milestone.
- **Task**: a concrete work item used to close a checkpoint.

Working rule: this repo should normally maintain **one active milestone** and **one active checkpoint** at a time.

## 3. Product definition
Roster Monster v2 builds a reusable roster-allocation core with department-specific template control, while preserving Google Sheets as the operational front end. ICU/HD is the first concrete implementation target.

## 4. Product-level delivery principles
- Preserve Google Sheets as the operational front end.
- Keep architecture-first and contract-first boundaries where needed.
- Prioritize work that directly unblocks real operator workflow.
- Avoid reopening settled contracts unless there is a strong consistency reason.
- Avoid spending effort on items that do not support the active checkpoint.

## 5. Milestone map

### M1 — Operator-ready request sheet generation
- **Goal:** Deliver an operator-usable ICU/HD request sheet shell, backed by closed generation contract boundaries.
- **Why it matters:** Immediate operational need; unblocks the next request sheet cycle and anchors downstream work.
- **Status:** **Completed** *(closed 2026-04-21 on operator delivery; see §11 and D-0019)*
- **Dependencies:** template/request/generation contract surfaces.
- **Exit criteria:** generation inputs, structural surfaces, operator edit boundaries, non-goals, and acceptance criteria are closed, and operator-ready ICU/HD sheet-shell generation is implemented for the empty-form use (new spreadsheet file or new tab in existing spreadsheet) with intended editable/protected behavior and practical validation in place.
- **Likely checkpoints:**
  - Close sheet-generation MVP boundary. *(C1, closed 2026-04-17)*
  - Align template artifact surfaces with generation needs. *(C2, closed 2026-04-18)*
  - Generation acceptance/handoff readiness. *(C3, closed 2026-04-18)*
  - Implement operator-ready sheet generation. *(C4, closed 2026-04-21)*

### M1.1 — Operator-facing launcher *(addendum to M1)*
- **Goal:** Provide a narrow operator-facing launcher so named monthly-rotation pilot operators can invoke empty ICU/HD request-sheet generation without running Apps Script by hand.
- **Why it matters:** Closes M1's operator-facing story end-to-end; turns a maintainer-only generator into a pilot-usable launcher without expanding M1's compute scope.
- **Status:** **Active** *(addendum milestone; M1 itself stays Completed, not reopened)*
- **Dependencies:** M1 complete; `docs/sheet_generation_contract.md` §12 (launcher surface).
- **Exit criteria:** a non-maintainer test operator can, after one-time Google consent, load the launcher URL, submit the form, and receive a working generated sheet or tab in either output mode, validated hands-on.
- **Likely checkpoints:**
  - Implement operator launcher web app.
- **Addendum framing:** M1.1 is derivative of M1's operator-facing surface, not a compute-line milestone. Addendum numbering convention (`M<parent>.<n>` with integer `n`, no nested decimals) is recorded in D-0021.

### M2 — Minimal local compute pipeline
- **Goal:** Stand up deterministic local parse/normalize/solve flow against closed contracts.
- **Why it matters:** Establishes executable core path before scale/orchestration.
- **Status:** Planned *(deferred during M1.1 addendum; next to activate after M1.1 closure)*
- **Dependencies:** M1 complete; snapshot/parser/domain boundaries stable.
- **Exit criteria:** repeatable local run path with interpretable outputs for ICU/HD scenarios.
- **Likely checkpoints:** parser-normalizer implementation closure; minimal rule/scorer/solver integration; local run artifact basics.

### M3 — Safe result/output and writeback
- **Goal:** Define and implement safe output surfaces and writeback behavior.
- **Why it matters:** Operator trust depends on safe, clear result delivery.
- **Status:** Planned
- **Dependencies:** M2 complete; stable output/writeback contract surfaces.
- **Exit criteria:** controlled operator-safe writeback and explicit failure/unsatisfied-state handling.
- **Likely checkpoints:** output contract closure; writeback mapping validation; result safety checks.

### M4 — Parallel operational search and orchestration
- **Goal:** Add reliable external/parallel execution without changing core compute semantics.
- **Why it matters:** Needed for operational reliability and throughput.
- **Status:** Planned
- **Dependencies:** M3 complete; stable local semantics.
- **Exit criteria:** traceable external execution lifecycle with guarded retries/failure handling.
- **Likely checkpoints:** execution envelope boundaries; orchestration mechanics; idempotence/retry guardrails.

### M5 — Observability and benchmark hardening
- **Goal:** Harden diagnostics, benchmark workflow, and reliability posture.
- **Why it matters:** Long-term confidence requires measurable, repeatable behavior.
- **Status:** Planned
- **Dependencies:** M4 complete; stable execution/output surfaces.
- **Exit criteria:** practical observability coverage and benchmark baselines for regression control.
- **Likely checkpoints:** event/log surface hardening; benchmark campaign baselines; reliability hardening passes.

## 6. Current active milestone
- **Active milestone:** `Operator-facing launcher` (M1.1, addendum to M1)

This is active now because:
- M1 (`Operator-ready request sheet generation`) closed on 2026-04-21 with operator-delivered ICU/HD sheet-shell generation in both output modes
- the generator is currently maintainer-only: each run requires direct Apps Script execution, which blocks non-maintainer operators in the monthly rotation from using it
- M1.1 closes that gap with a narrow operator-facing launcher that wraps the existing M1 entrypoints — no new compute, no new contract surface beyond a thin launcher addendum in `docs/sheet_generation_contract.md` §12
- activating M1.1 as an addendum (rather than reopening M1 or expanding M2) preserves M1 closure integrity and keeps M2's compute-core direction untouched; see D-0021 for the addendum-milestone framing and D-0022 for the launcher architecture

## 7. Checkpoint plan for the active milestone

M1.1 has a single implementation checkpoint because its architecture/contract surface is settled inside this same planning patch (see `docs/sheet_generation_contract.md` §12 and D-0021/D-0022).

### C1 — Implement operator launcher web app
- **Goal:** deliver a pilot-usable Apps Script web-app launcher consistent with the settled M1.1 contract surface.
- **In scope:** `doGet()` HTML form; form submission wired to the existing `generateIntoNewSpreadsheet` / `generateIntoExistingSpreadsheet` entrypoints; shared spreadsheet-reference normalization (accept URL or bare ID); Apps Script web-app deployment; GCP OAuth consent-screen Test Users list curation for the pilot operators.
- **Out of scope:** operator-editable template, persisted per-operator state, multi-department selector beyond ICU/HD, any compute work moving into Apps Script, public/open signup, and M2 compute-core work.
- **Dependencies:** M1 complete; `docs/sheet_generation_contract.md` §3A and §12.
- **Done criteria:** a non-maintainer test operator can, after one-time Google consent, load the launcher URL, submit the form, and receive a working generated sheet/tab in either output mode; sign-off recorded in §11.

## 8. Current active checkpoint
- **Active checkpoint:** `Implement operator launcher web app` (M1.1 C1)

Why this checkpoint is next:
- it is the only remaining checkpoint under M1.1 once the contract/architecture closure in this planning patch lands
- narrower than waiting for M2 to begin while the monthly rotation has no operator-facing entrypoint
- preserves M2 sequencing by deferring, not skipping

## 9. Task list for the current checkpoint

**C1 progress snapshot (reconciled 2026-04-22):** T1, T2, and T3 are Done — the launcher has shipped to the `/exec` deployment with §12.5 reference normalization, the `doGet()` form + `submitLauncherForm` wiring, and the deployment/Test-Users/consent walk-through documented in `apps_script/m1_sheet_generator/README.md`. T4 (hands-on non-maintainer verification + C1 sign-off note in §11) is the only remaining gate before M1.1 can close. Additive operational scope beyond T1–T4 landed during C1 and is captured in the **Additive scope landed during C1** note below rather than as retroactively-inserted tasks.

### T1 — Extend generator config helper to accept spreadsheet URL or bare ID
- **Purpose:** normalize the operator-supplied spreadsheet reference centrally (in `normalizeAndValidateConfig_`) so the launcher can pass the operator's raw input through unchanged, and existing entrypoint callers (including smoke tests) also benefit. Accepts both a full Google Sheets URL and a bare ID; extraction rule per `docs/sheet_generation_contract.md` §12.5.
- **Status:** Done
- **Relevant files:** `apps_script/m1_sheet_generator/src/GenerateSheet.gs`; `docs/sheet_generation_contract.md` §3A + §12.5.
- **Done condition:** both forms normalize correctly to a bare ID before reaching `SpreadsheetApp.openById`, with a human-readable error on unrecognized input.
- **Closure evidence:** `extractSpreadsheetId_` in `GenerateSheet.gs` implements §12.5 and is called from `normalizeAndValidateConfig_` before `SpreadsheetApp.openById`; landed via `f556d8a`, refined by `5bbf695` (matcher tightening) and `15b181d` (account-scoped URLs).

### T2 — Implement `doGet()` HTML form + wiring to existing entrypoints
- **Purpose:** serve an operator-facing form with the fields declared in `docs/sheet_generation_contract.md` §12.4, and wire submission (via `google.script.run`) to the existing generation entrypoints. Success/failure rendering per §12.6.
- **Status:** Done
- **Relevant files:** `apps_script/m1_sheet_generator/src/` (new launcher module and HTML).
- **Done condition:** form renders, submits, and returns a clickable link to the generated sheet or tab on success; surfaces validation/normalization errors on failure.
- **Closure evidence:** `Launcher.gs` (`doGet`, `submitLauncherForm`, `include_`), `LauncherForm.html` (form fields + `google.script.run.submitLauncherForm` wiring + success-view scriptlet), and `LauncherSuccess.html` (clickable link render) landed via `9887f4b`; error paths return through the `{ ok: false, error }` branch per §12.6.

### T3 — Configure Apps Script web-app deployment and GCP OAuth Test Users
- **Purpose:** deploy the Apps Script project as a web app ("Execute as: User accessing the web app"), and curate the GCP OAuth consent-screen Test Users list with the pilot operators per `docs/sheet_generation_contract.md` §12.3. Document the per-operator URL-visit consent step in `apps_script/m1_sheet_generator/README.md`.
- **Status:** Done
- **Relevant files:** `apps_script/m1_sheet_generator/README.md`; GCP console (no repo change).
- **Done condition:** the deployed launcher URL loads the form for a maintainer account; Test Users list contains the pilot operators; README documents the one-time consent walk-through.
- **Closure evidence:** README sections "Operator-facing Web App launcher (M1.1)" → "Deployment model", "Adding an operator to Test Users", and "First-run consent walk-through for a new operator" document the `executeAs: USER_ACCESSING` + `access: ANYONE` deployment and the per-operator Test Users workflow. A stable `/exec` deployment exists behind the operator-facing `https://tinyurl.com/cghicuhdlauncherv1` redirect. Off-repo GCP Test Users curation is an ongoing monthly-rotation maintainer action per D-0022, not a one-shot task closure.

### T4 — Verify end-to-end with a non-maintainer test operator
- **Purpose:** confirm M1.1 exit criteria hands-on — a non-maintainer test operator can load the launcher URL, complete OAuth consent, submit the form, and receive a working generated sheet/tab in both output modes. This is the last remaining gate before M1.1 can close, since T1–T3 are Done.
- **Status:** Planned
- **Relevant files:** `docs/delivery_plan.md` §11 (sign-off note).
- **Done condition:** at least one non-maintainer pilot operator has exercised both output modes successfully and the result is recorded as the C1 sign-off note in §11.

### Additive scope landed during C1
Auto-share of newly-created spreadsheets to "anyone with the link (Editor)" landed during C1 as operational polish on top of T1–T4. It was not a pre-declared task and is not being retroactively inserted as one; the directional decision, the three-attempt sequence (`DriveApp` under `drive.file` → `DriveApp` under full `drive` → Drive Advanced Service v3 under `drive.file`), and the resulting additive response-field surface (`autoShared`, `autoShareError`) are recorded in **D-0023**. Implementation lives in `tryAutoShareAnyoneWithLink_` in `GenerateSheet.gs` and in the success-view rendering branch in `LauncherForm.html`. Existing-spreadsheet mode intentionally inherits parent-file sharing and is unchanged. No contract structural change was needed — the additive fields sit within the `docs/sheet_generation_contract.md` §12 launcher surface already described there.

## 10. Explicitly deferred for now
- Solver implementation details.
- Scorer implementation details.
- Local run implementation mechanics.
- Writeback implementation mechanics.
- Worker/orchestrator mechanics.
- Benchmark hardening depth beyond milestone-level framing.
- Broad multi-department generalization beyond ICU/HD-first sequencing.
- Public or open-signup operator access for the launcher; first-release scope is named monthly-rotation pilot operators only, gated via GCP OAuth consent-screen Test Users.
- In-app operator allowlist / role model inside the launcher; access gating stays external to the app for pilot scope.
- Operator-editable template or structural mapping; template stays maintainer-owned.
- Persisted per-operator state beyond Google's OAuth session.
- Alternative launcher platforms (for example a static page over the Apps Script API Executable); the pilot sticks with Apps Script Web App per D-0022.

## 11. Recently completed checkpoints
- **C4 — Implement operator-ready sheet generation** *(closed 2026-04-21)*
  - Delivered the ICU/HD request sheet shell end-to-end through Google Apps Script in `apps_script/m1_sheet_generator/`, covering both output modes (new spreadsheet file, new tab in existing spreadsheet).
  - Applied whole-sheet protection restricted to the script owner with unprotected exceptions for operator-editable surfaces (doctor-name cells, request-entry cells, call-point cells, lower-shell assignment cells) and warning-only regex validation on request-entry cells.
  - Verified against the C3 acceptance checklist for an operator-owned May 2026 cycle (CGH ICU/HD Call, 2026-05-04 to 2026-06-01, 9/6/7 manpower) via `clasp run` execution against a user-managed GCP project.
  - Operator-facing operational lesson recorded as D-0020: `clasp run` requires both (a) GCP OAuth consent-screen scope allowlist and (b) `clasp login --use-project-scopes --include-clasp-scopes`.
  - Task closure status: T1 Done, T2 Done, T3 Done, T4 Done, T5 Done.
  - Main affected surfaces: `apps_script/m1_sheet_generator/` (code + README); no authoritative contract changes required.

### C4 sign-off note
C4 is complete. M1 is now delivered on operator terms, not just contract closure: the generator produces an operator-usable ICU/HD request sheet shell against settled M1 contracts, in both output modes, with intended editable/protected surfaces and practical validation in place, and has been exercised hands-on against an operator-owned May 2026 spreadsheet.

- **C3 — Define generation acceptance/handoff readiness** *(closed 2026-04-18)*
  - Locked M1 implementation-ready checklist for ICU/HD first-release generation handoff without reopening C1/C2.
  - Declared the first allowed implementation slice (template read + operator inputs + shell generation + output-mode support + practical locking/validation).
  - Declared explicit out-of-scope items to prevent parser/compute/writeback/orchestration/benchmark scope drift during generation-slice start.
  - Task closure status: T1 Done, T2 Done, T3 Done.
  - Main affected docs: `docs/delivery_plan.md`.

### C3 sign-off note
C3 is complete. M1 generation boundary is now implementation-handoff ready: acceptance assumptions, immediate generation-slice start scope, out-of-scope guardrails, and final contract-to-implementation notes are explicit and sufficient for execution without reopening milestone-level scope.

- **C2 — Align template artifact vs generation needs** *(closed 2026-04-18)*
  - Closed remaining cross-doc alignment between `docs/template_artifact_contract.md` and `docs/sheet_generation_contract.md`, including first-release visible title/header generated-surface alignment.
  - Confirmed ICU/HD first-release combined-shell generation declarations remain consistency-aligned and non-redesign.
  - Task closure status: T1 Done, T2 Done, T3 Done.
  - Main affected docs: `docs/template_artifact_contract.md`, `docs/sheet_generation_contract.md`, `docs/delivery_plan.md`.

### C2 sign-off note
C2 is complete. Template artifact and generation contract surfaces are now sufficiently aligned for ICU/HD first-release sheet-shell generation usage, with no material remaining ambiguity requiring checkpoint-level redesign before C3 handoff-readiness framing.

- **C1 — Close sheet-generation MVP boundary** *(closed 2026-04-17)*
  - Closed generation inputs, generated structural surfaces, allowed operator edits, editable/protected + validation boundary, explicit non-goals, and acceptance framing at contract/planning level.
  - Task closure status: T1 Done, T2 Done, T3 Done, T4 Done, T5 Done, T6 Done.
  - Main affected docs: `docs/sheet_generation_contract.md`, `docs/delivery_plan.md`.

### C1 sign-off note
C1 is complete. The sheet-generation MVP boundary is now closed for execution: generation inputs, structural surfaces, allowed operator edits, editable/protected + validation expectations, explicit non-goals, and checkpoint acceptance framing are sufficiently fixed to proceed to C2 without reopening milestone-level scope.

### Recently completed milestones
- **M1 — Operator-ready request sheet generation** *(closed 2026-04-21)*
  - Closed on operator delivery via C4, against settled contract surfaces fixed in C1/C2/C3. See D-0019 for the formal closure decision and D-0020 for the operator-facing clasp OAuth operational lesson surfaced during M1 execution.

## 12. Change log for this delivery plan
- **2026-04-16:** Document created as the living execution guide.
- **2026-04-16:** Activated Milestone 1 (`Operator-ready request sheet generation`).
- **2026-04-16:** Activated Checkpoint 1 (`Close sheet-generation MVP boundary`).
- **2026-04-17:** Closed Checkpoint 1 (`Close sheet-generation MVP boundary`) and recorded formal sign-off in this plan.
- **2026-04-17:** Activated Checkpoint 2 (`Align template artifact vs generation needs`) as current execution focus.
- **2026-04-18:** Closed Checkpoint 2 (`Align template artifact vs generation needs`) and recorded formal sign-off in this plan.
- **2026-04-18:** Activated Checkpoint 3 (`Define generation acceptance/handoff readiness`) as current execution focus.
- **2026-04-18:** Closed Checkpoint 3 (`Define generation acceptance/handoff readiness`) with explicit M1 implementation-ready checklist, allowed first implementation slice, out-of-scope guardrails, and contract-to-implementation handoff notes.
- **2026-04-18:** Closed Milestone 1 (`Operator-ready request sheet generation`) and activated Milestone 2 (`Minimal local compute pipeline`).
- **2026-04-18:** Seeded M2 active checkpoint (`Parser/normalizer implementation closure`) with narrow parser-first task framing.
- **2026-04-18:** Reopened Milestone 1 in place so milestone closure aligns with operator delivery rather than contract closure alone; returned Milestone 2 to Planned.
- **2026-04-18:** Activated Checkpoint 4 (`Implement operator-ready sheet generation`) as the current M1 implementation checkpoint; seeded compact task list T1–T5.
- **2026-04-21:** Closed Checkpoint 4 (`Implement operator-ready sheet generation`) with T1–T5 Done; verified the generated shell against the C3 acceptance checklist against an operator-owned May 2026 cycle.
- **2026-04-21:** Closed Milestone 1 (`Operator-ready request sheet generation`) on operator delivery; see D-0019.
- **2026-04-21:** Activated Milestone 2 (`Minimal local compute pipeline`) at milestone level; M2 checkpoints listed but none yet activated.
- **2026-04-21:** Activated Milestone 1.1 (`Operator-facing launcher`) as an addendum to closed Milestone 1; returned Milestone 2 to Planned under the one-active-milestone rule. See D-0021 (addendum-milestone convention) and D-0022 (launcher architecture).
- **2026-04-21:** Activated Checkpoint 1 (`Implement operator launcher web app`) as the M1.1 execution focus; seeded compact task list T1–T4.
- **2026-04-22:** Reconciled §9 C1 task status against shipped code (T1/T2/T3 Done, T4 remains the only pending gate) and captured the auto-share additive scope (D-0023) that landed during C1 without retroactively inserting new tasks. Reconciliation is documentation-only; C1 stays active pending T4 sign-off.

## 13. Relationship to other repo docs
- `README.md` = front door orientation.
- `docs/blueprint.md` = stable architecture truth.
- `docs/roadmap.md` = milestone-level delivery order.
- `docs/delivery_plan.md` = active execution guide.
- `docs/decision_log.md` = accepted directional decisions.
- Contract docs = normative technical boundary definitions.

## 14. Maintenance rules for this document
- Keep exactly one active milestone unless there is a deliberate exception.
- Keep exactly one active checkpoint unless there is a deliberate exception.
- Update this document whenever execution focus changes.
- Do not duplicate normative contract wording here.
- Do not turn this document into a full issue tracker.
- If a task does not support the active checkpoint, it likely does not belong here.

## 15. Initial seed content
This version reflects the 2026-04-21 activation of M1.1 (`Operator-facing launcher`) as an addendum to closed Milestone 1, and is seeded with:
- active milestone `Operator-facing launcher` (M1.1, addendum to M1)
- active checkpoint `Implement operator launcher web app` (M1.1 C1), with compact task list T1–T4
- M2 (`Minimal local compute pipeline`) returned to Planned pending M1.1 closure
- closed-milestone trail for M1 in §11 with C4 sign-off note and D-0019/D-0020 anchors
- explicit deferrals extended to cover launcher-scope drift (public signup, in-app allowlist, operator-editable template, persisted per-operator state, alternative launcher platforms)
