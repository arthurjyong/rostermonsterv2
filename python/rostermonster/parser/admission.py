"""Parser admission pipeline per `docs/parser_normalizer_contract.md`.

Implements the §11 transformation stages, §13 structural non-consumability
checks, §14 semantic non-consumability checks (including the FixedAssignment
scoped admission exception), and §10 issue-channel discipline.

Public entry: `parse(snapshot, template_artifact) -> ParserResult`.

Stage ordering (parser_normalizer_contract.md §11):
1. input admission
2. structural snapshot validation
3. cross-record reference resolution
4. template interpretation and base normalization
5. request parsing and effect derivation
6. normalized model assembly and internal consistency checks
7. final parser result decision

Implementations may merge adjacent stages internally (§11 implementation note);
this module groups stages 1-3 in `_validate_structural`, stages 4-5 in
`_interpret_and_normalize`, and stages 6-7 in the final assembly section.

Issue codes here are stable strings within this implementation (the contract
defers issue-code standardization per §10 — they are not normative across
implementations).
"""

from __future__ import annotations

from rostermonster.domain import (
    Doctor,
    DoctorGroup,
    EligibilityRule,
    FixedAssignment,
    DailyEffectState,
    IssueSeverity,
    NormalizedModel,
    Request,
    RosterDay,
    RosterPeriod,
    SlotDemand,
    SlotTypeDefinition,
    ValidationIssue,
)
from rostermonster.parser.request_semantics import parse_request_text
from rostermonster.parser.result import ParserResult
from rostermonster.parser.scoring_overlay import build_scoring_config
from rostermonster.snapshot import Snapshot
from rostermonster.template_artifact import TemplateArtifact


# --- Issue codes (stable within this implementation) -----------------------

# §13 structural codes
ISSUE_TEMPLATE_MISMATCH = "TEMPLATE_MISMATCH"
ISSUE_DOCTOR_KEY_DUPLICATE = "DOCTOR_KEY_DUPLICATE"
ISSUE_DOCTOR_LOCATOR_DUPLICATE = "DOCTOR_LOCATOR_DUPLICATE"
ISSUE_DAY_INDEX_DUPLICATE = "DAY_INDEX_DUPLICATE"
ISSUE_DAY_INDEX_NON_CONTIGUOUS = "DAY_INDEX_NON_CONTIGUOUS"
ISSUE_DAY_RAW_DATE_EMPTY = "DAY_RAW_DATE_EMPTY"
ISSUE_DAY_RAW_DATE_DUPLICATE = "DAY_RAW_DATE_DUPLICATE"
ISSUE_REQUEST_LOCATOR_DUPLICATE = "REQUEST_LOCATOR_DUPLICATE"
ISSUE_REQUEST_DOCTOR_REF_BROKEN = "REQUEST_DOCTOR_REF_BROKEN"
ISSUE_REQUEST_DAY_REF_BROKEN = "REQUEST_DAY_REF_BROKEN"
ISSUE_PREFILLED_LOCATOR_DUPLICATE = "PREFILLED_LOCATOR_DUPLICATE"
ISSUE_PREFILLED_DAY_REF_BROKEN = "PREFILLED_DAY_REF_BROKEN"

# §14 semantic codes
ISSUE_DOCTOR_SECTION_UNKNOWN = "DOCTOR_SECTION_UNKNOWN"
ISSUE_TEMPLATE_SECTION_GROUP_UNKNOWN = "TEMPLATE_SECTION_GROUP_UNKNOWN"
ISSUE_ELIGIBILITY_SLOT_UNKNOWN = "ELIGIBILITY_SLOT_UNKNOWN"
ISSUE_ELIGIBILITY_GROUP_UNKNOWN = "ELIGIBILITY_GROUP_UNKNOWN"
ISSUE_REQUEST_SEMANTICS_BINDING_UNSUPPORTED = "REQUEST_SEMANTICS_BINDING_UNSUPPORTED"

# §14 prefilled-assignment codes
ISSUE_PREFILLED_SURFACE_UNKNOWN = "PREFILLED_SURFACE_UNKNOWN"
ISSUE_PREFILLED_ROW_OFFSET_UNKNOWN = "PREFILLED_ROW_OFFSET_UNKNOWN"
ISSUE_PREFILLED_DOCTOR_NAME_UNRESOLVED = "PREFILLED_DOCTOR_NAME_UNRESOLVED"
ISSUE_PREFILLED_DOCTOR_NAME_AMBIGUOUS = "PREFILLED_DOCTOR_NAME_AMBIGUOUS"
ISSUE_PREFILLED_SLOT_DAY_DUPLICATE = "PREFILLED_SLOT_DAY_DUPLICATE"
ISSUE_PREFILLED_DOCTOR_TWO_SLOTS_SAME_DAY = "PREFILLED_DOCTOR_TWO_SLOTS_SAME_DAY"


def _has_errors(issues: list[ValidationIssue]) -> bool:
    """Return True if any issue carries `ERROR` severity (admission-blocking)."""
    return any(issue.severity is IssueSeverity.ERROR for issue in issues)


# ---------------------------------------------------------------------------
# Stages 1-3: structural snapshot validation
# (parser_normalizer_contract.md §11 stages 1-3, §13)
# ---------------------------------------------------------------------------


