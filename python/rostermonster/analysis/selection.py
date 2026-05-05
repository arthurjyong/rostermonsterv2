"""Top-K selection per `docs/analysis_contract.md` §11.

Pure score-rank with `HIGHEST_SCORE_WITH_CASCADE` tiebreak per
`docs/selector_contract.md` §12.2:
1. `totalScore` descending,
2. `pointBalanceGlobal` descending,
3. `crReward` descending,
4. numerically lowest `candidateId` (run-monotonic dense integer per
   `docs/selector_contract.md` §16.1).

The cascade alignment guarantees the analyzer's rank-1 always equals
the selector's BEST_ONLY winner under §11.1's equivalence claim.
"""

from __future__ import annotations

from typing import Any

from rostermonster.analysis.admission import AnalyzerInputError


def _ordering_key(candidate: dict[str, Any]) -> tuple[float, float, float, int]:
    """Sort key implementing §11 step 2's full cascade.

    Negate the descending-direction fields so Python's natural ascending
    sort produces the desired ordering. Final fallback (`candidateId`
    ascending) needs no negation — it's already ascending.

    Components are read from the FULL sidecar's per-candidate
    `score.components` map per `docs/scorer_contract.md` §10. Missing
    components on a successful candidate violate the scorer contract;
    we fail-loud rather than silently coercing to zero (a missing
    `pointBalanceGlobal` would corrupt cascade ordering invisibly).
    """
    components = candidate.get("score", {}).get("components")
    if not isinstance(components, dict):
        raise AnalyzerInputError(
            f"candidate {candidate.get('candidateId')!r} is missing "
            f"score.components — violates scorer_contract §10"
        )
    if "pointBalanceGlobal" not in components:
        raise AnalyzerInputError(
            f"candidate {candidate.get('candidateId')!r} score.components "
            f"is missing 'pointBalanceGlobal' (cascade tier 2)"
        )
    if "crReward" not in components:
        raise AnalyzerInputError(
            f"candidate {candidate.get('candidateId')!r} score.components "
            f"is missing 'crReward' (cascade tier 3)"
        )

    total_score = candidate.get("score", {}).get("totalScore")
    if total_score is None:
        raise AnalyzerInputError(
            f"candidate {candidate.get('candidateId')!r} is missing "
            f"score.totalScore"
        )

    candidate_id = candidate.get("candidateId")
    if not isinstance(candidate_id, int) or isinstance(candidate_id, bool):
        raise AnalyzerInputError(
            f"candidateId must be an integer (run-monotonic per "
            f"selector §16.1); got {candidate_id!r}"
        )

    # Negation produces "highest first" under Python's ascending sort.
    return (
        -float(total_score),
        -float(components["pointBalanceGlobal"]),
        -float(components["crReward"]),
        candidate_id,  # ascending — lowest wins per §12.2 sub-3.
    )


def select_top_k(
    candidates: list[dict[str, Any]],
    requested: int,
) -> list[dict[str, Any]]:
    """Sort candidates by §11's full cascade and take the first
    `min(requested, len(candidates))` entries.

    Returns the sliced + ordered list of raw candidate dicts (caller
    builds `AnalyzerCandidate` from these). Each returned candidate's
    rank-1-indexed position in the result list IS its
    `rankByTotalScore`.

    `requested` MUST already have passed `admission.validate_top_k`;
    this function does not re-check bounds.
    """
    ordered = sorted(candidates, key=_ordering_key)
    returned = min(requested, len(ordered))
    return ordered[:returned]
