"""Tests for `rostermonster.pipeline.run_pipeline()` per
`docs/decision_log.md` D-0050 (shared compute core) + D-0053 (random
seed default).

The shared core is what both the local CLI wrapper
(`rostermonster.run`) and the cloud HTTP wrapper
(`rostermonster_service.app`) call. Tests here verify:

- Random seed default (per D-0053): omitted seed produces a fresh
  random seed each call; the resolved seed is captured in
  `PipelineResult.resolved_seed` AND in `envelope.runEnvelope.seed`
  for replay.
- Explicit seed override: same `(snapshot, seed)` produces byte-
  identical envelopes (per D-0050 parity claim with refined
  precondition from D-0053).
- Default candidate budget: omitted `max_candidates` falls back to
  `_DEFAULT_MAX_CANDIDATES = 32` from `pipeline`.

Standalone runnable via `python3 python/tests/test_pipeline.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rostermonster.pipeline import (  # noqa: E402
    _DEFAULT_MAX_CANDIDATES,
    _RANDOM_SEED_MAX,
    _snapshot_from_dict,
    run_pipeline,
)
from rostermonster.selector import RetentionMode  # noqa: E402
from rostermonster.templates import icu_hd_template_artifact  # noqa: E402


_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "data" / "icu_hd_may_2026_snapshot.json"
)


def _load_fixture():
    raw = json.loads(_FIXTURE_PATH.read_text())
    return _snapshot_from_dict(raw)


def test_random_seed_default_picks_fresh_seed_each_call() -> None:
    """Per D-0053, omitted seed picks a fresh `random.randint` value
    per invocation. Two omitted-seed calls produce different
    `resolved_seed` values (with extremely high probability — 2^31
    namespace makes collisions negligible).

    Both runs use `max_candidates=2` to keep the test fast; the
    determinism property under test is about the seed, not the
    search depth.
    """
    snapshot = _load_fixture()
    template = icu_hd_template_artifact()

    result_a = run_pipeline(snapshot, template, max_candidates=2)
    result_b = run_pipeline(snapshot, template, max_candidates=2)

    assert result_a.state == "OK", \
        f"expected OK on real fixture, got {result_a.state}"
    assert result_b.state == "OK", \
        f"expected OK on real fixture, got {result_b.state}"
    assert 0 <= result_a.resolved_seed <= _RANDOM_SEED_MAX, \
        f"random seed should be in [0, {_RANDOM_SEED_MAX}]; " \
        f"got {result_a.resolved_seed}"
    assert 0 <= result_b.resolved_seed <= _RANDOM_SEED_MAX
    assert result_a.resolved_seed != result_b.resolved_seed, \
        f"two omitted-seed runs should produce different random seeds; " \
        f"got identical seed {result_a.resolved_seed}. (Possible RNG " \
        f"determinism leak.)"


def test_random_seed_recorded_in_run_envelope() -> None:
    """The resolved seed (random or explicit) MUST flow through to
    `envelope.runEnvelope.seed` so the operator can replay any run by
    passing that value back. Per D-0053 + selector v2 §9 item 3."""
    snapshot = _load_fixture()
    template = icu_hd_template_artifact()
    result = run_pipeline(snapshot, template, max_candidates=2)

    assert result.envelope is not None
    assert result.envelope.runEnvelope.seed == result.resolved_seed, (
        f"runEnvelope.seed should equal resolved_seed for replay; "
        f"got runEnvelope.seed={result.envelope.runEnvelope.seed}, "
        f"resolved_seed={result.resolved_seed}"
    )


def test_explicit_seed_produces_byte_identical_runs() -> None:
    """D-0050 dual-track parity claim with D-0053 refined precondition:
    same `(snapshot, optionalConfig)` produces byte-identical envelopes
    WHEN seed is explicitly set."""
    snapshot = _load_fixture()
    template = icu_hd_template_artifact()
    result_a = run_pipeline(snapshot, template, max_candidates=3, seed=42)
    result_b = run_pipeline(snapshot, template, max_candidates=3, seed=42)

    assert result_a.state == "OK"
    assert result_b.state == "OK"
    assert result_a.resolved_seed == 42
    assert result_b.resolved_seed == 42
    # Compare envelopes via their dataclass equality (envelopes are
    # frozen dataclasses; equality is field-wise).
    assert result_a.envelope == result_b.envelope, (
        "two explicit-seed runs at seed=42 should produce identical "
        "envelopes; got divergence — D-0050 parity claim broken"
    )


def test_default_max_candidates_resolves_to_pipeline_constant() -> None:
    """Per `docs/cloud_compute_contract.md` §9.3, omitted maxCandidates
    falls back to `_DEFAULT_MAX_CANDIDATES` (currently 32) from the
    shared core. Both surfaces tie to this same constant for parity."""
    snapshot = _load_fixture()
    template = icu_hd_template_artifact()
    # Pin the seed so the run completes fast + deterministically; the
    # property under test is about the resolved candidate budget, not
    # the search outcome.
    result = run_pipeline(snapshot, template, seed=12345)

    assert result.resolved_max_candidates == _DEFAULT_MAX_CANDIDATES, (
        f"omitted max_candidates should resolve to "
        f"_DEFAULT_MAX_CANDIDATES={_DEFAULT_MAX_CANDIDATES}; "
        f"got {result.resolved_max_candidates}"
    )


def test_explicit_max_candidates_passes_through() -> None:
    """Explicit max_candidates overrides the default and shows up in
    `resolved_max_candidates`."""
    snapshot = _load_fixture()
    template = icu_hd_template_artifact()
    result = run_pipeline(snapshot, template, max_candidates=5, seed=99)
    assert result.resolved_max_candidates == 5


def test_state_dispatch_ok_on_real_fixture() -> None:
    """Real ICU/HD May 2026 fixture is CONSUMABLE + produces a non-
    empty CandidateSet at modest seed/budget — should land at OK
    state, populated envelope, parser_issues empty."""
    snapshot = _load_fixture()
    template = icu_hd_template_artifact()
    result = run_pipeline(snapshot, template, max_candidates=3, seed=20260504)

    assert result.state == "OK"
    assert result.envelope is not None
    assert result.parser_issues == ()
    assert result.candidate_count == 3


def test_full_retention_emits_sidecars() -> None:
    """FULL retention mode produces sidecar files in the target dir.
    The shared core honors retention_mode + sidecar_dir directly per
    D-0050 (file-system side effects are caller-controlled)."""
    import tempfile
    snapshot = _load_fixture()
    template = icu_hd_template_artifact()
    with tempfile.TemporaryDirectory() as td:
        sidecar_dir = Path(td)
        result = run_pipeline(
            snapshot, template,
            max_candidates=3, seed=20260504,
            retention_mode=RetentionMode.FULL,
            sidecar_dir=sidecar_dir,
        )
        assert result.state == "OK"
        assert result.envelope is not None
        # Sidecar files materialized in the target dir per
        # `docs/selector_contract.md` §13 / §14.
        files = sorted(p.name for p in sidecar_dir.iterdir())
        assert any("candidates_summary" in f for f in files), \
            f"expected candidates_summary sidecar; got {files}"
        assert any("candidates_full" in f for f in files), \
            f"expected candidates_full sidecar; got {files}"


# Minimal pytest-equivalent runner for standalone invocation.
def _run() -> int:
    tests = [
        ("test_random_seed_default_picks_fresh_seed_each_call",
         test_random_seed_default_picks_fresh_seed_each_call),
        ("test_random_seed_recorded_in_run_envelope",
         test_random_seed_recorded_in_run_envelope),
        ("test_explicit_seed_produces_byte_identical_runs",
         test_explicit_seed_produces_byte_identical_runs),
        ("test_default_max_candidates_resolves_to_pipeline_constant",
         test_default_max_candidates_resolves_to_pipeline_constant),
        ("test_explicit_max_candidates_passes_through",
         test_explicit_max_candidates_passes_through),
        ("test_state_dispatch_ok_on_real_fixture",
         test_state_dispatch_ok_on_real_fixture),
        ("test_full_retention_emits_sidecars",
         test_full_retention_emits_sidecars),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(_run())
