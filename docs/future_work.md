# Future Work

## Purpose
Parking lot for hypothetical future directions and open ideas that are not yet committed work.

This document is intentionally **non-normative**:
- It is not a roadmap. Committed milestone-level delivery order lives in `docs/roadmap.md`.
- It is not a decision. Accepted directional decisions live in `docs/decision_log.md`.
- It is not an active execution tracker. Active milestone/checkpoint/task truth lives in `docs/delivery_plan.md`.
- It is not a contract. Normative technical boundaries live in the contract docs under `docs/`.

Entries here are ideas we want to remember, not commitments to build. If an entry is promoted to committed work, migrate it into the appropriate authoritative doc (roadmap / delivery plan / decision log / contract) and delete the entry from here. If an entry is deliberately rejected, record a short rationale in `docs/decision_log.md` and delete the entry from here.

## Entry format
Each entry should be short and concrete:
- **Title**
- **Date noted**
- **Context** — what we noticed, on which surface
- **Idea / direction** — what we might do later
- **Why deferred now** — usually: out of active checkpoint scope or not yet justified
- **Trigger to revisit** (optional) — what would make this worth picking up
- **Related surfaces** — files / docs the idea would touch

Keep entries implementation-facing. Do not restate contract meaning here. Do not turn this into a vague-ideas dumping ground.

## Maintenance
- Add entries as ideas surface during planning or implementation.
- Keep entries terse; detail belongs in the authoritative doc once the idea is committed.
- When an idea is promoted, move it and delete the parking-lot entry.
- When an idea is rejected, record a short rationale in `docs/decision_log.md` and delete the parking-lot entry.
- This doc must not grow into a parallel roadmap. If it starts dictating sequencing, promote the relevant entries and trim.

## Current entries

### FW-0001 — Launcher title should be department-driven, not hardcoded to ICU/HD
- **Date noted:** 2026-04-21
- **Context:** `apps_script/m1_sheet_generator/src/LauncherForm.html` renders a static `<h1>` reading "CGH ICU/HD Roster Launcher". This is harmless today because the Department dropdown has a single ICU/HD option and ICU/HD is the only supported template (blueprint §16, D-0005, D-0011). The title is effectively baked into the page rather than derived from the selected department.
- **Idea / direction:** When the launcher gains more than one department template, derive the title from the currently selected department / template rather than hardcoding it. Possible shapes: a generic "Roster Launcher" heading plus a department-driven subtitle, or a fully template-driven title string sourced from the template artifact. The title should follow the dropdown selection rather than lag behind it.
- **Why deferred now:** M1.1 scope is ICU/HD-only pilot; there is no second department template yet, so the single-value dropdown and fixed title are consistent with actual supported behavior.
- **Trigger to revisit:** First additional department template lands, or the Department dropdown gains a second option.
- **Related surfaces:** `apps_script/m1_sheet_generator/src/LauncherForm.html` (title literal and dropdown), `apps_script/m1_sheet_generator/src/Launcher.gs` (any server-side template listing surfaced to the form), `docs/sheet_generation_contract.md` §12 (launcher surface).

### FW-0002 — Launcher doctor-count groups should be template-driven, not hardcoded ICU/HD groups
- **Date noted:** 2026-04-21
- **Context:** `apps_script/m1_sheet_generator/src/LauncherForm.html` hardcodes three doctor-count inputs — `ICU only`, `ICU + HD`, `HD only` — mirroring the ICU/HD template's declared doctor groups (`ICU_ONLY`, `ICU_HD`, `HD_ONLY`). The number of inputs, their labels, and their identifiers are all ICU/HD-specific. The submission payload shape (`icuOnly`, `icuHd`, `hdOnly`) is equally ICU/HD-specific. Other departments will declare different doctor-group structures (for example, an Emergency Department template would not have ICU/HD groupings at all).
- **Idea / direction:** Drive the doctor-count fieldset from the selected department template's declared doctor groups rather than from hardcoded form fields. Render one numeric input per declared group, with labels sourced from the template. Corresponding consequence: the launcher payload and `normalizeAndValidateConfig_` consumption shape become template-driven rather than fixed on ICU/HD keys. The blueprint already treats slot/group structure and group-based eligibility as template-declared (blueprint §6, §16), so the direction is consistent with the architecture; only the launcher UI and payload have not yet been generalized.
- **Why deferred now:** ICU/HD is the sole first-release template. A template-driven form surface is not needed until a second department with a different group structure exists, and generalizing prematurely would add surface without operator benefit during the pilot.
- **Trigger to revisit:** First additional department template lands, or ICU/HD's group declarations change, or the launcher payload contract is revisited in `docs/sheet_generation_contract.md` §12.
- **Related surfaces:** `apps_script/m1_sheet_generator/src/LauncherForm.html` (doctor-count fieldset and payload shape), `apps_script/m1_sheet_generator/src/Launcher.gs` (`submitLauncherForm` payload mapping), `apps_script/m1_sheet_generator/src/GenerateSheet.gs` (`normalizeAndValidateConfig_` group handling), `docs/template_contract.md` (doctor-group declaration), `docs/sheet_generation_contract.md` §3A and §12.4.

