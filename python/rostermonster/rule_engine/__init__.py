"""Rule engine module per `docs/rule_engine_contract.md`.

Public entry: `evaluate(normalizedModel, ruleState, proposedUnit) → Decision`.

Stateless reference implementation per §13. Implements the five first-release
hard rules per §11 with full-list canonical ordering per §12. First-release
scope is the stateless reference only — no incremental/indexed
implementation lands in C4 (FW-0003 captures the future direction).
"""

from rostermonster.rule_engine.evaluator import evaluate
from rostermonster.rule_engine.result import (
    CANONICAL_ORDER,
    Decision,
    RULE_BACK_TO_BACK_CALL,
    RULE_BASELINE_ELIGIBILITY_FAIL,
    RULE_SAME_DAY_ALREADY_HELD,
    RULE_SAME_DAY_HARD_BLOCK,
    RULE_UNIT_ALREADY_FILLED,
    ViolationReason,
)
from rostermonster.rule_engine.state import RuleState

__all__ = [
    "evaluate",
    "Decision",
    "ViolationReason",
    "RuleState",
    "CANONICAL_ORDER",
    "RULE_BASELINE_ELIGIBILITY_FAIL",
    "RULE_SAME_DAY_HARD_BLOCK",
    "RULE_SAME_DAY_ALREADY_HELD",
    "RULE_UNIT_ALREADY_FILLED",
    "RULE_BACK_TO_BACK_CALL",
]
