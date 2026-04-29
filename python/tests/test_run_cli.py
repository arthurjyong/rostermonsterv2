"""Tests for the production CLI shim per `docs/snapshot_adapter_contract.md` §11.

The CLI is the consumer-side counterpart to the Apps Script extractor: it
reads a Snapshot-shape JSON file from disk and runs the full M2 compute
pipeline. These tests exercise the CLI end-to-end against the committed
ICU/HD May 2026 fixture, validating happy-path success + a few defensive
error paths.

Standalone runnable via `python3 python/tests/test_run_cli.py`.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rostermonster.run import (  # noqa: E402
    _snapshot_from_dict,
    _to_jsonable,
    main,
)
from rostermonster.selector import (  # noqa: E402
    FULL_FILE_NAME,
    SUMMARY_FILE_NAME,
)
from rostermonster.snapshot import Snapshot  # noqa: E402

_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "data" / "icu_hd_may_2026_snapshot.json"
)


def test_cli_runs_end_to_end_on_real_fixture() -> None:
    """Happy-path: real ICU/HD May 2026 snapshot → parser CONSUMABLE →
    solver candidates → scorer → selector → AllocationResult written
    to output file. Exit code 0."""
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "result.json"
        rc = main([
            "--snapshot", str(_FIXTURE_PATH),
            "--output", str(out_path),
            "--max-candidates", "3",
            "--seed", "20260504",
        ])
        assert rc == 0, f"CLI exited non-zero on happy path; rc={rc}"
        assert out_path.is_file(), "CLI did not write output file"
        envelope = json.loads(out_path.read_text())
        assert "result" in envelope
        assert "runEnvelope" in envelope
        # AllocationResult shape: winnerAssignment + winnerScore present.
        assert "winnerAssignment" in envelope["result"]
        assert "winnerScore" in envelope["result"]
        # All 116 assignments filled per the M2 May 2026 smoke test profile
        # (29 days × 4 slot types).
        assert len(envelope["result"]["winnerAssignment"]) == 116


def test_cli_full_retention_emits_sidecars() -> None:
    """`--retention FULL` writes both sidecar files (candidates_summary.csv
    + candidates_full.json) alongside the result envelope per
    `docs/selector_contract.md` §13 / §14. Verifies the files exist with
    non-trivial content and that two consecutive re-runs produce byte-
    identical sidecars (selector §18 byte-identical determinism, here
    extended to FULL-mode artifacts)."""
    with tempfile.TemporaryDirectory() as td:
        runs = []
        for label in ("first", "second"):
            out_path = Path(td) / f"{label}.json"
            sidecar_dir = Path(td) / f"{label}.sidecars"
            rc = main([
                "--snapshot", str(_FIXTURE_PATH),
                "--output", str(out_path),
                "--retention", "FULL",
                "--sidecar-dir", str(sidecar_dir),
                "--max-candidates", "3",
                "--seed", "20260504",
            ])
            assert rc == 0, f"CLI exited non-zero on FULL retention; rc={rc}"
            assert out_path.is_file()
            csv_path = sidecar_dir / SUMMARY_FILE_NAME
            full_path = sidecar_dir / FULL_FILE_NAME
            assert csv_path.is_file(), f"sidecar CSV not written: {csv_path}"
            assert full_path.is_file(), f"sidecar JSON not written: {full_path}"

            # Quick shape sanity: CSV has at least header + 3 data rows;
            # JSON has 3 candidates each carrying a non-empty assignments list.
            csv_lines = csv_path.read_text().splitlines()
            assert len(csv_lines) >= 4, "expected schema-version + header + 3 data rows"
            full_payload = json.loads(full_path.read_text())
            assert len(full_payload["candidates"]) == 3
            for cand in full_payload["candidates"]:
                assert cand["assignments"], "FULL sidecar candidate missing assignments"
            runs.append((out_path, csv_path, full_path))

        # Byte-identical determinism per selector §18, extended across the
        # FULL-mode sidecar artifacts. The result envelope itself differs
        # legitimately across re-runs because `result.candidatesSummaryPath`
        # / `result.candidatesFullPath` reflect the test's chosen sidecar
        # dirs (different per run by design); we compare only the sidecar
        # contents which are determined purely by snapshot + seed + config.
        _, csv1, full1 = runs[0]
        _, csv2, full2 = runs[1]
        assert csv1.read_text() == csv2.read_text(), \
            "candidates_summary.csv drifted across re-run"
        assert full1.read_text() == full2.read_text(), \
            "candidates_full.json drifted across re-run"


def test_cli_byte_identical_re_runs() -> None:
    """Re-running with the same seed produces byte-identical output per
    `docs/selector_contract.md` §18 + the M2 C5 smoke determinism guarantee."""
    with tempfile.TemporaryDirectory() as td:
        out1 = Path(td) / "first.json"
        out2 = Path(td) / "second.json"
        for path in (out1, out2):
            rc = main([
                "--snapshot", str(_FIXTURE_PATH),
                "--output", str(path),
                "--max-candidates", "3",
                "--seed", "20260504",
            ])
            assert rc == 0
        assert out1.read_text() == out2.read_text(), (
            "CLI re-run produced different output bytes — determinism "
            "guarantee broken"
        )


def test_cli_missing_snapshot_returns_2() -> None:
    """Missing input file → exit code 2 (CLI usage error per §11)."""
    rc = main([
        "--snapshot", "/nonexistent/path/snapshot.json",
        "--output", "/tmp/should-not-be-written.json",
    ])
    assert rc == 2


def test_snapshot_from_dict_round_trips() -> None:
    """Loading the fixture via `_snapshot_from_dict` produces a valid
    `Snapshot` whose top-level shape matches the dataclass contract."""
    raw = json.loads(_FIXTURE_PATH.read_text())
    snapshot = _snapshot_from_dict(raw)
    assert isinstance(snapshot, Snapshot)
    # Sanity: counts agree with the fixture's metadata.
    md = raw["metadata"]
    assert len(snapshot.doctorRecords) == md["extractionSummary"]["doctorRecordCount"]
    assert len(snapshot.dayRecords) == md["extractionSummary"]["dayRecordCount"]
    assert len(snapshot.requestRecords) == md["extractionSummary"]["requestRecordCount"]


def test_to_jsonable_handles_dataclasses_tuples_enums() -> None:
    """`_to_jsonable` is the JSON-serialization helper the CLI uses for
    the FinalResultEnvelope. Validates a few representative shapes."""
    from dataclasses import dataclass
    from enum import Enum

    class Color(Enum):
        RED = "red"
        BLUE = "blue"

    @dataclass(frozen=True)
    class Inner:
        value: int

    @dataclass(frozen=True)
    class Outer:
        items: tuple
        color: Color
        nested: Inner

    obj = Outer(
        items=(Inner(1), Inner(2)),
        color=Color.RED,
        nested=Inner(99),
    )
    result = _to_jsonable(obj)
    assert result == {
        "items": [{"value": 1}, {"value": 2}],
        "color": "RED",
        "nested": {"value": 99},
    }


# Minimal pytest-equivalent runner for standalone invocation.
def _run() -> int:
    tests = [
        ("test_cli_runs_end_to_end_on_real_fixture",
         test_cli_runs_end_to_end_on_real_fixture),
        ("test_cli_full_retention_emits_sidecars",
         test_cli_full_retention_emits_sidecars),
        ("test_cli_byte_identical_re_runs", test_cli_byte_identical_re_runs),
        ("test_cli_missing_snapshot_returns_2",
         test_cli_missing_snapshot_returns_2),
        ("test_snapshot_from_dict_round_trips",
         test_snapshot_from_dict_round_trips),
        ("test_to_jsonable_handles_dataclasses_tuples_enums",
         test_to_jsonable_handles_dataclasses_tuples_enums),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(_run())
