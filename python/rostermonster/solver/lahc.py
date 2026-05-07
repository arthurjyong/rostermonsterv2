"""Late Acceptance Hill Climbing (LAHC) strategy implementation per
`docs/solver_contract.md` §12A. Pinned in M6 C1 closure (D-0067).

Inner loop produces ONE candidate per call (per the strategy-registry's
per-candidate dispatch surface). The K-trajectory outer loop (K independent
seeded trajectories per §12A.2) lives in `solver.solve()` — each trajectory
calls `run_lahc(...)` once with its own derived seed, and `solve()` collects
the K resulting `_StrategyOutcome`s into a `CandidateSet`.

Algorithm (§12A.1):
1. Seed roster via `SEEDED_RANDOM_BLIND` (Phase 1 + Phase 2). If seed fails,
   propagate `_StrategyOutcome.unfillable` upstream — caller decides whether
   to drop the trajectory or fail the run per §12A.8 + §14.
2. Initialize history list of length `L` with the seed score in every slot.
3. Inner loop: random move generation → score → dual-clause accept → state
   update → history overwrite → best-roster + idle counter → increment.
4. Terminate when `idleIters >= idleThreshold` OR `currentIter >= maxIters`.
5. Emit `bestRoster` (NOT terminal `currentRoster`) — late-acceptance can
   leave terminal below `bestSoFar`, and emitting terminal would discard a
   higher-scoring roster the trajectory already discovered.

Move generator (§12A.1.a — implementation-defined): **mix of pairwise
doctor swap (between two non-fixed cells) AND single-cell reassignment
(replace a non-fixed cell's doctor with a different eligible doctor)**.
Each iteration picks one move type uniformly at random:

- **Swap** preserves total assignment count + section/slot demand, but
  cannot introduce a doctor not already present on the seed roster — the
  swap-only space is a permutation closure over the seed-roster doctor set.
- **Reassign** can change which doctors are present on the roster
  (replacing X at one cell with Y, where Y might not be on the roster
  before). This restores ergodicity over the rule-engine-valid roster
  space — any rule-valid roster is reachable from any other via finite
  composition of reassignments, even when the seed roster doesn't use
  every doctor.

Move generator is deterministic given `trajectorySeed_i` + iteration order
(single `Random` seeded once at trajectory start; controls both move-type
choice and within-type random selection).

Scoring oracle (§12A.6): `LAHC` opts into the §11.2 extension clause
`scoringConsultation: "READ_ONLY_ORACLE"`. The oracle is a caller-supplied
callable `(NormalizedModel, tuple[AssignmentUnit, ...]) → float` that
returns the candidate's `ScoreResult.totalScore` per `docs/scorer_contract.md`.
The strategy MUST treat the oracle as read-only — no scorer mutation, no
direction override, no scorer-owned-component alteration.

Determinism (§12A.4): byte-identical output at fixed
`(model, candidate_seed, cr_floor_x, scoring_oracle, lahc_params)` is
preserved by:
- The trajectory's RNG is seeded once from `candidate_seed`.
- Move generation reads from this RNG only (no ambient entropy).
- Scoring is deterministic per `docs/scorer_contract.md` §17 — the read-only
  oracle preserves this property.
- Termination is iteration-count based (idle / hard-iter); wall-clock is
  excluded per §15 + §12A.3.
"""

from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Callable

from rostermonster.domain import AssignmentUnit, NormalizedModel
from rostermonster.rule_engine.state import RuleState
# §12A.6 + §11.2 extension clause authorizes this scorer import. LAHC is the
# only solver-package module allowed to consume the scorer interface (read-
# only). All other solver modules remain scoring-blind per §9 + §11.
from rostermonster.scorer.scorer import score as _scorer_score
from rostermonster.scorer.result import ScoringConfig
from rostermonster.solver.strategy import (
    RuleEngineFn,
    _StrategyOutcome,
    run_seeded_random_blind,
)

# Type alias for the read-only scoring oracle injected by `solve()`. The
# oracle MUST be a deterministic function of `(model, assignments)` per
# `docs/scorer_contract.md` §17.
ScoringOracleFn = Callable[[NormalizedModel, tuple[AssignmentUnit, ...]], float]


