"""Scorer module per `docs/scorer_contract.md`.

Public entry: `score(allocation, normalizedModel, scoringConfig) → ScoreResult`.

Pure-function reference implementation per §6 + §10. All nine first-release
components per `docs/domain_model.md` §11.2 are computed on every call;
direction is fixed at `HIGHER_IS_BETTER` per §10. Operator-tuneable curve
parameters (FW-0007) and the v1 weight reference pass (FW-0014) remain
out of first release.
"""

from rostermonster.scorer.result import (
    ALL_COMPONENTS,
    COMPONENT_CR_REWARD,
    COMPONENT_DUAL_ELIGIBLE_ICU_BONUS,
    COMPONENT_POINT_BALANCE_GLOBAL,
    COMPONENT_POINT_BALANCE_WITHIN_SECTION,
    COMPONENT_PRE_LEAVE_PENALTY,
    COMPONENT_SPACING_PENALTY,
    COMPONENT_STANDBY_ADJACENCY_PENALTY,
    COMPONENT_STANDBY_COUNT_FAIRNESS_PENALTY,
    COMPONENT_UNFILLED_PENALTY,
    ScoreDirection,
    ScoreResult,
    ScoringConfig,
    uniform_point_rules,
)
from rostermonster.scorer.scorer import score

__all__ = [
    "score",
    "ScoreResult",
    "ScoringConfig",
    "ScoreDirection",
    "uniform_point_rules",
    "ALL_COMPONENTS",
    "COMPONENT_UNFILLED_PENALTY",
    "COMPONENT_POINT_BALANCE_WITHIN_SECTION",
    "COMPONENT_POINT_BALANCE_GLOBAL",
    "COMPONENT_SPACING_PENALTY",
    "COMPONENT_PRE_LEAVE_PENALTY",
    "COMPONENT_CR_REWARD",
    "COMPONENT_DUAL_ELIGIBLE_ICU_BONUS",
    "COMPONENT_STANDBY_ADJACENCY_PENALTY",
    "COMPONENT_STANDBY_COUNT_FAIRNESS_PENALTY",
]
