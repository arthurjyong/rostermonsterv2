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
from rostermonster.scorer import ScoringConfig

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
        downstream-consumable; `scoringConfig` is present and carries the
        parser's overlay of operator-edited sheet values onto template
        defaults per §9 (added under `docs/decision_log.md` D-0037). Non-
        blocking issues may still be present in `issues` per §15.
      - `consumability = NON_CONSUMABLE`: `normalizedModel = None` AND
        `scoringConfig = None`. The complete authoritative parser-stage issue
        list lives in `issues`. Partial normalized side payloads MUST NOT be
        emitted (§9).
    """

    consumability: Consumability
    issues: tuple[ValidationIssue, ...]
    normalizedModel: NormalizedModel | None
    scoringConfig: ScoringConfig | None = None

    @staticmethod
    def consumable(
        normalizedModel: NormalizedModel,
        scoringConfig: ScoringConfig,
        issues: tuple[ValidationIssue, ...] = (),
    ) -> "ParserResult":
        """Construct a `CONSUMABLE` result. `issues` may carry non-blocking
        findings per parser_normalizer_contract.md §15. Both
        `normalizedModel` and `scoringConfig` are required on the
        CONSUMABLE branch per §9 (D-0037)."""
        return ParserResult(
            consumability=Consumability.CONSUMABLE,
            issues=issues,
            normalizedModel=normalizedModel,
            scoringConfig=scoringConfig,
        )

    @staticmethod
    def non_consumable(issues: tuple[ValidationIssue, ...]) -> "ParserResult":
        """Construct a `NON_CONSUMABLE` result. Both `normalizedModel` and
        `scoringConfig` are forced to `None` per parser_normalizer_contract.md
        §9 (D-0037 — same admission discipline applies to both)."""
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
            scoringConfig=None,
        )
