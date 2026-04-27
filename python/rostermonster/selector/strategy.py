"""`HIGHEST_SCORE_WITH_CASCADE` strategy per `docs/selector_contract.md` §12.

Selection rule (§12.1): pick the candidate with the maximum `totalScore`.
Tie-break cascade (§12.2): when multiple candidates tie on `totalScore`,
prefer higher `pointBalanceGlobal`, then higher `crReward`, then lowest
`candidateId`. The cascade depth is exactly two (§12.2's two named
components plus the `candidateId` deterministic fallback); other
components from `docs/domain_model.md` §11.2 are not consulted by this
strategy (§12.3 — adding new components has no effect on this strategy).
"""

from __future__ import annotations

from rostermonster.scorer import (
    COMPONENT_CR_REWARD,
    COMPONENT_POINT_BALANCE_GLOBAL,
)
from rostermonster.selector.result import ScoredTrialCandidate


def pick_highest_score_with_cascade(
    candidates: tuple[ScoredTrialCandidate, ...],
) -> ScoredTrialCandidate:
    """Return the winning `ScoredTrialCandidate` per §12.

    Implementation: a deterministic sort key. Python's tuple comparison
    applies element-by-element, so a single `min(...)` call with the right
    key yields the §12 cascade in one pass:
    - negate `totalScore` so higher wins under min,
    - negate `pointBalanceGlobal` so less-negative wins under min,
    - negate `crReward` so more-positive wins under min,
    - keep `candidateId` natural so lowest wins under min.

    Caller MUST pass at least one candidate; an empty `candidates` tuple
    is a `solver_contract.md` §10.1 violation upstream — the solver does
    not emit empty `CandidateSet` on the success branch — and we don't
    silently paper it over here.
    """
    if not candidates:
        raise ValueError(
            "pick_highest_score_with_cascade called with no candidates; "
            "selector_contract §10.1 forbids empty CandidateSet on the "
            "success branch — caller upstream is the defect"
        )

    def cascade_key(stc: ScoredTrialCandidate) -> tuple[float, float, float, int]:
        components = stc.score.components
        return (
            -stc.score.totalScore,
            -components[COMPONENT_POINT_BALANCE_GLOBAL],
            -components[COMPONENT_CR_REWARD],
            stc.candidate.candidateId,
        )

    return min(candidates, key=cascade_key)
