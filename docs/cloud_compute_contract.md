# Cloud Compute Contract

## 1) Contract status and scope
This contract pins the boundary between the Apps Script side (bound shim and launcher) and the cloud-deployed Python compute service introduced in M4 C1 per `docs/decision_log.md` D-0049 / D-0050 / D-0051. It governs:
- the HTTP request/response shape exchanged across the boundary,
- the auth model that protects the boundary,
- the structured error envelope on the response side,
- determinism and idempotency stance,
- deployment posture (region, scaling, timeout, container).

The contract does NOT govern the operator-facing UX surfaces (bound shim menu interactions, success/error dialogs), the Python compute internals (parser, solver, scorer, selector — those have their own contracts), or the writeback step that consumes the cloud service's response (writeback contract handles that).

## 2) Contract identity and versioning
- **Contract name:** `cloud_compute_contract.md`
- **Contract version:** `1`
- **Bump rule:** §11.

## 3) Status discipline used in this document
- **Repo-settled** sections describe state pinned by prior contracts or decisions.
- **Proposed in this checkpoint (normative)** sections describe pinning landing in M4 C1 Phase 1.
- **Deferred** sections describe state explicitly not pinned by this contract.

## 4) Repo-settled architecture anchors
Repo-settled:
- `docs/decision_log.md` D-0017 / D-0018 — stack split: compute core lives in Python; Apps Script is the sheet-facing adapter. Cloud compute is the Python side delivered as an HTTP service.
- `docs/decision_log.md` D-0023 — M1.1 OAuth posture: launcher executes as user, scoped via `https://www.googleapis.com/auth/drive` and friends. Cloud compute does NOT add new OAuth scopes; the `ScriptApp.getIdentityToken()` mechanic uses the existing user-side authentication.
- `docs/decision_log.md` D-0040 — inbound transport (snapshot extraction) = browser-saved JSON file. Cloud compute receives the snapshot via HTTP request body, NOT via a Drive read or other side channel.
- `docs/decision_log.md` D-0041 — Apps Script project layout: launcher (`launcher`), bound shim (`bound_shim`), central library (`central_library`). Cloud compute is invoked from the bound shim per D-0052.
- `docs/decision_log.md` D-0044 — writeback transport = file upload via launcher form. Cloud compute is parallel to that path: same Python code, same wrapper envelope shape, but invoked over HTTP from the bound shim instead of consumed from a JSON file via the local CLI.
- `docs/decision_log.md` D-0045 — writeback envelope wrapper shape (`schemaVersion` + `finalResultEnvelope` + `snapshot` subset + `doctorIdMap`). The cloud compute service produces this same shape; the bound shim hands it directly to `RMLib.applyWriteback(envelope)` per D-0052 without a file boundary in between.
- `docs/decision_log.md` D-0049 — M4 reframed to "Cloud end-to-end pipeline + dual-track preservation". This contract is M4 C1's principal contract surface.
- `docs/decision_log.md` D-0050 — dual-track Python architecture: same compute core, two thin wrappers (CLI + HTTP). The HTTP wrapper governed by this contract calls the same compute core the local CLI calls.
- `docs/decision_log.md` D-0051 — Cloud Run platform + `ScriptApp.getIdentityToken()` → IAM auth + consolidated `RosterMonsterV2` GCP project.
- `docs/decision_log.md` D-0052 — Apps Script library reorganization: writeback library moves to central library so bound shim can invoke writeback inline; bound shim menu adds "Solve Roster" item.
- `docs/writeback_contract.md` — pure-function writeback adapter, contractVersion 1, §9 6-category snapshot subset. Cloud compute produces an envelope conforming to writeback §9.
- `docs/selector_contract.md` v2 — `FinalResultEnvelope` shape with required `runEnvelope.sourceSpreadsheetId` + `runEnvelope.sourceTabName` fields. Cloud compute's response embeds a conforming `FinalResultEnvelope`.

## 5) Purpose
Pin the cloud-deployed compute service's HTTP boundary so:
- the bound shim's "Solve Roster" handler knows exactly what to send and what to expect back,
- the cloud service implementation has unambiguous request/response semantics,
- the auth model is operator-account-scoped without introducing a new credential surface,
- the structured-error envelope mirrors the writeback diagnostic surface so the operator sees consistent failure messaging,
- determinism and idempotency stance is explicit (no surprise from cloud-mode runs differing from local-mode runs at the same seed).

## 6) Boundary position
Repo-settled:
- **Upstream** (caller): bound shim's "Solve Roster" handler in `apps_script/bound_shim/`, invoked from the in-spreadsheet menu. The launcher's writeback Web App does NOT call this service — the launcher's writeback path remains file-upload-only per D-0046.
- **Boundary**: HTTP POST request from Apps Script's `UrlFetchApp.fetch(...)` to a Cloud Run service URL. Single endpoint per service deployment.
- **Downstream** (callee): Cloud Run service running the Flask HTTP wrapper around `python/rostermonster/run.py`'s shared compute core per D-0050.

Proposed in this checkpoint (normative):

### 6.1 Stack ownership
The cloud compute service is owned by the Python side per the D-0017 / D-0018 stack split. The Flask wrapper is a thin HTTP adapter; substantive compute logic lives in the existing parser / solver / scorer / selector modules. No domain logic lands in the cloud-service code.

### 6.2 Single endpoint
The service exposes exactly one operator-facing operation: `POST /compute`. No additional operator-facing endpoints (no `/health`, `/version`, `/extract`, etc.) are pinned by this contract; if Cloud Run requires a health-check path, it MAY be added as an implementation-slice concern. The contract pins only the compute-call behavior.

**Maintainer-only test routes (M7 C2 onward, per `docs/decision_log.md` D-0070 + D-0071 sub-decision 14):** the service MAY additionally expose maintainer-only routes that bypass the §9 input contract for pre-promotion implementation testing. These routes are out-of-band — invoked by curl with the same operator-token auth (§7) restricted to the maintainer's email, NOT operator-reachable from the bound shim, and NOT part of the §9 / §10 boundary contract. The first such route is the **LAHC Cloud Batch test path**, added at M7 C2 to let the maintainer trigger the parallel cloud LAHC compute pipeline. The test route accepts the same snapshot body as §9 but routes through the M7 C2 Cloud Batch worker code path rather than the in-process direct-compute path. Specific URL path is implementation-slice. **Per D-0071 sub-decision 14, the test route is KEPT after the M7 C3/C4 operator path goes live** (NOT removed as previously planned at M7 C2 docs-lock). Retained because the test route exposes the SYNCHRONOUS-from-curl invocation pattern (maintainer waits for the orchestrator response inline rather than receiving an async callback to a launcher Web App) which remains the simplest maintainer-side smoke test surface after the operator path moves to async per D-0071. Operator path uses the §9/§10 + §10A async-callback contract; maintainer test route uses its own out-of-band invocation pattern; both share the underlying Cloud Batch worker + finalizer chain.

### 6.3 Stateless service
The service is stateless across requests. No per-operator state, no session cookies, no in-memory caching of snapshots between requests. Each request carries everything the service needs (snapshot + optional config); each response carries the full computed envelope.

## 7) Authentication
Proposed in this checkpoint (normative). Updated per `docs/decision_log.md` D-0054 (audience-mismatch finding from M4 C1 Phase 2 testing — original IAM-based design rejected every bound-shim request because `ScriptApp.getIdentityToken()`'s `aud` claim is the Apps Script project's GCP OAuth client ID, not the Cloud Run service URL).

### 7.1 Auth mechanism
The service runs `--allow-unauthenticated` at the Cloud Run platform layer. Operator-identity gating is enforced **app-side** by the Flask handler:
1. Bound shim calls `ScriptApp.getIdentityToken()` to mint a Google OIDC token carrying the operator's identity.
2. Bound shim sends the token as the value of a custom `X-Auth-Token` request header (NOT the standard `Authorization` header — see §7.5).
3. Flask handler validates the token via `google.oauth2.id_token.verify_oauth2_token(token, requests.Request(), audience=None)` — signature, expiry, and `email_verified` are checked; `aud` is intentionally not enforced.
4. Flask handler reads the `email` claim and checks it against the `ALLOWED_EMAILS` env var (comma-separated list of lower-cased emails) on the Cloud Run service.
5. Token-validation or allowlist mismatch returns a structured `INPUT_ERROR` response per §10.1 with one of the auth-specific `error.code` values (`MISSING_AUTH_TOKEN`, `INVALID_TOKEN`, `EMAIL_NOT_VERIFIED`, `EMAIL_NOT_ALLOWLISTED`, `SERVICE_MISCONFIGURED`).

### 7.2 Operator allowlist via env var
`ALLOWED_EMAILS` env var on the Cloud Run service is the operator allowlist. Adding a new pilot operator: `gcloud run services update roster-monster-compute --update-env-vars=ALLOWED_EMAILS=existing,new@example.com --region=asia-southeast1`. Single-knob configuration; no IAM ceremony, no service account creation. The same email must also be on the OAuth consent screen Test Users list for the operator's bound shim consent flow to succeed.

### 7.3 Required manifest OAuth scopes on the bound shim
The bound shim's `apps_script/bound_shim/src/appsscript.json` MUST declare the following scopes:
- **`https://www.googleapis.com/auth/spreadsheets`** (full, NOT `spreadsheets.currentonly`) — required by `SpreadsheetApp.openById()` which the writeback library calls inside `RMLib.applyWriteback(envelope)`. Live testing confirmed `spreadsheets.currentonly` is insufficient even when the target ID is the bound spreadsheet's own ID; Apps Script's scope check fires before the spreadsheet-existence check ("Specified permissions are not sufficient to call SpreadsheetApp.openById. Required permissions: https://www.googleapis.com/auth/spreadsheets"). The narrower `spreadsheets.currentonly` was the original M2 C9 default for the snapshot extractor, which only uses `getActiveSpreadsheet()` and never `openById`; M4 C1's writeback path requires the broader scope.
- **`https://www.googleapis.com/auth/script.external_request`** — required for `UrlFetchApp.fetch(...)` to call Cloud Run.
- **`openid`** — required for `ScriptApp.getIdentityToken()` to issue a valid OIDC ID token.
- **`https://www.googleapis.com/auth/userinfo.email`** — required to populate the OIDC token's `email` claim that Flask validates against the `ALLOWED_EMAILS` env var.
- **`https://www.googleapis.com/auth/script.container.ui`** (existing, unchanged) — required for the menu / dialog UI affordances the bound shim exposes.

These are operator-account scopes (no service account, no shared secret); each one is explicitly enumerated in the consent dialog the operator approves on first invocation of the "Solve Roster" menu. The launcher's own manifest is unchanged — the launcher does not invoke Cloud Run; the bound shim does.