@dataclass(frozen=True)
class LahcParams:
    """LAHC strategy-specific configuration per `docs/solver_contract.md`
    §11.2 (`additionalInputs.lahcParams`) + §12A.5 defaults.

    - `historyListLength` (`L`): default 1000 per literature priors (Burke
      & Bykov 2017; `L ∈ [500, 10000]` for combinatorial problems at
      roster scale).
    - `idleThreshold`: default 5000 (= 5 × L) per LAHC convention.
    - `maxIters`: default 100,000 — the v1 algorithm ceiling per
      trajectory. Cloud-mode operator-defaults will likely be smaller per
      §12A.5's cloud sync-budget caveat (deferred to FW-0035 per D-0068).
    """

    historyListLength: int = 1000
    idleThreshold: int = 5000
    maxIters: int = 100_000

    def __post_init__(self) -> None:
        # Fail-loud at construction: contract-§12A.5 invariants.
        if (
            isinstance(self.historyListLength, bool)
            or not isinstance(self.historyListLength, int)
            or self.historyListLength <= 0
        ):
            raise ValueError(
                f"LahcParams.historyListLength must be a positive integer "
                f"per docs/solver_contract.md §12A.5; got "
                f"{type(self.historyListLength).__name__}="
                f"{self.historyListLength!r}"
            )
        if (
            isinstance(self.idleThreshold, bool)
            or not isinstance(self.idleThreshold, int)
            or self.idleThreshold <= 0
        ):
            raise ValueError(
                f"LahcParams.idleThreshold must be a positive integer "
                f"per docs/solver_contract.md §12A.5; got "
                f"{type(self.idleThreshold).__name__}="
                f"{self.idleThreshold!r}"
            )
        if (
            isinstance(self.maxIters, bool)
            or not isinstance(self.maxIters, int)
            or self.maxIters <= 0
        ):
            raise ValueError(
                f"LahcParams.maxIters must be a positive integer "
                f"per docs/solver_contract.md §12A.5; got "
                f"{type(self.maxIters).__name__}={self.maxIters!r}"
            )


# Maximum move-generation attempts per inner-loop iteration before
# concluding the current state is rule-locked (no valid move of the chosen
# type reachable). 100 is a conservative ceiling — at ICU/HD scale
# (~116 cells, ~22 doctors) the rule-valid move density is high enough
# that 100 random tries almost always finds one. If exhausted, the
# trajectory terminates early with the best roster found so far.
_MOVE_GENERATION_MAX_TRIES = 100

# RNG-seed distinguisher — XORed with `candidate_seed` to get a separate
# RNG stream for inner-loop move selection that doesn't collide with the
# RNG stream used by `run_seeded_random_blind` to build the seed roster.
# The literal value is arbitrary; pinning it makes the LAHC trajectory's
# move sequence deterministic given `candidate_seed`.
_LAHC_RNG_DISTINGUISHER = 0x4C41_4843_5247_4E47  # "LAHCRGNG" interpreted as hex


def make_scoring_oracle(scoring_config: ScoringConfig) -> ScoringOracleFn:
    """Construct a read-only scoring oracle from a `ScoringConfig` per
    `docs/solver_contract.md` §12A.6 + §11.2's extension clause.

    The returned callable evaluates one candidate allocation and returns
    its `ScoreResult.totalScore` per `docs/scorer_contract.md` §10. The
    oracle is read-only — LAHC MUST NOT mutate scoring logic, override
    direction, or alter scorer-owned components.

    Lives here (in the LAHC-specific module) rather than in `solver.py` so
    the solver core stays scoring-blind by default; the §12A.6 exception is
    encapsulated in the strategy module that opts into it.
    """

    def _oracle(model: NormalizedModel, assignments: tuple[AssignmentUnit, ...]) -> float:
        return _scorer_score(assignments, model, scoring_config).totalScore

    return _oracle


