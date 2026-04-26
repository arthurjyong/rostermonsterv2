"""ICU/HD test fixtures for parser admission tests.

Builds minimal valid snapshot + template artifact pairs aligned to the
ICU/HD specimen in `docs/template_artifact_contract.md` §16. Tests mutate
copies of these to construct negative cases.
"""

from __future__ import annotations

from dataclasses import replace

from rostermonster.snapshot import (
    DayLocator,
    DayRecord,
    DoctorLocator,
    DoctorRecord,
    ExtractionSummary,
    PeriodRef,
    PhysicalSourceRef,
    PrefilledAssignmentLocator,
    PrefilledAssignmentRecord,
    RequestLocator,
    RequestRecord,
    Snapshot,
    SnapshotMetadata,
)
from rostermonster.template_artifact import (
    AssignmentRowDefinition,
    DoctorGroupDefinition,
    EligibilityRecord,
    InputSheetSection,
    OutputSurface,
    RequestSemanticsBinding,
    SlotDefinition,
    TemplateArtifact,
    TemplateIdentity,
)


def _physical_ref(a1: str = "A1") -> PhysicalSourceRef:
    return PhysicalSourceRef(
        sheetName="CGH ICU/HD Call",
        sheetGid="0",
        a1Refs=(a1,),
    )


def icu_hd_template_artifact() -> TemplateArtifact:
    """ICU/HD first-release template artifact aligned to the
    `docs/template_artifact_contract.md` §16 specimen."""
    return TemplateArtifact(
        identity=TemplateIdentity(
            templateId="cgh_icu_hd",
            templateVersion=1,
            label="CGH ICU/HD Call",
        ),
        slots=(
            SlotDefinition(
                slotId="MICU_CALL",
                label="MICU Call",
                slotFamily="MICU",
                slotKind="CALL",
                requiredCountPerDay=1,
            ),
            SlotDefinition(
                slotId="MICU_STANDBY",
                label="MICU Standby",
                slotFamily="MICU",
                slotKind="STANDBY",
                requiredCountPerDay=1,
            ),
            SlotDefinition(
                slotId="MHD_CALL",
                label="MHD Call",
                slotFamily="MHD",
                slotKind="CALL",
                requiredCountPerDay=1,
            ),
            SlotDefinition(
                slotId="MHD_STANDBY",
                label="MHD Standby",
                slotFamily="MHD",
                slotKind="STANDBY",
                requiredCountPerDay=1,
            ),
        ),
        doctorGroups=(
            DoctorGroupDefinition(groupId="ICU_ONLY"),
            DoctorGroupDefinition(groupId="ICU_HD"),
            DoctorGroupDefinition(groupId="HD_ONLY"),
        ),
        eligibility=(
            EligibilityRecord(slotId="MICU_CALL", eligibleGroups=("ICU_ONLY", "ICU_HD")),
            EligibilityRecord(slotId="MICU_STANDBY", eligibleGroups=("ICU_ONLY", "ICU_HD")),
            EligibilityRecord(slotId="MHD_CALL", eligibleGroups=("ICU_HD", "HD_ONLY")),
            EligibilityRecord(slotId="MHD_STANDBY", eligibleGroups=("ICU_HD", "HD_ONLY")),
        ),
        requestSemanticsBinding=RequestSemanticsBinding(
            contractId="ICU_HD_REQUEST_SEMANTICS",
            contractVersion=1,
        ),
        inputSheetSections=(
            InputSheetSection(sectionKey="MICU", groupId="ICU_ONLY"),
            InputSheetSection(sectionKey="MICU_HD", groupId="ICU_HD"),
            InputSheetSection(sectionKey="MHD", groupId="HD_ONLY"),
        ),
        outputSurfaces=(
            OutputSurface(
                surfaceId="lowerRosterAssignments",
                assignmentRows=(
                    AssignmentRowDefinition(slotId="MICU_CALL", rowOffset=0),
                    AssignmentRowDefinition(slotId="MICU_STANDBY", rowOffset=1),
                    AssignmentRowDefinition(slotId="MHD_CALL", rowOffset=2),
                    AssignmentRowDefinition(slotId="MHD_STANDBY", rowOffset=3),
                ),
            ),
        ),
    )


