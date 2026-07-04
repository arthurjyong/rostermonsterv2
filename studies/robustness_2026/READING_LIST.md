# Literature Reading List

_Status: DRAFT v0.1, 2026-07-04. Generated from the planning workflow (session 1b31c7ab, run wf_4b95a1c6-c59); edit freely, this is not yet frozen. The freeze commit (target: late July 2026, tag `robustness-freeze-2026-08`) is the pre-registration event._

## Read these five first, in order

1. Burke & Bykov, The late acceptance Hill-Climbing heuristic, EJOR 258(1):70-78, 2017 — the algorithm and the exact single-fixture sensitivity claims our production study statistically stress-tests; every framing decision hangs off this paper.
2. Eggensperger, Lindauer & Hutter, Pitfalls and Best Practices in Algorithm Configuration, JAIR 64:861-893, 2019 — the over-tuning/train-test pitfalls catalogue; the frozen confirmatory protocol must be written against this checklist BEFORE August 2026 data collection starts.
3. Campelo & Takahashi, Sample size estimation for power and accuracy in the experimental comparison of algorithms, Journal of Heuristics 25(2):305-338, 2019 — pre-specify power for the ~5-10 confirmatory instances now, or the small-n confirmatory design is indefensible later.
4. López-Ibáñez et al., The irace package, Operations Research Perspectives 3:43-58, 2016 — the standard tuner reviewers will demand we position our N=5-seed manual protocol against; read its instance-set and generalization handling.
5. Lakens, Equivalence Tests: A Practical Primer, Soc. Psych. and Personality Science 8(4):355-362, 2017 — the TOST anchor; equivalence testing is essentially absent from metaheuristics literature, so our delta=+/-2 plateau claims need this external methodological authority.

## Novelty threats and citation obligations (gaps to watch)