def run_lahc(
    rule_engine: RuleEngineFn,
    model: NormalizedModel,
    candidate_seed: int,
    cr_floor_x: int,
    *,
    scoring_oracle: ScoringOracleFn,
    lahc_params: LahcParams,
    **_kwargs,
) -> _StrategyOutcome:
    """Run one LAHC trajectory per `docs/solver_contract.md` §12A.1.

    Returns `_StrategyOutcome.assignments` set to `bestRoster` (NOT terminal
    `currentRoster`) per §12A.1 step 5.

    On seed-roster failure (`SEEDED_RANDOM_BLIND` returns `unfillable`),
    propagates the failure upstream — `solve()` decides whether to drop
    this trajectory (per §12A.8 — multi-trajectory K-emission semantics)
    or fail the run.

    `**_kwargs` swallows extra kwargs the registry may pass for other
    strategies (e.g., a future strategy's strategy-specific inputs). LAHC
    only consumes the named kwargs above.
    """
    # ---- Step 1: Seed roster -----------------------------------------------
    seed_outcome = run_seeded_random_blind(
        rule_engine, model, candidate_seed, cr_floor_x
    )
    if seed_outcome.unfillable:
        # Per §12A.8 / §14: propagate seed failure to the caller. The K-
        # trajectory outer loop in `solve()` decides whether to drop this
        # trajectory or fail the run.
        return seed_outcome

    current_roster = seed_outcome.assignments
    current_score = scoring_oracle(model, current_roster)

    # ---- Step 2: Initialize state -----------------------------------------
    L = lahc_params.historyListLength
    history = [current_score] * L
    best_roster = current_roster
    best_so_far = current_score
    idle_iters = 0
    current_iter = 0

    # Seeded RNG for move selection; distinct from any RNG used by the seed-
    # roster phase so move-generation streams are reproducible per §12A.4.
    rng = Random(candidate_seed ^ _LAHC_RNG_DISTINGUISHER)

    # Pre-compute the set of fixed-cell coordinates so the move generator
    # never proposes touching them. Fixed assignments are first-class input
    # facts per `docs/domain_model.md` §10.1 and MUST NOT be moved by the
    # solver.
    #
    # `FixedAssignment` carries `(dateKey, slotType, doctorId)` only —
    # `unitIndex` is assigned during `_seat_fixed_assignments` per
    # `python/rostermonster/solver/strategy.py`. To recover the seated
    # `unitIndex` for each fixed pin, we match seed-roster `AssignmentUnit`s
    # against the fixed-pin `(dateKey, slotType, doctorId)` triples per
    # `docs/domain_model.md` §10.1's identity discipline. This is a
    # deterministic identification: SAME_DAY_ALREADY_HELD per
    # `docs/rule_engine_contract.md` §11 prevents the same doctor from being
    # placed twice on the same `(dateKey, slotType)`, so the match is
    # one-to-one.
    fixed_pin_keys = {
        (fa.dateKey, fa.slotType, fa.doctorId) for fa in model.fixedAssignments
    }
    fixed_coords = frozenset(
        (a.dateKey, a.slotType, a.unitIndex)
        for a in current_roster
        if a.doctorId is not None
        and (a.dateKey, a.slotType, a.doctorId) in fixed_pin_keys
    )

    # Aggregate diagnostics: total move-generation tries, accepted moves.
    aggregate_attempts = 0
    aggregate_accepted = 0

    # Pre-compute per-slot eligibility lookup for the reassign move type
    # (mirrors `python/rostermonster/solver/strategy.py`'s `_eligibility_index`).
    # Built once per trajectory.
    eligibility_by_slot = {
        er.slotType: frozenset(er.eligibleGroups) for er in model.eligibility
    }
    group_by_doctor = {d.doctorId: d.groupId for d in model.doctors}
    all_doctor_ids = tuple(d.doctorId for d in model.doctors)

    # ---- Step 3-4: Inner loop ---------------------------------------------
    while idle_iters < lahc_params.idleThreshold and current_iter < lahc_params.maxIters:
        # 3.a: Move generation. Mix of swap + reassign per §12A.1.a — picked
        # uniformly per iteration. If the primary move type returns None
        # (rule-locked for THAT type at this state), fall back to the OTHER
        # type — only terminate the trajectory when BOTH types are rule-locked
        # (since either one being unblocked means progress is still
        # reachable per §12A.1.a's ergodicity invariant).
        primary_is_swap = rng.random() < 0.5
        if primary_is_swap:
            result = _generate_valid_swap(
                rule_engine, model, current_roster, fixed_coords, rng
            )
            if result is None:
                result = _generate_valid_reassign(
                    rule_engine,
                    model,
                    current_roster,
                    fixed_coords,
                    eligibility_by_slot,
                    group_by_doctor,
                    all_doctor_ids,
                    rng,
                )
        else:
            result = _generate_valid_reassign(
                rule_engine,
                model,
                current_roster,
                fixed_coords,
                eligibility_by_slot,
                group_by_doctor,
                all_doctor_ids,
                rng,
            )
            if result is None:
                result = _generate_valid_swap(
                    rule_engine, model, current_roster, fixed_coords, rng
                )
        if result is None:
            # Both move types rule-locked → terminate the trajectory with
            # whatever bestRoster has been found so far.
            break
        proposed_roster, tries_consumed = result
        aggregate_attempts += tries_consumed

        # 3.b: Evaluate.
        proposed_score = scoring_oracle(model, proposed_roster)

        # 3.c: Dual-clause accept criterion per §12A.1.c. Single-clause would
        # reject genuine improvements when the history-list slot still holds
        # a stale high after a recent worsening.
        accept = (proposed_score >= current_score) or (
            proposed_score >= history[current_iter % L]
        )

        # 3.d: State update — currentRoster + currentScore advance together.
        if accept:
            current_roster = proposed_roster
            current_score = proposed_score
            aggregate_accepted += 1

        # 3.e: History list update — overwrite per §12A.1.e. NOT max(...).
        # As the circular queue wraps every L iterations, old scores age
        # out — that aging is what enables late acceptance to escape local
        # optima.
        history[current_iter % L] = current_score

        # 3.f: Best-roster + idle counter (per §12A.1.f). bestSoFar advances
        # only on STRICT improvement so idle_iters stays monotone in
        # no-improvement passes; bestRoster updates atomically with
        # best_so_far.
        if current_score > best_so_far:
            best_so_far = current_score
            best_roster = current_roster
            idle_iters = 0
        else:
            idle_iters += 1

        # 3.g: Increment.
        current_iter += 1

    # ---- Step 5: Emit bestRoster ------------------------------------------
    # NOT terminal current_roster — late-acceptance routinely accepts moves
    # below best_so_far after first reaching it, so terminal can be strictly
    # worse than best_so_far. Under HIGHER_IS_BETTER scoring per
    # docs/scorer_contract.md §10, emitting terminal would discard a better
    # candidate the trajectory already found.
    #
    # Per-trajectory diagnostics surface to SearchDiagnostics per §12A.9.
    # `terminal_score` is current_score at termination (informative only —
    # may differ from best_so_far when late-acceptance left current below
    # best). `iters` is the actual inner-loop iteration count (variable due
    # to idle/maxIters termination + rule-locked early termination).
    strategy_data = {
        "iters": current_iter,
        "accepted_moves": aggregate_accepted,
        "best_score": float(best_so_far),
        "terminal_score": float(current_score),
    }
    return _StrategyOutcome(
        assignments=best_roster,
        unfillable=(),
        attempts=aggregate_attempts,
        rejection_counts={},
        strategy_data=strategy_data,
    )


