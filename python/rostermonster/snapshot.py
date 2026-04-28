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
class ComponentWeightLocator:
    """`surfaceKey=scorerConfigCells` locator (snapshot_contract.md §10,
    added under `docs/decision_log.md` D-0037)."""

    componentId: str
    surfaceKey: str = "scorerConfigCells"


@dataclass(frozen=True)
class CallPointLocator:
    """`surfaceKey=callPointCells` locator (snapshot_contract.md §10,
    added under `docs/decision_log.md` D-0037)."""

    callPointRowKey: str
    dayIndex: int
    surfaceKey: str = "callPointCells"


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
class ComponentWeightRecord:
    """Raw component-weight record (snapshot_contract.md §11A, added under
    `docs/decision_log.md` D-0037).

    Carries the operator-edited weight value from the launcher-generated
    Scorer Config tab. Records are raw snapshot facts — no parser-stage
    interpretation at snapshot layer. Blank cells produce records with empty
    `rawValue`, matching `requestRecords` blank-cell discipline per §9.
    Records do not carry sign-orientation classification (parser knows the
    component-to-sign mapping from `docs/scorer_contract.md` §10 / §15).
    """

    componentId: str
    rawValue: str
    sourceLocator: ComponentWeightLocator
    physicalSourceRef: PhysicalSourceRef


@dataclass(frozen=True)
class CallPointRecord:
    """Raw per-day call-point record (snapshot_contract.md §11A, added under
    `docs/decision_log.md` D-0037).

    Carries the operator-editable per-day call-point cell value from the
    request-entry sheet. The row identities are template-declared per
    `docs/template_artifact_contract.md` §9 (`pointRows.rowKey`); for
    ICU/HD first release these are `MICU_CALL_POINT` and `MHD_CALL_POINT`.
    Blank cells emit records with empty `rawValue`, same discipline as
    `requestRecords` per §9.
    """

    callPointRowKey: str
    dayIndex: int
    rawValue: str
    sourceLocator: CallPointLocator
    physicalSourceRef: PhysicalSourceRef


@dataclass(frozen=True)
class ScoringConfigRecords:
    """`scoringConfigRecords` top-level component on `Snapshot`
    (snapshot_contract.md §5 + §11A, added under `docs/decision_log.md`
    D-0037).

    Wraps the two record kinds so adding a third later (e.g. curve
    parameters under FW-0007) is an additive shape change inside this
    component rather than a new top-level Snapshot field.
    """

    componentWeightRecords: tuple[ComponentWeightRecord, ...] = field(default_factory=tuple)
    callPointRecords: tuple[CallPointRecord, ...] = field(default_factory=tuple)


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
    """Top-level snapshot (snapshot_contract.md §5).

    `scoringConfigRecords` defaults to empty (no operator overrides yet);
    a snapshot extracted from a request sheet that has not been touched on
    the Scorer Config tab is a legitimate first-release input — the parser
    overlay will fill `ScoringConfig` from template defaults at parse time
    per `docs/parser_normalizer_contract.md` §9 backstop rule. Per D-0038
    the parser overlay still emits a complete `ScoringConfig.pointRules`
    cross-product even when the snapshot's `scoringConfigRecords` is empty.
    """

    metadata: SnapshotMetadata
    doctorRecords: tuple[DoctorRecord, ...]
    dayRecords: tuple[DayRecord, ...]
    requestRecords: tuple[RequestRecord, ...]
    prefilledAssignmentRecords: tuple[PrefilledAssignmentRecord, ...] = field(
        default_factory=tuple
    )
    scoringConfigRecords: ScoringConfigRecords = field(
        default_factory=ScoringConfigRecords
    )
