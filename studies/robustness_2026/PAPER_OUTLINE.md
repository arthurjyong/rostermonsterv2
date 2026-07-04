# Paper Outline (MISTA 2027 full paper)

_Status: DRAFT v0.1, 2026-07-04. Generated from the planning workflow (session 1b31c7ab, run wf_4b95a1c6-c59); edit freely, this is not yet frozen. The freeze commit (target: late July 2026, tag `robustness-freeze-2026-08`) is the pre-registration event._

## Title options

- How Robust is Late Acceptance Hill-Climbing in Production? A Pre-Registered Parameter-Robustness Study of a Deployed Physician Rostering System
- Tune in May, Trust in December: Temporal Out-of-Sample Validation of LAHC Parameters in a Live ICU Rostering Deployment
- Pre-Registered Parameter Robustness for Late Acceptance Hill-Climbing: Evidence from Eight Months of a Deployed Physician Rostering System
- Beyond the Case Study: A Confirmatory, Pre-Specified Evaluation of LAHC Parameter Plateaus in Production Physician Rostering
- One Parameter, Two Hospitals, Eight Months: A Statistical Robustness Study of LAHC in a Deployed Call-Rostering System

(Note: option 5's 'Two Hospitals' is wrong, it is two units in one hospital; kept only as a rhythm template.)

## Draft abstract (~200 words, [X] = confirmatory placeholders)

Late Acceptance Hill-Climbing (LAHC) is prized for having a single control parameter, yet evidence of its parameter robustness in deployed systems is scarce, and metaheuristic parameter studies are almost universally tuned and evaluated on the same instances. We present a parameter-robustness study of LAHC inside a physician call-rostering system in live use at two hospital units since May 2026, designed as a temporal pre-registration. Two development months (May-June 2026: an 8-value, 30-seed L sweep; idle-cutoff and move-mix sweeps) were used solely to fix a production configuration (L=50, idle cutoff 3500, swap probability 0.5), a statistically validated 5-seed tuning protocol (TOST equivalence at a +/-2-point margin, 100% cliff-detection power, 93% pick stability), and falsifiable hypotheses, all frozen before [X] confirmatory monthly instances (August-December 2026) were collected under an unchanged protocol. Out-of-sample, the L plateau held on [X] of [X] instances, the frozen tuple stayed within [X] points of the per-instance re-tuned optimum, and [X] of [X] pre-specified hypotheses were confirmed. Two control experiments disentangle the large-L cliff from an idle-cutoff confound and test for L-idle interaction. We report operational telemetry ([X] production runs, best-of-22 trajectories on cloud batch infrastructure, byte-identical determinism) and discuss external validity for practitioners deploying LAHC.

## Sections

### 1. Introduction (~1.5 pp)

Opens with the methodological gap: parameter studies in metaheuristics tune and evaluate on the same instances, so 'robust' usually means 'robust in-sample'; deployed systems offer a natural fix that is almost never exploited, namely a temporal split where future months are genuinely unseen. States the three contributions: (1) a pre-registration-style design where two development months fix the production tuple, the N=5 tuning protocol, and all hypotheses before any confirmatory data exists; (2) the first (to our knowledge) statistical characterization of LAHC's L/idle/move-mix response surfaces on a live clinical rostering workload, including a validated minimum-seed tuning protocol; (3) confirmatory out-of-sample results on ~[X] instances from a deployed system plus honest operational telemetry. Explicitly frames the pre-registration as the answer to the 'nice case study, but does it generalize?' objection.

**Data source:** WRITING

**Figures:** Fig 1 (study timeline / pre-registration diagram)

### 2. Background and Related Work (~1 pp)

Three short threads: (a) LAHC canon and variants (Burke & Bykov 2017 EJOR 258(1):70-78 for the L-vs-runtime trade-off; Bazargani & Lobo 2017 GECCO parameter-less LAHC, which we considered and rejected for determinism/audit reasons; Namazi & Sanderson 2018 Diversified LAHC as a different failure mode); (b) parameter tuning and algorithm configuration (irace, SMAC, and why an operator-facing 5-seed protocol is a different design point than offline configurators); (c) pre-registration and confirmatory analysis norms imported from empirical ML/medicine, noting their near-absence in metaheuristics evaluation, plus physician/nurse rostering deployment reports for context.

**Data source:** WRITING

### 3. The Deployed System (~1.5 pp)

Describes the production stack the study is embedded in: Google Sheets operator front end, snapshot extraction to a canonical JSON, a deterministic Python pipeline with a 9-component weighted scorer, and a best-of-K LAHC solve (K=22 in production) fanned out on Google Cloud Batch (c3-highcpu VM, one trajectory per vCPU, ~110-145s wall). Foregrounds the byte-identical determinism contract (solver_contract section 12A.4: same snapshot + seed + params yields byte-identical output), because determinism is what makes archived production runs re-scorable and the whole retrospective/confirmatory design auditable. Notes the operator-weight mechanism (weights live in the snapshot; the scorer is a pure function), which sets up the fixed-reference-config re-scoring in section 8. Ends with the production tuple L=50 / idleThreshold=3500 / swapProbability=0.5 hardcoded at the May 2026 M7 lock (decision D-0070).

**Data source:** WRITING

**Figures:** Fig 2 (architecture diagram); Table 1 (instance characteristics)

### 4. Study Design: Temporal Development/Confirmatory Split (~1.5 pp)

The methodological core. Development set = May 2026 (22 doctors x 29 days x 638 requests, 13 usable production runs) and June 2026 (18 doctors x 27 days x 486 requests, 11 runs), collected ad hoc during live tuning and used ONLY to fix (i) the production tuple, (ii) the N=5-seed tuning protocol, and (iii) the hypothesis set with numeric decision thresholds (e.g., H1: plateau membership of L in {10,50,100} via TOST at delta=+/-2 on each confirmatory instance; H2: frozen-tuple regret vs per-instance re-tuned optimum < [X] points; H3: cliff reproduction at L>=500; H4: swapProbability 0.5 equivalent to 0.25/0.75). Confirmatory set = monthly instances from August 2026 onward (~5 cycles, up to 2 units, up to ~10 instances), collected under a frozen pre-specified protocol with instrumentation added before the freeze (per-run wall-time fields and lahcParams echo in result.json, adopted-candidate logging). States the freeze artifact: a dated, hash-pinned protocol document in the repo. Discloses the deviation-handling rule (any protocol change after freeze is reported as such).

**Data source:** WRITING

**Figures:** Fig 1 (timeline, shared with intro); Table 3 (pre-specified hypotheses + frozen thresholds)

### 5. Development-Set Characterization (~2.5 pp)

The exploratory evidence, reported with real numbers and explicitly labeled non-confirmatory. 5.1 L response surface: 8 log-spaced L values x 30 seeds on the May fixture; plateau L in {1,10,50,100} with means 90.22/90.42/91.04/91.39 (sd 0.74-1.25) and a cliff at L>=500 (means 75.9/35.5/6.4/2.8 at 500/1000/5000/10000), Wilcoxon signed-rank p<<0.001 on adjacent cliff pairs (artifacts: l_sweep.py, l_sweep_data.json). 5.2 idleThreshold elbow at ~3500 and move-mix plateau (swapProbability ~0.25-0.75 statistically equivalent, extremes 0.0/1.0 no lead and worse variance; idle_threshold_sweep.py, move_mix_sweep.py). 5.3 The N=5 tuning protocol: TOST equivalence of plateau pairs at delta=+/-2, bootstrap power 100% at N>=5 for cliff detection (min N for both 80% and 95% power = 5), pick-stability 100% on-plateau and 93.2% best-decade at N=5 (seed_count_analysis.py/.json). 5.4 Budget context: best-of-K saturation (K=10 captures 95.7% of best-of-135; best_of_k_analysis.py) and the matched-wall-time SRB baseline (SRB K=100 ~162s vs LAHC K=10 ~158s, t(4)=-0.28 p=0.78 on time; score delta +53.85 for LAHC, t(4)=11.10, p<<0.001, 5/5 paired wins; paired_comparison.py, comparable_budget.py).

**Data source:** EXISTS (experimental/m6_lahc_comparison + m6_c4_dryrun; PDFs and JSON data files already generated)

**Figures:** Fig 3 (L sweep); Fig 4 (idle elbow); Fig 5 (move-mix); Fig 6 (N=5 protocol triptych); Fig 7 (best-of-K saturation); Table 2 (SRB vs LAHC paired comparison)

### 6. Control Experiments (~1 pp)

Two pre-planned controls run on the archived development fixtures before the confirmatory window, closing the two known internal-validity holes. Control A (idle-disabled large-L): the L>=500 cliff was measured under idleThreshold=5000, and smaller L makes the idle counter fire sooner, so the cliff could be an idle-cutoff/budget confound rather than intrinsic LAHC degradation; re-run the L sweep with the idle cutoff disabled (maxIters as the sole cap, budget raised) and overlay against Fig 3 to separate 'large L is worse' from 'large L was starved'. Control B (joint tuple mini-sweep): L=50 and idleThreshold=3500 were tuned on different fixtures and the pair has never been jointly swept; run a 3x3 grid (L in {10,50,100} x idle in {2000,3500,5000}) at N=5 seeds per cell (using the exact protocol section 4 froze, which doubles as a protocol dress rehearsal) on both dev fixtures, testing for interaction and confirming the production tuple sits on a 2-D plateau, not a ridge.

**Data source:** COMPUTE (new runs on archived May/June fixtures, scripts derivable from l_sweep.py / idle_threshold_sweep.py)

**Figures:** Fig 8 (Control A overlay); Fig 9 (Control B L x idle heatmap, both fixtures)

### 7. Confirmatory Results (~2 pp) [TEMPLATE]

Written now as a template with [X] placeholders and the pre-specified analysis fixed. 7.1 Instances: [X] monthly instances from [X] units, Aug-Dec 2026, characteristics appended to Table 1. 7.2 Plateau verification: per-instance mini L sweep at the frozen N=5 protocol; H1 (plateau membership) confirmed on [X]/[X] instances; H3 (cliff at L>=500) reproduced on [X]/[X]. 7.3 Frozen-tuple regret: production tuple within [X] points (mean [X], max [X]) of each instance's re-tuned optimum; H2 [confirmed/refuted]. 7.4 Move-mix spot-check: H4 [X]. 7.5 Pre-specified aggregate tests across instances (e.g., sign test on plateau-vs-cliff ordering, [X] of [X]) plus a clearly labeled exploratory subsection for anything surprising. Every hypothesis outcome lands in Table 4 next to its frozen threshold, including failures; the paper commits to publishing this section whichever way the numbers fall.

**Data source:** PROSPECTIVE (Aug-Dec 2026 confirmatory months under the frozen protocol)

**Figures:** Fig 10 (per-month plateau verification panel); Fig 11 (frozen-tuple regret vs re-tuned optimum); Table 4 (hypothesis outcomes vs frozen thresholds)

### 8. Operational Telemetry and External Validity (~1 pp)

What eight months of voluntary production use actually looked like, reported against the instrumentation gaps rather than around them: 28 archived runs (24 usable) across 2 units in the development window, all K=22; June runs span 4 operator weight configurations because weights were being retuned live, so pooled cross-run score comparisons are computed by re-scoring archived snapshots under a single fixed reference config (possible because snapshots carry full config and the scorer is a pure deterministic function); confirmatory-window telemetry adds wall-time and lahcParams echo, adopted-candidate identity, and re-solve counts (instrumented pre-freeze). Discusses external validity honestly: 2 units in one hospital, voluntary operator use, month-shapes of 18-22 doctors x 27-29 days, and what plausibly transfers (the tuning protocol and plateau-shape methodology) versus what does not (the specific tuple values).

**Data source:** COMPUTE (re-scoring of gcs_archive runs under fixed reference config) + PROSPECTIVE (confirmatory-window telemetry)

**Figures:** Table 5 (telemetry: runs/month, units, K, wall time, weight-config epochs, adoption)

### 9. Limitations (~0.5 pp)

Single deployment site and a narrow instance family (two month-shapes in development, [X] in confirmation); development runs were collected while weights were retuned, mitigated but not eliminated by fixed-config re-scoring; no per-iteration wall-time telemetry in development-era result.json and Cloud Logging timing markers expired at ~30 days, so development-era time claims rest on the offline sweep measurements, not production logs; the only infeasibility sample is a 1-doctor toy, so nothing is claimed about UNSATISFIED behavior; the confirmatory sample size (~[X] instances) bounds the strength of aggregate tests, which is exactly why per-instance equivalence tests were pre-specified; adoption/override behavior before the freeze was not recorded.

**Data source:** WRITING

### 10. Conclusion (~0.5 pp)

Restates the finding shape: on a deployed clinical rostering system, LAHC's parameter plateau [held / partially held / did not hold] out-of-sample under a design where the tuple, protocol, and hypotheses were frozen months before the test data existed. Argues the temporal pre-registration pattern is cheap for anyone running a metaheuristic in production (the confirmatory data collects itself) and proposes it as a reporting norm for deployed-system papers. Closes with the JoS-special-issue extension path: multi-site replication and promotion of the tuned defaults into the normative solver contract (the FW-0037 promotion trigger of 2+ confirming cycles maps exactly onto this study).

**Data source:** WRITING

## Master figure and table list

- Fig 1: Study timeline and pre-registration diagram: development months (May-Jun 2026, exploratory, tuple/protocol/hypotheses fixed) -> freeze artifact (dated, hash-pinned) -> confirmatory months (Aug-Dec 2026, frozen protocol). [NEW, drawn]
- Fig 2: System architecture: Sheets front end -> snapshot JSON -> deterministic pipeline + 9-component scorer -> Cloud Batch best-of-K=22 LAHC fan-out -> analyzer -> writeback; determinism contract annotated. [NEW, drawn]
- Table 1: Instance characteristics: May 2026 (22 doctors, 29 days, 638 requests, 13 usable runs), June 2026 (18, 27, 486, 11 runs), plus [X] confirmatory rows appended. [EXISTS for dev rows; PROSPECTIVE rows added]
- Fig 3: L sweep, mean +/- sd score vs log L, 30 seeds x 8 values: plateau 90.2-91.4 at L in {1,10,50,100}, cliff at L>=500 with Wilcoxon annotations. [EXISTS: l_sweep.pdf / l_sweep_data.json, redraw for print]
- Fig 4: Score vs idleThreshold elbow curve, elbow at ~3500. [EXISTS: idle_threshold_sweep.pdf, redraw]
- Fig 5: Move-mix sweep, score vs swapProbability in {0.0, 0.25, 0.5, 0.75, 1.0}, plateau at intermediate values. [EXISTS: move_mix_sweep.pdf, redraw]
- Fig 6: N=5 tuning-protocol validation triptych: TOST equivalence grid at delta margins, bootstrap cliff-detection power vs N (100% at N>=5), pick-stability vs N (93.2% best-decade at N=5). [EXISTS: seed_count_analysis.pdf/.json, redraw]
- Fig 7: Best-of-K saturation curve, K=10 reaches 95.7% of best-of-135. [EXISTS: best_of_k_analysis.pdf, redraw]
- Table 2: Matched-wall-time SRB vs LAHC paired comparison: ~162s vs ~158s (p=0.78 on time), score delta +53.85, t(4)=11.10, 5/5 LAHC wins. [EXISTS: paired_comparison.py / comparable_budget.py outputs]
- Table 3: Pre-specified hypotheses H1-H4 with frozen numeric decision thresholds. [NEW, written at freeze]
- Fig 8: Control A: L sweep with idle cutoff disabled, overlaid on Fig 3, separating intrinsic large-L degradation from idle-cutoff starvation. [COMPUTE]
- Fig 9: Control B: joint L x idleThreshold 3x3 heatmap at N=5 seeds/cell on both dev fixtures, production tuple marked. [COMPUTE]
- Fig 10: Confirmatory panel: per-month plateau verification, one mini L sweep per instance, [X] instances. [PROSPECTIVE]
- Fig 11: Confirmatory frozen-tuple regret: production tuple score vs per-instance re-tuned optimum, per instance. [PROSPECTIVE]
- Table 4: Hypothesis outcomes vs frozen thresholds (H1-H4 plus aggregate tests), including any failures. [PROSPECTIVE]
- Table 5: Operational telemetry: runs per month, units, K, wall time, weight-config epochs (4 in June), adopted candidate, re-solves; dev-window rows via fixed-config re-scoring of the GCS archive. [COMPUTE + PROSPECTIVE]

## Conference-talk spine

A 20-minute MISTA talk lifts a 6-slide spine directly from the outline, with Fig 1 as the visual anchor recurring on slides 2, 4, and 5. Slide 1, 'A rostering system you can audit': the deployed stack in one picture (Fig 2), live at two ICU/HD units since May 2026, byte-identical determinism as the punchline that makes everything after it possible. Slide 2, 'The case-study problem': metaheuristic parameter studies tune and test on the same instances; our fix is temporal pre-registration (Fig 1), state the freeze date and the hash-pinned protocol. Slide 3, 'What development told us': one visual strip of Fig 3 + Fig 4 + Fig 6 panel c, the plateau/cliff story and the 5-seed protocol in 90 seconds, real numbers on the slide (90.2-91.4 plateau, cliff p<<0.001, N=5 gives 100% power / 93% stability). Slide 4, 'What we froze': Table 3 verbatim, hypotheses and thresholds, emphasize these were committed before any confirmatory instance existed. Slide 5, 'Did it hold?': Fig 10 + Table 4, the confirmatory panel, including any failed hypothesis shown in red, credibility comes from showing misses. Slide 6, 'What you can take home': the two controls in one breath (cliff is/is not an idle artifact; tuple sits on a 2-D plateau), then the practitioner recipe: 5 seeds, TOST at your own delta, freeze, wait a month. Optional slide 7 for Q&A backup: Table 5 telemetry and the weight-retuning re-scoring trick.

_Harmonization note: Section 4 and Table 3 refer to hypotheses H1-H4 as sketched by the outline draft; the canonical hypothesis set is H1-H7 in PROTOCOL_DRAFT.md and supersedes the outline numbering._
