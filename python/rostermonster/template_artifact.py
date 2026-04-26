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

from dataclasses import dataclass


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
class TemplateArtifact:
    """Parser-consumable template artifact (template_artifact_contract.md §4).

    Full artifact shape includes additional generation-only fields not modeled
    here (point rows, legend, visible labels, anchor cells, etc.). Parser
    admission does not consume those.
    """

    identity: TemplateIdentity
    slots: tuple[SlotDefinition, ...]
    doctorGroups: tuple[DoctorGroupDefinition, ...]
    eligibility: tuple[EligibilityRecord, ...]
    requestSemanticsBinding: RequestSemanticsBinding
    inputSheetSections: tuple[InputSheetSection, ...]
    outputSurfaces: tuple[OutputSurface, ...]
