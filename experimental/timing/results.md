# M2 pipeline timing benchmark — first run

**Run on:** Darwin 24.6.0 (Mac mini)
**Python:** 3.14
**Snapshot fixture:** real ICU/HD May 2026 (22 doctors × 29 days × 638 requests)
**Seed:** 20260504 (fixed; byte-identical output guaranteed per `docs/selector_contract.md` §18)
**Retention:** BEST_ONLY
**Date:** 2026-04-29

## Measured

| max-candidates | wall time (s) | winner score | placement attempts | seconds per candidate |
|--:|--:|--:|--:|--:|
| 1 | 1.73 | -506.029 | 76,682 | 1.73 |
| 10 | 16.34 | -286.580 | 759,385 | 1.63 |
| 100 | 162.45 | -59.968 | 7,614,358 | 1.62 |
| 1,000 | _stopped at the user's request_ | — | — | — |
| 10,000 | _not run_ | — | — | — |
| 100,000 | _not run_ | — | — | — |

## Linear scaling — what the projections look like

Wall time and rule-engine attempts both scale linearly in `--max-candidates` (each candidate is an independent solver run with no caching across iterations under `SEEDED_RANDOM_BLIND`). At ≈1.6 s per candidate:

| max-candidates | projected wall time |
|--:|--|
| 1,000 | ~27 minutes |
| 10,000 | ~4.5 hours |
| 100,000 | ~45 hours |

Projections valid only at this dataset size (22 doctors × 29 days). Larger rosters scale further; smaller rosters scale less.

## Interpretation

- **Score gradient diminishes fast.** 1 candidate = -506; 10 = -287; 100 = -60. Going 1→10 saves ~220 points; 10→100 saves ~227 more. Each 10× more candidates is a comparable gain at this scale.
- **Practical pilot ceiling: ~100-200 candidates.** Sub-3 minutes wall time, score quality already near the achievable optimum on this dataset.
- **For genuine 1000+ candidate exploration**, the path is `docs/future_work.md` FW-0003 (incremental rule engine — likely 10-50× speedup at the inner loop), then optional parallelisation, then cloud orchestration (M4 territory).

## How to reproduce / extend

```
PYTHONPATH=python python3 experimental/timing/run_timing_benchmark.py \
  --snapshot path/to/snapshot.json
```

Custom ladder:
```
PYTHONPATH=python python3 experimental/timing/run_timing_benchmark.py \
  --snapshot path/to/snapshot.json \
  --counts 50,200,500
```

The script's per-run timeout is 10 minutes (`_TIMEOUT_SEC = 600`). Bumping it would let 1000-iter runs complete (~27 min) but those projections are linear so the marginal information value is low — stop the benchmark when the per-candidate cost stabilises.
