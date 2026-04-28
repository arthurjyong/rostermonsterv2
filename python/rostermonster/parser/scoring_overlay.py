"""Parser-stage scoring overlay per `docs/parser_normalizer_contract.md` §9.

Builds `ScoringConfig` by overlaying the snapshot's `scoringConfigRecords`
onto template defaults. Sheet wins where the cell is present and parseable;
template defaults backstop where the sheet cell is absent or blank. The
producer-coverage requirement (D-0038) is total — every `(call-slot
slotType, dateKey)` pair from the model's cross-product MUST appear in the
emitted `pointRules`.

Admission cases per §14:
- mis-signed operator-edited component weight (penalty positive, reward
  negative) → NON_CONSUMABLE,
- malformed numeric in `componentWeightRecords` or `callPointRecords`
  populated cells → NON_CONSUMABLE,
- incomplete `pointRules` cross-product after overlay → NON_CONSUMABLE
  (defensive — should not trigger when template `pointRows.defaultRule`
  covers every call-slot at construction time).
"""

from __future__ import annotations

from datetime import date

from rostermonster.domain import (
    IssueSeverity,
    NormalizedModel,
    RosterDay,
    ValidationIssue,
)
from rostermonster.scorer import ALL_COMPONENTS, ScoringConfig
from rostermonster.scorer.result import PENALTY_COMPONENTS, REWARD_COMPONENTS
from rostermonster.snapshot import (
    CallPointRecord,
    ComponentWeightRecord,
    Snapshot,
)
from rostermonster.template_artifact import (
    PointRowDefinition,
    PointRowDefaultRule,
    TemplateArtifact,
)

# Issue codes — stable strings within this implementation; the contract
# defers issue-code standardization per §10. Mirrors the existing pattern
# in admission.py.
ISSUE_SCORING_COMPONENT_WEIGHT_UNKNOWN = "SCORING_COMPONENT_WEIGHT_UNKNOWN"
ISSUE_SCORING_COMPONENT_WEIGHT_DUPLICATE = "SCORING_COMPONENT_WEIGHT_DUPLICATE"
ISSUE_SCORING_COMPONENT_WEIGHT_MALFORMED = "SCORING_COMPONENT_WEIGHT_MALFORMED"
ISSUE_SCORING_COMPONENT_WEIGHT_MIS_SIGNED = "SCORING_COMPONENT_WEIGHT_MIS_SIGNED"
ISSUE_SCORING_COMPONENT_WEIGHT_DEFAULT_MIS_SIGNED = (
    "SCORING_COMPONENT_WEIGHT_DEFAULT_MIS_SIGNED"
)
ISSUE_SCORING_COMPONENT_WEIGHT_DEFAULT_MISSING = (
    "SCORING_COMPONENT_WEIGHT_DEFAULT_MISSING"
)
ISSUE_SCORING_CALL_POINT_DUPLICATE = "SCORING_CALL_POINT_DUPLICATE"
ISSUE_SCORING_CALL_POINT_DAY_REF_BROKEN = "SCORING_CALL_POINT_DAY_REF_BROKEN"
ISSUE_SCORING_CALL_POINT_ROW_KEY_UNKNOWN = "SCORING_CALL_POINT_ROW_KEY_UNKNOWN"
ISSUE_SCORING_CALL_POINT_MALFORMED = "SCORING_CALL_POINT_MALFORMED"
ISSUE_SCORING_POINT_RULES_INCOMPLETE = "SCORING_POINT_RULES_INCOMPLETE"
ISSUE_SCORING_POINT_ROW_SLOT_TYPE_DUPLICATE = "SCORING_POINT_ROW_SLOT_TYPE_DUPLICATE"


def _is_blank(raw: str) -> bool:
    """A cell is "blank" per §9 backstop rule when the raw text strips to
    empty. The snapshot layer preserves whitespace exactly per §11A; the
    parser is the layer that decides "blank means use template default"."""
    return raw.strip() == ""


def _is_weekend(d: date) -> bool:
    """Saturday (5) and Sunday (6) — first-release ICU/HD has no public
    holiday calendar, so weekend is calendar-based. The contract field
    name `weekendOrPublicHoliday` anticipates a future calendar feed
    (FW territory) without forcing a parser dependency on one yet."""
    return d.weekday() >= 5


