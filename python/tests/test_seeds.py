"""Tests for the shared K-trajectory seed-derivation helper per
`docs/solver_contract.md` §12A.10.

Covers determinism, the load-bearing `_UINT64_MASK` negative-seed handling
that prevents CPython's `Random.seed(int)` `abs(...)` from aliasing
contract-valid `seed` and `-seed` inputs, K-boundary cases (`K=0`, `K=1`,
the M7 C2 closure-K of 104), input validation, and byte-identity with the
pre-helper inline `Random + getrandbits(63)` loop the solver used before
M7 C2 Task 2A.

Standalone runnable via `python3 python/tests/test_seeds.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from random import Random

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rostermonster.solver import derive_K_seeds  # noqa: E402  (re-export check)
from rostermonster.solver.seeds import (  # noqa: E402
    _UINT64_MASK,
    _per_candidate_seed,
)
from rostermonster.solver.seeds import (  # noqa: E402
    derive_K_seeds as derive_K_seeds_direct,
)


# --- Re-export sanity ----------------------------------------------------


def test_public_export_is_same_object() -> None:
    """`from rostermonster.solver import derive_K_seeds` must resolve to the
    same callable as the direct seeds-module import — the orchestrator (M7
    C2 Task 2D) relies on the package re-export."""
    assert derive_K_seeds is derive_K_seeds_direct


# --- Determinism (§12A.10) ----------------------------------------------


def test_deterministic_across_invocations() -> None:
    """Same `(masterSeed, K)` MUST produce byte-identical output across
    invocations per §12A.10."""
    seeds_a = derive_K_seeds(42, 104)
    seeds_b = derive_K_seeds(42, 104)
    assert seeds_a == seeds_b


def test_returns_list_of_int_of_length_K() -> None:
    """Return type is `list[int]` of length `K` per the §12A.10 signature."""
    seeds = derive_K_seeds(42, 7)
    assert isinstance(seeds, list)
    assert len(seeds) == 7
    assert all(isinstance(s, int) for s in seeds)


def test_K_zero_returns_empty_list() -> None:
    """`K = 0` returns `[]` (no trajectories to seed)."""
    assert derive_K_seeds(42, 0) == []


def test_K_one_returns_single_seed() -> None:
    """`K = 1` returns a 1-element list — the SEEDED_RANDOM_BLIND single-K
    case still flows through the helper."""
    seeds = derive_K_seeds(42, 1)
    assert len(seeds) == 1


def test_K_104_matches_M7_C2_closure_K() -> None:
    """M7 C2's closure-K is 104 trajectories (per D-0070 sub-decision 7's
    three-quota rule + C3_CPUS=108 binding cap). Sanity-check the helper at
    the actual production K so any boundary issue at large K surfaces."""
    seeds = derive_K_seeds(42, 104)
    assert len(seeds) == 104
    # All 104 must be unique with overwhelming probability — a degenerate
    # implementation that returned the same seed K times would be caught.
    assert len(set(seeds)) == 104


# --- Sequential-stream byte-identity vs the pre-helper inline loop ------


def test_byte_identical_to_inline_pre_helper_loop() -> None:
    """The helper MUST produce the SAME seed sequence the solver emitted
    pre-M7-C2-Task-2A (inline `Random(seed & _UINT64_MASK)` +
    `rng.getrandbits(63)` per iteration). This guarantees that the refactor
    leaves all existing local-CLI runs byte-identical per §12A.10's
    "sequential stream advance, NOT index-addressable" property."""
    master_seed = 12345
    K = 50
    # Reconstruct the pre-helper inline derivation.
    rng = Random(master_seed & _UINT64_MASK)
    expected = [rng.getrandbits(63) for _ in range(K)]
    actual = derive_K_seeds(master_seed, K)
    assert actual == expected


def test_byte_identical_for_negative_seed() -> None:
    """Negative-seed path MUST also match the pre-helper inline loop
    byte-for-byte — this is the load-bearing case the `_UINT64_MASK` step
    exists for."""
    master_seed = -12345
    K = 50
    rng = Random(master_seed & _UINT64_MASK)
    expected = [rng.getrandbits(63) for _ in range(K)]
    actual = derive_K_seeds(master_seed, K)
    assert actual == expected


# --- Negative-seed mask preservation (§12A.10 + §12A.4) -----------------


def test_negated_master_seed_produces_distinct_sequence() -> None:
    """Per `docs/solver_contract.md` §12A.10: the helper MUST apply
    `_UINT64_MASK` so contract-valid `seed` and `-seed` inputs produce
    DIFFERENT seed sequences. CPython's `Random.seed(int)` normalizes via
    `abs(...)`, which without the mask would alias `seed` and `-seed` —
    this is the same regression the M5-era PR #85 fix prevented at the
    solver's inline loop, now enforced inside the shared helper."""
    pos = derive_K_seeds(12345, 8)
    neg = derive_K_seeds(-12345, 8)
    assert pos != neg, (
        "derive_K_seeds(12345, K) and derive_K_seeds(-12345, K) emitted "
        "identical seed sequences — _UINT64_MASK was bypassed; the "
        "Random.seed(int) abs() aliasing is back."
    )


