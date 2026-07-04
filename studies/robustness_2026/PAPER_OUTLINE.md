# Paper Outline (journal target: ORHC / Healthcare Analytics / HCMS)

_Status: v1.1, 2026-07-04. Aligned with PROTOCOL_DRAFT.md v0.2/v0.3 (retrospective high-resolution tuning study on real + perturbed instances, plus the algorithm-comparison arm); the earlier temporal pre-registration framing (archive_PROTOCOL_v01_preregistration.md) is dropped throughout. Research questions RQ1-RQ5 and the 14 design revisions live in LITERATURE_SURVEY.md §C-D and are authoritative for the experiments._

## Title options

- Tuning Late Acceptance Hill-Climbing for Physician Rostering: A Statistical Response-Surface Study on Deployed-System Instances
- How Sensitive is LAHC, Really? Equivalence-Tested Parameter Response Surfaces from a Live ICU Rostering System
- Choosing and Tuning a Search Algorithm for Real-World ICU Call Rostering: Evidence from a Deployed System

## Draft abstract (~200 words, [X] = placeholders)

Late Acceptance Hill-Climbing (LAHC) is prized for having a single control parameter, yet the entire published guidance on choosing its history length L rests on coarse sweeps and visual scatter plots, with no confidence intervals or equivalence tests, and the founders' own question about the interaction between L and idle-cutoff termination (PATAT 2008) has never been statistically addressed. We characterize the joint response surface of LAHC solution quality and time-to-convergence over L, idle cutoff, and move mix on [X] instances derived from a physician call-rostering system in live hospital use: real production months plus deterministic perturbations spanning realistic demand variation (request subsampling, staffing reduction). Design follows algorithm-configuration best practice: instance-blocked paired seeds, train/test instance splits with parent-side discipline, budgets in move evaluations, and pre-specified TOST equivalence margins derived from operationally meaningful roster-score units. We locate the industrial default (Timefold, L=400) on the measured curve, test the canonical linear time-in-L law, and report the first designed move-mix experiment in the LAHC literature. [Optional arm: under identically designed tuning budgets, LAHC is compared with simulated annealing, step-counting hill climbing, tabu search, and restart hill-climbing (LAHC at L=1), with a scoring-blind constructive baseline and CP-SAT bounds as reference points.] Results: [X]. We release anonymized instances and all analysis code.

## Sections

### 1. Introduction (~1.5 pp)
The gap (LITERATURE_SURVEY §B gap 1): no statistically characterized L-response curve exists; guidance is 3-9 coarse values; idle/L interaction open since 2008; no published move-mix experiment. Contributions: (1) first CI-and-equivalence-backed LAHC response surface, on production-derived instances; (2) test of the linear time-in-L law and the industrial default's placement; (3) first designed move-mix experiment; (4) [if arm runs] first-in-domain fairly-tuned algorithm comparison on production rostering instances. **Source: WRITING** (survey done).

### 2. Background and related work (~1.5 pp)
LAHC canon and variants (pin our exact variant in pseudocode: three non-equivalent versions circulate; DLAS/CLAHC shift optimal L by orders of magnitude); algorithm-configuration norms (irace/ParamILS/SMAC, fair-budget doctrine, overtuning); rostering field practice (one-config-one-seed comparisons; INRC hierarchy; deployed-system genre). **Source: WRITING** (from LITERATURE_SURVEY evidence base).

### 3. The deployed system (~1.5 pp)
Sheets front end → snapshot JSON → deterministic Python pipeline with 9-component weighted scorer → best-of-K LAHC on Cloud Batch; byte-identical determinism contract (makes archived runs re-scorable and every experiment auditable). Production fanout: **designed K=88 on a single c3-highcpu-88 (Pool(88), cloud_compute_contract §8.7); during the pilot to date every live run executed at K=22 on c3-highcpu-22 under the documented CPUS_ALL_REGIONS quota workaround (all archived runs kApproved=22)**; the paper reports both layers explicitly. Production tuple L=50 / idleThreshold=3500 / swapProbability=0.5 (D-0070). **Source: WRITING + EXISTS (contracts, archive).**

### 4. Instances and study design (~2 pp)
Real months (May 2026: 22 doctors × 29 days × 638 requests; June 2026: 18 × 27 × 486; later months join as they accrue) plus deterministic perturbed variants (request subsampling 60/80/100%, doctor-pool reduction, reshuffles), ~10-15 instances. Design discipline per survey §D: instance+seed blocking; train/test split fixed before any experiment with all children of one parent on one side; budgets denominated in move evaluations; proportional and CCP-style idle cutoffs with cutoff ≥ L; fixed reference scoring config for all endpoints; TOST margin pre-specified in roster-score units with operational justification; month as blocking factor. **Source: COMPUTE (instance generator) + WRITING.**