### FW-0003 — Incremental rule engine implementation as an optimization
- **Date noted:** 2026-04-23
- **Context:** `docs/rule_engine_contract.md` §13 permits internal caching/indexing as long as the public contract remains stateless, and §14 defines the equivalence-test discipline required for any non-stateless implementation to ship. First release ships only the stateless reference implementation and is not required to carry an equivalence-test corpus.
- **Idea / direction:** When profiling shows the stateless reference to be the search-rate bottleneck during solver runs, implement an incremental-state rule engine that maintains indexed occupancy, call-adjacency structures, and eligibility bitsets across solver `tryAdd`/`undo` operations. Ship it only behind a contract-owned corpus of `(normalizedModel, ruleState, proposedUnit) → expected Decision` fixtures that cover at least each hard invariant in §11 and the `FixedAssignment` scoped admission cases in §15, per §14. Byte-identical decisions including canonical violation ordering are non-negotiable.
- **Why deferred now:** First-release correctness target is "works and is auditable," not "works at solver's peak search rate." The stateless reference is the easier implementation to review and is the contractual baseline. Incremental state makes sense only once the solver is exercising it hard enough for validity checks to become the dominant cost.
- **Trigger to revisit:** Profiling on realistic ICU/HD-sized inputs shows rule-engine time dominating a full `SEEDED_RANDOM_BLIND` run, or a later score-aware strategy's search rate requires faster validity adjudication than the stateless reference can supply.
- **Related surfaces:** `docs/rule_engine_contract.md` §13 and §14, future rule-engine test-corpus files (not yet created), solver Phase 2 rule-engine call sites.

### FW-0004 — Score-aware solver strategies
- **Date noted:** 2026-04-23
- **Context:** `docs/solver_contract.md` §11.2 defines an additive extension clause (`scoringConsultation: "READ_ONLY_ORACLE"`) that future strategies MAY opt into for read-only access to a scoring oracle. First release ships exactly `SEEDED_RANDOM_BLIND` (§11.1), which is scoring-blind end-to-end.
- **Idea / direction:** Add one or more score-aware strategies behind the existing `StrategyDescriptor` interface — candidate directions include hill-climb, simulated annealing, beam search, constraint propagation, and CP-SAT (as a native ILP/CP encoding of the problem). Each new strategy declares its own `additionalInputs` (neighborhood size, temperature schedule, beam width, propagator set, etc.) and, when it consults scoring, sets `scoringConsultation: "READ_ONLY_ORACLE"` per §11.2. The scorer stays the single owner of component logic and direction.
- **Why deferred now:** First release needs a correctness baseline before it can judge whether score-aware search actually improves ICU/HD outputs vs. `SEEDED_RANDOM_BLIND` + scoring + selector. Landing a score-aware strategy prematurely would make it hard to isolate whether quality gains came from the solver change, the scorer weight choices, or the selector retention decisions.
- **Trigger to revisit:** The minimal local compute pipeline (M2) has landed and benchmark runs show `SEEDED_RANDOM_BLIND` is consistently leaving meaningful score headroom on realistic inputs, or a specific quality regression against v1 cannot be closed by scorer-weight tuning alone.
- **Related surfaces:** `docs/solver_contract.md` §11.2, §20; `docs/scorer_contract.md` §6 (scorer boundary); future strategy-descriptor registrations.

