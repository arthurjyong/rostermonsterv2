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
            "--writeback-ready", "false",
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


def test_cli_writeback_ready_emits_wrapper_envelope() -> None:
    """Default `--writeback-ready=true` mode (M3 C1+) emits the writeback
    wrapper envelope per `docs/decision_log.md` D-0045 + D-0047 — a single
    JSON file with `finalResultEnvelope` + `snapshot` (subset) +
    `doctorIdMap` at top level. This is what the operator uploads to the
    launcher's writeback form. Verifies the wrapper shape is correct,
    embedded `finalResultEnvelope` matches what `--writeback-ready=false`
    would have emitted, and re-runs are byte-identical."""
    with tempfile.TemporaryDirectory() as td:
        wrapper_path = Path(td) / "wrapper.json"
        bare_path = Path(td) / "bare.json"

        # Default mode: writeback-ready=true → wrapper.
        rc = main([
            "--snapshot", str(_FIXTURE_PATH),
            "--output", str(wrapper_path),
            "--max-candidates", "3",
            "--seed", "20260504",
        ])
        assert rc == 0, f"CLI exited non-zero on writeback-ready run; rc={rc}"

        # Comparison run: writeback-ready=false → bare FinalResultEnvelope.
        rc2 = main([
            "--snapshot", str(_FIXTURE_PATH),
            "--output", str(bare_path),
            "--max-candidates", "3",
            "--seed", "20260504",
            "--writeback-ready", "false",
        ])
        assert rc2 == 0

        wrapper = json.loads(wrapper_path.read_text())
        bare = json.loads(bare_path.read_text())

        # Wrapper-shape contract per D-0045: top-level keys are
        # `schemaVersion`, `finalResultEnvelope`, `snapshot`, `doctorIdMap`.
        assert wrapper["schemaVersion"] == 1
        assert "finalResultEnvelope" in wrapper
        assert "snapshot" in wrapper
        assert "doctorIdMap" in wrapper

        # Embedded FinalResultEnvelope matches the bare-mode output exactly.
        # This proves writeback-ready=true is purely additive — it doesn't
        # mutate the selector's output, just wraps it.
        assert wrapper["finalResultEnvelope"] == bare

        # Snapshot subset shape sanity per D-0045 sub-decision 3 +
        # writeback contract §9 (6 required categories).
        snap = wrapper["snapshot"]
        assert "columnADoctorNames" in snap
        assert "requestCells" in snap
        assert "callPointCells" in snap
        assert "prefilledFixedAssignmentCells" in snap
        assert "outputAssignmentRows" in snap
        assert "shellParameters" in snap

        # outputAssignmentRows is the lower-shell row order from the
        # template's outputMapping per writeback §9 6th category.
        # Required so the writeback library can place prefilled cells
        # at their (surfaceId, rowOffset) source-tab coordinates per
        # writeback §10.1.
        rows = snap["outputAssignmentRows"]
        assert isinstance(rows, list) and len(rows) > 0, \
            "outputAssignmentRows must be a non-empty list"
        for entry in rows:
            assert set(entry.keys()) >= {"surfaceId", "slotType", "rowOffset"}

        # Shell parameters carry the writeback contract §9 item 2 fields.
        params = snap["shellParameters"]
        assert "department" in params
        assert "periodStartDate" in params
        assert "periodEndDate" in params
        assert "doctorCountByGroup" in params

        # ICU/HD May 2026 fixture should produce 22 column-A entries
        # (9 + 6 + 7) matching the doctor count.
        assert len(snap["columnADoctorNames"]) == 22

        # doctorIdMap shape per D-0045 sub-decision 4 + writeback §9 item 3.
        for entry in wrapper["doctorIdMap"]:
            assert set(entry.keys()) >= {"doctorId", "sectionGroup", "rowIndex"}
        assert len(wrapper["doctorIdMap"]) == 22

        # Byte-identical determinism: re-run with same flags → identical wrapper.
        wrapper2_path = Path(td) / "wrapper2.json"
        rc3 = main([
            "--snapshot", str(_FIXTURE_PATH),
            "--output", str(wrapper2_path),
            "--max-candidates", "3",
            "--seed", "20260504",
        ])
        assert rc3 == 0
        assert wrapper_path.read_text() == wrapper2_path.read_text(), \
            "wrapper envelope drifted across writeback-ready re-run"


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


def test_cli_default_strategy_records_seeded_random_blind() -> None:
    """Per `docs/selector_contract.md` §16.5 producer obligation: every
    post-M6 C3 Task 1 producer MUST populate `solverStrategy` +
    `solverStrategyConfig` together. Default CLI mode (no --strategy) runs
    SEEDED_RANDOM_BLIND and the envelope MUST reflect that — operators
    looking at archived envelopes need to be able to tell which strategy
    ran without parsing per-batch diagnostics.
    """
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "result.json"
        rc = main([
            "--snapshot", str(_FIXTURE_PATH),
            "--output", str(out_path),
            "--max-candidates", "3",
            "--seed", "20260504",
            "--writeback-ready", "false",
        ])
        assert rc == 0
        envelope = json.loads(out_path.read_text())
        run_env = envelope["runEnvelope"]
        assert run_env["solverStrategy"] == "SEEDED_RANDOM_BLIND", (
            f"default --strategy should record SEEDED_RANDOM_BLIND on "
            f"runEnvelope.solverStrategy; got {run_env['solverStrategy']!r}"
        )
        # SEEDED_RANDOM_BLIND variant has no payload beyond the discriminator.
        assert run_env["solverStrategyConfig"] == {"strategy": "SEEDED_RANDOM_BLIND"}, (
            f"SEEDED_RANDOM_BLIND solverStrategyConfig should be the bare "
            f"discriminator; got {run_env['solverStrategyConfig']}"
        )


