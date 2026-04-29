"""Time the M2 compute pipeline at increasing `--max-candidates` values.

Runs the production CLI shim (`python -m rostermonster.run`) for each iteration
count, captures wall time, and writes a markdown summary to `results.md`.
Skips runs that exceed `_TIMEOUT_SEC` so a runaway 100k-candidate run doesn't
block the maintainer's machine.

Usage:

    PYTHONPATH=python python3 experimental/timing/run_timing_benchmark.py \\
        --snapshot path/to/snapshot.json

Output:
- `experimental/timing/results.md` — markdown table summarising wall time +
  winner score + placement-attempt count for each iteration size.
- `experimental/timing/runs/<N>iters.result.json` — full result envelope per
  run (gitignored).

Reproducibility: same snapshot + same seed + same max-candidates produces
byte-identical output per `docs/selector_contract.md` §18.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

# Counts to time. Inflated counts caught by `_TIMEOUT_SEC` to avoid hanging
# the maintainer's machine. Default ladder: 1 → 100,000 in 10x steps.
_DEFAULT_COUNTS = [1, 10, 100, 1000, 10000, 100000]

# Per-run timeout. 600s == 10 minutes — generous for the 100k case but
# stops a runaway run from blocking the script. Adjust if needed.
_TIMEOUT_SEC = 600

_SEED = 20260504
_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNS_DIR = _REPO_ROOT / "experimental" / "timing" / "runs"
_RESULTS_PATH = _REPO_ROOT / "experimental" / "timing" / "results.md"


def main() -> int:
    p = argparse.ArgumentParser(
        description="Time the M2 compute pipeline at varying iteration counts."
    )
    p.add_argument(
        "--snapshot", required=True,
        help="path to snapshot JSON file (extractor output)",
    )
    p.add_argument(
        "--counts", type=str, default=None,
        help="comma-separated list of iteration counts (default: " +
             ",".join(str(c) for c in _DEFAULT_COUNTS) + ")",
    )
    args = p.parse_args()

    counts = (
        [int(c) for c in args.counts.split(",")] if args.counts
        else _DEFAULT_COUNTS
    )
    snapshot_path = Path(args.snapshot)
    if not snapshot_path.is_file():
        print(f"snapshot not found: {snapshot_path}", file=sys.stderr)
        return 1

    _RUNS_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for n in counts:
        out_path = _RUNS_DIR / f"{n}iters.result.json"
        cmd = [
            sys.executable, "-m", "rostermonster.run",
            "--snapshot", str(snapshot_path),
            "--retention", "BEST_ONLY",
            "--max-candidates", str(n),
            "--seed", str(_SEED),
            "--output", str(out_path),
        ]
        env = {"PYTHONPATH": str(_REPO_ROOT / "python"), "PATH": _path()}
        print(f"\n[{n}] running CLI ...", flush=True)
        t0 = time.perf_counter()
        try:
            res = subprocess.run(
                cmd, env=env, capture_output=True, text=True,
                timeout=_TIMEOUT_SEC,
            )
            elapsed = time.perf_counter() - t0
            if res.returncode != 0:
                print(f"[{n}] non-zero exit ({res.returncode}); stderr: "
                      f"{res.stderr[:300]}")
                rows.append({
                    "n": n, "elapsed_sec": elapsed, "status": "FAILED",
                    "score": None, "placement_attempts": None,
                })
                continue
        except subprocess.TimeoutExpired:
            elapsed = _TIMEOUT_SEC
            print(f"[{n}] TIMEOUT after {_TIMEOUT_SEC}s — skipping rest")
            rows.append({
                "n": n, "elapsed_sec": elapsed, "status": "TIMEOUT",
                "score": None, "placement_attempts": None,
            })
            break

        # Parse the result envelope to get the winner score + diagnostics.
        env_data = json.loads(out_path.read_text())
        result = env_data.get("result", {})
        score = (result.get("winnerScore") or {}).get("totalScore")
        diag = result.get("searchDiagnostics") or {}
        attempts = diag.get("placementAttempts")
        candidates = diag.get("candidateEmitCount", n)
        print(f"[{n}] elapsed={elapsed:.2f}s  candidates={candidates}  "
              f"winnerScore={score}  placementAttempts={attempts}")
        rows.append({
            "n": n, "elapsed_sec": elapsed, "status": "OK",
            "score": score, "placement_attempts": attempts,
            "candidates": candidates,
        })

    # Write markdown summary.
    _write_markdown(rows)
    print(f"\nWrote summary to {_RESULTS_PATH}")
    return 0


def _path() -> str:
    """Pull PATH from the parent shell so subprocess can find python3 / etc."""
    import os
    return os.environ.get("PATH", "")


def _write_markdown(rows: list[dict]) -> None:
    lines = [
        "# M2 pipeline timing benchmark",
        "",
        f"**Run on:** {platform.platform()}",
        f"**Python:** {platform.python_version()}",
        f"**Snapshot fixture:** real ICU/HD May 2026 (22 doctors × 29 days × "
        "638 requests)",
        f"**Seed:** {_SEED} (fixed for byte-identical determinism per "
        "`docs/selector_contract.md` §18)",
        f"**Retention:** BEST_ONLY (winner-only; FULL retention has slightly "
        "higher I/O cost from sidecar emission)",
        "",
        "| max-candidates | wall time (s) | winner score | "
        "placement attempts | seconds per candidate |",
        "|--:|--:|--:|--:|--:|",
    ]
    for r in rows:
        n = r["n"]
        elapsed = r["elapsed_sec"]
        if r["status"] != "OK":
            lines.append(f"| {n:,} | — | _{r['status']}_ | — | — |")
            continue
        score = r["score"]
        attempts = r["placement_attempts"]
        per_candidate = elapsed / max(n, 1)
        lines.append(
            f"| {n:,} | {elapsed:.2f} | {score:.3f} | "
            f"{attempts:,} | {per_candidate:.4f} |"
        )

    lines.append("")
    lines.append(
        "_Wall time includes Python startup overhead (~0.5s per invocation). "
        "For pure compute time at very large iteration counts, run the "
        "pipeline directly without subprocess. Per-candidate cost rises "
        "slightly with N because the solver explores deeper into the search "
        "space, hitting more rule-engine rejections per emitted candidate; "
        "look at `searchDiagnostics.placementAttempts` for the underlying "
        "work._"
    )
    _RESULTS_PATH.write_text("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
