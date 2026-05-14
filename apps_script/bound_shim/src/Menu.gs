// Menu.gs
// Container-bound shim for launcher-generated operator spreadsheets per
// `docs/decision_log.md` D-0041 + `docs/snapshot_adapter_contract.md` §3.
//
// Stays intentionally thin (delegate-only). All extractor + writeback logic
// lives in the central Apps Script Library declared in `appsscript.json`
// under the symbol `RMLib`. Library is loaded at version `0` (HEAD per
// D-0041 sub-decision 3), so updates to the central library propagate to
// every operator sheet on next menu click without requiring a re-push of
// this bound shim.
//
// M4 C1 (per D-0049 / D-0052) adds a second menu item "Solve Roster" that
// orchestrates extract → cloud-compute → writeback inline, ending with a
// new writeback tab in the operator's source spreadsheet.
//
// Simple triggers MUST be declared here (NOT in the library) — Apps Script
// does not fire `onOpen` / `onEdit` on imported library functions per
// D-0041 sub-decision 9.

function onOpen(e) {
  SpreadsheetApp.getUi()
    .createMenu('Roster Monster')
    .addItem('Extract Snapshot', 'menuExtractSnapshot_')
    .addItem('Solve Roster', 'menuSolveRoster_')
    .addToUi();
}

function menuExtractSnapshot_() {
  // Delegate to the central library. The library returns an HtmlOutput
  // payload that triggers a browser download of the snapshot JSON file
  // per `docs/decision_log.md` D-0040.
  var html = RMLib.extractSnapshotForActiveSheet();
  SpreadsheetApp.getUi().showModalDialog(html, 'Snapshot ready');
}

// Multi-click guard: TWO per-spreadsheet locks on DocumentProperties,
// each storing a timestamp (ms since epoch). Different scopes,
// different enforcement strengths.
//
// 1. EXTRACT lock (`_RM_EXTRACT_LOCK_KEY`) — set when a click commits
//    to the slow path (~14s extract + ~1.5s POST). Set inside
//    `_quickValidate_` under a LockService doc lock (atomic check-and-
//    set across racing executions per Codex P2 round 1 finding);
//    cleared in `menuSolveRoster_`'s try/finally so it auto-releases
//    on success, cloud-error, AND uncaught exception. Acts as a HARD
//    BLOCK on concurrent re-clicks during the slow path. TTL is 7 min
//    — must exceed any plausible live `_solveRoster_` duration (per
//    Codex P2 round 2 finding: too-short TTL lets a slow live run be
//    misidentified as stale). Apps Script caps per-execution runtime
//    at 6 min on consumer accounts, so 7 min = 6 min cap + 60s buffer
//    for kill-timing edge cases. Cost: after a rare Apps-Script-killed
//    crash, the operator waits up to 7 min for the lock to TTL out.
//
// 2. ASYNC lock (`_RM_ASYNC_LOCK_KEY`) — set when a click submits an
//    async LAHC run (Cloud Run returned `SUBMITTED`). The actual solve
//    runs on Cloud Batch for 5-10 min and the operator sees results
//    via email; during that window, a re-click should not silently
//    kick off a second extract that Cloud Run will reject ~15s later.
//    Per Codex P2 round 3 finding + maintainer-confirmed warn-don't-
//    block scope: ASYNC lock triggers a SOFT WARN (YES/NO confirm
//    dialog) on the next click — operator can still override and
//    start a new run. TTL is 11 min — covers the 10-min Cloud Batch
//    operator-facing hard cap with a 1-min buffer.
var _RM_EXTRACT_LOCK_KEY = 'rm_solve_extract_inflight_ts_ms';
var _RM_EXTRACT_LOCK_TTL_MS = 7 * 60 * 1000;
var _RM_ASYNC_LOCK_KEY = 'rm_solve_async_inflight_ts_ms';
var _RM_ASYNC_LOCK_TTL_MS = 11 * 60 * 1000;
// `LockService.getDocumentLock().tryLock(N)` waits up to N ms to acquire
// the doc-scoped concurrency lock. TWO timeout values for two different
// callers, because the two callers have opposite urgency profiles:
//
// - ACQUIRE timeout (500ms) — used by `_quickValidate_` + the YES-path
//   `_refreshExtractLockIfOwned_`. The operator IS waiting on these, so
//   fail fast: if the lock is contended, bail quickly with a clear
//   "another execution is racing this one" alert rather than making the
//   operator stare at a frozen menu.
//
// - CLEANUP timeout (5s) — used by `_clearExtractLockIfOwned_`. The
//   operator is NOT waiting on cleanup (it runs in finally / cancel /
//   error paths after the operator-facing outcome is already decided).
//   Fail-fast here is actively harmful: a 500ms timeout that loses a
//   race silently leaves the EXTRACT lock set, hard-blocking the next
//   click for the full 7-min TTL. 5s is ~25-100× the expected lock
//   hold time, so cleanup virtually always succeeds; the 7-min TTL is
//   the last-resort backstop. Per Codex P2 round 8 finding on PR #170.
var _RM_DOC_LOCK_ACQUIRE_TIMEOUT_MS = 500;
var _RM_DOC_LOCK_CLEANUP_TIMEOUT_MS = 5 * 1000;

