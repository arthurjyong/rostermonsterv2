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

Two-command deploy: first build the Docker image (Cloud Build's
`--source` autodetection prefers buildpacks when `pyproject.toml`
is present in the source tree, so we explicitly use `gcloud builds
submit` to force the Dockerfile path); then deploy the image.

From the repo root:

```bash
# 1) Build + push the image
gcloud builds submit \
    --tag gcr.io/rostermonsterv2/roster-monster-compute:latest \
    --project rostermonsterv2

# 2) Deploy the image to Cloud Run
gcloud run deploy roster-monster-compute \
    --image gcr.io/rostermonsterv2/roster-monster-compute:latest \
    --region asia-southeast1 \
    --allow-unauthenticated \
    --max-instances 5 \
    --min-instances 0 \
    --concurrency 1 \
    --timeout 300s \
    --set-env-vars "ALLOWED_EMAILS=arthurjyong@gmail.com" \
    --project rostermonsterv2
```

Per `docs/decision_log.md` D-0054, the service runs
`--allow-unauthenticated` at the platform layer; operator-identity
gating is enforced **app-side** by Flask validating the bound shim's
ID token against the `ALLOWED_EMAILS` env var. The IAM
`roles/run.invoker` binding is no longer required for invocation
(public service); it can be left in place as defense-in-depth so
that a future switch back to `--no-allow-unauthenticated` works
without re-binding.

**Adding a new pilot operator** to the allowlist:

```bash
gcloud run services update roster-monster-compute \
    --update-env-vars "ALLOWED_EMAILS=existing@example.com,new@example.com" \
    --region asia-southeast1 \
    --project rostermonsterv2
```

The same email must also be on the OAuth consent screen Test Users
list for the operator's bound shim consent flow to succeed.

## Local development

```bash
# Install deps
pip install -r cloud_compute_service/requirements.txt

# Run the Flask dev server
PYTHONPATH=python python -m rostermonster_service.app
# Service listens on http://0.0.0.0:8080/compute
```

## Smoke test against the deployed service

Per D-0054, the operator's ID token travels in `X-Auth-Token`
(NOT `Authorization` — Cloud Run strips the latter on
`--allow-unauthenticated` services). `gcloud auth
print-identity-token` issues a token whose `email` claim is the
gcloud-authenticated user; that email must be on `ALLOWED_EMAILS`.

```bash
URL=$(gcloud run services describe roster-monster-compute \
    --region asia-southeast1 \
    --project rostermonsterv2 \
    --format="value(status.url)")
TOKEN=$(gcloud auth print-identity-token)
curl -X POST "${URL}/compute" \
    -H "X-Auth-Token: ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$(jq '{snapshot: .}' python/tests/data/icu_hd_may_2026_snapshot.json)"
```

Expected response: `{"state": "OK", "writebackEnvelope": {...}, "error": null}`.

## Configuration

The service reads two environment variables:

- **`PORT`** (Cloud-Run-injected) — the bind port. Defaults to 8080
  if unset (local dev).
- **`ALLOWED_EMAILS`** (REQUIRED in production) — comma-separated
  list of operator emails permitted to invoke the service. Per
  `docs/decision_log.md` D-0054, Flask reads this on every request,
  validates the X-Auth-Token's `email` claim against it, and
  returns `INPUT_ERROR` with `code: "EMAIL_NOT_ALLOWLISTED"` on
  mismatch. If `ALLOWED_EMAILS` is unset, the service rejects every
  request with `code: "SERVICE_MISCONFIGURED"` (defense-in-depth
  against accidental no-allowlist deploys).
- **`DISABLE_AUTH_FOR_LOCAL_TESTING`** (set in
  `python/tests/test_service.py`) — skips the auth path entirely.
  Production Cloud Run never sets this. Used by Flask test_client
  unit tests to avoid mocking Google's token-verification endpoint.

Defaults for `maxCandidates` and `seed` live in
`python/rostermonster/pipeline.py`; both surfaces (CLI + this
service) defer to those constants per `docs/decision_log.md` D-0050 +
D-0053.
