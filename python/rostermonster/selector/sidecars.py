"""Sidecar artifact writers per `docs/selector_contract.md` §14.

Two artifacts under `FULL` retention:
- `candidates_summary.csv` (§14.1) — one CSV row per candidate with full
  per-component breakdown plus run-level metadata columns,
- `candidates_full.json` (§14.2) — full per-candidate payload (every
  `AssignmentUnit` and full `ScoreResult`) suitable for programmatic
  round-trip.

Both files MUST be byte-identical under identical inputs on a single
implementation on a single platform per §18. The implementation here
uses Python's stdlib `json` and a stable column order to ensure that.

Filesystem placement is execution-layer-owned per §14.3 — the writers
take a target directory and emit the two files inside it under stable
names (`candidates_summary.csv`, `candidates_full.json`). The selector
returns the resolved paths on `AllocationResult.candidatesSummaryPath` /
`candidatesFullPath`.
"""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

from rostermonster.scorer import ALL_COMPONENTS
from rostermonster.selector.result import (
    SIDECAR_SCHEMA_VERSION,
    RunEnvelope,
    ScoredTrialCandidate,
)

# Stable file names. The contract leaves directory + naming convention to
# the execution layer (§14.3); the file *names* themselves are part of the
# §14 wording ("emits two sidecar files: candidates_summary.csv and
# candidates_full.json"). Treating the names as fixed is consistent with
# the contract's column-stability rule for downstream tooling.
SUMMARY_FILE_NAME = "candidates_summary.csv"
FULL_FILE_NAME = "candidates_full.json"


def _summary_csv_text(
    scored: tuple[ScoredTrialCandidate, ...],
    runEnvelope: RunEnvelope,
) -> str:
    """Render the §14.1 CSV body as a string. Pulled out so the byte-
    identical determinism rule (§18) is testable without touching the
    filesystem and so file-write callers do not duplicate the layout
    logic."""
    buf = StringIO()
    # `schemaVersion: 1` declared as a top-of-file comment line per §14.1.
    # CSV-RFC-4180 strictly does not support comments, but the §14.1
    # wording says "preferred where the CSV variant in use supports
    # header comments" and explicitly accepts this convention. Downstream
    # parsers in our control skip lines starting with '#'; downstream
    # spreadsheet tools render the comment as one literal cell in row 1
    # and the operator can ignore it.
    buf.write(f"# schemaVersion: {SIDECAR_SCHEMA_VERSION}\n")
    writer = csv.writer(buf, lineterminator="\n")
    header = [
        "candidateId",
        "totalScore",
        *ALL_COMPONENTS,
        "runId",
        "seed",
        "batchId",
    ]
    writer.writerow(header)
    for stc in scored:
        components = stc.score.components
        row = [
            stc.candidate.candidateId,
            stc.score.totalScore,
            *(components[c] for c in ALL_COMPONENTS),
            runEnvelope.runId,
            runEnvelope.seed,
            # First-release `SEEDED_RANDOM_BLIND` does not surface batches
            # per `docs/solver_contract.md` §18.2; the §14.1 rule says
            # `batchId` MUST be the empty string in that case (header
            # shape is invariant across runs under schemaVersion 1).
            "",
        ]
        writer.writerow(row)
    return buf.getvalue()


def _full_json_text(
    scored: tuple[ScoredTrialCandidate, ...],
    runEnvelope: RunEnvelope,
) -> str:
    """Render the §14.2 JSON body as a string. Top-level fields per
    §14.2 (`runId`, `schemaVersion`, `generationTimestamp`); per-candidate
    payload indexed by `candidateId` carrying full `AssignmentUnit[]`
    and full `ScoreResult` (total + components).

    `json.dumps(..., sort_keys=True, indent=2)` gives byte-identical
    output across re-runs on the same platform per §18. Trailing newline
    avoids POSIX-tool off-by-one issues; the byte content is still
    deterministic.
    """
    payload = {
        "schemaVersion": SIDECAR_SCHEMA_VERSION,
        "runId": runEnvelope.runId,
        "generationTimestamp": runEnvelope.generationTimestamp,
        "candidates": [
            {
                "candidateId": stc.candidate.candidateId,
                "assignments": [
                    {
                        "dateKey": u.dateKey,
                        "slotType": u.slotType,
                        "unitIndex": u.unitIndex,
                        "doctorId": u.doctorId,
                    }
                    for u in stc.candidate.assignments
                ],
                "score": {
                    "totalScore": stc.score.totalScore,
                    "direction": stc.score.direction.value,
                    "components": dict(stc.score.components),
                },
            }
            for stc in scored
        ],
    }
    return json.dumps(payload, sort_keys=True, indent=2) + "\n"


def write_sidecars(
    target_dir: Path,
    scored: tuple[ScoredTrialCandidate, ...],
    runEnvelope: RunEnvelope,
) -> tuple[Path, Path]:
    """Write `candidates_summary.csv` + `candidates_full.json` under
    `target_dir`. Returns the resolved paths.

    Caller (typically the public `select()` entry under `FULL` retention)
    is responsible for `target_dir` existing and being writable; the
    selector contract scopes filesystem placement to the execution layer
    (§14.3). Sidecar emission is the only side effect the selector is
    permitted to perform per §18 — no clocks, no env vars, no fs reads.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    summary_path = target_dir / SUMMARY_FILE_NAME
    full_path = target_dir / FULL_FILE_NAME
    summary_path.write_text(
        _summary_csv_text(scored, runEnvelope), encoding="utf-8"
    )
    full_path.write_text(
        _full_json_text(scored, runEnvelope), encoding="utf-8"
    )
    return summary_path, full_path
