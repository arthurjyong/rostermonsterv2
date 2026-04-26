# Writeback Contract (First-Pass Working Draft)

## 1) Contract status and scope
This document defines the writeback boundary that sits between the selector's `FinalResultEnvelope` output (`docs/selector_contract.md`) and the operator-facing Google Sheets shell that M1 generated (`docs/sheet_generation_contract.md`).

It is intended to be concrete enough for implementation planning for writeback work.

It explicitly separates:
- repo-settled anchors,
- writeback-boundary decisions adopted in this checkpoint,
- still-open items in this checkpoint,
- and explicit deferrals.

Scope is limited to writeback-stage rendering of a `FinalResultEnvelope` into the operator-facing spreadsheet. This is not a sheet-generation, rule-engine, scorer, solver, selector, parser/normalizer, or execution design document.

This contract is drafted **scope-ahead of M3 activation** alongside the four M2 compute-pipeline contracts (rule engine / scorer / solver / selector). M3 (`Safe result/output and writeback`) remains `Planned` per `docs/delivery_plan.md` §5; M2 (`Minimal local compute pipeline`) remains the active milestone. Drafting the writeback contract scope-ahead lets the compute-pipeline boundary that feeds writeback (the selector's `FinalResultEnvelope` per `docs/selector_contract.md` §10) carry through to a settled receiver-side surface without forcing M3 activation while M2 is still mid-flight; see D-0031.

Hard validity is **not** in writeback scope; the rule engine remains the sole hard-validity authority (`docs/rule_engine_contract.md`). Scoring is **not** in writeback scope; the scorer remains the sole component-score authority (`docs/scorer_contract.md`). Search is **not** in writeback scope; the solver remains the sole candidate-generation authority (`docs/solver_contract.md`). Selection and retention are **not** in writeback scope; the selector remains the sole final-result-construction and retention authority (`docs/selector_contract.md`).

## 2) Contract identity and versioning
Contract identity/version for binding:
- `contractId: WRITEBACK`
- `contractVersion: 1`

Version bump rule (normative):
- bump `contractVersion` only when writeback-stage input/output shape, branch-on-write semantics, atomicity/idempotency discipline, doctor identity resolution mechanism, run-envelope traceability surface (visible footer rows or hidden developer metadata keys), or determinism guarantees change in a way that breaks v1-targeted readers.
- do **not** bump for wording cleanup, formatting, added examples, additive run-envelope fields per `docs/selector_contract.md` §16.3 that v1-targeted writeback readers can tolerate, additive hidden developer metadata keys that v1-targeted readers can ignore, or clarification that does not change behavior.

## 3) Status discipline used in this document
Each normative statement is classified as one of:
- **Repo-settled**: already anchored by existing repo contracts/blueprint/decision log.
- **Proposed in this checkpoint**: adopted here as first-release writeback-boundary direction.
- **Still open in this checkpoint**: recognized as unresolved here and left explicit.
- **Deferred**: intentionally out of this checkpoint's decision scope.

## 4) Repo-settled architecture anchors
The following are treated as repo-settled anchors:
- The pipeline is three-stage `solver → scorer → selector`; the selector is the final compute stage producing the operator-facing result, and writeback consumes that result downstream (`docs/decision_log.md` D-0027).
- Apps Script is the platform for the M1 sheet-generation surface and for operator-facing sheet-side work, with compute-heavy core staying local-first Python (`docs/decision_log.md` D-0017, D-0018). Writeback is sheet-facing and inherits this stack split; see §6.
- Auto-share / Drive Advanced Service v3 OAuth-scope discipline established for M1.1 carries into writeback: writeback MUST stay on non-restricted scopes available to the operator-execution context already in use, and MUST NOT introduce a new credential surface (`docs/decision_log.md` D-0023).
- The selector's `FinalResultEnvelope` shape (`docs/selector_contract.md` §10) is the upstream input writeback consumes. Selector contract v2 (`docs/selector_contract.md` §2.1, §9 item 3; `docs/decision_log.md` D-0032) requires `runEnvelope.sourceSpreadsheetId` and `runEnvelope.sourceTabName` so selector compliance implies writeback input compatibility for source-sheet identity (see §18; `docs/decision_log.md` D-0030, D-0031, D-0032).
- Operator-allowed edits after M1 sheet generation include column A doctor names, request-entry cells, call-point cells, and lower-shell prefilled fixed-assignment cells (`docs/sheet_generation_contract.md` §6). Writeback's snapshot bundle (§9) carries these surfaces literally so the writeback tab can reconstruct them without reaching back into the source tab.
- `Doctor.doctorId` is runtime identity; `displayName` is the human-facing/output-facing identity (`docs/domain_model.md` §7.3). Writeback-side mapping from `doctorId` to displayed cell value is the writeback contract's resolution responsibility; see §12.
- `AssignmentUnit` is the smallest retained assignment atom (`docs/domain_model.md` §10.2); `AllocationResult` is the canonical solved-allocation output object (`docs/domain_model.md` §10.3); `AssignmentUnit` and `AllocationResult` enter writeback through `FinalResultEnvelope.result` on the success branch.
- `unitIndex` is operationally identifying but does not carry implicit difficulty or workload differentiation (`docs/decision_log.md` D-0029; `docs/domain_model.md` §10.2). Writeback-side rendering of multi-unit demand is deferred (see §22 and FW-0021) because ICU/HD first release uses `requiredCount = 1` everywhere (`docs/sheet_generation_contract.md` §5; `docs/domain_model.md` §7.7).
- Solver returns whole-run failure as `UnsatisfiedResult` rather than partial allocation (`docs/solver_contract.md` §10.2, §14; D-0026 sub-decision 5). On the success branch, every `AssignmentUnit.doctorId` in the winning candidate is non-null by upstream contract guarantee in first release.
- Spreadsheet reference normalization (URL or bare ID) lives in the sheet-generation config helper (`docs/sheet_generation_contract.md` §3A and §12.5). Writeback inherits the same rule for any spreadsheet identifier it consumes.
- The writeback boundary is named at `docs/domain_model.md` §14: writeback formatting/mapping is an adapter concern; the core allocation remains `doctorId`-based.

## 5) Purpose
Repo-settled intent + checkpoint narrowing:
- Render a `FinalResultEnvelope` into the operator-facing Google Sheets shell that M1 generated, on both the success branch (`AllocationResult`) and the failure branch (`UnsatisfiedResultEnvelope`).
- Preserve the operator's source tab as an invariant under writeback action — every writeback emits a new tab in the source spreadsheet rather than mutating the source tab — so an operator never loses data they typed mid-flow.
- Make run-envelope traceability persistent in the sheet artifact so any writeback tab found out of context is unambiguously attributable to a specific `runId` and source-tab identity.
- Keep writeback adapter concerns (sheet-side rendering, tab management, operator-facing diagnostic surface) on the sheet-facing stack while preserving the compute pipeline's pure-function discipline upstream.

## 6) Boundary position
Repo-settled:
- Upstream: selector emits a `FinalResultEnvelope` per `docs/selector_contract.md` §10 (success branch is `AllocationResult`; failure branch is `UnsatisfiedResultEnvelope`). The run envelope inside `FinalResultEnvelope.runEnvelope` carries the run identity and traceability fields the writeback tab embeds (§16, §18).
- Boundary: writeback consumes a `FinalResultEnvelope` plus a snapshot bundle (column-A doctor names, request cells, call-point cells, prefilled fixed-assignment cells, shell parameters) plus a `doctorIdMap` from `doctorId` to `(sectionGroup, rowIndex)` per source-tab structure, and produces a new tab in the source spreadsheet identified by `runEnvelope.sourceSpreadsheetId` (§18).
- Downstream: the operator views the new writeback tab in their spreadsheet, and the launcher returns a link anchored to the new tab. There is no further pipeline stage.

Proposed in this checkpoint (normative):

### 6.1 Stack ownership
Writeback is sheet-facing per the D-0017 / D-0018 stack split. Writeback runs on the Apps Script platform alongside the M1 sheet-generation surface, consuming a serialized JSON envelope (§9) produced by the local-first Python compute pipeline upstream. Apps Script is the sole writer to the operator-facing spreadsheet; the Python core does not hold Sheets credentials and does not write to operator-owned spreadsheets directly. This preserves the OAuth-scope discipline established in M1.1 (`docs/decision_log.md` D-0023) and keeps a clean credential-isolation boundary in place for any future cloud-orchestrated Python compute mode (forward-compatibility note, not a committed direction).

### 6.2 Pure-function adapter discipline
Writeback is a pure adapter from `(finalResultEnvelope, snapshot, doctorIdMap)` to a new tab in the source spreadsheet. It does not mutate the source tab (§11), does not read state outside its declared inputs and the live spreadsheet target it is asked to write to, and does not consult the rule engine, scorer, solver, or selector interfaces. Apps Script execution context (operator OAuth session, spreadsheet handle) is the only external surface writeback touches, with a single carve-out for the writeback-execution wall clock consulted solely for the `_RM<YYMMDDHHMMSS>` tab-name uniqueness suffix per §11.1; see §9 normative properties for the precise statement.

### 6.3 Transport mechanics deferred to implementation slice
The concrete transport that delivers the JSON envelope to the writeback launcher (operator paste, file upload, Drive Picker, or alternative) is an implementation-slice concern and is **not** pinned by this contract. The contract requires only that the JSON envelope arrives in the Apps Script execution context with the categories of content named in §9; the launcher's input form and the wire-level representation of that JSON are execution-layer outputs. This mirrors the way `docs/selector_contract.md` §14.3 leaves sidecar file paths to the execution layer.

The transport decision is jointly scoped with the structurally-symmetric inbound side per `docs/decision_log.md` D-0036 (snapshot-extraction Apps Script implementation pinned to a late-M2 checkpoint before M3 activation). When the transport is settled, both inbound (snapshot ingestion) and outbound (writeback envelope delivery) directions adopt the same transport mechanic to avoid two divergent transports across the same Apps Script ↔ Python boundary.

## 7) What this contract governs
This contract governs:
- the shape of writeback input (the `FinalResultEnvelope`, the snapshot bundle, and the `doctorIdMap`),
- the shape of writeback output (a new tab in the source spreadsheet for both success and failure branches),
- the always-new-tab branch-on-write semantics and tab-name discipline (§11),
- doctor identity resolution from `doctorId` to displayed cell value via the snapshot's column-A bundle (§12),
- failure-branch tab content for `UnsatisfiedResultEnvelope` input (§13),
- atomicity discipline for partial-write failure (§14),
- idempotency behavior on repeated envelope upload (§15),
- run-envelope traceability into the sheet via visible footer rows and hidden developer metadata (§16),
- the writeback-stage diagnostic surface the operator-facing launcher MUST expose (§17),
- source-sheet identity propagation via required `runEnvelope` fields per `docs/selector_contract.md` v2 §9 item 3 (§18; `docs/decision_log.md` D-0032),
- determinism guarantees (§19),
- schema versioning rules for the writeback artifact (§20).

## 8) What this contract does not govern
This contract does **not** govern:
- sheet generation, structural surface layout, or any aspect of the M1-generated shell other than reading its operator-edited content via the snapshot bundle (see `docs/sheet_generation_contract.md`),
- pipeline compute stages — rule engine, scorer, solver, selector are all settled (`docs/rule_engine_contract.md`, `docs/scorer_contract.md`, `docs/solver_contract.md`, `docs/selector_contract.md`),
- authentication, OAuth consent screen management, access control, or operator allowlisting (M1.1 launcher territory; `docs/sheet_generation_contract.md` §12.3, `docs/decision_log.md` D-0022, D-0023),
- spreadsheet creation, sharing, or file-level operations on new spreadsheets (sheet-generation territory; `docs/decision_log.md` D-0023),
- the concrete wire format / transport / launcher form by which the JSON envelope arrives in the Apps Script execution context (implementation-slice concern; see §6.3),
- the concrete shape of the JSON envelope's serialization (key ordering, whitespace, Unicode normalization, file extension, MIME type) — the contract names the categories of content the JSON MUST carry but does not pin schema layout, mirroring `docs/selector_contract.md` §14.3,
- selector-stage sidecar artifacts (`candidates_full.json`, `candidates_summary.csv`) — these are selector-stage audit outputs (`docs/selector_contract.md` §14) and are NOT consumed by writeback; the writeback envelope MUST NOT carry FULL-retention sidecars or per-candidate scores beyond the winner,
- writeback to formats other than Google Sheets (CSV export, PDF export, etc.); first release is Google-Sheets-only by inheritance of the operator-facing platform commitment (`docs/decision_log.md` D-0004, D-0017),
- cross-spreadsheet or cross-tab destination override (deferred; see §22 and FW-0022),
- in-situ writeback to the source tab when no operator edits are detected (deferred; see §22 and FW-0023),
- partial-allocation rendering for unfilled `AssignmentUnit` entries — first-release upstream contract guarantees no null `doctorId` on the success branch (`docs/solver_contract.md` §10.2, §14; D-0026 sub-decision 5); see §22 and FW-0021,
- richer failure-tab presentation (banners, categorized diagnostic blocks, snapshot reconstruction in the failure tab, `searchDiagnostics` aggregation tables) beyond the first-release minimum content in §13; see §22 and FW-0019,
- duplicate-tab cleanup or detect-and-skip on repeated envelope upload (deferred per §15; see FW-0020),
- observability transport, log format, or run lifecycle management beyond the launcher-facing diagnostic surface in §17.

## 9) Input shape
Writeback invocations consume the following inputs:

1. **`finalResultEnvelope`** — a `FinalResultEnvelope` per `docs/selector_contract.md` §10. The selector's run envelope (`finalResultEnvelope.runEnvelope`) MUST carry the source-sheet identity fields required per `docs/selector_contract.md` v2 §9 item 3 (see §18): `sourceSpreadsheetId` and `sourceTabName`. The `result` field is either an `AllocationResult` (success branch) or an `UnsatisfiedResultEnvelope` (failure branch); writeback handles both per §10, §11, and §13.
2. **`snapshot`** — a literal cell-data snapshot of the source tab at run-start, taken at the parser/normalizer boundary upstream. The snapshot MUST carry the categories of content the writeback tab needs to reconstruct the structural surfaces of an M1-generated shell:
   - `columnADoctorNames` — per-section column-A doctor-name cell values (operator-edited per `docs/sheet_generation_contract.md` §6),
   - `requestCells` — operator-supplied request-entry cell values,
   - `callPointCells` — call-point cell values (operator-overridable from M1 generation defaults per `docs/sheet_generation_contract.md` §8),
   - `prefilledFixedAssignmentCells` — operator-prefilled lower-shell cells admitted as `FixedAssignment` (`docs/sheet_generation_contract.md` §6; `docs/domain_model.md` §10.1),
   - `shellParameters` — `department`, `periodStartDate`, `periodEndDate`, and `doctorCountByGroup` per `docs/sheet_generation_contract.md` §3.
3. **`doctorIdMap`** — a mapping from `doctorId` to `(sectionGroup, rowIndex)` per the source tab's structural layout, built at the parser/normalizer boundary from the source tab's column-A cells. Writeback consumes this map to resolve `AssignmentUnit.doctorId` to the column-A cell value the operator typed, per §12.

Normative properties:
- The three inputs MUST arrive together as a single JSON envelope handed off to the Apps Script execution context. The contract pins the categories of content the envelope MUST carry and pins the input identities the contract relies on (§9 items 1–3, §16, §18) but does not pin the JSON's concrete schema layout (key ordering, nesting, naming conventions); see §6.3 and §8.
- The envelope MUST NOT carry FULL-retention selector sidecar artifacts (`candidates_full.json`, `candidates_summary.csv`) or per-candidate scores beyond the winner. Those are selector-stage audit outputs (`docs/selector_contract.md` §14) and are not consumed by writeback. Operators do not upload them.
- The `finalResultEnvelope` carries `searchDiagnostics` per `docs/selector_contract.md` §10.1 (success branch) and §10.2 (failure branch); the upstream selector contract requires `searchDiagnostics` on every envelope, so a conforming `FinalResultEnvelope` always includes it. Writeback MUST NOT **consume** `searchDiagnostics` content for tab rendering beyond the minimum failure-branch fields named in §13 (`unfilledDemand` and `reasons`, which the failure-branch envelope already exposes alongside `searchDiagnostics`). Aggregated funnel counts, rejection histograms, per-batch summaries, and any other content within `searchDiagnostics` are selector-stage retention surfaces (`docs/selector_contract.md` §14, §17) that ride on the envelope by upstream contract guarantee but are ignored by writeback rendering. Writeback similarly does not consume `winnerScore` component breakdowns or `selectorStrategyId` for tab rendering — these fields ride on the envelope per `docs/selector_contract.md` §10 but are not writeback-tab content.
- Writeback MUST NOT read any state outside the declared inputs and the live spreadsheet target it is asked to write to, with one narrow exception: the writeback-execution wall clock MAY be consulted SOLELY for the `_RM<YYMMDDHHMMSS>` tab-name suffix per §11.1, whose sole purpose is tab-name uniqueness across repeated invocations under §15.1 and which does not affect tab content. Otherwise: no environment variables, no clocks for traceability or content (the run envelope's `generationTimestamp` is execution-layer-supplied per `docs/selector_contract.md` §16; writeback MUST NOT synthesize timestamps for visible-footer or hidden-metadata traceability content), no filesystem reads beyond the JSON envelope handoff itself. See §19 for the matching determinism statement.
- Writeback MUST NOT mutate the source tab (`runEnvelope.sourceTabName`); see §11.

## 10) Output shape
Writeback produces a single new tab in the source spreadsheet (`runEnvelope.sourceSpreadsheetId`). The new tab's content depends on the input branch.

### 10.1 Success-branch tab — `AllocationResult` input
The success-branch writeback tab carries:
- a reconstructed M1-style structural shell sourced from the snapshot bundle's `shellParameters` and `columnADoctorNames` so the writeback tab is operator-readable as a roster shell on its own,
- `requestCells`, `callPointCells`, and `prefilledFixedAssignmentCells` from the snapshot bundle, written into their corresponding cell positions,
- the winner allocation: every `AssignmentUnit` from `finalResultEnvelope.result.winnerAssignment` rendered into its assignment cell with the column-A cell value of the resolved doctor (§12),
- the run-envelope traceability footer (§16.1) at the bottom of the tab,
- the run-envelope traceability hidden developer metadata (§16.2) attached to the tab.

### 10.2 Failure-branch tab — `UnsatisfiedResultEnvelope` input
The failure-branch writeback tab carries:
- a "FAILED" indicator at the top of the tab (single header row),
- `unfilledDemand` rendered as plain-text rows,
- `reasons` rendered as plain-text rows,
- the run-envelope traceability footer (§16.1) at the bottom of the tab, with `Status: FAILED`,
- the run-envelope traceability hidden developer metadata (§16.2) attached to the tab, with `status: "FAILED"`.

The failure-branch tab MUST NOT carry a reconstructed structural shell, snapshot reconstruction, or rich formatting in first release; see §13.

### 10.3 Tab protection
Both branches MUST mark the writeback tab as read-only from the operator's perspective. The whole tab is protected; the operator views the writeback tab but does not edit it. This applies uniformly across success and failure branches.

### 10.4 Branch discipline
A single writeback invocation MUST produce exactly one new tab per `FinalResultEnvelope` input, regardless of branch. Mixed-mode outputs (success-branch content on a failure-branch input, partial winner content alongside failure diagnostics, etc.) are contract-breaking defects.

## 11) Branch-on-write behavior — always-new-tab
Proposed in this checkpoint (normative):

Every writeback invocation MUST create a new tab in the source spreadsheet. The source tab named by `runEnvelope.sourceTabName` (§18) MUST NOT be mutated by writeback under any circumstance, including the case where the tab's assignment region is empty at writeback time. A writeback implementation that writes back to the source tab in any branch is contract-broken.

### 11.1 Tab name
The new tab MUST be named `<source-tab-prefix>_RM<YYMMDDHHMMSS>` where:
- `<source-tab-prefix>` is the value of `runEnvelope.sourceTabName`, deterministically truncated as specified below to fit within the spreadsheet platform's tab-name length limit,
- `<YYMMDDHHMMSS>` is the second-resolution writeback-execution wall-clock timestamp formatted as a fixed locale-independent ASCII positional string with the layout `YY` (two-digit year, 00–99) + `MM` (two-digit month, 01–12) + `DD` (two-digit day-of-month, 01–31) + `HH` (two-digit 24-hour, 00–23) + `MM` (two-digit minute, 00–59) + `SS` (two-digit second, 00–59), zero-padded with no separators (for example, `260426145025`). The timestamp MUST be evaluated in UTC so the result is stable across operator locales and Apps Script runtime time-zone settings; locale-dependent rendering of the timestamp into tab names is contract-prohibited.

#### 11.1.1 Length-limit truncation
The full tab name (including `<source-tab-prefix>`, the `_RM<YYMMDDHHMMSS>` suffix, and any collision-uniqueness suffix per §11.1.2) MUST fit within Google Sheets' tab-name length limit (currently 100 characters). When the concatenation would exceed the limit, the implementation MUST deterministically truncate `<source-tab-prefix>` from the right (preserving the leading characters of `runEnvelope.sourceTabName`) until the full name fits. Truncation is a property of the visible tab name only; the hidden developer metadata key `sourceTabName` (§16.2) MUST carry the full untruncated source tab name regardless of any visible-name truncation, so traceability to the source tab is preserved end-to-end through the metadata surface even when the visible tab name is shortened. Implementations MUST NOT truncate the `_RM<YYMMDDHHMMSS>` suffix or the collision-uniqueness suffix; only the source-tab prefix is truncatable.

#### 11.1.2 Collision uniqueness
The second-resolution timestamp is sufficient to make tab-name collisions vanishingly rare in practice. Implementations MUST guarantee tab-name uniqueness within the spreadsheet by auto-suffixing `_2`, `_3`, … on the rare same-second collision (after the `_RM<YYMMDDHHMMSS>` suffix). The contract requires uniqueness; the auto-suffix scheme is the recommended mechanism but is not the only conformant option — any deterministic uniqueness mechanism that preserves the `_RM<YYMMDDHHMMSS>` suffix and respects the §11.1.1 length-limit truncation is acceptable.

### 11.2 Safety property
The source tab is invariant under writeback action. Whatever the operator typed on the source tab at any time — before the run, during the run, or between the run and writeback — stays exactly as the operator left it. The writeback tab faithfully reflects what the pipeline saw at run-start (the snapshot bundle), and the source tab faithfully reflects what the operator currently has. The two representations coexist on different tabs; the operator can compare side-by-side.

### 11.3 Conflict-handling collapse
Because the source tab is never mutated, the broader conflict-handling problem (operator edits between run-start and writeback) does not arise at the writeback boundary. Writeback never blocks on detected operator edits and never refuses based on conflict; there is no detect-and-refuse, detect-and-warn, or blind-overwrite mode to surface. The conflict-handling collapse is about CONFLICT semantics specifically; runtime-error semantics are governed separately by §14 (atomicity discipline; partial tab state on mid-write failure is cleaned up, surfaced as runtime error per §17.3) and remain the proper failure mode for any mid-write exception. Operator-edited column-A names, request cells, call-point cells, or fixed-assignment prefills made between run-start and writeback do not propagate to the writeback tab — the writeback tab reflects run-start state per the snapshot bundle. This is an accepted consequence; both representations remain visible to the operator on different tabs.

### 11.4 Spreadsheet bloat
Repeated writebacks on the same spreadsheet accumulate writeback tabs. Writeback does not implement bloat mitigation in first release (no auto-archive, no tab-grouping, no cleanup-on-N-tabs); the operator manages cleanup of accumulated writeback tabs by deleting tabs themselves. See §22 and FW-0023 for an in-situ optimization that would reduce bloat in the no-conflict case; see FW-0020 for an idempotency-via-runId-skip mechanism that would reduce bloat from accidental re-uploads. Both are deferred for first release.

## 12) Doctor identity resolution
Proposed in this checkpoint (normative):

Writeback resolves `AssignmentUnit.doctorId` to the displayed cell value via the snapshot bundle's column-A cell values, mediated by the `doctorIdMap`:

1. For each `AssignmentUnit` in the winning candidate (success branch only), the writeback implementation MUST look up `doctorId` in `doctorIdMap` to obtain the `(sectionGroup, rowIndex)` of the doctor's column-A cell on the source tab.
2. The implementation MUST then read the column-A cell value at `(sectionGroup, rowIndex)` from the snapshot bundle's `columnADoctorNames` and write that string into the assignment cell of the writeback tab.

### 12.1 Single source of truth
The column-A cell value the operator typed at run-start is the single source of truth for the displayed doctor name. Writeback does not consult any other doctor-name source — not the parser/normalizer's canonical doctor table, not a sidecar metadata block on the run envelope, not the live source-tab column A at writeback time. This preserves the operator's mental model that column A is the canonical doctor-name surface and avoids any hidden disagreement between parser-stage and writeback-stage doctor displays.

### 12.2 Mid-flow column-A edits do not propagate
Because the writeback tab is reconstructed from the snapshot bundle, operator edits to source-tab column A made between run-start and writeback do not propagate to the writeback tab. The writeback tab faithfully reflects the run-start column-A content. The source tab remains as the operator currently has it. Both representations coexist on different tabs (§11.2).

### 12.3 Null `doctorId` not in scope
First-release upstream contracts (`docs/solver_contract.md` §10, §14; `docs/decision_log.md` D-0026 sub-decision 5) guarantee that every `AssignmentUnit` in a success-branch `winnerAssignment` has non-null `doctorId`. Writeback MUST NOT receive a null-`doctorId` `AssignmentUnit` on the success branch in first release. Cell representation for null `doctorId` is deferred; see §22 and FW-0021.

## 13) Failure-branch behavior
Proposed in this checkpoint (normative):

When `finalResultEnvelope.result` is an `UnsatisfiedResultEnvelope` per `docs/selector_contract.md` §10.2, writeback follows the always-new-tab pattern (§11) and emits a failure-branch tab with deliberately minimum content.

### 13.1 Minimum content
The first-release failure-branch tab MUST carry, at minimum:
- a "FAILED" indicator at the top (single header row),
- `unfilledDemand` entries from the input envelope, rendered as plain-text rows,
- `reasons` entries from the input envelope, rendered as plain-text rows,
- the run-envelope traceability footer (§16.1) at the bottom, with `Status: FAILED`,
- the run-envelope traceability hidden developer metadata (§16.2), with `status: "FAILED"`.

### 13.2 Explicitly out of first-release scope
The following are explicitly NOT in the first-release failure-branch tab:
- a reconstructed M1-style structural shell or snapshot reconstruction (the operator can refer to the source tab; the failure tab does not duplicate that surface),
- rich formatting (banners, colored cells, categorized diagnostic blocks, structured tables),
- `searchDiagnostics` aggregation tables (rejection-reason histograms, per-batch summaries, candidate-funnel counts) — these are selector-stage retention surfaces, not writeback-input content (`docs/selector_contract.md` §14, §17).

### 13.3 Rationale
First-release failure-branch content is intentionally simple and crude. The operator-facing job at this stage is to convey "the run failed; here is the unfilled demand and the structured reasons" without expanding into a richer diagnostic surface. Richer presentation is a deferred surface tied to pilot-operator feedback (FW-0019); building it before that feedback exists would over-fit the failure tab to assumed needs.

### 13.4 Tab protection
The failure tab MUST be marked read-only on the same protection discipline as the success tab (§10.3).

## 14) Atomicity discipline
Proposed in this checkpoint (normative):

Writeback MUST surface to the operator either a fully-populated writeback tab (containing the complete winner allocation per §10.1, or the complete failure-branch content per §13.1) OR no new tab at all. Implementations MUST clean up any partial tab state on mid-write failure.

### 14.1 Cleanup-on-failure
On any exception or write-stage error during tab population, the writeback implementation MUST attempt to delete the partial writeback tab so the operator does not see a half-written artifact.

### 14.2 Cleanup-failure surface
If the cleanup attempt itself fails (for example, a secondary Apps Script exception during sheet deletion), the writeback diagnostic surface (§17) MUST name the orphaned tab so the operator can manually delete it. A cleanup failure is not a writeback success: the runtime-error state per §17 applies, and the orphan-tab name is part of the surfaced error content.

### 14.3 Out of contract scope
The concrete implementation pattern (Apps Script `Range.setValues` batch write + `try { populate } catch (e) { spreadsheet.deleteSheet(newTab); throw e; }` or equivalent) is an implementation-slice concern. The contract names the operator-facing semantics ("fully populated tab OR no tab; orphan-tab name surfaced on cleanup failure") rather than the code path.

## 15) Idempotency
Proposed in this checkpoint (normative):

Writeback MUST treat each envelope upload as a fresh invocation that creates a new tab unconditionally. There is no detect-and-skip path on repeated upload of the same `runId`.

### 15.1 New tab per upload
Every successful envelope upload produces a new tab with a freshly-computed `_RM<YYMMDDHHMMSS>` timestamp suffix (§11.1). Repeated uploads of the same envelope produce multiple writeback tabs with distinct timestamp suffixes (or, on the rare same-second collision, distinct auto-suffix `_2` / `_3` / … per §11.1).

### 15.2 Operator agency
Writeback respects operator agency: an operator who re-uploads a finalized envelope a second or third time gets a second or third writeback tab without protest. The contract trusts the operator to manage their own spreadsheet; bloat from re-uploads is a self-imposed consequence the operator can clean up by deleting tabs (§11.4).

### 15.3 Content-equivalent rather than tab-list-identical
Repeated writebacks of the same envelope produce **content-equivalent** writeback tabs — same allocation values land in equivalent cells of equivalent tabs — rather than tab-list-identical results. The brief's idempotency intent (no silent duplicate-allocation effects, no off-by-one cell drift on re-run) is preserved at the content level: every writeback tab from the same `runId` shows the same winner allocation, the same column-A doctor names, the same request/call-point/prefilled cells, and the same run-envelope traceability footer. The set of tabs in the spreadsheet differs across re-runs (one extra tab per re-run), but the content of any single writeback tab from the same `runId` is content-equivalent across re-runs within the determinism scope of §19.

### 15.4 Idempotency-via-runId-skip is deferred
A future detect-and-skip mode that scans the target spreadsheet's hidden developer metadata (§16.2) for a matching `runId` and short-circuits to "already written, skipping" diagnostic + link to the existing tab is captured in FW-0020. This is deferred from first release because operator agency takes precedence over duplicate-tab clutter at pilot scope.

## 16) Run-envelope traceability into the sheet
Proposed in this checkpoint (normative):

Every writeback tab (success or failure) MUST carry run-envelope traceability content in two complementary surfaces: a visible footer for operator-direct audit, and hidden developer metadata for programmatic consumption.

### 16.1 Visible footer rows
At the very bottom of the writeback tab, after any structural shell content (§10.1) or failure-branch content (§13.1), the writeback implementation MUST append four traceability rows in the following exact order:

| Row | Content |
|-----|---------|
| 1 | `Run ID: <finalResultEnvelope.runEnvelope.runId>` |
| 2 | `Generated: <finalResultEnvelope.runEnvelope.generationTimestamp formatted human-readably>` |
| 3 | `Source: <finalResultEnvelope.runEnvelope.sourceTabName>` |
| 4 | `Status: SUCCESS` (success branch) or `Status: FAILED` (failure branch) |

`generationTimestamp` is execution-layer-supplied per `docs/selector_contract.md` §16; its rendering format (for example, `2026-04-26 14:30:25 SGT`) is implementation-slice. The visible footer rows are operator-readable text, not structural cells; they MUST NOT be confused with assignment cells or with the M1-shell legend block.

### 16.2 Hidden developer metadata
The writeback implementation MUST attach the following six developer metadata keys to the writeback tab via Apps Script `Sheet.addDeveloperMetadata(key, value)` (or platform-equivalent):

| Key | Type | Source |
|-----|------|--------|
| `runId` | string | `finalResultEnvelope.runEnvelope.runId` |
| `generationTimestamp` | ISO 8601 string | `finalResultEnvelope.runEnvelope.generationTimestamp` |
| `sourceTabName` | string | `finalResultEnvelope.runEnvelope.sourceTabName` |
| `sourceSpreadsheetId` | string | `finalResultEnvelope.runEnvelope.sourceSpreadsheetId` |
| `contractVersion` | string | `"1"` — string representation of this contract's `contractVersion: 1` per §2. Apps Script `Sheet.addDeveloperMetadata(key, value)` stores values as strings; future bumps store the next integer's string form (`"2"`, `"3"`, …). |
| `status` | enum | `"SUCCESS"` (success branch) or `"FAILED"` (failure branch) |

### 16.3 Explicitly NOT included
The following are explicitly not part of first-release traceability content:
- per-cell metadata or per-cell notes (overkill for the operator-facing audit need),
- score breakdown / `searchDiagnostics` content / per-candidate scores — these are selector-stage audit artifacts (`docs/selector_contract.md` §14, §17), not writeback-traceability content,
- run-envelope fields beyond the six keys above (`seed`, `fillOrderPolicy`, `crFloorMode`, `crFloorComputed`, `selectorStrategyId`) — these are not needed for sheet-side audit; they are available in the JSON envelope if a downstream tool needs them.

### 16.4 Additivity
Future expansion of hidden developer metadata keys is additive and does not require a `contractVersion` bump per §2, provided the six first-release keys above remain present and v1-targeted readers can ignore additional keys. Removing or renaming an existing first-release key, or changing its value semantics, does require a bump.

## 17) Writeback-stage diagnostic surface
Proposed in this checkpoint (normative):

The writeback launcher MUST surface a three-state operator-facing diagnostic on every invocation. Visual styling, button placement, and exact wording are implementation-slice concerns; the contract pins the minimum content.

### 17.1 Success state
On success (`AllocationResult` input, fully-populated success-branch tab, no runtime error), the launcher MUST surface:
- a confirmation message,
- the new writeback tab name,
- a link to the spreadsheet (anchored to the new tab where the platform supports tab anchoring).

### 17.2 Failure state
On `UnsatisfiedResultEnvelope` input (fully-populated failure-branch tab, no runtime error), the launcher MUST surface:
- a brief failure indicator,
- the new failure-branch tab name,
- a link to the spreadsheet (anchored to the failure tab where the platform supports tab anchoring).

The launcher MUST NOT duplicate the failure-branch tab's `unfilledDemand` and `reasons` content into the launcher diagnostic itself; the detailed content lives on the failure tab per §13. Duplicating it into the launcher would create two truth surfaces for the same diagnostic.

### 17.3 Runtime-error state
On runtime error — any exception raised during writeback, whether before tab creation (input-validation defects, contract-input shape failures, missing-required-field detections at the writeback ingestion boundary), during tab population (mid-write Apps Script API failures), or during cleanup-on-failure (secondary errors per §14.2) — the launcher MUST surface:
- the human-readable error message,
- if cleanup-on-failure left an orphaned tab per §14.2, the orphan-tab name so the operator can manually delete it.

Pre-write input-validation defects (for example, a `FinalResultEnvelope` that arrives at writeback ingestion without selector-contract-v2 required-`runEnvelope` fields per §9 item 1 and `docs/selector_contract.md` §9 item 3) MUST surface through this state without creating any tab. Post-creation runtime errors MUST attempt cleanup-on-failure per §14 and surface through this state with the orphan-tab name when cleanup itself fails. Defensive writeback-side validation of the required-fields set is a backstop against catastrophic execution-layer-composition defects; the primary enforcement of those required fields is upstream at the selector boundary per `docs/selector_contract.md` §9 item 3.

### 17.4 No partial-state launcher commit
Writeback MUST NOT leave the operator in a state where the launcher diagnostic implies success but the spreadsheet contains a partial or absent tab, or where the spreadsheet contains a fully-populated tab but the launcher diagnostic implies failure. The launcher diagnostic and the spreadsheet state are surfaces of one writeback outcome and MUST agree.

## 18) Source-sheet identity propagation
Proposed in this checkpoint (normative):

Writeback consumes `runEnvelope.sourceSpreadsheetId` and `runEnvelope.sourceTabName` as required `runEnvelope` fields per `docs/selector_contract.md` §9 item 3 (selector `contractVersion: 2`; see `docs/decision_log.md` D-0032 for the selector v1 → v2 bump). The fields are execution-layer-supplied at parser/normalizer ingestion time (when the source tab and spreadsheet are known) and flow through the pipeline alongside `runId`, `generationTimestamp`, and other run-level metadata.

### 18.1 Field semantics
- `sourceSpreadsheetId` — a Google Sheets spreadsheet identifier, normalized per `docs/sheet_generation_contract.md` §12.5 (bare ID extracted from URL or accepted as-is when supplied as a bare ID). Writeback uses this field to identify the target spreadsheet to create the writeback tab inside.
- `sourceTabName` — a string naming the source tab the snapshot was taken from. Writeback uses this field as the basis for the new writeback tab name (§11.1).

### 18.2 Required runEnvelope fields per selector contract v2
Both fields are required at the selector boundary per `docs/selector_contract.md` §9 item 3 under `contractVersion: 2`. Selector enforces the required-fields check on input alongside `runId`, `snapshotRef`, `configRef`, `seed`, `fillOrderPolicy`, `crFloorMode`, `crFloorComputed`, and `generationTimestamp`; absence at selector entry is a contract-breaking defect on the caller side (`docs/selector_contract.md` §9). The selector forwards the run envelope unchanged from its inputs to the `FinalResultEnvelope` per `docs/selector_contract.md` §16.4, so by the time the envelope reaches writeback the fields are guaranteed present by selector compliance — there is no separate execution-layer composition gate the writeback contract needs to enforce, and no contract-seam ambiguity between selector compliance and writeback compatibility on this surface.

The fields were initially proposed as additive run-envelope fields per `docs/selector_contract.md` §16.3 (no selector contract bump) during the writeback contract's first-draft round; PR #66 codex review surfaced the resulting contract-seam gap (selector compliance without these fields would not imply writeback compatibility) as a P1 consistency flag, and the resolution adopted in this PR is the upstream patch — selector contract v1 → v2 with the fields added to §9 item 3 — recorded in `docs/decision_log.md` D-0032. Writeback-side defensive validation of these fields at the writeback ingestion boundary remains a backstop for catastrophic execution-layer-composition defects (the launcher surfaces such input-validation failures through the runtime-error state per §17.3); the primary enforcement is upstream at the selector boundary.

### 18.3 Destination is source-only in first release
Writeback always targets the source spreadsheet and source tab named on the run envelope. The operator MAY manually copy or move the resulting tab afterwards if they want a different destination, but the writeback boundary itself does not accept an override. Cross-spreadsheet or cross-tab destination override is deferred; see §22 and FW-0022.

### 18.4 Launcher UX implication
Because the launcher consumes the source spreadsheet identity from the run envelope rather than from a separate operator-supplied form field, the writeback launcher form does not require a `spreadsheetId` input. The launcher MAY surface a confirmation preview ("About to writeback to: `<sourceSpreadsheetName>` / `<sourceTabName>` — confirm?") sourced from the envelope before initiating the writeback; the preview content and confirmation interaction are implementation-slice concerns. The result page anchors its spreadsheet link to the new writeback tab (§17).

## 19) Determinism
Proposed in this checkpoint (normative):
- Given identical `(finalResultEnvelope, snapshot, doctorIdMap)` inputs, writeback MUST produce content-equivalent writeback tabs across repeated invocations within a single implementation on a single platform. Content-equivalent means the same allocation values land in equivalent cells, the same column-A doctor names appear, the same request/call-point/prefilled cells appear, and the same run-envelope traceability footer (§16.1) and hidden developer metadata (§16.2) are present.
- Writeback MUST NOT promise byte-identical Google Sheets state across invocations. The Google Sheets platform carries implicit metadata (edit timestamps, last-modified-by, revision history) that is not under writeback's control. Writeback also MUST NOT promise tab-list identity across re-runs; per §15.3, repeated invocations create distinct new tabs with distinct `_RM<YYMMDDHHMMSS>` timestamps.
- Writeback MUST NOT consume clocks, environment variables, or filesystem state beyond the JSON envelope it is asked to render and the live spreadsheet target it is asked to write to. The `_RM<YYMMDDHHMMSS>` tab-name timestamp and the visible-footer `Generated:` line are the only timestamp content writeback emits, and both derive from execution-layer-supplied values (`generationTimestamp` for the footer; the writeback-execution wall clock for the tab-name suffix, which is the only deliberate non-deterministic input the contract permits — its sole purpose is tab-name uniqueness across repeated invocations under §15.1, and it does not affect tab content).
- Cross-implementation or cross-platform determinism is not required and is not guaranteed; Apps Script runtime versions, spreadsheet locale formatting, and hidden-metadata library implementations differ across deployments (see `docs/future_work.md` FW-0011 for the cross-implementation determinism direction).

A writeback implementation that produces non-content-equivalent outputs under identical inputs on a single platform is contract-broken regardless of any other observed property.

## 20) Schema versioning
Proposed in this checkpoint (normative):

The writeback tab artifact (visible footer row layout per §16.1, hidden developer metadata key set per §16.2, branch-on-write tab-name discipline per §11.1) carries `contractVersion: 1` per §2.

### 20.1 Bump rule
Bump `contractVersion`:
- when the visible footer row count, ordering, or content semantics change in a way a v1-targeted reader would notice (for example, removing the `Status:` row, or reordering the four rows),
- when a first-release hidden developer metadata key (§16.2) is removed, renamed, or changes value semantics,
- when the `_RM<YYMMDDHHMMSS>` tab-name discipline changes in a way a v1-targeted reader would notice (for example, changing the prefix or the timestamp resolution),
- when input shape (§9), branch-on-write semantics (§11), atomicity discipline (§14), idempotency behavior (§15), or determinism guarantees (§19) change.

Do **not** bump:
- for wording cleanup, formatting, or added examples,
- for additive run-envelope fields per `docs/selector_contract.md` §16.3 that v1-targeted writeback readers can tolerate,
- for additive hidden developer metadata keys (per §16.4) that v1-targeted readers can ignore,
- for clarification that does not change behavior.

### 20.2 Writeback tab is not a sidecar artifact
Unlike the selector's `candidates_summary.csv` and `candidates_full.json` (`docs/selector_contract.md` §14, §19), the writeback artifact lives in the operator's spreadsheet rather than on disk. There is no separate `schemaVersion` field independent of `contractVersion`; the hidden developer metadata key `contractVersion` (§16.2) IS the schema-version surface for the writeback artifact.

## 21) Consistency with adjacent contracts
Repo-settled alignments:
- Consistent with `docs/decision_log.md` D-0017 / D-0018: Apps Script is the writeback stack; compute-heavy core stays local-first Python upstream of the JSON handoff (§6.1).
- Consistent with `docs/decision_log.md` D-0023: writeback inherits the auto-share / OAuth-scope discipline established for M1.1; no new credential surface is introduced (§4, §6).
- Consistent with `docs/decision_log.md` D-0027: writeback consumes the selector's `FinalResultEnvelope` as the canonical pipeline output and does not reach back into rule-engine, scorer, solver, or selector interfaces.
- Consistent with `docs/selector_contract.md` v2 §10, §16: writeback consumes the selector's success-branch `AllocationResult` and failure-branch `UnsatisfiedResultEnvelope`, propagates the run envelope unchanged into the writeback artifact, and depends on selector v2's expanded `runEnvelope` required-fields list — `sourceSpreadsheetId` and `sourceTabName` were added to `docs/selector_contract.md` §9 item 3 in the same change round per `docs/decision_log.md` D-0032 (selector v1 → v2 bump). Selector compliance therefore implies writeback compatibility on the source-sheet-identity surface; no execution-layer composition gate is required.
- Consistent with `docs/sheet_generation_contract.md` §3A and §12.5: the source-sheet reference normalization rule (URL or bare ID) governs how `runEnvelope.sourceSpreadsheetId` is interpreted at the parser/normalizer ingestion boundary (§18.1); writeback inherits this rule rather than re-implementing it.
- Consistent with `docs/sheet_generation_contract.md` §6: operator-allowed edits after generation (column A doctor names, request cells, call-point cells, lower-shell prefilled cells) are exactly the categories of content the writeback snapshot bundle (§9) carries forward into the writeback tab.
- Consistent with `docs/sheet_generation_contract.md` §9: the writeback tab inherits the protection posture (whole-tab read-only, §10.3) consistent with the protection discipline established for M1-generated structural surfaces.
- Consistent with `docs/domain_model.md` §7.3: doctor identity resolution treats `doctorId` as runtime identity and column-A cell value as the displayed name (§12); the resolution mechanism is mediated through the `doctorIdMap` rather than through the parser/normalizer doctor table.
- Consistent with `docs/domain_model.md` §10.1, §10.3: `FixedAssignment` entries are first-class normalized input on the upstream side and arrive as `AssignmentUnit` entries within the success-branch `winnerAssignment` per `docs/solver_contract.md` §10.1; writeback renders them on the writeback tab the same as solver-placed `AssignmentUnit` entries.
- Consistent with `docs/domain_model.md` §10.2 and `docs/decision_log.md` D-0029: `unitIndex` is operationally identifying but does not carry implicit difficulty or workload differentiation; writeback rendering of multi-unit demand is deferred (§22, FW-0021).
- Consistent with `docs/domain_model.md` §14: writeback formatting/mapping is an adapter concern, with the core allocation remaining `doctorId`-based; this contract is the normative home for the adapter behavior previously named only at the boundary level.

Proposed in this checkpoint:
- This contract formalizes the writeback adapter's pure-function shape, the always-new-tab branch-on-write semantics, the `doctorIdMap`-mediated doctor identity resolution, the cleanup-on-failure atomicity discipline, the operator-agency idempotency stance, the four-row visible footer + six-key hidden developer metadata traceability surface, the three-state launcher diagnostic minimum content, and the source-sheet identity additivity exercise — while remaining aligned with sheet-generation / selector / domain-model boundaries and with the D-0017 / D-0018 stack split.

## 22) Explicit deferrals
The following are explicitly deferred and not fixed by this document:
- the concrete JSON envelope schema layout (key ordering, nesting, naming conventions, file extension, MIME type) — implementation-slice concern per §6.3 and §8,
- the concrete launcher transport for the JSON envelope (paste, file upload, Drive Picker, alternative) — implementation-slice concern per §6.3,
- richer failure-tab presentation beyond the first-release minimum content in §13 (banners, categorized diagnostic blocks, snapshot reconstruction in the failure tab, `searchDiagnostics` aggregation tables) — see `docs/future_work.md` FW-0019,
- idempotency-via-`runId`-skip detection that scans hidden developer metadata for a matching `runId` and short-circuits to "already written, skipping" — see `docs/future_work.md` FW-0020,
- writeback rendering for partial-allocation strategies (cell representation for null `doctorId` `AssignmentUnit` entries, multi-unit `requiredCount > 1` rendering, partial-fill markers) — see `docs/future_work.md` FW-0021,
- cross-spreadsheet or cross-tab writeback destination override (launcher field that overrides `runEnvelope.sourceSpreadsheetId` / `sourceTabName` for archival, testing, or porting use cases) — see `docs/future_work.md` FW-0022,
- in-situ writeback optimization for the no-conflict case (detect whether the source tab's assignment region is unchanged from the snapshot and write in-situ if so, branching only on detected conflict) — see `docs/future_work.md` FW-0023,
- writeback to formats other than Google Sheets (CSV export, PDF export),
- multi-cycle writeback orchestration (writing back across several roster periods at once),
- cross-implementation and cross-platform determinism for writeback content-equivalence (see `docs/future_work.md` FW-0011),
- concrete function/API signatures, language-specific shapes, and module decomposition within the writeback Apps Script module.

## 23) Current checkpoint status
### Repo-settled in prior docs
- pipeline-stage separation `solver → scorer → selector` and selector ownership of the operator-facing final result (`docs/decision_log.md` D-0027; `docs/selector_contract.md`),
- Apps Script as the sheet-facing surface; local-first Python for the compute-heavy core (`docs/decision_log.md` D-0017, D-0018),
- OAuth-scope discipline and auto-share posture inherited from M1.1 (`docs/decision_log.md` D-0023),
- `FinalResultEnvelope` shape per selector contract v2 (`docs/selector_contract.md` §10; `docs/decision_log.md` D-0030); `runEnvelope` required-fields list expanded to include `sourceSpreadsheetId` and `sourceTabName` in selector v2 (`docs/selector_contract.md` §9 item 3; `docs/decision_log.md` D-0032), with §16.3 retained for *future* optional-additive expansions,
- operator-allowed edits after sheet generation and protection posture for generated surfaces (`docs/sheet_generation_contract.md` §6, §9),
- spreadsheet reference normalization (`docs/sheet_generation_contract.md` §3A, §12.5),
- `Doctor.doctorId` runtime-identity vs `displayName` sheet-facing-identity separation (`docs/domain_model.md` §7.3, §14),
- `unitIndex` operational-equivalence and same-`SlotType`-unit interchangeability for doctor admissibility (`docs/decision_log.md` D-0029; `docs/domain_model.md` §10.2),
- whole-run-failure discipline upstream — no null `doctorId` in success-branch `winnerAssignment` in first release (`docs/solver_contract.md` §10, §14; `docs/decision_log.md` D-0026 sub-decision 5).

### Proposed and adopted in this checkpoint
- pure-adapter public contract with `(finalResultEnvelope, snapshot, doctorIdMap) → new tab in source spreadsheet` shape,
- always-new-tab branch-on-write semantics with source-tab invariance (§11),
- tab-name discipline `<sourceTabName>_RM<YYMMDDHHMMSS>` with auto-suffix for collision uniqueness (§11.1),
- doctor identity resolution via `doctorIdMap` mediation onto snapshot column-A values (§12),
- failure-branch tab with very-simple-and-crude minimum content (§13),
- cleanup-on-failure atomicity with orphan-tab name surfaced on cleanup-failure secondary error (§14),
- operator-agency idempotency: every upload creates a new tab unconditionally (§15),
- four-row visible footer (`Run ID:` / `Generated:` / `Source:` / `Status:`) plus six-key hidden developer metadata (`runId`, `generationTimestamp`, `sourceTabName`, `sourceSpreadsheetId`, `contractVersion`, `status`) (§16),
- three-state launcher diagnostic surface (success / failure / runtime error) with orphan-tab surfacing on cleanup failure (§17),
- source-sheet identity propagation via required `runEnvelope` fields `sourceSpreadsheetId` and `sourceTabName` per `docs/selector_contract.md` v2 §9 item 3 (§18); selector contract bumped from v1 to v2 in the same change round (`docs/decision_log.md` D-0032) — the fields were initially proposed as §16.3 additive but the contract-seam gap surfaced in PR #66 codex review motivated the upstream-patch resolution,
- content-equivalent determinism within a single implementation on a single platform (§19),
- writeback artifact `contractVersion: 1` with explicit additive-vs-breaking bump rule (§20).

### Still open / deferred
- concrete JSON envelope schema layout and launcher transport mechanics,
- concrete function/API signatures and module decomposition within the writeback Apps Script module,
- richer failure-tab presentation (`docs/future_work.md` FW-0019),
- idempotency-via-`runId`-skip detection (`docs/future_work.md` FW-0020),
- writeback rendering for partial-allocation strategies (`docs/future_work.md` FW-0021),
- cross-spreadsheet / cross-tab destination override (`docs/future_work.md` FW-0022),
- in-situ optimization for the no-conflict case (`docs/future_work.md` FW-0023),
- writeback to formats other than Google Sheets,
- multi-cycle writeback orchestration,
- cross-implementation and cross-platform determinism (`docs/future_work.md` FW-0011).

This document is a first-pass working draft checkpoint drafted scope-ahead of M3 activation per D-0031. M2 (`Minimal local compute pipeline`) remains the active milestone; M3 (`Safe result/output and writeback`) remains `Planned` per `docs/delivery_plan.md` §5; this contract becomes the natural M3 C1 once M3 activates. No executable code lands alongside this contract; implementation work for the writeback stage remains deferred until M3 activates.
