# Analysis Renderer Contract (First-Pass Working Draft)

## 1) Contract status and scope
This document defines the analysis-renderer boundary that sits between the analyzer engine's `AnalyzerOutput` (per `docs/analysis_contract.md` §10) and the source spreadsheet's tab surface that the operator inspects.

It is intended to be concrete enough for implementation planning for M5 C2 renderer work.

It explicitly separates:
- repo-settled anchors,
- renderer-boundary decisions adopted in this checkpoint,
- still-open items in this checkpoint,
- and explicit deferrals.

Scope is limited to renderer-stage `AnalyzerOutput → K roster tabs + 1 comparison tab` construction in the source spreadsheet. This is not an analyzer-engine, upload-portal, writeback, or template-generator design document.

The renderer is a **sibling consumer** of the wrapper envelope per `docs/decision_log.md` D-0055 — it shares the central library with `Writeback.gs` per D-0052 and reuses the same `SpreadsheetApp.openById(sourceSpreadsheetId)` opening pattern + the same shared formatting utilities for visual identity.

## 2) Contract identity and versioning
Contract identity/version for binding:
- `contractId: ANALYSIS_RENDERER`
- `contractVersion: 1`

Version bump rule (normative):
- bump `contractVersion` only when renderer input shape, tab-emission shape, target-spreadsheet behavior, naming convention in a way that breaks v1-targeted readers, or determinism guarantees change.
- do **not** bump for wording cleanup, formatting tweaks, additive optional tab-content fields that v1 readers can ignore, or clarification that does not change behavior.

### 2.1 Version history
- **v1 (2026-05-05, this PR):** initial analysis-renderer contract closure per `docs/decision_log.md` D-0060..D-0063. Tab-shape, target-spreadsheet behavior, tab naming, collision policy, atomicity discipline.

## 3) Status discipline used in this document
Each normative statement is classified as one of:
- **Repo-settled**: already anchored by existing repo contracts/blueprint/decision log.
- **Proposed in this checkpoint**: adopted here as first-release renderer-boundary direction.
- **Still open in this checkpoint**: recognized as unresolved here and left explicit.
- **Deferred**: intentionally out of this checkpoint's decision scope.

## 4) Repo-settled architecture anchors
The following are treated as repo-settled anchors:
- The renderer is a downstream consumer of `AnalyzerOutput` per `docs/analysis_contract.md` §10 (`docs/decision_log.md` D-0055 sub-decision 2 — three-piece architecture: Python analyzer engine + `AnalyzerOutput` + Apps Script analyzer renderer).
- The renderer lives in the central Apps Script library (`apps_script/central_library/`) alongside `Writeback.gs` per `docs/decision_log.md` D-0052 + D-0060 (this PR). File name: `AnalysisRenderer.gs`.
- The renderer opens the source spreadsheet via `SpreadsheetApp.openById(sourceSpreadsheetId)` — the same pattern writeback uses per `docs/writeback_contract.md` §18 + `docs/decision_log.md` D-0051 sub-3a (manifest scope `https://www.googleapis.com/auth/spreadsheets` already broad enough to cover this).
- The renderer is invoked from a route on the launcher Web App per D-0046 / D-0063 (this PR). The operator uploads the `AnalyzerOutput` JSON via that route; the launcher hands it to `RMLib.renderAnalysis(output)` in the central library, which returns a structured result (success/failure + new tab IDs).
- Schema versioning + byte-identical determinism are the same disciplines the rest of the per-run artifact set follows (selector sidecars per `docs/selector_contract.md` §18 + §19; analyzer per `docs/analysis_contract.md` §15 + §14).

## 5) Purpose
Repo-settled intent + checkpoint narrowing:
- Project the analyzer engine's structured `AnalyzerOutput` into the operator's source spreadsheet as K roster tabs + 1 comparison tab, so the operator can visually compare candidates and pick the best one for their actual operational context.
- Make the comparison surface the operator-facing instrument that closes the loop on the M5 thesis (per `docs/decision_log.md` D-0055): operator picks among K candidates with full component breakdowns rather than trusting `totalScore` alone.

