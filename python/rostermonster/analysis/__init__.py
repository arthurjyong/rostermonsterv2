"""Analysis module per `docs/analysis_contract.md`.

Public entry: `analyze(snapshot, envelope, fullSidecar, *, topK,
generatedAt, analysisConfig=None) → AnalyzerOutput`.

Pure-function reference implementation per §6 + §15. Reads three input
files (full Snapshot JSON + wrapper envelope + `candidates_full.json`),
emits one `AnalyzerOutput` JSON. Solver-agnostic by contract per §12;
parser-overlay reuse for `cumulativeCallPoints` per §10.6 + §17.
"""

from __future__ import annotations

from typing import Any

from rostermonster.analysis.admission import (
    AnalyzerInputError,
    admit,
)
from rostermonster.analysis.aggregates import (
    _slot_kind_map,
    build_assignment_ref,
    build_component_breakdowns,
    build_equity_scalars,
    build_hot_and_locked_days,
    build_pairwise_hamming,
    build_per_doctor_aggregates,
)
from rostermonster.analysis.output import (
    ANALYSIS_CONTRACT_VERSION,
    AnalyzerCandidate,
    AnalyzerOutput,
    AnalyzerSource,
    ComparisonAggregates,
    TopKResult,
)
from rostermonster.analysis.selection import select_top_k
from rostermonster.parser import Consumability, parse
from rostermonster.pipeline import _snapshot_from_dict
from rostermonster.scorer.result import ScoringConfig
from rostermonster.templates import icu_hd_template_artifact

__all__ = [
    "AnalyzerInputError",
    "AnalyzerOutput",
    "analyze",
]


def _resolve_template(snapshot_dict: dict[str, Any]):
    """Look up the template by `snapshot.metadata.templateId` per §10.6.

    `metadata.templateId` is REQUIRED per `docs/analysis_contract.md`
    §9 input #1 — missing-templateId is fail-loud rather than silently
    defaulting to ICU/HD, because parser-overlay call-point resolution
    depends on the template the pipeline used; defaulting here would
    let the analyzer compute against the wrong template's defaults
    when the snapshot is from a future second template.

    First-release ICU/HD-only — `cgh_icu_hd` is the only registered
    template per `docs/decision_log.md` D-0019 / `templates/__init__.py`.
    Future templates extend this lookup.
    """
    md = snapshot_dict.get("metadata") or {}
    template_id = md.get("templateId")
    if not template_id:
        raise AnalyzerInputError(
            "snapshot.metadata.templateId is missing — required per "
            "analysis_contract §9 input #1 so the analyzer's parser-"
            "overlay reuse resolves call-point defaults against the "
            "same template the pipeline used"
        )
    if template_id == "cgh_icu_hd":
        return icu_hd_template_artifact()
    raise AnalyzerInputError(
        f"unknown templateId {template_id!r}; first release supports "
        f"only 'cgh_icu_hd'"
    )


def _resolve_scoring_config(
    snapshot_dict: dict[str, Any],
) -> ScoringConfig:
    """Run the parser/normalizer overlay path to obtain the post-overlay
    `ScoringConfig` per §10.6 call-point source note.

    Reuses the same `parse(snapshot, template)` entrypoint the rest of
    the pipeline uses, so call-point weights match scorer-equivalent
    values exactly. Re-parsing should always succeed when the analyzer's
    other inputs (envelope + sidecar) exist — those are pipeline
    outputs and the pipeline filters NON_CONSUMABLE before it ever
    produces a sidecar.
    """
    snapshot = _snapshot_from_dict(snapshot_dict)
    template = _resolve_template(snapshot_dict)
    parser_result = parse(snapshot, template)
    if parser_result.consumability is not Consumability.CONSUMABLE:
        raise AnalyzerInputError(
            f"snapshot did not parse as CONSUMABLE; analyzer cannot "
            f"resolve scoringConfig. Issues: "
            f"{[i.code for i in parser_result.issues]}"
        )
    config = (parser_result.scoringConfig
              or ScoringConfig.first_release_defaults(
                  parser_result.normalizedModel
              ))
    return config, parser_result.normalizedModel