def _validate_structural(
    snapshot: Snapshot, template_artifact: TemplateArtifact
) -> list[ValidationIssue]:
    """Stages 1-3 — input admission, structural validation, cross-record refs.

    All findings here are §13 structural issues (`severity=ERROR`); any single
    finding makes the snapshot NON_CONSUMABLE per §13.
    """
    issues: list[ValidationIssue] = []

    # Stage 1 — input admission. Top-level shape: snapshot.metadata.templateId
    # must match the template artifact's identity.
    if (
        snapshot.metadata.templateId != template_artifact.identity.templateId
        or snapshot.metadata.templateVersion
        != template_artifact.identity.templateVersion
    ):
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.ERROR,
                code=ISSUE_TEMPLATE_MISMATCH,
                message=(
                    "Snapshot metadata declares "
                    f"templateId={snapshot.metadata.templateId!r} / "
                    f"templateVersion={snapshot.metadata.templateVersion} but "
                    f"the supplied template artifact is "
                    f"{template_artifact.identity.templateId!r} / "
                    f"{template_artifact.identity.templateVersion}."
                ),
                context={
                    "snapshotTemplateId": snapshot.metadata.templateId,
                    "snapshotTemplateVersion": snapshot.metadata.templateVersion,
                    "artifactTemplateId": template_artifact.identity.templateId,
                    "artifactTemplateVersion": template_artifact.identity.templateVersion,
                },
            )
        )
        # Template mismatch is fatal — downstream resolution against this
        # template artifact would be meaningless.
        return issues

    # Stage 2 — structural snapshot validation per §13 and snapshot_contract.md
    # uniqueness/contiguity rules.

    # Doctor record uniqueness on sourceDoctorKey
    seen_keys: set[str] = set()
    for doc in snapshot.doctorRecords:
        if doc.sourceDoctorKey in seen_keys:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_DOCTOR_KEY_DUPLICATE,
                    message=(
                        f"Duplicate sourceDoctorKey {doc.sourceDoctorKey!r} in "
                        f"doctorRecords; keys must be unique "
                        f"(snapshot_contract.md §7)."
                    ),
                    context={"sourceDoctorKey": doc.sourceDoctorKey},
                )
            )
        seen_keys.add(doc.sourceDoctorKey)

    # Doctor record uniqueness on (sectionKey, doctorIndexInSection)
    seen_locators: set[tuple[str, int]] = set()
    for doc in snapshot.doctorRecords:
        loc = (
            doc.sourceLocator.sectionKey,
            doc.sourceLocator.doctorIndexInSection,
        )
        if loc in seen_locators:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_DOCTOR_LOCATOR_DUPLICATE,
                    message=(
                        f"Duplicate doctor locator (sectionKey={loc[0]!r}, "
                        f"doctorIndexInSection={loc[1]}) — must be unique within "
                        f"doctorRecords (snapshot_contract.md §10)."
                    ),
                    context={
                        "sectionKey": loc[0],
                        "doctorIndexInSection": loc[1],
                    },
                )
            )
        seen_locators.add(loc)

    # Day record uniqueness on dayIndex + contiguity from 0
    day_indices = [d.dayIndex for d in snapshot.dayRecords]
    seen_day_idx: set[int] = set()
    for di in day_indices:
        if di in seen_day_idx:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_DAY_INDEX_DUPLICATE,
                    message=(
                        f"Duplicate dayIndex={di} in dayRecords "
                        f"(snapshot_contract.md §8)."
                    ),
                    context={"dayIndex": di},
                )
            )
        seen_day_idx.add(di)

    expected = set(range(len(snapshot.dayRecords)))
    if seen_day_idx != expected:
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.ERROR,
                code=ISSUE_DAY_INDEX_NON_CONTIGUOUS,
                message=(
                    f"dayRecords dayIndex set is not a contiguous sequence "
                    f"starting from 0 (snapshot_contract.md §8). "
                    f"Got {sorted(seen_day_idx)}; expected {sorted(expected)}."
                ),
                context={"observed": sorted(seen_day_idx)},
            )
        )

    # Day rawDateText must be non-empty and unique (otherwise dateKey is
    # structurally degenerate — §13 ordering/coverage defect).
    seen_dates: dict[str, int] = {}
    for day in snapshot.dayRecords:
        date_key = day.rawDateText.strip()
        if date_key == "":
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_DAY_RAW_DATE_EMPTY,
                    message=(
                        f"dayRecord at dayIndex={day.dayIndex} has empty "
                        f"rawDateText; date identity cannot be derived."
                    ),
                    context={"dayIndex": day.dayIndex},
                )
            )
            continue
        if date_key in seen_dates:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_DAY_RAW_DATE_DUPLICATE,
                    message=(
                        f"Duplicate rawDateText {date_key!r} across dayIndex="
                        f"{seen_dates[date_key]} and dayIndex={day.dayIndex}."
                    ),
                    context={
                        "rawDateText": date_key,
                        "firstDayIndex": seen_dates[date_key],
                        "duplicateDayIndex": day.dayIndex,
                    },
                )
            )
            continue
        seen_dates[date_key] = day.dayIndex

    # Stage 3 — cross-record reference resolution.

    # Request record uniqueness on (sourceDoctorKey, dayIndex) and reference integrity
    seen_req_locators: set[tuple[str, int]] = set()
    for req in snapshot.requestRecords:
        loc = (req.sourceDoctorKey, req.dayIndex)
        if loc in seen_req_locators:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_REQUEST_LOCATOR_DUPLICATE,
                    message=(
                        f"Duplicate request locator "
                        f"(sourceDoctorKey={loc[0]!r}, dayIndex={loc[1]}) — "
                        f"must be unique (snapshot_contract.md §10)."
                    ),
                    context={"sourceDoctorKey": loc[0], "dayIndex": loc[1]},
                )
            )
        seen_req_locators.add(loc)

        if req.sourceDoctorKey not in seen_keys:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_REQUEST_DOCTOR_REF_BROKEN,
                    message=(
                        f"requestRecord sourceDoctorKey={req.sourceDoctorKey!r} "
                        f"does not reference any doctorRecord."
                    ),
                    context={"sourceDoctorKey": req.sourceDoctorKey},
                )
            )
        if req.dayIndex not in seen_day_idx:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_REQUEST_DAY_REF_BROKEN,
                    message=(
                        f"requestRecord dayIndex={req.dayIndex} does not "
                        f"reference any dayRecord."
                    ),
                    context={"dayIndex": req.dayIndex},
                )
            )

    # Prefilled-assignment record uniqueness + dayIndex reference integrity.
    # Surface/rowOffset reference integrity is a §14 semantic concern handled
    # in stage 5 (see _process_prefilled_assignments).
    seen_pf_locators: set[tuple[str, int, int]] = set()
    for pf in snapshot.prefilledAssignmentRecords:
        loc3 = (pf.surfaceId, pf.rowOffset, pf.dayIndex)
        if loc3 in seen_pf_locators:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_PREFILLED_LOCATOR_DUPLICATE,
                    message=(
                        f"Duplicate prefilled-assignment locator "
                        f"(surfaceId={loc3[0]!r}, rowOffset={loc3[1]}, "
                        f"dayIndex={loc3[2]}) — must be unique "
                        f"(snapshot_contract.md §10)."
                    ),
                    context={
                        "surfaceId": loc3[0],
                        "rowOffset": loc3[1],
                        "dayIndex": loc3[2],
                    },
                )
            )
        seen_pf_locators.add(loc3)

        if pf.dayIndex not in seen_day_idx:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_PREFILLED_DAY_REF_BROKEN,
                    message=(
                        f"prefilledAssignmentRecord dayIndex={pf.dayIndex} "
                        f"does not reference any dayRecord."
                    ),
                    context={"dayIndex": pf.dayIndex},
                )
            )

    return issues


