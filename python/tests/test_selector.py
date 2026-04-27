"""Tests for the selector per `docs/selector_contract.md`.

Covers the contract claims §10/§12/§13/§14/§15/§16/§18/§19:
- §10.3 branch discipline (success vs failure)
- §12 cascade — totalScore → pointBalanceGlobal → crReward → candidateId
- §13 retention modes — FULL writes sidecars, BEST_ONLY does not
- §14 sidecar shape — schemaVersion declared, header / column order
- §15 failure-branch no-sidecars regardless of retention
- §16.4 envelope passthrough — selector synthesizes nothing
- §18 byte-identical determinism
- §19 schemaVersion: 1

Pytest-compatible. Standalone runnable via
`python3 python/tests/test_selector.py`.
"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rostermonster.domain import (  # noqa: E402
    AssignmentUnit,
    IssueSeverity,
    ValidationIssue,
)
from rostermonster.scorer import (  # noqa: E402
    ALL_COMPONENTS,
    COMPONENT_CR_REWARD,
    COMPONENT_POINT_BALANCE_GLOBAL,
    ScoreDirection,
    ScoreResult,
)
from rostermonster.selector import (  # noqa: E402
    FULL_FILE_NAME,
    SELECTOR_STRATEGY_HIGHEST_SCORE_WITH_CASCADE,
    SIDECAR_SCHEMA_VERSION,
    SUMMARY_FILE_NAME,
    AllocationResult,
    FinalResultEnvelope,
    RetentionMode,
    RunEnvelope,
    ScoredCandidateSet,
    ScoredTrialCandidate,
    UnsatisfiedResultEnvelope,
    select,
)
from rostermonster.solver import (  # noqa: E402
    SearchDiagnostics,
    TrialCandidate,
    UnfilledDemandEntry,
    UnsatisfiedResult,
)
from rostermonster.solver.result import CrFloorMode  # noqa: E402


# --- Fixtures ---------------------------------------------------------


def _envelope(run_id: str = "run-001") -> RunEnvelope:
    return RunEnvelope(
        runId=run_id,
        snapshotRef="snap-1",
        configRef="cfg-1",
        seed=42,
        fillOrderPolicy="MOST_CONSTRAINED_FIRST",
        crFloorMode="SMART_MEDIAN",
        crFloorComputed=1,
        generationTimestamp="2026-04-28T00:00:00Z",
        sourceSpreadsheetId="sheet-id-1",
        sourceTabName="ICU/HD May 2026",
    )


def _diagnostics() -> SearchDiagnostics:
    return SearchDiagnostics(
        strategyId="SEEDED_RANDOM_BLIND",
        fillOrderPolicy="MOST_CONSTRAINED_FIRST",
        crFloorMode=CrFloorMode.SMART_MEDIAN,
        crFloorComputed=1,
        seed=42,
        placementAttempts=10,
        ruleEngineRejectionsByReason={"BASELINE_ELIGIBILITY_FAIL": 2},
        candidateEmitCount=3,
        unfilledDemandCount=0,
    )


def _make_score(
    *,
    total: float,
    point_balance_global: float = 0.0,
    cr_reward: float = 0.0,
) -> ScoreResult:
    """Construct a ScoreResult with an explicit total/PBG/CR and zeros
    elsewhere. Bypasses `from_components` because we want `totalScore` to
    carry an arbitrary value (not the sum) so tie-break tests can isolate
    cascade rules without simultaneously varying the sum."""
    components = {c: 0.0 for c in ALL_COMPONENTS}
    components[COMPONENT_POINT_BALANCE_GLOBAL] = point_balance_global
    components[COMPONENT_CR_REWARD] = cr_reward
    return ScoreResult(
        totalScore=total,
        components=components,
        direction=ScoreDirection.HIGHER_IS_BETTER,
        context={},
    )


def _scored_candidate(
    candidate_id: int,
    *,
    total: float,
    point_balance_global: float = 0.0,
    cr_reward: float = 0.0,
    assignments: tuple[AssignmentUnit, ...] = (),
) -> ScoredTrialCandidate:
    return ScoredTrialCandidate(
        candidate=TrialCandidate(
            candidateId=candidate_id,
            assignments=assignments
            or (
                AssignmentUnit(
                    dateKey="2026-05-01",
                    slotType="MICU_CALL",
                    unitIndex=0,
                    doctorId=f"dr_{candidate_id}",
                ),
            ),
        ),
        score=_make_score(
            total=total,
            point_balance_global=point_balance_global,
            cr_reward=cr_reward,
        ),
    )


def _scored_set(
    *scored: ScoredTrialCandidate,
) -> ScoredCandidateSet:
    return ScoredCandidateSet(
        candidates=tuple(scored),
        diagnostics=_diagnostics(),
    )


# --- Output shape (§10) -----------------------------------------------


def test_select_returns_allocation_result_on_success_branch() -> None:
    """Per §10.3 branch discipline: success input produces
    `AllocationResult` inside `FinalResultEnvelope.result`."""
    s = _scored_set(_scored_candidate(1, total=10.0))
    env = select(
        s,
        retentionMode=RetentionMode.BEST_ONLY,
        runEnvelope=_envelope(),
    )
    assert isinstance(env, FinalResultEnvelope)
    assert isinstance(env.result, AllocationResult)
    assert env.selectorStrategyId == SELECTOR_STRATEGY_HIGHEST_SCORE_WITH_CASCADE
    assert env.retentionMode is RetentionMode.BEST_ONLY


def test_select_returns_unsatisfied_envelope_on_failure_branch() -> None:
    """Per §15: an `UnsatisfiedResult` input MUST produce an
    `UnsatisfiedResultEnvelope` and forward `unfilledDemand` / `reasons`
    / `diagnostics` unchanged."""
    unfilled = (
        UnfilledDemandEntry(dateKey="2026-05-01", slotType="MHD_CALL", unitIndex=0),
    )
    reasons = (
        ValidationIssue(
            severity=IssueSeverity.ERROR,
            code="UNFILLABLE_DEMAND",
            message="no eligible doctors",
            context={},
        ),
    )
    failure = UnsatisfiedResult(
        unfilledDemand=unfilled,
        reasons=reasons,
        diagnostics=_diagnostics(),
    )
    env = select(
        failure,
        retentionMode=RetentionMode.FULL,  # mode is irrelevant on failure
        runEnvelope=_envelope(),
    )
    assert isinstance(env.result, UnsatisfiedResultEnvelope)
    assert env.result.unfilledDemand == unfilled
    assert env.result.reasons == reasons


# --- §12 cascade ------------------------------------------------------


def test_winner_is_highest_total_score() -> None:
    """§12.1 selection rule: max `totalScore` wins."""
    s = _scored_set(
        _scored_candidate(1, total=5.0),
        _scored_candidate(2, total=10.0),
        _scored_candidate(3, total=7.0),
    )
    env = select(s, retentionMode=RetentionMode.BEST_ONLY, runEnvelope=_envelope())
    assert isinstance(env.result, AllocationResult)
    assert env.result.winnerScore.totalScore == 10.0


def test_tie_break_prefers_higher_point_balance_global() -> None:
    """§12.2 cascade step 1: tied `totalScore` → higher `pointBalanceGlobal`
    (less-negative penalty contribution) wins."""
    s = _scored_set(
        _scored_candidate(1, total=10.0, point_balance_global=-5.0),
        _scored_candidate(2, total=10.0, point_balance_global=-1.0),
    )
    env = select(s, retentionMode=RetentionMode.BEST_ONLY, runEnvelope=_envelope())
    assert isinstance(env.result, AllocationResult)
    # Candidate 2 has the less-negative pointBalanceGlobal → winner.
    assert env.result.winnerScore.components[COMPONENT_POINT_BALANCE_GLOBAL] == -1.0


def test_tie_break_prefers_higher_cr_reward_when_pbg_also_tied() -> None:
    """§12.2 cascade step 2: tied on `totalScore` AND `pointBalanceGlobal`
    → higher `crReward` wins."""
    s = _scored_set(
        _scored_candidate(1, total=10.0, point_balance_global=-1.0, cr_reward=2.0),
        _scored_candidate(2, total=10.0, point_balance_global=-1.0, cr_reward=5.0),
    )
    env = select(s, retentionMode=RetentionMode.BEST_ONLY, runEnvelope=_envelope())
    assert isinstance(env.result, AllocationResult)
    assert env.result.winnerScore.components[COMPONENT_CR_REWARD] == 5.0


def test_tie_break_final_fallback_picks_lowest_candidate_id() -> None:
    """§12.2 cascade final fallback: total tie → lowest `candidateId` wins."""
    s = _scored_set(
        _scored_candidate(7, total=10.0),
        _scored_candidate(3, total=10.0),
        _scored_candidate(5, total=10.0),
    )
    env = select(s, retentionMode=RetentionMode.BEST_ONLY, runEnvelope=_envelope())
    assert isinstance(env.result, AllocationResult)
    # candidateId comparison is on the raw integer (per §16); 3 wins.
    assert env.result.winnerAssignment[0].doctorId == "dr_3"


# --- §13 retention modes ----------------------------------------------


def test_best_only_does_not_write_sidecars() -> None:
    """§13.1: under `BEST_ONLY`, no sidecar files are written and the
    AllocationResult MUST NOT carry `candidatesSummaryPath` /
    `candidatesFullPath`."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td)
        s = _scored_set(_scored_candidate(1, total=1.0))
        env = select(
            s,
            retentionMode=RetentionMode.BEST_ONLY,
            runEnvelope=_envelope(),
            sidecarTargetDir=target,
        )
        assert isinstance(env.result, AllocationResult)
        assert env.result.candidatesSummaryPath is None
        assert env.result.candidatesFullPath is None
        # Directory was not used by the selector under BEST_ONLY — nothing
        # should have been written there.
        assert list(target.iterdir()) == []


