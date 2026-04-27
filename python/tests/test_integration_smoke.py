"""M2 C4 T4 — integration smoke test (parser → solver → scorer end-to-end).

Exercises the full M2 compute pipeline against the real ICU/HD May 2026
snapshot fixture committed under `python/tests/data/`:

    Snapshot → parse() → CONSUMABLE NormalizedModel
            → solve() → CandidateSet
            → score() per candidate → ranked roster

Assertions cover the §10.1 success-branch invariants the solver promises
and the additional integration checks `docs/delivery_plan.md` §8 T4
specifies — non-empty CandidateSet, byte-identical re-runs under fixed
seed, zero rule-engine hard-rule violations across emitted candidates.

Pytest-compatible. Standalone runnable via
`python3 python/tests/test_integration_smoke.py`.
"""

from __future__ import annotations

import sys
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
