"""Tier 1–5 aggregate computations per `docs/analysis_contract.md` §10
+ §13.

Tier 1: per-component score decomposition (`ComponentBreakdown`).
Tier 2 (v2 per D-0073): per-doctor equity (`PerDoctorAggregates`) —
group classification, CALL/STANDBY counts, `totalCallPoints` via
parser-overlay reuse, average call points per call, three call-gap
metrics (shortest/second-shortest/longest, scorer-stride convention),
CR fulfilled/unfulfilled counts.
Tier 3 (v2 per D-0073): equity scalars (`EquityScalars`) — stdev,
min-max gap, Gini across the doctor population for callCount and
totalCallPoints (dropped weekendCallCount in v2).
Tier 4: hot/locked days (per-day disagreement count + locked-day
inverse).
Tier 5: pairwise Hamming distance over `(dateKey, slotType, unitIndex)`
cells.

Tier 6 (rule-violation breakdown) is NOT computed — parked as FW-0032.
Tier 7 (decision-support tags) is renderer-derived per §10.9.
"""

from __future__ import annotations

import statistics
from datetime import date
from typing import Any

from rostermonster.analysis.admission import AnalyzerInputError
from rostermonster.analysis.output import (
    AssignmentRefRecord,
    ComponentBreakdown,
    EquityScalars,
    HotDayEntry,
    LockedDayEntry,
    PerDoctorAggregates,
)
from rostermonster.domain import CanonicalRequestClass, NormalizedModel
from rostermonster.scorer.result import ScoringConfig

# `slotKind` values per `docs/template_artifact_contract.md` / domain
# §7.6.
SLOT_KIND_CALL = "CALL"
SLOT_KIND_STANDBY = "STANDBY"


def _slot_kind_map(model: NormalizedModel) -> dict[str, str]:
    """Build `slotType → slotKind` map from the normalized model's
    template-projected slot definitions per `docs/domain_model.md` §7.6.

    Used to classify each AssignmentUnit as CALL vs STANDBY for Tier 2
    counts.
    """
    return {st.slotType: st.slotKind for st in model.slotTypes}


def _gini(values: list[float]) -> float:
    """Gini coefficient over a non-negative-valued distribution.

    Standard formula: `Gini = sum(|xi - xj|) / (2 * n * sum(xi))`. Returns
    `0.0` for an all-zero distribution (degenerate but well-defined).
    Bounded `[0.0, 1.0)`.
    """
    n = len(values)
    if n == 0:
        return 0.0
    total = sum(values)
    if total <= 0.0:
        return 0.0
    sad = sum(abs(a - b) for a in values for b in values)
    return sad / (2.0 * n * total)


def _stat_block(values: list[float]) -> dict[str, float]:
    """`{stdev, minMaxGap, gini}` rollup over a per-doctor distribution
    for one candidate. Used by `EquityScalars` per §10.8."""
    if not values:
        return {"stdev": 0.0, "minMaxGap": 0.0, "gini": 0.0}
    stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
    return {
        "stdev": float(stdev),
        "minMaxGap": float(max(values) - min(values)),
        "gini": float(_gini(values)),
    }