def test_full_writes_both_sidecars_and_returns_paths() -> None:
    """§13.2: under `FULL`, `candidates_summary.csv` and
    `candidates_full.json` MUST be written and their paths MUST be on
    the AllocationResult."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td)
        s = _scored_set(
            _scored_candidate(1, total=1.0),
            _scored_candidate(2, total=2.0),
        )
        env = select(
            s,
            retentionMode=RetentionMode.FULL,
            runEnvelope=_envelope(),
            sidecarTargetDir=target,
        )
        assert isinstance(env.result, AllocationResult)
        assert env.result.candidatesSummaryPath is not None
        assert env.result.candidatesFullPath is not None
        assert (target / SUMMARY_FILE_NAME).exists()
        assert (target / FULL_FILE_NAME).exists()


def test_full_requires_sidecar_target_dir() -> None:
    """Implementation rule (consistent with §14.3): `FULL` mode without a
    target directory has no write destination; surface as ValueError so the
    boundary is explicit rather than failing later inside the writer."""
    s = _scored_set(_scored_candidate(1, total=1.0))
    raised = False
    try:
        select(
            s,
            retentionMode=RetentionMode.FULL,
            runEnvelope=_envelope(),
            # no sidecarTargetDir
        )
    except ValueError:
        raised = True
    assert raised


# --- §14 sidecar shape ------------------------------------------------


def test_summary_csv_has_required_columns_and_schema_version() -> None:
    """§14.1: header includes `candidateId`, `totalScore`, every
    first-release component, then `runId`, `seed`, `batchId`. §19:
    `schemaVersion: 1` is declared at the top of the file."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td)
        s = _scored_set(_scored_candidate(1, total=10.0, cr_reward=3.0))
        select(
            s,
            retentionMode=RetentionMode.FULL,
            runEnvelope=_envelope(),
            sidecarTargetDir=target,
        )
        text = (target / SUMMARY_FILE_NAME).read_text()
        first_line = text.splitlines()[0]
        assert f"schemaVersion: {SIDECAR_SCHEMA_VERSION}" in first_line, (
            f"expected schemaVersion declaration on first line; got "
            f"{first_line!r}"
        )
        # Skip the comment line; parse the rest as CSV.
        body_lines = text.splitlines()[1:]
        reader = csv.reader(body_lines)
        header = next(reader)
        assert header[0] == "candidateId"
        assert header[1] == "totalScore"
        assert header[2:11] == list(ALL_COMPONENTS)
        assert header[11:14] == ["runId", "seed", "batchId"]