def _default_point_for_day(rule: PointRowDefaultRule, dateKey: str) -> float:
    """Pick the right default weight for a `(pointRow, dateKey)` pair given
    the row's `defaultRule`. Classification is `(this_day, next_day) →
    weight` — the weights reflect the operator's call burden:
    `weekdayToWeekday` (1.0) is the normal weekday loss; `weekdayToWeekendOrPublicHoliday`
    (1.75) and `weekendOrPublicHolidayToWeekendOrPublicHoliday` (2.0) cost
    more because they consume rest days; `weekendOrPublicHolidayToWeekday`
    (1.5) is mid-range. Period-boundary days simply look at the calendar
    next day; no special-casing needed."""
    today = date.fromisoformat(dateKey)
    tomorrow = date.fromordinal(today.toordinal() + 1)
    if _is_weekend(today):
        if _is_weekend(tomorrow):
            return rule.weekendOrPublicHolidayToWeekendOrPublicHoliday
        return rule.weekendOrPublicHolidayToWeekday
    if _is_weekend(tomorrow):
        return rule.weekdayToWeekendOrPublicHoliday
    return rule.weekdayToWeekday


def _check_sign(component: str, weight: float) -> bool:
    """Sign orientation per `docs/scorer_contract.md` §10 / §15.

    Returns True if the weight respects the component's classification
    (penalty ≤ 0, reward ≥ 0); zero is allowed for both (component
    contributes nothing). Returns False on mis-sign.
    """
    if component in PENALTY_COMPONENTS:
        return weight <= 0
    if component in REWARD_COMPONENTS:
        return weight >= 0
    # Unknown component — caller has already classified earlier; treat as
    # mis-sign-clean since there's no orientation to violate.
    return True


def _overlay_component_weights(
    snapshot: Snapshot,
    template: TemplateArtifact,
) -> tuple[dict[str, float] | None, list[ValidationIssue]]:
    """Build the `ScoringConfig.weights` map by overlaying snapshot
    component-weight records onto template defaults.

    Returns `(weights, issues)`. On any admission-blocking issue, weights
    is `None`. Otherwise weights covers every first-release component and
    is sign-correct.
    """
    issues: list[ValidationIssue] = []

    # Index records by componentId; reject duplicates (snapshot-contract
    # §10 says componentId is unique within componentWeightRecords).
    by_component: dict[str, ComponentWeightRecord] = {}
    for record in snapshot.scoringConfigRecords.componentWeightRecords:
        if record.componentId in by_component:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_SCORING_COMPONENT_WEIGHT_DUPLICATE,
                    message=(
                        f"componentWeightRecords contains duplicate componentId "
                        f"{record.componentId!r}"
                    ),
                    context={"componentId": record.componentId},
                )
            )
            continue
        if record.componentId not in ALL_COMPONENTS:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_SCORING_COMPONENT_WEIGHT_UNKNOWN,
                    message=(
                        f"componentWeightRecord references unknown componentId "
                        f"{record.componentId!r}; expected one of "
                        f"docs/domain_model.md §11.2"
                    ),
                    context={"componentId": record.componentId},
                )
            )
            continue
        by_component[record.componentId] = record

    weights: dict[str, float] = {}
    for component in ALL_COMPONENTS:
        record = by_component.get(component)
        if record is None or _is_blank(record.rawValue):
            # Backstop to template default per §9.
            default = template.componentWeights.get(component)
            if default is None:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.ERROR,
                        code=ISSUE_SCORING_COMPONENT_WEIGHT_DEFAULT_MISSING,
                        message=(
                            f"template.componentWeights missing default for "
                            f"{component!r}; required per "
                            f"docs/template_artifact_contract.md §11"
                        ),
                        context={"componentId": component},
                    )
                )
                continue
            if not _check_sign(component, default):
                # Template-shipped default is itself mis-signed — distinct
                # from operator mis-sign, but still admission-blocking
                # (template artifact validity per template_artifact §11
                # requires sign-orientation preservation).
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.ERROR,
                        code=ISSUE_SCORING_COMPONENT_WEIGHT_DEFAULT_MIS_SIGNED,
                        message=(
                            f"template default for {component!r} violates "
                            f"sign orientation per docs/scorer_contract.md "
                            f"§10 / §15; got {default!r}"
                        ),
                        context={"componentId": component, "value": default},
                    )
                )
                continue
            weights[component] = default
            continue
        # Operator-edited cell present and non-blank — parse + sign-check.
        try:
            value = float(record.rawValue.strip())
        except ValueError:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_SCORING_COMPONENT_WEIGHT_MALFORMED,
                    message=(
                        f"componentWeightRecord for {component!r} has "
                        f"non-numeric rawValue {record.rawValue!r}; parser "
                        f"must not silently substitute a default per "
                        f"docs/parser_normalizer_contract.md §14"
                    ),
                    context={
                        "componentId": component,
                        "rawValue": record.rawValue,
                    },
                )
            )
            continue
        if not _check_sign(component, value):
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_SCORING_COMPONENT_WEIGHT_MIS_SIGNED,
                    message=(
                        f"operator weight for {component!r} violates sign "
                        f"orientation per docs/scorer_contract.md §10 / §15 "
                        f"(penalty must be ≤ 0; reward must be ≥ 0); "
                        f"got {value!r}"
                    ),
                    context={"componentId": component, "value": value},
                )
            )
            continue
        weights[component] = value

    if issues:
        return None, issues
    return weights, []