// "Solve Roster" menu handler per `docs/decision_log.md` D-0049 +
// `docs/cloud_compute_contract.md`. Synchronously orchestrates the
// three pipeline stages and surfaces a single result dialog at the end:
//
//   1. Pre-flight validation (`_quickValidate_`) — cheap click-time
//      checks that catch the most common operator mistakes (wrong tab,
//      missing config, in-flight re-click) BEFORE the ~14s extract.
//      On success, atomically sets the EXTRACT lock under a LockService
//      doc lock; that lock stays set for the duration of the slow path
//      and is cleared in the finally block. Also detects an active
//      ASYNC lock (a previous run still in its 5-10 min Cloud Batch
//      window) and returns a `warning` for the caller to surface.
//   2. If a `warning` was returned, show a YES/NO confirm dialog. NO
//      cancels (and releases the EXTRACT lock); YES clears the ASYNC
//      lock and proceeds.
//   3. Show "Initializing snapshot" toast — narrates the slow extract
//      so the operator knows the click registered and roughly how long
//      to expect. Toast stays visible until the terminal modal replaces
//      it.
//   4. Extract snapshot in-memory via RMLib (no file boundary).
//   5. POST snapshot to Cloud Run /compute endpoint with an OIDC token
//      from `ScriptApp.getIdentityToken()` per D-0051 sub-decision 2.
//   6. Pass the returned writebackEnvelope to RMLib.applyWriteback()
//      per D-0052 to render the new writeback tab (sync path; the LAHC
//      async path returns SUBMITTED at step 5 and the actual writeback
//      lands via the launcher's `async-render-callback` route).
//   7. On SUBMITTED_ASYNC, set the ASYNC lock so future clicks during
//      the 5-10 min Cloud Batch window get the soft-warn dialog at
//      step 2.
//
// Wall-clock budget: preflight (<1s) + extract (~14s) + cloud (~1-2s) +
// writeback (~3-5s on the deprecated sync path). Comfortably within
// Apps Script's 6 min per-execution limit per
// `docs/cloud_compute_contract.md` §8.4.
function menuSolveRoster_() {
  var ui = SpreadsheetApp.getUi();
  var t0 = Date.now();
  console.log('[timing] solve_roster_start ts_ms=' + t0);

  // Step 1: cheap preflight. Returns `{ok: false, error}` to abort with
  // a click-time alert; `{ok: true, warning?}` to proceed (with optional
  // soft-warn dialog if a previous async run is still pending).
  var pre = _quickValidate_();
  var tPreflight = Date.now();
  console.log('[timing] preflight_done delta_ms=' + (tPreflight - t0) +
    ' elapsed_ms=' + (tPreflight - t0));
  if (!pre.ok) {
    ui.alert('Solve Roster — cannot start', pre.error, ui.ButtonSet.OK);
    return;
  }

  // Track our own EXTRACT lock identifier (timestamp set by
  // `_quickValidate_`) so cleanup paths only clear the lock when it's
  // still ours — never accidentally delete a foreign execution's lock
  // per Codex P2 round 5 finding (modal-dwell takeover defense).
  var ownExtractLockTs = pre.ownExtractLockTs;

  // Step 2: soft warn for active ASYNC lock per Codex P2 round 3
  // finding + maintainer-confirmed warn-don't-block scope. EXTRACT
  // lock has already been set inside _quickValidate_; release it
  // (ownership-checked) if the operator cancels.
  if (pre.warning) {
    var response = ui.alert(
      'Possible run in progress',
      pre.warning,
      ui.ButtonSet.YES_NO
    );
    if (response !== ui.Button.YES) {
      _clearExtractLockIfOwned_(ownExtractLockTs);
      return;
    }
    // YES — refresh the EXTRACT lock atomically (verifies ownership +
    // pushes the TTL window forward to cover the slow path). If
    // another execution claimed the slot while the operator was on the
    // dialog, refresh returns null → bail with a clear re-click prompt.
    // Per Codex P2 round 5 finding.
    var refreshed = _refreshExtractLockIfOwned_(ownExtractLockTs);
    if (refreshed === null) {
      // Refresh can return null because (a) another execution took the
      // slot, or (b) `_refreshExtractLockIfOwned_`'s own LockService
      // tryLock timed out under transient contention — and case (b)
      // leaves OUR lock still set with our timestamp. Without this
      // ownership-checked clear, the operator's re-click would be
      // hard-blocked by their own phantom lock until the 7-min TTL.
      // Per Codex P2 round 7 finding on PR #170. Cleanup is idempotent:
      // no-op in case (a) where the lock isn't ours anymore.
      _clearExtractLockIfOwned_(ownExtractLockTs);
      ui.alert(
        'Solve Roster — re-click required',
        'Could not refresh the in-flight lock — another execution may ' +
        'have claimed the slot while you were on the dialog, or the ' +
        'lock service is temporarily contended. Click Solve Roster ' +
        'again to retry.',
        ui.ButtonSet.OK
      );
      return;
    }
    ownExtractLockTs = refreshed;
    // NOTE: we intentionally do NOT clear the ASYNC lock here. The
    // operator clicked YES, but their NEW run hasn't submitted yet —
    // it could still fail (extract error, auth, network, Cloud HTTP
    // error). If we cleared the ASYNC marker now and the new run then
    // failed, we'd have forgotten about the PREVIOUS run that may
    // still be processing on Cloud Batch — the next click would skip
    // the warn dialog and waste a full extract before Cloud Run's
    // concurrent-rejection responds. Instead, the ASYNC marker is
    // OVERWRITTEN (not cleared-then-set) only when the new run
    // actually returns SUBMITTED_ASYNC below; if the new run fails,
    // the previous run's ASYNC marker correctly stays in place. Per
    // Codex P2 round 8 finding on PR #170.
  }

  // Step 3: show the "Initializing" toast. The EXTRACT lock has already
  // been set inside `_quickValidate_` (atomically with the check, under a
  // LockService doc lock per Codex P2 round 1 finding); lock release
  // happens in the finally block below.
  SpreadsheetApp.getActiveSpreadsheet().toast(
    'Initializing snapshot — please wait up to 1 minute for the next prompt.',
    'Roster Monster',
    -1
  );

  var result;
  try {
    result = _solveRoster_(t0, tPreflight);
    // Step 7: if we just submitted an async LAHC run, set the ASYNC lock
    // here (BEFORE the finally clears EXTRACT) so the EXTRACT→ASYNC
    // handoff is gap-free — a concurrent click during the entire flow
    // always sees at least one of the two locks set, never both clear.
    // Per Codex P2 round 3 + round 4 findings: ASYNC lock causes future
    // clicks during the 5-10 min Cloud Batch window to surface the
    // soft-warn dialog at step 2. This `setProperty` OVERWRITES any
    // prior ASYNC marker (e.g., from a run the operator just overrode
    // via the warn dialog) with the new run's fresh timestamp — which
    // is exactly why the YES path above does NOT pre-clear it: only a
    // genuinely-submitted replacement run should reset the marker (per
    // Codex P2 round 8 finding).
    if (result && result.kind === 'SUBMITTED_ASYNC') {
      PropertiesService.getDocumentProperties().setProperty(
        _RM_ASYNC_LOCK_KEY, String(Date.now()));
    }
  } catch (e) {
    // Clear the EXTRACT lock BEFORE showing the blocking error alert.
    // ui.alert() suspends server-side execution until the operator
    // clicks OK, and Apps Script's `finally` block runs AFTER the
    // catch body completes (i.e., after the alert is dismissed).
    // Without this early clear, other clicks on this spreadsheet
    // would be hard-blocked as "still in extract" for the entire
    // duration of operator dwell on the error dialog. The finally
    // clear below remains as a no-op safety net (idempotent).
    // Per Codex P2 round 6 finding on PR #170.
    _clearExtractLockIfOwned_(ownExtractLockTs);
    ui.alert(
      'Solve Roster failed',
      _formatErrorForOperator_(e),
      ui.ButtonSet.OK
    );
    return;
  } finally {
    _clearExtractLockIfOwned_(ownExtractLockTs);
  }

  _showSolveRosterResult_(result);
}

