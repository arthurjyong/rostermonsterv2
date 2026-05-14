# Cloud end-to-end pipeline timing — M7 async path

**Measured:** 2026-05-14
**Pipeline:** bound shim (click) → Cloud Run front door → Cloud Batch worker → launcher async callback → operator email
**Source:** Cloud Logging `[timing]` markers (instrumentation from PR #167)
**Environment:** Cloud Run revision `roster-monster-compute-00017-pxk`, region `asia-southeast1`, `K=22` / `c3-highcpu-22` (quota-limited workaround per PR #161 — *not* the M7 baseline `K=88` / `c3-highcpu-88`)
**Fixture:** single live ICU/HD snapshot, source spreadsheet `1g_7VE-Dad0bI8TVWo7EsTxdG2bM8-XzGLmDBlwroFko`

> Non-normative scratch per `experimental/README.md`. Wall times are infrastructure-dependent — VM provisioning, Cloud Run cold-start, and regional capacity all vary run-to-run. Treat this as an order-of-magnitude baseline, not an SLA.

## Runs

Three runs on the same fixture, same day:

| Run | Click (UTC) | Batch wall | Click → email | Click side measured? |
|--|--|--:|--:|--|
| 1 | ~13:10 | 3m45s | ~4m (est.) | No — operator copy not yet GCP-linked |
| 2 | ~13:20 | 3m06s | ~3m23s (est.) | No — operator copy not yet GCP-linked |
| 3 | 13:59:26 | 3m00s | **3m23s** | **Yes** — operator copy GCP-linked first |

Runs 1–2 predate GCP-linking the operator copy's Apps Script project, so only their cloud-side markers reached Cloud Logging; their click side is estimated from Run 3's measured 23.5s. Run 3 is the first fully-measured end-to-end run.

## Run 3 — full waterfall

Solve clean: K′ = 22 of K = 22 trajectories retained, 0 dropped.

| Stage | Duration | Notes |
|--|--:|--|
| Click → "submitted" | 23.5s | preflight 1.8s · config 0.2s · snapshot extract 13.2s · front-door call 8.3s (incl. ~6s Cloud Run cold start) |
| VM provisioning | 47.5s | Batch job `createTime` → `worker_container_init` |
| LAHC solve (Pool, K=22) | 66.0s | `worker_pool_done duration_ms=65999` |
| Aggregate + score + select + analyze | 0.1s | inline finalize step |
| Callback handoff (worker → launcher) | 3.6s | network transit + Apps Script `doPost` spin-up |
| Launcher callback processing | 62.2s | token validate 0.2s · writeback 13.9s · render analysis tabs 47.4s · send email 0.3s |
| **Total — click → email in inbox** | **3m23s** | |

## Interpretation

- **Time distribution:** ~⅓ LAHC solve, ~⅓ launcher callback (writeback + tab render), ~¼ VM provisioning, ~12% the click side the operator actually waits on at their desk.
- **Biggest single stage** is the launcher rendering the analysis tabs (47.4s); LAHC (66s) is larger but that's the actual optimization work.
- **Operator-perceived wait** is just the 23.5s click → "submitted"; everything after runs unattended and emails them.
- **Variance:** VM provisioning ran ~47s here vs. an inferred ~1m43s in Run 1's longer batch wall; Cloud Run cold start added ~6s to Run 3's front-door call. Warm front door + fast provisioning lands nearer ~2m45s; cold start + slow provisioning nearer ~4m.

## Finding — callback POST times out on healthy runs

On Run 3 the worker's callback POST to the launcher **hit its 60s timeout** (`finalize_callback_done elapsed_ms=60180`): the launcher's callback processing took ~62s (dominated by the 47.4s analysis render), longer than the worker's 60s per-attempt timeout set in PR #171.

This was **harmless this run** — Apps Script `doPost` keeps executing regardless of whether the HTTP client is still listening, and `retries=0` (also PR #171) prevents a duplicate POST — so the launcher finished ~6s later and the operator got the email, writeback, and all tabs. The Batch job went `SUCCEEDED`.

But it means the 60s timeout is **exceeded on every healthy run** at this render cost, so "callback timed out" in the worker logs is no longer a meaningful failure signal. Candidate follow-ups (not yet decided): lengthen the timeout past worst-case launcher processing, or have the launcher acknowledge receipt immediately and do the slow writeback/render after responding.

## How to reproduce

The click-side (bound shim) `[timing]` markers only reach Cloud Logging if the operator copy's Apps Script project is GCP-linked: open the sheet → Extensions → Apps Script → Project Settings → Google Cloud Platform → Change project → `693837275969`. Cloud-side markers (worker, launcher, Cloud Run) flow unconditionally.

After a run, scrape the markers (replace `<start>` with a timestamp just before the click):

```
gcloud logging read 'resource.type="app_script_function" AND timestamp>"<start>"' --project rostermonsterv2 --order=asc --format="value(timestamp,jsonPayload.message,textPayload)"
gcloud logging read 'resource.type="batch.googleapis.com/Job" AND timestamp>"<start>"' --project rostermonsterv2 --order=asc --format="value(timestamp,textPayload)" | grep timing
gcloud batch jobs list --project rostermonsterv2 --location asia-southeast1 --format="value(name.basename(),status.state,createTime,updateTime)"
```

Marker format is `[timing] stage_name {delta_ms|ts_ms|elapsed_ms}=N ...` per PR #167.