def _overlay_point_rules(
    snapshot: Snapshot,
    template: TemplateArtifact,
    model: NormalizedModel,
) -> tuple[dict[tuple[str, str], float] | None, list[ValidationIssue]]:
    """Build the `ScoringConfig.pointRules` map by overlaying snapshot
    callPointRecords onto template defaults.

    Returns `(pointRules, issues)`. On any admission-blocking issue,
    pointRules is `None`. Otherwise pointRules covers the full cross-product
    of (call-slot, dateKey) per D-0038 producer-coverage requirement.
    """
    issues: list[ValidationIssue] = []

    # Index point rows by rowKey; build the slotType → rowKey reverse
    # mapping the parser uses to translate snapshot callPointRecords (keyed
    # by callPointRowKey) into ScoringConfig.pointRules (keyed by slotType).
    # Reject duplicate slotType bindings — silently overwriting earlier rows
    # would let populated callPointRecords for the overwritten row look
    # structurally valid while never being applied (template_artifact §9
    # binds at most one pointRow per call slot).
    point_row_by_key: dict[str, PointRowDefinition] = {
        pr.rowKey: pr for pr in template.pointRows
    }
    row_key_by_slot_type: dict[str, str] = {}
    for pr in template.pointRows:
        if pr.slotType in row_key_by_slot_type:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_SCORING_POINT_ROW_SLOT_TYPE_DUPLICATE,
                    message=(
                        f"template.pointRows binds slotType {pr.slotType!r} "
                        f"to multiple rowKeys "
                        f"({row_key_by_slot_type[pr.slotType]!r}, "
                        f"{pr.rowKey!r}); per "
                        f"docs/template_artifact_contract.md §9 each call "
                        f"slot has at most one pointRow"
                    ),
                    context={
                        "slotType": pr.slotType,
                        "firstRowKey": row_key_by_slot_type[pr.slotType],
                        "duplicateRowKey": pr.rowKey,
                    },
                )
            )
            continue
        row_key_by_slot_type[pr.slotType] = pr.rowKey

    # Day index → dateKey from the model period (parser's already-built
    # day-axis lookup).
    day_index_to_date_key: dict[int, str] = {
        d.dayIndex: d.dateKey for d in model.period.days
    }
    valid_day_indices = set(day_index_to_date_key.keys())

    # Index records by (rowKey, dayIndex); reject duplicates per
    # snapshot_contract.md §10 ((callPointRowKey, dayIndex) is unique).
    by_key: dict[tuple[str, int], CallPointRecord] = {}
    for record in snapshot.scoringConfigRecords.callPointRecords:
        path = (record.callPointRowKey, record.dayIndex)
        if path in by_key:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_SCORING_CALL_POINT_DUPLICATE,
                    message=(
                        f"callPointRecords contains duplicate "
                        f"(callPointRowKey={record.callPointRowKey!r}, "
                        f"dayIndex={record.dayIndex})"
                    ),
                    context={
                        "callPointRowKey": record.callPointRowKey,
                        "dayIndex": record.dayIndex,
                    },
                )
            )
            continue
        if record.callPointRowKey not in point_row_by_key:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_SCORING_CALL_POINT_ROW_KEY_UNKNOWN,
                    message=(
                        f"callPointRecord references unknown "
                        f"callPointRowKey {record.callPointRowKey!r}; "
                        f"template declares "
                        f"{sorted(point_row_by_key.keys())}"
                    ),
                    context={"callPointRowKey": record.callPointRowKey},
                )
            )
            continue
        if record.dayIndex not in valid_day_indices:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code=ISSUE_SCORING_CALL_POINT_DAY_REF_BROKEN,
                    message=(
                        f"callPointRecord references unknown dayIndex "
                        f"{record.dayIndex}"
                    ),
                    context={"dayIndex": record.dayIndex},
                )
            )
            continue
        by_key[path] = record

    if issues:
        # Bail before parsing any cell values; surface all structural
        # issues at once, matching the parser's existing per-stage idiom.
        return None, issues

    # Build the cross-product. Iterate model-declared call slots × period
    # days so the resulting map is keyed by (slotType, dateKey) per
    # scorer_contract.md §11.
    point_rules: dict[tuple[str, str], float] = {}
    call_slot_types = [st.slotType for st in model.slotTypes if st.slotKind == "CALL"]
    for slot_type in call_slot_types:
        row_key = row_key_by_slot_type.get(slot_type)
        if row_key is None:
            # Template doesn't declare a point row for this call slot —
            # surface as completeness defect; producer-coverage per D-0038
            # cannot be satisfied without the row binding.
            for day in model.period.days:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.ERROR,
                        code=ISSUE_SCORING_POINT_RULES_INCOMPLETE,
                        message=(
                            f"template.pointRows has no row whose slotType "
                            f"matches call-slot {slot_type!r}; cannot derive "
                            f"({slot_type}, {day.dateKey}) per D-0038 "
                            f"producer coverage"
                        ),
                        context={
                            "slotType": slot_type,
                            "dateKey": day.dateKey,
                        },
                    )
                )
            continue
        rule = point_row_by_key[row_key].defaultRule
        for day in model.period.days:
            record = by_key.get((row_key, day.dayIndex))
            if record is None or _is_blank(record.rawValue):
                point_rules[(slot_type, day.dateKey)] = _default_point_for_day(
                    rule, day.dateKey
                )
                continue
            try:
                value = float(record.rawValue.strip())
            except ValueError:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.ERROR,
                        code=ISSUE_SCORING_CALL_POINT_MALFORMED,
                        message=(
                            f"callPointRecord for ({row_key}, {day.dayIndex}) "
                            f"has non-numeric rawValue {record.rawValue!r}; "
                            f"parser must not silently substitute a default "
                            f"per docs/parser_normalizer_contract.md §14"
                        ),
                        context={
                            "callPointRowKey": row_key,
                            "dayIndex": day.dayIndex,
                            "rawValue": record.rawValue,
                        },
                    )
                )
                continue
            point_rules[(slot_type, day.dateKey)] = value

    if issues:
        return None, issues

    # D-0038 belt-and-braces completeness check. Should be redundant given
    # we built from the model cross-product; surface as an internal-defect
    # signal if it ever trips.
    expected = {
        (slot_type, day.dateKey)
        for slot_type in call_slot_types
        for day in model.period.days
    }
    missing = sorted(expected - point_rules.keys())
    if missing:
        return None, [
            ValidationIssue(
                severity=IssueSeverity.ERROR,
                code=ISSUE_SCORING_POINT_RULES_INCOMPLETE,
                message=(
                    f"pointRules missing required (slotType, dateKey) entries "
                    f"per docs/scorer_contract.md §11 / D-0038: {missing}"
                ),
                context={"missing": missing},
            )
        ]

    return point_rules, []


def build_scoring_config(
    snapshot: Snapshot,
    template: TemplateArtifact,
    model: NormalizedModel,
) -> tuple[ScoringConfig | None, list[ValidationIssue]]:
    """Public entry per `docs/parser_normalizer_contract.md` §9 overlay.

    Returns `(scoringConfig, issues)`. On any admission-blocking issue
    `scoringConfig` is `None` and `issues` is non-empty (admission caller
    should surface as `NON_CONSUMABLE`). On clean overlay `scoringConfig`
    is the validated config and `issues` is empty.
    """
    weights, weight_issues = _overlay_component_weights(snapshot, template)
    point_rules, pr_issues = _overlay_point_rules(snapshot, template, model)
    issues = list(weight_issues) + list(pr_issues)
    if issues or weights is None or point_rules is None:
        return None, issues
    return ScoringConfig(weights=weights, pointRules=point_rules), []
