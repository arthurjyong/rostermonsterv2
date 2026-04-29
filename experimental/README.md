# Experimental

**Non-normative scratch space** for run outputs, timing benchmarks, and exploratory roster generation. None of the contents here are contract-binding or part of the M2 deliverable; this directory is for the maintainer to characterize behavior and inspect "real" rosters before formalizing anything.

If a finding here promotes to settled work, migrate it into the proper authoritative doc (`docs/decision_log.md`, `docs/future_work.md`, etc.) and delete the entry from this folder.

## Layout

- `timing/` — benchmark runs measuring how long the solver+scorer+selector pipeline takes at different `--max-candidates` values. The `run_timing_benchmark.py` script is committed and re-runnable; raw output JSON files are gitignored to keep the repo lean.
- (future) `roster_inspections/` — saved generations from the live launcher + extractor, for spot-checking that the produced rosters are operationally sensible.

## Conventions

- **Don't commit large JSON outputs** by default — they're easy to regenerate and bloat the repo. Per-run timing summaries (small markdown / CSV) are fine to commit for reference.
- **Note machine + Python version** in any timing reports. Solver wall time is hardware-dependent and a 2024 MacBook will differ from a 2020 Linux laptop.
- **Reproducibility lives in the seed.** Any saved roster output should be reproducible from `(--snapshot path, --seed N, --max-candidates M, --retention X)` per `docs/selector_contract.md` §18 byte-identical-determinism guarantee.

## When to clean this up

After M3 closes (or when this folder accumulates more than a few MB of saved files), prune it. The contents here are exploratory — keeping every old run forever is not the goal.
