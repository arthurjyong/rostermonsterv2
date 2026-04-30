# Cloud Run container for the M4 C1 cloud compute service per
# `docs/decision_log.md` D-0051 + `docs/cloud_compute_contract.md` §8.5.
#
# Build context: repo root.
# Build: `gcloud run deploy roster-monster-compute --source . \
#          --region asia-southeast1 --no-allow-unauthenticated`
# Or: `docker build -f cloud_compute_service/Dockerfile -t rmcompute .`
#
# Per D-0051 sub-decision 5, Flask is chosen over FastAPI for smaller
# container size + faster cold start. gunicorn is the production WSGI
# server (Cloud Run requires a process listening on $PORT).

FROM python:3.12-slim AS base

# Avoid .pyc clutter + ensure unbuffered stdout for Cloud Run logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install Python deps. flask + gunicorn are the only runtime deps; the
# rostermonster package itself is pure-Python with no third-party
# dependencies, so the install footprint stays minimal — important for
# Cloud Run cold-start latency (D-0051 sub-decision 5 + §8.6).
COPY cloud_compute_service/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Copy the rostermonster + rostermonster_service modules into the image.
# The build context is the repo root so we cherry-pick the python/ tree.
COPY python/rostermonster /app/rostermonster
COPY python/rostermonster_service /app/rostermonster_service

# Cloud Run injects PORT in the container env (default 8080). gunicorn
# binds to 0.0.0.0:$PORT. Single worker because compute is CPU-bound
# (concurrency 1 per `docs/cloud_compute_contract.md` §8.3).
# 600s timeout matches the 5-min service-side timeout per §8.4 with
# headroom for gunicorn's wrapping overhead.
ENV PORT=8080
EXPOSE 8080

CMD exec gunicorn \
    --bind 0.0.0.0:${PORT} \
    --workers 1 \
    --threads 1 \
    --timeout 600 \
    --access-logfile - \
    --error-logfile - \
    'rostermonster_service.app:app'
