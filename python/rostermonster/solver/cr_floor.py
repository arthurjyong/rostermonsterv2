"""`crFloor` computation per `docs/solver_contract.md` §13.

Two modes:
- `SMART_MEDIAN` (default): `X = floor(median(CR-count-per-doctor))` over the
  full doctor set including doctors with zero `CR` requests (§13.1).
- `MANUAL`: `X = manualValue`, which MUST be `>= 0` per §13.2.

Returned `X` is logged in `SearchDiagnostics.crFloorComputed` per §13.4.
"""

from __future__ import annotations

from statistics import median

from rostermonster.domain import CanonicalRequestClass, NormalizedModel
from rostermonster.solver.result import CrFloorConfig, CrFloorMode


def compute_cr_floor(model: NormalizedModel, config: CrFloorConfig) -> int:
    """Compute Phase 1's `X` per solver §13.

    `SMART_MEDIAN`: median CR-count over all doctors (§13.1 — including
    doctors with zero CR requests). Floor of the median; fractional medians
    arise on even doctor counts and §13.1 specifies `floor(...)`.

    `MANUAL`: returns `manualValue` after validation (§13.2 — non-negative
    integer required).
    """
    if config.mode is CrFloorMode.MANUAL:
        if config.manualValue is None:
            raise ValueError(
                "CrFloorConfig.manualValue is required when mode = MANUAL "
                "per docs/solver_contract.md §13.2"
            )
        if config.manualValue < 0:
            raise ValueError(
                f"CrFloorConfig.manualValue must be >= 0 per "
                f"docs/solver_contract.md §13.2; got {config.manualValue!r}"
            )
        return config.manualValue

    cr_count_per_doctor: list[int] = []
    for doctor in model.doctors:
        count = sum(
            1
            for req in model.requests
            if req.doctorId == doctor.doctorId
            and CanonicalRequestClass.CR in req.canonicalClasses
        )
        cr_count_per_doctor.append(count)
    if not cr_count_per_doctor:
        return 0
    return int(median(cr_count_per_doctor))
