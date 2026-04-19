# M1 Sheet Generator (Apps Script)

This folder owns the M1 Apps Script scaffold for sheet-facing generation. It is the
only Apps Script project in the repo and is scoped to building the roster Google
Sheet (layout, headers, validations, protections). Compute-heavy core logic —
parsing, normalization, solving — does **not** live here; it belongs outside
Apps Script.

## Layout

```
apps_script/m1_sheet_generator/
├── .clasp.json            # local-only, gitignored; points at the real Apps Script project
├── .clasp.json.example    # committed template
├── README.md
└── src/
    ├── appsscript.json
    ├── Menu.gs
    ├── GenerateSheet.gs
    ├── Layout.gs
    ├── DatesAndHolidays.gs
    ├── ProtectionAndValidation.gs
    └── TemplateData.gs
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
`clasp open` opens the project in the Apps Script web editor.

## Scope reminder

Keep this project thin. Anything that isn't "build or update the Sheet" should
live outside Apps Script.