def test_seed_zero_works() -> None:
    """`masterSeed = 0` is a contract-valid input (§9 64-bit signed range
    includes 0). MUST produce a valid K-element list."""
    seeds = derive_K_seeds(0, 5)
    assert len(seeds) == 5


def test_int64_min_and_max_seed_boundaries() -> None:
    """The full 64-bit signed range is contract-valid per §9. MUST not
    raise at the boundaries and MUST produce distinct streams."""
    int64_min = -(2**63)
    int64_max = 2**63 - 1
    s_min = derive_K_seeds(int64_min, 3)
    s_max = derive_K_seeds(int64_max, 3)
    assert len(s_min) == 3
    assert len(s_max) == 3
    assert s_min != s_max


def test_different_master_seeds_produce_different_sequences() -> None:
    """Sanity check against pathologically-constant implementations: two
    different `masterSeed` values MUST emit different sequences for K > 0."""
    a = derive_K_seeds(1, 8)
    b = derive_K_seeds(2, 8)
    assert a != b


# --- Sequential-stream advance (NOT index-addressable) ------------------


def test_K_plus_one_extends_K_sequence() -> None:
    """§12A.10 pins sequential stream advance: `derive_K_seeds(s, K+1)`'s
    first K elements MUST equal `derive_K_seeds(s, K)`. This guarantees
    that growing K appends; it never reshuffles the prefix."""
    base = derive_K_seeds(42, 10)
    extended = derive_K_seeds(42, 11)
    assert extended[:10] == base
    assert len(extended) == 11


# --- Input validation ----------------------------------------------------


def test_negative_K_rejected() -> None:
    """`K < 0` is a caller bug — fail fast at the boundary."""
    try:
        derive_K_seeds(42, -1)
    except ValueError as e:
        assert "K" in str(e)
        return
    raise AssertionError("derive_K_seeds(_, -1) should have raised ValueError")


def test_non_int_K_rejected() -> None:
    """`K` must be an `int`. Strings, floats, None all reject — same
    boundary discipline as `terminationBounds.maxCandidates` at §15."""
    for bad_K in ("3", 3.0, None, 3.5):
        try:
            derive_K_seeds(42, bad_K)  # type: ignore[arg-type]
        except ValueError as e:
            assert "K" in str(e)
            continue
        raise AssertionError(f"derive_K_seeds(_, {bad_K!r}) should have raised ValueError")


def test_bool_K_rejected() -> None:
    """`bool` is an `int` subclass in Python; reject `True`/`False`
    explicitly so they don't slip through as `1`/`0`. Same discipline as
    solver.py's `seed` and `terminationBounds.maxCandidates` validation."""
    for bad_K in (True, False):
        try:
            derive_K_seeds(42, bad_K)  # type: ignore[arg-type]
        except ValueError as e:
            assert "K" in str(e)
            continue
        raise AssertionError(f"derive_K_seeds(_, {bad_K!r}) should have raised ValueError")