# ---------------------------------------------------------------------------
# Stages 4-5a: template interpretation and base normalization
# (parser_normalizer_contract.md §11 stage 4, §14 ICU/HD parser obligations)
# ---------------------------------------------------------------------------


def _interpret_template(
    snapshot: Snapshot, template_artifact: TemplateArtifact
) -> tuple[
    list[Doctor],
    list[DoctorGroup],
    list[SlotTypeDefinition],
    list[SlotDemand],
    list[EligibilityRule],
    list[ValidationIssue],
]:
    """Stage 4 — resolve canonical doctor groups, instantiate slot demand and
    eligibility per §14 ICU/HD parser obligations.

    Returns `(doctors, groups, slotTypes, slotDemand, eligibility, issues)`.
    Caller decides whether ERROR-severity issues block CONSUMABLE.
    """
    issues: list[ValidationIssue] = []

    # Verify request semantics binding is the supported ICU/HD first release.
    binding = template_artifact.requestSemanticsBinding
    if (
        binding.contractId != "ICU_HD_REQUEST_SEMANTICS"
        or binding.contractVersion != 1
    ):
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.ERROR,
                code=ISSUE_REQUEST_SEMANTICS_BINDING_UNSUPPORTED,
                message=(
                    f"Template requestSemanticsBinding "
                    f"(contractId={binding.contractId!r}, "
                    f"contractVersion={binding.contractVersion}) is not the "
                    f"ICU/HD first-release contract supported by this parser."
                ),
                context={
                    "contractId": binding.contractId,
                    "contractVersion": binding.contractVersion,
                },
            )
        )

    # Build template lookup tables for cross-validation.
    known_group_ids = {g.groupId for g in template_artifact.doctorGroups}
    known_slot_ids = {s.slotId for s in template_artifact.slots}
    section_to_group: dict[str, str] = {}
    for sec in template_artifact.inputSheetSections:
        if sec.groupId not in known_group_ids:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_TEMPLATE_SECTION_GROUP_UNKNOWN,
                    message=(
                        f"inputSheetLayout.sections section {sec.sectionKey!r} "
                        f"declares groupId={sec.groupId!r} not in doctorGroups."
                    ),
                    context={
                        "sectionKey": sec.sectionKey,
                        "groupId": sec.groupId,
                    },
                )
            )
        section_to_group[sec.sectionKey] = sec.groupId

    # Cross-validate eligibility records against template slots/groups.
    eligibility: list[EligibilityRule] = []
    for elig in template_artifact.eligibility:
        if elig.slotId not in known_slot_ids:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_ELIGIBILITY_SLOT_UNKNOWN,
                    message=(
                        f"eligibility entry references unknown slotId="
                        f"{elig.slotId!r}."
                    ),
                    context={"slotId": elig.slotId},
                )
            )
            continue
        for gid in elig.eligibleGroups:
            if gid not in known_group_ids:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.ERROR,
                        code=ISSUE_ELIGIBILITY_GROUP_UNKNOWN,
                        message=(
                            f"eligibility entry for slotId={elig.slotId!r} "
                            f"references unknown groupId={gid!r}."
                        ),
                        context={"slotId": elig.slotId, "groupId": gid},
                    )
                )
        eligibility.append(
            EligibilityRule(
                slotType=elig.slotId,
                eligibleGroups=tuple(elig.eligibleGroups),
            )
        )

    # Resolve canonical doctor group for each snapshot doctor.
    doctors: list[Doctor] = []
    for doc in snapshot.doctorRecords:
        section_key = doc.sourceLocator.sectionKey
        group_id = section_to_group.get(section_key)
        if group_id is None:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_DOCTOR_SECTION_UNKNOWN,
                    message=(
                        f"Doctor sourceDoctorKey={doc.sourceDoctorKey!r} sits "
                        f"in sectionKey={section_key!r}, which is not declared "
                        f"in inputSheetLayout.sections; canonical doctor group "
                        f"cannot be resolved (parser_normalizer_contract.md §14)."
                    ),
                    context={
                        "sourceDoctorKey": doc.sourceDoctorKey,
                        "sectionKey": section_key,
                    },
                )
            )
            continue
        doctors.append(
            Doctor(
                doctorId=doc.sourceDoctorKey,
                displayName=doc.displayName,
                groupId=group_id,
                provenance=doc.sourceLocator,
            )
        )

    # Build domain-side groups, slot type definitions, and per-day slot demand.
    groups = [DoctorGroup(groupId=g.groupId) for g in template_artifact.doctorGroups]
    slot_types = [
        SlotTypeDefinition(
            slotType=s.slotId,
            displayLabel=s.label,
            slotFamily=s.slotFamily,
            slotKind=s.slotKind,
        )
        for s in template_artifact.slots
    ]

    slot_demand: list[SlotDemand] = []
    # Sort dayRecords by dayIndex defensively so demand instantiation order is
    # deterministic regardless of incoming list order.
    for day in sorted(snapshot.dayRecords, key=lambda d: d.dayIndex):
        date_key = day.rawDateText.strip()
        for slot in template_artifact.slots:
            slot_demand.append(
                SlotDemand(
                    dateKey=date_key,
                    slotType=slot.slotId,
                    requiredCount=slot.requiredCountPerDay,
                    provenance=day.sourceLocator,
                )
            )

    return (doctors, groups, slot_types, slot_demand, eligibility, issues)


