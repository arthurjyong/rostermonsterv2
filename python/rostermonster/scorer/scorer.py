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
    PENALTY_COMPONENTS,
    REWARD_COMPONENTS,
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

    Validates:
    1. §11 — `scoringConfig.weights` covers every first-release component
       identifier (missing entries are a configuration defect).
    2. §10 + §15 — sign orientation is a property of the component, not the
       weight: a penalty component's weight MUST be ≤ 0 and a reward
       component's weight MUST be ≥ 0. Mis-signed weights would invert the
       direction-guard invariant (§13) — for example, a positive
       `unfilledPenalty` weight would make unfilled assignments INCREASE
       totalScore — so we reject at config validation rather than silently
       allowing the inversion.

    Then invokes each component in canonical order and sums the signed
    contributions into `totalScore` via `ScoreResult.from_components`,
    which enforces the §10 component-breakdown completeness rule.
    """
    missing_weights = [
        c for c in ALL_COMPONENTS if c not in scoringConfig.weights
    ]
    if missing_weights:
        raise ValueError(
            f"scoringConfig.weights missing required entries per "
            f"docs/scorer_contract.md §11: {missing_weights}"
        )

    sign_errors: list[str] = []
    for component, weight in scoringConfig.weights.items():
        if component in PENALTY_COMPONENTS and weight > 0:
            sign_errors.append(
                f"{component} is a penalty (must contribute non-positively "
                f"per §10) but weight is {weight!r} (> 0)"
            )
        elif component in REWARD_COMPONENTS and weight < 0:
            sign_errors.append(
                f"{component} is a reward (must contribute non-negatively "
                f"per §10) but weight is {weight!r} (< 0)"
            )
    if sign_errors:
        raise ValueError(
            "scoringConfig.weights violates per-component sign orientation "
            "per docs/scorer_contract.md §10 / §15: "
            + "; ".join(sign_errors)
        )

    components: dict[str, float] = {}
    for component in ALL_COMPONENTS:
        compute = _COMPUTE_BY_COMPONENT[component]
        components[component] = compute(allocation, normalizedModel, scoringConfig)

    return ScoreResult.from_components(components)
