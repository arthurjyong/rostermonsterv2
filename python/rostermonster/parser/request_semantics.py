"""ICU/HD first-release request grammar parser per
`docs/request_semantics_contract.md`.

Implements:
- §6 lexical and grammar rules (comma-separated only, trim-tolerant,
  case-insensitive, blank-is-valid),
- §7 accepted raw token vocabulary,
- §9 raw-to-canonical mapping,
- §10 canonical-to-machine-effect mapping,
- §11 combination handling (preserve recognized set, union effects),
- §12 duplicate handling (canonicalize, non-blocking issue),
- §13 unknown / malformed handling (NON_CONSUMABLE for any unknown token or
  broken grammar),
- §15 canonical deterministic ordering for emitted sets.

Bound by `docs/template_artifact_contract.md` §8 to ICU/HD first release via
`requestSemanticsBinding.contractId == "ICU_HD_REQUEST_SEMANTICS"` and
`contractVersion == 1`.
"""

from __future__ import annotations

from dataclasses import dataclass

from rostermonster.domain import (
    CanonicalRequestClass,
    IssueSeverity,
    MachineEffect,
    ValidationIssue,
)

# request_semantics_contract.md §7 — accepted raw token vocabulary.
ACCEPTED_RAW_TOKENS: frozenset[str] = frozenset(
    {
        "CR",
        "NC",
        "AL",
        "TL",
        "SL",
        "MC",
        "HL",
        "NSL",
        "OPL",
        "EXAM",
        "EMCC",
        "PM_OFF",
    }
)

# request_semantics_contract.md §9 — raw-to-canonical mapping.
RAW_TO_CANONICAL: dict[str, CanonicalRequestClass] = {
    "CR": CanonicalRequestClass.CR,
    "NC": CanonicalRequestClass.NC,
    "AL": CanonicalRequestClass.FULL_DAY_OFF,
    "TL": CanonicalRequestClass.FULL_DAY_OFF,
    "SL": CanonicalRequestClass.FULL_DAY_OFF,
    "MC": CanonicalRequestClass.FULL_DAY_OFF,
    "HL": CanonicalRequestClass.FULL_DAY_OFF,
    "NSL": CanonicalRequestClass.FULL_DAY_OFF,
    "OPL": CanonicalRequestClass.FULL_DAY_OFF,
    "EXAM": CanonicalRequestClass.FULL_DAY_OFF,
    "EMCC": CanonicalRequestClass.PM_OFF,
    "PM_OFF": CanonicalRequestClass.PM_OFF,
}

# request_semantics_contract.md §10 — canonical-to-machine-effect mapping.
CANONICAL_TO_EFFECTS: dict[CanonicalRequestClass, frozenset[MachineEffect]] = {
    CanonicalRequestClass.CR: frozenset({MachineEffect.callPreferencePositive}),
    CanonicalRequestClass.NC: frozenset({MachineEffect.sameDayHardBlock}),
    CanonicalRequestClass.FULL_DAY_OFF: frozenset(
        {
            MachineEffect.sameDayHardBlock,
            MachineEffect.prevDayCallSoftPenaltyTrigger,
        }
    ),
    CanonicalRequestClass.PM_OFF: frozenset(
        {
            MachineEffect.sameDayHardBlock,
            MachineEffect.prevDayCallSoftPenaltyTrigger,
        }
    ),
}

# Issue codes. Not standardized by the contract per §13, but stable within this
# implementation so tests and downstream tooling can assert on them.
ISSUE_REQUEST_UNKNOWN_TOKEN = "REQUEST_UNKNOWN_TOKEN"
ISSUE_REQUEST_MALFORMED_GRAMMAR = "REQUEST_MALFORMED_GRAMMAR"
ISSUE_REQUEST_DUPLICATE_TOKEN = "REQUEST_DUPLICATE_TOKEN"
ISSUE_REQUEST_CR_PLUS_BLOCKING = "REQUEST_CR_PLUS_BLOCKING"


@dataclass(frozen=True)
class RequestParseResult:
    """Outcome of parsing one raw request text.

    `consumable=True` means deterministic downstream-governing facts are
    derivable; non-blocking findings may still appear in `issues` per
    request_semantics_contract.md §11 / §12. `consumable=False` means the
    upstream parser must surface NON_CONSUMABLE for the snapshot per §13.
    """

    consumable: bool
    recognizedRawTokens: tuple[str, ...]
    canonicalClasses: tuple[CanonicalRequestClass, ...]
    machineEffects: tuple[MachineEffect, ...]
    issues: tuple[ValidationIssue, ...]


_FORBIDDEN_DELIMITERS = ("/", ";", ".", "|", "\\")