def test_non_int_master_seed_rejected() -> None:
    """`masterSeed` must satisfy §9 input #3 — a 64-bit signed integer.
    Validation lives in the helper (NOT only in `solve()`) because the M7
    C2 Task 2D orchestrator calls `derive_K_seeds` directly with decoded
    request data BEFORE the per-task workers invoke `solve()`. Without the
    helper-side guard, non-int seeds would either TypeError deep in the
    `& _UINT64_MASK` step or silently produce wrong trajectory seeds."""
    for bad_seed in ("42", 1.5, None, b"\x00\x00"):
        try:
            derive_K_seeds(bad_seed, 3)  # type: ignore[arg-type]
        except ValueError as e:
            assert "masterSeed" in str(e)
            continue
        raise AssertionError(f"derive_K_seeds({bad_seed!r}, 3) should have raised ValueError")


def test_bool_master_seed_rejected() -> None:
    """`bool` is an `int` subclass — reject `True`/`False` explicitly so
    they don't slip through as `masterSeed=1`/`masterSeed=0`. Same
    isinstance-with-bool-rejection discipline `solve()` applies to its
    `seed` parameter at the §9 boundary."""
    for bad_seed in (True, False):
        try:
            derive_K_seeds(bad_seed, 3)  # type: ignore[arg-type]
        except ValueError as e:
            assert "masterSeed" in str(e)
            continue
        raise AssertionError(f"derive_K_seeds({bad_seed!r}, 3) should have raised ValueError")


def test_master_seed_above_int64_max_rejected() -> None:
    """§9 input #3 caps `seed` at `INT64_MAX = 2**63 - 1`. Out-of-range
    ints would silently alias modulo `_UINT64_MASK = 2**64 - 1` if the
    helper's range check were bypassed — this test guards the §9 ceiling."""
    int64_max = 2**63 - 1
    try:
        derive_K_seeds(int64_max + 1, 3)
    except ValueError as e:
        assert "masterSeed" in str(e)
        return
    raise AssertionError("derive_K_seeds(INT64_MAX + 1, 3) should have raised ValueError")


def test_master_seed_below_int64_min_rejected() -> None:
    """§9 input #3 floors `seed` at `INT64_MIN = -(2**63)`. Mirror of the
    `INT64_MAX + 1` test — guards the §9 lower bound."""
    int64_min = -(2**63)
    try:
        derive_K_seeds(int64_min - 1, 3)
    except ValueError as e:
        assert "masterSeed" in str(e)
        return
    raise AssertionError("derive_K_seeds(INT64_MIN - 1, 3) should have raised ValueError")


# --- Internal primitives still match contract ---------------------------


def test_per_candidate_seed_uses_63_bits() -> None:
    """`_per_candidate_seed` MUST use `getrandbits(63)` per §12A.10's
    sequential-stream-advance property. A 64-bit draw would shift the
    sequence and break byte-identity with all pre-Task-2A archival runs."""
    rng = Random(0)
    s = _per_candidate_seed(rng)
    # 63 bits ⇒ 0 <= s < 2**63 (signed-int positive range).
    assert 0 <= s < (1 << 63)


def test_uint64_mask_is_64_bit_unsigned_max() -> None:
    """`_UINT64_MASK` MUST be `2**64 - 1`. Any other value would not align
    `seed` and `-seed` to distinct bit patterns under CPython's
    `Random.seed(int)` `abs(...)` normalization."""
    assert _UINT64_MASK == (1 << 64) - 1


# --- Standalone runner ---------------------------------------------------


if __name__ == "__main__":
    import inspect

    failures = 0
    funcs = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    for name, fn in funcs:
        try:
            sig = inspect.signature(fn)
            if len(sig.parameters) > 0:
                continue
            fn()
            print(f"ok   {name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {name}: {exc}")
    if failures:
        sys.exit(1)
