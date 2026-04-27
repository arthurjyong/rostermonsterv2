"""Rule engine result types per `docs/rule_engine_contract.md` §10–§12.

`Decision` is the public output shape. `ViolationReason` is the per-rule
finding emitted when a hard rule fires. The contract uses `ViolationReason`
vocabulary (not `ValidationIssue`) to keep parser-stage admission concerns
(which use `ValidationIssue`) distinct from rule-engine validity decisions
on a single proposed placement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Five first-release hard-rule codes per docs/rule_engine_contract.md §11,
# in canonical cheapest-first ordering per §12.
RULE_BASELINE_ELIGIBILITY_FAIL = "BASELINE_ELIGIBILITY_FAIL"
RULE_SAME_DAY_HARD_BLOCK = "SAME_DAY_HARD_BLOCK"
RULE_SAME_DAY_ALREADY_HELD = "SAME_DAY_ALREADY_HELD"
RULE_UNIT_ALREADY_FILLED = "UNIT_ALREADY_FILLED"
RULE_BACK_TO_BACK_CALL = "BACK_TO_BACK_CALL"

# Canonical ordering tuple; the order here IS §12's normative ordering and is
# used by the evaluator to sort emitted reasons.
CANONICAL_ORDER: tuple[str, ...] = (
    RULE_BASELINE_ELIGIBILITY_FAIL,
    RULE_SAME_DAY_HARD_BLOCK,
    RULE_SAME_DAY_ALREADY_HELD,
    RULE_UNIT_ALREADY_FILLED,
    RULE_BACK_TO_BACK_CALL,
)


@dataclass(frozen=True)
class ViolationReason:
    """One fired hard-rule violation (rule_engine_contract.md §10).

    `code` is one of the five first-release codes above. `context` carries
    the references that pinpoint the violation (proposedUnit fields, the
    conflicting unit, etc.) for downstream diagnostic surfaces.
    """

    code: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    """Public output of `evaluate(...)` (rule_engine_contract.md §10, §12).

    Contract rule:
      - `valid = True`: `reasons` MUST be empty.
      - `valid = False`: `reasons` MUST be non-empty AND ordered per §12 AND
        contain every applicable violation (full-list, not first-hit).
    """

    valid: bool
    reasons: tuple[ViolationReason, ...]

    @staticmethod
    def admit() -> "Decision":
        """Construct an admit (`valid=True`) Decision with no reasons."""
        return Decision(valid=True, reasons=())

    @staticmethod
    def reject(reasons: tuple[ViolationReason, ...]) -> "Decision":
        """Construct a reject (`valid=False`) Decision; `reasons` MUST be
        non-empty per §10."""
        if not reasons:
            raise ValueError(
                "Decision.reject requires at least one ViolationReason "
                "(rule_engine_contract.md §10 — when valid=False, reasons "
                "MUST contain at least one entry)"
            )
        return Decision(valid=False, reasons=reasons)