### FW-0005 — Parallel solver strategy
- **Date noted:** 2026-04-23
- **Context:** `docs/solver_contract.md` §20 explicitly defers parallel execution transport, worker coordination, and cross-worker merge semantics. First release is single-worker and single-process.
- **Idea / direction:** Add a parallel strategy — for example, independent-workers-with-seeded-merge, where N workers each run a seeded variant of the base strategy under distinct seeds and a merge step produces the final `CandidateSet`. Preserve byte-identical determinism under fixed `(seed, workerCount)` inputs. The parallel strategy is an additive `StrategyDescriptor` registration per §11.2 and does not change the solver's single-invocation return shape.
- **Why deferred now:** Single-worker throughput has not been measured against realistic ICU/HD inputs yet. Parallelism only matters if single-worker search time becomes operationally constraining, and it introduces transport/coordination complexity that cuts against M2's minimal-pipeline framing.
- **Trigger to revisit:** Single-worker runs exceed acceptable operator-facing latency on realistic inputs, or benchmark campaigns require running many seeds in parallel for comparative study.
- **Related surfaces:** `docs/solver_contract.md` §11, §20; future worker/orchestration milestones (M4 in `docs/delivery_plan.md` §5).

### FW-0006 — Activate the `scoringConsultation: "READ_ONLY_ORACLE"` extension clause
- **Date noted:** 2026-04-23
- **Context:** `docs/solver_contract.md` §11.2 declares the extension clause but `docs/solver_contract.md` §12 ships `SEEDED_RANDOM_BLIND` with `scoringConsultation: false`. First release has no registered strategy that consults scoring.
- **Idea / direction:** When the first score-aware strategy (FW-0004) lands, activate the clause by registering its descriptor with `scoringConsultation: "READ_ONLY_ORACLE"` and wiring a read-only scoring-oracle handle through the solver boundary. The handle MUST NOT let the strategy mutate scoring logic, override direction, or take over scorer-component ownership (`docs/scorer_contract.md`). The clause activation does not require a `contractVersion` bump if it conforms to §11.2; it does require updating the contract's current-status section to reflect the change.
- **Why deferred now:** There is nothing to activate until a score-aware strategy exists (FW-0004). Activating the clause without a consumer would widen the contract surface for no gain.
- **Trigger to revisit:** The first score-aware strategy lands.
- **Related surfaces:** `docs/solver_contract.md` §11.2, §21; `docs/scorer_contract.md` §6.