def icu_hd_snapshot() -> Snapshot:
    """A minimal valid ICU/HD snapshot covering all three sections, five days,
    a few requests, and one prefilled assignment exercising the FixedAssignment
    scoped admission per parser_normalizer_contract.md §14."""
    doctor_records = (
        # MICU section (ICU_ONLY)
        DoctorRecord(
            sourceDoctorKey="micu_dr_a",
            displayName="Dr Alpha",
            rawSectionText="MICU",
            sourceLocator=DoctorLocator(
                sectionKey="MICU", doctorIndexInSection=0
            ),
            physicalSourceRef=_physical_ref("A4"),
        ),
        DoctorRecord(
            sourceDoctorKey="micu_dr_b",
            displayName="Dr Bravo",
            rawSectionText="MICU",
            sourceLocator=DoctorLocator(
                sectionKey="MICU", doctorIndexInSection=1
            ),
            physicalSourceRef=_physical_ref("A5"),
        ),
        # MICU_HD section (ICU_HD)
        DoctorRecord(
            sourceDoctorKey="icuhd_dr_c",
            displayName="Dr Charlie",
            rawSectionText="ICU + HD",
            sourceLocator=DoctorLocator(
                sectionKey="MICU_HD", doctorIndexInSection=0
            ),
            physicalSourceRef=_physical_ref("A8"),
        ),
        DoctorRecord(
            sourceDoctorKey="icuhd_dr_d",
            displayName="Dr Delta",
            rawSectionText="ICU + HD",
            sourceLocator=DoctorLocator(
                sectionKey="MICU_HD", doctorIndexInSection=1
            ),
            physicalSourceRef=_physical_ref("A9"),
        ),
        # MHD section (HD_ONLY)
        DoctorRecord(
            sourceDoctorKey="mhd_dr_e",
            displayName="Dr Echo",
            rawSectionText="MHD",
            sourceLocator=DoctorLocator(
                sectionKey="MHD", doctorIndexInSection=0
            ),
            physicalSourceRef=_physical_ref("A12"),
        ),
        DoctorRecord(
            sourceDoctorKey="mhd_dr_f",
            displayName="Dr Foxtrot",
            rawSectionText="MHD",
            sourceLocator=DoctorLocator(
                sectionKey="MHD", doctorIndexInSection=1
            ),
            physicalSourceRef=_physical_ref("A13"),
        ),
    )

    day_records = tuple(
        DayRecord(
            dayIndex=i,
            rawDateText=f"2026-05-{i + 1:02d}",
            sourceLocator=DayLocator(dayIndex=i),
            physicalSourceRef=_physical_ref(f"B3:F3"),
        )
        for i in range(5)
    )

    request_records = (
        # Dr Alpha requests CR on day 0 (callPreferencePositive) and AL on day 2 (FULL_DAY_OFF).
        RequestRecord(
            sourceDoctorKey="micu_dr_a",
            dayIndex=0,
            rawRequestText="CR",
            sourceLocator=RequestLocator(sourceDoctorKey="micu_dr_a", dayIndex=0),
            physicalSourceRef=_physical_ref("B4"),
        ),
        RequestRecord(
            sourceDoctorKey="micu_dr_a",
            dayIndex=2,
            rawRequestText="AL",
            sourceLocator=RequestLocator(sourceDoctorKey="micu_dr_a", dayIndex=2),
            physicalSourceRef=_physical_ref("D4"),
        ),
        # Dr Charlie has duplicate-recognized-tokens combination (non-blocking issue).
        RequestRecord(
            sourceDoctorKey="icuhd_dr_c",
            dayIndex=1,
            rawRequestText="NC, NC",
            sourceLocator=RequestLocator(sourceDoctorKey="icuhd_dr_c", dayIndex=1),
            physicalSourceRef=_physical_ref("C8"),
        ),
        # Dr Echo: blank request (CONSUMABLE no-op).
        RequestRecord(
            sourceDoctorKey="mhd_dr_e",
            dayIndex=4,
            rawRequestText="",
            sourceLocator=RequestLocator(sourceDoctorKey="mhd_dr_e", dayIndex=4),
            physicalSourceRef=_physical_ref("F12"),
        ),
    )

    # One prefilled MHD_CALL assignment for Dr Foxtrot on day 3 — exercises the
    # §14 FixedAssignment scoped admission.
    prefilled = (
        PrefilledAssignmentRecord(
            dayIndex=3,
            rawAssignedDoctorText="Dr Foxtrot",
            surfaceId="lowerRosterAssignments",
            rowOffset=2,  # MHD_CALL per the template
            sourceLocator=PrefilledAssignmentLocator(
                surfaceId="lowerRosterAssignments",
                rowOffset=2,
                dayIndex=3,
            ),
            physicalSourceRef=_physical_ref("E22"),
        ),
    )

    metadata = SnapshotMetadata(
        snapshotId="snap_test_001",
        templateId="cgh_icu_hd",
        templateVersion=1,
        sourceSpreadsheetId="1abcdef",
        sourceTabName="CGH ICU/HD Call",
        generationTimestamp="2026-04-26T10:00:00Z",
        periodRef=PeriodRef(
            periodId="2026-05",
            periodLabel="May 2026",
        ),
        extractionSummary=ExtractionSummary(
            doctorRecordCount=len(doctor_records),
            dayRecordCount=len(day_records),
            requestRecordCount=len(request_records),
            prefilledAssignmentRecordCount=len(prefilled),
        ),
    )

    return Snapshot(
        metadata=metadata,
        doctorRecords=doctor_records,
        dayRecords=day_records,
        requestRecords=request_records,
        prefilledAssignmentRecords=prefilled,
    )


# --- Mutation helpers for negative-case construction ----------------------


def _replace_in_tuple(items, index, **kwargs):
    """Return a new tuple with `items[index]` replaced via dataclasses.replace."""
    return tuple(
        replace(item, **kwargs) if i == index else item
        for i, item in enumerate(items)
    )


