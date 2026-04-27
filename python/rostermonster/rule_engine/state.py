"""`RuleState` value object per `docs/rule_engine_contract.md` §9.

The set of assignments already present in the candidate under construction —
including `FixedAssignment`-derived entries from the normalized model and any
solver-placed `AssignmentUnit` entries accumulated so far. Stateless wrapper;
the evaluator builds local indexes on each `evaluate()` call (§13 permits
internal caching but the public RuleState shape stays as a thin tuple).
"""

from __future__ import annotations

from dataclasses import dataclass

from rostermonster.domain import AssignmentUnit


@dataclass(frozen=True)
class RuleState:
    """Existing assignments in the candidate under construction.

    Per §9: `ruleState` MUST be a pure derivative of the `normalizedModel`
    plus solver-placed assignments. Callers MUST NOT smuggle additional
    state beyond `assignments`.
    """

    assignments: tuple[AssignmentUnit, ...]

    @staticmethod
    def empty() -> "RuleState":
        """Empty state — no assignments placed yet (start of a search)."""
        return RuleState(assignments=())
