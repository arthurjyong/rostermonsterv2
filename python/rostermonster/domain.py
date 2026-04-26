"""Core normalized domain types per `docs/domain_model.md`.

These are the post-parser/post-normalizer types that downstream stages (rule
engine, scorer, solver, selector) consume. Parser populates them during
admission; the normalizer side adds parser-stage provenance per
`docs/parser_normalizer_contract.md` §16 (recoverable linkage back to origin
snapshot records/locators on snapshot-derived entities) and ensures the
emitted normalized model satisfies the §17 explicit-handoff guarantees.

Provenance shape (first release): each snapshot-derived entity carries a
`provenance` field typed as the relevant `sourceLocator` from
`rostermonster.snapshot`. Concrete provenance field-shape standardization
across all entities is deferred per parser_normalizer §16 and §19; this is
the simplest stable shape that satisfies the §16 traceability obligation
without inventing a new field-shape standard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rostermonster.snapshot import (
    DayLocator,
    DoctorLocator,
    PrefilledAssignmentLocator,
    RequestLocator,
)


class IssueSeverity(str, Enum):
    """Severity tag on `ValidationIssue` (domain_model.md §13).

    `ERROR` denotes admission-relevant findings (drives `NON_CONSUMABLE` when
    accumulated). `WARNING` denotes non-blocking findings retained for
    diagnostics on `CONSUMABLE` outputs (parser_normalizer_contract.md §15).
    `INFO` is reserved for narrative/diagnostic content.
    """

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class ValidationIssue:
    """Shared structured issue shape (domain_model.md §13).

    Used uniformly across parsing, normalization, rule, and allocation
    validation outputs. Minimum fields: `severity`, `code`, `message`,
    `context`. `context` is a free-shape mapping carrying entity references /
    paths / dates / doctor / slot identifiers per the shared-shape direction.
    """

    severity: IssueSeverity
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


class CanonicalRequestClass(str, Enum):
    """Canonical normalized request classes (request_semantics_contract.md §8)."""

    CR = "CR"
    NC = "NC"
    FULL_DAY_OFF = "FULL_DAY_OFF"
    PM_OFF = "PM_OFF"


class MachineEffect(str, Enum):
    """Canonical machine-effect vocabulary (request_semantics_contract.md §10)."""

    sameDayHardBlock = "sameDayHardBlock"
    prevDayCallSoftPenaltyTrigger = "prevDayCallSoftPenaltyTrigger"
    callPreferencePositive = "callPreferencePositive"


@dataclass(frozen=True)
class RosterDay:
    """One date in the roster period (domain_model.md §7.2).

    `provenance` traces back to the snapshot `dayRecord` per
    parser_normalizer_contract.md §16.
    """

    dateKey: str
    dayIndex: int
    provenance: DayLocator


@dataclass(frozen=True)
class RosterPeriod:
    """Scope object for one roster run (domain_model.md §7.1)."""

    periodId: str
    periodLabel: str
    days: tuple[RosterDay, ...]


@dataclass(frozen=True)
class Doctor:
    """Assignable doctor (domain_model.md §7.3).

    `doctorId` is runtime identity; `displayName` is sheet-facing identity.
    `groupId` is parser-resolved canonical membership per §7.3
    (snapshot.sectionKey → inputSheetLayout.sections[].groupId).
    `provenance` traces back to the snapshot `doctorRecord` per
    parser_normalizer_contract.md §16.
    """

    doctorId: str
    displayName: str
    groupId: str
    provenance: DoctorLocator


@dataclass(frozen=True)
class DoctorGroup:
    """Template-defined doctor group (domain_model.md §7.4)."""

    groupId: str


@dataclass(frozen=True)
class SlotTypeDefinition:
    """Normalized slot metadata (domain_model.md §7.6).

    First-release minimum required fields per §7.6: `slotType` (identity) +
    `displayLabel`. `slotFamily` and `slotKind` are first-release optional
    semantic metadata sourced from the template artifact's slot record.
    `workloadWeight` is deferred (FW-0009). Template-only entity — no
    snapshot provenance per parser_normalizer_contract.md §16.
    """

    slotType: str
    displayLabel: str
    slotFamily: str
    slotKind: str


@dataclass(frozen=True)
class SlotDemand:
    """Explicit demand per `(dateKey, slotType)` (domain_model.md §7.7).

    Origin includes one snapshot record (the day) crossed with one template
    declaration (the slot). `provenance` traces back to the day side per
    parser_normalizer_contract.md §16; the slot side is template-only and
    needs no snapshot provenance.
    """

    dateKey: str
    slotType: str
    requiredCount: int
    provenance: DayLocator


@dataclass(frozen=True)
class EligibilityRule:
    """Baseline `slot -> groups` eligibility (domain_model.md §9.1)."""

    slotType: str
    eligibleGroups: tuple[str, ...]


@dataclass(frozen=True)
class FixedAssignment:
    """Operator-prefilled assignment admitted by parser (domain_model.md §7.8, §10.1).

    First-class normalized input, not an allocation result. Solver fills only
    residual unfilled demand after accounting for fixed assignments.
    `provenance` traces back to the snapshot `prefilledAssignmentRecord` per
    parser_normalizer_contract.md §16.
    """

    dateKey: str
    slotType: str
    doctorId: str
    provenance: PrefilledAssignmentLocator


@dataclass(frozen=True)
class Request:
    """Per-doctor per-date request (domain_model.md §8.1).

    `recognizedRawTokens`, `canonicalClasses`, and `machineEffects` are
    canonical-deterministic-ordered sets per request_semantics_contract.md §15.

    `parseIssues` mirrors any non-blocking parse issues raised on this
    specific request per parser_normalizer_contract.md §10 rule 4: request
    parse issues must also appear on the relevant normalized `Request` when a
    normalized `Request` exists in a `CONSUMABLE` output. This is supplemental
    to the authoritative top-level `ParserResult.issues` channel (§10 rules 1
    and 6) — entity-local content is never the sole record.

    `provenance` traces back to the snapshot `requestRecord` per
    parser_normalizer_contract.md §16.
    """

    doctorId: str
    dateKey: str
    rawRequestText: str
    recognizedRawTokens: tuple[str, ...]
    canonicalClasses: tuple[CanonicalRequestClass, ...]
    machineEffects: tuple[MachineEffect, ...]
    provenance: RequestLocator
    parseIssues: tuple[ValidationIssue, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DailyEffectState:
    """Day-level normalized machine effect state (domain_model.md §8.2).

    Derived from per-doctor `Request` machine effects. Keyed by
    `(doctorId, dateKey)`; carries the union of effects firing on that day.
    `provenance` traces back to the originating `requestRecord` per
    parser_normalizer_contract.md §16 (one Request → one DailyEffectState in
    first-release one-request-per-cell semantics).
    """

    doctorId: str
    dateKey: str
    effects: tuple[MachineEffect, ...]
    provenance: RequestLocator


@dataclass(frozen=True)
class NormalizedModel:
    """Top-level normalized model emitted on `CONSUMABLE` parser results.

    Post-parser/post-normalizer state ready for downstream consumption per
    parser_normalizer_contract.md §17 (explicit handoff to rule engine).
    Provenance per §16 and any final handoff polish are T2's territory.
    """

    period: RosterPeriod
    doctors: tuple[Doctor, ...]
    doctorGroups: tuple[DoctorGroup, ...]
    slotTypes: tuple[SlotTypeDefinition, ...]
    slotDemand: tuple[SlotDemand, ...]
    eligibility: tuple[EligibilityRule, ...]
    fixedAssignments: tuple[FixedAssignment, ...] = field(default_factory=tuple)
    requests: tuple[Request, ...] = field(default_factory=tuple)
    dailyEffects: tuple[DailyEffectState, ...] = field(default_factory=tuple)
