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

    Mode comparison uses value equality (`==`), not identity (`is`).
    `CrFloorMode` is a `(str, Enum)`, so callers MAY legitimately pass the
    bare string `"MANUAL"` per the contract's value vocabulary; identity
    comparison would silently treat the string as `SMART_MEDIAN`.
    """
    if config.mode == CrFloorMode.MANUAL:
        manual = config.manualValue
        if manual is None:
            raise ValueError(
                "CrFloorConfig.manualValue is required when mode = MANUAL "
                "per docs/solver_contract.md §13.2"
            )
        # `bool` is a subclass of `int` in Python; reject it explicitly so
        # `True`/`False` don't slip through as 1/0 — the contract requires a
        # non-negative integer, and a boolean configuration value is almost
        # certainly a caller-side bug.
        if isinstance(manual, bool) or not isinstance(manual, int):
            raise ValueError(
                f"CrFloorConfig.manualValue must be a non-negative integer "
                f"per docs/solver_contract.md §13.2; got "
                f"{type(manual).__name__}={manual!r}"
            )
        if manual < 0:
            raise ValueError(
                f"CrFloorConfig.manualValue must be >= 0 per "
                f"docs/solver_contract.md §13.2; got {manual!r}"
            )
        return manual
    if config.mode != CrFloorMode.SMART_MEDIAN:
        raise ValueError(
            f"Unknown CrFloorConfig.mode {config.mode!r}; first-release "
            f"modes are exactly {{ SMART_MEDIAN, MANUAL }} per "
            f"docs/solver_contract.md §13"
        )

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