// Cheap click-time validation. Returns one of:
//   - `{ok: false, error: <msg>}` — abort immediately with click-time
//     alert (no toast, no slow extract). Triggered by EXTRACT lock,
//     missing config, OAuth issue, or wrong tab.
//   - `{ok: true}` — proceed normally. EXTRACT lock has been set
//     atomically; caller must clear it in finally.
//   - `{ok: true, warning: <msg>}` — proceed BUT first show a YES/NO
//     confirm dialog with the warning text. Triggered by ASYNC lock
//     (a previous SUBMITTED run is still within its 5-10 min Cloud
//     Batch window). Caller releases the EXTRACT lock if the operator
//     declines; clears the ASYNC lock if the operator confirms.
// Target latency: <1 second total (one DeveloperMetadata finder call
// dominates at ~50-200ms; the other checks are O(1) property reads).
// Intentionally does NOT duplicate the snapshot extractor's structural
// validation — the extractor is the authoritative validator for sheet
// structure, and we'd need the full 14s metadata sweep to replicate it.
// This function only catches the click-time mistakes that don't need
// the slow path:
//   1. EXTRACT lock — concurrent click during slow path (HARD BLOCK).
//   2. Cloud Run URL not configured.
//   3. Operator email unavailable (OAuth scope issue).
//   4. Active tab is not a request-entry tab (the most common operator
//      mistake; currently surfaces ~14s late as `EXTRACTION_ERROR`).
//   5. ASYNC lock — previous SUBMITTED still in Cloud Batch window
//      (SOFT WARN — operator can override).
// Anything more semantic (weird prefill names, malformed request cells,
// scorer-config drift) requires the slow path's full sweep — the toast
// covers the wait so the operator knows we're working.
function _quickValidate_() {
  // Acquire the doc-scoped LockService lock so the EXTRACT timestamp
  // check-and-set is atomic across racing executions (two operators on
  // the same sheet, or two rapid Apps Script invocations from the same
  // operator). Without this, the original implementation had a TOCTOU
  // window between getProperty and setProperty during which a second
  // execution could pass the check + both would set the timestamp +
  // both would race into Cloud Run submission. Per Codex P2 round 1
  // finding on PR #170. Lock spans only the check-and-set window inside
  // this function (typical ~50-200ms — one metadata finder dominates);
  // released via try/finally before this function returns. The much
  // longer EXTRACT TIMESTAMP guard (held for the whole 14s extract)
  // is the actual multi-click block; the LockService lock just makes
  // its acquisition atomic.
  var docLock = LockService.getDocumentLock();
  if (!docLock.tryLock(_RM_DOC_LOCK_ACQUIRE_TIMEOUT_MS)) {
    return { ok: false, error:
      'Could not acquire the document lock to start Solve Roster — ' +
      'another execution is racing this one. Wait a moment and try again.' };
  }
  try {
    var props = PropertiesService.getDocumentProperties();

    // Check 1: EXTRACT lock (HARD BLOCK). If a previous click is still
    // mid-extract on this spreadsheet (within the TTL), reject so the
    // operator doesn't kick off a duplicate extract.
    var extractTsStr = props.getProperty(_RM_EXTRACT_LOCK_KEY);
    if (extractTsStr) {
      var extractElapsed = Date.now() - parseInt(extractTsStr, 10);
      if (extractElapsed >= 0 && extractElapsed < _RM_EXTRACT_LOCK_TTL_MS) {
        return { ok: false, error:
          'A previous Solve Roster click is still in extract on this ' +
          'spreadsheet (started ' + Math.ceil(extractElapsed / 1000) +
          's ago). Wait for the prompt before clicking again.' };
      }
      // Stale lock (>TTL or clock-skew negative) — clear and proceed.
      // Crash-recovery path: covers the case where a prior
      // `menuSolveRoster_` was killed before its finally block ran.
      props.deleteProperty(_RM_EXTRACT_LOCK_KEY);
    }

    // Check 2: Cloud Run URL configured on the central library. Same check
    // _solveRoster_ does internally — surfacing it here means the operator
    // gets a clear CONFIG_ERROR alert at click time instead of waiting ~14s
    // for the extract before the same error fires.
    var cloudUrl = RMLib.getCloudRunUrl();
    if (!cloudUrl) {
      return { ok: false, error:
        'CONFIG_ERROR: Cloud Run URL not configured. The maintainer needs ' +
        'to set the CLOUD_RUN_URL Script Property on the Roster Monster ' +
        'Central Library Apps Script project.' };
    }

    // Check 3: operator email available. Required for the LAHC async path's
    // operatorEmail field per `docs/cloud_compute_contract.md` §9.3 (the
    // Cloud Batch finalizer needs it for the always-email-on-every-outcome
    // path per §10A.7). Same defense as inside _solveRoster_; pulled forward
    // to click time.
    var operatorEmail = Session.getActiveUser().getEmail();
    if (!operatorEmail) {
      return { ok: false, error:
        'OPERATOR_EMAIL_UNAVAILABLE: Could not read your email address. ' +
        'Re-open the spreadsheet and re-authorize when prompted (verify ' +
        'the userinfo.email OAuth scope).' };
    }

    // Check 4: active tab is a request-entry tab. The single most common
    // operator mistake is clicking Solve Roster from a different tab (e.g.,
    // a writeback tab from a prior run, or a Scorer Config tab). Without
    // this preflight, the operator waits ~14s for the extract to fail with
    // "EXTRACTION_ERROR: not a request-entry tab". One `withKey()` finder
    // on the active sheet only — does NOT trigger the workbook-wide sweep
    // that the full extractor does.
    var activeSheet = SpreadsheetApp.getActiveSheet();
    var tabTypeMatches = activeSheet.createDeveloperMetadataFinder()
      .withKey('rosterMonster:tabType').find();
    if (tabTypeMatches.length !== 1 ||
        tabTypeMatches[0].getValue() !== 'requestEntry') {
      return { ok: false, error:
        'This tab ("' + activeSheet.getName() + '") is not a request-entry ' +
        'tab. Open the period\'s request-entry tab (usually named like ' +
        '"<Section> Requests <month>") and click Solve Roster from there.' };
    }

    // All hard checks passed — atomically set the EXTRACT lock under the
    // doc lock so a racing second click sees it on its check. The
    // timestamp we set is also returned to the caller as `ownExtractLockTs`
    // so caller can verify ownership later (during the refresh after a
    // YES on the warn dialog, and in the finally cleanup) per Codex P2
    // round 5 finding — the timestamp acts as a per-execution lock
    // identifier.
    var ownExtractLockTs = String(Date.now());
    props.setProperty(_RM_EXTRACT_LOCK_KEY, ownExtractLockTs);

    // Check 5: ASYNC lock (SOFT WARN). If a previous SUBMITTED run is
    // still within its Cloud Batch window, surface a warning string for
    // the caller's YES/NO dialog. Maintainer-confirmed warn-don't-block
    // scope per Codex P2 round 3 finding: operator can override and
    // start a new run (e.g., if they suspect the previous run failed
    // silently or its email got lost).
    var asyncWarning = null;
    var asyncTsStr = props.getProperty(_RM_ASYNC_LOCK_KEY);
    if (asyncTsStr) {
      var asyncElapsed = Date.now() - parseInt(asyncTsStr, 10);
      if (asyncElapsed >= 0 && asyncElapsed < _RM_ASYNC_LOCK_TTL_MS) {
        var asyncMins = Math.ceil(asyncElapsed / 60000);
        asyncWarning =
          'A previous Solve Roster run was submitted on this spreadsheet ' +
          '~' + asyncMins + ' minute(s) ago and may still be processing ' +
          '(typical wait: 5-10 minutes from submit). If the email hasn\'t ' +
          'arrived, the run is likely still active and Cloud Run will ' +
          'reject a new submission after the ~15-second snapshot extract.' +
          '\n\nContinue anyway?';
      } else {
        // Stale ASYNC lock (>TTL) — the run window has lapsed; clear so
        // future clicks aren't warned about it.
        props.deleteProperty(_RM_ASYNC_LOCK_KEY);
      }
    }

    return {
      ok: true,
      warning: asyncWarning,
      ownExtractLockTs: ownExtractLockTs,
    };
  } finally {
    docLock.releaseLock();
  }
}

