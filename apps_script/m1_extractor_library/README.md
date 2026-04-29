# Roster Monster — Extractor Library

A central Apps Script Library carrying the snapshot-extractor logic that
operator sheets call into via the bound template shim
(`apps_script/m1_template_bound_script/`). When the bound shim's menu
handler fires, it delegates to `RMLib.extractSnapshotForActiveSheet()`
declared here.

Per `docs/decision_log.md` D-0041 + `docs/snapshot_adapter_contract.md` §3.

## Why this is a separate Apps Script Library (not a bound-script-only design)

The bound shim is frozen at `makeCopy()` time inside each operator-copy.
If the entire extractor logic lived in the bound shim, bug fixes would
never reach already-distributed sheets without manual per-sheet
re-attachment ceremony. Apps Script's library system gives us a single
update surface: this library is published once, every bound shim depends
on it at version `0` (HEAD per D-0041 sub-decision 3), and `clasp push`
to this project propagates immediately to every operator on next click.

## What lives here

- `src/Extractor.gs` — public entrypoint `extractSnapshotForActiveSheet()`
  invoked by the bound shim's menu handler. Implements the procedure pinned
  in `docs/snapshot_adapter_contract.md` §6 (sheet-scoped DeveloperMetadata
  finder + runId-paired tab discovery + per-anchor cardinality validation +
  Snapshot-shape JSON build + browser-download blob).
- `src/SnapshotBuilder.gs` — internal helpers that translate from
  DeveloperMetadata anchor reads to `Snapshot` records per
  `docs/snapshot_contract.md` §5..§12 (locator surfaces, physicalSourceRef,
  raw cell text preservation, dateKey ISO normalization per D-0033).
- `src/CompletenessValidator.gs` — per-anchor cardinality / uniqueness /
  value-coverage checks per `docs/snapshot_adapter_contract.md` §6 step 5
  + D-0043 sub-decision 3.
- `src/DownloadBlob.gs` — `Utilities.newBlob` + `HtmlService` payload that
  serves the JSON as a browser download per
  `docs/snapshot_adapter_contract.md` §7.
- `src/appsscript.json` — minimal scopes per D-0041 sub-decision 7.

## One-time setup

Done once per environment per `docs/snapshot_adapter_contract.md` §3:

1. Create a new standalone Apps Script project in Drive (Drive →
   New → More → Google Apps Script). Record the script project ID.
2. Set Drive sharing on the library to **Anyone with link → Editor** (per
   D-0041 sub-decision 6 + FW-0025 trade-off; required for HEAD-mode
   library access by operator runtime users).
3. From the repo: `cd apps_script/m1_extractor_library/ && clasp clone <library-script-project-ID>` to wire this directory.
4. Replace the auto-cloned `appsscript.json` with the one in this repo.
5. `clasp push` to upload.
6. Update `apps_script/m1_template_bound_script/src/appsscript.json` to
   replace the `libraryId` placeholder with this library's script ID, then
   `clasp push` the bound shim.

## Updating

Just `clasp push` after editing the library code. Updates propagate to every
operator's next menu click via HEAD-mode library loading. No bound-shim
re-deploy needed for library-only changes.

If a fix changes the bound shim's API surface (new function signature, new
menu item, new trigger declaration), the bound shim ALSO needs a `clasp push`
— but already-distributed operator sheets won't pick up bound-shim changes
until they regenerate via the launcher.

## API surface (called by the bound shim)

- `RMLib.extractSnapshotForActiveSheet()` → `HtmlService` output that the
  bound shim can hand to `SpreadsheetApp.getUi().showModalDialog(...)`.
  Triggers a browser download of the snapshot JSON file.

Future entrypoints (not in M2 C9 scope) will be declared here when needed:

- `RMLib.handleCallPointEdit(e)` — FW-0024 onEdit logic, called from the
  bound shim's `onEdit(e)` trigger.
