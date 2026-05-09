"""Production CLI shim per `docs/snapshot_adapter_contract.md` §11.

Reads a Snapshot-shape JSON file produced by the Apps Script extractor
(per `docs/decision_log.md` D-0040 transport — operator-saved browser
download), runs the full M2 compute pipeline (parser → solver → scorer
→ selector), and writes a `FinalResultEnvelope` JSON file alongside the
input.

Per `docs/decision_log.md` D-0050, the substantive compute logic lives
in `rostermonster.pipeline.run_pipeline()` so the cloud HTTP wrapper
(`rostermonster_service.app`) calls the same code path. This module
is the thin CLI adapter — argparse + file I/O + exit-code dispatch.

Usage::

    python -m rostermonster.run --snapshot path/to/snapshot.json
    python -m rostermonster.run --snapshot path/to/snapshot.json \\
        --output path/to/result.json --seed 12345

Exit codes:
- 0: success — winning candidate selected, FinalResultEnvelope written.
- 1: failure — snapshot did not parse to CONSUMABLE, OR solver returned
  an UnsatisfiedResult (no rule-valid roster found within the search
  budget). The FinalResultEnvelope is still written, carrying the
  failure-branch shape per `docs/selector_contract.md` §10.2.
- 2: invalid CLI usage — missing `--snapshot`, file not readable, etc.

For pilot scope this CLI deliberately keeps surface narrow. Operator
launches it from the terminal, points at the downloaded JSON, gets a
result file. Future work covers richer modes (interactive selection,
multi-template support, sidecar output directory).

Per `docs/decision_log.md` D-0053, the `--seed` flag has NO default
value. When omitted, `pipeline.run_pipeline()` picks a fresh seed
via `random.randint(0, 2**31-1)` and records it in
`runEnvelope.seed`. Operators wanting byte-identical re-runs MUST
pass `--seed N` explicitly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Re-export pipeline helpers for backwards-compat. Existing tests import
# `_snapshot_from_dict`, `_to_jsonable`, etc. from `rostermonster.run`;
# the helpers live in `rostermonster.pipeline` per D-0050 dual-track
# architecture, but the import path is preserved so test churn is zero.
from rostermonster.pipeline import (  # noqa: F401
    _assemble_writeback_wrapper,
    _build_doctor_id_map,
    _build_run_envelope,
    _build_writeback_snapshot_subset,
    _snapshot_from_dict,
    _to_jsonable,
    run_pipeline,
)
from rostermonster.selector import (
    AllocationResult,
    FinalResultEnvelope,
    RetentionMode,
)
from rostermonster.snapshot import Snapshot
from rostermonster.solver import (
    LahcParams,
    STRATEGY_LAHC,
    STRATEGY_SEEDED_RANDOM_BLIND,
)
from rostermonster.templates import icu_hd_template_artifact


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. Returns the process exit code."""
    args = _parse_args(argv)
    snapshot_path = Path(args.snapshot)
    if not snapshot_path.is_file():
        print(f"snapshot file not found: {snapshot_path}", file=sys.stderr)
        return 2

    output_path = (
        Path(args.output) if args.output
        else snapshot_path.with_name(snapshot_path.stem + ".result.json")
    )

    raw = json.loads(snapshot_path.read_text())
    snapshot = _snapshot_from_dict(raw)
    template = icu_hd_template_artifact()

    # Resolve retention + sidecar dir CLI-side. The shared core honors
    # retention_mode + sidecar_dir directly; the directory-creation
    # side effect stays here as a CLI ergonomic.
    retention_mode = RetentionMode[args.retention.upper()]
    sidecar_dir: Path | None = None
    if retention_mode is RetentionMode.FULL:
        sidecar_dir = (Path(args.sidecar_dir) if args.sidecar_dir
                       else output_path.parent / (output_path.stem + ".sidecars"))
        sidecar_dir.mkdir(parents=True, exist_ok=True)

    # Resolve LAHC params from CLI flags (only meaningful when --strategy LAHC
    # is requested; misuse with --strategy SEEDED_RANDOM_BLIND fails loudly
    # in run_pipeline). When --strategy LAHC and no --lahc-* overrides, pass
    # `None` so run_pipeline applies §12A.5 defaults.
    lahc_params: LahcParams | None = None
    if args.strategy == STRATEGY_LAHC:
        lahc_overrides_set = (
            args.lahc_history_length is not None
            or args.lahc_iter_cap is not None
            or args.lahc_idle_threshold is not None
            or args.lahc_swap_probability is not None
        )
        if lahc_overrides_set:
            defaults = LahcParams()
            # Use `is not None` not `or` — `or` treats explicit `0` as
            # falsy and silently falls back to defaults, masking what
            # would be an invalid maintainer tuning. With `is not None`,
            # `--lahc-iter-cap 0` reaches LahcParams.__post_init__ and
            # fails loud with the §12A.5 positive-integer rule.
            try:
                lahc_params = LahcParams(
                    historyListLength=(
                        args.lahc_history_length
                        if args.lahc_history_length is not None
                        else defaults.historyListLength
                    ),
                    idleThreshold=(
                        args.lahc_idle_threshold
                        if args.lahc_idle_threshold is not None
                        else defaults.idleThreshold
                    ),
                    maxIters=(
                        args.lahc_iter_cap
                        if args.lahc_iter_cap is not None
                        else defaults.maxIters
                    ),
                    swapProbability=(
                        args.lahc_swap_probability
                        if args.lahc_swap_probability is not None
                        else defaults.swapProbability
                    ),
                )
            except ValueError as e:
                # LahcParams validates §12A.5 (must be positive integer).
                # Surface the validation error as a CLI usage error
                # (stderr + exit code 2) so the operator gets the same
                # stable CLI behavior as the other --lahc-* misuse paths
                # rather than an unhandled-exception traceback.
                print(f"invalid LAHC parameter: {e}", file=sys.stderr)
                return 2
    elif (
        args.lahc_history_length is not None
        or args.lahc_iter_cap is not None
        or args.lahc_idle_threshold is not None
        or args.lahc_swap_probability is not None
    ):
        # Fail loud: setting LAHC knobs without --strategy LAHC is almost
        # certainly an operator mistake (forgot the flag) — we'd silently
        # ignore them otherwise and the operator would think their tuning
        # took effect.
        print(
            f"--lahc-* flags are only meaningful when --strategy LAHC; "
            f"got --strategy {args.strategy}. Add `--strategy LAHC` or "
            f"drop the --lahc-* flags.",
            file=sys.stderr,
        )
        return 2

    result = run_pipeline(
        snapshot,
        template,
        max_candidates=args.max_candidates,
        seed=args.seed,
        retention_mode=retention_mode,
        sidecar_dir=sidecar_dir,
        strategy_id=args.strategy,
        lahc_params=lahc_params,
    )

    if result.state == "PARSER_NON_CONSUMABLE":
        print(
            f"NON_CONSUMABLE — {len(result.parser_issues)} issue(s):",
            file=sys.stderr,
        )
        for issue in result.parser_issues:
            print(f"  [{issue.severity}] {issue.code}: {issue.message}",
                  file=sys.stderr)
        # Write a minimal failure envelope so the operator workflow has a
        # stable artifact even on failure. Selector failure-branch shape
        # is for SOLVER UnsatisfiedResult; pre-solve admission failure is
        # NOT a selector concern, so we emit a small CLI-specific error
        # JSON instead.
        output_path.write_text(json.dumps({
            "status": "PARSER_NON_CONSUMABLE",
            "snapshotPath": str(snapshot_path),
            "issueCount": len(result.parser_issues),
            "issues": [
                {"severity": i.severity.name if hasattr(i.severity, "name")
                 else str(i.severity),
                 "code": i.code, "message": i.message}
                for i in result.parser_issues
            ],
        }, indent=2))
        print(f"\nWrote diagnostic to {output_path}", file=sys.stderr)
        return 1

    assert result.envelope is not None  # OK + UNSATISFIED both populate
    _write_output(result.envelope, snapshot, template, output_path,
                  writeback_ready=args.writeback_ready)

    if result.state == "OK":
        assert isinstance(result.envelope.result, AllocationResult)
        score_total = result.envelope.result.winnerScore.totalScore
        n_filled = sum(
            1 for a in result.envelope.result.winnerAssignment
            if a.doctorId is not None
        )
        n_total = len(result.envelope.result.winnerAssignment)
        msg = (f"Selected winner across {result.candidate_count} candidates. "
               f"Score: {score_total:.3f}. "
               f"Assignments filled: {n_filled}/{n_total}. "
               f"Seed: {result.resolved_seed}. "
               f"Output: {output_path}")
        if sidecar_dir is not None:
            msg += (f"\nFULL retention sidecars: "
                    f"{result.envelope.result.candidatesSummaryPath} + "
                    f"{result.envelope.result.candidatesFullPath}")
        print(msg)
        return 0

    # UNSATISFIED branch — solver returned no rule-valid roster within
    # the budget, or selector returned a failure-branch envelope.
    print(f"UNSATISFIED — no rule-valid roster found within "
          f"{result.resolved_max_candidates} candidate budget. "
          f"Seed: {result.resolved_seed}. "
          f"Result written to {output_path}", file=sys.stderr)
    return 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m rostermonster.run",
        description=(
            "Run the Roster Monster compute pipeline against an "
            "extractor-produced snapshot JSON file."
        ),
    )
    p.add_argument(
        "--snapshot", required=True,
        help="path to snapshot JSON file (produced by the Apps Script extractor)",
    )
    p.add_argument(
        "--output", default=None,
        help="output path for the FinalResultEnvelope JSON "
             "(default: <snapshot>.result.json alongside the input)",
    )
    p.add_argument(
        "--seed", type=int, default=None,
        help="RNG seed for solver determinism. When omitted, a fresh "
             "seed is picked per invocation per `docs/decision_log.md` "
             "D-0053; the chosen seed is recorded in runEnvelope.seed "
             "so the run can be replayed by passing it back here.",
    )
    p.add_argument(
        "--max-candidates", type=int, default=None,
        help="max number of candidates the solver enumerates "
             "(default 32 — defined in `rostermonster.pipeline`)",
    )
    p.add_argument(
        "--retention", choices=["BEST_ONLY", "FULL"], default="BEST_ONLY",
        help="selector retention mode per `docs/selector_contract.md` §13. "
             "BEST_ONLY (default) keeps only the winner; FULL emits "
             "sidecar files (candidates_summary.csv + candidates_full.json) "
             "with the full ranked candidate set",
    )
    p.add_argument(
        "--sidecar-dir", default=None,
        help="directory for FULL-retention sidecar files (only meaningful "
             "with --retention FULL; defaults to <output>.sidecars/ "
             "alongside the output file)",
    )
    p.add_argument(
        "--strategy",
        choices=[STRATEGY_SEEDED_RANDOM_BLIND, STRATEGY_LAHC],
        default=STRATEGY_SEEDED_RANDOM_BLIND,
        help="solver search strategy per `docs/solver_contract.md` §11.1. "
             "Defaults to SEEDED_RANDOM_BLIND for byte-identical CI / pre-M6 "
             "semantics. Pass --strategy LAHC to opt into Late Acceptance "
             "Hill Climbing (M6 C2 implementation per §12A). The chosen "
             "strategy is recorded on runEnvelope.solverStrategy per "
             "`docs/selector_contract.md` §16.5 so the M5 analyzer + ops "
             "trail can identify the producer.",
    )
    p.add_argument(
        "--lahc-history-length", type=int, default=None,
        help="LAHC history-list length L per `docs/solver_contract.md` "
             "§12A.5 (default 1000). Maintainer-only knob per D-0067 "
             "sub-decision 6 — operator-facing UI changes are out of M6 "
             "scope. Only meaningful with --strategy LAHC.",
    )
    p.add_argument(
        "--lahc-iter-cap", type=int, default=None,
        help="LAHC hard iteration cap (maxIters) per `docs/solver_contract.md` "
             "§12A.5 (default 100,000). Maintainer-only knob. Only meaningful "
             "with --strategy LAHC.",
    )
    p.add_argument(
        "--lahc-idle-threshold", type=int, default=None,
        help="LAHC idle-iter termination threshold per `docs/solver_contract.md` "
             "§12A.5 (default 5000 — the loop terminates after this many "
             "consecutive iterations without improvement). Maintainer-only knob. "
             "Only meaningful with --strategy LAHC.",
    )
    p.add_argument(
        "--lahc-swap-probability", type=float, default=None,
        help="LAHC primary-move-type bias per `docs/solver_contract.md` §12A.7 "
             "(default 0.5 — 50/50 swap-vs-reassign coin flip per iteration; "
             "the un-chosen type still fires as fallback when the primary's "
             "bounded random sampler returns None per §12A.1.a). Must be in "
             "[0.0, 1.0]. swap_p=0.0 → reassign-primary; swap_p=1.0 → "
             "swap-primary. Maintainer-only knob. Only meaningful with "
             "--strategy LAHC.",
    )
    p.add_argument(
        "--writeback-ready",
        type=_parse_bool,
        default=True,
        help="when true (default), the output JSON is the writeback envelope "
             "wrapper per `docs/decision_log.md` D-0045 + D-0047 (single file "
             "containing FinalResultEnvelope + snapshot subset + doctorIdMap, "
             "ready to upload to the launcher's writeback form). When false, "
             "the output is the bare FinalResultEnvelope (pre-M3 C1 behavior, "
             "useful for callers that don't intend to writeback).",
    )
    return p.parse_args(argv)


