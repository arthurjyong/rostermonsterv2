"""Core normalized domain types per `docs/domain_model.md`.

These are the post-parser/post-normalizer types that downstream stages (rule
engine, scorer, solver, selector) consume. Parser populates them during
admission; T2 (normalizer side) will refine provenance per §16 and explicit
handoff per §17.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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
    """One date in the roster period (domain_model.md §7.2)."""

    dateKey: str
    dayIndex: int


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
    """

    doctorId: str
    displayName: str
    groupId: str


@dataclass(frozen=True)
class DoctorGroup:
    """Template-defined doctor group (domain_model.md §7.4)."""

    groupId: str


@dataclass(frozen=True)
class SlotTypeDefinition:
    """Normalized slot metadata (domain_model.md §7.6).

    First-release minimum required fields per §7.6: `slotType` (identity) +
    `displayLabel`. `workloadWeight` is deferred (FW-0009).
    """

    slotType: str
    slotFamily: str
    slotKind: str


@dataclass(frozen=True)
class SlotDemand:
    """Explicit demand per `(dateKey, slotType)` (domain_model.md §7.7)."""

    dateKey: str
    slotType: str
    requiredCount: int


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
    """

    dateKey: str
    slotType: str
    doctorId: str


@dataclass(frozen=True)
class Request:
    """Per-doctor per-date request (domain_model.md §8.1).

    `recognizedRawTokens`, `canonicalClasses`, and `machineEffects` are
    canonical-deterministic-ordered sets per request_semantics_contract.md §15.
    """

    doctorId: str
    dateKey: str
    rawRequestText: str
    recognizedRawTokens: tuple[str, ...]
    canonicalClasses: tuple[CanonicalRequestClass, ...]
    machineEffects: tuple[MachineEffect, ...]


@dataclass(frozen=True)
class DailyEffectState:
    """Day-level normalized machine effect state (domain_model.md §8.2).

    Derived from per-doctor `Request` machine effects. Keyed by
    `(doctorId, dateKey)`; carries the union of effects firing on that day.
    """

    doctorId: str
    dateKey: str
    effects: tuple[MachineEffect, ...]


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
