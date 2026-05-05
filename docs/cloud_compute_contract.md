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
The service exposes exactly one operation in first release: `POST /compute`. No additional endpoints (no `/health`, `/version`, `/extract`, etc.) are pinned by this contract; if Cloud Run requires a health-check path, it MAY be added as an implementation-slice concern. The contract pins only the compute-call behavior.

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
Service-side timeout: 5 minutes. Compute time at the default `_DEFAULT_MAX_CANDIDATES` (currently `32`) is ~50s on the ICU/HD May 2026 fixture; 5min provides comfortable headroom for cold-start + larger overridden config values. The bound shim's `UrlFetchApp.fetch()` inherits Apps Script's per-script-execution 6 min wall clock; the alignment is intentional.

### 8.5 Container
- Base image: `python:3.12-slim` (or compatible — pinned at Dockerfile commit time).
- Dependencies: `flask` + the local `rostermonster` package (installed via `pip install -e python/` or equivalent at build time).
- Build: `gcloud run deploy --source` or `gcloud builds submit` + `gcloud run deploy --image`. CI integration is implementation-slice and not pinned by this contract.

### 8.6 Cold-start expectation
Flask cold start is ~1-2 seconds at the chosen container size. Operator-visible latency at first invocation includes cold-start + compute. If cold-start latency becomes operator-friction, the platform's `min-instances ≥ 1` setting (paid) is the documented mitigation. First release accepts cold start as a tradeoff for scale-to-zero cost savings.

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
  "optionalConfig": {
    "maxCandidates": 50,
    "seed": 20260430
  }
}
```

Concrete properties:
1. **`snapshot`** *(required)*: A full Snapshot per `docs/snapshot_contract.md` §5..§11, including all sections required by the parser/normalizer for ingestion. Same shape as the JSON file the bound shim's existing "Export Snapshot" menu produces — no schema divergence between local-mode (file-on-disk) and cloud-mode (in-request-body) extraction outputs. The bound shim assembles this in-memory via the central library's snapshot-builder API per D-0052.
2. **`optionalConfig`** *(optional)*: An object overriding compute defaults. First-release recognized fields:
   - `maxCandidates` *(integer, optional)*: number of candidates the solver enumerates before selector cascade. When omitted, the service falls back to the local CLI's `_DEFAULT_MAX_CANDIDATES` constant in `python/rostermonster/run.py` (currently `32`). Tying both surfaces to the same Python constant guarantees that an operator running the CLI and the bound shim with no `maxCandidates` override gets the same candidate-count budget on both surfaces.
   - `seed` *(integer, optional)*: random seed for the solver's `SEEDED_RANDOM_BLIND` strategy. When omitted, the service picks a fresh random seed per invocation via `random.randint(0, 2**31 - 1)` per `docs/decision_log.md` D-0053. The chosen seed is recorded in `RunEnvelope.seed` (per `docs/selector_contract.md` v2 §9 item 3) so the operator can reproduce a specific run by reading the seed off the writeback tab's traceability footer (per `docs/writeback_contract.md` §16) and replaying via `optionalConfig.seed=<that-value>`. Both surfaces share this random-default behavior — same shared compute core per D-0050. **Parity precondition refined**: D-0050's "byte-identical at same input" guarantee holds when `optionalConfig.seed` is explicitly set to the same value across both surfaces; with omitted seed each surface picks its own random seed and envelopes differ, which is expected operator-facing behavior (each invocation is a fresh attempt at the search space).
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
- The Apps Script side's bound shim menu UX (toast styling, dialog wording, progress indicator design) — implementation-slice for M4 C1 Phase 2.
- The Python compute internals (parser/solver/scorer/selector contracts govern those).
- The Cloud Run deployment's CI/CD pipeline, monitoring dashboards, alerting policies — operational concerns deferred to FW-0028 (observability) when concrete drivers surface.
- Asynchronous compute mode (job queues, worker pools, callbacks) — deferred to FW-0027 (parallel operational search).
- Any operational rate-limiting beyond Cloud Run's `max-instances=5` cap — first-release pilot doesn't need it.
- The exact wire-level JSON formatting (key ordering, whitespace, Unicode normalization) — request/response semantics are pinned but byte-level layout is implementation-slice.
- The local CLI's behavior — governed by the existing `docs/snapshot_adapter_contract.md` §11 and `docs/decision_log.md` D-0047. Local CLI continues to work unchanged; cloud-mode is purely additive to the dual-track architecture.

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

### Still open / deferred
- Async / queue-based compute mode → FW-0027.
- Observability / structured logging hooks → FW-0028.
- Multi-region deployment, post-pilot scale concerns → revisit with concrete driver.
- Auth model extension to non-Google-account operators → revisit with concrete driver.