### FW-0007 — Operator-tuneable scoring-curve parameters
- **Date noted:** 2026-04-23
- **Context:** `docs/scorer_contract.md` §15 makes component weights operator-tuneable at run scope (v1 parity). `docs/scorer_contract.md` §19 explicitly defers operator-tuneable curve parameters (for example, `crReward`'s diminishing-marginal-utility curve shape beyond weights) — first release MAY ship a fixed curve with limited tuneable parameters.
- **Idea / direction:** Expose curve parameters (for example, `crReward` curve shape selector and its coefficients) as sheet-extracted inputs flowing into `scoringConfig.curves` per `docs/scorer_contract.md` §11. Preserve the strict-monotonic-decrease property in §12 regardless of operator-supplied values; reject out-of-contract curve shapes at parser boundary rather than silently clamping.
- **Why deferred now:** Operators need a baseline `crReward` curve they can tune against before the project knows which curve-parameter knobs actually matter. First-release tuneable surface is already broader than v1 (weights plus `crFloor`); adding curve parameters on day one risks surfacing knobs nobody is ready to use.
- **Trigger to revisit:** Weight tuning alone fails to produce acceptable `CR`-distribution behavior on realistic inputs, or a specific operator-facing scenario demonstrably needs a non-default curve shape.
- **Related surfaces:** `docs/scorer_contract.md` §11, §12, §15, §19; sheet parser extraction boundary.

### FW-0008 — Per-unit-position fairness scoring component
- **Date noted:** 2026-04-23
- **Context:** `docs/scorer_contract.md` §19 and `docs/domain_model.md` §7.7 note that `SlotDemand.requiredCount` MAY be greater than 1, but ICU/HD first-release demand instantiation treats every `(dateKey, slotType)` as a single unit. First-release fairness scoring (`pointBalanceWithinSection`, `pointBalanceGlobal`, `standbyCountFairnessPenalty`) does not distinguish between unit positions on a multi-unit day.
- **Idea / direction:** When a future department lands with `requiredCount > 1`, add a `unitPositionFairnessPenalty` component that differentiates position-within-day load when it is meaningful (for example, first-on-call vs. second-on-call). Register it via the scorer's component enumeration with appropriate direction-guard preservation (`docs/scorer_contract.md` §13).
- **Why deferred now:** No first-release department declares `requiredCount > 1`. Adding a fairness component that always contributes zero would pollute the component breakdown for no operator signal.
- **Trigger to revisit:** First additional department template lands with `requiredCount > 1` for any slot type, or ICU/HD changes to require multi-unit days.
- **Related surfaces:** `docs/scorer_contract.md` §10 (component shape), §19; `docs/domain_model.md` §7.7, §11.2.

### FW-0009 — `workloadWeight` on `SlotTypeDefinition`
- **Date noted:** 2026-04-23
- **Context:** `docs/domain_model.md` §7.6 lists `workloadWeight` (or equivalent burden weight) as optional and deferred unless introduced by a future contract checkpoint. First-release `SlotTypeDefinition` does not carry burden weight, and fairness scoring therefore treats all call slots as equal-weight.
- **Idea / direction:** Introduce `workloadWeight` on `SlotTypeDefinition` once a department's slot set includes meaningfully unequal-burden slot types (for example, a 24-hour weekend call vs. a weekday short call). Fairness scoring components consume this weight under the existing direction-guard invariant. The addition is a `domain_model` contract change and will travel with a coordinated `scorer_contract` patch.
- **Why deferred now:** ICU/HD's current slot set does not justify burden weighting; fairness scoring works acceptably at unit weight.
- **Trigger to revisit:** A department template declares slot types that are not equivalently burdensome, or operators report v1 fairness behavior that depended on implicit burden weighting we have not surfaced in v2 yet.
- **Related surfaces:** `docs/domain_model.md` §7.6, §11.2; `docs/scorer_contract.md` §4, §10.

### FW-0010 — Streaming/delta scoring implementation
- **Date noted:** 2026-04-23
- **Context:** `docs/scorer_contract.md` §16 permits a streaming/delta scoring implementation as an optimization, provided it produces byte-identical `ScoreResult` values to the pure-function evaluation within a single implementation on a single platform, and does not leak lifecycle state into the public contract. Byte-identical is the single normative parity criterion; cross-implementation or cross-platform parity is FW-0011 territory.
- **Idea / direction:** When solver search volume + scoring cost become the pipeline bottleneck, ship a streaming scorer that computes component deltas on `tryAdd`/`undo` rather than scoring complete allocations from scratch. Back it with a parity test against the pure-function reference over a representative candidate corpus, analogous to the rule-engine equivalence discipline but scoped to scorer identical-output guarantees.
- **Why deferred now:** First release ships the pure-function reference only, which is the easier implementation to review and the contractual baseline. Streaming is only worth the review cost when profiling shows scoring as a dominant cost.
- **Trigger to revisit:** Profiling on realistic ICU/HD-sized runs shows scorer time dominating, or a score-aware solver strategy (FW-0004) needs higher-frequency scoring than the pure-function implementation supports.
- **Related surfaces:** `docs/scorer_contract.md` §16, §17; scorer test corpus (not yet created).

### FW-0011 — Cross-implementation determinism
- **Date noted:** 2026-04-23
- **Context:** `docs/solver_contract.md` §16 and `docs/scorer_contract.md` §17 and `docs/rule_engine_contract.md` §17 each scope determinism to a single implementation on a single platform. Cross-implementation determinism is explicitly not guaranteed today because RNG choices, floating-point ordering, and container iteration order differ across runtimes.
- **Idea / direction:** If the project ever ports the core pipeline to a different language/runtime (for example, a Go or Rust reimplementation for worker performance, or a secondary JVM implementation for integration), plan the port with cross-implementation determinism as a first-class requirement: specify RNG primitives, float aggregation order, and container iteration order at the contract level so both implementations produce byte-identical outputs under identical inputs, with the equivalence-test corpora doing the enforcement.
- **Why deferred now:** There is no second implementation to converge against, and first-release Python is the only target (D-0018).
- **Trigger to revisit:** A second-runtime port of any stage in the pipeline is seriously proposed.
- **Related surfaces:** `docs/rule_engine_contract.md` §17; `docs/scorer_contract.md` §17; `docs/solver_contract.md` §16; `docs/decision_log.md` D-0018.

### FW-0012 — Rule-engine rejection-reason distribution diagnostics
- **Date noted:** 2026-04-23
- **Context:** `docs/rule_engine_contract.md` §12 requires the rule engine to return every applicable violation in canonical order, so each probe already carries full reason-cardinality information at the rule-engine boundary. The solver's `SearchDiagnostics` payload does not yet aggregate these rejection reasons into distributions across probes within a run or across runs.
- **Idea / direction:** Extend the solver diagnostics payload to aggregate per-rule rejection counts and violation-combination histograms (for example, "20% of probes failed `BASELINE_ELIGIBILITY_FAIL` as the first canonical reason; 40% co-failed `SAME_DAY_HARD_BLOCK` and `BACK_TO_BACK_CALL`") so operators and benchmark campaigns can see which rules most constrain the search. This is an implementation-side diagnostics surface on top of already-complete per-probe data; it is not a contract change to the rule engine.
- **Why deferred now:** First-release diagnostic needs are satisfied by the raw per-probe violation-reason emission; aggregation and visualization come later once benchmark-campaign surfaces exist.
- **Trigger to revisit:** Operator-facing rejection diagnostics or benchmark-campaign comparison workflows need rule-level distribution summaries.
- **Related surfaces:** `docs/rule_engine_contract.md` §12; future solver `SearchDiagnostics` payload; future operator-facing diagnostic surfaces.

### FW-0013 — Richer retention modes and artifact export formats
- **Date noted:** 2026-04-23
- **Context:** `docs/solver_contract.md` §14 moves retention to the selector stage, which is not itself contract-closed yet. `docs/domain_model.md` §12.5 lists retention options (best-only, top-K, full, and full-chunk with diagnostics). The settled first-release intent is that the selector ships **best-only as the default retention mode** with **`FULL` retention available as a per-run operator opt-in for ad-hoc auditability** (so an operator can request, for example, all 5,000 generated rosters scored and traceable for one cycle, then revert to best-only once the pipeline is stable). `TOP_K`, `FULL_WITH_DIAGNOSTICS`, and per-batch artifact export formats remain deferred to benchmark-campaign work.
- **Idea / direction:** Two phases of work behind the same future-work entry, gated on selector-contract closure:
  1. **First-release-intended (gated on selector contract):** define the selector's retention surface so `BEST_ONLY` is the default and `FULL` is an operator-opt-in mode per run. Each retained `TrialCandidate` MUST carry a stable run-local `candidateId`, full `ScoreResult` (total + components), enough information to reconstruct the `AllocationResult`, and batch/chunk/run identifiers for trace-back, so operators can build an auditable scored-candidate table.
  2. **Benchmark-campaign-deferred:** extend the selector with `TOP_K` and `FULL_WITH_DIAGNOSTICS` modes for benchmark campaigns (M5 in `docs/delivery_plan.md` §5), plus artifact export formats that serialize retained `TrialCandidate[]` and per-batch `TrialBatchResult` payloads for offline comparison of strategies and weight configurations.
- **Why deferred now:** The selector contract is not yet drafted, so the retention surface — including the operator-opt-in `FULL` knob — has no contract home yet. Best-only retention is sufficient for M2's minimal local compute pipeline goal in the absence of audit demand; the operator-opt-in `FULL` knob lands when the selector contract is authored, and `TOP_K`/`FULL_WITH_DIAGNOSTICS` land alongside benchmark-campaign work.
- **Trigger to revisit:** Selector contract closure lands (Phase 1), or M5 benchmark campaign work begins (Phase 2).
- **Related surfaces:** `docs/domain_model.md` §12.5; future `docs/selector_contract.md` (not yet created); `docs/solver_contract.md` §14; `docs/decision_log.md` D-0027 sub-decision 2.

### FW-0014 — V1 score-weight reference pass during ICU/HD implementation slice
- **Date noted:** 2026-04-23
- **Context:** `docs/scorer_contract.md` §19 defers concrete weight values for ICU/HD first release and notes that the implementation slice should reference v1. First-release scorer ships with component identifiers and direction locked but without shipped weight defaults.
- **Idea / direction:** During the scorer implementation slice, make a one-time v1 reference pass: extract v1's effective ICU/HD scoring weights (after undoing v1's lower-is-better direction flip), translate them into v2's `HIGHER_IS_BETTER` direction, and ship them as the template's default weights. Document the translation so operator-supplied overrides can be compared against a known baseline.
- **Why deferred now:** The scorer implementation has not started. Locking default weights before implementation risks repeating v1's tuning quirks without the context to judge them.
- **Trigger to revisit:** Scorer implementation slice begins (M2 or a follow-on checkpoint under the scorer contract).
- **Related surfaces:** `docs/scorer_contract.md` §11, §15, §19; v1 ICU/HD scoring reference (outside this repo).

