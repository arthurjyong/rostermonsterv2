"""Pure-function scorer entry per `docs/scorer_contract.md` §6.

Public entry: `score(allocation, normalizedModel, scoringConfig) → ScoreResult`.

Orchestrates the nine first-release components in canonical order and
returns a `ScoreResult` whose `components` dict contains every component
identifier (zero-valued or otherwise) per §10. No internal state, no side
effects, no reads outside the three declared inputs.
"""

from __future__ import annotations

from rostermonster.domain import AssignmentUnit, NormalizedModel
from rostermonster.scorer.components import (
    cr_reward,
    dual_eligible_icu_bonus,
    point_balance_global,
    point_balance_within_section,
    pre_leave_penalty,
    spacing_penalty,
    standby_adjacency_penalty,
    standby_count_fairness_penalty,
    unfilled_penalty,
)
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
    ScoreResult,
    ScoringConfig,
)

# Component identifier → compute function. Keyed canonically so the order
# in `ScoreResult.components` matches `ALL_COMPONENTS` for stable
# downstream serialization (sidecar artifacts, diagnostic surfaces).
_COMPUTE_BY_COMPONENT = {
    COMPONENT_UNFILLED_PENALTY: unfilled_penalty,
    COMPONENT_POINT_BALANCE_WITHIN_SECTION: point_balance_within_section,
    COMPONENT_POINT_BALANCE_GLOBAL: point_balance_global,
    COMPONENT_SPACING_PENALTY: spacing_penalty,
    COMPONENT_PRE_LEAVE_PENALTY: pre_leave_penalty,
    COMPONENT_CR_REWARD: cr_reward,
    COMPONENT_DUAL_ELIGIBLE_ICU_BONUS: dual_eligible_icu_bonus,
    COMPONENT_STANDBY_ADJACENCY_PENALTY: standby_adjacency_penalty,
    COMPONENT_STANDBY_COUNT_FAIRNESS_PENALTY: standby_count_fairness_penalty,
}


def score(
    allocation: tuple[AssignmentUnit, ...],
    normalizedModel: NormalizedModel,
    scoringConfig: ScoringConfig,
) -> ScoreResult:
    """Score one candidate allocation per `docs/scorer_contract.md`.

    Verifies `scoringConfig.weights` covers every first-release component
    identifier per §11 (missing entries are a configuration defect), then
    invokes each component in canonical order. Sums the signed contributions
    into `totalScore` via `ScoreResult.from_components`, which also enforces
    the §10 component-breakdown completeness rule.
    """
    missing_weights = [
        c for c in ALL_COMPONENTS if c not in scoringConfig.weights
    ]
    if missing_weights:
        raise ValueError(
            f"scoringConfig.weights missing required entries per "
            f"docs/scorer_contract.md §11: {missing_weights}"
        )

    components: dict[str, float] = {}
    for component in ALL_COMPONENTS:
        compute = _COMPUTE_BY_COMPONENT[component]
        components[component] = compute(allocation, normalizedModel, scoringConfig)

    return ScoreResult.from_components(components)