def parse_request_text(
    raw_text: str,
    *,
    doctor_id: str,
    date_key: str,
) -> RequestParseResult:
    """Parse one raw request cell text under ICU/HD first-release grammar.

    `doctor_id` and `date_key` are echoed into emitted issue contexts so the
    upstream parser can surface where in the snapshot a finding was raised.
    """
    issues: list[ValidationIssue] = []
    base_context = {"doctorId": doctor_id, "dateKey": date_key}

    # Blank string after trim is valid and means no request codes (§6 rule 4).
    if raw_text is None:
        raw_text = ""
    trimmed = raw_text.strip()
    if trimmed == "":
        return RequestParseResult(
            consumable=True,
            recognizedRawTokens=(),
            canonicalClasses=(),
            machineEffects=(),
            issues=(),
        )

    # §6 rule 5 — non-comma delimiters are not accepted, not auto-corrected.
    for forbidden in _FORBIDDEN_DELIMITERS:
        if forbidden in trimmed:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_REQUEST_MALFORMED_GRAMMAR,
                    message=(
                        f"Request text uses non-comma delimiter "
                        f"{forbidden!r}; comma-separated grammar is the only "
                        f"accepted form per docs/request_semantics_contract.md §6."
                    ),
                    context={
                        **base_context,
                        "rawRequestText": raw_text,
                        "forbiddenDelimiter": forbidden,
                    },
                )
            )
            return RequestParseResult(
                consumable=False,
                recognizedRawTokens=(),
                canonicalClasses=(),
                machineEffects=(),
                issues=tuple(issues),
            )

    # §6 rules 1-3 — comma-separated, trim-tolerant, case-insensitive.
    raw_token_strings = [
        segment.strip().upper()
        for segment in trimmed.split(",")
        if segment.strip() != ""
    ]

    # §13 — unknown tokens make the request NON_CONSUMABLE; parser must not guess.
    unknown_tokens = [t for t in raw_token_strings if t not in ACCEPTED_RAW_TOKENS]
    if unknown_tokens:
        for unknown in unknown_tokens:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_REQUEST_UNKNOWN_TOKEN,
                    message=(
                        f"Unknown request token {unknown!r}; accepted raw tokens "
                        f"are listed in docs/request_semantics_contract.md §7."
                    ),
                    context={
                        **base_context,
                        "rawRequestText": raw_text,
                        "unknownToken": unknown,
                    },
                )
            )
        return RequestParseResult(
            consumable=False,
            recognizedRawTokens=(),
            canonicalClasses=(),
            machineEffects=(),
            issues=tuple(issues),
        )

    # §12 — duplicate handling: canonicalize to stable sets, emit non-blocking issue.
    if len(raw_token_strings) != len(set(raw_token_strings)):
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.WARNING,
                code=ISSUE_REQUEST_DUPLICATE_TOKEN,
                message=(
                    "Request text contains duplicate recognized tokens; "
                    "canonicalized to a stable set per "
                    "docs/request_semantics_contract.md §12."
                ),
                context={**base_context, "rawRequestText": raw_text},
            )
        )

    recognized_raw = tuple(sorted(set(raw_token_strings)))
    canonical_set = {RAW_TO_CANONICAL[t] for t in recognized_raw}

    # §11 normative special case — CR + blocking-class combination is CONSUMABLE
    # but emits a non-blocking issue.
    blocking_classes = {
        CanonicalRequestClass.NC,
        CanonicalRequestClass.FULL_DAY_OFF,
        CanonicalRequestClass.PM_OFF,
    }
    if (
        CanonicalRequestClass.CR in canonical_set
        and (canonical_set & blocking_classes)
    ):
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.WARNING,
                code=ISSUE_REQUEST_CR_PLUS_BLOCKING,
                message=(
                    "Request text combines CR with a blocking class; "
                    "preserved as CONSUMABLE with full union of effects per "
                    "docs/request_semantics_contract.md §11."
                ),
                context={**base_context, "rawRequestText": raw_text},
            )
        )

    # §11 — machine effects are full union across canonical classes.
    effects_set: set[MachineEffect] = set()
    for canonical in canonical_set:
        effects_set |= CANONICAL_TO_EFFECTS[canonical]

    # §15 — emit canonical deterministic ordering for sets. Sorted by value
    # name gives reproducible ordering across runs and across re-runs of
    # canonical-class membership.
    canonical_sorted = tuple(sorted(canonical_set, key=lambda c: c.value))
    effects_sorted = tuple(sorted(effects_set, key=lambda e: e.value))

    return RequestParseResult(
        consumable=True,
        recognizedRawTokens=recognized_raw,
        canonicalClasses=canonical_sorted,
        machineEffects=effects_sorted,
        issues=tuple(issues),
    )