### FW-0015 — Benchmark campaign mode interaction with solver contract
- **Date noted:** 2026-04-23
- **Context:** `docs/blueprint.md` §11 lists benchmark campaign mode as an intended execution mode, and M5 in `docs/delivery_plan.md` §5 scopes "Observability and benchmark hardening." `docs/solver_contract.md` defines single-invocation semantics only; it does not govern how multiple solver invocations are coordinated for comparative study.
- **Idea / direction:** When benchmark campaign mode lands, define how the solver contract interacts with campaign-level orchestration: how seeds sweep across runs, whether `SearchDiagnostics` payloads aggregate at campaign level, whether campaign mode can drive alternative strategy selection, and how operator-tuneable surfaces (§17 and `docs/scorer_contract.md` §15) are varied across campaign runs without contract drift. This is probably a campaign-level contract doc, not a change to the solver contract itself.
- **Why deferred now:** Benchmark campaign infrastructure is not in M2 scope. Defining solver-campaign interaction without an actual campaign runner makes the interaction speculative.
- **Trigger to revisit:** Benchmark campaign work begins under M5, or an earlier need emerges for multi-seed comparative runs under the solver contract.
- **Related surfaces:** `docs/solver_contract.md` §15, §17, §18; `docs/blueprint.md` §11; `docs/delivery_plan.md` §5 M5.

