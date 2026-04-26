"""Parser side of the parser/normalizer module per `docs/parser_normalizer_contract.md`.

Public entry: `parse(snapshot, template_artifact) -> ParserResult`.

Implements the admission machinery (§13 structural validation + §14 semantic
admission, including the `FixedAssignment` scoped admission exception) and
emits `ParserResult` per §9. T2 (normalizer side) refines provenance per §16
and explicit handoff to the rule engine per §17.
"""

from rostermonster.parser.admission import parse
from rostermonster.parser.result import (
    Consumability,
    IssueSeverity,
    ParserResult,
    ValidationIssue,
)

__all__ = [
    "parse",
    "ParserResult",
    "ValidationIssue",
    "Consumability",
    "IssueSeverity",
]
