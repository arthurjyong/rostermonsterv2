"""Snapshot input types per `docs/snapshot_contract.md`.

Snapshot is pre-interpretation raw input. Parser interprets and normalizes
downstream. These dataclasses model exactly the shape declared in
snapshot_contract.md sections 5-12; they do not embed downstream semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PhysicalSourceRef:
    """Concrete sheet-facing extraction trace (snapshot_contract.md §12)."""

    sheetName: str
    sheetGid: str
    a1Refs: tuple[str, ...]


@dataclass(frozen=True)
class DoctorLocator:
    """`surfaceKey=doctorRows` locator (snapshot_contract.md §10)."""

    sectionKey: str
    doctorIndexInSection: int
    surfaceKey: str = "doctorRows"


@dataclass(frozen=True)
class DayLocator:
    """`surfaceKey=dayAxis` locator (snapshot_contract.md §10)."""

    dayIndex: int
    surfaceKey: str = "dayAxis"


@dataclass(frozen=True)
class RequestLocator:
    """`surfaceKey=requestCells` locator (snapshot_contract.md §10)."""

    sourceDoctorKey: str
    dayIndex: int
    surfaceKey: str = "requestCells"


@dataclass(frozen=True)
class PrefilledAssignmentLocator:
    """`surfaceKey=outputMapping` locator (snapshot_contract.md §10)."""

    surfaceId: str
    rowOffset: int
    dayIndex: int
    surfaceKey: str = "outputMapping"


@dataclass(frozen=True)
class DoctorRecord:
    """Raw doctor record (snapshot_contract.md §7)."""

    sourceDoctorKey: str
    displayName: str
    rawSectionText: str
    sourceLocator: DoctorLocator
    physicalSourceRef: PhysicalSourceRef


@dataclass(frozen=True)
class DayRecord:
    """Raw day record (snapshot_contract.md §8)."""

    dayIndex: int
    rawDateText: str
    sourceLocator: DayLocator
    physicalSourceRef: PhysicalSourceRef


@dataclass(frozen=True)
class RequestRecord:
    """Raw request record (snapshot_contract.md §9)."""

    sourceDoctorKey: str
    dayIndex: int
    rawRequestText: str
    sourceLocator: RequestLocator
    physicalSourceRef: PhysicalSourceRef


@dataclass(frozen=True)
class PrefilledAssignmentRecord:
    """Raw prefilled assignment record (snapshot_contract.md §11)."""

    dayIndex: int
    rawAssignedDoctorText: str
    surfaceId: str
    rowOffset: int
    sourceLocator: PrefilledAssignmentLocator
    physicalSourceRef: PhysicalSourceRef


@dataclass(frozen=True)
class PeriodRef:
    """Period identity (snapshot_contract.md §6)."""

    periodId: str
    periodLabel: str


@dataclass(frozen=True)
class ExtractionSummary:
    """Structural counts only — not a reporting object (snapshot_contract.md §6)."""

    doctorRecordCount: int
    dayRecordCount: int
    requestRecordCount: int
    prefilledAssignmentRecordCount: int


@dataclass(frozen=True)
class SnapshotMetadata:
    """Metadata block (snapshot_contract.md §6)."""

    snapshotId: str
    templateId: str
    templateVersion: int
    sourceSpreadsheetId: str
    sourceTabName: str
    generationTimestamp: str
    periodRef: PeriodRef
    extractionSummary: ExtractionSummary


@dataclass(frozen=True)
class Snapshot:
    """Top-level snapshot (snapshot_contract.md §5)."""

    metadata: SnapshotMetadata
    doctorRecords: tuple[DoctorRecord, ...]
    dayRecords: tuple[DayRecord, ...]
    requestRecords: tuple[RequestRecord, ...]
    prefilledAssignmentRecords: tuple[PrefilledAssignmentRecord, ...] = field(
        default_factory=tuple
    )