def build_component_breakdowns(
    selected_candidates: list[dict[str, Any]],
    scoring_config: ScoringConfig,
) -> list[dict[str, ComponentBreakdown]]:
    """Tier 1 per-candidate component breakdown per §10.3.

    Returns one `dict[componentName, ComponentBreakdown]` per candidate
    in input order. Each entry includes `weighted`, `raw`,
    `rankAcrossTopK`, `gapToNextRanked`.

    `raw` is `weighted / weights[componentName]` when the weight is
    non-zero; sentinel `0` when the weight is zero (per §10.3 v1
    tolerance). Cross-candidate rank/gap are computed per-component
    after all candidates' weighted values are collected.
    """
    if not selected_candidates:
        return []

    # Collect weighted values per component across the K candidates.
    component_names = sorted(scoring_config.weights.keys())
    weighted_by_component: dict[str, list[tuple[float, int]]] = {
        cn: [] for cn in component_names
    }
    for idx, cand in enumerate(selected_candidates):
        components = cand.get("score", {}).get("components", {})
        for cn in component_names:
            if cn not in components:
                # Scorer §10 contractually requires every first-release
                # component on every emitted ScoreResult. Silent zero-
                # fill would corrupt rank/gap calculations on a partial
                # sidecar; fail-loud surfaces upstream defect cleanly.
                raise AnalyzerInputError(
                    f"candidate {cand.get('candidateId')!r} score.components "
                    f"is missing required component {cn!r} — scorer "
                    f"contract §10 violation upstream"
                )
            weighted_by_component[cn].append(
                (float(components[cn]), idx)
            )

    # Rank within K per component (descending by weighted value).
    rank_table: dict[str, list[int]] = {cn: [0] * len(selected_candidates)
                                        for cn in component_names}
    gap_table: dict[str, list[float | None]] = {cn: [None] * len(selected_candidates)
                                                for cn in component_names}
    for cn in component_names:
        # Sort descending by weighted value; ties broken by candidate
        # index so the rank assignment is deterministic.
        sorted_pairs = sorted(weighted_by_component[cn],
                              key=lambda p: (-p[0], p[1]))
        for rank_zero_indexed, (value, idx) in enumerate(sorted_pairs):
            rank_table[cn][idx] = rank_zero_indexed + 1
            if rank_zero_indexed < len(sorted_pairs) - 1:
                next_value = sorted_pairs[rank_zero_indexed + 1][0]
                gap_table[cn][idx] = float(value - next_value)
            else:
                gap_table[cn][idx] = None

    # Build per-candidate breakdowns. Component presence already verified
    # in the collection loop above — `components[cn]` is safe here.
    out: list[dict[str, ComponentBreakdown]] = []
    for idx, cand in enumerate(selected_candidates):
        components = cand["score"]["components"]
        per_candidate: dict[str, ComponentBreakdown] = {}
        for cn in component_names:
            weighted = float(components[cn])
            weight = float(scoring_config.weights.get(cn, 0.0))
            raw = (weighted / weight) if weight != 0.0 else 0.0
            per_candidate[cn] = ComponentBreakdown(
                weighted=weighted,
                raw=raw,
                rankAcrossTopK=rank_table[cn][idx],
                gapToNextRanked=gap_table[cn][idx],
            )
        out.append(per_candidate)
    return out


def _call_date_gaps(call_dates: list[str]) -> tuple[int | None, int | None, int | None]:
    """Return (shortest, second-shortest, longest) stride-day gap between
    consecutive CALL dates for one doctor, per §10.6 (v2).

    Gap definition matches the scorer's `spacingPenalty` semantics
    (`scorer/components.py:189`): `(date_next - date_prev).days`. Mon→Wed
    = 2 (NOT 1) so an operator can cross-reference the scorer's
    `weight / 2^(gap-2)` curve directly.

    Returns `(None, None, None)` when callCount < 2 (no gap defined).
    Second-shortest is `None` when callCount < 3 (only one gap exists).
    """
    if len(call_dates) < 2:
        return None, None, None
    sorted_dates = sorted(date.fromisoformat(dk) for dk in call_dates)
    strides = [
        (sorted_dates[i + 1] - sorted_dates[i]).days
        for i in range(len(sorted_dates) - 1)
    ]
    shortest = min(strides)
    longest = max(strides)
    if len(strides) < 2:
        second_shortest: int | None = None
    else:
        second_shortest = sorted(strides)[1]
    return shortest, second_shortest, longest


def _per_doctor_cr_counts(
    candidate_assignments: list[dict[str, Any]],
    slot_kind: dict[str, str],
    model: NormalizedModel,
) -> dict[str, tuple[int, int]]:
    """Return `{doctorId: (fulfilled, unfulfilled)}` per §10.6 (v2).

    A CR is "fulfilled" when the candidate assigns the requesting doctor
    to ANY call-kind slot on the request's `dateKey`. Mirrors the scorer
    `cr_reward` definition (`scorer/components.py:240-261`) so the
    analyzer's per-doctor count is bit-identical to the rationale behind
    the scorer's `crReward` component contribution.
    """
    on_call: set[tuple[str, str]] = {
        (a["doctorId"], a["dateKey"])
        for a in candidate_assignments
        if a.get("doctorId") is not None
        and slot_kind.get(a["slotType"]) == SLOT_KIND_CALL
    }
    out: dict[str, list[int]] = {}
    for req in model.requests:
        if CanonicalRequestClass.CR not in req.canonicalClasses:
            continue
        bucket = out.setdefault(req.doctorId, [0, 0])
        if (req.doctorId, req.dateKey) in on_call:
            bucket[0] += 1
        else:
            bucket[1] += 1
    return {k: (v[0], v[1]) for k, v in out.items()}


