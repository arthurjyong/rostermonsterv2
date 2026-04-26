"""ParserResult and admission-decision enum.

Implements parser_normalizer_contract.md §9 (parser outputs) and §10 (issue
schema vs issue channel vs admission decision). `ValidationIssue` and
`IssueSeverity` are shared domain types per `docs/domain_model.md` §13 and
live in `rostermonster.domain`; they are re-exported here for ergonomics
(callers reach them via `from rostermonster.parser import ...`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rostermonster.domain import IssueSeverity, NormalizedModel, ValidationIssue

__all__ = [
    "Consumability",
    "IssueSeverity",
    "ParserResult",
    "ValidationIssue",
]


class Consumability(str, Enum):
    """Binary admission decision (parser_normalizer_contract.md §9, §15)."""

    CONSUMABLE = "CONSUMABLE"
    NON_CONSUMABLE = "NON_CONSUMABLE"


@dataclass(frozen=True)
class ParserResult:
    """Top-level parser handoff (parser_normalizer_contract.md §9).

    Contract rule:
      - `consumability = CONSUMABLE`: `normalizedModel` is present and
        downstream-consumable. Non-blocking issues may still be present in
        `issues` per §15.
      - `consumability = NON_CONSUMABLE`: `normalizedModel = None`. The
        complete authoritative parser-stage issue list lives in `issues`.
        Partial normalized side payloads MUST NOT be emitted (§9).
    """

    consumability: Consumability
    issues: tuple[ValidationIssue, ...]
    normalizedModel: NormalizedModel | None

    @staticmethod
    def consumable(
        normalizedModel: NormalizedModel,
        issues: tuple[ValidationIssue, ...] = (),
    ) -> "ParserResult":
        """Construct a `CONSUMABLE` result. `issues` may carry non-blocking
        findings per parser_normalizer_contract.md §15."""
        return ParserResult(
            consumability=Consumability.CONSUMABLE,
            issues=issues,
            normalizedModel=normalizedModel,
        )

    @staticmethod
    def non_consumable(issues: tuple[ValidationIssue, ...]) -> "ParserResult":
        """Construct a `NON_CONSUMABLE` result. `normalizedModel` is forced to
        `None` per parser_normalizer_contract.md §9."""
        if not issues:
            raise ValueError(
                "NON_CONSUMABLE ParserResult requires at least one issue "
                "(parser_normalizer_contract.md §10 — every parser-stage issue "
                "affecting consumability must appear in ParserResult.issues)"
            )
        return ParserResult(
            consumability=Consumability.NON_CONSUMABLE,
            issues=issues,
            normalizedModel=None,
        )
