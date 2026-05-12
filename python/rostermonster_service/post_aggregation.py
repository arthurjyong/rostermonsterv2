"""Shared post-aggregation pipeline for the M7 LAHC parallel-solver
path per `docs/cloud_compute_contract.md` §8.7 + §10A.

This module hosts the score → select → analyzer → wrapper-envelope
pipeline that runs AFTER the K-trajectory Pool finishes. Two surfaces
call it:

1. **`worker.py` inline finalize step (M7 C4 T2A.2 onward, operator
   path)** — runs in the same Python process as the Cloud Batch task's
   Pool, after `Pool.close() + .join()`. POSTs the resulting wrapper
   envelope + `AnalyzerOutput` to the launcher Web App callback per
   §10A.

2. **`lahc_orchestrator.py` (M7 C2 maintainer test path, kept per
   D-0071 sub-decision 14)** — runs in the Cloud Run process, polls
   Batch + reads `result.json` from GCS + drives the same pipeline so
   the synchronous-from-curl maintainer test route can return the
   wrapper envelope inline.

Both surfaces feed an `agg` dict (single-task aggregation shape per
`lahc_orchestrator._aggregate_single_task_result`) and get back a
wrapper envelope dict. The shared discipline keeps cross-surface
byte-identity intact per `docs/solver_contract.md` §12A.4 — drift
between surfaces would silently fork the operator-facing writeback.

**Extracted at M7 C4 T2A.2 PR-A** from `lahc_orchestrator.py` (where
this code lived under `_build_post_aggregation_envelope` +
`_build_unsatisfied_from_aggregation` + `_assignment_unit_from_dict`).
The orchestrator-side public symbols stay back-compatible by importing
from this module.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from rostermonster.domain import AssignmentUnit, IssueSeverity, ValidationIssue
from rostermonster.parser import Consumability, parse
from rostermonster.pipeline import _assemble_writeback_wrapper, _snapshot_from_dict
from rostermonster.scorer import ScoringConfig, score
from rostermonster.selector import (
    LahcParamsRecord,
    LahcStrategyConfig,
    RetentionMode,
    RunEnvelope,
    ScoredCandidateSet,
    ScoredTrialCandidate,
    select,
)
from rostermonster.selector.result import SIDECAR_SCHEMA_VERSION
from rostermonster.solver import (
    STRATEGY_LAHC,
    CandidateSet,
    LahcParams,
    PreferenceSeedingConfig,
    SearchDiagnostics,
    TrialCandidate,
    UnfilledDemandEntry,
    UnsatisfiedResult,
    compute_cr_floor,
    derive_K_seeds,
)
from rostermonster.templates import icu_hd_template_artifact


def assignment_unit_from_dict(d: dict) -> AssignmentUnit:
    """Inverse of `_to_jsonable(AssignmentUnit)` — rebuilds an
    `AssignmentUnit` from the worker's serialized dict form so the
    downstream scorer/selector can consume it."""
    return AssignmentUnit(
        dateKey=d["dateKey"],
        slotType=d["slotType"],
        unitIndex=int(d["unitIndex"]),
        doctorId=d["doctorId"],
    )


def build_post_aggregation_envelope(
    *,
    snapshot_dict: dict,
    agg: dict,
    master_seed: int,
    K_approved: int,
    run_id: str,
) -> dict | None:
    """T2G post-aggregation pipeline: take the K' candidates aggregated
    from the worker's per-trajectory output + run them through the
    standard scorer → selector → wrapper-envelope chain (matching what
    `pipeline.run_pipeline()` does for the local CLI path) so cloud-mode
    writebacks produce the same `writebackEnvelope` shape as the local
    `POST /compute` route per §13 byte-identity.

    Returns the wrapper envelope dict, or `None` if K' == 0 AND the
    failure-branch envelope can't be constructed (defensive — should
    never happen because the orchestrator pre-validates snapshot
    consumability before dispatching to Cloud Batch + the snapshot is
    immutable in GCS thereafter).
    """
    candidates_raw = agg["candidates"]

    snapshot = _snapshot_from_dict(snapshot_dict)
    template = icu_hd_template_artifact()
    parser_result = parse(snapshot, template)
    # Caller pre-validates parser consumability at entry (returning
    # INPUT_ERROR with code PARSER_REJECTED on NON_CONSUMABLE); the
    # snapshot is immutable in GCS, so re-parse here MUST also be
    # CONSUMABLE. Assert the invariant rather than carrying a defensive
    # `return None` branch.
    assert parser_result.consumability is Consumability.CONSUMABLE, (
        "post-Batch parser_result is " + repr(parser_result.consumability)
        + " despite caller's pre-dispatch CONSUMABLE check + GCS-"
        "immutable snapshot — internal invariant broken"
    )

    model = parser_result.normalizedModel
    scoring_config = (parser_result.scoringConfig
                      or ScoringConfig.first_release_defaults(model))
    # §13.4 audit requirement: the computed CR floor MUST be logged in
    # SearchDiagnostics + RunEnvelope. Both surfaces below derive the
    # value the same way `solve()` does so wrapper diagnostics match
    # the solver run that produced the candidates.
    cr_floor_seeding = PreferenceSeedingConfig()
    cr_floor_x = compute_cr_floor(model, cr_floor_seeding.crFloor)

    # Reconstruct trial candidates from agg["candidates"]. Each
    # candidate's assignments came from the worker as JSON dicts;
    # convert back to AssignmentUnit objects so the scorer/selector
    # can consume them. `candidateId` is 1-indexed dense per
    # `docs/selector_contract.md` §16; emission order = aggregation
    # order. Empty when K' == 0 (failure-branch path).
    trial_candidates = tuple(
        TrialCandidate(
            candidateId=i + 1,
            assignments=tuple(
                assignment_unit_from_dict(a) for a in cand["assignments"]
            ),
        )
        for i, cand in enumerate(candidates_raw)
    )

    # Build SearchDiagnostics. Per `docs/solver_contract.md` §12A.9, the
    # per-trajectory arrays MUST have an entry for EVERY trajectory the
    # solver attempted, with `0` / `None` for `SEED_FAILED` entries.
    # Walk `derive_K_seeds()` once + key by candidateSeed only — under
    # single-task every candidate carries `taskIndex=0`, so the partition-
    # based lookup wouldn't disambiguate anyway. Single-source-of-truth
    # via the same helper the worker uses.
    candidate_lookup = {c["candidateSeed"]: c for c in candidates_raw}
    failed_lookup = {f["candidateSeed"]: f for f in agg["failedTrajectories"]}
    all_seeds = derive_K_seeds(master_seed, K_approved)
    per_traj_status_list: list[str] = []
    per_traj_iters_list: list[int] = []
    per_traj_accepted_list: list[int] = []
    per_traj_best_list: list[float | None] = []
    per_traj_terminal_list: list[float | None] = []
    for seed in all_seeds:
        if seed in candidate_lookup:
            c = candidate_lookup[seed]
            per_traj_status_list.append("SUCCEEDED")
            per_traj_iters_list.append(int(c["iters"]))
            per_traj_accepted_list.append(int(c["acceptedMoves"]))
            per_traj_best_list.append(c["bestScore"])
            per_traj_terminal_list.append(c["terminalScore"])
        elif seed in failed_lookup:
            per_traj_status_list.append("SEED_FAILED")
            per_traj_iters_list.append(0)
            per_traj_accepted_list.append(0)
            per_traj_best_list.append(None)
            per_traj_terminal_list.append(None)
        # else: missing — no per-trajectory entry recorded; surfaces via
        # the caller's incompleteTaskIndices analog.
    per_traj_status = tuple(per_traj_status_list)
    per_traj_iters = tuple(per_traj_iters_list)
    per_traj_accepted = tuple(per_traj_accepted_list)
    per_traj_best = tuple(per_traj_best_list)
    per_traj_terminal = tuple(per_traj_terminal_list)

    diagnostics = SearchDiagnostics(
        strategyId=STRATEGY_LAHC,
        fillOrderPolicy="MOST_CONSTRAINED_FIRST",
        crFloorMode="SMART_MEDIAN",
        crFloorComputed=cr_floor_x,
        seed=master_seed,
        placementAttempts=int(agg["aggregateAttempts"]),
        ruleEngineRejectionsByReason=dict(agg["aggregateRejectionsByReason"]),
        candidateEmitCount=len(trial_candidates),
        unfilledDemandCount=0,
        lahcHistoryListLength=50,   # FW-0037 elbow tuple per worker.py
        lahcMaxIters=LahcParams().maxIters,
        lahcIdleThreshold=3500,
        lahcSwapProbability=0.5,
        seedDerivationFunction="python.Random.getrandbits.candidate_seed",
        perTrajectoryStatus=per_traj_status,
        perTrajectoryIters=per_traj_iters,
        perTrajectoryAcceptedMoves=per_traj_accepted,
        perTrajectoryBestScore=per_traj_best,
        perTrajectoryTerminalScore=per_traj_terminal,
    )

    # Build RunEnvelope mirroring pipeline._build_run_envelope's LAHC
    # branch. §13 byte-identity invariant: writebackEnvelope MUST match
    # local-CLI's `pipeline._build_run_envelope` for the same snapshot +
    # explicit seed. Local CLI uses `runId=md.snapshotId` and
    # `crFloorComputed=0` in the RunEnvelope.
    md = snapshot.metadata
    run_envelope = RunEnvelope(
        runId=md.snapshotId,
        snapshotRef=md.snapshotId,
        configRef="first_release_defaults",
        seed=master_seed,
        fillOrderPolicy="MOST_CONSTRAINED_FIRST",
        crFloorMode="SMART_MEDIAN",
        crFloorComputed=0,
        generationTimestamp=md.generationTimestamp,
        sourceSpreadsheetId=md.sourceSpreadsheetId,
        sourceTabName=md.sourceTabName,
        solverStrategy=STRATEGY_LAHC,
        solverStrategyConfig=LahcStrategyConfig(
            lahcParams=LahcParamsRecord(
                historyListLength=50,
                idleThreshold=3500,
                maxIters=LahcParams().maxIters,
                swapProbability=0.5,
            ),
        ),
    )

    # Branch on K'. Both paths produce a FinalResultEnvelope (success
    # OR failure-branch) per `docs/cloud_compute_contract.md` §10.2 +
    # §10.3 — UNSATISFIED responses MUST still carry a wrapper so the
    # bound shim's `RMLib.applyWriteback(response.writebackEnvelope)`
    # call doesn't crash on null.
    if trial_candidates:
        # SUCCESS branch — score K' candidates + run selector.
        candidate_set = CandidateSet(
            candidates=trial_candidates,
            diagnostics=diagnostics,
        )
        scored = ScoredCandidateSet(
            candidates=tuple(
                ScoredTrialCandidate(
                    candidate=cand,
                    score=score(cand.assignments, model, scoring_config),
                )
                for cand in candidate_set.candidates
            ),
            diagnostics=diagnostics,
        )
        # FULL required by analyzer admission (analysis_contract §9.1).
        # Path keyed on run_envelope.runId (== md.snapshotId, matching
        # the local-CLI pipeline._build_run_envelope) so the path
        # string baked into writebackEnvelope is byte-identical with
        # the local path's. Codex P2 round 2 on PR #163: the
        # orchestrator's run_id kwarg uses derive_run_id(snapshot_id,
        # master_seed) which differs from md.snapshotId, so keying on
        # run_id would re-break byte-identity. Use /tmp explicitly
        # (not tempfile.gettempdir, which is /var/folders/... on
        # macOS) so the audit's local-vs-cloud comparison agrees.
        sidecar_dir = Path("/tmp") / "rm-lahc-sidecars" / run_envelope.runId
        sidecar_dir.mkdir(parents=True, exist_ok=True)
        envelope = select(
            scored,
            retentionMode=RetentionMode.FULL,
            runEnvelope=run_envelope,
            sidecarTargetDir=sidecar_dir,
        )
    else:
        # FAILURE branch (K' == 0) — synthesize an UnsatisfiedResult
        # from per-trajectory failedTrajectories aggregation; selector
        # forwards via the failure-branch wrapper per
        # `docs/selector_contract.md` §15.
        unsatisfied = build_unsatisfied_from_aggregation(
            agg=agg, diagnostics=diagnostics, master_seed=master_seed,
        )
        # Failure branch skips sidecar emission regardless of retention
        # mode (selector_contract §15).
        envelope = select(
            unsatisfied,
            retentionMode=RetentionMode.FULL,
            runEnvelope=run_envelope,
        )

    return _assemble_writeback_wrapper(envelope, snapshot, template)


def build_unsatisfied_from_aggregation(
    *, agg: dict, diagnostics: SearchDiagnostics, master_seed: int,
) -> UnsatisfiedResult:
    """Synthesize an `UnsatisfiedResult` from aggregated
    `failedTrajectories` for the K'==0 path. The selector then wraps it
    in the failure-branch FinalResultEnvelope per
    `docs/selector_contract.md` §15 + §10.2, so callbacks can return a
    non-null wrapper even when every trajectory failed (bound shim's
    `RMLib.applyWriteback(envelope)` requires non-null per
    `docs/cloud_compute_contract.md` §10.3).

    `unfilledDemand` is deduped by `(dateKey, slotType, unitIndex)`
    matching `solver.py::_build_unsatisfied`'s discipline. `reasons`
    carries one ValidationIssue per (failed_trajectory, unit) pair so
    analyzer / writeback consumers can see which seed hit which failure
    (per §12A.8 "complete per-trajectory failure data")."""
    seen_units: set[tuple[str, str, int]] = set()
    unfilled_list: list[UnfilledDemandEntry] = []
    reasons_list: list[ValidationIssue] = []
    for failed in agg["failedTrajectories"]:
        candidate_seed = failed.get("candidateSeed")
        task_index = failed.get("taskIndex")
        for u in failed.get("unfilledDemand", []) or []:
            date_key = u.get("dateKey", "")
            slot_type = u.get("slotType", "")
            unit_index = int(u.get("unitIndex", 0))
            reasons_list.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code="UNFILLABLE_DEMAND",
                    message=(
                        "No eligible-and-rule-valid doctor for ("
                        + str(date_key) + ", " + str(slot_type)
                        + ", unit " + str(unit_index)
                        + ") under LAHC seed=" + str(candidate_seed)
                        + " (Cloud Batch task " + str(task_index) + ")"
                    ),
                    context={
                        "dateKey": date_key,
                        "slotType": slot_type,
                        "unitIndex": unit_index,
                        "taskIndex": task_index,
                        "seed": candidate_seed,
                    },
                )
            )
            key = (date_key, slot_type, unit_index)
            if key in seen_units:
                continue
            seen_units.add(key)
            unfilled_list.append(
                UnfilledDemandEntry(
                    dateKey=date_key,
                    slotType=slot_type,
                    unitIndex=unit_index,
                )
            )
    # Override the per-trajectory diagnostic count with the deduped
    # unfilled count per `docs/solver_contract.md` §18 audit invariant.
    failure_diagnostics = dataclasses.replace(
        diagnostics, unfilledDemandCount=len(unfilled_list),
    )
    return UnsatisfiedResult(
        unfilledDemand=tuple(unfilled_list),
        reasons=tuple(reasons_list),
        diagnostics=failure_diagnostics,
    )


def build_full_sidecar_dict(
    *,
    snapshot_dict: dict,
    agg: dict,
    master_seed: int,
    K_approved: int,
    run_id: str,
) -> dict[str, Any] | None:
    """Build the in-memory `fullSidecar` dict the analyzer consumes.

    Mirrors `selector/sidecars.py::_full_json_text`'s payload shape but
    constructs the dict directly from the post-aggregation pipeline's
    intermediate state — saves a round-trip through GCS that the M7 C2
    multi-task pattern paid because each task wrote a partial result.
    Under the single-task pattern the candidates stay in-memory inside
    one Python process, so the sidecar can be assembled inline with no
    file I/O.

    Returns `None` when K' == 0 — the analyzer doesn't run on the
    failure branch per `docs/analysis_contract.md` §9.2 + §10A.6's
    `analyzerOutput: null` convention for `state ∈ {UNSATISFIED,
    COMPUTE_ERROR}`.
    """
    candidates_raw = agg["candidates"]
    if not candidates_raw:
        return None

    # Re-parse to get model + scoring_config so we can score the
    # in-memory candidates here and emit the per-candidate `score`
    # block the analyzer admits per `docs/analysis_contract.md` §10.0.
    snapshot = _snapshot_from_dict(snapshot_dict)
    template = icu_hd_template_artifact()
    parser_result = parse(snapshot, template)
    assert parser_result.consumability is Consumability.CONSUMABLE
    model = parser_result.normalizedModel
    scoring_config = (parser_result.scoringConfig
                      or ScoringConfig.first_release_defaults(model))
    md = snapshot.metadata

    candidates_payload: list[dict[str, Any]] = []
    for i, cand in enumerate(candidates_raw):
        assignments = [
            assignment_unit_from_dict(a) for a in cand["assignments"]
        ]
        score_result = score(tuple(assignments), model, scoring_config)
        candidates_payload.append({
            "candidateId": i + 1,
            "assignments": [
                {
                    "dateKey": u.dateKey,
                    "slotType": u.slotType,
                    "unitIndex": u.unitIndex,
                    "doctorId": u.doctorId,
                }
                for u in assignments
            ],
            "score": {
                "totalScore": score_result.totalScore,
                "direction": score_result.direction.value,
                "components": dict(score_result.components),
            },
        })

    # `runId` MUST match `envelope.finalResultEnvelope.runEnvelope.runId`
    # per `docs/analysis/admission.py`'s admission check — local-CLI
    # +  cloud paths agree on `md.snapshotId` per the §13 byte-identity
    # invariant locked in `build_post_aggregation_envelope` above.
    return {
        "schemaVersion": SIDECAR_SCHEMA_VERSION,
        "runId": md.snapshotId,
        "generationTimestamp": md.generationTimestamp,
        "candidates": candidates_payload,
    }