def build_per_doctor_aggregates(
    candidate: dict[str, Any],
    scoring_config: ScoringConfig,
    slot_kind: dict[str, str],
    sorted_date_keys: list[str],
    doctor_ids: list[str],
    model: NormalizedModel,
) -> dict[str, PerDoctorAggregates]:
    """Tier 2 per-doctor equity per §10.6 (v2) for one candidate.

    v2 signature adds `model: NormalizedModel` (required for groupId
    classification + CR record traversal). `sorted_date_keys` kept for
    compatibility with caller's signature; not used in v2 (max-
    consecutive-days-off was dropped per D-0073).
    """
    _ = sorted_date_keys  # retained for callsite back-compat (unused in v2)
    assignments = candidate.get("assignments", [])
    # Pre-resolve doctor group from the normalized model; admission per
    # §10.0 guarantees every doctor in the snapshot is in `model.doctors`.
    group_by_doctor: dict[str, str] = {d.doctorId: d.groupId for d in model.doctors}
    by_doctor: dict[str, dict[str, Any]] = {
        d: {"call": 0, "standby": 0, "points": 0.0, "call_dates": []}
        for d in doctor_ids
    }
    for a in assignments:
        doctor_id = a.get("doctorId")
        if doctor_id is None:
            continue  # Unfilled units are not per-doctor counted.
        if doctor_id not in by_doctor:
            # Doctor in sidecar not in snapshot — admission §10.0 should
            # have caught this; fail-loud here as a defense in depth.
            raise AnalyzerInputError(
                f"candidate {candidate.get('candidateId')!r} assignment "
                f"references unknown doctorId {doctor_id!r}"
            )
        slot_type = a["slotType"]
        kind = slot_kind.get(slot_type, "")
        date_key = a["dateKey"]
        if kind == SLOT_KIND_CALL:
            by_doctor[doctor_id]["call"] += 1
            by_doctor[doctor_id]["call_dates"].append(date_key)
            point_weight = scoring_config.pointRules.get(
                (slot_type, date_key)
            )
            if point_weight is None:
                # Per scorer §11 + D-0038, pointRules MUST cover every
                # CALL `(slotType, dateKey)` pair. Missing key is an
                # upstream defect.
                raise AnalyzerInputError(
                    f"scoring config missing pointRules for "
                    f"({slot_type!r}, {date_key!r})"
                )
            by_doctor[doctor_id]["points"] += float(point_weight)
        elif kind == SLOT_KIND_STANDBY:
            by_doctor[doctor_id]["standby"] += 1
        # Other slot kinds (none in first release) are ignored.

    cr_counts = _per_doctor_cr_counts(assignments, slot_kind, model)

    out: dict[str, PerDoctorAggregates] = {}
    for d in doctor_ids:
        stats = by_doctor[d]
        call_count = int(stats["call"])
        total_points = float(stats["points"])
        shortest_gap, second_shortest_gap, longest_gap = _call_date_gaps(
            stats["call_dates"]
        )
        avg_points: float | None = (
            total_points / call_count if call_count > 0 else None
        )
        cr_fulfilled, cr_unfulfilled = cr_counts.get(d, (0, 0))
        out[d] = PerDoctorAggregates(
            group=group_by_doctor[d],
            callCount=call_count,
            standbyCount=int(stats["standby"]),
            totalCallPoints=total_points,
            averageCallPointsPerCall=avg_points,
            shortestCallGap=shortest_gap,
            secondShortestCallGap=second_shortest_gap,
            longestCallGap=longest_gap,
            callRequestsFulfilled=cr_fulfilled,
            callRequestsUnfulfilled=cr_unfulfilled,
        )
    return out