# ---------------------------------------------------------------------------
# Stage 5b: request parsing and effect derivation
# (parser_normalizer_contract.md §11 stage 5, §14, request_semantics_contract.md)
# ---------------------------------------------------------------------------


def _parse_requests(
    snapshot: Snapshot,
    doctors: list[Doctor],
    day_index_to_date_key: dict[int, str],
) -> tuple[list[Request], list[DailyEffectState], list[ValidationIssue]]:
    """Stage 5 — parse each request cell under ICU/HD grammar; derive
    `Request` and `DailyEffectState` per `docs/request_semantics_contract.md`.
    """
    issues: list[ValidationIssue] = []
    requests: list[Request] = []

    doctor_by_key = {d.doctorId: d for d in doctors}

    for req in snapshot.requestRecords:
        # If a request references an unknown doctor or day, the structural
        # stage already flagged it; skip semantic processing.
        if req.sourceDoctorKey not in doctor_by_key:
            continue
        if req.dayIndex not in day_index_to_date_key:
            continue
        date_key = day_index_to_date_key[req.dayIndex]
        result = parse_request_text(
            req.rawRequestText,
            doctor_id=req.sourceDoctorKey,
            date_key=date_key,
        )
        issues.extend(result.issues)
        if not result.consumable:
            # request_semantics_contract.md §14 — request-level NON_CONSUMABLE
            # propagates upward. The parent ParserResult.consumability check
            # will see ERROR-severity issues and refuse CONSUMABLE. Per §9, no
            # partial Request is emitted when the parse fails.
            continue
        # §10 rule 4 — request parse issues mirror onto the normalized Request.
        # Top-level ParserResult.issues remains the authoritative record (§10
        # rule 1); entity-local content here is supplemental (§10 rules 5-6).
        requests.append(
            Request(
                doctorId=req.sourceDoctorKey,
                dateKey=date_key,
                rawRequestText=req.rawRequestText,
                recognizedRawTokens=result.recognizedRawTokens,
                canonicalClasses=result.canonicalClasses,
                machineEffects=result.machineEffects,
                provenance=req.sourceLocator,
                parseIssues=result.issues,
            )
        )

    # Derive per-(doctor, date) DailyEffectState as the union of effects across
    # any requests fired on that day. With first-release one-request-per-cell
    # uniqueness, this is just a direct projection — the originating request's
    # source locator carries through as DailyEffectState.provenance per §16.
    daily_effects: list[DailyEffectState] = [
        DailyEffectState(
            doctorId=r.doctorId,
            dateKey=r.dateKey,
            effects=r.machineEffects,
            provenance=r.provenance,
        )
        for r in requests
        if r.machineEffects
    ]

    return requests, daily_effects, issues


# ---------------------------------------------------------------------------
# Stage 5c: prefilled-assignment processing → FixedAssignment
# (parser_normalizer_contract.md §14 prefilled-assignment cases)
# ---------------------------------------------------------------------------