### FW-0016 — Retention stage re-emergence under scoring-aware solvers
- **Date noted:** 2026-04-23
- **Context:** `docs/solver_contract.md` §14 explicitly moves retention downstream to the selector, because in v1 retention was entangled with search in ways that made benchmark comparisons hard to interpret. That downstream placement is specifically justified for the scoring-blind first release: retention requires scores, and the solver has none.
- **Idea / direction:** Once a score-aware solver strategy lands (FW-0004), revisit whether some retention decisions meaningfully re-emerge mid-search (for example, a hill-climb strategy that keeps a top-K of best-so-far neighbors during search). If so, specify the retention-in-solver surface as an additive strategy-descriptor field rather than a contract-wide override, preserving §14's rule that scoring-blind strategies do not populate best-candidate fields and do not implement retention modes.
- **Why deferred now:** First-release solver is scoring-blind by contract (§11.1), so mid-search retention has no score to rank against. The contract's current retention boundary is deliberate, not provisional.
- **Trigger to revisit:** First score-aware strategy is being designed and its behavior benefits from in-search retention decisions.
- **Related surfaces:** `docs/solver_contract.md` §11.2, §14, §20; future `docs/selector_contract.md` (not yet created).

### FW-0017 — Canonical lowest-`unitIndex`-first fill-order rule for `requiredCount > 1`
- **Date noted:** 2026-04-23
- **Context:** ICU/HD first release uses `requiredCount = 1` for every `(dateKey, slotType)`, so `unitIndex` is always 0 and the question of "which `unitIndex` to fill first within a multi-unit `(dateKey, slotType)`" never arises in practice. `docs/decision_log.md` D-0029 settles that all units of the same `SlotType` are equivalent for validity and baseline workload weight, but it does not yet specify the solver's canonical fill order for multiple unfilled `unitIndex` values within one `(dateKey, slotType)`.
- **Idea / direction:** When the first department template lands with `requiredCount > 1` for any slot type, extend `docs/solver_contract.md` §12.2 (Phase 2 tie-breaking) with an explicit rule that within a single `(dateKey, slotType)`, the solver MUST fill the lowest unfilled `unitIndex` first. This preserves seeded-determinism guarantees in the multi-unit case (different `unitIndex` orderings under the same `seed` would otherwise produce different but equally-valid candidates, which would silently break `docs/solver_contract.md` §16 byte-identical determinism). The rule is mechanical and independent of `fillOrderPolicy` choice — it applies after the policy has selected the `(dateKey, slotType)` to fill next. Pair the contract change with an equivalence-test fixture covering multi-unit demand to lock the behavior in test.
- **Why deferred now:** No first-release department exercises the multi-unit case, so adding the rule today is normative wording for a code path that cannot execute. Landing it alongside the first multi-unit department keeps the contract change scoped to a setting where it can be validated end-to-end.
- **Trigger to revisit:** First additional department template lands with `requiredCount > 1` for any slot type, or ICU/HD changes to require multi-unit days.
- **Related surfaces:** `docs/solver_contract.md` §12.2, §16; `docs/domain_model.md` §7.7, §10.2; `docs/decision_log.md` D-0029.