- No paper found that does exactly what we claim (statistical, equivalence-tested parameter-robustness study on production instances of a deployed metaheuristic system, evaluated on held-out instances) — searched hard across AAC, overtuning, rostering, and deployed-systems literature. But the claim MUST be phrased narrowly: 'tuned-parameter generalization across instances' per se is studied (Styles & Hoos LION 2012 configuration transfer/scaling; Eggensperger et al. JAIR 2019 treat train/test generalization as a known pitfall; Birattari 2009 formalizes tuning as generalization). Our novelty = production-derived instances of a live deployed system + a pre-fixed train/test instance partition with parent-side discipline (per PROTOCOL_DRAFT.md v0.2+) + equivalence-testing framing, not 'nobody studied generalization'.
- Burke & Bykov EJOR 2017 itself contains history-length sensitivity experiments (on benchmarks) and explicitly claims L is easy to set; Bazargani & Lobo GECCO 2017 built parameter-less LAHC because tuning L was considered a burden. A 'LAHC is robust' headline will draw 'already known/expected' — position as first statistical confirmation on production data, plus the L>=500 cliff and never-swept joint L x idleThreshold interaction as new content.
- Knust & Xie, Annals of OR 272:187-216, 2019 (SA on nurse rostering benchmark AND real-world instances) is the closest domain-adjacent precedent for metaheuristic evaluation on real rostering instances; failing to cite it would look ignorant. Same for the Ceschia/Di Gaspero/Schaerf line (INRC-II SA, AOR 288:95-113, 2020; multi-neighborhood SA healthcare papers through 2025) whose irace-tune-then-validate workflow is the field default we extend.
- Schneider, Bischl & Feurer, Overtuning in Hyperparameter Optimization (AutoML Conf 2025, PMLR 293) shows the ML/AutoML community is actively colonizing the tuning-generalization question; an OR-side empirical analogue could appear before the Jan-Feb 2027 MISTA deadline — monitor arXiv (cs.NE, cs.AI, math.OC) for 'overtuning'/'configuration generalization' + scheduling.
- Timefold/OptaPlanner ships Late Acceptance as a flagship algorithm in real industrial deployments (docs recommend it for rostering); no academic robustness study of it in production found, only grey literature (docs, benchmark blog posts). This supports our gap claim but check their materials before submission — a practitioner benchmark write-up could be waved at us, and citing the docs preempts that.
- Theory on generalization of learned algorithm parameters exists (Gupta & Roughgarden SICOMP 2017; Balcan et al. data-driven algorithm design line, e.g. 'Refined bounds for algorithm configuration', ICML 2020) — cite briefly or AAC-literate reviewers will flag the omission; it strengthens us (theory exists, empirical production studies don't).
- TOST/equivalence testing in algorithm comparison: essentially nothing exists in the metaheuristics literature (confirmed by search) — this is an opportunity but also a risk: statisticians may attack margin choice (delta=+/-2) as post hoc since it was set on the dev set; pre-register the margin justification in the frozen protocol and cite Lakens 2017 (and optionally the intersection-union permutation approach, arXiv:1802.01877) for margin-setting discipline.
- Two verification chores before citing: (a) HealthRota evaluation (Future Healthcare Journal 2022) author list needs confirming from PMC9345226; (b) the permutation equivalence test (arXiv:1802.01877) final published venue needs confirming. Both are optional citations; drop them if verification fails.

## LAHC core, behavior, and variants

_Defines the algorithm under study, establishes the original (single-fixture, benchmark-based) claims about history-length sensitivity that our production statistical study confirms/refines, and covers the variant literature (parameter-less, diversified, step-counting) that a robustness finding must be positioned against._

- **[must-read-fully]** Burke, E.K., Bykov, Y. The late acceptance Hill-Climbing heuristic. European Journal of Operational Research 258(1):70-78, 2017. DOI 10.1016/j.ejor.2016.07.012
  - Canonical LAHC paper; claims history length L is the sole, 'easy to specify' parameter with runtime-to-convergence roughly proportional to L; our plateau (L 1-100) + cliff (L>=500) result directly stress-tests these claims on production data
  - Slots into: Related Work (LAHC) + Introduction (claims under test)
- **[background]** Burke, E.K., Bykov, Y. A late acceptance strategy in hill-climbing for exam timetabling problems. PATAT 2008 conference proceedings, Montreal, 2008
  - Original LAHC introduction; cite for historical lineage alongside the 2017 EJOR version
  - Slots into: Related Work (LAHC)
- **[cite-and-skim]** Fonseca, G.H.G., Santos, H.G., Carrano, E.G. Late acceptance hill-climbing for high school timetabling. Journal of Scheduling 19(4):453-465, 2016. DOI 10.1007/s10951-015-0458-5
  - Strong LAHC application result in timetabling (note: high school timetabling, NOT nurse rostering); evidence LAHC is competitive in scheduling domains
  - Slots into: Related Work (LAHC applications)
- **[cite-and-skim]** Bolaji, A.L., Bamigbola, A.F., Shola, P.B. Late acceptance hill climbing algorithm for solving patient admission scheduling problem. Knowledge-Based Systems 145:197-206, 2018. DOI 10.1016/j.knosys.2018.01.017
  - LAHC applied to a healthcare scheduling problem; closest published LAHC-in-healthcare precedent
  - Slots into: Related Work (LAHC applications)
- **[must-read-fully]** Bazargani, M., Lobo, F.G. Parameter-less late acceptance hill-climbing. GECCO 2017, pp. 219-226. DOI 10.1145/3071178.3071225
  - Argues L needs automating and proposes a parameter-less LAHC; our robustness result speaks directly to whether that machinery is needed in practice, and their behavioral analysis of L is the closest existing sensitivity study
  - Slots into: Related Work (LAHC parameter sensitivity) + Discussion
- **[cite-and-skim]** Namazi, M., Sanderson, C., Newton, M.A.H., Polash, M.M.A., Sattar, A. Diversified Late Acceptance Search. Australasian Joint Conference on Artificial Intelligence (AI 2018), LNCS; arXiv:1806.09328
  - DLAS variant with explicit experiments on the influence of history length; shows LAHC can degenerate to plain HC (stagnation), relevant to interpreting our cliff/plateau
  - Slots into: Related Work (LAHC variants)
- **[cite-and-skim]** Bykov, Y., Petrovic, S. A Step Counting Hill Climbing Algorithm applied to University Examination Timetabling. Journal of Scheduling 19(4):479-492, 2016. DOI 10.1007/s10951-016-0469-x
  - Sibling single-parameter acceptance heuristic (SCHC) from the same lineage; frames LAHC within a family of one-knob local searches
  - Slots into: Related Work (LAHC variants)
- **[cite-and-skim]** Franzin, A., Stützle, T. Revisiting simulated annealing: A component-based analysis. Computers & Operations Research 104:191-206, 2019. DOI 10.1016/j.cor.2018.12.015
  - Methodological template for decomposing an acceptance-criterion metaheuristic into components and analyzing parameter/component effects with automated configuration; nearest methodological sibling to our L x idleThreshold x swapP decomposition
  - Slots into: Related Work (LAHC/methodology bridge) + Methods

## Metaheuristic parameter tuning, algorithm configuration, and tuning-vs-test generalization

_Our novelty claim lives here: standard AAC tools (irace, ParamILS, SMAC, SPO) define what 'tuning' normally means, and the overtuning/generalization literature defines the gap we fill (nobody has run a statistical parameter-robustness study on held-out production-derived instances of a deployed system). Must cite precisely to phrase the claim defensibly._

- **[must-read-fully]** López-Ibáñez, M., Dubois-Lacoste, J., Pérez Cáceres, L., Birattari, M., Stützle, T. The irace package: Iterated racing for automatic algorithm configuration. Operations Research Perspectives 3:43-58, 2016. DOI 10.1016/j.orp.2016.09.002
  - De-facto standard tuner; reviewers will ask why we didn't just irace the tuple; read its train/test-instance handling to position our frozen N=5-seed protocol against it
  - Slots into: Related Work (tuning) + Methods (protocol justification)
- **[cite-and-skim]** Hutter, F., Hoos, H.H., Leyton-Brown, K., Stützle, T. ParamILS: An Automatic Algorithm Configuration Framework. Journal of Artificial Intelligence Research 36:267-306, 2009. DOI 10.1613/jair.2861
  - Foundational AAC framework; explicitly discusses training/test instance splits for configuration evaluation
  - Slots into: Related Work (tuning)
- **[cite-and-skim]** Birattari, M., Stützle, T., Paquete, L., Varrentrapp, K. A racing algorithm for configuring metaheuristics. GECCO 2002, pp. 11-18, Morgan Kaufmann
  - F-Race origin; racing = statistically discarding configurations, the intellectual ancestor of our Wilcoxon/TOST-based pick-stability protocol
  - Slots into: Related Work (tuning)
- **[cite-and-skim]** Birattari, M. Tuning Metaheuristics: A Machine Learning Perspective. Studies in Computational Intelligence 197, Springer, 2009 (1st ed. 2005). DOI 10.1007/978-3-642-00483-4
  - Canonical formalization of tuning as a generalization problem over an instance distribution (tune on sample, evaluate expected performance on unseen instances); the theoretical frame for our train/test instance partition
  - Slots into: Related Work (tuning) + Methods (design rationale)
- **[cite-and-skim]** Hutter, F., Hoos, H.H., Leyton-Brown, K. Sequential Model-Based Optimization for General Algorithm Configuration. LION 5, LNCS 6683, pp. 507-523, Springer, 2011. DOI 10.1007/978-3-642-25566-3_40
  - SMAC; completes the standard-tooling triad (irace/ParamILS/SMAC) reviewers expect acknowledged
  - Slots into: Related Work (tuning)
- **[background]** Bartz-Beielstein, T., Lasarczyk, C., Preuss, M. et al., Sequential Parameter Optimization line; see Bartz-Beielstein, T., Preuss, M. Experimental Analysis of Optimization Algorithms: Tuning and Beyond. In: Theory and Principled Methods for the Design of Metaheuristics, pp. 205-245, Springer, 2014. DOI 10.1007/978-3-642-33206-7_10
  - SPO/DACE tradition: model-based parameter analysis with statistical DOE; supports treating parameter sweeps as designed experiments rather than tuner runs
  - Slots into: Related Work (tuning) + Methods
- **[must-read-fully]** Eggensperger, K., Lindauer, M., Hutter, F. Pitfalls and Best Practices in Algorithm Configuration. Journal of Artificial Intelligence Research 64:861-893, 2019. DOI 10.1613/jair.1.11420
  - Catalogues over-tuning to training instances and prescribes disjoint test sets and clean experimental discipline; our frozen pre-specified confirmatory protocol should be written to visibly satisfy this checklist
  - Slots into: Methods (confirmatory protocol) + Related Work (tuning)
- **[cite-and-skim]** Schneider, L., Bischl, B., Feurer, M. Overtuning in Hyperparameter Optimization. Fourth International Conference on Automated Machine Learning (AutoML 2025), PMLR 293; arXiv:2506.19540
  - Quantifies how often tuned configurations fail to generalize (ML analogue, ~10% severe cases); motivates asking the same question for a deployed OR system
  - Slots into: Introduction (motivation) + Related Work (tuning)
- **[cite-and-skim]** Styles, J., Hoos, H.H. (with Müller, M.) Automatically Configuring Algorithms for Scaling Performance. LION 6 / Springer LNCS, 2012. DOI 10.1007/978-3-642-34413-8_15
  - Studies transfer of tuned configurations across instance distributions (small-to-large scaling); the closest existing 'do tuned parameters generalize across instances' empirical work, must cite when phrasing novelty
  - Slots into: Related Work (tuning generalization)
- **[background]** Gupta, R., Roughgarden, T. A PAC Approach to Application-Specific Algorithm Selection. SIAM Journal on Computing 46(3):992-1017, 2017. DOI 10.1137/15M1050276
  - Theory: sample complexity of learning algorithm parameters from instance samples; lets us say the generalization question has theory but essentially no empirical production-data studies
  - Slots into: Related Work (tuning generalization)
- **[background]** Rasulo, A., Smith-Miles, K., Muñoz, M.A., Handl, J., López-Ibáñez, M. Extending Instance Space Analysis to Algorithm Configuration Spaces. GECCO 2024 Companion. DOI 10.1145/3638530.3654264
  - Joint instance-space x configuration-space robustness visualization (Smith-Miles ISA lineage); background for 'robustness across instances' framing and month-shape heterogeneity discussion
  - Slots into: Related Work (tuning generalization) + Discussion

## Statistical comparison of stochastic algorithms (nonparametrics, equivalence/TOST, sample size, best-of-K)

_Supplies the methods-section authority for every statistical instrument we use: Wilcoxon/Friedman guidance, TOST equivalence (rare in this field, needs an anchor citation), pre-specified sample-size/power for the small confirmatory set (~5-10 instances), and expected-max-over-budget analysis for best-of-K=22._

- **[cite-and-skim]** Demšar, J. Statistical Comparisons of Classifiers over Multiple Data Sets. Journal of Machine Learning Research 7:1-30, 2006
  - Canonical justification for Wilcoxon signed-rank (2 algorithms) and Friedman + post-hoc (many) over multiple instances; the multi-instance confirmatory analysis follows this template
  - Slots into: Methods (statistical design)
- **[cite-and-skim]** Derrac, J., García, S., Molina, D., Herrera, F. A practical tutorial on the use of nonparametric statistical tests as a methodology for comparing evolutionary and swarm intelligence algorithms. Swarm and Evolutionary Computation 1(1):3-18, 2011. DOI 10.1016/j.swevo.2011.02.002
  - The standard metaheuristics-community citation for nonparametric test methodology (García/Herrera school)
  - Slots into: Methods (statistical design)
- **[must-read-fully]** Campelo, F., Takahashi, F. Sample size estimation for power and accuracy in the experimental comparison of algorithms. Journal of Heuristics 25(2):305-338, 2019. DOI 10.1007/s10732-018-9396-7
  - Principled a-priori sample-size/power calculation for algorithm experiments; use to pre-specify how many confirmatory months/runs/seeds are needed and defend the small-n design
  - Slots into: Methods (confirmatory design, power analysis)
- **[cite-and-skim]** Campelo, F., Wanner, E.F. Sample size calculations for the experimental comparison of multiple algorithms on multiple problem instances. Journal of Heuristics 26:851-883, 2020. DOI 10.1007/s10732-020-09454-w
  - Extends the above to multiple algorithms x multiple instances with Holm correction (CAISEr package); matches our tuple-comparison-across-months layout
  - Slots into: Methods (confirmatory design)
- **[must-read-fully]** Lakens, D. Equivalence Tests: A Practical Primer for t Tests, Correlations, and Meta-Analyses. Social Psychological and Personality Science 8(4):355-362, 2017. DOI 10.1177/1948550617697177
  - Standard accessible TOST reference (delta bounds, power for equivalence); anchors our TOST delta=+/-2 plateau-equivalence claims since no established TOST precedent exists in metaheuristics
  - Slots into: Methods (equivalence testing)
- **[background]** Pesarin, F., Salmaso, L., Carrozzo, E., Arboretti, R. Testing for equivalence: an intersection-union permutation solution. arXiv:1802.01877 (published version in Statistical Methods in Medical Research / related venue)
  - Permutation-based equivalence testing; optional nonparametric fallback if reviewers object to parametric TOST on score distributions (verify final published venue before citing)
  - Slots into: Methods (equivalence testing, robustness check)
- **[must-read-fully]** Dodge, J., Gururangan, S., Card, D., Schwartz, R., Smith, N.A. Show Your Work: Improved Reporting of Experimental Results. EMNLP-IJCNLP 2019, pp. 2185-2194. DOI 10.18653/v1/D19-1224
  - Expected best-found performance as a function of budget k (with estimator + code); the principled published method for our best-of-K saturation curve (k=10 gives 95.7% of best-of-135)
  - Slots into: Methods (best-of-K analysis)
- **[background]** Hoos, H.H., Stützle, T. Stochastic Local Search: Foundations and Applications. Morgan Kaufmann/Elsevier, 2004
  - Run-time/solution-quality distribution (RTD/SQD) methodology for randomized local search; classical foundation for analyzing restart/best-of-K behavior of LAHC trajectories
  - Slots into: Methods (best-of-K analysis) + Background

## Physician and nurse rostering, including deployed systems

_Establishes the problem domain, shows where a deployed ICU/HD physician call-rostering system sits in the literature, and provides the deployed-system comparators that make 'production' credible; also shows most deployed-system papers report implementation stories, not statistical parameter-robustness studies (our gap)._

- **[cite-and-skim]** Burke, E.K., De Causmaecker, P., Vanden Berghe, G., Van Landeghem, H. The State of the Art of Nurse Rostering. Journal of Scheduling 7(6):441-499, 2004. DOI 10.1023/B:JOSH.0000046076.75950.0b
  - Canonical rostering survey; standard scene-setting citation for hospital staff rostering
  - Slots into: Background / Related Work (rostering)
- **[cite-and-skim]** Van den Bergh, J., Beliën, J., De Bruecker, P., Demeulemeester, E., De Boeck, L. Personnel scheduling: A literature review. European Journal of Operational Research 226(3):367-385, 2013. DOI 10.1016/j.ejor.2012.11.029
  - 300+ paper personnel-scheduling review; use for the broader taxonomy and the observation that real-world application papers are a minority
  - Slots into: Background / Related Work (rostering)
- **[must-read-fully]** Erhard, M., Schoenfelder, J., Fügener, A., Brunner, J.O. State of the art in physician scheduling. European Journal of Operational Research 265(1):1-18, 2018. DOI 10.1016/j.ejor.2017.06.037
  - The physician-scheduling review (68 papers to 2016); use its classification to precisely place our ICU/HD call-rostering problem and note the scarcity of deployed systems
  - Slots into: Background / Related Work (physician rostering)
- **[cite-and-skim]** Böðvarsdóttir, E.B., Bagger, N.-C.F., Høffner, L.E., Stidsen, T.J.R. A flexible mixed integer programming-based system for real-world nurse rostering. Journal of Scheduling 25(1):59-88, 2022. DOI 10.1007/s10951-021-00705-7
  - Recent deployed real-world rostering system (MIP-based, Denmark); comparator for deployment claims and contrast to our metaheuristic choice
  - Slots into: Related Work (deployed systems)
- **[cite-and-skim]** Patrick, J., Montazeri, A., Michalowski, W., Banerjee, D. Automated Pathologist Scheduling at The Ottawa Hospital. INFORMS Journal on Applied Analytics 49(2):93-103, 2019. DOI 10.1287/inte.2018.0969
  - Deployed hospital physician-scheduling system with reported operational adoption; exemplar of the implementation-story genre our paper goes beyond
  - Slots into: Related Work (deployed systems)
- **[cite-and-skim]** Sindermann, K., Schüller, M., Brunner, J.O. Optimizing Physician Scheduling at Kempten Hospital: A Database-Driven Mathematical Programming Approach. INFORMS Journal on Applied Analytics, 2026 (article in advance). DOI 10.1287/inte.2024.0185
  - The most recent deployed physician-scheduling system paper (German hospital, MIP); freshest deployment comparator at submission time
  - Slots into: Related Work (deployed systems)
- **[must-read-fully]** Knust, F., Xie, L. Simulated annealing approach to nurse rostering benchmark and real-world instances. Annals of Operations Research 272(1-2):187-216, 2019. DOI 10.1007/s10479-017-2546-8
  - Metaheuristic (SA) evaluated on both benchmark AND real-world rostering instances; closest domain precedent for real-instance metaheuristic evaluation, cite carefully when claiming novelty
  - Slots into: Related Work (deployed systems / novelty positioning)
- **[background]** Ceschia, S., Schaerf, A. Solving the static INRC-II nurse rostering problem by simulated annealing based on large neighborhoods. Annals of Operations Research 288(1):95-113, 2020. DOI 10.1007/s10479-020-03527-6
  - Schaerf-group exemplar of irace-tuned SA with statistical validation on rostering benchmarks; represents the field-default tuning-then-validate methodology we extend to production data
  - Slots into: Related Work (rostering methodology)
- **[background]** Beed, R. et al. (authors per journal page) HealthRota: An evaluation of a digital rostering platform for managing hospital doctors' rotas and leave. Future Healthcare Journal 9(2), Royal College of Physicians, 2022. DOI per S2514664524004946 listing; PMC9345226
  - Deployed doctor-rostering platform evaluated via usability surveys (SUS); useful contrast: we evaluate a deployed system via objective score statistics + telemetry, explicitly not surveys (verify author list from PMC before citing)
  - Slots into: Related Work (deployed systems, evaluation-style contrast)

## Reproducibility, determinism, and experimental reporting standards in OR/metaheuristics

_Backs the byte-identical determinism contract and frozen pre-specified protocol as first-class contributions; gives the reporting checklist (seeds, budgets, instance disclosure) the experimental sections must visibly satisfy, and the Hooker-style 'scientific not competitive testing' framing of the whole study._

- **[cite-and-skim]** Hooker, J.N. Testing heuristics: We have it all wrong. Journal of Heuristics 1(1):33-42, 1995. DOI 10.1007/BF02430364
  - Classic argument for controlled scientific experimentation on heuristics instead of competitive benchmarking; the philosophical charter for a parameter-robustness study rather than a horse race
  - Slots into: Introduction (framing) + Methods
- **[background]** Barr, R.S., Golden, B.L., Kelly, J.P., Resende, M.G.C., Stewart, W.R. Designing and reporting on computational experiments with heuristic methods. Journal of Heuristics 1(1):9-32, 1995. DOI 10.1007/BF02430363
  - Founding reporting-standards paper for heuristic experiments (disclosure, reproducibility); checklist ancestor
  - Slots into: Methods (experimental setup)
- **[background]** Johnson, D.S. A theoretician's guide to the experimental analysis of algorithms. In: Data Structures, Near Neighbor Searches, and Methodology: Fifth and Sixth DIMACS Implementation Challenges, pp. 215-250, AMS, 2002
  - Mandatory-reading experimental-analysis guidance (pitfalls, seeds, reproducibility); classic authority citation
  - Slots into: Methods (experimental setup)
- **[cite-and-skim]** Kendall, G., Bai, R., Błazewicz, J., De Causmaecker, P., Gendreau, M., John, R., et al. Good Laboratory Practice for optimization research. Journal of the Operational Research Society 67(4):676-689, 2016. DOI 10.1057/jors.2015.77
  - OR-specific standards proposal (code/data/seed disclosure); our determinism contract can be presented as exceeding GLP
  - Slots into: Methods (reproducibility) + Discussion
- **[cite-and-skim]** López-Ibáñez, M., Branke, J., Paquete, L. Reproducibility in Evolutionary Computation. ACM Transactions on Evolutionary Learning and Optimization 1(4):1-21, 2021. DOI 10.1145/3466624
  - Typology of reproducibility levels for stochastic optimization; lets us name exactly which level a byte-identical determinism contract achieves
  - Slots into: Methods (reproducibility) + Discussion
- **[cite-and-skim]** Bartz-Beielstein, T., Doerr, C., Bossek, J., et al. Benchmarking in Optimization: Best Practice and Open Issues. arXiv:2007.03488, 2020
  - Community consensus on benchmarking: goals, performance measures, analysis, reproducibility; use to justify design choices (fixed reference scorer config for cross-run re-scoring, seed policies)
  - Slots into: Methods (experimental setup)

