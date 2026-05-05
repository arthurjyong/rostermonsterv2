"""Analyzer CLI shim per `docs/analysis_contract.md` §16.

Reads three input files (full Snapshot JSON + wrapper envelope JSON +
`candidates_full.json`), runs `analyze(...)`, writes one
`AnalyzerOutput` JSON file. Pure I/O + argparse around the
`rostermonster.analysis.analyze` core function.

Usage::

    python -m rostermonster.analysis \\
        --snapshot path/to/snapshot.json \\
        --envelope path/to/final_envelope.json \\
        --full-sidecar path/to/candidates_full.json \\
        --output path/to/analyzer_output.json

Optional flags:

    --top-k N            Top-K to surface (default 5; bounds [1, 20]
                         per `docs/decision_log.md` D-0056).
    --generated-at TS    ISO-8601 timestamp echoed into
                         `AnalyzerOutput.generatedAt` per §10. When
                         omitted the CLI fills in `datetime.now(
                         tz=timezone.utc).isoformat()` so the analyzer
                         engine itself stays clock-free per §15 — the
                         CLI is the execution-layer surface that
                         supplies the timestamp.

Exit codes:
- 0: success — `AnalyzerOutput` written.
- 1: admission failure — `AnalyzerInputError` raised (out-of-range K,
  retention BEST_ONLY, failure-branch envelope, coherence mismatch,
  doctor-identity drift, etc.). Stderr carries the structured message.
- 2: invalid CLI usage.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from rostermonster.analysis import AnalyzerInputError, analyze
from rostermonster.analysis.output import render_analyzer_output_json


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m rostermonster.analysis",
        description=(
            "Analyzer CLI per docs/analysis_contract.md — "
            "read snapshot + envelope + FULL sidecar JSON, "
            "emit AnalyzerOutput JSON."
        ),
    )
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--envelope", required=True, type=Path)
    parser.add_argument("--full-sidecar", required=True, type=Path,
                        dest="full_sidecar")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=5, dest="top_k",
                        help="Top-K to surface (default 5; [1, 20])")
    parser.add_argument("--generated-at", type=str, default=None,
                        dest="generated_at",
                        help=(
                            "ISO-8601 timestamp for AnalyzerOutput."
                            "generatedAt; defaults to current UTC"
                        ))
    return parser.parse_args(argv)


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    try:
        snapshot = _read_json(args.snapshot)
        envelope = _read_json(args.envelope)
        full_sidecar = _read_json(args.full_sidecar)
    except FileNotFoundError as e:
        print(f"error: input file not found: {e.filename}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON in input: {e}", file=sys.stderr)
        return 2

    generated_at = args.generated_at or datetime.now(
        tz=timezone.utc
    ).isoformat()

    try:
        output = analyze(
            snapshot,
            envelope,
            full_sidecar,
            topK=args.top_k,
            generatedAt=generated_at,
        )
    except AnalyzerInputError as e:
        print(f"analyzer rejected input: {e}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_analyzer_output_json(output),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
