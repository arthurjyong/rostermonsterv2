"""Solver module per `docs/solver_contract.md`.

Public entry: `solve(normalizedModel, *, seed, terminationBounds,
preferenceSeeding=None, fillOrderPolicy=..., strategyId=...) →
CandidateSet | UnsatisfiedResult`.

Pure-function reference implementation of `SEEDED_RANDOM_BLIND` per §11.1 +
§12. Phase 1 (`CR_MINIMUM_PER_DOCTOR`) seeds CR placements up to `crFloor`;
Phase 2 (`MOST_CONSTRAINED_FIRST`) fills the remaining demand. The solver is
scoring-blind end-to-end and never imports `rostermonster.scorer`.
"""

from rostermonster.solver.cr_floor import compute_cr_floor
from rostermonster.solver.lahc import LahcParams
from rostermonster.solver.result import (
    FILL_ORDER_POLICY_MOST_CONSTRAINED_FIRST,
    STRATEGY_LAHC,
    STRATEGY_SEEDED_RANDOM_BLIND,
    CandidateSet,
    CrFloorConfig,
    CrFloorMode,
    PreferenceSeedingConfig,
    SearchDiagnostics,
    TerminationBounds,
    TrialCandidate,
    UnfilledDemandEntry,
    UnsatisfiedResult,
)
from rostermonster.solver.seeds import derive_K_seeds
from rostermonster.solver.solver import solve
from rostermonster.solver.strategy import RuleEngineFn

__all__ = [
    "solve",
    "compute_cr_floor",
    "derive_K_seeds",
    "CandidateSet",
    "UnsatisfiedResult",
    "TrialCandidate",
    "UnfilledDemandEntry",
    "SearchDiagnostics",
    "CrFloorConfig",
    "CrFloorMode",
    "PreferenceSeedingConfig",
    "TerminationBounds",
    "RuleEngineFn",
    "LahcParams",
    "STRATEGY_SEEDED_RANDOM_BLIND",
    "STRATEGY_LAHC",
    "FILL_ORDER_POLICY_MOST_CONSTRAINED_FIRST",
]
