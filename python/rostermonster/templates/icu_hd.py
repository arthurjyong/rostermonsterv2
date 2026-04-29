"""ICU/HD first-release template artifact aligned to
`docs/template_artifact_contract.md` §16.

Promoted from `python/tests/fixtures.py` to a production-side module under
M2 C9 Phase 2 so the production CLI (`rostermonster.run`) consumes the
template without test-package imports. Test fixtures continue to source
this same template via the re-export in `python/rostermonster/templates/__init__.py`.
"""

from __future__ import annotations

from rostermonster.template_artifact import (
    AssignmentRowDefinition,
    DoctorGroupDefinition,
    EligibilityRecord,
    InputSheetSection,
    OutputSurface,
    PointRowDefaultRule,
    PointRowDefinition,
    RequestSemanticsBinding,
    SlotDefinition,
    TemplateArtifact,
    TemplateIdentity,
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
        # `pointRows` and `componentWeights` added under D-0037 — the parser
        # consumes both at scoring-overlay time per
        # `docs/parser_normalizer_contract.md` §9. Default values are the
        # ICU/HD first-release weights documented in
        # `docs/template_artifact_contract.md` §9 + §11.
        pointRows=(
            PointRowDefinition(
                rowKey="MICU_CALL_POINT",
                slotType="MICU_CALL",
                label="MICU Call Point",
                defaultRule=PointRowDefaultRule(
                    weekdayToWeekday=1.0,
                    weekdayToWeekendOrPublicHoliday=1.75,
                    weekendOrPublicHolidayToWeekendOrPublicHoliday=2.0,
                    weekendOrPublicHolidayToWeekday=1.5,
                ),
            ),
            PointRowDefinition(
                rowKey="MHD_CALL_POINT",
                slotType="MHD_CALL",
                label="MHD Call Point",
                defaultRule=PointRowDefaultRule(
                    weekdayToWeekday=1.0,
                    weekdayToWeekendOrPublicHoliday=1.75,
                    weekendOrPublicHolidayToWeekendOrPublicHoliday=2.0,
                    weekendOrPublicHolidayToWeekday=1.5,
                ),
            ),
        ),
        componentWeights={
            "unfilledPenalty": -100.0,
            "pointBalanceWithinSection": -1.0,
            "pointBalanceGlobal": -1.0,
            "spacingPenalty": -2.0,
            "preLeavePenalty": -10.0,
            "crReward": 5.0,
            "dualEligibleIcuBonus": 0.5,
            "standbyAdjacencyPenalty": -3.0,
            "standbyCountFairnessPenalty": -1.0,
        },
    )