### 7.4 Token freshness
`ScriptApp.getIdentityToken()` issues short-lived tokens (~1 hour); the bound shim acquires a fresh token at each invocation. No token caching is required or expected at the Apps Script side. Flask validates the token's expiry on each request via the google-auth library.

### 7.5 Custom `X-Auth-Token` header (NOT `Authorization`)
The standard `Authorization` header CANNOT be used with this auth model. Per Google's documentation (https://cloud.google.com/run/docs/securing/managing-access#allow-unauthenticated), Cloud Run drops the `Authorization` header on `--allow-unauthenticated` services to prevent token-leakage from public services. Using a custom `X-Auth-Token` header is the documented workaround — Cloud Run does not strip non-`Authorization` headers, so the bound shim's token arrives at Flask intact. This is a contract-level decision per `docs/decision_log.md` D-0054; clients of this contract MUST use `X-Auth-Token`.

### 7.6 Service account flow remains future-work
The cleanest long-term auth architecture is a service account with `roles/run.invoker` + the Apps Script OAuth2 library minting OIDC tokens with the correct audience (the Google-recommended Cloud Run + Apps Script pattern). Deferred for first release because (a) it requires storing service-account JSON in Apps Script Script Properties (a credential surface), (b) it requires importing the apps-script-oauth2 library, (c) operator-identity gating becomes service-account-mediated rather than direct (operator-attribution lost in Cloud Run logs without app-level email surfacing). Promote when pilot scope grows or formal least-privilege posture is required; the migration is backwards-compatible (token transport stays as `X-Auth-Token`, just becomes service-account-mediated).

## 8) Deployment posture
Proposed in this checkpoint (normative):

### 8.1 Platform
Cloud Run, GCP project `RosterMonsterV2`. Service name: `roster-monster-compute` (provisional; pinned at first deploy).

### 8.2 Region
Asia-Southeast1 (Singapore) — operator-proximate. May be revisited if pilot expands to operators outside Asia-Pacific.

### 8.3 Scaling
- **Min instances**: 0 (scale-to-zero — cost-saving default).
- **Max instances**: 5 (defense-in-depth bound; first-release pilot scale doesn't need more).
- **Concurrency**: 1 request per instance (compute is CPU-bound; sharing CPU across concurrent requests degrades both).

### 8.4 Request timeout
Service-side timeout: 5 minutes (300s). **M6 C4 cloud benchmark (2026-05-09 per `docs/decision_log.md` D-0069):** at the default `_DEFAULT_MAX_CANDIDATES` (currently `32`) on the ICU/HD May 2026 dev-copy fixture, full request wall time is ~283s cold and ~270s warm (Phase 1 + Phase 2 × K=32 + scorer + selector + writeback assembly under a GIL-bound 1-vCPU container). **Headroom against the 300s timeout is asymmetric and must be reasoned about separately for cold vs warm runs:**
- **Cold path: ~17s headroom** (300 − 283). The first operator request after Cloud Run scales to zero pays the cold-start tax and is the load-bearing case for "can the operator's first call time out before any `maxCandidates` override?". The answer is "yes, easily" — any per-cycle variance + container init drift can blow the budget at default K=32.
- **Warm path: ~30s headroom** (300 − 270). Subsequent operator requests on a still-warm instance have more slack, but it's still a thin margin once `maxCandidates > 32` overrides land or `K × per-trajectory-time` grows under FW-0035 / FW-0036.

The 5-min cap is not a comfortable ceiling at default config — the cold-path margin is what determines whether the first request fits, and at 17s any cold-start variance flips the request into a 504. The bound shim's `UrlFetchApp.fetch()` inherits Apps Script's per-script-execution 6 min wall clock; the alignment is intentional.

**M7 C3 (D-0071, 2026-05-11) — async pivot for the LAHC strategy path:** The 300s timeout governs the **SRB strategy path only** going forward. The **LAHC strategy path no longer blocks on this timeout** — D-0071 pivots LAHC to an async architecture (M7 C4 implementation). On the LAHC path, the Cloud Run Service is a thin front door: validate input → submit Cloud Batch job → return `SUBMITTED` in ~3-5s (well under any timeout). Compute itself runs in Cloud Batch (worker task group → finalizer task group) under a separate **10-min hard cap** enforced via the finalizer's first-action self-check (`now - RM_SUBMIT_TIMESTAMP_MS > 600_000` → finalizer skips aggregation and sends the timeout-failure email). The finalizer task POSTs the final envelope to a launcher Web App callback per §10A async-callback contract. The 300s Cloud Run Service timeout never participates in the LAHC compute deadline calculus — it only constrains the front-door `submit + return SUBMITTED` round-trip, which has no realistic chance of approaching 300s. **Pre-D-0071 framing** (Cloud Run Service timeout LOWERED to 250s + tail-case Apps Script wall budget of 10+250+30+60+10=360s) is **superseded for the LAHC path** by D-0071's async architecture; that framing remains accurate for the SRB path only.

### 8.5 Container
- Base image: `python:3.12-slim` (or compatible — pinned at Dockerfile commit time).
- Dependencies: `flask` + the local `rostermonster` package (installed via `pip install -e python/` or equivalent at build time).
- Build: `gcloud run deploy --source` or `gcloud builds submit` + `gcloud run deploy --image`. CI integration is implementation-slice and not pinned by this contract.

### 8.6 Cold-start expectation
**M6 C4 cloud benchmark (2026-05-09 per `docs/decision_log.md` D-0069):** measured cold-vs-warm delta is **~13s** at default `_DEFAULT_MAX_CANDIDATES=32` (cold ~283s − warm ~270s per §8.4). This is substantially larger than the pre-M6-C4 framing that cited "~1-2 seconds" container Flask cold start — that older number measured Flask process startup in isolation and missed (a) the Cloud Run container scheduling + image pull on scale-to-zero spinup and (b) Python module-import time for the heavy compute core (`rostermonster.solver`, `rostermonster.scorer`, `rostermonster.parser_normalizer`, etc.) the cloud wrapper transitively imports. Operator-visible latency at first invocation includes cold-start + compute; under the §8.4 timeout math the cold-path margin is the load-bearing one, and ~13s cold-start overhead consumes most of the available headroom under the 5-min Cloud Run cap. If cold-start latency becomes operator-friction (e.g., the first daily request consistently exceeds the timeout under any `maxCandidates` override or under future cloud LAHC at FW-0035 promotion), the platform's `min-instances ≥ 1` setting (paid — keeps at least one container warm so subsequent requests skip the ~13s cold tax) is the documented mitigation; this becomes more compelling under cloud-mode LAHC (FW-0035) + parallel-solver M7 (FW-0038) since both compress the per-request budget further. First release accepts cold start as a tradeoff for scale-to-zero cost savings.

### 8.7 Cloud Batch posture (M7 C2 onward, LAHC strategy path)
Pinned in M7 C2 Task 1 (2026-05-10) per `docs/decision_log.md` D-0070 + the M7 C2 design conversation. **Amended at M7 C3 Task 1 (2026-05-11) per `docs/decision_log.md` D-0071** — finalizer task group added; orchestrator-side 240s polling deadline replaced by Cloud Batch finalizer task that POSTs to launcher Web App callback per §10A; per-task wall budget unblocked from 180s to 540s under a 10-min hard cap enforced via finalizer self-check; concurrent-rejection enforced via Cloud Batch job labels (spreadsheet ID only, normalized to label-safe chars). Cloud Batch is the parallel-execution layer underneath the Cloud Run Service for the LAHC strategy path. SRB stays on the existing in-process direct-compute path (§8.1..§8.6 unchanged for SRB). LAHC dispatches to Cloud Batch via the orchestrator wiring landed in M7 C2 Task 2D + M7 C4 finalizer task group landing.

**Bucket posture:**
- **Bucket:** `rostermonsterv2-lahc` (region `asia-southeast1`, dual-region disabled, uniform bucket-level access enabled). Single project-owned bucket holds all M7 LAHC run artifacts. The bucket name is referenced verbatim throughout §8.7 (object key paths, IAM scoping, the GCS read/write discipline note). If `rostermonsterv2-lahc` is globally unavailable at create time, the maintainer creates a bucket with an alternative name AND lands a docs-only contract amendment updating every §8.7 reference to the selected name before M7 C2 Task 2A proceeds. The contract refuses to dual-name the bucket implicitly because IAM scoping + object-path consistency would silently diverge if §8.7 references drifted from the live bucket.
- **Lifecycle rule:** auto-delete objects older than 90 days. Keeps the bucket bounded without explicit per-run cleanup logic. 90 days gives audit headroom for any run within a quarter-cycle.
- **Object naming convention** (per-run keys, where `{runId}` is the same `runEnvelope.runId` per `docs/selector_contract.md` v2 §9):
  ```
  gs://rostermonsterv2-lahc/{runId}/snapshot.json          # input snapshot, written by orchestrator (in-pipeline)
  gs://rostermonsterv2-lahc/{runId}/task-{n}/seeds.json    # per-task seed slice, written by orchestrator (in-pipeline; one file per Batch task index n in [0, taskCount))
  gs://rostermonsterv2-lahc/{runId}/task-{n}/result.json   # per-task result, written by Batch task on completion (in-pipeline)
  gs://rostermonsterv2-lahc/{runId}/candidates_full.json   # OPTIONAL out-of-band maintainer-audit artifact — see "candidates_full.json reconciliation" below
  ```
  All keys MUST be derivable deterministically from `(runId, task_index)` — no opaque IDs.

**`candidates_full.json` reconciliation with D-0070 sub-decision 10:** D-0070 sub-decision 10 states "no `candidates_full.json` serialization needed because the analyzer runs inline before the response returns" — this means the analyzer pass-through does NOT depend on the GCS artifact. The analyzer always operates on the in-memory K-candidate aggregation produced by the orchestrator's Batch-result aggregation step; this is unchanged. The `candidates_full.json` GCS write is an **OPTIONAL out-of-band maintainer-audit surface ADDITIVE to D-0070 sub-decision 10's in-pipeline framing** — written as a side-effect of the orchestrator's aggregation so the maintainer can later replay `python -m rostermonster.analysis` locally against historical runs (e.g., to re-render with different `--top-k N` or to inspect FW-0030's K-trajectory results without re-running). Implementers MUST NOT make the analyzer pass-through depend on the GCS artifact, MUST NOT block the operator-facing response on the GCS write completing, and MUST tolerate the GCS write failing (log + continue; the operator-facing analyzer + writeback path remains intact). The artifact lands at M7 C2 Task 2D as a fire-and-forget step after Batch aggregation; if M7 C3 measurement shows the GCS write blowing the wall budget, the artifact can be deferred to a post-response background task or dropped without affecting any in-pipeline contract.