// Atomically refresh the EXTRACT lock if and only if it's still owned
// by this execution (current value matches `ownTs`). Returns the new
// timestamp on success; null if the lock has been overwritten by another
// execution (e.g., a second operator's click took over while the first
// operator was on the warn dialog). Per Codex P2 round 5 finding: closes
// the modal-dwell race where the EXTRACT TTL could expire mid-dialog
// and another execution could claim the slot. Apps Script's 6-min
// per-execution limit bounds dwell to less than the 7-min TTL in
// practice, but the ownership check makes the guard robust to TTL
// changes and clock skew.
function _refreshExtractLockIfOwned_(ownTs) {
  var docLock = LockService.getDocumentLock();
  if (!docLock.tryLock(_RM_DOC_LOCK_ACQUIRE_TIMEOUT_MS)) return null;
  try {
    var props = PropertiesService.getDocumentProperties();
    if (props.getProperty(_RM_EXTRACT_LOCK_KEY) !== ownTs) return null;
    var newTs = String(Date.now());
    props.setProperty(_RM_EXTRACT_LOCK_KEY, newTs);
    return newTs;
  } finally {
    docLock.releaseLock();
  }
}

// Atomically clear the EXTRACT lock if and only if it's still owned by
// this execution. Used by the cancel path on the warn dialog, the
// catch block, the YES-refresh-failed path, AND the finally block in
// `menuSolveRoster_` so we never accidentally delete another
// execution's lock if a takeover happened. Silent on ownership
// mismatch (lock not ours) — the appropriate response is to leave the
// foreign lock alone.
//
// Uses the PATIENT cleanup timeout (5s), not the fast-fail acquire
// timeout: the operator is not waiting on cleanup, and a fail-fast
// timeout that loses a race would silently leak the EXTRACT lock and
// hard-block the next click for the full 7-min TTL. Per Codex P2
// round 8 finding on PR #170.
function _clearExtractLockIfOwned_(ownTs) {
  var docLock = LockService.getDocumentLock();
  if (!docLock.tryLock(_RM_DOC_LOCK_CLEANUP_TIMEOUT_MS)) return;
  try {
    var props = PropertiesService.getDocumentProperties();
    if (props.getProperty(_RM_EXTRACT_LOCK_KEY) === ownTs) {
      props.deleteProperty(_RM_EXTRACT_LOCK_KEY);
    }
  } finally {
    docLock.releaseLock();
  }
}

