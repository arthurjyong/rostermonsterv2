"""Integration smoke test — full M2 pipeline end-to-end.

Exercises the full M2 compute pipeline against the real ICU/HD May 2026
snapshot fixture committed under `python/tests/data/`:

    Snapshot → parse() → CONSUMABLE NormalizedModel
            → solve() → CandidateSet
            → score() per candidate → ScoredCandidateSet
            → select() → FinalResultEnvelope (winner + optional sidecars)

Originally introduced under M2 C4 T4 (parser → solver → scorer); extended
under M2 C5 to cover the selector stage and sidecar emission.

Pytest-compatible. Standalone runnable via
`python3 python/tests/test_integration_smoke.py`.
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

from rostermonster.parser import Consumability, parse  # noqa: E402
from rostermonster.rule_engine import RuleState  # noqa: E402
from rostermonster.rule_engine import evaluate as rule_engine_evaluate  # noqa: E402
from rostermonster.scorer import (  # noqa: E402
    ALL_COMPONENTS,
    ScoreDirection,
    ScoringConfig,
    score,
)
from rostermonster.selector import (  # noqa: E402
    FULL_FILE_NAME,
    SUMMARY_FILE_NAME,
    AllocationResult,
    FinalResultEnvelope,
    RetentionMode,
    RunEnvelope,
    ScoredCandidateSet,
    ScoredTrialCandidate,
    select,
)
from rostermonster.solver import (  # noqa: E402
    CandidateSet,
    TerminationBounds,
    solve,
)
from tests.fixtures import icu_hd_template_artifact  # noqa: E402
from tests.test_real_icu_hd_may_2026 import _load_real_snapshot  # noqa: E402


# Stable seed used across all assertions in this file so byte-identical
# checks are reproducible. Picked once and pinned here.
_RUN_SEED = 20260504


def _parsed_model():
    """Real snapshot → CONSUMABLE NormalizedModel via the production parser."""
    template = icu_hd_template_artifact()
    snapshot = _load_real_snapshot()
    result = parse(snapshot, template)
    assert result.consumability is Consumability.CONSUMABLE, (
        f"smoke-test fixture didn't parse CONSUMABLE; got "
        f"{result.consumability!r} with issues "
        f"{[i.code for i in result.issues]}"
    )
    return result.normalizedModel


# --- Pipeline shape -------------------------------------------------------


def test_pipeline_produces_non_empty_candidate_set() -> None:
    """`docs/solver_contract.md` §10.1: `CandidateSet.candidates` MUST be
    non-empty on the success branch. The integration check confirms the
    real ICU/HD May 2026 input feasibly produces candidate rosters under
    `SEEDED_RANDOM_BLIND` with default `crFloor`."""
    model = _parsed_model()
    result = solve(
        model,
        ruleEngine=rule_engine_evaluate,
        seed=_RUN_SEED,
        terminationBounds=TerminationBounds(maxCandidates=3),
    )
    assert isinstance(result, CandidateSet), (
        f"solver returned non-CandidateSet on real ICU/HD May 2026 input: "
        f"{type(result).__name__}; pipeline cannot reach the scorer"
    )
    assert len(result.candidates) == 3
    for cand in result.candidates:
        assert cand.assignments, "emitted candidate carries no assignments"
        assert all(
            isinstance(u.doctorId, str) and u.doctorId
            for u in cand.assignments
        ), (
            f"candidate {cand.candidateId} contains an unfilled "
            f"AssignmentUnit — solver §10.1 forbids partial-fill leakage"
        )


def test_each_candidate_passes_rule_engine_for_every_assignment() -> None:
    """`docs/solver_contract.md` §10.1: every emitted candidate MUST be free
    of rule-engine hard-validity violations. Equivalence check: for each
    `AssignmentUnit` in a candidate, build the rule state as the other
    assignments and confirm `rule_engine.evaluate(...)` admits the unit. If
    all units admit under the others, the roster is rule-engine-clean."""
    model = _parsed_model()
    result = solve(
        model,
        ruleEngine=rule_engine_evaluate,
        seed=_RUN_SEED,
        terminationBounds=TerminationBounds(maxCandidates=2),
    )
    assert isinstance(result, CandidateSet)
    for cand in result.candidates:
        units = cand.assignments
        for i, unit in enumerate(units):
            others = units[:i] + units[i + 1 :]
            decision = rule_engine_evaluate(
                model,
                RuleState(assignments=others),
                unit,
            )
            assert decision.valid, (
                f"hard-rule violation for {unit} in candidate "
                f"{cand.candidateId}: {decision.reasons}"
            )


# --- Scorer integration ---------------------------------------------------


def test_each_candidate_produces_a_complete_score_result() -> None:
    """`docs/scorer_contract.md` §10: every `ScoreResult.components` carries
    every first-release component identifier (zero-valued or otherwise) and
    `direction` is the `HIGHER_IS_BETTER` literal. Run the scorer over each
    candidate the solver emits and confirm shape conformance — this is the
    integration-level proof that the parser → solver → scorer handoff is
    type-compatible end-to-end."""
    model = _parsed_model()
    config = ScoringConfig.first_release_defaults(model)
    result = solve(
        model,
        ruleEngine=rule_engine_evaluate,
        seed=_RUN_SEED,
        terminationBounds=TerminationBounds(maxCandidates=2),
    )
    assert isinstance(result, CandidateSet)
    for cand in result.candidates:
        score_result = score(cand.assignments, model, config)
        assert score_result.direction is ScoreDirection.HIGHER_IS_BETTER
        for component in ALL_COMPONENTS:
            assert component in score_result.components, (
                f"candidate {cand.candidateId} missing component "
                f"{component!r} in ScoreResult"
            )
        # totalScore must equal the signed sum of components.
        recomputed = sum(score_result.components[c] for c in ALL_COMPONENTS)
        assert score_result.totalScore == recomputed, (
            f"totalScore {score_result.totalScore!r} != sum of components "
            f"{recomputed!r} for candidate {cand.candidateId}"
        )


# --- Determinism (§16) ----------------------------------------------------


def test_pipeline_is_byte_identical_under_fixed_seed() -> None:
    """`docs/solver_contract.md` §16: identical inputs MUST produce
    byte-identical outputs. Run the parser → solver → scorer pipeline twice
    on the same fixture + seed and assert the candidate assignments and
    score results match exactly."""
    bounds = TerminationBounds(maxCandidates=4)

    model_a = _parsed_model()
    config_a = ScoringConfig.first_release_defaults(model_a)
    result_a = solve(
        model_a,
        ruleEngine=rule_engine_evaluate,
        seed=_RUN_SEED,
        terminationBounds=bounds,
    )
    scores_a = [score(c.assignments, model_a, config_a) for c in result_a.candidates]

    model_b = _parsed_model()
    config_b = ScoringConfig.first_release_defaults(model_b)
    result_b = solve(
        model_b,
        ruleEngine=rule_engine_evaluate,
        seed=_RUN_SEED,
        terminationBounds=bounds,
    )
    scores_b = [score(c.assignments, model_b, config_b) for c in result_b.candidates]

    assert result_a == result_b, (
        "solver outputs diverged across re-runs on identical inputs — "
        "byte-identical determinism (§16) is broken"
    )
    assert scores_a == scores_b, (
        "scorer outputs diverged across re-runs on identical inputs — "
        "scorer §17 determinism broken under integration handoff"
    )


# --- Sorted candidate ranking (proves ranking pipeline is wired) ---------


def test_candidates_can_be_sorted_by_total_score() -> None:
    """`docs/scorer_contract.md` §10 + `docs/selector_contract.md` §11.1
    cascade: `HIGHER_IS_BETTER` direction means a sort by `totalScore`
    descending is the basic ranking primitive the selector consumes
    downstream. Confirm the integration produces a ranked list with
    monotone-non-increasing scores after sorting (the selector's
    `pointBalanceGlobal` / `crReward` / `candidateId` cascade is the
    selector's responsibility — this only checks the basic sort works)."""
    model = _parsed_model()
    config = ScoringConfig.first_release_defaults(model)
    result = solve(
        model,
        ruleEngine=rule_engine_evaluate,
        seed=_RUN_SEED,
        terminationBounds=TerminationBounds(maxCandidates=5),
    )
    assert isinstance(result, CandidateSet)
    scored = [
        (cand, score(cand.assignments, model, config))
        for cand in result.candidates
    ]
    scored.sort(key=lambda pair: pair[1].totalScore, reverse=True)
    for i in range(1, len(scored)):
        assert scored[i - 1][1].totalScore >= scored[i][1].totalScore


# --- M2 C5: selector stage --------------------------------------------------


def _envelope_for(seed: int, run_id: str = "smoke-run-0001") -> RunEnvelope:
    """Stable run envelope for the integration smoke. All fields fixed
    so byte-identical determinism (`docs/selector_contract.md` §18) can
    be asserted across re-runs of the entire pipeline."""
    return RunEnvelope(
        runId=run_id,
        snapshotRef="icu_hd_may_2026_snapshot.json",
        configRef="first_release_defaults",
        seed=seed,
        fillOrderPolicy="MOST_CONSTRAINED_FIRST",
        crFloorMode="SMART_MEDIAN",
        crFloorComputed=0,  # placeholder; smoke test doesn't assert on this
        generationTimestamp="2026-04-28T00:00:00Z",
        sourceSpreadsheetId="dev-copy-fixture",
        sourceTabName="ICU/HD May 2026",
    )


def _full_pipeline_to_envelope(
    *,
    seed: int,
    max_candidates: int,
    retention: RetentionMode,
    sidecar_dir: Path | None,
) -> FinalResultEnvelope:
    """Run parser → solver → scorer → selector and return the envelope."""
    model = _parsed_model()
    config = ScoringConfig.first_release_defaults(model)
    solver_result = solve(
        model,
        ruleEngine=rule_engine_evaluate,
        seed=seed,
        terminationBounds=TerminationBounds(maxCandidates=max_candidates),
    )
    assert isinstance(solver_result, CandidateSet)
    scored = ScoredCandidateSet(
        candidates=tuple(
            ScoredTrialCandidate(
                candidate=cand,
                score=score(cand.assignments, model, config),
            )
            for cand in solver_result.candidates
        ),
        diagnostics=solver_result.diagnostics,
    )
    return select(
        scored,
        retentionMode=retention,
        runEnvelope=_envelope_for(seed),
        sidecarTargetDir=sidecar_dir,
    )


def test_selector_picks_a_winner_on_real_data() -> None:
    """End-to-end success branch: parser → solver → scorer → selector
    on the real ICU/HD May 2026 fixture produces an `AllocationResult`
    with a non-empty `winnerAssignment` and full `winnerScore` component
    breakdown per `docs/selector_contract.md` §10.1 + §13.1."""
    env = _full_pipeline_to_envelope(
        seed=_RUN_SEED,
        max_candidates=3,
        retention=RetentionMode.BEST_ONLY,
        sidecar_dir=None,
    )
    assert isinstance(env.result, AllocationResult)
    assert env.result.winnerAssignment, "winning candidate has no assignments"
    for component in ALL_COMPONENTS:
        assert component in env.result.winnerScore.components
    assert env.result.winnerScore.direction is ScoreDirection.HIGHER_IS_BETTER
    # BEST_ONLY: no sidecar paths.
    assert env.result.candidatesSummaryPath is None
    assert env.result.candidatesFullPath is None


def test_full_retention_emits_sidecars_with_all_candidates() -> None:
    """End-to-end FULL retention: both sidecar files are written, the
    CSV row count matches `maxCandidates`, and the JSON candidate list
    matches by candidateId per `docs/selector_contract.md` §14."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td)
        env = _full_pipeline_to_envelope(
            seed=_RUN_SEED,
            max_candidates=4,
            retention=RetentionMode.FULL,
            sidecar_dir=target,
        )
        assert isinstance(env.result, AllocationResult)
        assert env.result.candidatesSummaryPath is not None
        assert env.result.candidatesFullPath is not None

        body_lines = (target / SUMMARY_FILE_NAME).read_text().splitlines()[1:]
        rows = list(csv.reader(body_lines))
        # rows[0] = header, rows[1..] = data; expect 4 data rows.
        assert len(rows) == 5
        # candidateId column should be 1..4 in emission order.
        assert [int(r[0]) for r in rows[1:]] == [1, 2, 3, 4]

        payload = json.loads((target / FULL_FILE_NAME).read_text())
        assert payload["runId"] == "smoke-run-0001"
        assert len(payload["candidates"]) == 4
        assert [c["candidateId"] for c in payload["candidates"]] == [1, 2, 3, 4]


def test_selector_byte_identical_re_runs_on_real_data() -> None:
    """End-to-end determinism: the full pipeline + selector + sidecar
    files are byte-identical across re-runs on identical inputs per
    `docs/selector_contract.md` §18 + `docs/solver_contract.md` §16.

    Compares content semantics, not the resolved sidecar paths — those
    legitimately differ when each re-run writes into its own temp
    directory (the path string is execution-layer-owned per §14.3, not
    a determinism property)."""
    with tempfile.TemporaryDirectory() as td_a, tempfile.TemporaryDirectory() as td_b:
        target_a = Path(td_a)
        target_b = Path(td_b)
        env_a = _full_pipeline_to_envelope(
            seed=_RUN_SEED,
            max_candidates=3,
            retention=RetentionMode.FULL,
            sidecar_dir=target_a,
        )
        env_b = _full_pipeline_to_envelope(
            seed=_RUN_SEED,
            max_candidates=3,
            retention=RetentionMode.FULL,
            sidecar_dir=target_b,
        )
        assert isinstance(env_a.result, AllocationResult)
        assert isinstance(env_b.result, AllocationResult)
        # Compare the determinism-relevant fields directly. `candidatesSummaryPath`
        # / `candidatesFullPath` legitimately vary across runs because the
        # caller picked different target directories.
        assert env_a.result.winnerAssignment == env_b.result.winnerAssignment
        assert env_a.result.winnerScore == env_b.result.winnerScore
        assert env_a.result.searchDiagnostics == env_b.result.searchDiagnostics
        assert env_a.result.trialBatches == env_b.result.trialBatches
        assert env_a.runEnvelope == env_b.runEnvelope
        assert env_a.retentionMode == env_b.retentionMode
        assert env_a.selectorStrategyId == env_b.selectorStrategyId
        # Sidecar file *contents* are byte-identical even though their
        # paths differ.
        assert (target_a / SUMMARY_FILE_NAME).read_bytes() == (
            target_b / SUMMARY_FILE_NAME
        ).read_bytes()
        assert (target_a / FULL_FILE_NAME).read_bytes() == (
            target_b / FULL_FILE_NAME
        ).read_bytes()


# --- standalone runner ----------------------------------------------------


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