def with_duplicate_doctor_key(snapshot: Snapshot) -> Snapshot:
    """Return a snapshot mutated so two doctorRecords share `sourceDoctorKey`."""
    docs = list(snapshot.doctorRecords)
    docs[1] = replace(docs[1], sourceDoctorKey=docs[0].sourceDoctorKey)
    return replace(snapshot, doctorRecords=tuple(docs))


def with_non_contiguous_day_index(snapshot: Snapshot) -> Snapshot:
    """Skip dayIndex=2 to break contiguity per snapshot_contract.md §8."""
    days = tuple(d for d in snapshot.dayRecords if d.dayIndex != 2)
    return replace(snapshot, dayRecords=days)


def with_unknown_doctor_section(snapshot: Snapshot) -> Snapshot:
    """Reassign the first doctor's section to one not declared in the template."""
    docs = list(snapshot.doctorRecords)
    docs[0] = replace(
        docs[0],
        sourceLocator=replace(
            docs[0].sourceLocator, sectionKey="UNKNOWN_SECTION"
        ),
    )
    return replace(snapshot, doctorRecords=tuple(docs))


def with_request_referencing_unknown_doctor(snapshot: Snapshot) -> Snapshot:
    """Inject a request referencing a doctor key absent from doctorRecords."""
    bad_request = RequestRecord(
        sourceDoctorKey="ghost_doctor",
        dayIndex=0,
        rawRequestText="CR",
        sourceLocator=RequestLocator(sourceDoctorKey="ghost_doctor", dayIndex=0),
        physicalSourceRef=_physical_ref("B99"),
    )
    return replace(
        snapshot, requestRecords=snapshot.requestRecords + (bad_request,)
    )


def with_malformed_request_grammar(snapshot: Snapshot) -> Snapshot:
    """Inject a request using non-comma delimiter per §6 violation."""
    return replace(
        snapshot,
        requestRecords=_replace_in_tuple(
            snapshot.requestRecords, 0, rawRequestText="CR/NC"
        ),
    )


def with_unknown_request_token(snapshot: Snapshot) -> Snapshot:
    """Inject a request with an unknown token per §13 violation."""
    return replace(
        snapshot,
        requestRecords=_replace_in_tuple(
            snapshot.requestRecords, 0, rawRequestText="CR, XYZ"
        ),
    )


def with_unresolved_prefill_doctor(snapshot: Snapshot) -> Snapshot:
    """Replace the prefill cell text with a name that isn't on any roster."""
    return replace(
        snapshot,
        prefilledAssignmentRecords=_replace_in_tuple(
            snapshot.prefilledAssignmentRecords,
            0,
            rawAssignedDoctorText="Dr NotInRoster",
        ),
    )


def with_ambiguous_prefill_doctor(snapshot: Snapshot) -> Snapshot:
    """Make two doctors share a displayName so the prefill name is ambiguous."""
    docs = list(snapshot.doctorRecords)
    # Dr Foxtrot is already in MHD section (last doctor); rename Dr Alpha
    # (first doctor) to "Dr Foxtrot" to create the ambiguity.
    docs[0] = replace(docs[0], displayName="Dr Foxtrot")
    return replace(snapshot, doctorRecords=tuple(docs))


def with_prefill_into_unknown_surface(snapshot: Snapshot) -> Snapshot:
    """Point a prefill record at a surface the template does not declare."""
    return replace(
        snapshot,
        prefilledAssignmentRecords=_replace_in_tuple(
            snapshot.prefilledAssignmentRecords,
            0,
            surfaceId="ghostSurface",
            sourceLocator=replace(
                snapshot.prefilledAssignmentRecords[0].sourceLocator,
                surfaceId="ghostSurface",
            ),
        ),
    )


def with_prefill_using_messy_whitespace_and_case(snapshot: Snapshot) -> Snapshot:
    """Replace the prefill cell text with a noisy form of the doctor's name —
    leading/trailing spaces, doubled internal spaces, and lowercase — to
    exercise the D-0034 normalization rule (trim + collapse internal
    whitespace + casefold)."""
    return replace(
        snapshot,
        prefilledAssignmentRecords=_replace_in_tuple(
            snapshot.prefilledAssignmentRecords,
            0,
            rawAssignedDoctorText="   dr   foxtrot  ",
        ),
    )


def with_prefill_doctor_two_slots_same_day(snapshot: Snapshot) -> Snapshot:
    """Add a second prefill record placing the same doctor in another slot
    on the same date as the existing prefill."""
    existing = snapshot.prefilledAssignmentRecords[0]
    duplicate = PrefilledAssignmentRecord(
        dayIndex=existing.dayIndex,
        rawAssignedDoctorText=existing.rawAssignedDoctorText,
        surfaceId=existing.surfaceId,
        rowOffset=3,  # MHD_STANDBY (different slot, same day)
        sourceLocator=PrefilledAssignmentLocator(
            surfaceId=existing.surfaceId,
            rowOffset=3,
            dayIndex=existing.dayIndex,
        ),
        physicalSourceRef=_physical_ref("E23"),
    )
    return replace(
        snapshot,
        prefilledAssignmentRecords=snapshot.prefilledAssignmentRecords + (duplicate,),
    )