def _normalize_doctor_name(text: str) -> str:
    """Apply the D-0034 doctor-name matching normalization: trim leading /
    trailing whitespace, collapse internal whitespace runs to a single space,
    and case-fold (Unicode case-insensitive comparison). Punctuation and
    diacritics are NOT folded.

    Handles realistic spreadsheet quirks observed on the ICU/HD May 2026
    source (trailing space, occasional double-space inside names) and obvious
    operator typing variations (case differences) without admitting risky
    fuzzy matches that could confuse two distinct doctors. The §14 ambiguity
    check (multiple matches → NON_CONSUMABLE) catches edge cases where this
    normalization happens to collapse two distinct displayNames.
    """
    return " ".join(text.split()).casefold()


def _process_prefilled_assignments(
    snapshot: Snapshot,
    template_artifact: TemplateArtifact,
    doctors: list[Doctor],
    day_index_to_date_key: dict[int, str],
) -> tuple[list[FixedAssignment], list[ValidationIssue]]:
    """Stage 5c — resolve prefilled-assignment cells into normalized
    `FixedAssignment` facts under §14 prefilled-assignment cases.

    Implements the allowed FixedAssignment scoped admission exception (§14):
    structurally and semantically resolvable prefilled assignments are admitted
    even when they would otherwise violate request-derived hard block, baseline
    eligibility, or back-to-back prohibition. The override applies only to
    that fixed assignment itself; downstream legality remains downstream.

    Doctor-name matching uses the D-0034 normalization on both sides of the
    comparison (see `_normalize_doctor_name`).
    """
    issues: list[ValidationIssue] = []
    fixed_assignments: list[FixedAssignment] = []

    if not snapshot.prefilledAssignmentRecords:
        return fixed_assignments, issues

    # Build (surfaceId, rowOffset) -> slotId lookup from outputMapping.
    surface_row_to_slot: dict[tuple[str, int], str] = {}
    known_surface_ids: set[str] = set()
    for surface in template_artifact.outputSurfaces:
        known_surface_ids.add(surface.surfaceId)
        for row in surface.assignmentRows:
            surface_row_to_slot[(surface.surfaceId, row.rowOffset)] = row.slotId

    # Build display-name → doctorId lookup using the D-0034 normalization on
    # both sides (trim + collapse internal whitespace + casefold). Ambiguity
    # (two doctors sharing the same normalized name) is detected here and
    # surfaced when a prefilled cell matches the colliding form.
    name_to_doctors: dict[str, list[str]] = {}
    for doc in doctors:
        norm = _normalize_doctor_name(doc.displayName)
        name_to_doctors.setdefault(norm, []).append(doc.doctorId)

    # Track to detect "same doctor fixed into two slots on the same date" and
    # "duplicate slot/day mapping" §14 cases.
    slot_day_to_doctor: dict[tuple[str, str], str] = {}
    doctor_day_to_slot: dict[tuple[str, str], str] = {}

    for pf in snapshot.prefilledAssignmentRecords:
        if pf.surfaceId not in known_surface_ids:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_PREFILLED_SURFACE_UNKNOWN,
                    message=(
                        f"prefilledAssignmentRecord references "
                        f"surfaceId={pf.surfaceId!r} not declared in template "
                        f"outputMapping.surfaces[]."
                    ),
                    context={
                        "surfaceId": pf.surfaceId,
                        "dayIndex": pf.dayIndex,
                        "rowOffset": pf.rowOffset,
                    },
                )
            )
            continue

        slot_id = surface_row_to_slot.get((pf.surfaceId, pf.rowOffset))
        if slot_id is None:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_PREFILLED_ROW_OFFSET_UNKNOWN,
                    message=(
                        f"prefilledAssignmentRecord references "
                        f"(surfaceId={pf.surfaceId!r}, rowOffset={pf.rowOffset}) "
                        f"which is not declared as an assignmentRow on that "
                        f"surface; populated cell cannot be mapped to a slot."
                    ),
                    context={
                        "surfaceId": pf.surfaceId,
                        "rowOffset": pf.rowOffset,
                        "dayIndex": pf.dayIndex,
                    },
                )
            )
            continue

        date_key = day_index_to_date_key.get(pf.dayIndex)
        if date_key is None:
            # Already flagged in the structural stage, but skip resolution.
            continue

        # Skip blank / whitespace-only prefill cells — they signal
        # "not yet prefilled by operator" rather than a populated fixed
        # assignment per snapshot_contract.md §11 ("populated cells").
        norm_name = _normalize_doctor_name(pf.rawAssignedDoctorText)
        if norm_name == "":
            continue

        candidates = name_to_doctors.get(norm_name, [])
        if not candidates:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_PREFILLED_DOCTOR_NAME_UNRESOLVED,
                    message=(
                        f"prefilledAssignmentRecord rawAssignedDoctorText="
                        f"{pf.rawAssignedDoctorText!r} does not match any "
                        f"doctor displayName in doctor-entry sections."
                    ),
                    context={
                        "rawAssignedDoctorText": pf.rawAssignedDoctorText,
                        "dayIndex": pf.dayIndex,
                        "surfaceId": pf.surfaceId,
                        "rowOffset": pf.rowOffset,
                    },
                )
            )
            continue
        if len(candidates) > 1:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_PREFILLED_DOCTOR_NAME_AMBIGUOUS,
                    message=(
                        f"prefilledAssignmentRecord rawAssignedDoctorText="
                        f"{pf.rawAssignedDoctorText!r} matches multiple doctors "
                        f"({candidates}); identity is not uniquely resolvable."
                    ),
                    context={
                        "rawAssignedDoctorText": pf.rawAssignedDoctorText,
                        "candidateDoctorIds": candidates,
                        "dayIndex": pf.dayIndex,
                    },
                )
            )
            continue

        doctor_id = candidates[0]

        # §14 — corrupted duplicate mapping for the same slot/day.
        slot_day_key = (slot_id, date_key)
        if slot_day_key in slot_day_to_doctor:
            existing = slot_day_to_doctor[slot_day_key]
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_PREFILLED_SLOT_DAY_DUPLICATE,
                    message=(
                        f"Two prefilled assignments target the same "
                        f"(slot={slot_id!r}, date={date_key!r}); existing "
                        f"doctorId={existing!r}, new doctorId={doctor_id!r}."
                    ),
                    context={
                        "slotType": slot_id,
                        "dateKey": date_key,
                        "existingDoctorId": existing,
                        "newDoctorId": doctor_id,
                    },
                )
            )
            continue

        # §14 — same doctor fixed into two slots on the same date.
        doc_day_key = (doctor_id, date_key)
        if doc_day_key in doctor_day_to_slot:
            other_slot = doctor_day_to_slot[doc_day_key]
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_PREFILLED_DOCTOR_TWO_SLOTS_SAME_DAY,
                    message=(
                        f"Doctor doctorId={doctor_id!r} is prefilled into two "
                        f"slots on dateKey={date_key!r}: {other_slot!r} and "
                        f"{slot_id!r}."
                    ),
                    context={
                        "doctorId": doctor_id,
                        "dateKey": date_key,
                        "slotA": other_slot,
                        "slotB": slot_id,
                    },
                )
            )
            continue

        slot_day_to_doctor[slot_day_key] = doctor_id
        doctor_day_to_slot[doc_day_key] = slot_id
        fixed_assignments.append(
            FixedAssignment(
                dateKey=date_key,
                slotType=slot_id,
                doctorId=doctor_id,
                provenance=pf.sourceLocator,
            )
        )

    return fixed_assignments, issues


