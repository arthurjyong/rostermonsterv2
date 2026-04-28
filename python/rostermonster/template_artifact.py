"""Template artifact input types per `docs/template_artifact_contract.md`.

Models the parser-consumable subset of the template artifact. The full artifact
shape per template_artifact_contract.md §4 has eight required top-level sections
(identity, slots, doctorGroups, eligibility, requestSemanticsBinding,
inputSheetLayout, outputMapping, scoring); this module models the fields the
parser reads at admission time. Generation-only fields (point rows, legend,
visible labels, anchor cells, etc.) are intentionally omitted here because
parser admission does not depend on them.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TemplateIdentity:
    """`identity` section (template_artifact_contract.md §4, §13)."""

    templateId: str
    templateVersion: int
    label: str


@dataclass(frozen=True)
class SlotDefinition:
    """One slot record (template_artifact_contract.md §5)."""

    slotId: str
    label: str
    slotFamily: str
    slotKind: str
    requiredCountPerDay: int


@dataclass(frozen=True)
class DoctorGroupDefinition:
    """One doctor-group record (template_artifact_contract.md §6)."""

    groupId: str


@dataclass(frozen=True)
class EligibilityRecord:
    """One eligibility record (template_artifact_contract.md §7)."""

    slotId: str
    eligibleGroups: tuple[str, ...]


@dataclass(frozen=True)
class RequestSemanticsBinding:
    """`requestSemanticsBinding` section (template_artifact_contract.md §8)."""

    contractId: str
    contractVersion: int


@dataclass(frozen=True)
class InputSheetSection:
    """One `inputSheetLayout.sections[]` record (template_artifact_contract.md §9).

    Carries the section-based doctor-group derivation declarations parser uses
    to resolve canonical doctor groups from snapshot
    `doctorRecord.sourceLocator.sectionKey`.
    """

    sectionKey: str
    groupId: str


@dataclass(frozen=True)
class AssignmentRowDefinition:
    """One `outputMapping.surfaces[].assignmentRows[]` record
    (template_artifact_contract.md §10)."""

    slotId: str
    rowOffset: int


@dataclass(frozen=True)
class OutputSurface:
    """One `outputMapping.surfaces[]` record (template_artifact_contract.md §10).

    Parser uses (surfaceId, assignmentRows) to resolve prefilled-assignment
    cells to their target slot per parser_normalizer_contract.md §14.
    """

    surfaceId: str
    assignmentRows: tuple[AssignmentRowDefinition, ...]


@dataclass(frozen=True)
class PointRowDefaultRule:
    """`pointRows[].defaultRule` shape (template_artifact_contract.md §9).

    Four numeric fields covering the four day-transition cases; the parser
    overlay picks the right field per day-of-week per
    `docs/parser_normalizer_contract.md` §9 backstop rule (used when the
    operator has not edited the corresponding per-day cell). For ICU/HD
    first release the values are `1.0 / 1.75 / 2.0 / 1.5`.
    """

    weekdayToWeekday: float
    weekdayToWeekendOrPublicHoliday: float
    weekendOrPublicHolidayToWeekendOrPublicHoliday: float
    weekendOrPublicHolidayToWeekday: float


@dataclass(frozen=True)
class PointRowDefinition:
    """One `inputSheetLayout.pointRows[]` record
    (template_artifact_contract.md §9).

    `slotType` binding added under `docs/decision_log.md` D-0037 — anchors
    the parser overlay's `(callPointRowKey, dayIndex) → (slotType, dateKey)`
    mapping per `docs/parser_normalizer_contract.md` §9. MUST reference a
    `slots[].slotId` whose `slotKind == "CALL"`. Standby and other non-call
    slots have no point row.
    """

    rowKey: str
    slotType: str
    label: str
    defaultRule: PointRowDefaultRule


@dataclass(frozen=True)
class TemplateArtifact:
    """Parser-consumable template artifact (template_artifact_contract.md §4).

    Full artifact shape includes additional generation-only fields not modeled
    here (legend, visible labels, anchor cells, etc.). The parser-relevant
    additions made under D-0037 — `pointRows` (for the call-point overlay
    backstop) and `componentWeights` (for the component-weight overlay
    backstop) — ARE modeled here because the parser consumes them at overlay
    time per `docs/parser_normalizer_contract.md` §9.
    """

    identity: TemplateIdentity
    slots: tuple[SlotDefinition, ...]
    doctorGroups: tuple[DoctorGroupDefinition, ...]
    eligibility: tuple[EligibilityRecord, ...]
    requestSemanticsBinding: RequestSemanticsBinding
    inputSheetSections: tuple[InputSheetSection, ...]
    outputSurfaces: tuple[OutputSurface, ...]
    pointRows: tuple[PointRowDefinition, ...] = field(default_factory=tuple)
    componentWeights: dict[str, float] = field(default_factory=dict)