def test_cli_lahc_strategy_records_default_lahc_params() -> None:
    """`--strategy LAHC` without --lahc-* overrides records the §12A.5
    defaults (L=1000, idleThreshold=5000, maxIters=100k) in the envelope.
    Tighter test budget here (--max-candidates 1) keeps runtime <10s on
    the 22-doctor fixture even at LAHC's default 100k maxIters per
    trajectory."""
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "result.json"
        rc = main([
            "--snapshot", str(_FIXTURE_PATH),
            "--output", str(out_path),
            "--max-candidates", "1",
            "--seed", "20260504",
            "--strategy", "LAHC",
            "--lahc-iter-cap", "200",  # tight cap so the test finishes fast
            "--lahc-idle-threshold", "100",
            "--writeback-ready", "false",
        ])
        assert rc == 0, f"--strategy LAHC failed; rc={rc}"
        envelope = json.loads(out_path.read_text())
        run_env = envelope["runEnvelope"]
        assert run_env["solverStrategy"] == "LAHC"
        cfg = run_env["solverStrategyConfig"]
        assert cfg["strategy"] == "LAHC"
        # Verify the actual override values are recorded — this is the
        # provenance role: operator can replay the run by passing the
        # recorded params back, and analyzer can distinguish default-vs-
        # tuned runs per §16.5.
        assert cfg["lahcParams"]["maxIters"] == 200
        assert cfg["lahcParams"]["idleThreshold"] == 100
        # historyListLength left at default — verify it picked up §12A.5's
        # default of 1000.
        assert cfg["lahcParams"]["historyListLength"] == 1000


def test_cli_lahc_flags_without_lahc_strategy_fails_loud() -> None:
    """Setting --lahc-* knobs without --strategy LAHC almost always means
    the operator forgot the --strategy flag and would silently get
    SEEDED_RANDOM_BLIND with their tuning ignored. Fail loud at the CLI
    boundary rather than silently dropping the params."""
    rc = main([
        "--snapshot", str(_FIXTURE_PATH),
        "--output", "/tmp/should-not-be-written.json",
        "--lahc-history-length", "500",
        # Note: NOT passing --strategy LAHC — defaults to SEEDED_RANDOM_BLIND.
    ])
    assert rc == 2, (
        f"CLI should reject --lahc-* without --strategy LAHC; got rc={rc}"
    )


def test_cli_lahc_zero_override_fails_loud(capsys=None) -> None:
    """Codex P2 round-1 on PR #130: `--lahc-iter-cap 0` (or any explicit
    zero on a --lahc-* knob) used to silently fall back to the §12A.5
    default because the CLI used `args.x or default` (which treats `0`
    as falsy). Round-1 fix: use `is not None` so explicit zero reaches
    `LahcParams.__post_init__` which rejects non-positive values per
    §12A.5.

    Codex P2 round-2 follow-on: ValueError tracebacks aren't the
    documented CLI behavior — invalid CLI knobs should print to stderr
    and exit 2 (the usage-error path), matching the
    --lahc-*-without-LAHC branch. Round-2 fix: wrap LahcParams() in
    try/except, print message + return 2.
    """
    rc = main([
        "--snapshot", str(_FIXTURE_PATH),
        "--output", "/tmp/should-not-be-written.json",
        "--strategy", "LAHC",
        "--lahc-iter-cap", "0",  # invalid per §12A.5 (must be positive)
    ])
    assert rc == 2, (
        f"--lahc-iter-cap 0 should exit with CLI usage code 2; got rc={rc}"
    )


def test_cli_lahc_byte_identical_re_runs() -> None:
    """LAHC determinism per `docs/solver_contract.md` §12A.4: same args
    + same fixture → byte-identical CLI output. Mirrors
    test_cli_byte_identical_re_runs but for the LAHC strategy."""
    with tempfile.TemporaryDirectory() as td:
        first_path = Path(td) / "first.json"
        second_path = Path(td) / "second.json"
        common = [
            "--snapshot", str(_FIXTURE_PATH),
            "--max-candidates", "1",
            "--seed", "20260504",
            "--strategy", "LAHC",
            "--lahc-iter-cap", "100",
            "--lahc-idle-threshold", "50",
            "--writeback-ready", "false",
        ]
        rc1 = main(common + ["--output", str(first_path)])
        rc2 = main(common + ["--output", str(second_path)])
        assert rc1 == 0 and rc2 == 0
        assert first_path.read_text() == second_path.read_text(), (
            "LAHC CLI runs with identical args must produce byte-identical "
            "output per §12A.4"
        )


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
        ("test_cli_writeback_ready_emits_wrapper_envelope",
         test_cli_writeback_ready_emits_wrapper_envelope),
        ("test_cli_full_retention_emits_sidecars",
         test_cli_full_retention_emits_sidecars),
        ("test_cli_byte_identical_re_runs", test_cli_byte_identical_re_runs),
        ("test_cli_missing_snapshot_returns_2",
         test_cli_missing_snapshot_returns_2),
        ("test_cli_default_strategy_records_seeded_random_blind",
         test_cli_default_strategy_records_seeded_random_blind),
        ("test_cli_lahc_strategy_records_default_lahc_params",
         test_cli_lahc_strategy_records_default_lahc_params),
        ("test_cli_lahc_flags_without_lahc_strategy_fails_loud",
         test_cli_lahc_flags_without_lahc_strategy_fails_loud),
        ("test_cli_lahc_zero_override_fails_loud",
         test_cli_lahc_zero_override_fails_loud),
        ("test_cli_lahc_byte_identical_re_runs",
         test_cli_lahc_byte_identical_re_runs),
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