def _parse_bool(value: str) -> bool:
    """Loose bool parser for the --writeback-ready CLI flag. Accepts
    `true`/`false`/`yes`/`no`/`1`/`0` (case-insensitive)."""
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"true", "yes", "1", "y", "t"}:
        return True
    if s in {"false", "no", "0", "n", "f"}:
        return False
    raise argparse.ArgumentTypeError(
        f"expected a boolean (true/false/yes/no/1/0), got {value!r}"
    )


def _write_output(envelope: FinalResultEnvelope, snapshot: Snapshot,
                  template: Any, output_path: Path, *,
                  writeback_ready: bool) -> None:
    """Serialize the CLI's output JSON to disk. When `writeback_ready` is
    true (the M3 C1+ default per `docs/decision_log.md` D-0047), the output
    is the writeback wrapper envelope per D-0045 (single file containing
    `finalResultEnvelope` + `snapshot` subset + `doctorIdMap`). When false,
    the output is the bare `FinalResultEnvelope` (pre-M3 C1 behavior, kept
    available for callers that don't intend to writeback — for example,
    test harnesses that assert on the selector's exact output shape per
    `docs/selector_contract.md` §10)."""
    if writeback_ready:
        payload = _assemble_writeback_wrapper(envelope, snapshot, template)
    else:
        payload = _to_jsonable(envelope)
    output_path.write_text(json.dumps(payload, indent=2))


if __name__ == "__main__":
    sys.exit(main())