**Cloud Batch job spec invariants** (job submitted by Cloud Run Service orchestrator on every LAHC request):
- **Machine type:** `c3-highcpu-8` (8 vCPU, 16 GB RAM; Intel Sapphire Rapids per D-0070 sub-decision 3).
- **Region:** `asia-southeast1` (intra-region with Cloud Run Service + GCS bucket; free egress).
- **Allocation policy:** on-demand only (NOT Spot per D-0070 sub-decision 4 — predictable wall-time).
- **Task count + packing:** derived per D-0070 sub-decision 7's three-quota rule from K_approved (currently 104 per M7 C1 closure → `taskCount=13`, `parallelism=13`, all tasks fully packed at 8 trajectories each). **`taskCountPerNode: 1`** MUST be set on the `taskGroup` so Cloud Batch provisions exactly one task per VM. Without this, Batch's bin-packing logic could co-schedule multiple tasks onto one `c3-highcpu-8` VM (8 vCPU); each task starts `multiprocessing.Pool(8)`, so co-scheduling would oversubscribe the VM and almost certainly miss the per-task wall budget. The "1 task = 1 VM" pinning is what makes the dense-pack math (8 trajectories × 13 VMs = 104) match actual VM allocation.
- **Per-task timeout (worker task group):** **540s** (`taskGroups[0].taskSpec.maxRunDuration: "540s"`) per **D-0071 sub-decision 7** (M7 C3 amendment). Pre-D-0071 setting was 180s under the sync framing; D-0071's async pivot unblocks this to 540s (9 min) to accommodate slow trajectories without the sync request budget pressure. Covers VM provisioning ~30-60s + 8 parallel LAHC trajectories ~360-450s (real production roster at the FW-0037 elbow tuple `L=50`/`idleThreshold=3500`) + GCS I/O ~5-10s + buffer with comfortable margin. The 540s setting fits inside the 10-min total wall budget enforced via the finalizer's first-action self-check (see "Finalizer task group" below).
- **Per-task retry policy (worker task group):** **1 retry on failure, fail-fast on second** (`taskGroups[0].taskSpec.maxRetryCount: 1`). Default Cloud Batch retry is 0; a single retry shrugs off transient VM stalls without doubling worst-case wall time on every run.
- **Job labels for concurrent-rejection (D-0071 sub-decision 8):** Cloud Run Service MUST attach `labels: {spreadsheet_id: "<normalized>"}` to every submitted Cloud Batch job. Operator email is **NOT** stored as a label because Cloud Batch (Google Resource Manager) labels only allow `[a-z0-9_-]{1,63}` — emails contain `@` and `.` which fail label validation. **Normalization for the spreadsheet ID label value:** lowercase the raw `snapshot.metadata.sourceSpreadsheetId`, replace any character outside `[a-z0-9_-]` with `-`, then truncate to 63 chars. Raw spreadsheet IDs commonly carry uppercase characters (Drive uses base64url-ish IDs); without normalization, `submitJob` fails before the concurrent-run guard can ever run. Before submitting a new job, Cloud Run Service MUST `batch.jobs.list` with `filter='labels.spreadsheet_id=<normalized>' AND status.state IN (QUEUED, SCHEDULED, RUNNING)` (region `asia-southeast1`) and **REJECT the new request with INPUT_ERROR code `CONCURRENT_RUN_REJECTED`** if any matching in-flight job exists. The rejection message includes the in-flight job's `createTime` (read off the listed job) + operator-email-of-the-in-flight-job (read off the listed job's `taskGroups[0].taskSpec.environment.variables.RM_OPERATOR_EMAIL`, NOT from a label) — same field the finalizer uses to email the operator per sub-decision 5. Operator-facing message: "A solve is already running for this spreadsheet (started at <createTime> by <existingOperatorEmail>). Wait for completion (you'll receive an email when done)." This protects against duplicate work + protects against the B-prime callback writing to the same spreadsheet twice. Note: label-based query is best-effort (Cloud Batch eventual consistency on filtered list) — race window is tight but non-zero. Acceptable for v1 per D-0071 sub-decision 8 (acceptable-gap-for-v1; finalizer's writeback is idempotent at the spreadsheet level since each writeback creates a new tab — no destructive overwrite if a race slips through).
- **Finalizer task group (D-0071 sub-decision 2 + 3 + 12):** a SECOND task group `taskGroups[1]` runs the finalizer **after the worker task group completes**, gated by:
  ```
  taskGroups[1]:
    name: "finalizer"
    taskCount: 1
    parallelism: 1
    taskSpec:
      maxRunDuration: "120s"   # finalizer's own Batch maxRunDuration — safety net (implementation-slice value; tunable based on observed analyzer/scorer wall time in M7 C4 + M7 C5)
      maxRetryCount: 0          # finalizer is single-shot; retry semantics are operator-visible via the always-email-on-failure path
      runnables: [...]          # invokes worker.py --finalizer-mode (single-image dispatch — see "Container image strategy" below)
      environment:
        variables:
          RM_SUBMIT_TIMESTAMP_MS: "<set by orchestrator at submitJob time>"
          RM_OPERATOR_EMAIL: "<from §9.3 operatorEmail input>"
          RM_LAUNCHER_CALLBACK_URL: "<launcher Web App URL>"
    dependencies:
      - taskGroup: "group0"     # the worker task group
        condition: "SUCCEEDED_OR_FAILED"   # finalizer runs whether workers succeed, fail, or partial — guarantees operator notification even on worker-side disasters per D-0071 sub-decision 12
  ```
  Finalizer responsibilities (M7 C4 implementation):
  1. **Total-wall self-check (D-0071 sub-decision 7):** finalizer's FIRST action is to compare current wall time vs `RM_SUBMIT_TIMESTAMP_MS`. If `(now_ms - RM_SUBMIT_TIMESTAMP_MS) > 600_000` (10 min), finalizer SKIPS aggregation/scoring/render entirely and sends the timeout-failure email immediately (the cost-mention failure email per §10A.7 + D-0071 sub-decision 5). This is how the 10-min hard cap is enforced — Cloud Batch's `Job` schema has no job-level `maxRunDuration`, so the operational deadline is the finalizer's self-check rather than a Batch field.
  2. **Aggregate** worker task results from `gs://rostermonsterv2-lahc/{runId}/task-{n}/result.json` (handles K' partial-failure tolerance per the existing aggregation logic — moved from orchestrator to finalizer).
  3. **Score + select** K candidates → produce `FinalResultEnvelope` + `writebackEnvelope` per `docs/selector_contract.md` v2 §9.
  4. **Analyze** in-memory K candidates → produce `AnalyzerOutput` per `docs/analysis_contract.md`.
  5. **POST callback** to launcher Web App per §10A async-callback contract (with ID-token-in-body auth + retry behavior pinned in §10A).
  6. **Email operator** on any non-OK outcome per §10A.7 (always-email-on-failure).

  Per D-0071 sub-decision 11 + 12, the finalizer **runs always** (regardless of worker outcome) — the `SUCCEEDED_OR_FAILED` dependency guarantees this. If all workers fail entirely, the finalizer aggregates K'=0 → emits `COMPUTE_ERROR` callback (code `WORKER_ALL_FAILED`) + always-email path fires. If the finalizer itself crashes before the email-send line, the operator's outcome is silent (FW-0039 captured this gap as accepted-for-v1; mitigations later).
- **Total wall budget (D-0071 sub-decision 7):** enforced by the finalizer's first-action self-check (10-min / 600_000 ms elapsed since `RM_SUBMIT_TIMESTAMP_MS`). Worker tasks run in parallel within their 540s `maxRunDuration` budget; finalizer's own Batch `maxRunDuration` (120s safety net) caps any single finalizer run independent of the self-check. Cloud Batch's `Job` schema has no job-level `maxRunDuration`; the operational ceiling is the finalizer's elapsed check at 600s, not a Batch field.
- **Orchestrator-side completion deadline:** **NO orchestrator-side polling under D-0071.** Pre-D-0071 the Cloud Run Service polled `batch.jobs.get` and called `batch.jobs.cancel` at 240s. Under D-0071's async pivot, the Cloud Run Service returns `SUBMITTED` immediately after `submitJob` returns — no poll loop, no cancel logic. The Cloud Batch finalizer task is now responsible for end-of-run aggregation + callback (replacing what the orchestrator used to do synchronously). Pre-D-0071 framing is **deprecated for the LAHC path** but retained in this contract's history (the M7 C2 lock language is preserved in §16 for cross-reference).
- **Service account:** the same default Compute Engine SA used by Cloud Run (`{project_number}-compute@developer.gserviceaccount.com`) acts as both the **Batch job creator** (called by Cloud Run Service to submit jobs) AND the **Batch task identity** (the SA that Batch VMs run as). Required IAM additions for M7 C2 (one-time setup, recorded in project memory):
  - `roles/batch.jobsEditor` (project-wide; submit + manage Batch jobs) — required by the job creator.
  - `roles/batch.agentReporter` (project-wide; report VM agent state back to the Batch control plane) — required by the Batch task identity. Without this, VMs spin up but cannot report task progress, and Batch eventually fails the job.
  - `roles/iam.serviceAccountUser` ON the same default Compute SA (granted to itself; principal = `serviceAccount:{project_number}-compute@developer.gserviceaccount.com`) — required so the job creator can "act as" the Batch task identity during job submission. Self-impersonation is NOT implicit on GCP; the role must be granted explicitly even when creator = task identity. Without this, `submitJob` fails with `iam.serviceaccounts.actAs` permission denied.
  - `roles/storage.objectAdmin` scoped to bucket `rostermonsterv2-lahc` only (read/write run artifacts) — required by both the job creator (orchestrator-side snapshot/seed write) and the Batch task identity (worker-side seeds read + result write).
  Existing roles from M4 C1 (`cloudbuild.builds.builder`, `storage.objectViewer`, `logging.logWriter`) carry through; the new bucket-scoped `objectAdmin` supersedes the project-wide read-only `objectViewer` for the LAHC bucket only.

**Container image strategy:** Cloud Run Service and Cloud Batch worker share a **single container image** dispatched by a `--worker-mode` CLI flag added in M7 C2 Task 2B (specific Python module location is implementation-slice; what the contract pins is that the same image satisfies both surfaces). Cloud Run Service container starts in service mode (Flask HTTP wrapper bound to the Cloud Run port); Cloud Batch tasks start in worker mode by overriding the container's command via the job spec's `taskSpec.runnables[0].container.commands[]` array (Cloud Batch's `Runnable.Container` v1 schema has `commands[]` + `entrypoint`, NOT a singular `command` field). One image to keep in sync across CI; one Dockerfile bakes both modes. The single-image discipline pins the same Python compute core to both surfaces, preserving the D-0050 dual-track guarantee.

**Partial-failure tolerance:** if 1+ Batch task fails after retry, OR a surviving task emits fewer candidates than its assigned trajectory count (per `docs/solver_contract.md` §12A.8 — individual trajectories can drop on per-trajectory seed-construction failure WITHOUT failing the whole task), the orchestrator MUST aggregate from the surviving task results' candidates and proceed with the actual emitted count rather than fail the whole run.

**Primary K' definition (source of truth):**
```
K' = sum(len(candidates_emitted_by_task_n) for task_n in completed_tasks)
```
Each completed task emits 0..N candidates where N is its assigned trajectory count (8 for fully-packed tasks; the trajectory count for the final task when K_approved isn't a multiple of 8). Per LAHC §12A.2 each surviving trajectory produces exactly one `bestRoster` candidate, so K' equals the total surviving-trajectory count. Tasks that didn't complete (failed after retry, or cancelled by `batch.jobs.cancel` after the 240s deadline) contribute 0 candidates.

**`dropped_count` for diagnostics (derived):** `dropped_count = K_approved - K'`. Covers ALL drop sources by construction:
- Task-level failures or cancellations contribute the failed task's full trajectory count (8 for fully-packed) to `dropped_count`.
- Per-trajectory seed-construction failures within a completed task per §12A.8 contribute 1 each to `dropped_count`.
- Mixed cases (1 task failed + 1 surviving task drops 1 trajectory) sum correctly.

**Worked examples** (K=104, 13 fully-packed tasks, 8 trajectories each):
- All tasks complete + every trajectory emits → `K' = 104`, `dropped_count = 0`.
- 1 entire task fails after retry → `K' = 96`, `dropped_count = 8`.
- All 13 tasks complete but 2 trajectories within one task hit per-trajectory seed-construction failure → `K' = 102`, `dropped_count = 2`.
- 1 task fails entirely + 1 surviving task drops 1 trajectory → `K' = 95`, `dropped_count = 9`.

LAHC's `K' >= 1` exit criterion per §12A.8 is preserved by this aggregation (surviving trajectories produce valid `bestRoster` candidates per §12A.1 step 5). The actual `K'` MUST be surfaced in `SearchDiagnostics` (added field at M7 C3 contract amendment). Whole-run `UnsatisfiedResult` only fires when `K' == 0` (degenerate case — all tasks failed entirely OR all surviving tasks' trajectories returned per-trajectory seed-construction failures).

**GCS read/write discipline at the boundary:** the pipeline reads from / writes to GCS only inside the orchestrator + Batch worker code paths. Drive is NOT a pipeline data path — operator-facing data flows continue per the §9 / §10 contract (snapshot in via HTTP body, envelope back via HTTP response). The optional `candidates_full.json` artifact (per the reconciliation note above) is maintainer-accessible via `gsutil cp` for post-hoc analysis; operator never reads from GCS.

**Per-task `seeds.json` schema (orchestrator → worker):** pinned at M7 C2 Task 2D (2026-05-10); `attemptId` added at M7 C2 Task 2G (2026-05-10) per the concurrent-replay race fix.

```
{
  "schemaVersion": 1,
  "runId": "<runEnvelope.runId per docs/selector_contract.md v2 §9>",
  "taskIndex": <int in [0, taskCount)>,
  "masterSeed": <int — the §9 input #3 master seed for this run>,
  "attemptId": "<uuid hex — fresh per orchestrator call>",
                          // T2G concurrent-replay race fix: orchestrator
                          // generates a per-call attemptId; worker echoes
                          // back into result.json; aggregation validates
                          // result.attemptId == expected_attempt_id on
                          // read so a parallel attempt at the same runId
                          // prefix can't pollute K' aggregation. See the
                          // "Concurrent-replay race" notes after the
                          // result.json schema.
  "seeds": [<int>, ...]   // per-task slice of the K_approved seeds the
                          // orchestrator pre-derived via
                          // derive_K_seeds(masterSeed, K_approved) per
                          // docs/solver_contract.md §12A.10. Length MUST
                          // be <= 8 (the dense-pack invariant — 1
                          // trajectory per c3-highcpu-8 vCPU). Length is
                          // typically 8 for fully-packed tasks; the final
                          // task in a non-multiple-of-8 K_approved
                          // partition may carry fewer (current production
                          // K=104 → all 13 tasks fully packed).
}
```

**Per-task `result.json` schema (worker → orchestrator):** pinned at M7 C2 Task 2D (2026-05-10); `attemptId` added at M7 C2 Task 2G (2026-05-10).

```
{
  "schemaVersion": 1,
  "runId": "<echoed from seeds.json>",
  "taskIndex": <echoed from seeds.json>,
  "masterSeed": <echoed from seeds.json>,
  "attemptId": "<echoed from seeds.json>",  // T2G concurrent-replay race fix; orchestrator validates on read
  "candidates": [               // SUCCEEDED trajectories — len(candidates)
                                // is this task's contribution to K' per
                                // the primary K' definition above
    {
      "candidateSeed": <int>,                   // the seed this trajectory ran on
      "assignments": [...],                     // _to_jsonable(TrialCandidate.assignments) — ready for orchestrator analyzer pass-through
      "iters": <int>,                           // §12A.9 perTrajectoryIters
      "acceptedMoves": <int>,                   // §12A.9 perTrajectoryAcceptedMoves
      "bestScore": <float | null>,              // §12A.9 perTrajectoryBestScore
      "terminalScore": <float | null>           // §12A.9 perTrajectoryTerminalScore
    },
    ...
  ],
  "failedTrajectories": [       // SEED_FAILED per §12A.8 — drop-and-continue
    {
      "candidateSeed": <int>,
      "unfilledDemand": [...]   // _to_jsonable(UnsatisfiedResult.unfilledDemand)
    },
    ...
  ],
  "aggregateAttempts": <int>,                    // sum of placementAttempts across this task's trajectories
  "aggregateRejectionsByReason": {<code>: <int>} // sum of ruleEngineRejectionsByReason across this task's trajectories
  // Optional fields, present only when applicable (omitted in the common case
  // for minimal orchestrator-side parsing surface area):
  // "trajectoryExceptions": [   // present iff any trajectory raised an
                                 // unhandled exception inside _run_one_trajectory;
                                 // the exception is contained per §12A.8 drop-and-continue
                                 // — the other trajectories still surface in
                                 // candidates / failedTrajectories.
  //   {
  //     "candidateSeed": <int>,
  //     "exceptionType": "<class name>",
  //     "exceptionMessage": "<repr>"
  //   }
  // ]
  // "parserRejection": {        // present iff parser rejected the snapshot
                                 // entirely; in this case candidates +
                                 // failedTrajectories are both empty (this task
                                 // contributes 0 to K' per §8.7 partial-failure
                                 // tolerance).
  //   "issueCount": <int>,
  //   "issues": [{"severity": ..., "code": ..., "message": ...}, ...]
  // }
  // "workerError": {            // present iff worker_main itself raised — wrapping
                                 // emergency surface so the orchestrator's K'
                                 // aggregation has structured input even when
                                 // the worker fails outside trajectory execution
  //   "exceptionType": "<class name>",
  //   "exceptionMessage": "<repr>"
  // }
}
```

The worker (`python/rostermonster_service/worker.py`) hardcodes the FW-0037 elbow tuple (`L=50`, `idleThreshold=3500`, `swapProbability=0.5`) per `docs/delivery_plan.md` §9 M7 C2 Task 2D + the M7 architecture lock at D-0070 — this is the M7 production LAHC operating point. Each Batch task runs `multiprocessing.Pool(8)` over its assigned trajectories, where each pool child invokes `solve(strategyId=LAHC, terminationBounds=K=1, _candidate_seeds=[its_one_seed], lahcParams=<FW-0037 tuple>, ...)` per the M7 C2 Task 2C `_candidate_seeds` private override.

## 9) Request shape
Proposed in this checkpoint (normative):

### 9.1 HTTP method + path
`POST /compute` (single endpoint per §6.2).

### 9.2 Headers
- `Authorization: Bearer <id-token>` (required per §7).
- `Content-Type: application/json` (required).
- Other headers are implementation-slice; the service MUST NOT depend on operator-supplied custom headers for behavior.

### 9.3 Body schema
JSON object with the following top-level fields:

```json
{
  "snapshot": { ...full snapshot per docs/snapshot_contract.md §5..§11... },
  "operatorEmail": "operator@example.com",
  "optionalConfig": {
    "solverStrategy": "LAHC",
    "lahcParams": { "L": 50, "idleThreshold": 3500, "swapProbability": 0.5 },
    "maxCandidates": 50,
    "seed": 20260430
  }
}
```

Concrete properties:
1. **`snapshot`** *(required)*: A full Snapshot per `docs/snapshot_contract.md` §5..§11, including all sections required by the parser/normalizer for ingestion. Same shape as the JSON file the bound shim's existing "Export Snapshot" menu produces — no schema divergence between local-mode (file-on-disk) and cloud-mode (in-request-body) extraction outputs. The bound shim assembles this in-memory via the central library's snapshot-builder API per D-0052.
2. **`operatorEmail`** *(required for LAHC strategy path; optional for SRB)*: The operator's email address sourced from `Session.getActiveUser().getEmail()` in the bound shim per **D-0071 sub-decision 6** (M7 C3 amendment). Used by the Cloud Batch finalizer for the always-email-on-failure path per §10A.7 + as the recipient of the operator-facing success notification email. MUST match the same authenticated operator's email (the Flask handler validates `operatorEmail` against the `email` claim from §7.1's OIDC token validation; mismatch returns `INPUT_ERROR` with code `OPERATOR_EMAIL_MISMATCH`). On the SRB strategy path this field is optional and ignored (SRB stays synchronous; no callback / no email needed). For LAHC paths under D-0071 the field is required because the finalizer task is the only surface that can email the operator after the front-door `SUBMITTED` response returns. Empty / missing on a LAHC request → `INPUT_ERROR` with code `OPERATOR_EMAIL_REQUIRED`.
3. **`optionalConfig`** *(optional)*: An object overriding compute defaults. First-release recognized fields:
   - `solverStrategy` *(string, optional)*: Solver strategy enum per `docs/solver_contract.md` §11.2 — `"SEEDED_RANDOM_BLIND"` or `"LAHC"` (M7 C3 amendment per **D-0070 + D-0071**). When omitted, the service falls back to `"SEEDED_RANDOM_BLIND"` (the M4-baseline strategy; preserves M4 client compatibility). When `"LAHC"` is passed, the service dispatches to the Cloud Batch async path per §8.7 + §10.6 — Cloud Run returns `SUBMITTED` immediately and the finalizer task POSTs to the launcher Web App callback per §10A. **Per D-0071 sub-decision 13**, the bound shim's operator menu `Roster Monster → Solve Roster` always passes `"LAHC"` (bound shim is LAHC-only on the operator path until FW-0035 parity work — SRB stays accessible via the local CLI for maintainer dev work). The maintainer-only `/compute-lahc-test` debug route (§6.2) also defaults to `"LAHC"` since its purpose is to exercise the LAHC path.
   - `lahcParams` *(object, optional, only used when `solverStrategy="LAHC"`)*: LAHC algorithm parameters per `docs/solver_contract.md` §12A.6 — `{L: int, idleThreshold: int, swapProbability: float}`. When omitted, the service uses the FW-0037 elbow tuple defaults pinned in M7 (`L=50`, `idleThreshold=3500`, `swapProbability=0.5`) per §8.7 worker hardcoding. Passing this field is additive; the service falls back to the worker-hardcoded values when omitted. M7 C4 operator path SHOULD omit this field (defaults are already the M7 production tuple); maintainer-only experiments may override.
   - `maxCandidates` *(integer, optional)*: number of candidates the solver enumerates before selector cascade. When omitted, the service falls back to the local CLI's `_DEFAULT_MAX_CANDIDATES` constant in `python/rostermonster/run.py` (currently `32`). Tying both surfaces to the same Python constant guarantees that an operator running the CLI and the bound shim with no `maxCandidates` override gets the same candidate-count budget on both surfaces.
   - `seed` *(integer, optional)*: random seed for the solver's `SEEDED_RANDOM_BLIND` strategy (or the master seed for LAHC's K-trajectory seed derivation per `docs/solver_contract.md` §12A.10). When omitted, the service picks a fresh random seed per invocation via `random.randint(0, 2**31 - 1)` per `docs/decision_log.md` D-0053. The chosen seed is recorded in `RunEnvelope.seed` (per `docs/selector_contract.md` v2 §9 item 3) so the operator can reproduce a specific run by reading the seed off the writeback tab's traceability footer (per `docs/writeback_contract.md` §16) and replaying via `optionalConfig.seed=<that-value>`. Both surfaces share this random-default behavior — same shared compute core per D-0050. **Parity precondition refined**: D-0050's "byte-identical at same input" guarantee holds when `optionalConfig.seed` is explicitly set to the same value across both surfaces; with omitted seed each surface picks its own random seed and envelopes differ, which is expected operator-facing behavior (each invocation is a fresh attempt at the search space).
   - Future config fields: additive only. New optional fields MAY be added without a contract version bump (§11). Removing or renaming fields is a contract bump.

### 9.4 Snapshot identity propagation
The snapshot's `metadata.sourceSpreadsheetId` + `metadata.sourceTabName` MUST conform to `docs/selector_contract.md` v2 §9 item 3 (required `runEnvelope` fields). The cloud service propagates these through the run envelope unchanged so the writeback step that consumes the response can target the correct source spreadsheet per `docs/writeback_contract.md` §18.

### 9.5 Body size
First-release ICU/HD scale: snapshot ~290 KB, optional config ~50 bytes. Cloud Run's per-request body limit is 32 MiB on HTTP/1.1 (hard, not configurable); HTTP/2 streaming has different rules but the bound shim's `UrlFetchApp.fetch` is HTTP/1.1, so the practical ceiling is 32 MiB. No first-release size concern. If snapshot scope ever grows past that ceiling, the response shape and transport mechanic both need rethinking — `UrlFetchApp` returns `413 Payload Too Large` rather than chunking, so the contract would need a fallback mechanic (multipart upload, snapshot-via-Drive-ID, or async job submission per FW-0027).

## 10) Response shape
Proposed in this checkpoint (normative):

The service ALWAYS responds with HTTP `200 OK` carrying a structured JSON envelope (the only exceptions are auth failures handled by Cloud Run before the service runs, and infrastructure-level errors like Cloud Run cold-start failures — see §10.5). Application-level errors are surfaced via the response envelope's `state` field, NOT via HTTP status codes. This mirrors the writeback library's 3-state diagnostic discipline per `docs/writeback_contract.md` §17.

### 10.1 Response envelope
```json
{
  "state": "OK" | "UNSATISFIED" | "INPUT_ERROR" | "COMPUTE_ERROR",
  "writebackEnvelope": { ...wrapper envelope per docs/decision_log.md D-0045... } | null,
  "error": { "code": "...", "message": "..." } | null
}
```

Top-level fields:
1. **`state`** *(required)*: enumerated string discriminant. One of:
   - `"OK"` — compute succeeded; `writebackEnvelope` is populated; `error` is null.
   - `"UNSATISFIED"` — solver returned an `UnsatisfiedResultEnvelope` (no allocation possible); `writebackEnvelope` is populated with the `FinalResultEnvelope` carrying the failure-branch result; `error` is null. Bound shim still calls `RMLib.applyWriteback(envelope)` to render the failure-branch tab per `docs/writeback_contract.md` §13.
   - `"INPUT_ERROR"` — request failed pre-compute validation (missing required snapshot fields, malformed JSON, invalid optional config). `writebackEnvelope` is null; `error` is populated.
   - `"COMPUTE_ERROR"` — pre-compute validation passed but the compute path itself raised an unexpected exception. `writebackEnvelope` is null; `error` is populated.
2. **`writebackEnvelope`** *(nullable)*: when `state ∈ {"OK", "UNSATISFIED"}`, this is the same wrapper envelope shape the local CLI emits per D-0045 + writeback `§9`. The bound shim hands this directly to `RMLib.applyWriteback(envelope)` without any reshape. When `state ∈ {"INPUT_ERROR", "COMPUTE_ERROR"}`, this is null.
3. **`error`** *(nullable)*: when `state ∈ {"INPUT_ERROR", "COMPUTE_ERROR"}`, this carries diagnostic content:
   - `code` *(string, machine-readable)*: stable enum value the bound shim can dispatch on. First-release values: `INVALID_SNAPSHOT_SHAPE`, `INVALID_OPTIONAL_CONFIG`, `PARSER_REJECTED`, `COMPUTE_EXCEPTION`. Additive — new codes MAY be added without contract bump.
   - `message` *(string, human-readable)*: a short message safe to surface in the bound shim's failure dialog. Includes enough context for the operator to know what to fix (or that they should contact the maintainer); does NOT include stack traces or internal-only diagnostic content.
   When `state = "OK" | "UNSATISFIED"`, this is null.

### 10.2 Branch-on-state at the consumer
The bound shim's "Solve Roster" handler dispatches on `response.state`:
- `"OK"` → success toast → invoke `RMLib.applyWriteback(response.writebackEnvelope)` → success dialog with new-tab link (per `docs/writeback_contract.md` §17.1).
- `"UNSATISFIED"` → distinct "no allocation possible" toast → invoke `RMLib.applyWriteback(response.writebackEnvelope)` to render the failure-branch tab → inform operator the failure tab carries details (per `docs/writeback_contract.md` §17.2).
- `"INPUT_ERROR" | "COMPUTE_ERROR"` → error dialog showing `error.message` → no writeback fires → operator can retry after addressing the root cause (or contact maintainer if the error indicates a defect).

### 10.3 No partial-state response
A response MUST satisfy exactly one of:
- `state = "OK"` with non-null `writebackEnvelope` carrying an `AllocationResult` and null `error`,
- `state = "UNSATISFIED"` with non-null `writebackEnvelope` carrying an `UnsatisfiedResultEnvelope` and null `error`,
- `state ∈ {"INPUT_ERROR", "COMPUTE_ERROR"}` with null `writebackEnvelope` and non-null `error`.

The service MUST NOT emit responses where `state = "OK"` carries an `UnsatisfiedResultEnvelope` (those are `"UNSATISFIED"`) or where `error` and `writebackEnvelope` are both populated. This invariant is enforced server-side; bound shim assumes it without re-validating.

### 10.4 Determinism
The service is deterministic in the same sense the local CLI is per `docs/selector_contract.md` §18: same `(snapshot, optionalConfig)` input produces byte-identical `writebackEnvelope` across re-runs **when `optionalConfig.seed` is explicitly set**. With omitted `optionalConfig.seed`, each invocation picks a fresh random seed per `docs/decision_log.md` D-0053; outputs differ across invocations and that is expected behavior (each invocation is a fresh attempt at the search space). The chosen seed is always recorded in `runEnvelope.seed` so the operator can replay any run by passing that seed back as an explicit override. The cloud service inherits this guarantee by sharing the compute core with the local CLI per D-0050; no separate determinism guarantee is offered.

### 10.5 Infrastructure-level errors
Errors that prevent the service code from running (Cloud Run cold-start failure, IAM rejection, network partition) surface to the bound shim as `UrlFetchApp.fetch()` exceptions or non-200 HTTP statuses, NOT through the response envelope. The bound shim catches these at the `UrlFetchApp` layer and surfaces them through the same error-dialog path as `state = "COMPUTE_ERROR"` (with a different `code` so the operator-facing message can be tailored). Specific codes the bound shim MAY emit on infrastructure errors:
- `INFRASTRUCTURE_AUTH_REJECTED` — Cloud Run returned 401/403.
- `INFRASTRUCTURE_TIMEOUT` — `UrlFetchApp.fetch()` exceeded its timeout window.
- `INFRASTRUCTURE_UNREACHABLE` — DNS / network failure preventing the request from completing.
These are emitted by the bound shim as a side surface; the service contract doesn't pin them since the service never participates in the path.

### 10.6 SUBMITTED state (M7 C4 onward, LAHC strategy path) — per D-0071
Pinned in M7 C3 Task 1 (2026-05-11) per `docs/decision_log.md` D-0071. When `optionalConfig.solverStrategy = "LAHC"` (M7 C3 amendment), the Cloud Run Service responds **synchronously** with a SUBMITTED envelope after Cloud Batch job submission returns successfully (typically 3-5s end-to-end including OIDC validation + Cloud Batch `submitJob` round-trip):

```json
{
  "state": "SUBMITTED",
  "writebackEnvelope": null,
  "error": null,
  "submission": {
    "batchJobName": "projects/{project_number}/locations/asia-southeast1/jobs/{job_id}",
    "jobId": "<the Cloud Batch job id, distinct from runEnvelope.runId>",
    "runId": "<the runEnvelope.runId for this run>"
  }
}
```

Top-level field additions to §10.1's response envelope shape:
1. **`state = "SUBMITTED"`** — new enum value. Joins `OK` / `UNSATISFIED` / `INPUT_ERROR` / `COMPUTE_ERROR`. Indicates the service has accepted the request, validated input, and successfully submitted the Cloud Batch job; the actual compute outcome will arrive later via the §10A async-callback path. **Additive — no contract version bump** per §11.1's enum-bump rule. v1-targeted clients (SRB-only operators) never see `SUBMITTED` because SRB stays synchronous; the new value only fires on the LAHC path.
2. **`submission`** *(present when `state = "SUBMITTED"`, null otherwise)* — diagnostic surface carrying the batch job identity. `batchJobName` is the full Cloud Batch job resource name (useful for `gcloud batch jobs describe`); `jobId` is the short id (useful for callback correlation); `runId` is the run envelope id (useful for cross-referencing the callback's writeback envelope).

Bound shim dispatch on `state = "SUBMITTED"` (M7 C4 implementation per D-0071 sub-decision 9):
- Show an in-flight toast: "Roster solve submitted. You'll receive an email when complete (typically 5-10 minutes)."
- Return immediately to the operator (the toast is non-blocking). The actual writeback + analyzer tabs land asynchronously when the launcher Web App receives the §10A callback POST.

The SUBMITTED-state response semantically aligns with §10.3's no-partial-state invariant: `writebackEnvelope` is null (compute hasn't run yet) + `error` is null (no failure) + `submission` is non-null. INPUT_ERROR / COMPUTE_ERROR cases on the LAHC front-door path still emit per §10.1 (no SUBMITTED → no callback expected — operator sees the error immediately in the bound shim dialog).

## 10A) Async callback contract (LAHC strategy path, M7 C4 onward) — per D-0071
Pinned in M7 C3 Task 1 (2026-05-11) per `docs/decision_log.md` D-0071. **A new boundary** between the Cloud Batch finalizer task and the launcher Web App — distinct from §9/§10's bound-shim → Cloud-Run boundary. The finalizer task POSTs the final envelope to the launcher Web App after Cloud Batch completes (whether worker tasks succeeded, partially-failed, or fully failed; the finalizer runs always per §8.7 + D-0071 sub-decision 11).

### 10A.1 Boundary position
- **Upstream** (caller): Cloud Batch finalizer task running on a `c3-highcpu-8` VM in `asia-southeast1` per §8.7. Invoked as the second task group in the Cloud Batch job (single task, runs after all worker tasks per the `SUCCEEDED_OR_FAILED` dependency).
- **Boundary**: HTTPS POST request from the finalizer task's `requests.post(...)` to the launcher Web App's `/exec?action=async-render-callback` endpoint (existing launcher Web App URL per `docs/decision_log.md` D-0046; new action handler added at M7 C4 per D-0071 sub-decision 3).
- **Downstream** (callee): launcher Web App in `apps_script/launcher/src/` adds a new `async-render-callback` action handler that invokes `RMLib.applyWriteback(envelope) + RMLib.renderAnalysis(envelope)` from the central library against the callback's POSTed envelope.

### 10A.2 Why "B-prime"
Per D-0071 sub-decision 3, the architecture name "B-prime" denotes the callback-delivery shape chosen over alternative options considered (A: in-Apps-Script polling; B: callback into the bound shim; B-prime: callback into the launcher Web App). B-prime was chosen because the launcher Web App is already operator-owned + already exposes a Web App URL surface (the existing writeback file-upload route at `/exec?action=writeback` per D-0046) — reusing it as the callback target requires zero new Apps Script projects, zero new Drive-level shares, zero new credential surfaces. The bound shim, by contrast, has no public Web App URL — exposing one for callbacks would require a new deployment + new OAuth scopes + new operator share. B-prime delivers without those costs.

### 10A.3 HTTP method + path
`POST <launcher-web-app-url>?action=async-render-callback&runId=<runId>&attemptId=<attemptId>` per D-0071 sub-decision 3.
- `<launcher-web-app-url>` is the existing launcher's deployed Web App URL (the same `/exec` URL used for `?action=writeback` per D-0046). The Cloud Run Service propagates this URL into the Cloud Batch job spec as an env var on the finalizer task; the finalizer reads it at runtime.
- `runId` query param: the `runEnvelope.runId` per `docs/selector_contract.md` v2 §9 — used by the launcher to correlate the callback with the operator's pending request (and for logging / audit).
- `attemptId` query param: echoes the §8.7 per-call `attemptId` — used by the launcher to detect duplicate callbacks (idempotency surface, see §10A.6).

### 10A.4 Headers
- `Content-Type: application/json` (required).
- **No `Authorization` header.** The OIDC ID token MUST be carried in the POST body's `idToken` field per §10A.5 + §10A.6. Apps Script Web App handlers (`doPost(e)`) do NOT expose HTTP request headers to the Apps Script code — the official event object lists `e.parameter` / `e.parameters` / `e.queryString` / `e.contextPath` / `e.pathInfo` / `e.postData` only, with no header surface. An `Authorization: Bearer` header would arrive at the Apps Script runtime but the handler could not read or validate it, making every legitimate callback either un-validatable (if the handler ignored auth) or rejected (if it required a surface it cannot read). The body-field approach is the only auth-token surface a Web App handler can validate.

### 10A.5 Authentication
Per **D-0071 sub-decision 4** the callback uses **GCP ID-token auth** (NOT a shared secret, NOT an HMAC signature). The token rides in the POST body's `idToken` field per §10A.4 — Apps Script Web App handlers cannot read request headers, so a header-based surface would not work.

- Finalizer task generates a Google OIDC ID token via the metadata server's `instance/service-accounts/default/identity?audience=<launcher-web-app-url>` endpoint (Cloud Batch VMs run as the default Compute Engine SA per §8.7; the metadata server is available on the VM by default). The token's `aud` claim is the launcher Web App URL.
- Finalizer puts the token in the POST body's `idToken` field (the body schema in §10A.6 lists `idToken` as the FIRST top-level field).
- Launcher Web App's `async-render-callback` handler reads `e.postData.contents`, JSON-parses, and extracts `body.idToken` BEFORE doing any other field validation. The handler then validates the token by calling Google's tokeninfo endpoint (`https://oauth2.googleapis.com/tokeninfo?id_token=<token>` via `UrlFetchApp.fetch(...)`) — the same pattern the existing launcher routes use for external HTTPS calls. Required claims:
  - `aud` MUST match the launcher Web App URL (the token is unforgeable for any other audience).
  - `email` MUST equal the Cloud Batch finalizer SA email (`{project_number}-compute@developer.gserviceaccount.com`) — confirms the caller is the legitimate finalizer task, not an arbitrary GCP identity. Email is hardcoded in the launcher (no env var; SA email is stable for the project).
  - `email_verified` MUST be true.
  - The token's `exp` claim MUST not be in the past (tokeninfo enforces this server-side; the launcher relies on tokeninfo's expiry check rather than verifying locally).
- Auth failures return HTTP 401 with a body `{"state": "AUTH_REJECTED"}` and the launcher logs the failed attempt. The finalizer treats 401 as terminal (does NOT retry — token issue indicates a config drift, not transience).
- The `idToken` field MUST be stripped from the body before the launcher logs / persists the callback payload — the token grants access to the launcher URL for ~1h and should not survive in logs.

Per D-0071 sub-decision 4 alternatives explicitly rejected:
- **Shared secret in env var**: rejected as a credential surface (Apps Script Script Properties is a secret storage but introduces operational ceremony for rotation + accidental leakage risk).
- **HMAC over body**: rejected because the body carries `writebackEnvelope` (~few-hundred-KB potentially) — HMAC computation + verification is fine technically but adds CPU + adds a secret-key rotation surface. GCP ID-token-in-body is the least-new-credential-surface option that an Apps Script Web App handler can actually validate.
- **`Authorization` header**: technically the standard for OIDC bearer tokens BUT Apps Script's `doPost(e)` event object has no header field — see §10A.4.

### 10A.6 Body schema
```json
{
  "idToken": "<Google OIDC ID token from the finalizer's metadata-server identity endpoint>",
  "schemaVersion": 1,
  "runId": "<echoes the query param>",
  "attemptId": "<echoes the query param>",
  "state": "OK" | "UNSATISFIED" | "COMPUTE_ERROR",
  "writebackEnvelope": { ...wrapper envelope per D-0045 + writeback §9... } | null,
  "analyzerOutput": { ...AnalyzerOutput per docs/analysis_contract.md... } | null,
  "error": { "code": "...", "message": "..." } | null,
  "diagnostics": {
    "kApproved": <int>,
    "kPrime": <int>,
    "droppedCount": <int>,
    "wallTimeSeconds": <float>,
    "batchJobName": "<full Cloud Batch job resource name>"
  }
}
```

Top-level fields:
1. **`idToken`** *(required, string)* — the OIDC ID token the finalizer minted via the Cloud Batch VM's metadata server (audience = launcher Web App URL). Carries the auth surface per §10A.5 — Apps Script Web App handlers cannot read HTTP headers, so the token rides in the body. The handler reads and validates this field BEFORE inspecting any other body content. The launcher MUST strip this field from the body before any logging / persistence.
2. **`schemaVersion`** *(required, integer)* — currently `1`. Bumps if the callback envelope's required-fields set changes (separate from the §11 contract version, which governs the §9 + §10 boundary).
3. **`runId`** *(required, string)* — echoes the query param. Launcher uses it for cross-referencing with the operator's pending request.
4. **`attemptId`** *(required, string)* — echoes the query param. Launcher uses it for idempotent dispatch (see "idempotency" below).
5. **`state`** *(required, enum string)* — `"OK"` / `"UNSATISFIED"` / `"COMPUTE_ERROR"`. Same semantics as §10.1's response states minus `SUBMITTED` (the front-door already returned that) and minus `INPUT_ERROR` (input validation runs synchronously at the front door; if it fails the finalizer never runs). `COMPUTE_ERROR` here covers post-submission failures: worker tasks failed entirely (K'=0), aggregation raised, analyzer raised, or the finalizer itself caught an unhandled exception.
6. **`writebackEnvelope`** *(nullable)* — present when `state ∈ {"OK", "UNSATISFIED"}`. Same shape as §10.1's `writebackEnvelope`; the launcher hands directly to `RMLib.applyWriteback(envelope)`.
7. **`analyzerOutput`** *(nullable)* — present when `state = "OK"` (per D-0071 sub-decision 12 + the §10.6 OK-only convention). Same shape as `docs/analysis_contract.md` §4 `AnalyzerOutput`; the launcher hands directly to `RMLib.renderAnalysis(envelope, analyzerOutput, sourceSpreadsheetId)`. Null when `state ∈ {"UNSATISFIED", "COMPUTE_ERROR"}` (analyzer doesn't run on failure paths).
8. **`error`** *(nullable)* — present when `state = "COMPUTE_ERROR"`. Same shape as §10.1's `error`. Carries machine-readable `code` + human-readable `message`. First-release codes: `WORKER_ALL_FAILED` (K'=0; all worker tasks failed entirely), `AGGREGATION_EXCEPTION`, `ANALYZER_EXCEPTION`, `FINALIZER_EXCEPTION`.
9. **`diagnostics`** *(required)* — fixed object carrying observability fields surfaced in the operator-facing email + the launcher's audit log:
   - `kApproved` *(integer)* — the K_approved value the orchestrator submitted (per §8.7 sub-decision 7 derivation).
   - `kPrime` *(integer)* — the actual K' after partial-failure aggregation (per §8.7's primary K' definition). `kPrime == kApproved` is the all-success case; `kPrime < kApproved` indicates partial success.
   - `droppedCount` *(integer)* — derived `kApproved - kPrime`.
   - `wallTimeSeconds` *(float)* — total wall time from front-door `submitJob` returning to finalizer's callback POST. Used by the operator-facing email for the "took N minutes" line.
   - `batchJobName` *(string)* — full Cloud Batch job resource name. Used by maintainer audit + by the operator's email's "log link" if surfaced.

**Idempotency:** the launcher tracks (`runId`, `attemptId`) tuples in a short-lived Properties Service entry; a duplicate callback for the same tuple returns HTTP 200 + body `{"state": "DUPLICATE_IGNORED"}` and does NOT re-invoke writeback / re-render / re-email. This protects against the finalizer's retry-on-5xx behavior (§10A.7) double-firing the operator-facing surface.

### 10A.7 Retry behavior + always-email-on-failure
Per **D-0071 sub-decision 10**:

**Finalizer-side retry on callback POST failures:**
- On 2xx response: finalizer logs success + exits (Cloud Batch task completes).
- On 5xx response: finalizer retries up to 3 times with exponential backoff (2s, 4s, 8s per D-0071 sub-decision 10). Failures after the third retry are treated as terminal "launcher unreachable" — finalizer logs the failure + emails the operator with the failure-path email per §10A.7's always-email-on-failure, then exits cleanly.
- On 401: terminal, no retry (token issue indicates config drift).
- On 4xx (other): terminal, no retry (request shape issue → maintainer-visible logs).

**Always-email-on-failure (D-0071 sub-decision 10):**
The finalizer **always emails the operator on any failure path** — `state = "COMPUTE_ERROR"`, AND launcher-unreachable after retries, AND callback returned a 4xx other than 401. Email content:
- **Subject**: `[RosterMonsterV2] Roster solve failed — <error.code or 'CALLBACK_UNREACHABLE'>`.
- **Body**: short human-readable explanation + the `runId` + `attemptId` + `wallTimeSeconds` + a link to the launcher's "what to do next" page (or a maintainer contact line if the launcher itself is the failure surface).
- **Attachment**: the full `AnalyzerOutput` JSON when `state = "OK"` succeeded but the callback POST failed (so the operator can still inspect the analysis offline). Empty when no analyzer output exists (state ∈ {UNSATISFIED, COMPUTE_ERROR}). Max attachment size capped by Gmail's 25 MB limit; AnalyzerOutput is typically ~50-200 KB so this is comfortable.

**Success notification email (D-0071 sub-decision 10, success path):**
The finalizer also emails the operator on `state = "OK"` (per the always-on framing). Subject: `[RosterMonsterV2] Roster solve complete — runId <short-id>`. Body: short summary + link to the spreadsheet (sourced from `snapshot.metadata.sourceSpreadsheetId`). No attachment on success — the analyzer output is already rendered into the spreadsheet via the callback path.

**Operator email source (D-0071 sub-decision 6):** `operatorEmail` from §9.3's required input. Finalizer uses this address; does NOT introspect tokens or session state at finalizer time (finalizer task runs on a Cloud Batch VM with no Apps Script session context).

### 10A.8 Versioning
Independent from the §11 contract version. The callback envelope carries its own `schemaVersion: 1` per §10A.6. Bump rules mirror §11.1's spirit (additive optional fields don't bump; required-field changes bump). The launcher Web App MUST dispatch on `schemaVersion` to remain forward-compatible with future bumps.

### 10A.9 Out-of-scope (10A)
- Polling-based callback (the operator's bound shim does NOT poll Cloud Run for status; the email is the sole "I'm done" surface for the operator).
- Per-operator callback URL routing (single launcher Web App URL is the global callback target; operator scoping is via the `email` claim + `operatorEmail` field, not URL routing).
- Synchronous-replay fallback (if the launcher is unreachable, there is no "re-submit + wait sync" fallback; operator is emailed + can re-trigger from the bound shim manually).
- Finalizer-task-crash watchdog (if the finalizer task itself crashes before reaching either the callback POST or the failure email, the operator is silently in the dark — this is the FW-0039 accepted gap per D-0071 sub-decision 17).

## 11) Schema versioning
Proposed in this checkpoint (normative):

The contract carries `contractVersion: 1` per §2.

### 11.1 Bump rule
Bump `contractVersion`:
- when the request body's required-fields set changes in a way a v1-targeted client would notice (for example, removing the `snapshot` field, requiring a new top-level field besides `snapshot`/`optionalConfig`),
- when the response envelope's `state` enum gains a new value a v1-targeted client cannot dispatch (or when an existing value changes semantics),
- when the response envelope's required-fields set changes (for example, adding a required sibling field at the top level),
- when the auth mechanism changes (for example, moving from IAM-based to OAuth-token-based or shared-secret-based),
- when determinism or idempotency guarantees change.

Do **not** bump:
- for additive `optionalConfig` fields that v1-targeted clients can omit,
- for additive `error.code` enum values that v1-targeted clients can fall back to a generic dispatch on (§10.1),
- for additive `writebackEnvelope` content that propagates from upstream contracts (e.g., new `runEnvelope` fields per `docs/selector_contract.md` §16.3),
- for wording, formatting, or example clarifications that don't change behavior.

## 12) Idempotency
Proposed in this checkpoint (normative):

The service is **stateless** (§6.3) and **deterministic** (§10.4). Two identical requests produce identical responses; the service does NOT internally deduplicate, retry, or cache. Client-side retry behavior is the bound shim's responsibility; first-release bound shim does NOT auto-retry on transient failures (operator manually re-invokes the menu if needed). The writeback step's existing idempotency stance per `docs/writeback_contract.md` §15 (always-new-tab, operator-agency, no runId-skip) is unchanged by the cloud-mode invocation path — operator clicks "Solve Roster" twice → two writeback tabs → operator manually deletes the redundant one if they want.

## 13) Determinism
Proposed in this checkpoint (normative):

Cloud-mode runs and local-mode runs at the same `(snapshot, optionalConfig)` produce byte-identical wrapper envelopes **when `optionalConfig.seed` is explicitly set to the same value across both surfaces**. With omitted seed, each surface picks its own random seed per `docs/decision_log.md` D-0053; envelopes differ. This is the intended operator-facing behavior (each "Solve Roster" click attempts a fresh point in the search space). The chosen seed is recorded in `runEnvelope.seed` on every run so the operator can pin any roster by replaying with that seed value. D-0050's shared-compute-core architecture guarantees that with the same explicit seed both invocation paths reach the same Python compute code with the same inputs and produce the same output. Maintainer-side solver-strategy experiments performed via the local CLI with explicit seeds are guaranteed reproducible in the cloud, and any cloud-mode defect is reproducible from the local CLI by reading the seed off the run envelope and passing it via `--seed`.

The only sources of non-determinism explicitly allowed:
- The response's HTTP-level metadata (timing headers, server-region headers, etc.) is non-deterministic by Cloud Run nature — these are NOT part of the contract surface.
- The Cloud Run service's logs / observability surface is non-deterministic — also NOT part of the contract surface.

The contract's determinism guarantee is bytes-of-`writebackEnvelope`-only.

## 14) Consistency with adjacent contracts
Repo-settled alignments:
- Consistent with `docs/decision_log.md` D-0017 / D-0018: cloud compute is Python-side; Apps Script is the adapter layer.
- Consistent with `docs/decision_log.md` D-0023: bound shim's identity token mechanism reuses operator-account auth (no service account, no shared secret). The cloud invocation path adds three explicit manifest scopes on the bound shim per §7.3 (`script.external_request`, `openid`, `userinfo.email`) — these are surfaces the existing operator-account-auth posture already accommodates; the operator-account discipline itself is unchanged.
- Consistent with `docs/selector_contract.md` v2 §9 item 3: snapshot's `sourceSpreadsheetId` + `sourceTabName` propagate through the run envelope into the response's `writebackEnvelope`.
- Consistent with `docs/writeback_contract.md` §6.2 + §9: response's `writebackEnvelope` matches writeback contract's input shape; bound shim hands it directly to `RMLib.applyWriteback(envelope)` without reshape.
- Consistent with `docs/writeback_contract.md` §17: the response's `state` field semantically aligns with writeback's 3-state diagnostic — `"OK"` / `"UNSATISFIED"` / `"INPUT_ERROR"` / `"COMPUTE_ERROR"` map onto writeback's `SUCCESS` / `FAILED` / `RUNTIME_ERROR` (with the cloud side splitting `RUNTIME_ERROR` into pre-compute vs in-compute branches for diagnostic clarity).
- Consistent with `docs/snapshot_contract.md` §5..§11: the request body's `snapshot` field carries the full snapshot shape that the parser expects, no abridgement.
- Consistent with `docs/selector_contract.md` §18: cloud-mode determinism is explicitly inherited from selector-side determinism.

## 15) Explicitly out of scope
The following are explicitly NOT pinned by this contract:
- The Apps Script side's bound shim menu UX (toast styling, dialog wording, progress indicator design) — implementation-slice for M4 C1 Phase 2 + M7 C4 (the SUBMITTED-state in-flight toast for the async LAHC path per §10.6 + D-0071 sub-decision 9).
- The Python compute internals (parser/solver/scorer/selector contracts govern those).
- The Cloud Run deployment's CI/CD pipeline, monitoring dashboards, alerting policies — operational concerns deferred to FW-0028 (observability) when concrete drivers surface.
- ~~Asynchronous compute mode (job queues, worker pools, callbacks) — deferred to FW-0027 (parallel operational search).~~ **Updated at M7 C3 Task 1 (2026-05-11) per D-0071: async compute mode IS pinned by this contract for the LAHC strategy path per §8.7 finalizer task group + §10.6 SUBMITTED state + §10A async-callback contract.** FW-0027 absorbed into M7 C3+C4 per D-0071. The SRB strategy path remains synchronous per §9 / §10 (unchanged from M4 C1 framing).
- Any operational rate-limiting beyond Cloud Run's `max-instances=5` cap — first-release pilot doesn't need it. Concurrent-rejection by spreadsheet ID (§8.7) is NOT a rate-limit — it's a duplicate-prevention surface.
- The exact wire-level JSON formatting (key ordering, whitespace, Unicode normalization) — request/response semantics are pinned but byte-level layout is implementation-slice.
- The local CLI's behavior — governed by the existing `docs/snapshot_adapter_contract.md` §11 and `docs/decision_log.md` D-0047. Local CLI continues to work unchanged; cloud-mode is purely additive to the dual-track architecture.
- The finalizer-task-crash watchdog — the FW-0039 accepted-gap per D-0071 sub-decision 17. If the finalizer task itself crashes before reaching either the callback POST or the failure-email path, the operator's outcome is silent. Mitigations (Cloud Batch task-failure-notification dispatch, separate `finalizer-watchdog` task group, monitoring alert on finalizer-task non-completion, etc.) are explicitly out-of-scope for v1 and revisit-able when an actual silent-failure incident surfaces.

## 16) Current checkpoint status
### Repo-settled in prior docs
- D-0017 / D-0018 (stack split) — lines through every decision touching the boundary.
- D-0040 (browser-download inbound transport) — cloud-mode receives the snapshot in-request-body, NOT via Drive.
- D-0044 / D-0045 (writeback envelope shape + transport) — cloud-mode response carries the same wrapper-envelope shape.
- D-0050 (dual-track architecture) — this contract codifies the HTTP wrapper.
- D-0051 (Cloud Run + IdentityToken auth + consolidated GCP) — this contract pins the auth mechanic on the wire.
- D-0052 (library reorganization) — bound shim's "Solve Roster" handler is the principal client of this service.

### Proposed and adopted in this checkpoint
- §2 contractVersion 1.
- §6 boundary position: bound-shim → Cloud-Run.
- §7 auth: IAM-based, IdentityToken, no public access.
- §8 deployment posture: Cloud Run, asia-southeast1, scale-to-zero, max-5, 5min timeout, Flask container.
- §9 request shape: POST /compute with `{snapshot, optionalConfig?}`.
- §10 response shape: 4-state envelope (`OK` / `UNSATISFIED` / `INPUT_ERROR` / `COMPUTE_ERROR`).
- §11 schema versioning bump rule.
- §12 idempotency stance: stateless service, no auto-retry, writeback contract's idempotency stance unchanged.
- §13 determinism: shared compute core guarantees byte-identical results across local CLI vs cloud.
- §14 consistency with adjacent contracts.
- §15 explicit out-of-scope items.

### Pinned in M7 C2 Task 1 (2026-05-10) per D-0070 + post-D-0070 sequencing conversation
- §6.2 acknowledges **maintainer-only test routes** beyond the operator-facing `POST /compute` endpoint. M7 C2 adds the LAHC Cloud Batch test path. (At M7 C2 lock-time this section said "route is removed when §9 is amended at M7 C3"; **superseded at M7 C3 Task 1 per D-0071 sub-decision 14 — debug route is KEPT** since maintainer-side sync-from-curl invocation is still the simplest smoke-test surface even after operator path moves to async.)
- §8.7 pins the **Cloud Batch posture for the LAHC strategy path**: bucket name `rostermonsterv2-lahc` (asia-southeast1, 90-day lifecycle); GCS object naming convention; Cloud Batch job spec invariants (`c3-highcpu-8`, on-demand, `taskCountPerNode: 1`, per-task `maxRunDuration: 180s` at M7 C2 lock, per-task `maxRetryCount: 1`); orchestrator-side completion deadline 240s implemented as a polling loop + `batch.jobs.cancel` on overrun; IAM additions on the default Compute SA acting as both job creator + Batch task identity (`roles/batch.jobsEditor` project-wide + `roles/batch.agentReporter` project-wide + `roles/iam.serviceAccountUser` on itself + `roles/storage.objectAdmin` bucket-scoped); single-container-image dispatch via `--worker-mode`; partial-failure tolerance with `K'` defined as `sum(len(candidates_per_completed_task))` (source-of-truth, covers task-level failures + per-trajectory §12A.8 seed-construction failures within completed tasks; `dropped_count = K_approved - K'` is the derived diagnostic); GCS-only data path (Drive is NOT a pipeline data path); `candidates_full.json` reframed as OPTIONAL out-of-band maintainer-audit ADDITIVE to D-0070 sub-decision 10's in-pipeline framing — analyzer pass-through still operates on in-memory aggregation; GCS write is fire-and-forget, MUST NOT block operator response. **The M7 C2 lock language for the 180s per-task budget + 240s orchestrator polling deadline is SUPERSEDED at M7 C3 per D-0071 — see the M7 C3 entry below.**
- No `contractVersion` bump (additive deployment-posture pinning per §11.1's bump rule).

### Pinned in M7 C3 Task 1 (2026-05-11) per D-0071 (async architecture decision)
- §6.2 — maintainer-only `/compute-lahc-test` debug route KEPT after operator path goes live (D-0071 sub-decision 14; supersedes M7 C2 lock's "route is removed when §9 is amended" framing).
- §8.4 — request timeout `300s` governs the **SRB strategy path only** going forward. LAHC strategy path no longer blocks on this timeout (front door returns `SUBMITTED` in 3-5s; compute runs in Cloud Batch under a separate 10-min hard cap).
- §8.7 (worker task group) — per-task `maxRunDuration` raised from `180s` → `540s` per D-0071 sub-decision 7 (worker tasks no longer constrained by the sync request budget; the budget room is reclaimed for slow trajectories on real-production rosters).
- §8.7 (finalizer task group) — NEW second task group `taskGroups[1]` added per D-0071 sub-decision 2 + 3 + 12. Single task, `maxRunDuration: 120s` (Batch-level safety net; implementation-slice tunable), `maxRetryCount: 0`, depends on the worker task group via `condition: SUCCEEDED_OR_FAILED` (runs always — D-0071 sub-decision 12). Replaces the orchestrator-side polling loop. **Total wall budget enforced via finalizer's first-action self-check** at 600s elapsed since `RM_SUBMIT_TIMESTAMP_MS` (set by Cloud Run Service at `submitJob` time and passed via the finalizer task's env). Per D-0071 sub-decision 7, Cloud Batch's `Job` schema has no job-level `maxRunDuration` field, so the operational 10-min cap is enforced via the self-check rather than via Batch. Worker maxRunDuration 540s + finalizer self-check at 600s = bounded.
- §8.7 (concurrent rejection) — Cloud Batch job labels `{spreadsheet_id: <normalized>}` attached on every submission per D-0071 sub-decision 8. **Operator email is NOT a label** (emails contain `@` / `.` which fail Cloud Batch label validation `[a-z0-9_-]{1,63}`); spreadsheet-ID label value is normalized (lowercase + non-`[a-z0-9_-]` → `-` + truncate to 63 chars). Orchestrator MUST list in-flight jobs filtered by the normalized label and reject the new request with `INPUT_ERROR` code `CONCURRENT_RUN_REJECTED`. Operator-email-of-in-flight-job for the rejection message is read off the in-flight job's `taskGroups[0].taskSpec.environment.variables.RM_OPERATOR_EMAIL`, NOT from a label.
- §8.7 (orchestrator-side polling deadline) — DEPRECATED for the LAHC path per D-0071. The Cloud Run Service no longer polls Cloud Batch on the LAHC path; it returns `SUBMITTED` immediately and the finalizer handles completion + callback + email. (Pre-D-0071 M7 C2 lock's 240s polling deadline is preserved for cross-reference but does not run on the LAHC path under D-0071.)
- §9.3 — required `operatorEmail` field added for the LAHC strategy path per D-0071 sub-decision 6 (sourced from `Session.getActiveUser().getEmail()` in the bound shim; validated against the OIDC token's `email` claim).
- §9.3 — recognized `optionalConfig` fields extended: `solverStrategy` (enum, optional, defaults to `SEEDED_RANDOM_BLIND`; LAHC dispatches to async Cloud Batch path), `lahcParams` (object, optional, used only when `solverStrategy="LAHC"`; defaults to FW-0037 elbow tuple). Both additive per §11.1's bump rule — no `contractVersion` bump.
- §10.6 — `SUBMITTED` state added to response envelope (additive enum value per §11.1's bump rule — no `contractVersion` bump). LAHC strategy path returns `SUBMITTED` after Cloud Batch `submitJob` returns; the actual outcome lands via the §10A async-callback path. New `submission` field on the envelope carries `{batchJobName, jobId, runId}` for diagnostics.
- §10A — NEW async-callback contract section: pins the boundary between Cloud Batch finalizer task and the launcher Web App. Includes boundary position (Cloud Batch finalizer → launcher Web App `/exec?action=async-render-callback`), GCP ID-token auth per D-0071 sub-decision 4 (NOT shared secret, NOT HMAC, NOT `Authorization` header — Apps Script Web App handlers cannot read request headers; token rides in the POST body's `idToken` field), body schema (idToken first + state + writebackEnvelope + analyzerOutput OK-only + error + diagnostics), retry behavior (3 retries with backoff per D-0071 sub-decision 10), idempotency (launcher tracks `(runId, attemptId)` tuples), always-email-on-failure (D-0071 sub-decision 5 + 10), and the FW-0039 finalizer-crash gap surfaced as accepted-for-v1 (D-0071 sub-decision 17). The callback envelope carries its own `schemaVersion: 1` (independent from the §11 contract version).
- §15 — FW-0027 reference removed from out-of-scope (FW-0027 absorbed into M7 C3+C4 per D-0071). New out-of-scope entry: finalizer-task-crash watchdog (FW-0039 gap accepted-for-v1).
- §16 — this checkpoint-status entry records the amendments.
- No `contractVersion` bump (all changes additive — new `SUBMITTED` enum value + new optional input fields + new boundary section + retained backward-compat for the SRB strategy path).

### Still open / deferred
- ~~Async / queue-based compute mode → FW-0027.~~ **No longer deferred — absorbed into M7 C3+C4 per D-0071 (this contract amendment).** SRB strategy path remains synchronous; LAHC strategy path is async per §10.6 + §10A.
- Observability / structured logging hooks → FW-0028.
- Multi-region deployment, post-pilot scale concerns → revisit with concrete driver.
- Auth model extension to non-Google-account operators → revisit with concrete driver.
- Finalizer-task-crash watchdog (FW-0039) → accepted-gap-for-v1 per D-0071 sub-decision 17; revisit when a concrete silent-failure incident surfaces.
