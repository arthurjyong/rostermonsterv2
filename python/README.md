# Roster Monster v2 — local-first Python compute pipeline

Local-first Python implementation of the Roster Monster v2 compute pipeline, per
`docs/decision_log.md` D-0018 (stack ownership: Apps Script for sheet-facing
surface, local-first Python for compute-heavy core).

## Status

Active milestone: **M2** (`Minimal local compute pipeline`).
Active checkpoint: **M2 C3** (`Parser/normalizer implementation closure`),
currently at **T1** (parser side).

Subsequent tasks/checkpoints will extend this package with the normalizer side
(T2), rule engine, scorer, solver, and selector implementations.

## Layout

```
rostermonster/
├── domain.py              # core normalized domain types
├── snapshot.py            # snapshot input types (per docs/snapshot_contract.md)
├── template_artifact.py   # template artifact input types (per docs/template_artifact_contract.md)
└── parser/
    ├── __init__.py        # public entry: parse(snapshot, template) -> ParserResult
    ├── result.py          # ParserResult, ValidationIssue, Consumability
    ├── request_semantics.py  # ICU/HD request grammar (per docs/request_semantics_contract.md)
    └── admission.py       # admission pipeline (structural + semantic per parser_normalizer §13/§14)

tests/
├── fixtures.py            # ICU/HD test fixture builders
└── test_parser.py         # admission tests (positive + negative)
```

## Smoke test

From the `python/` directory:

```
python3 tests/test_parser.py
```

Exit code 0 means all admission cases passed. Failures are printed to stderr.

(Pytest-compatible: when `pytest` is available, the same file is discoverable
via `pytest tests/`.)

## Scope

ICU/HD first release only. Multi-department generalization, CLI / launcher
integration, and downstream-stage wiring (rule engine / scorer / solver /
selector / writeback) all remain deferred per
`docs/delivery_plan.md` §10.