# ---------------------------------------------------------------------------
# Stages 6-7: assembly and final result decision
# (parser_normalizer_contract.md §11 stages 6-7, §9, §15)
# ---------------------------------------------------------------------------


def parse(snapshot: Snapshot, template_artifact: TemplateArtifact) -> ParserResult:
    """Public parser entry. Run the §11 transformation stages and emit
    `ParserResult` per §9.

    Any ERROR-severity issue accumulated across stages forces NON_CONSUMABLE
    (§13 / §14). WARNING-severity issues are non-blocking and ride through on
    CONSUMABLE outputs per §15.
    """
    accumulated: list[ValidationIssue] = []

    # Stages 1-3: structural validation. If structural validation fails the
    # downstream stages cannot run safely (uncontrolled doctor-key references,
    # broken day axis), so we short-circuit on ERRORs here.
    structural_issues = _validate_structural(snapshot, template_artifact)
    if _has_errors(structural_issues):
        return ParserResult.non_consumable(tuple(structural_issues))
    accumulated.extend(structural_issues)

    # Stage 4: template interpretation.
    (
        doctors,
        groups,
        slot_types,
        slot_demand,
        eligibility,
        template_issues,
    ) = _interpret_template(snapshot, template_artifact)
    accumulated.extend(template_issues)

    # If any template-interpretation step failed, downstream resolution can't
    # proceed safely (eligibility unresolved, groups unknown, etc.).
    if _has_errors(template_issues):
        return ParserResult.non_consumable(tuple(accumulated))

    # Build (dayIndex -> dateKey) from validated dayRecords for the next stages.
    day_index_to_date_key: dict[int, str] = {
        d.dayIndex: d.rawDateText.strip() for d in snapshot.dayRecords
    }

    # Stage 5a-b: request parsing.
    requests, daily_effects, request_issues = _parse_requests(
        snapshot, doctors, day_index_to_date_key
    )
    accumulated.extend(request_issues)

    if _has_errors(request_issues):
        return ParserResult.non_consumable(tuple(accumulated))

    # Stage 5c: prefilled-assignment processing.
    fixed_assignments, prefill_issues = _process_prefilled_assignments(
        snapshot, template_artifact, doctors, day_index_to_date_key
    )
    accumulated.extend(prefill_issues)

    if _has_errors(prefill_issues):
        return ParserResult.non_consumable(tuple(accumulated))

    # Stage 6-7: assembly and final result decision.
    period = RosterPeriod(
        periodId=snapshot.metadata.periodRef.periodId,
        periodLabel=snapshot.metadata.periodRef.periodLabel,
        days=tuple(
            RosterDay(
                dateKey=d.rawDateText.strip(),
                dayIndex=d.dayIndex,
                provenance=d.sourceLocator,
            )
            for d in sorted(snapshot.dayRecords, key=lambda x: x.dayIndex)
        ),
    )

    normalized_model = NormalizedModel(
        period=period,
        doctors=tuple(doctors),
        doctorGroups=tuple(groups),
        slotTypes=tuple(slot_types),
        slotDemand=tuple(slot_demand),
        eligibility=tuple(eligibility),
        fixedAssignments=tuple(fixed_assignments),
        requests=tuple(requests),
        dailyEffects=tuple(daily_effects),
    )

    # §17 explicit-handoff defense: confirm assembled model is internally
    # consistent before emitting. This is a backstop — earlier admission
    # stages already guarantee these properties; a failure here indicates a
    # parser-internal defect, not a snapshot/template issue.
    consistency_issues = _verify_handoff_consistency(normalized_model)
    if consistency_issues:
        # Internal-defect path: fail closed by surfacing as NON_CONSUMABLE
        # rather than emitting a malformed CONSUMABLE handoff.
        return ParserResult.non_consumable(
            tuple(accumulated) + tuple(consistency_issues)
        )

    # Scoring-config overlay per `docs/parser_normalizer_contract.md` §9
    # (D-0037). Sheet wins / template defaults backstop. Mis-signed weights,
    # malformed numeric cells, and incomplete pointRules coverage (D-0038)
    # are all admission-blocking — same NON_CONSUMABLE discipline as the
    # earlier admission stages, with both `normalizedModel` and
    # `scoringConfig` forced to None on failure per §9.
    scoring_config, scoring_issues = build_scoring_config(
        snapshot, template_artifact, normalized_model
    )
    if scoring_issues:
        return ParserResult.non_consumable(
            tuple(accumulated) + tuple(scoring_issues)
        )

    return ParserResult.consumable(
        normalizedModel=normalized_model,
        scoringConfig=scoring_config,
        issues=tuple(accumulated),
    )


