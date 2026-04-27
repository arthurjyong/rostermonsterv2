"""Scorer result + config types per `docs/scorer_contract.md` §10–§11.

`ScoreResult` is the public output shape with mandatory total + required
per-component breakdown + literal direction tag. `ScoringConfig` is the
input config shape carrying per-component weights (operator-tuneable per
§15) and curve parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rostermonster.domain import NormalizedModel

# First-release component identifiers per docs/domain_model.md §11.2 +
# docs/scorer_contract.md §4. Every ScoreResult MUST include all nine of
# these in `components`, even when one contributes zero, per §10.
COMPONENT_UNFILLED_PENALTY = "unfilledPenalty"
COMPONENT_POINT_BALANCE_WITHIN_SECTION = "pointBalanceWithinSection"
COMPONENT_POINT_BALANCE_GLOBAL = "pointBalanceGlobal"
COMPONENT_SPACING_PENALTY = "spacingPenalty"
COMPONENT_PRE_LEAVE_PENALTY = "preLeavePenalty"
COMPONENT_CR_REWARD = "crReward"
COMPONENT_DUAL_ELIGIBLE_ICU_BONUS = "dualEligibleIcuBonus"
COMPONENT_STANDBY_ADJACENCY_PENALTY = "standbyAdjacencyPenalty"
COMPONENT_STANDBY_COUNT_FAIRNESS_PENALTY = "standbyCountFairnessPenalty"

# Canonical iteration order — used to ensure ScoreResult.components is built
# deterministically across runs and platforms.
ALL_COMPONENTS: tuple[str, ...] = (
    COMPONENT_UNFILLED_PENALTY,
    COMPONENT_POINT_BALANCE_WITHIN_SECTION,
    COMPONENT_POINT_BALANCE_GLOBAL,
    COMPONENT_SPACING_PENALTY,
    COMPONENT_PRE_LEAVE_PENALTY,
    COMPONENT_CR_REWARD,
    COMPONENT_DUAL_ELIGIBLE_ICU_BONUS,
    COMPONENT_STANDBY_ADJACENCY_PENALTY,
    COMPONENT_STANDBY_COUNT_FAIRNESS_PENALTY,
)

# Per scorer §10: "Reward components contribute non-negatively to totalScore;
# penalty components contribute non-positively. Sign orientation is a property
# of the component, not the weight." Per §15: "Operator-supplied weights MUST
# preserve per-component sign orientation: a reward component remains a reward,
# a penalty component remains a penalty, regardless of the numeric weight the
# operator supplies." score(...) validates these classifications at entry.
PENALTY_COMPONENTS: frozenset[str] = frozenset(
    {
        COMPONENT_UNFILLED_PENALTY,
        COMPONENT_POINT_BALANCE_WITHIN_SECTION,
        COMPONENT_POINT_BALANCE_GLOBAL,
        COMPONENT_SPACING_PENALTY,
        COMPONENT_PRE_LEAVE_PENALTY,
        COMPONENT_STANDBY_ADJACENCY_PENALTY,
        COMPONENT_STANDBY_COUNT_FAIRNESS_PENALTY,
    }
)
REWARD_COMPONENTS: frozenset[str] = frozenset(
    {
        COMPONENT_CR_REWARD,
        COMPONENT_DUAL_ELIGIBLE_ICU_BONUS,
    }
)
# Sanity: classifications partition the component set exactly.
assert PENALTY_COMPONENTS | REWARD_COMPONENTS == set(ALL_COMPONENTS)
assert PENALTY_COMPONENTS.isdisjoint(REWARD_COMPONENTS)


class ScoreDirection(str, Enum):
    """Score direction is fixed to `HIGHER_IS_BETTER` per blueprint §5 +
    domain_model.md §4.2 / §11.1 + scorer §10. A scorer implementation
    MUST NOT emit a different value."""

    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"


@dataclass(frozen=True)
class ScoringConfig:
    """Scoring configuration carrying component weights and per-day call-point
    weights per scorer v2 §11 (`docs/scorer_contract.md` v2; bumped from v1
    under `docs/decision_log.md` D-0037).

    `weights` MUST include an entry for every first-release component
    identifier per §11; missing entries are a configuration defect.

    `pointRules` carries per-`(slotType, dateKey)` call-point weights derived
    from the operator-facing per-day call-point cells declared in
    `docs/template_artifact_contract.md` §9 `pointRows`. `pointBalance*`
    components MUST consume `pointRules` rather than a "1 point per call"
    placeholder. Coverage is total: `pointRules` MUST contain an entry for
    every `(slotType, dateKey)` pair where `slotType` is a call-slot per
    `slotTypes[].slotKind == "CALL"` and `dateKey` ranges over the period's
    `dayRecords`. Missing keys cause `score()` to raise — there is no silent
    fallback to `1.0` (D-0038 reverses the original D-0037 sub-decision 5
    silent-fallback rule; producer obligation lives on the parser overlay
    path per `docs/parser_normalizer_contract.md` §9, where sheet-cell overlay
    plus template-default backstop together cover the cross-product).

    First-release `crReward` curve is fixed at the harmonic shape (kth
    honored CR per doctor contributes `weights[crReward] / k`) — strict-
    monotonic-decrease holds per §12. Operator-tuneable curve parameters
    are explicitly deferred per scorer §19 to FW-0007.

    First-release default weights are sign-correct (rewards positive,
    penalties negative) placeholders; the v1 reference-pass tuning lands
    separately per FW-0014.
    """

    weights: dict[str, float]
    pointRules: dict[tuple[str, str], float]
    # `pointRules` is required (no default) per scorer v2 §11. Per D-0038, it
    # MUST cover the full cross-product of call-slot slotTypes × period days;
    # missing keys raise at score() time. The construction-time required-field
    # rule (D-0037 sub-decision 9 / PR #82) and the per-key fail-loud rule
    # (D-0038) are architectural mates: producers cannot omit the field, and
    # they cannot omit individual keys either.

    @staticmethod
    def first_release_defaults(model: "NormalizedModel") -> "ScoringConfig":
        """First-release placeholder defaults. Sign-correct (rewards positive,
        penalties negative) and magnitude-reasonable for proving the pipeline
        works end-to-end. v1 magnitude tuning lands per FW-0014.

        `pointRules` is built as a uniform-1.0 cross-product over the model's
        call-slots × period days (test/fixture-grade coverage). The production
        parser overlay produces non-uniform values from `pointRows.defaultRule`
        weekday/weekend mapping (1.0 / 1.75 / 2.0 / 1.5) overlaid with sheet
        cells per `docs/parser_normalizer_contract.md` §9; this factory is for
        ad-hoc test fixtures and degenerate "no operator overrides + uniform
        defaults" callers, NOT a model of the production overlay.
        """
        return ScoringConfig(
            weights={
                COMPONENT_UNFILLED_PENALTY: -100.0,
                COMPONENT_POINT_BALANCE_WITHIN_SECTION: -1.0,
                COMPONENT_POINT_BALANCE_GLOBAL: -1.0,
                COMPONENT_SPACING_PENALTY: -2.0,
                COMPONENT_PRE_LEAVE_PENALTY: -10.0,
                COMPONENT_CR_REWARD: 5.0,
                COMPONENT_DUAL_ELIGIBLE_ICU_BONUS: 0.5,
                COMPONENT_STANDBY_ADJACENCY_PENALTY: -3.0,
                COMPONENT_STANDBY_COUNT_FAIRNESS_PENALTY: -1.0,
            },
            pointRules=uniform_point_rules(model),
        )


def uniform_point_rules(
    model: "NormalizedModel", weight: float = 1.0
) -> dict[tuple[str, str], float]:
    """Build a `pointRules` map that assigns `weight` to every
    `(call-slot slotType, dateKey)` pair from the model's cross-product.

    Intended for test fixtures and ad-hoc callers needing a complete
    `pointRules` that satisfies D-0038 producer-coverage. NOT a model of the
    production parser overlay — that path computes per-day defaults from
    `pointRows.defaultRule` (weekday/weekend mapping per
    `docs/template_artifact_contract.md` §9) and overlays sheet cells on top.
    """
    call_slot_types = [
        st.slotType for st in model.slotTypes if st.slotKind == "CALL"
    ]
    return {
        (slot_type, day.dateKey): weight
        for slot_type in call_slot_types
        for day in model.period.days
    }


@dataclass(frozen=True)
class ScoreResult:
    """Public scorer output per scorer §10.

    Contract invariants enforced via factory:
    - `components` MUST include every first-release component identifier
      (even when contributing zero).
    - `direction` MUST be the `HIGHER_IS_BETTER` literal.
    - `totalScore` MUST equal the signed sum of component contributions.

    `context` is a free-shape mapping reserved for diagnostic detail (e.g.,
    per-component sub-breakdowns for explainability per §11.1's "optional
    deeper breakdowns for diagnostics/explainability").
    """

    totalScore: float
    components: dict[str, float]
    direction: ScoreDirection = ScoreDirection.HIGHER_IS_BETTER
    context: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_components(
        components: dict[str, float],
        *,
        context: dict[str, Any] | None = None,
    ) -> "ScoreResult":
        """Construct a `ScoreResult` from per-component contributions.
        Validates §10's "every first-release component identifier MUST appear"
        rule and computes `totalScore` as the signed sum."""
        missing = [c for c in ALL_COMPONENTS if c not in components]
        if missing:
            raise ValueError(
                f"ScoreResult.components missing required first-release "
                f"identifiers per docs/scorer_contract.md §10: {missing}"
            )
        extra = [c for c in components if c not in ALL_COMPONENTS]
        if extra:
            raise ValueError(
                f"ScoreResult.components contains unknown identifiers "
                f"(not in docs/domain_model.md §11.2): {extra}"
            )
        total = sum(components[c] for c in ALL_COMPONENTS)
        return ScoreResult(
            totalScore=total,
            components=dict(components),
            direction=ScoreDirection.HIGHER_IS_BETTER,
            context=dict(context) if context else {},
        )