def _generate_valid_swap(
    rule_engine: RuleEngineFn,
    model: NormalizedModel,
    current_roster: tuple[AssignmentUnit, ...],
    fixed_coords: frozenset[tuple[str, str, int]] | set[tuple[str, str, int]],
    rng: Random,
) -> tuple[tuple[AssignmentUnit, ...], int] | None:
    """Generate a rule-valid pairwise doctor swap between two non-fixed
    cells. Returns `(proposed_roster, tries_consumed)` on success, `None`
    when no valid swap is found in `_MOVE_GENERATION_MAX_TRIES` attempts.

    Validity check: only the two swapped cells need re-validation against
    the rest of the roster (other cells are unchanged). One `evaluate(...)`
    call per swapped cell — the rule engine returns `Decision.valid` when
    the proposed unit doesn't violate any rule against the supplied state.
    """
    movable_indices = [
        i
        for i, a in enumerate(current_roster)
        if a.doctorId is not None
        and (a.dateKey, a.slotType, a.unitIndex) not in fixed_coords
    ]
    if len(movable_indices) < 2:
        # Not enough non-fixed filled cells to swap — strategy can't make
        # any move from here. Caller terminates the trajectory.
        return None

    for tries in range(1, _MOVE_GENERATION_MAX_TRIES + 1):
        i, j = rng.sample(movable_indices, 2)
        cell_i = current_roster[i]
        cell_j = current_roster[j]
        if cell_i.doctorId == cell_j.doctorId:
            # Swap is a no-op; skip and burn a try.
            continue

        new_i = AssignmentUnit(
            dateKey=cell_i.dateKey,
            slotType=cell_i.slotType,
            unitIndex=cell_i.unitIndex,
            doctorId=cell_j.doctorId,
        )
        new_j = AssignmentUnit(
            dateKey=cell_j.dateKey,
            slotType=cell_j.slotType,
            unitIndex=cell_j.unitIndex,
            doctorId=cell_i.doctorId,
        )

        # Validate both swapped cells against the rest of the roster. One
        # evaluate call per cell; we stage new_i first into the state, then
        # check new_j against the updated state.
        others = tuple(
            a for k, a in enumerate(current_roster) if k != i and k != j
        )
        state_no_swap = RuleState(assignments=others)
        decision_i = rule_engine(model, state_no_swap, new_i)
        if not decision_i.valid:
            continue
        state_with_new_i = RuleState(assignments=others + (new_i,))
        decision_j = rule_engine(model, state_with_new_i, new_j)
        if not decision_j.valid:
            continue

        # Both new cells valid — build the proposed roster.
        proposed = list(current_roster)
        proposed[i] = new_i
        proposed[j] = new_j
        return tuple(proposed), tries

    # Exhausted tries without finding a valid swap.
    return None


