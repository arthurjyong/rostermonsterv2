"""One-shot extractor: ICU/HD May 2026 xlsx → committed JSON snapshot fixture.

This is a **test-only bridge**, NOT the production snapshot adapter. The
production adapter is its own future checkpoint (M3 territory or later);
this script exists solely to derive a stable JSON snapshot fixture from
the dev-copy ICU/HD May 2026 xlsx for the M2 C3 T3 hand-test.

Usage (from repo root):

    ICU_HD_XLSX_PATH="/path/to/[DEV COPY] CGH ICU_HD MO ROSTER MAY_2026.xlsx" \\
        python3 python/tests/extract_icu_hd_may_2026.py

Default path is the dev-copy at `for_claude_code/media/`. The script reads
the xlsx, normalizes Excel serial dates to ISO 8601 per `docs/decision_log.md`
D-0033, and writes `python/tests/data/icu_hd_may_2026_snapshot.json` — a JSON
representation of the `rostermonster.snapshot.Snapshot` shape that the T3
test loads back into a `Snapshot` dataclass.

Run once at fixture-derivation time; the JSON fixture lives in the repo
afterwards. Re-run only if the dev-copy xlsx materially changes.
"""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# Default path is relative to the repo root: <repo>/for_claude_code/media/...
# `for_claude_code/` is gitignored (per .gitignore "Local-only scratch folder
# for Claude Code context"), so the xlsx lives in the user's local checkout
# only. Set ICU_HD_XLSX_PATH to override.
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_XLSX_PATH = (
    _REPO_ROOT / "for_claude_code" / "media"
    / "[DEV COPY] CGH ICU_HD MO ROSTER MAY_2026.xlsx"
)
OUTPUT_PATH = (
    Path(__file__).resolve().parent / "data" / "icu_hd_may_2026_snapshot.json"
)

# Section detection — visible header text → logical sectionKey aligned to the
# template artifact's `inputSheetSections`. The template artifact is the
# authority on sectionKeys; this mapping translates the operator-facing
# header text the dev-copy carries into the matching logical key.
SECTION_HEADER_MAP = {
    "MICU  (ICU_ONLY)": "MICU",
    "ICU + HD  (ICU_HD)": "MICU_HD",
    "MHD  (HD_ONLY)": "MHD",
}

# Sheet1 is "LATEST PER XPSEAN" in this workbook.
SHEET_PATH = "xl/worksheets/sheet1.xml"


def _excel_serial_to_iso(serial: float) -> str:
    """Convert Excel serial date (with the standard 1900-leap-year quirk) to
    ISO 8601 (YYYY-MM-DD) per D-0033."""
    epoch = datetime(1899, 12, 30)
    return (epoch + timedelta(days=int(serial))).strftime("%Y-%m-%d")


def _cell_value(cell, shared: list[str]) -> str:
    t = cell.get("t")
    v = cell.find("s:v", NS)
    if v is None:
        inline = cell.find("s:is", NS)
        if inline is not None:
            return "".join(
                x.text or ""
                for x in inline.iter(
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
                )
            )
        return ""
    if t == "s":
        return shared[int(v.text)]
    return v.text or ""


def _column_letter(ref: str) -> str:
    """`"B12"` → `"B"`; `"AC4"` → `"AC"`."""
    return "".join(ch for ch in ref if ch.isalpha())


def _row_index(ref: str) -> int:
    """`"B12"` → 12."""
    return int("".join(ch for ch in ref if ch.isdigit()))


def _column_index(letter: str) -> int:
    """`"A"` → 0, `"B"` → 1, …, `"Z"` → 25, `"AA"` → 26, …"""
    n = 0
    for ch in letter:
        n = n * 26 + (ord(ch.upper()) - ord("A") + 1)
    return n - 1


