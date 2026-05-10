"""Shared K-trajectory seed-derivation helper per `docs/solver_contract.md`
§12A.10 (pinned in M7 C2 Task 1, 2026-05-10) per `docs/decision_log.md`
D-0070 sub-decision 8.

Public entry: `derive_K_seeds(masterSeed, K) -> list[int]`.

This module is the single source of truth for the K-trajectory seed
sequence consumed by LAHC's outer loop (§12A.2). Both the local CLI's
K-trajectory loop in `solver.py` AND the Cloud Run Service orchestrator
(M7 C2 Task 2D) call this same helper, guaranteeing byte-identical seed
sequences across surfaces — including the negative-seed `_UINT64_MASK`
semantics that prevent CPython's `Random.seed(int)` `abs(...)` from
aliasing `seed` and `-seed` for contract-valid negative seeds.
"""

from __future__ import annotations

from random import Random

# 64-bit unsigned mask applied to `masterSeed` before initializing the
# underlying `Random` stream. CPython's `Random.seed(int)` normalizes via
# `abs(seed)`, which would otherwise collapse `seed`/`-seed` pairs into the
# same RNG stream — so contract-valid inputs `1` and `-1` would generate
# identical candidate trajectories despite §9 accepting the full signed
# 64-bit range. Load-bearing per §12A.10.
_UINT64_MASK = (1 << 64) - 1


def _per_candidate_seed(rng: Random) -> int:
    """Single-step seed derivation. Sequential stream advance via
    `rng.getrandbits(63)` keeps each emitted seed inside the 64-bit signed
    range used by `Random()` and stays deterministic under the parent
    stream. NOT index-addressable per §12A.10."""
    return rng.getrandbits(63)


def derive_K_seeds(masterSeed: int, K: int) -> list[int]:
    """Derive `K` per-trajectory seeds from `masterSeed` per
    `docs/solver_contract.md` §12A.10.

    Returns a list of length `K` containing the K trajectory seeds in
    trajectory-index order: `[trajectorySeed_0, ..., trajectorySeed_{K-1}]`.

    Determinism: same `(masterSeed, K)` produces byte-identical output
    across invocations and across surfaces (local CLI vs Cloud Run Service
    orchestrator) per §12A.10.

    `K = 0` returns `[]`. `K < 0` is a caller bug (rejected at the boundary).
    """
    if isinstance(K, bool) or not isinstance(K, int):
        raise ValueError(
            f"K must be a non-negative integer per "
            f"docs/solver_contract.md §12A.10; got "
            f"{type(K).__name__}={K!r}"
        )
    if K < 0:
        raise ValueError(
            f"K must be a non-negative integer per "
            f"docs/solver_contract.md §12A.10; got {K!r}"
        )
    rng = Random(masterSeed & _UINT64_MASK)
    return [_per_candidate_seed(rng) for _ in range(K)]
