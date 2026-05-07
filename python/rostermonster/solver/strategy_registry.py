"""Strategy registry for the solver per `docs/solver_contract.md` §11.

Per §11.1 (Registered strategies — currently `SEEDED_RANDOM_BLIND` + `LAHC`)
and §11.2 (additive extension clause), the solver dispatches to a registered
strategy by `strategyId`. Unregistered `strategyId` values are rejected at
strategy-resolution time per §11.1, BEFORE any §10 `CandidateSet` /
`UnsatisfiedResult` construction begins.

`LAHC`'s algorithm implementation per §12A lands in **M6 C2 Task 2B** per
`docs/delivery_plan.md` §9. This module currently registers a placeholder
run function that raises `NotImplementedError` until then. Registering the
placeholder keeps the contract surface consistent with §11.1's listing —
`solve(strategyId="LAHC")` is a recognized call shape (no `ValueError` from
strategy resolution) but signals "not yet implemented" rather than silently
returning `SEEDED_RANDOM_BLIND` output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from rostermonster.solver.result import (
    STRATEGY_LAHC,
    STRATEGY_SEEDED_RANDOM_BLIND,
)
from rostermonster.solver.strategy import _StrategyOutcome, run_seeded_random_blind


@dataclass(frozen=True)
class _StrategyDescriptor:
    """Internal registry entry per `docs/solver_contract.md` §11.

    Maps to the contract's `StrategyDescriptor`:
    - `strategy_id` ↔ contract's `strategyId`.
    - `run` is the callable that produces a `_StrategyOutcome` per candidate
      construction. The callable signature follows
      `run_seeded_random_blind`'s pattern:
      `(rule_engine, model, candidate_seed, cr_floor_x) → _StrategyOutcome`.
    Additional contract fields (`requiredInputs`, `additionalInputs`,
    `scoringConsultation`) are encoded via the run-function signature
    convention; LAHC will extend that convention in M6 C2 Task 2B when the
    `scoringConsultation: "READ_ONLY_ORACLE"` extension clause activates per
    §11.2 + §12A.6.
    """

    strategy_id: str
    run: Callable[..., _StrategyOutcome]


def _run_lahc_placeholder(
    rule_engine, model, candidate_seed, cr_floor_x
) -> _StrategyOutcome:
    """Placeholder for the `LAHC` strategy registered in
    `docs/solver_contract.md` §11.1 + §12A. The algorithm spec is fully
    pinned in §12A (M6 C1 closure per `docs/decision_log.md` D-0067), but
    the implementation lands in **M6 C2 Task 2B** per
    `docs/delivery_plan.md` §9. Until then, calling
    `solve(strategyId="LAHC")` raises `NotImplementedError` with a pointer
    to where the implementation will arrive.
    """
    raise NotImplementedError(
        "LAHC strategy is registered (per docs/solver_contract.md §11.1 + "
        "§12A) but the algorithm implementation lands in M6 C2 Task 2B per "
        "docs/delivery_plan.md §9. Use strategyId='SEEDED_RANDOM_BLIND' "
        "until M6 C2 Task 2B closes."
    )


_REGISTRY: dict[str, _StrategyDescriptor] = {
    STRATEGY_SEEDED_RANDOM_BLIND: _StrategyDescriptor(
        strategy_id=STRATEGY_SEEDED_RANDOM_BLIND,
        run=run_seeded_random_blind,
    ),
    STRATEGY_LAHC: _StrategyDescriptor(
        strategy_id=STRATEGY_LAHC,
        run=_run_lahc_placeholder,
    ),
}


def get_strategy(strategy_id: str) -> _StrategyDescriptor:
    """Look up a registered strategy by `strategy_id`. Raises `ValueError`
    per `docs/solver_contract.md` §11.1 for unregistered ids — the
    rejection MUST happen at strategy-resolution time, BEFORE any §10
    output construction begins.
    """
    if strategy_id not in _REGISTRY:
        registered = sorted(_REGISTRY.keys())
        raise ValueError(
            f"Unknown strategyId {strategy_id!r}; registered strategies "
            f"per docs/solver_contract.md §11.1 are exactly {registered}"
        )
    return _REGISTRY[strategy_id]
