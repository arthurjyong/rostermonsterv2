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
from rostermonster.solver.result import (
    FILL_ORDER_POLICY_MOST_CONSTRAINED_FIRST,
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
from rostermonster.solver.solver import solve

__all__ = [
    "solve",
    "compute_cr_floor",
    "CandidateSet",
    "UnsatisfiedResult",
    "TrialCandidate",
    "UnfilledDemandEntry",
    "SearchDiagnostics",
    "CrFloorConfig",
    "CrFloorMode",
    "PreferenceSeedingConfig",
    "TerminationBounds",
    "STRATEGY_SEEDED_RANDOM_BLIND",
    "FILL_ORDER_POLICY_MOST_CONSTRAINED_FIRST",
]
