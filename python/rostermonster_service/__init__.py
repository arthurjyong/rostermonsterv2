"""HTTP wrapper around `rostermonster.pipeline.run_pipeline()` per
`docs/decision_log.md` D-0050 + `docs/cloud_compute_contract.md`.

The Cloud Run service consumes this package as `python -m
rostermonster_service.app` (or via the `Dockerfile`'s gunicorn
entrypoint). Apps Script's bound shim "Solve Roster" handler is the
operator-facing client per D-0052.

Public surface:
- `rostermonster_service.app.create_app()` — Flask app factory.
"""