def analyze(
    snapshot: dict[str, Any],
    envelope: dict[str, Any],
    fullSidecar: dict[str, Any],
    *,
    topK: int,
    generatedAt: str,
    analysisConfig: dict[str, Any] | None = None,
) -> AnalyzerOutput:
    """Run the full analyzer pipeline per `docs/analysis_contract.md`.

    Order:
    1. Admission per §9.1 / §9.2 / §9.5 / §10.0 / §11.
    2. Resolve post-overlay `ScoringConfig` via parser overlay reuse.
    3. Top-K selection per §11 (selector-cascade tiebreak).
    4. Tier 1–5 aggregate computations per §10 + §13.
    5. Assemble `AnalyzerOutput`.

    `generatedAt` is caller-supplied per §9 input #5 — the analyzer
    MUST NOT consume clocks per §15.
    """
    # `analysisConfig` is reserved per §9 input #6; first release ships
    # no required fields. Kept in the signature for forward
    # compatibility with future tuneable knobs.
    _ = analysisConfig

    admit(snapshot, envelope, fullSidecar, topK)

    scoring_config, normalized_model = _resolve_scoring_config(snapshot)
    slot_kind = _slot_kind_map(normalized_model)
    sorted_date_keys = [d.dateKey for d in normalized_model.period.days]
    doctor_ids = [d.doctorId for d in normalized_model.doctors]

    # Top-K selection over the FULL sidecar.
    candidates = list(fullSidecar.get("candidates", []))
    selected = select_top_k(candidates, topK)

    # Tier 1: per-component breakdowns.
    component_breakdowns = build_component_breakdowns(selected, scoring_config)

    # Tiers 2 + 5: per-doctor aggregates per candidate.
    per_doctor_aggregates_list: list[dict[str, Any]] = []
    for cand in selected:
        per_doctor_aggregates_list.append(
            build_per_doctor_aggregates(
                cand,
                scoring_config,
                slot_kind,
                sorted_date_keys,
                doctor_ids,
            )
        )

    # Build per-candidate AnalyzerCandidate.
    analyzer_candidates: list[AnalyzerCandidate] = []
    for rank_idx, cand in enumerate(selected):
        score_obj = cand.get("score", {})
        analyzer_candidates.append(
            AnalyzerCandidate(
                candidateId=int(cand["candidateId"]),
                rankByTotalScore=rank_idx + 1,
                recommended=(rank_idx == 0),
                totalScore=float(score_obj.get("totalScore", 0.0)),
                scoreComponents=component_breakdowns[rank_idx],
                fillStats={
                    "slotsFilled": sum(
                        1 for a in cand.get("assignments", [])
                        if a.get("doctorId") is not None
                    ),
                    "slotsTotal": len(cand.get("assignments", [])),
                },
                perDoctor=per_doctor_aggregates_list[rank_idx],
                assignment=build_assignment_ref(cand),
            )
        )

    # Tier 3: equity scalars per-candidate.
    per_candidate_equity = {
        int(cand["candidateId"]): build_equity_scalars(
            per_doctor_aggregates_list[rank_idx]
        )
        for rank_idx, cand in enumerate(selected)
    }

    # Tier 5: pairwise Hamming distance.
    pairwise = build_pairwise_hamming(selected)

    # Tier 4: hot + locked days.
    hot, locked = build_hot_and_locked_days(selected, sorted_date_keys)

    # Build `doctorIdMap` (analyzer-constructed per §10.0).
    doctor_id_map = {
        rec["sourceDoctorKey"]: rec["displayName"]
        for rec in snapshot.get("doctorRecords", [])
    }

    # Source ride-through.
    final = envelope["finalResultEnvelope"]
    run_env = final["runEnvelope"]
    source = AnalyzerSource(
        runId=run_env["runId"],
        seed=run_env.get("seed"),
        sourceSpreadsheetId=run_env.get("sourceSpreadsheetId", ""),
        sourceTabName=run_env.get("sourceTabName", ""),
    )

    return AnalyzerOutput(
        contractVersion=ANALYSIS_CONTRACT_VERSION,
        generatedAt=generatedAt,
        source=source,
        topK=TopKResult(
            requested=topK,
            returned=len(selected),
            candidates=analyzer_candidates,
        ),
        comparison=ComparisonAggregates(
            pairwiseHammingDistance=pairwise,
            hotDays=hot,
            lockedDays=locked,
            perCandidateEquity=per_candidate_equity,
        ),
        doctorIdMap=doctor_id_map,
    )