def build_equity_scalars(
    per_doctor: dict[str, PerDoctorAggregates],
) -> EquityScalars:
    """Tier 3 per-candidate equity scalars per §10.8 (v2).

    v2 drops `weekendCallCount` block (PerDoctorAggregates field dropped)
    and renames `cumulativeCallPoints` → `totalCallPoints` per D-0073.
    """
    call_counts = [float(a.callCount) for a in per_doctor.values()]
    total_points = [float(a.totalCallPoints) for a in per_doctor.values()]
    return EquityScalars(
        callCount=_stat_block(call_counts),
        totalCallPoints=_stat_block(total_points),
    )


def build_assignment_ref(
    candidate: dict[str, Any],
) -> list[AssignmentRefRecord]:
    """§10.5 ride-through of the FULL sidecar's `assignments[*]`."""
    out: list[AssignmentRefRecord] = []
    for a in candidate.get("assignments", []):
        out.append(
            AssignmentRefRecord(
                dateKey=a["dateKey"],
                slotType=a["slotType"],
                unitIndex=int(a["unitIndex"]),
                doctorId=a.get("doctorId"),
            )
        )
    return out


def build_pairwise_hamming(
    selected_candidates: list[dict[str, Any]],
) -> dict[int, dict[int, int]]:
    """Tier 5 pairwise Hamming distance over `(dateKey, slotType,
    unitIndex)` cells per §10.7. Symmetric — emits the full square so
    readers don't need triangle-lookup bookkeeping.
    """
    # Build per-candidate cell-key → doctorId map.
    cell_to_doctor: dict[int, dict[tuple[str, str, int], str | None]] = {}
    for cand in selected_candidates:
        cid = cand["candidateId"]
        cells: dict[tuple[str, str, int], str | None] = {}
        for a in cand.get("assignments", []):
            cells[(a["dateKey"], a["slotType"], int(a["unitIndex"]))] = (
                a.get("doctorId")
            )
        cell_to_doctor[cid] = cells

    candidate_ids = [c["candidateId"] for c in selected_candidates]
    out: dict[int, dict[int, int]] = {a: {} for a in candidate_ids}
    for a in candidate_ids:
        for b in candidate_ids:
            if a == b:
                out[a][b] = 0
                continue
            if b in out.get(a, {}):
                continue  # already filled (symmetric — see below)
            distance = 0
            cells_a = cell_to_doctor[a]
            cells_b = cell_to_doctor[b]
            keys = set(cells_a) | set(cells_b)
            for k in keys:
                if cells_a.get(k) != cells_b.get(k):
                    distance += 1
            out[a][b] = distance
            out[b][a] = distance
    return out


def build_hot_and_locked_days(
    selected_candidates: list[dict[str, Any]],
    sorted_date_keys: list[str],
) -> tuple[list[HotDayEntry], list[LockedDayEntry]]:
    """Tier 4 day-level per §10.7.

    A day's "assignment tuple" is the sorted set of
    `(slotType, unitIndex, doctorId)` triples on that date. A day is
    LOCKED if every candidate produces the same tuple; HOT otherwise.
    """
    # Build per-candidate per-day assignment tuple.
    per_candidate_per_day: dict[int, dict[str, tuple]] = {}
    for cand in selected_candidates:
        cid = cand["candidateId"]
        per_day: dict[str, list[tuple[str, int, str | None]]] = {}
        for a in cand.get("assignments", []):
            per_day.setdefault(a["dateKey"], []).append(
                (a["slotType"], int(a["unitIndex"]), a.get("doctorId"))
            )
        per_candidate_per_day[cid] = {
            k: tuple(sorted(v)) for k, v in per_day.items()
        }

    candidate_ids = [c["candidateId"] for c in selected_candidates]
    hot: list[HotDayEntry] = []
    locked: list[LockedDayEntry] = []
    for dk in sorted_date_keys:
        distinct: set[tuple] = set()
        for cid in candidate_ids:
            distinct.add(per_candidate_per_day.get(cid, {}).get(dk, ()))
        n = len(distinct)
        if n == 1:
            locked.append(LockedDayEntry(dateKey=dk))
        else:
            hot.append(HotDayEntry(dateKey=dk, distinctAssignments=n))
    return hot, locked
