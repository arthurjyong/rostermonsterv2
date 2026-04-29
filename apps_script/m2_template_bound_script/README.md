# Roster Monster — Template Bound Script

A thin (~30 line) Apps Script project that lives **container-bound** to the
maintainer-owned template spreadsheet (`[INTERNAL] Roster Monster Template`).
Every launcher-generated operator sheet is created via
`DriveApp.getFileById(TEMPLATE_FILE_ID).makeCopy(...)`, which carries this
bound script along with the copy. The result: every operator sheet has a
native `Roster Monster → Extract Snapshot` menu without any per-sheet
script-attachment ceremony.

Per `docs/decision_log.md` D-0041 + `docs/snapshot_adapter_contract.md` §3.

## Why this exists

The launcher (`apps_script/m1_sheet_generator/`) is a standalone Web App.
Sheets it creates via `SpreadsheetApp.create()` are not container-bound to
the launcher project — simple `onOpen` / `onEdit` triggers declared in the
launcher do not fire on those sheets. That gap is what reverted the FW-0024
attempt in PR #89.

D-0041 resolves it by changing the launcher to copy a maintainer-owned
template spreadsheet that already has a bound script attached (this
project). Each `makeCopy()` carries the bound script with it, so every
generated sheet hits the same `onOpen` and gets the same menu.

## Why so thin

The bound script is frozen in each operator-copy at the moment of
`makeCopy()`. Updates to this code do not propagate to already-distributed
sheets. To keep that staleness inert, the bound shim is delegate-only — it
declares the menu in `onOpen(e)` and forwards each menu action into the
central Apps Script Library
(`apps_script/m2_extractor_library/`), which IS update-propagable via
HEAD-mode library loading per D-0041 sub-decision 3.

If a function needs to be a simple-trigger entrypoint (e.g., FW-0024's
`onEdit(e)`), it MUST be declared here and delegate; Apps Script does not
fire simple triggers on imported library functions.

## One-time setup

Done once per environment per `docs/snapshot_adapter_contract.md` §3:

1. Create `[INTERNAL] Roster Monster Template` spreadsheet in Drive. Record
   the File ID.
2. Inside that spreadsheet: Extensions → Apps Script. This creates the
   container-bound script project. Record the bound script project ID.
3. Set Drive sharing on the template to **Anyone with link → Viewer** (per
   D-0041 sub-decision 6 + FW-0025 trade-off; see those references for the
   pilot-scope risk acceptance).
4. From the repo: `cd apps_script/m2_template_bound_script/ && clasp clone <bound-script-project-ID>` to wire this directory to the bound script project.
5. Replace the auto-cloned `appsscript.json` with the one in this repo (it
   declares the central library as a dependency at version `0` / HEAD).
6. Update the central library's `scriptId` placeholder in `appsscript.json`
   to the actual library project ID (see
   `apps_script/m2_extractor_library/README.md`).
7. `clasp push` to upload.

## Contents

- `src/Menu.gs` — `onOpen(e)` installer + delegating menu handlers.
- `src/appsscript.json` — manifest declaring the central library dependency
  at version `0` (HEAD / always-latest per D-0041 sub-decision 3).

## Updating

Updates to the menu structure or trigger entrypoints land via this project's
own `clasp push`. They DO NOT reach already-distributed operator sheets — by
design, since the shim is thin and the actual logic lives in the library.
Operators who need menu-structure changes must regenerate via the launcher.

If pilot scope expands such that this rough edge becomes operationally
painful, revisit per FW-0025.