def extract(xlsx_path: Path) -> dict:
    """Read the xlsx and return a Snapshot-shaped dict."""
    with zipfile.ZipFile(xlsx_path) as z:
        with z.open("xl/sharedStrings.xml") as f:
            ss_root = ET.parse(f).getroot()
        shared = [
            "".join(
                t.text or ""
                for t in si.iter(
                    "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
                )
            )
            for si in ss_root.findall("s:si", NS)
        ]

        with z.open(SHEET_PATH) as f:
            sheet_root = ET.parse(f).getroot()

    # Index every cell as (rowIndex, columnIndex) → value.
    rows = sheet_root.findall("s:sheetData/s:row", NS)
    cells: dict[tuple[int, str], str] = {}
    for row in rows:
        r_idx = int(row.get("r"))
        for c in row.findall("s:c", NS):
            ref = c.get("r")
            col = _column_letter(ref)
            val = _cell_value(c, shared)
            cells[(r_idx, col)] = val

    # Day axis lives on row 2 starting at column B.
    row2 = sorted(
        ((col, val) for (r, col), val in cells.items() if r == 2 and col != "A"),
        key=lambda kv: _column_index(kv[0]),
    )
    day_records = []
    column_to_day_index: dict[str, int] = {}
    for day_index, (col, raw) in enumerate(row2):
        try:
            iso = _excel_serial_to_iso(float(raw))
        except (TypeError, ValueError):
            iso = (raw or "").strip()
        day_records.append(
            {
                "dayIndex": day_index,
                "rawDateText": iso,
                "sourceLocator": {
                    "surfaceKey": "dayAxis",
                    "dayIndex": day_index,
                },
                "physicalSourceRef": {
                    "sheetName": "LATEST PER XPSEAN",
                    "sheetGid": "0",
                    "a1Refs": [f"{col}2"],
                },
            }
        )
        column_to_day_index[col] = day_index

    # Walk down column A row-by-row to find section headers and doctors.
    max_row = max(r for (r, _) in cells.keys())
    doctor_records: list[dict] = []
    current_section_key: str | None = None
    current_section_raw_header: str | None = None
    doctor_index_in_section = 0
    for r in range(4, max_row + 1):
        a_val = (cells.get((r, "A"), "") or "").strip()
        if a_val in SECTION_HEADER_MAP:
            current_section_key = SECTION_HEADER_MAP[a_val]
            current_section_raw_header = a_val
            doctor_index_in_section = 0
            continue
        # Stop when we hit the lower-shell / point-rows region — those are
        # not doctor entries. Heuristic: lines starting with these labels
        # mark non-doctor rows.
        if a_val in {
            "MICU Call Point",
            "MHD Call Point",
            "Roster / Assignments",
            "MICU Call",
            "MICU Standby",
            "MHD Call",
            "MHD Standby",
            "Descriptions",
            "Roster Notes / FAQ",
        }:
            current_section_key = None
            current_section_raw_header = None
            continue
        if current_section_key is None or a_val == "":
            continue
        if a_val.startswith(("CR — ", "NC — ", "AL — ", "TL — ", "SL ", "HL —", "NSL —", "OPL —", "EMCC —", "PM_OFF —", "EXAM —")):
            # Legend lines start with "CODE — description"
            continue
        # Treat as a doctor row.
        display_name = a_val
        source_doctor_key = f"{current_section_key.lower()}_dr_{doctor_index_in_section}"
        # snapshot_contract.md §7 — rawSectionText is the raw visible section
        # header text from the sheet (audit/debug only); not the logical
        # sectionKey. The mapped sectionKey rides on sourceLocator.path.
        doctor_records.append(
            {
                "sourceDoctorKey": source_doctor_key,
                "displayName": display_name,
                "rawSectionText": current_section_raw_header or "",
                "sourceLocator": {
                    "surfaceKey": "doctorRows",
                    "sectionKey": current_section_key,
                    "doctorIndexInSection": doctor_index_in_section,
                },
                "physicalSourceRef": {
                    "sheetName": "LATEST PER XPSEAN",
                    "sheetGid": "0",
                    "a1Refs": [f"A{r}"],
                },
            }
        )
        doctor_index_in_section += 1

    # Build a quick (doctorRow, sourceDoctorKey) lookup by re-scanning column A
    # for the doctors we just kept.
    name_to_row: dict[tuple[str, str], int] = {}
    current_section_key = None
    doc_idx = 0
    for r in range(4, max_row + 1):
        a_val = (cells.get((r, "A"), "") or "").strip()
        if a_val in SECTION_HEADER_MAP:
            current_section_key = SECTION_HEADER_MAP[a_val]
            doc_idx = 0
            continue
        if a_val in {
            "MICU Call Point",
            "MHD Call Point",
            "Roster / Assignments",
            "MICU Call",
            "MICU Standby",
            "MHD Call",
            "MHD Standby",
            "Descriptions",
            "Roster Notes / FAQ",
        }:
            current_section_key = None
            continue
        if current_section_key is None or a_val == "":
            continue
        if a_val.startswith(("CR — ", "NC — ", "AL — ", "TL — ", "SL ", "HL —", "NSL —", "OPL —", "EMCC —", "PM_OFF —", "EXAM —")):
            continue
        key = f"{current_section_key.lower()}_dr_{doc_idx}"
        name_to_row[(current_section_key, key)] = r
        doc_idx += 1

    # Request records — one per (doctor, day) cell, blank or otherwise per
    # snapshot_contract.md §9 ("blank request cells still emit request records";
    # `rawRequestText` "preserves exact raw cell text (not trimmed or normalized)").
    request_records: list[dict] = []
    for doc in doctor_records:
        section_key = doc["sourceLocator"]["sectionKey"]
        key = doc["sourceDoctorKey"]
        row = name_to_row[(section_key, key)]
        for col, day_index in column_to_day_index.items():
            # Do NOT trim — rawRequestText preserves exact raw cell text.
            cell_val = cells.get((row, col), "") or ""
            request_records.append(
                {
                    "sourceDoctorKey": key,
                    "dayIndex": day_index,
                    "rawRequestText": cell_val,
                    "sourceLocator": {
                        "surfaceKey": "requestCells",
                        "sourceDoctorKey": key,
                        "dayIndex": day_index,
                    },
                    "physicalSourceRef": {
                        "sheetName": "LATEST PER XPSEAN",
                        "sheetGid": "0",
                        "a1Refs": [f"{col}{row}"],
                    },
                }
            )

    # Prefilled assignment records — empty in the May 2026 dev copy
    # (operator has not entered any fixed assignments yet).
    prefilled_records: list[dict] = []

    return {
        "metadata": {
            "snapshotId": "icu_hd_may_2026_devcopy_handtest",
            "templateId": "cgh_icu_hd",
            "templateVersion": 1,
            "sourceSpreadsheetId": "icu_hd_may_2026_devcopy",
            "sourceTabName": "LATEST PER XPSEAN",
            "generationTimestamp": "2026-04-27T00:00:00Z",
            "periodRef": {
                "periodId": "2026-05",
                "periodLabel": "May 2026",
            },
            "extractionSummary": {
                "doctorRecordCount": len(doctor_records),
                "dayRecordCount": len(day_records),
                "requestRecordCount": len(request_records),
                "prefilledAssignmentRecordCount": len(prefilled_records),
            },
        },
        "doctorRecords": doctor_records,
        "dayRecords": day_records,
        "requestRecords": request_records,
        "prefilledAssignmentRecords": prefilled_records,
    }


def main() -> int:
    xlsx_path = Path(os.environ.get("ICU_HD_XLSX_PATH", DEFAULT_XLSX_PATH))
    if not xlsx_path.exists():
        print(
            f"ERROR: xlsx not found at {xlsx_path!r}. Set ICU_HD_XLSX_PATH "
            f"to override the default dev-copy path.",
            file=sys.stderr,
        )
        return 1

    snapshot_dict = extract(xlsx_path)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(snapshot_dict, indent=2) + "\n")
    print(
        f"Wrote {OUTPUT_PATH} — "
        f"{snapshot_dict['metadata']['extractionSummary']['doctorRecordCount']} doctors, "
        f"{snapshot_dict['metadata']['extractionSummary']['dayRecordCount']} days, "
        f"{snapshot_dict['metadata']['extractionSummary']['requestRecordCount']} requests, "
        f"{snapshot_dict['metadata']['extractionSummary']['prefilledAssignmentRecordCount']} prefills."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