# ---------------------------------------------------------------------------
# §17 explicit-handoff internal-consistency check
# ---------------------------------------------------------------------------


# §17 internal-consistency codes — fire only when an earlier admission stage
# has missed a check that should have caught the inconsistency upstream.
ISSUE_HANDOFF_REQUEST_DOCTOR_ORPHAN = "HANDOFF_REQUEST_DOCTOR_ORPHAN"
ISSUE_HANDOFF_REQUEST_DATE_ORPHAN = "HANDOFF_REQUEST_DATE_ORPHAN"
ISSUE_HANDOFF_FIXED_ASSIGNMENT_DOCTOR_ORPHAN = "HANDOFF_FIXED_ASSIGNMENT_DOCTOR_ORPHAN"
ISSUE_HANDOFF_FIXED_ASSIGNMENT_DATE_ORPHAN = "HANDOFF_FIXED_ASSIGNMENT_DATE_ORPHAN"
ISSUE_HANDOFF_FIXED_ASSIGNMENT_SLOT_ORPHAN = "HANDOFF_FIXED_ASSIGNMENT_SLOT_ORPHAN"
ISSUE_HANDOFF_SLOT_DEMAND_DATE_ORPHAN = "HANDOFF_SLOT_DEMAND_DATE_ORPHAN"
ISSUE_HANDOFF_SLOT_DEMAND_SLOT_ORPHAN = "HANDOFF_SLOT_DEMAND_SLOT_ORPHAN"
ISSUE_HANDOFF_SLOT_DEMAND_INCOMPLETE = "HANDOFF_SLOT_DEMAND_INCOMPLETE"
ISSUE_HANDOFF_ELIGIBILITY_SLOT_ORPHAN = "HANDOFF_ELIGIBILITY_SLOT_ORPHAN"
ISSUE_HANDOFF_ELIGIBILITY_GROUP_ORPHAN = "HANDOFF_ELIGIBILITY_GROUP_ORPHAN"
ISSUE_HANDOFF_DOCTOR_GROUP_ORPHAN = "HANDOFF_DOCTOR_GROUP_ORPHAN"
ISSUE_HANDOFF_DAILY_EFFECT_DOCTOR_ORPHAN = "HANDOFF_DAILY_EFFECT_DOCTOR_ORPHAN"
ISSUE_HANDOFF_DAILY_EFFECT_DATE_ORPHAN = "HANDOFF_DAILY_EFFECT_DATE_ORPHAN"


