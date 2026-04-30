# Cloud Compute Service (M4 C1)

The Cloud Run container that hosts the HTTP wrapper around
`rostermonster.pipeline.run_pipeline()` per `docs/decision_log.md`
D-0050 + D-0051 and `docs/cloud_compute_contract.md`.

## What lives here

- `requirements.txt` — runtime deps (flask + gunicorn; rostermonster
  itself has no third-party deps).
- `README.md` — this file.

The `Dockerfile` lives at the **repo root** (not here) so
`gcloud run deploy --source .` from the repo root finds it
automatically without extra flags. The Dockerfile copies the Python
source from `python/rostermonster/` and `python/rostermonster_service/`
plus this directory's `requirements.txt` into the image at build
time.

A `.gcloudignore` at the repo root prunes the Cloud Build upload
context (excludes `.git`, `apps_script/`, `docs/`, test data, etc.)
to keep build times short — important for cold-start sensitivity.

## Build + deploy (M4 C1 Phase 2 workstream b)

From the repo root:

```bash
gcloud run deploy roster-monster-compute \
    --source . \
    --region asia-southeast1 \
    --no-allow-unauthenticated \
    --max-instances 5 \
    --min-instances 0 \
    --concurrency 1 \
    --timeout 300s \
    --project rostermonsterv2
```

`--source .` triggers Cloud Build under the hood, picking up the
`Dockerfile` here per Cloud Run's source-deploy convention. After
deployment, grant the operator allowlist `roles/run.invoker`:

```bash
gcloud run services add-iam-policy-binding roster-monster-compute \
    --member="user:arthurjyong@gmail.com" \
    --role="roles/run.invoker" \
    --region=asia-southeast1 \
    --project=rostermonsterv2
```

(Repeat per allowlisted email.)

## Local development

```bash
# Install deps
pip install -r cloud_compute_service/requirements.txt

# Run the Flask dev server
PYTHONPATH=python python -m rostermonster_service.app
# Service listens on http://0.0.0.0:8080/compute
```

## Smoke test against the deployed service

```bash
TOKEN=$(gcloud auth print-identity-token)
URL="https://roster-monster-compute-<HASH>-as.a.run.app/compute"
curl -X POST "$URL" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$(jq '{snapshot: .}' python/tests/data/icu_hd_may_2026_snapshot.json)"
```

Expected response: `{"state": "OK", "writebackEnvelope": {...}, "error": null}`.

## Configuration

All container config is encoded in the Dockerfile + the `gcloud run
deploy` flags. The service has no environment-variable knobs beyond
`PORT` (Cloud-Run-injected). Defaults for `maxCandidates` and `seed`
live in `python/rostermonster/pipeline.py`; both surfaces (CLI + this
service) defer to those constants per `docs/decision_log.md` D-0050 +
D-0053.