// Internal orchestrator. Throws Error on any unrecoverable failure;
// caller (`menuSolveRoster_`) catches and renders the message into the
// error dialog. `_timing_t0` and `_timing_t_preflight` are passed in
// from the caller so the timing waterfall stays continuous from the
// click instant — `_timing_t0` is the menu-click anchor (used for
// `elapsed_ms`); `_timing_t_preflight` is the previous marker (used
// for `config_resolved`'s `delta_ms`).
function _solveRoster_(_timing_t0, _timing_t_preflight) {
  // Timing instrumentation per the M7 closure UX-improvement thread —
  // captures click → first-prompt latency so we can identify the
  // dominant bottleneck (extract vs Cloud Run cold-start vs Batch
  // submit). console.log() writes to Cloud Logging when the Apps Script
  // project is linked to a GCP project (verify via Apps Script editor →
  // Project Settings → Google Cloud Platform). Format: `[timing] stage
  // delta_ms=N elapsed_ms=N` so the dry-run analysis script can parse it.
  // The `solve_roster_start` and `preflight_done` markers are emitted
  // by the caller (`menuSolveRoster_`) before this function runs.

  // Stage 0: resolve Cloud Run URL from the central library's script
  // properties. Library-level properties are shared across all consumers
  // (one source of truth) and don't get nulled-out by makeCopy() of
  // operator spreadsheets. Note this duplicates the preflight check —
  // intentional: keeps `_solveRoster_` self-contained for testing /
  // direct invocation paths that bypass the menu handler.
  var cloudUrl = RMLib.getCloudRunUrl();
  if (!cloudUrl) {
    throw new Error(
      'CONFIG_ERROR: Cloud Run URL not configured. Maintainer should ' +
      'open the Roster Monster Extractor Library Apps Script project, ' +
      'navigate to Project Settings → Script Properties, and add ' +
      '"CLOUD_RUN_URL" with the deployed service URL ' +
      '(e.g., https://roster-monster-compute-...run.app). See ' +
      'cloud_compute_service/README.md.'
    );
  }

  // Stage 1: extract snapshot in-memory via the central library.
  var _timing_t1 = Date.now();
  console.log(
    '[timing] config_resolved delta_ms=' + (_timing_t1 - _timing_t_preflight) +
    ' elapsed_ms=' + (_timing_t1 - _timing_t0)
  );
  var snapshot;
  try {
    snapshot = RMLib.extractSnapshotInMemoryForActiveSheet();
  } catch (e) {
    throw new Error(
      'EXTRACT_FAILED: ' + ((e && e.message) ? e.message : String(e))
    );
  }
  var _timing_t2 = Date.now();
  console.log(
    '[timing] snapshot_extracted delta_ms=' + (_timing_t2 - _timing_t1) +
    ' elapsed_ms=' + (_timing_t2 - _timing_t0)
  );

  // Stage 2: acquire an OIDC token for Cloud Run IAM auth.
  var token = ScriptApp.getIdentityToken();
  if (!token) {
    throw new Error(
      'AUTH_ERROR: ScriptApp.getIdentityToken() returned no token. ' +
      'Verify the bound shim manifest declares the openid + ' +
      'userinfo.email OAuth scopes per `docs/decision_log.md` D-0051 ' +
      'sub-decision 3a.'
    );
  }

  // Stage 3: POST to Cloud Run /compute. Note `muteHttpExceptions: true`
  // is required so we can dispatch on HTTP status codes (401/403 for
  // auth failures per `docs/cloud_compute_contract.md` §7.5; 200 for
  // application-level state per §10) rather than have UrlFetchApp throw
  // on every non-2xx response.
  //
  // M7 C4 T2D: bound shim is LAHC-only on the operator path per D-0071
  // sub-decision 13 (SRB stays in code for benchmarks but no operator-
  // facing menu item). `solverStrategy: 'LAHC'` activates the Cloud Run
  // thin front door at app.py: validate + concurrent-rejection + submit
  // Batch + return SUBMITTED in ~3-5s. `operatorEmail` is REQUIRED on
  // the LAHC path per §9.3 (the Cloud Batch finalizer needs it for the
  // always-email-on-every-outcome path); sourced from
  // `Session.getActiveUser().getEmail()` per D-0071 sub-decision 6.
  var endpoint = cloudUrl.replace(/\/+$/, '') + '/compute';
  var operatorEmail = Session.getActiveUser().getEmail();
  if (!operatorEmail) {
    throw new Error(
      'OPERATOR_EMAIL_UNAVAILABLE: Session.getActiveUser().getEmail() ' +
      'returned empty. Verify the bound shim manifest declares the ' +
      'userinfo.email OAuth scope per `docs/decision_log.md` D-0051 ' +
      'sub-decision 3a (the LAHC async path requires operatorEmail ' +
      'to receive the completion email per §10A.7).'
    );
  }
  var requestBody = JSON.stringify({
    snapshot: snapshot,
    operatorEmail: operatorEmail,
    optionalConfig: {
      solverStrategy: 'LAHC',
    },
  });

  var _timing_t3 = Date.now();
  console.log(
    '[timing] request_prepared delta_ms=' + (_timing_t3 - _timing_t2) +
    ' elapsed_ms=' + (_timing_t3 - _timing_t0)
  );
  var response;
  try {
    response = UrlFetchApp.fetch(endpoint, {
      method: 'post',
      // Per `docs/decision_log.md` D-0054, the operator's ID token
      // travels via `X-Auth-Token` (not `Authorization`). Cloud Run
      // strips the standard `Authorization` header from public
      // services to prevent token leakage; using a custom header
      // bypasses that scrubbing while keeping the Flask-side
      // operator-allowlist auth path functional.
      headers: { 'X-Auth-Token': token },
      contentType: 'application/json',
      payload: requestBody,
      muteHttpExceptions: true,
    });
  } catch (e) {
    // Pre-response transport failure (DNS, network, etc).
    throw new Error(
      'NETWORK_ERROR: Could not reach Cloud Run at ' + endpoint + '. ' +
      ((e && e.message) ? e.message : String(e))
    );
  }
  var _timing_t4 = Date.now();
  console.log(
    '[timing] cloud_response_received delta_ms=' + (_timing_t4 - _timing_t3) +
    ' elapsed_ms=' + (_timing_t4 - _timing_t0) +
    ' http_status=' + response.getResponseCode()
  );

  var statusCode = response.getResponseCode();
  if (statusCode === 401 || statusCode === 403) {
    throw new Error(
      'AUTH_REJECTED: Cloud Run rejected the request (HTTP ' + statusCode +
      '). Verify your account is on the OAuth Test Users list AND has ' +
      'roles/run.invoker on the roster-monster-compute service.'
    );
  }
  if (statusCode !== 200) {
    throw new Error(
      'CLOUD_HTTP_' + statusCode + ': ' +
      String(response.getContentText() || '').substring(0, 500)
    );
  }

  var body;
  try {
    body = JSON.parse(response.getContentText());
  } catch (e) {
    throw new Error(
      'CLOUD_RESPONSE_NOT_JSON: ' + String(response.getContentText() || '').substring(0, 500)
    );
  }

  // Stage 4: dispatch on cloud-side state.
  if (body.state === 'INPUT_ERROR' || body.state === 'COMPUTE_ERROR') {
    return {
      kind: 'CLOUD_ERROR',
      cloudState: body.state,
      errorCode: body.error && body.error.code,
      errorMessage: body.error && body.error.message,
    };
  }
  // M7 C4 T2B defensive-async handler per `docs/delivery_plan.md` §9
  // T2C scope: accept the new `SUBMITTED` enum value (added in M7 C3
  // per D-0071 sub-decision 2 + Codex P2 round 1 ordering fix). When
  // Cloud Run cuts over to the async LAHC path at T2D, the operator
  // path returns `SUBMITTED` immediately + the actual outcome lands
  // asynchronously via the launcher's `async-render-callback` route.
  // Pre-T2C the bound shim would have thrown `CLOUD_UNEXPECTED_STATE`
  // on every operator click between Cloud Run cutover and bound shim
  // re-deploy; T2C lands FIRST to close that window. NO request-body
  // change here — bound shim still sends the SRB shape; T2D flips
  // the strategy to LAHC + threads operatorEmail through (so this
  // SUBMITTED handler only fires once T2D's request-shape change
  // also lands).
  if (body.state === 'SUBMITTED') {
    var _timing_t5 = Date.now();
    console.log(
      '[timing] submitted_state_returned delta_ms=' + (_timing_t5 - _timing_t4) +
      ' elapsed_ms=' + (_timing_t5 - _timing_t0) +
      ' run_id=' + ((body.submission || {}).runId || 'unknown')
    );
    return {
      kind: 'SUBMITTED_ASYNC',
      cloudState: 'SUBMITTED',
      submission: body.submission || {},
    };
  }
  if (body.state !== 'OK' && body.state !== 'UNSATISFIED') {
    throw new Error(
      'CLOUD_UNEXPECTED_STATE: ' + JSON.stringify(body.state)
    );
  }
  if (!body.writebackEnvelope) {
    throw new Error(
      'CLOUD_MISSING_ENVELOPE: state=' + body.state + ' but writebackEnvelope is null'
    );
  }

  // Stage 5: hand the writeback envelope to the central library's
  // writeback adapter. The library parses, opens the source spreadsheet
  // (which is the active one), writes the new tab, returns the
  // 3-state diagnostic per writeback contract §17.
  var writebackResult = RMLib.applyWriteback(
    JSON.stringify(body.writebackEnvelope)
  );

  return {
    kind: 'WRITEBACK_DONE',
    cloudState: body.state,
    writebackState: writebackResult.state,
    writebackTabName: writebackResult.tabName,
    writebackUrl: writebackResult.spreadsheetUrl,
    writebackError: writebackResult.error,
  };
}

