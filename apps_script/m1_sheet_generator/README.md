# M1 Sheet Generator (Apps Script)

This folder owns the M1 Apps Script generator core for the ICU/HD empty
request-sheet shell. It is the only Apps Script project in the repo and is
scoped to the sheet-facing generation slice. Compute-heavy core logic —
parsing, normalization, solving — does **not** live here; it belongs outside
Apps Script.

## What this project does today

- Generates a first-release **ICU/HD empty request-sheet shell** driven by
  the committed runtime template artifact (`src/TemplateArtifact.gs`).
- Supports both output modes from
  `docs/sheet_generation_contract.md`:
  - create into a **new spreadsheet file**, or
  - create as a **new tab in an existing spreadsheet** (by ID).
- Emits the required structural surfaces: title/header block, date axis,
  weekday row, grouped doctor sections sized from `doctorCountByGroup`,
  MICU/MHD call-point rows with default values from the 4-case rule,
  lower roster/output shell assignment rows, and a legend/Descriptions block.
- Highlights weekends and Singapore public holidays across date-keyed columns.
- Applies **whole-sheet protection** restricted to the script owner, with
  unprotected exceptions only for operator-editable ranges: doctor-name
  cells, request-entry cells, call-point cells, and lower-shell assignment
  cells.
- Applies **warning-only** regex data validation to request-entry cells. The
  parser remains authoritative for request interpretation.

## What this project does not do yet

- No Google Form intake and no final launcher UX (menu, sidebar, add-on).
  `Menu.gs` is intentionally a no-op. Public entrypoints are invoked directly
  during development.
- No parser, normalizer, solver, scorer, writeback, or orchestration code.
  Those remain outside Apps Script.

## Public entrypoints (in `src/GenerateSheet.gs`)

Both entrypoints take a single `config` object:

```js
{
  department: 'CGH ICU/HD Call',          // optional; defaults to ICU/HD
  periodStartDate: '2026-04-06',          // YYYY-MM-DD, required
  periodEndDate:   '2026-04-30',          // YYYY-MM-DD, required
  doctorCountByGroup: {                   // required, non-negative integers
    ICU_ONLY: 4,
    ICU_HD:   5,
    HD_ONLY:  3,
  },
  spreadsheetId: '…'                      // required only for existing-mode
}
```

- `generateIntoNewSpreadsheet(config)` creates a fresh spreadsheet named
  `CGH ICU/HD Roster <start> - <end>` (ISO dates) and a tab named
  `vMMDDHHMMSS` (script-timezone timestamp).
- `generateIntoExistingSpreadsheet(config)` opens the spreadsheet by ID and
  adds a tab named `vMMDDHHMMSS`. If that exact tab name already exists the
  call throws loudly and does not modify the target.

Both entrypoints return `{ spreadsheetId, spreadsheetUrl, spreadsheetName,
sheetName, periodStartDate, periodEndDate, doctorCountByGroup, mode }`.

## Layout

```
apps_script/m1_sheet_generator/
├── .clasp.json                 # local-only, gitignored; points at the real Apps Script project
├── .clasp.json.example         # committed template
├── README.md
└── src/
    ├── appsscript.json
    ├── Menu.gs                 # no-op; launcher UX deferred
    ├── GenerateSheet.gs        # public entrypoints + config validation
    ├── Layout.gs               # structural sheet builder
    ├── DatesAndHolidays.gs     # date-range expansion, SG holiday map, call-point rule
    ├── ProtectionAndValidation.gs  # whole-sheet protection + warning-only validation
    ├── TemplateData.gs         # department → artifact resolver
    └── TemplateArtifact.gs     # committed first-release ICU/HD runtime artifact
```

## Apps Script project link

The real `.clasp.json` in this folder is intentionally **gitignored** so the
script ID stays out of shared history. To set up locally, copy the example:

```
cp .clasp.json.example .clasp.json
# then paste your scriptId
```

## Using clasp

Install once:

```
npm install -g @google/clasp
clasp login
```

Then from this folder:

```
cd apps_script/m1_sheet_generator
clasp status
clasp push
clasp open
```

`clasp push` uploads everything under `src/` to the Apps Script project.
`clasp open` opens the project in the Apps Script web editor, where you can
run either public entrypoint against a test `config` object.

## API executable / `clasp run`

The helpers in this project (including those in `src/DebugSmokeTest.gs`) can
be invoked remotely with `clasp run` instead of from the Apps Script editor.
`clasp run` is not a single-switch feature — several independent prerequisites
all have to be satisfied in the operator's local environment, and missing any
one of them typically surfaces as the same opaque API error:
`Script function not found. Please make sure script is deployed as API executable.`

Full prerequisite list:

1. Link the Apps Script project to a **user-managed Google Cloud Platform
   project**. By default Apps Script uses a hidden Google-managed project
   that does not expose API access.
2. Enable the **Apps Script API** for your account:
   https://script.google.com/home/usersettings
3. Add an `executionApi` block to the Apps Script manifest
   (`src/appsscript.json`), for example:

        "executionApi": {
          "access": "MYSELF"
        }

   Without this block the Apps Script API refuses to invoke any function,
   even after deployment. The manifest in this repo does **not** ship with
   this block; each operator adds it locally with the access level that
   matches their setup.
4. Create an **API Executable** deployment in the Apps Script editor
   (*Deploy → New deployment → API Executable*), or `clasp deploy`.
   Re-deploy whenever the manifest or public surface changes.
5. In the GCP project from step 1, configure the **OAuth consent screen**
   so every scope listed in the manifest's `oauthScopes` is added to the
   consent screen's Data Access allowlist. For this project that includes
   at minimum `https://www.googleapis.com/auth/spreadsheets` and
   `https://www.googleapis.com/auth/userinfo.email`. A scope that is
   declared in the manifest but missing here will surface as
   `You do not have permission to call SpreadsheetApp.openById` (or
   similar) at runtime, not at login.
6. In the same GCP project, create an **OAuth 2.0 Client ID** of type
   *Desktop app* and download the JSON credentials file.
7. Re-authenticate clasp against that GCP project with the
   credentials file **and** the project-scope flags:

        clasp login --creds <path-to-credentials.json> --use-project-scopes --include-clasp-scopes

   Both flags matter. `--creds` swaps clasp off its built-in default OAuth
   client onto the user-managed GCP client (required so clasp is allowed
   to call scripts owned by that project). `--use-project-scopes` makes
   the login request the manifest's declared `oauthScopes`, not just
   clasp's baseline scopes — so the resulting token can actually satisfy
   the runtime permission checks from step 5. `--include-clasp-scopes`
   retains clasp's own management scopes so `clasp push`, `clasp pull`,
   and `clasp deploy` continue to work from the same token.

Once all of the above are in place, public functions become callable from
this folder. Example helpers defined in `src/DebugSmokeTest.gs`:

    clasp run smokeTestGenerateNewSpreadsheet_20260504_20260608
    clasp run smokeTestGenerateIntoExistingSpreadsheet_20260504_20260608
    clasp run smokeTestGenerateMay2026OperatorShell

Live deployment IDs, execution URLs, and operator OAuth client credentials
are **environment-specific operational metadata** and are intentionally
**not** committed to this repo as stable configuration. They belong in each
operator's local environment only.

## Holiday data

`DatesAndHolidays.gs` carries a local Singapore public-holiday map covering
2025 and 2026, both reconciled against the official MOM gazette. Future years
must be added the same way — holiday logic throws explicitly rather than
silently assume unsupported years are non-holidays.

## Scope reminder

Keep this project thin. Anything that isn't "build or update the Sheet"
should live outside Apps Script.