def test_summary_csv_batch_id_is_empty_for_non_batched_strategy() -> None:
    """§14.1: when the active solver strategy does not surface batches
    (first-release `SEEDED_RANDOM_BLIND` does not), the `batchId` cell
    MUST be the empty string — header shape is invariant per §19."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td)
        s = _scored_set(_scored_candidate(1, total=1.0))
        select(
            s,
            retentionMode=RetentionMode.FULL,
            runEnvelope=_envelope(),
            sidecarTargetDir=target,
        )
        body_lines = (target / SUMMARY_FILE_NAME).read_text().splitlines()[1:]
        rows = list(csv.reader(body_lines))
        # rows[0] is header; rows[1] is the data row.
        assert rows[1][13] == ""  # batchId column index


def test_full_json_top_level_fields_and_per_candidate_payload() -> None:
    """§14.2: top-level `runId`, `schemaVersion: 1`, `generationTimestamp`;
    per-candidate payload indexed by `candidateId` with full
    `AssignmentUnit[]` and full `ScoreResult`."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td)
        env_in = _envelope()
        s = _scored_set(_scored_candidate(1, total=10.0, cr_reward=3.0))
        select(
            s,
            retentionMode=RetentionMode.FULL,
            runEnvelope=env_in,
            sidecarTargetDir=target,
        )
        payload = json.loads((target / FULL_FILE_NAME).read_text())
        assert payload["schemaVersion"] == SIDECAR_SCHEMA_VERSION
        assert payload["runId"] == env_in.runId
        assert payload["generationTimestamp"] == env_in.generationTimestamp
        assert len(payload["candidates"]) == 1
        cand = payload["candidates"][0]
        assert cand["candidateId"] == 1
        assert "assignments" in cand
        assert "score" in cand
        assert cand["score"]["totalScore"] == 10.0
        # Full component breakdown per scorer §10 — every component appears.
        for c in ALL_COMPONENTS:
            assert c in cand["score"]["components"]