function _showSolveRosterResult_(result) {
  var ui = SpreadsheetApp.getUi();
  if (result.kind === 'CLOUD_ERROR') {
    ui.alert(
      'Solve Roster — ' + result.cloudState,
      'Cloud compute returned ' + result.cloudState + ' (' +
      (result.errorCode || 'no code') + '): ' +
      (result.errorMessage || '(no message)'),
      ui.ButtonSet.OK
    );
    return;
  }

  if (result.kind === 'SUBMITTED_ASYNC') {
    // M7 C4 T2C async UX per D-0071 sub-decision 9: post-submit
    // notification. The actual writeback + analyzer tabs land
    // asynchronously when the launcher Web App receives the §10A
    // callback POST from the Cloud Batch worker's inline finalize
    // step. Operator gets an email when complete (per §10A.7
    // always-email-on-every-outcome).
    //
    // **Switched from `.toast()` (bottom-right, non-blocking) to
    // `ui.alert()` (centered modal, requires OK click) on
    // 2026-05-13** per operator feedback that the small bottom-
    // right notification was easy to miss. The modal is more
    // intrusive but acknowledges-by-default — operator must click
    // OK to confirm they've seen "wait for email", which is the
    // right signal for an async flow where nothing else changes
    // on-screen for ~5-10 minutes.
    ui.alert(
      'Solve Roster — Submitted',
      'We’ll email you when the roster is ready '
        + '— can take up to 10 minutes.',
      ui.ButtonSet.OK
    );
    return;
  }

  // WRITEBACK_DONE
  if (result.writebackState === 'SUCCESS' ||
      result.writebackState === 'FAILED') {
    var heading = (result.writebackState === 'SUCCESS')
      ? 'Roster written to new tab'
      : 'No allocation possible — failure tab written';
    var detail = (result.writebackState === 'SUCCESS')
      ? 'A new tab "' + (result.writebackTabName || '?') +
        '" was added to this spreadsheet with the winner allocation, ' +
        'traceability footer, and read-only protection.'
      : 'A new tab "' + (result.writebackTabName || '?') +
        '" was added to this spreadsheet describing what could not be ' +
        'filled (see the new tab for unfilledDemand + reasons).';
    if (result.writebackUrl) {
      detail += '\n\nLink: ' + result.writebackUrl;
    }
    ui.alert(heading, detail, ui.ButtonSet.OK);
    return;
  }

  // RUNTIME_ERROR from the writeback library — extract succeeded, cloud
  // succeeded, but writeback itself errored mid-write.
  ui.alert(
    'Writeback runtime error',
    String(result.writebackError || '(no message)'),
    ui.ButtonSet.OK
  );
}

function _formatErrorForOperator_(e) {
  var msg = (e && e.message) ? String(e.message) : String(e);
  // Trim Apps Script's stack-trace prefix if present.
  return msg;
}