def _verify_handoff_consistency(model: NormalizedModel) -> list[ValidationIssue]:
    """§17 explicit-handoff internal-consistency check.

    Verifies the assembled `NormalizedModel` satisfies the rule-engine handoff
    assumptions per parser_normalizer_contract.md §17:
      - normalized identities required downstream are already resolved,
      - normalized references are internally consistent,
      - downstream-governing eligibility / demand facts are instantiated.

    Earlier admission stages enforce these properties on the path that
    produces the model. This function is a defense layer that fails closed if
    a parser-internal defect produced an inconsistent model — an internal
    invariant violation, not a snapshot/template issue.
    """
    issues: list[ValidationIssue] = []

    doctor_ids = {d.doctorId for d in model.doctors}
    group_ids = {g.groupId for g in model.doctorGroups}
    slot_type_ids = {st.slotType for st in model.slotTypes}
    date_keys = {day.dateKey for day in model.period.days}

    for doc in model.doctors:
        if doc.groupId not in group_ids:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_HANDOFF_DOCTOR_GROUP_ORPHAN,
                    message=(
                        f"Internal handoff defect: Doctor doctorId={doc.doctorId!r} "
                        f"references unknown groupId={doc.groupId!r}."
                    ),
                    context={"doctorId": doc.doctorId, "groupId": doc.groupId},
                )
            )

    for req in model.requests:
        if req.doctorId not in doctor_ids:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_HANDOFF_REQUEST_DOCTOR_ORPHAN,
                    message=(
                        f"Internal handoff defect: Request references unknown "
                        f"doctorId={req.doctorId!r}."
                    ),
                    context={"doctorId": req.doctorId, "dateKey": req.dateKey},
                )
            )
        if req.dateKey not in date_keys:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_HANDOFF_REQUEST_DATE_ORPHAN,
                    message=(
                        f"Internal handoff defect: Request references unknown "
                        f"dateKey={req.dateKey!r}."
                    ),
                    context={"doctorId": req.doctorId, "dateKey": req.dateKey},
                )
            )

    for fa in model.fixedAssignments:
        if fa.doctorId not in doctor_ids:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_HANDOFF_FIXED_ASSIGNMENT_DOCTOR_ORPHAN,
                    message=(
                        f"Internal handoff defect: FixedAssignment references "
                        f"unknown doctorId={fa.doctorId!r}."
                    ),
                    context={
                        "doctorId": fa.doctorId,
                        "dateKey": fa.dateKey,
                        "slotType": fa.slotType,
                    },
                )
            )
        if fa.dateKey not in date_keys:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_HANDOFF_FIXED_ASSIGNMENT_DATE_ORPHAN,
                    message=(
                        f"Internal handoff defect: FixedAssignment references "
                        f"unknown dateKey={fa.dateKey!r}."
                    ),
                    context={
                        "doctorId": fa.doctorId,
                        "dateKey": fa.dateKey,
                        "slotType": fa.slotType,
                    },
                )
            )
        if fa.slotType not in slot_type_ids:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_HANDOFF_FIXED_ASSIGNMENT_SLOT_ORPHAN,
                    message=(
                        f"Internal handoff defect: FixedAssignment references "
                        f"unknown slotType={fa.slotType!r}."
                    ),
                    context={
                        "doctorId": fa.doctorId,
                        "dateKey": fa.dateKey,
                        "slotType": fa.slotType,
                    },
                )
            )

    for sd in model.slotDemand:
        if sd.dateKey not in date_keys:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_HANDOFF_SLOT_DEMAND_DATE_ORPHAN,
                    message=(
                        f"Internal handoff defect: SlotDemand references "
                        f"unknown dateKey={sd.dateKey!r}."
                    ),
                    context={"dateKey": sd.dateKey, "slotType": sd.slotType},
                )
            )
        if sd.slotType not in slot_type_ids:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_HANDOFF_SLOT_DEMAND_SLOT_ORPHAN,
                    message=(
                        f"Internal handoff defect: SlotDemand references "
                        f"unknown slotType={sd.slotType!r}."
                    ),
                    context={"dateKey": sd.dateKey, "slotType": sd.slotType},
                )
            )

    # SlotDemand completeness — every (dateKey × slotType) pair implied by
    # period.days × slotTypes must have a SlotDemand record. A normalization
    # defect that drops a pair would silently slip past the per-record orphan
    # checks above; downstream solvers would then under-allocate by treating
    # missing demand as absent.
    expected_pairs = {
        (day.dateKey, st.slotType)
        for day in model.period.days
        for st in model.slotTypes
    }
    actual_pairs = {(sd.dateKey, sd.slotType) for sd in model.slotDemand}
    missing_pairs = expected_pairs - actual_pairs
    for pair in sorted(missing_pairs):
        issues.append(
            ValidationIssue(
                severity=IssueSeverity.ERROR,
                code=ISSUE_HANDOFF_SLOT_DEMAND_INCOMPLETE,
                message=(
                    f"Internal handoff defect: SlotDemand missing for pair "
                    f"(dateKey={pair[0]!r}, slotType={pair[1]!r}). Expected "
                    f"every (period.day × slotType) pair to have a SlotDemand "
                    f"record so downstream solver does not under-allocate."
                ),
                context={"dateKey": pair[0], "slotType": pair[1]},
            )
        )

    for de in model.dailyEffects:
        if de.doctorId not in doctor_ids:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_HANDOFF_DAILY_EFFECT_DOCTOR_ORPHAN,
                    message=(
                        f"Internal handoff defect: DailyEffectState references "
                        f"unknown doctorId={de.doctorId!r}."
                    ),
                    context={"doctorId": de.doctorId, "dateKey": de.dateKey},
                )
            )
        if de.dateKey not in date_keys:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_HANDOFF_DAILY_EFFECT_DATE_ORPHAN,
                    message=(
                        f"Internal handoff defect: DailyEffectState references "
                        f"unknown dateKey={de.dateKey!r}."
                    ),
                    context={"doctorId": de.doctorId, "dateKey": de.dateKey},
                )
            )

    for er in model.eligibility:
        if er.slotType not in slot_type_ids:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_HANDOFF_ELIGIBILITY_SLOT_ORPHAN,
                    message=(
                        f"Internal handoff defect: EligibilityRule references "
                        f"unknown slotType={er.slotType!r}."
                    ),
                    context={"slotType": er.slotType},
                )
            )
        for gid in er.eligibleGroups:
            if gid not in group_ids:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.ERROR,
                        code=ISSUE_HANDOFF_ELIGIBILITY_GROUP_ORPHAN,
                        message=(
                            f"Internal handoff defect: EligibilityRule for "
                            f"slotType={er.slotType!r} references unknown "
                            f"groupId={gid!r}."
                        ),
                        context={"slotType": er.slotType, "groupId": gid},
                    )
                )

    return issues