# --- §15 failure-branch no-sidecars ----------------------------------


def test_failure_branch_writes_no_sidecars_under_full_retention() -> None:
    """§15: on the failure branch, retentionMode has no behavioral
    effect — no sidecars written regardless of mode."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td)
        failure = UnsatisfiedResult(
            unfilledDemand=(
                UnfilledDemandEntry(
                    dateKey="2026-05-01", slotType="MHD_CALL", unitIndex=0
                ),
            ),
            reasons=(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    code="UNFILLABLE_DEMAND",
                    message="x",
                    context={},
                ),
            ),
            diagnostics=_diagnostics(),
        )
        env = select(
            failure,
            retentionMode=RetentionMode.FULL,
            runEnvelope=_envelope(),
            sidecarTargetDir=target,
        )
        assert isinstance(env.result, UnsatisfiedResultEnvelope)
        # Directory exists but no files were written.
        assert list(target.iterdir()) == []


# --- §16 envelope passthrough ----------------------------------------


def test_run_envelope_rides_through_unchanged() -> None:
    """§16.4: the selector synthesizes nothing about identity and MUST NOT
    alter the run envelope."""
    s = _scored_set(_scored_candidate(1, total=1.0))
    env_in = _envelope("run-zzz")
    env_out = select(
        s, retentionMode=RetentionMode.BEST_ONLY, runEnvelope=env_in
    )
    assert env_out.runEnvelope is env_in or env_out.runEnvelope == env_in


# --- §18 byte-identical determinism ----------------------------------


def test_sidecars_are_byte_identical_under_repeated_runs() -> None:
    """§18: identical inputs produce byte-identical sidecar files within
    a single implementation on a single platform."""
    with tempfile.TemporaryDirectory() as td_a, tempfile.TemporaryDirectory() as td_b:
        target_a = Path(td_a)
        target_b = Path(td_b)
        s = _scored_set(
            _scored_candidate(1, total=10.0, cr_reward=2.0),
            _scored_candidate(2, total=8.0, point_balance_global=-1.0),
            _scored_candidate(3, total=10.0, cr_reward=2.0),
        )
        env_in = _envelope()
        select(s, retentionMode=RetentionMode.FULL, runEnvelope=env_in, sidecarTargetDir=target_a)
        select(s, retentionMode=RetentionMode.FULL, runEnvelope=env_in, sidecarTargetDir=target_b)
        assert (target_a / SUMMARY_FILE_NAME).read_bytes() == (
            target_b / SUMMARY_FILE_NAME
        ).read_bytes()
        assert (target_a / FULL_FILE_NAME).read_bytes() == (
            target_b / FULL_FILE_NAME
        ).read_bytes()


# --- Strategy / retention gating -------------------------------------


def test_unknown_selector_strategy_id_is_rejected() -> None:
    """§11.1: unregistered `selectorStrategyId` MUST be rejected before
    any §10 output construction begins."""
    s = _scored_set(_scored_candidate(1, total=1.0))
    raised = False
    try:
        select(
            s,
            retentionMode=RetentionMode.BEST_ONLY,
            runEnvelope=_envelope(),
            selectorStrategyId="MULTI_OBJECTIVE_PARETO",
        )
    except ValueError:
        raised = True
    assert raised


def test_bare_string_retention_mode_value_accepted() -> None:
    """`RetentionMode` is a `(str, Enum)`; the value vocabulary `"FULL"`
    and `"BEST_ONLY"` strings MUST be accepted (mirrors the same
    contract-string-vs-enum tolerance on the solver's `CrFloorMode`)."""
    s = _scored_set(_scored_candidate(1, total=1.0))
    env = select(
        s,
        retentionMode="BEST_ONLY",  # type: ignore[arg-type]
        runEnvelope=_envelope(),
    )
    assert env.retentionMode is RetentionMode.BEST_ONLY


def test_unknown_retention_mode_is_rejected() -> None:
    """A retention mode outside `{BEST_ONLY, FULL}` is a first-release
    defect per §13."""
    s = _scored_set(_scored_candidate(1, total=1.0))
    raised = False
    try:
        select(
            s,
            retentionMode="TOP_K",  # type: ignore[arg-type]
            runEnvelope=_envelope(),
        )
    except ValueError:
        raised = True
    assert raised


# --- Empty success-branch input is a caller defect -------------------


def test_empty_scored_set_on_success_branch_raises() -> None:
    """`docs/solver_contract.md` §10.1: success-branch CandidateSet MUST
    be non-empty. Passing an empty set to the selector is a caller defect
    and we surface it explicitly rather than emitting an
    AllocationResult with no winner."""
    empty = ScoredCandidateSet(candidates=(), diagnostics=_diagnostics())
    raised = False
    try:
        select(
            empty,
            retentionMode=RetentionMode.BEST_ONLY,
            runEnvelope=_envelope(),
        )
    except ValueError:
        raised = True
    assert raised


# --- Architectural import boundary (§9) ------------------------------


def test_selector_package_does_not_consume_rule_engine_or_scorer_functions() -> None:
    """Per §9: the selector MUST NOT consume the scorer interface (the
    `score(...)` function) nor any rule-engine handle. Importing the
    result *types* (`ScoreResult`, etc.) is permitted and necessary —
    the contract explicitly allows the selector to preserve the full
    `ScoreResult` component breakdown into `winnerScore` and the sidecar
    columns.

    Architectural invariant: source files under `selector/` MUST NOT
    `from rostermonster.rule_engine import evaluate` or
    `from rostermonster.scorer import score`."""
    selector_root = Path(__file__).resolve().parent.parent / "rostermonster" / "selector"
    forbidden_imports = (
        "from rostermonster.rule_engine import evaluate",
        "from rostermonster.scorer import score",
    )
    offenders: list[str] = []
    for src in sorted(selector_root.glob("*.py")):
        for raw_line in src.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            for forbidden in forbidden_imports:
                if line.startswith(forbidden):
                    # Exclude false-positive prefix matches (e.g.
                    # `import score_two`) by requiring the next character
                    # to be whitespace, comma, or end-of-line.
                    tail = line[len(forbidden) :]
                    if not tail or tail[0] in (" ", ",", "\t"):
                        offenders.append(f"{src.name}: {line}")
    assert not offenders, (
        f"selector package consumes rule-engine or scorer functions "
        f"(violates docs/selector_contract.md §9): {offenders}"
    )


# --- standalone runner -----------------------------------------------


def _all_tests():
    return [v for k, v in globals().items() if k.startswith("test_") and callable(v)]


def main() -> int:
    failures: list[tuple[str, BaseException]] = []
    passes = 0
    for fn in _all_tests():
        try:
            fn()
            passes += 1
            print(f"  PASS  {fn.__name__}")
        except BaseException as exc:
            failures.append((fn.__name__, exc))
            print(f"  FAIL  {fn.__name__}: {exc}", file=sys.stderr)
    total = passes + len(failures)
    print(f"\n{passes}/{total} passed")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