## 6) Boundary position
Repo-settled:
- Upstream: the renderer consumes `AnalyzerOutput` per `docs/analysis_contract.md` §10 (passed in-memory after the launcher Web App route deserializes it from the operator's uploaded JSON file).
- Boundary: `RMLib.renderAnalysis(output) → AnalysisRendererResult`. Pure function over `AnalyzerOutput` with one declared side effect (writing tabs into the source spreadsheet identified by `output.source.sourceSpreadsheetId`).
- Downstream: operator-facing tabs in the source spreadsheet.

Proposed in this checkpoint:
- The renderer is a one-input function: `AnalyzerOutput` is its only data input. It MUST NOT consume the wrapper envelope, the FULL sidecar, or the snapshot directly — those flow through the analyzer engine's contract surface and any data the renderer needs is already projected into `AnalyzerOutput`. (Forward compatibility: when the analyzer's emission set grows or shrinks under additive bumps per `docs/analysis_contract.md` §14, the renderer's input shape grows or shrinks with it; no separate input contract.)
- The renderer is solver-agnostic by transitive contract — it consumes `AnalyzerOutput`, which is itself solver-agnostic per `docs/analysis_contract.md` §12.
- The renderer reuses formatting utilities the writeback library already provides (`apps_script/central_library/src/Writeback.gs` exports the helpers used to format roster-tab visual identity); no separate formatter library is introduced.

## 7) What this contract governs
This contract governs:
- the shape of renderer input (`AnalyzerOutput` per `docs/analysis_contract.md` §10, in-memory; §9),
- the shape of renderer output (K + 1 tabs in the source spreadsheet; §10),
- target-spreadsheet behavior — opening, scope, tab placement (§11),
- tab naming convention + collision policy (§12),
- per-tab content shape — roster tab + comparison tab (§13),
- atomicity + idempotency discipline (§14 + §15),
- failure-branch behavior + diagnostic surface (§16),
- determinism guarantees (§17),
- schema versioning (§18),
- the renderer's module placement at `apps_script/central_library/src/AnalysisRenderer.gs` (§4).

## 8) What this contract does not govern
This contract does **not** govern:
- analyzer engine behavior, top-K selection, or `AnalyzerOutput` field semantics (see `docs/analysis_contract.md`),
- the upload portal Web App route — request validation, multipart parsing, or session UX (see M5 C3 / forthcoming sub-PR),
- writeback library behavior or its single-tab output (see `docs/writeback_contract.md`),
- template-generation behavior (see `docs/sheet_generation_contract.md`),
- file-level Apps Script project structure beyond placement of `AnalysisRenderer.gs` (clasp configs, manifest scopes, library version-pinning — see `docs/decision_log.md` D-0041 / D-0051 / D-0052),
- log format, observability transport, or operator-visible progress UI beyond the structured success/failure return shape (§16),
- multi-template support — first-release ICU/HD only; cross-template label propagation tracked separately as `docs/future_work.md` FW-0029,
- sortable / interactive Sheets features (filters, conditional formatting beyond static color blocks, named ranges, charts) — first release ships static layout only.

## 9) Input shape
Renderer invocations are evaluated against the following inputs:

1. **`output`** — an `AnalyzerOutput` object per `docs/analysis_contract.md` §10. Required top-level fields the renderer consumes:
   - `contractVersion` — MUST equal `1`; future versions that change `AnalyzerOutput` shape MAY require a renderer bump per §18.
   - `source.sourceSpreadsheetId` — the target spreadsheet ID the renderer opens via `SpreadsheetApp.openById(...)` per §11.
   - `source.runId` — embedded into tab traceability footers per §13.
   - `topK.requested`, `topK.returned`, `topK.candidates[]` — drives the K roster tabs (one per candidate, in `rankByTotalScore` order). Empty `candidates[]` is fail-loud per §16.
   - `comparison` — drives the single comparison tab.
   - `doctorIdMap` — used to translate `doctorId` → display name for any tab cell that surfaces a doctor.
   - `generatedAt` — embedded into traceability footer.

The renderer MUST NOT consume any field outside `AnalyzerOutput`. No environment variables, no clocks, no other Apps Script state.

### 9.1 Admission checks (fail-loud)
Mirroring the parser/normalizer + analyzer admission discipline (`docs/decision_log.md` D-0038, `docs/analysis_contract.md` §9.5), the renderer MUST fail-loud on:
- `output.contractVersion != 1` — version mismatch; renderer cannot consume future shapes without an update.
- Missing `output.source.sourceSpreadsheetId` — cannot open target spreadsheet.
- `output.topK.candidates` empty or missing — nothing to render; signals upstream defect.
- `SpreadsheetApp.openById(...)` raises (missing spreadsheet, permissions denied, or operator's launcher OAuth scope insufficient — though manifest scope per `docs/decision_log.md` D-0051 sub-3a should cover this) — surface the error verbatim in the structured failure return.

Failure surface: structured rejection in `AnalysisRendererResult.error` per §16, NOT a Google Sheets crash dialog.

## 10) Output shape
The renderer returns an `AnalysisRendererResult` to the launcher Web App caller:

```
AnalysisRendererResult {
  state: "OK" | "FAILED"
  newTabIds: string[]                  // newly-created sheetGid values; ordered by render order
  newTabNames: string[]                // 1:1 with newTabIds
  spreadsheetUrl?: string | null       // operator-facing URL of the source spreadsheet; OPTIONAL — see §10.2
  error?: { code: string, message: string }   // present iff state == "FAILED"
}
```

### 10.2 `spreadsheetUrl` field semantics
`spreadsheetUrl` is the operator-facing URL of the source spreadsheet, constructed from `SpreadsheetApp.openById(...).getUrl()` so it points at the operator's actual sheet (not a Drive folder). The upload portal's success page surfaces it as a clickable "open your roster spreadsheet to see the analysis tabs" link.

Presence rules:
- `state == "OK"`: `spreadsheetUrl` MUST be present and non-empty (the spreadsheet was successfully opened to write tabs into, so a URL is reachable).
- `state == "FAILED"` with `error.code == "RENDER_EXCEPTION"`: `spreadsheetUrl` MUST be present (the spreadsheet was opened before mid-render failure, so a URL is reachable; the partial-state surface in `newTabIds` + `newTabNames` plus the URL lets the operator inspect what was written).
- `state == "FAILED"` with `error.code ∈ { "INVALID_INPUT_VERSION", "MISSING_SOURCE_SPREADSHEET_ID", "EMPTY_TOPK" }`: `spreadsheetUrl` MAY be absent or `null` (admission failed before the spreadsheet was ever opened; no URL to surface).
- `state == "FAILED"` with `error.code == "OPEN_BY_ID_FAILED"`: `spreadsheetUrl` MAY be absent or `null` (`openById(...).getUrl()` itself failed; no URL is reachable).

Renderer implementations MUST omit the field (or emit `null`) rather than fabricate a placeholder URL when no real URL is reachable. v1 readers (the launcher Web App route + tests) MUST tolerate both omission and `null`.

### 10.1 Tabs written
On `state == "OK"`:
- **K roster tabs** — one per candidate in `output.topK.candidates`, in `rankByTotalScore` order (rank 1 = first tab written; rank K = last). Per-tab shape per §13.1.
- **1 comparison tab** — last tab written in render order; per-tab shape per §13.2.

Total: `K + 1` tabs added to the source spreadsheet.

## 11) Target-spreadsheet behavior
Proposed in this checkpoint (normative):

The renderer writes K + 1 tabs into the **source spreadsheet** identified by `output.source.sourceSpreadsheetId` — the same spreadsheet that hosts the operator's input request data and (potentially) writeback's roster tab from a prior Quick Solve run.

Rationale: keeping all roster artifacts in one operator-facing spreadsheet means the operator does not juggle Drive files. Trade-off: tab proliferation across multiple analyze invocations (each adds K + 1 tabs). Mitigated by the always-new-tab pattern (§12 collision policy) and by operator manual cleanup discipline; M5 C4 validation will surface whether tab clutter becomes operationally painful.

### 11.1 Co-existence with writeback's roster tab
When writeback has previously run on the source spreadsheet (per `docs/writeback_contract.md`), the spreadsheet already contains writeback's BEST_ONLY winner roster tab. The renderer MUST NOT delete, modify, or hide writeback's tab — they coexist. The renderer's rank-1 roster tab is by `docs/analysis_contract.md` §11.1's equivalence claim the same candidate as writeback's tab; surfacing the same content twice (once as writeback's tab, once as the renderer's rank-1 tab) is by design — different audit purposes.

### 11.2 Permission scope
The launcher's manifest scope `https://www.googleapis.com/auth/spreadsheets` per `docs/decision_log.md` D-0051 sub-3a is sufficient for `SpreadsheetApp.openById(...)` against any spreadsheet the operator has Editor access to. The renderer adds no new manifest scopes.

### 11.3 Invocation transport
Per `docs/decision_log.md` D-0063, the renderer is invoked from a route on the launcher Web App. The operator uploads the `AnalyzerOutput` JSON via the launcher's existing form-upload pattern (mirroring D-0046's writeback upload route); the launcher's route deserializes the JSON, calls `RMLib.renderAnalysis(output)`, and surfaces the returned `AnalysisRendererResult` to the operator.

Direct-from-bound-shim or other invocation surfaces are NOT in M5 first release; deferred to future work if a Deep Solve / cloud-side renderer-invocation pattern emerges per M6 framing.

## 12) Tab naming + collision policy
Proposed in this checkpoint (normative):

### 12.1 Naming convention
- **Roster tab name**: `Analysis <RUN_SHORT> <RANK>` — e.g., `Analysis abc123 1`, `Analysis abc123 2`, …, `Analysis abc123 K`.
  - `<RUN_SHORT>` = first 6 characters of `output.source.runId` (provides per-run grouping; full `runId` is in the traceability footer).
  - `<RANK>` = the candidate's `rankByTotalScore` (1 through K). Padded to width-2 if K ≥ 10 for stable lexicographic sort: `Analysis abc123 01`, `02`, …, `10`.
- **Comparison tab name**: `Analysis <RUN_SHORT> Comparison`.

### 12.2 Collision policy — always-new-tab per writeback's discipline
If a tab with the chosen name already exists in the source spreadsheet (e.g., the operator ran the same `runId` twice and is uploading the same `AnalyzerOutput` for re-rendering), the renderer MUST follow the **always-new-tab** pattern from `docs/writeback_contract.md` §11: append `(<N>)` suffix where `<N>` is the smallest integer ≥ 2 that yields a unique tab name. Example: `Analysis abc123 1 (2)`, `Analysis abc123 1 (3)`. Existing tabs are NEVER overwritten or modified; the renderer's contract surface is purely additive.

This mirrors writeback's "operator audit trail is preserved by construction" rationale per `docs/writeback_contract.md` §11.

### 12.3 Tab placement
New tabs are appended to the right of all existing tabs in the spreadsheet. The renderer MUST NOT reorder existing tabs.

## 13) Per-tab content shape
Proposed in this checkpoint (normative):

### 13.1 Roster tab (one per candidate)
Each roster tab renders ONE candidate's full assignment matrix using the same visual layout writeback's roster tab uses per `docs/writeback_contract.md` §10 + §16 (shared formatter reuse from `apps_script/central_library/src/Writeback.gs` formatting helpers per `docs/decision_log.md` FW-0029 — analyzer renderer uses the same hardcoded ICU/HD label maps until FW-0029 promotion).

Per-tab content (top-to-bottom):
1. **Header block** — `Analysis Tab — Rank <N> of <K>` plus the candidate's `totalScore`, `recommended` flag (visually distinct if `recommended: true`), and a one-line "best on" summary derived from `scoreComponents[*].rankAcrossTopK == 1` per `docs/analysis_contract.md` §10.9 (renderer-derivable Tier 7 tags).
2. **Per-day assignment grid** — same shape as writeback's roster tab: rows = days, columns = slot types, cells = doctor display names (resolved via `output.doctorIdMap`). Multi-unit slots (per `docs/analysis_contract.md` §10.5 `unitIndex`) get sub-rows or comma-separated cell content per the writeback contract's existing convention.
3. **Per-doctor summary block** — surfaces `output.topK.candidates[*].perDoctor`: per-doctor CALL count, STANDBY count, weekend-CALL count, `cumulativeCallPoints`, `maxConsecutiveDaysOff` (Tier 2 per `docs/analysis_contract.md` §10.6).
4. **Per-component score block** — surfaces `output.topK.candidates[*].scoreComponents`: per-component `weighted` value, `raw` value, `rankAcrossTopK`, `gapToNextRanked` (Tier 1 per `docs/analysis_contract.md` §10.3). Rendered as a small table with one row per scorer component.
5. **Traceability footer** — `runId`, `seed`, `generatedAt`, `sourceSpreadsheetId`, `sourceTabName`, `analysis_contract.contractVersion`, `analysis_renderer_contract.contractVersion`. Read-only via Sheets cell protection (matching writeback's footer discipline per `docs/writeback_contract.md` §16).

### 13.2 Comparison tab (one per render)
The comparison tab is the operator's primary cross-candidate decision-support surface. Per the maintainer's "don't show by default but give max detail when asked" framing per `docs/decision_log.md` D-0058 sub-decision 4, the comparison tab surfaces the maximum-detail Tier 3 + Tier 4 + Tier 5 cross-candidate data; per-candidate Tier 1 + Tier 2 data is on the K roster tabs.

Per-tab content (top-to-bottom):
1. **Header block** — `Analysis Tab — Comparison` plus K, `requested` vs `returned`, `runId` short, `recommended` candidate's rank (always rank 1 per `docs/analysis_contract.md` §11.1).
2. **Score-decomposition matrix** — rows = candidates, columns = scorer components (every first-release component per `docs/domain_model.md` §11.2). Each cell shows the candidate's `weighted` value for that component. A "totals" column shows `totalScore`. Column-best is bolded (rank 1 within column), column-worst is italicized — this is the renderer's Tier 7 derivation per `docs/analysis_contract.md` §10.9.
3. **Equity scalars block** — rows = candidates, columns = (callCount stdev / minMaxGap / Gini, weekendCallCount stdev / minMaxGap / Gini, cumulativeCallPoints stdev / minMaxGap / Gini). Tier 3 from `output.comparison.perCandidateEquity`.
4. **Day-level disagreement** — one row per `output.comparison.hotDays[*]` (or per `output.comparison.lockedDays[*]` listing under a separate sub-block). Tier 4.
5. **Pairwise Hamming matrix** — K × K table; cell `[a][b]` shows `output.comparison.pairwiseHammingDistance[a][b]`. Diagonal is zero. Tier 5 — the load-bearing operator diagnostic for "are my K candidates actually different?" per `docs/decision_log.md` D-0056.
6. **Per-doctor cross-candidate block** (optional, surface in detail-view sub-block) — for each doctor: a small table showing how their CALL count varies across the K candidates. Drives "this candidate is worse for Dr X but better for Dr Y" comparisons. v1 implementations MAY ship this collapsed-by-default and require operator click-to-expand if Sheets's row-grouping feature is used; otherwise just rendered statically below the rest of the content.
7. **Traceability footer** — same fields as roster-tab footer (§13.1 item 5).

### 13.3 Default-visible vs detail-view
Per `docs/decision_log.md` D-0058 sub-decision 4, the analyzer emits everything in scope; the renderer decides UX visibility. v1 ships everything in §13.1 and §13.2 visibly rendered (no collapse-by-default beyond Sheets's native row-grouping where used). M5 C4 operator validation may surface that the maximum-detail view is too dense; subsequent renderer revisions can adjust without requiring an analyzer-contract change.

## 14) Atomicity discipline
Proposed in this checkpoint (normative):

The renderer's tab-write sequence is **best-effort sequential** — Apps Script + SpreadsheetApp does not provide cross-tab transactional semantics, so atomicity in the strict ACID sense is not achievable. To minimize partial-state risk:

- The renderer SHOULD `SpreadsheetApp.flush()` after each tab is fully populated, so a mid-render Apps Script timeout produces a partial set of complete tabs rather than half-populated tabs.
- The render order is rank-1 roster tab → rank-2 → … → rank-K → comparison tab. If render fails partway through, the operator sees rank-1 onward complete, plus a missing comparison tab — informative partial state.
- On any caught exception during rendering, the renderer MUST NOT delete already-written tabs. Operator can manually clean up.
- The structured `AnalysisRendererResult.error` carries enough detail (which tab number was being written when failure occurred) for the operator to know what to expect in the spreadsheet.

## 15) Idempotency
Proposed in this checkpoint (normative):

Re-rendering the same `AnalyzerOutput` twice produces TWO sets of K + 1 tabs — the second invocation's tabs get `(2)` suffixes per §12.2 collision policy. This is INTENTIONAL: the renderer is purely additive; idempotent overwrite would silently destroy operator's prior audit trail.

Operator workflow for "re-render with the same output": operator manually deletes the old tabs in Sheets UI, then re-uploads. The collision policy then produces fresh tabs without suffix. Operator-side cleanup is the explicit pattern.

## 16) Failure-branch behavior + diagnostic surface
Proposed in this checkpoint (normative):

On any admission failure (§9.1) or render-time exception, the renderer returns:

```
{ state: "FAILED", newTabIds: [...], newTabNames: [...], spreadsheetUrl: "...", error: { code, message } }
```

`newTabIds` + `newTabNames` carry the tabs that WERE successfully written before failure (best-effort partial-state surface per §14).

`error.code` enumerates known failure modes:
- `INVALID_INPUT_VERSION` — `output.contractVersion != 1`.
- `MISSING_SOURCE_SPREADSHEET_ID` — admission §9.1.
- `EMPTY_TOPK` — admission §9.1.
- `OPEN_BY_ID_FAILED` — `SpreadsheetApp.openById()` raised; message carries the underlying reason (permissions, missing, etc.).
- `RENDER_EXCEPTION` — caught exception during tab population; message carries which tab + the exception text.

`error.message` is operator-readable and surfaces the load-bearing detail for diagnosis.

## 17) Determinism
Proposed in this checkpoint (normative):

- Given identical `AnalyzerOutput` input AND identical source-spreadsheet state (no pre-existing colliding tab names per §12.2), the renderer MUST produce a byte-identical sequence of tab content (same cell values, same number formatting, same ordering of sub-blocks within each tab). Within-tab cell-content determinism is required; pixel-perfect rendering (which depends on Sheets's view zoom, font availability, etc.) is NOT guaranteed.
- The renderer MUST NOT consume clocks, environment variables, or filesystem state. `output.generatedAt` is the timestamp surfaced in traceability footers (already caller-supplied per `docs/analysis_contract.md` §15); the renderer does not call `new Date().toISOString()`.
- A renderer implementation that produces non-byte-identical content under identical inputs is contract-broken regardless of its observed visual quality.

## 18) Schema versioning
Proposed in this checkpoint (normative):

`contractVersion: 1` per §2.

Bump rule:
- bump `contractVersion` only when tab shape, tab-naming convention, target-spreadsheet behavior, or `AnalysisRendererResult` shape change in a way that breaks v1-targeted callers (i.e., the launcher's Web App route).
- additive changes a v1 caller can tolerate (additional optional fields on `AnalysisRendererResult`, additional sub-blocks within tab content that don't shift positional cells) do NOT require a bump.
- removing or renaming fields, changing tab-naming convention, or changing target-spreadsheet behavior (e.g., switching to a separate Drive-created spreadsheet) does require a bump.

## 19) Consistency with adjacent contracts
- **Upstream analyzer** (`docs/analysis_contract.md`): the renderer reads `AnalyzerOutput` per §10. v1 of this contract is compatible with `analysis_contract.md` `contractVersion: 1`. Future analyzer bumps that alter `AnalyzerOutput` shape MAY trigger renderer bumps.
- **Sibling writeback** (`docs/writeback_contract.md`): the renderer co-exists with writeback's tab in the source spreadsheet (§11.1) and reuses writeback's formatting helpers (§13.1). Both libraries live in the central library per `docs/decision_log.md` D-0052.
- **Upstream selector** (`docs/selector_contract.md`): unaffected; renderer does not consume the FULL sidecar or `FinalResultEnvelope` directly.
- **Upstream snapshot** (`docs/snapshot_contract.md`): unaffected; renderer does not consume the snapshot.
- **Upstream cloud_compute** (`docs/cloud_compute_contract.md`): unaffected; renderer is local-mode only in M5 (cloud-side analyzer-pipeline integration is `docs/future_work.md` FW-0030 + future M6 territory).
- **Sibling sheet_generation** (`docs/sheet_generation_contract.md`): unaffected; renderer does not generate the input sheet shell.

## 20) Explicit deferrals
- **Cloud-side renderer invocation** (e.g., from a Cloud Run Deep Solve job auto-rendering after compute) — out of M5; deferred to FW-0030 / M6 framing.
- **Multi-template label propagation** — `apps_script/central_library/src/Writeback.gs`'s hardcoded ICU/HD label maps remain the source of truth for tab content labels; analyzer-renderer reuses the same maps until `docs/future_work.md` FW-0029 promotes them to template-aware projection.
- **Interactive Sheets features** — filters, conditional formatting beyond static color blocks, named ranges, charts, sparklines. v1 ships static tabular layout only.
- **Operator tab-cleanup automation** — the always-new-tab + suffix policy (§12.2 + §15) means operator manages cleanup manually. A future "clear prior analysis tabs" maintenance command on the launcher could automate this; out of M5 C2 scope.
- **Tier 7 decision-support tags formalization** — the comparison tab's "best on dimension X" / "lowest on dimension Y" derivation (§13.2 item 2) is renderer-side per `docs/analysis_contract.md` §10.9. If M5 C4 surfaces that the renderer's derivation logic is non-trivial enough to warrant moving Tier 7 into analyzer-emitted form, that triggers an analyzer bump per `docs/analysis_contract.md` §14 — not a renderer bump.
- **Comparison-tab UX optimization** — collapse-by-default for sub-blocks, visual hierarchy tuning, color coding. M5 C4 operator validation drives subsequent renderer revisions; v1 ships max-detail visible.
- **Atomicity beyond best-effort sequential** — Apps Script does not expose cross-tab transactional semantics, so v1 stops at `SpreadsheetApp.flush()` per tab. If a future Apps Script API offers transactional batching, revisit then.

## 21) Current checkpoint status
- This document is M5 C2's first deliverable — the renderer contract draft per `docs/decision_log.md` D-0055 sub-decision 2. It pins the renderer's input/output, target-spreadsheet behavior, tab-naming + collision policy, atomicity, determinism sufficiently for M5 C2 implementation work to land against a stable contract surface.
- The renderer implementation (`apps_script/central_library/src/AnalysisRenderer.gs`) + the launcher Web App route + tests are M5 C2 implementation; closure is the M5 C2 closure sub-PR.
- D-0060 (M5 C2 module placement: central library), D-0061 (separate analysis_renderer_contract.md), D-0062 (target = source spreadsheet, accepting tab-bloat trade-off), D-0063 (invocation surface = launcher Web App route per D-0046 pattern) are this contract's load-bearing direction-setting decisions and are recorded in `docs/decision_log.md`.