### 5. LAHC response surface results (~2.5 pp)
5.1 Fine L sweep (~14 log-spaced levels × 100 seeds) with CIs and equivalence bands; cliff location; linear time-in-L law test with per-instance angle coefficients; Timefold L=400 located on the curve. 5.2 Idle-cutoff axis (absolute vs proportional vs CCP) and L×idle interaction (the 2008 open question). 5.3 Move-mix sweep and L×mix interaction (first designed experiment). 5.4 Stagnation diagnostics (DLAS fraction) explaining failures mechanistically. Dev-era single-fixture results (30-seed sweeps, FW-0036/0037) cited as pilot evidence only. **Source: COMPUTE (the core new experiments).**

### 6. Restarts: best-of-K analysis (~1 pp)
Expected-best-of-K curves via order statistics on pooled runs (unbiased estimator), budget-dependent crossover of best-of-K vs one long run, tail-shape diagnostics, SCHC T/Lc coefficient as pre-registered predictor. Framed as application of published machinery to a new problem class, not new methodology. **Source: COMPUTE (analysis over sweep pools).**

### 7. Algorithm comparison arm [optional, staged] (~1.5 pp)
LAHC vs SA vs SCHC vs tabu vs restart-HC (LAHC at L=1) under the Franzin & Stützle protocol, with SRB (SEEDED_RANDOM_BLIND, the scoring-blind constructive baseline per solver_contract §12) reported separately as the constructive reference, not as a search algorithm: shared code skeleton, identical neighborhoods and termination, equal pre-specified DOE tuning budgets, ARPD vs CP-SAT bound, Friedman + Shaffer-static post hocs, multiple time budgets (30 s / 10 min / production). SA temperature by the 85% convention or tuned; note LAHC's rescaling invariance vs SA's scale sensitivity to our fixed 9-component score. Scoped as first-in-domain. **Source: COMPUTE (new solvers behind the same interface + CP-SAT model).**

### 8. Deployment context and external validity (~1 pp)
Telemetry as descriptive external validity, not headline: months live, runs per month (28 archived runs May 10-Jun 29, two units), voluntary operator use, live weight retuning (4 configs in June; absorbed by fixed-reference re-scoring), K=22-in-practice vs K=88-design, time-to-roster. Field-standard instance descriptors; per-component violation counts; independent post-hoc fairness statistics (std dev / range / Jain index of per-doctor burden). Held-out accrued months reported as free out-of-sample validation if available by submission. **Source: COMPUTE (archive walk + re-scoring) + PROSPECTIVE (bonus only).**

### 9. Limitations (~0.5 pp)
One ward, one scoring formulation, one LAHC variant (results variant-specific by design); perturbed instances are correlated descendants of few real parents (month-as-block, parent-side splits, claims scoped accordingly); no wall-time telemetry from dev-era production runs; UNSATISFIED behavior uncharacterized. **Source: WRITING.**

### 10. Conclusion (~0.5 pp)
The practitioner recipe (measure the angle coefficient, pick L in the equivalence band, set proportional cutoff, restart per the crossover rule); what transfers (the method) vs what does not (the specific tuple); released anonymized instances answering the field's most-cited gap. **Source: WRITING.**

## Master figure and table list

- Table 1: instance family characteristics (real + perturbed; field-standard descriptors). [COMPUTE]
- Fig 1: system architecture with determinism contract annotated; K=88 design / K=22 pilot-practice noted. [DRAW]
- Fig 2: fine L response curves with CIs + equivalence bands, all instances overlaid; Timefold L=400 and production L=50 marked. [COMPUTE]
- Fig 3: time-in-L linearity and per-instance angle coefficients. [COMPUTE]
- Fig 4: L × idle-cutoff interaction heatmap (absolute vs proportional cutoffs). [COMPUTE]
- Fig 5: move-mix response and L×mix interaction. [COMPUTE]
- Fig 6: stagnation-fraction diagnostics. [COMPUTE]
- Fig 7: expected-best-of-K curves with budget-dependent crossover. [COMPUTE]
- Table 2: tuning-protocol validation (minimum seeds, pick stability), updated from dev-era N=5 analysis. [COMPUTE]
- [Arm] Fig 8 + Table 3: algorithm comparison ARPD vs CP-SAT bound across budgets, adjusted p-values. [COMPUTE]
- Table 4: deployment telemetry (runs/month, units, K design vs practice, weight-config epochs, time-to-roster). [COMPUTE]

## Conference-talk spine (if ever needed; journal-first)

Five slides: the deployed system in one picture; the gap (all published L guidance is coarse and unstatistical); the response surface (Fig 2 + Fig 4); the practitioner recipe; the comparison arm or held-out validation as closer.