def _generate_valid_reassign(
    rule_engine: RuleEngineFn,
    model: NormalizedModel,
    current_roster: tuple[AssignmentUnit, ...],
    fixed_coords: frozenset[tuple[str, str, int]] | set[tuple[str, str, int]],
    eligibility_by_slot: dict[str, frozenset[str]],
    group_by_doctor: dict[str, str],
    all_doctor_ids: tuple[str, ...],
    rng: Random,
) -> tuple[tuple[AssignmentUnit, ...], int] | None:
    """Generate a rule-valid single-cell reassignment per §12A.1.a. Picks
    a non-fixed cell at random and replaces its current doctor with a
    different eligible doctor. Returns `(proposed_roster, tries_consumed)`
    on success, `None` after exhausting `_MOVE_GENERATION_MAX_TRIES`.

    Reassignment can introduce a doctor not present on the seed roster —
    this is the move type that gives LAHC ergodicity over the rule-engine-
    valid roster space (swap alone cannot, since swap-only is a closure
    over the seed-roster doctor set).

    Validity check: only the reassigned cell needs evaluation against the
    rest of the roster (other cells unchanged). One `evaluate(...)` call
    per attempt. The new doctor MUST be ≠ the current cell's doctor;
    same-day-already-held + eligibility violations are caught by the rule
    engine.
    """
    movable_indices = [
        i
        for i, a in enumerate(current_roster)
        if a.doctorId is not None
        and (a.dateKey, a.slotType, a.unitIndex) not in fixed_coords
    ]
    if not movable_indices:
        return None

    for tries in range(1, _MOVE_GENERATION_MAX_TRIES + 1):
        i = rng.choice(movable_indices)
        cell = current_roster[i]
        eligible_groups = eligibility_by_slot.get(cell.slotType, frozenset())
        # Candidate doctors: eligible-group AND not the current cell's doctor.
        # Pre-filtering via eligibility avoids wasting most attempts on
        # rule-engine BASELINE_ELIGIBILITY_FAIL rejections.
        candidate_doctors = [
            d
            for d in all_doctor_ids
            if d != cell.doctorId
            and group_by_doctor.get(d) in eligible_groups
        ]
        if not candidate_doctors:
            continue
        new_doctor = rng.choice(candidate_doctors)
        new_unit = AssignmentUnit(
            dateKey=cell.dateKey,
            slotType=cell.slotType,
            unitIndex=cell.unitIndex,
            doctorId=new_doctor,
        )
        # Validate against the rest of the roster (excluding the cell being
        # replaced). The rule engine catches SAME_DAY_ALREADY_HELD,
        # BACK_TO_BACK_CALL, hard-blocks, etc.
        others = tuple(a for k, a in enumerate(current_roster) if k != i)
        state = RuleState(assignments=others)
        decision = rule_engine(model, state, new_unit)
        if not decision.valid:
            continue

        proposed = list(current_roster)
        proposed[i] = new_unit
        return tuple(proposed), tries

    return None
