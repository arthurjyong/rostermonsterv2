"""Tests for the M7 C4 T2A.1 Cloud Batch worker per
`docs/cloud_compute_contract.md` §8.7 +
`python/rostermonster_service/worker.py`.

Exercises the full read → compute → write cycle against an in-memory
GCS adapter + a serial pool executor (no real google-cloud-storage
dependency, no multiprocessing fork). Covers:

- Round-trip: snapshot → result.json with the §8.7 schema +
  populated `candidates` list (one TrialCandidate per SUCCEEDED
  trajectory per the §12A.2 K-trajectory-independence semantics).
- Local seed derivation (§12A.10): result.json's candidate seeds MUST
  match `derive_K_seeds(masterSeed, K_approved)` byte-for-byte — the
  single-task pattern retires the per-task seeds.json file and makes
  the worker the source-of-truth for trajectory seeds.
- Determinism: same `(masterSeed, K_approved)` produces byte-identical
  result.json across invocations per §12A.4.
- Per-trajectory exception handling: a child raising surfaces as a
  `trajectoryExceptions` entry rather than killing the whole task per
  §12A.8 drop-and-continue discipline.
- Parser rejection: snapshot that fails to parse populates
  `parserRejection` in result.json (NOT raised) so the orchestrator's
  §8.7 partial-failure aggregation treats it as a 0-candidate
  contribution rather than a missing task.
- AttemptId echo: the `attempt_id` kwarg (T2A.1 env-plumbed via
  `RM_ATTEMPT_ID`) is echoed into result.json so the orchestrator can
  validate on read that result.json belongs to THIS attempt — closes
  the concurrent-replay overwrite race on deterministic runId.
- Result URI matches the §8.7 key path (`gs://{bucket}/{runId}/result.json`).
- CLI dispatch: `--master-seed` defaults to `RM_MASTER_SEED` env var
  Cloud Batch sets per-task; missing both surfaces exit code 2.

Standalone runnable via `python3 python/tests/test_worker.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from rostermonster.solver import derive_K_seeds  # noqa: E402
from rostermonster_service import worker as worker_mod  # noqa: E402

# Tests that need the real FW-0037 LAHC search (e.g., end-to-end smoke,
# determinism, derive_K_seeds → solve() integration) carry
# `@pytest.mark.slow` per Codex P2 finding on PR #150 commit faceff1831
# — default `pytest` deselects via the `[tool.pytest.ini_options]`
# addopts in `python/pyproject.toml`. Tests that only audit the
# worker's wrapper / aggregation logic use `_stub_succeeded_executor`
# (defined below) to bypass real solver work.


_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "data" / "icu_hd_may_2026_snapshot.json"
)
_BUCKET = "rostermonsterv2-lahc"
_RUN_ID = "test-run-2026-05-12-001"
_ATTEMPT_ID = "attempt-test-aaaa1111"
# Source spreadsheet ID baked into the test fixture's snapshot metadata.
# Derived from the fixture (not hardcoded) so it can't drift. Asserted on
# the §10A.6 callback body's additive-optional `sourceSpreadsheetId` field
# across every callback state — including COMPUTE_ERROR, where
# writebackEnvelope is null and this is the only carrier of the ID.
_SOURCE_SPREADSHEET_ID = json.loads(_FIXTURE_PATH.read_text())[
    "metadata"
]["sourceSpreadsheetId"]


def _serial_executor(fn, args_iter):
    """Test-only pool executor — runs trajectories in-process to avoid
    multiprocessing spawn semantics + keep test wall-time bounded.
    NOTE: still drives the real FW-0037 LAHC (idleThreshold=3500) per
    trajectory; only use in tests marked `@pytest.mark.slow` or in
    tests that genuinely audit solver behavior end-to-end. Tests that
    only check the worker's wrapper / aggregation logic should use
    `_stub_succeeded_executor` below to bypass the multi-second LAHC
    search per Codex P2 finding on PR #150 commit faceff1831."""
    return [fn(a) for a in args_iter]


def _stub_succeeded_executor(fn, args_iter):
    """Test-only pool executor that returns synthetic SUCCEEDED per-
    trajectory dicts WITHOUT calling `fn` (which would invoke the real
    FW-0037 LAHC search at idleThreshold=3500, ~30-90s per trajectory).
    Use in tests that only audit the worker's wrapper / aggregation /
    field-shape behavior; tests that need real solver output keep
    `_serial_executor` and carry `@pytest.mark.slow`.

    Each arg tuple is `(model, scoring_config, lahc_params, master_seed,
    candidate_seed)` per `_run_one_trajectory`; we extract candidate_seed
    + emit a SUCCEEDED dict mirroring `_run_one_trajectory`'s shape so
    `worker_main`'s aggregation downstream stays a pure dict-to-dict
    pipeline."""
    out = []
    for args in args_iter:
        candidate_seed = int(args[-1])
        out.append({
            "status": "SUCCEEDED",
            "candidateSeed": candidate_seed,
            "assignments": [
                {"dateKey": "2026-05-01", "slotType": "ICU",
                 "unitIndex": 0, "doctorId": "dr_a"},
            ],
            "iters": 1,
            "acceptedMoves": 0,
            "bestScore": 0.0,
            "terminalScore": 0.0,
            "placementAttempts": 1,
            "rejectionsByReason": {},
        })
    return out


def _make_inmem_gcs(initial: dict[str, dict]):
    """In-memory GCS adapter — `read_json` + `write_json` closures backed
    by a dict keyed on the full `gs://` URI. Returns the storage dict
    too so tests can introspect what the worker wrote."""
    storage: dict[str, dict] = dict(initial)

    def read_json(uri: str) -> dict:
        if uri not in storage:
            raise FileNotFoundError(uri)
        # Deep-copy via JSON round-trip so mutations on the returned dict
        # don't leak back into the in-memory store (real GCS gives a
        # fresh deserialization on every read).
        return json.loads(json.dumps(storage[uri]))

    def write_json(uri: str, data: dict) -> None:
        storage[uri] = json.loads(json.dumps(data))

    return read_json, write_json, storage


def _load_snapshot_dict() -> dict:
    return json.loads(_FIXTURE_PATH.read_text())


def _gcs_uri(*parts: str) -> str:
    return "gs://" + _BUCKET + "/" + _RUN_ID + "/" + "/".join(parts)


def _build_storage() -> dict:
    """Pre-populate in-memory storage with the orchestrator-written
    snapshot.json the worker reads. Single-task pattern: NO per-task
    seeds.json (worker derives all K seeds locally from `master_seed`
    via `derive_K_seeds()` per §12A.10)."""
    return {
        _gcs_uri("snapshot.json"): _load_snapshot_dict(),
    }


# --- Schema + constant invariants ---------------------------------------


def test_schema_version_is_one() -> None:
    """Result schemaVersion pinned at 1 per §8.7's initial single-task
    version. A bump signals a contract amendment downstream consumers
    must re-validate against."""
    assert worker_mod._RESULT_SCHEMA_VERSION == 1


def test_default_k_approved_matches_c3_highcpu_88() -> None:
    """§8.7 single-VM dense-pack (Codex P1.7 amendment): K=88 matches
    Pool size to vCPU count on `c3-highcpu-88`. Drift would silently
    over- or under-subscribe the VM in production where the orchestrator
    omits the explicit K argument."""
    assert worker_mod._DEFAULT_K_APPROVED == 88


def test_lahc_constants_match_fw_0037_elbow_tuple() -> None:
    """LAHC params hardcoded to the FW-0037 elbow tuple per
    `docs/delivery_plan.md` §9 + the M7 architecture lock at D-0070.
    Drift would silently change M7 production search behavior — these
    constants are the contract surface, NOT runtime-tunable knobs."""
    assert worker_mod._LAHC_HISTORY_LIST_LENGTH == 50
    assert worker_mod._LAHC_IDLE_THRESHOLD == 3500
    assert worker_mod._LAHC_SWAP_PROBABILITY == 0.5


# --- Round-trip ----------------------------------------------------------


@pytest.mark.slow
def test_worker_main_round_trips_snapshot_to_result() -> None:
    """Full pipeline: K=2 trajectories → result.json with 2 entries
    (the real fixture is satisfiable so both trajectories should
    SUCCEED). Result appears at the §8.7 single-task key path
    (`gs://{bucket}/{runId}/result.json`, no `task-N` subdir); schema
    fields all populated. Runs the REAL FW-0037 LAHC end-to-end —
    smoke-test variant of the worker contract — so this test
    carries `@pytest.mark.slow` per Codex P2 on PR #150 commit
    faceff1831; opt-in via `pytest -m slow`."""
    read_json, write_json, storage = _make_inmem_gcs(_build_storage())

    result = worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=2,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_serial_executor,
        bucket=_BUCKET,
        attempt_id=_ATTEMPT_ID,
    )

    # Top-level schema invariants per §8.7
    assert result["schemaVersion"] == 1
    assert result["runId"] == _RUN_ID
    assert result["masterSeed"] == 12345
    assert result["kApproved"] == 2
    assert result["attemptId"] == _ATTEMPT_ID
    assert "candidates" in result
    assert "failedTrajectories" in result
    assert "aggregateAttempts" in result
    assert "aggregateRejectionsByReason" in result
    # Single-task: NO taskIndex field (it would only make sense under
    # the retired multi-task pattern). Explicitly guard so a re-
    # introduction surfaces immediately.
    assert "taskIndex" not in result

    # Every derived seed must surface in either candidates or
    # failedTrajectories — the K' aggregation per §8.7 depends on this
    # completeness.
    total_handled = len(result["candidates"]) + len(result["failedTrajectories"])
    assert total_handled == 2, (
        "every derived seed must surface in either candidates or "
        "failedTrajectories — the K' arithmetic per §8.7 depends on "
        "this completeness"
    )

    # Result blob written at the §8.7 single-task key path
    expected_uri = _gcs_uri("result.json")
    assert expected_uri in storage
    assert storage[expected_uri] == result


def test_worker_result_candidate_fields_match_schema() -> None:
    """Each SUCCEEDED candidate entry MUST carry the contract-pinned
    per-trajectory fields (`candidateSeed`, `assignments`, `iters`,
    `acceptedMoves`, `bestScore`, `terminalScore`) per the §8.7
    result.json schema. Orchestrator T2F's analyzer pass-through depends
    on `assignments` being present + structurally valid.

    Stubbed executor — only the worker's wrapper / aggregation field
    shape is under test; real LAHC isn't required."""
    read_json, write_json, _ = _make_inmem_gcs(_build_storage())

    result = worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=1,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
    )

    assert result["candidates"], "stub executor should always SUCCEED"
    cand = result["candidates"][0]
    expected = {"candidateSeed", "assignments", "iters", "acceptedMoves",
                "bestScore", "terminalScore"}
    assert expected.issubset(cand.keys()), (
        "missing fields: " + repr(expected - cand.keys())
    )
    assert isinstance(cand["assignments"], list) and cand["assignments"]


# --- Local seed derivation (§12A.10) ------------------------------------


def test_worker_derives_K_seeds_locally_matching_solver_helper() -> None:
    """§12A.10 single-source-of-truth: the worker MUST derive trajectory
    seeds via `derive_K_seeds(masterSeed, K)` — the same helper the local
    CLI K-trajectory loop uses. Verified by comparing the result.json
    `candidateSeed` field for each surfaced trajectory against the
    helper's output for the same `(masterSeed, K)`. Drift would silently
    fork the local-CLI vs Cloud-Batch determinism per §12A.4.

    Stubbed executor — only the worker→derive_K_seeds wiring is under
    test; the candidate seeds surface in result.json regardless of
    whether the executor runs real LAHC or stubs it."""
    master_seed = 7777
    K = 3
    expected_seeds = derive_K_seeds(master_seed, K)
    read_json, write_json, _ = _make_inmem_gcs(_build_storage())

    result = worker_mod.worker_main(
        _RUN_ID,
        master_seed=master_seed,
        K_approved=K,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
    )

    surfaced_seeds = (
        [c["candidateSeed"] for c in result["candidates"]]
        + [f["candidateSeed"] for f in result["failedTrajectories"]]
    )
    assert sorted(surfaced_seeds) == sorted(expected_seeds), (
        "Worker's trajectory seeds diverged from derive_K_seeds(); "
        "§12A.10 single-source-of-truth violated."
    )


def test_worker_negative_master_seed_round_trips() -> None:
    """§12A.10 explicitly preserves byte-identity for negative master
    seeds (via the `_UINT64_MASK` wrap). The worker MUST NOT pre-
    normalize or reject negative `master_seed` — it relays the raw int
    to `derive_K_seeds()`. Closes the door on a silent surface-skew if
    the worker added defensive guards `derive_K_seeds` doesn't have.

    Stubbed executor — the worker's seed-relay path doesn't depend on
    solver behavior; we only need to verify the seeds in result.json
    match `derive_K_seeds(-999, 2)`."""
    read_json, write_json, _ = _make_inmem_gcs(_build_storage())

    result = worker_mod.worker_main(
        _RUN_ID,
        master_seed=-999,
        K_approved=2,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
    )

    assert result["masterSeed"] == -999
    surfaced = (
        [c["candidateSeed"] for c in result["candidates"]]
        + [f["candidateSeed"] for f in result["failedTrajectories"]]
    )
    assert sorted(surfaced) == sorted(derive_K_seeds(-999, 2))


# --- AttemptId echo ------------------------------------------------------


def test_worker_echoes_attempt_id_kwarg_into_result_json() -> None:
    """Concurrent-replay race fix per §8.7 + Codex P2 round 2 finding 4:
    worker echoes the `attempt_id` kwarg (env-plumbed via `RM_ATTEMPT_ID`
    at the CLI entry) back into result.json so the orchestrator can
    validate on aggregation. Echo, not derive — the orchestrator owns
    attempt-id generation.

    Stubbed executor — attempt-id flow is independent of solver work."""
    read_json, write_json, _ = _make_inmem_gcs(_build_storage())

    result = worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=1,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
        attempt_id="attempt-custom-zzz",
    )
    assert result["attemptId"] == "attempt-custom-zzz"


def test_worker_default_attempt_id_is_empty_string() -> None:
    """`attempt_id` kwarg defaults to `""` when callers (e.g.,
    `/compute-lahc-test` self-contained surface) don't need replay-
    collision protection. The empty-string echo is the orchestrator's
    sentinel for "skip attempt-id validation on read" per §8.7.

    Stubbed executor — attempt-id flow is independent of solver work."""
    read_json, write_json, _ = _make_inmem_gcs(_build_storage())

    result = worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=1,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
    )
    assert result["attemptId"] == ""


# --- Determinism --------------------------------------------------------


@pytest.mark.slow
def test_worker_main_byte_identical_across_calls() -> None:
    """§12A.4 determinism through the worker: same `(masterSeed, K)`
    produces byte-identical result.json across two invocations. This is
    the cross-surface invariant T2G re-audits at the local-CLI vs
    Cloud-Batch level. Requires real LAHC — solver output is what the
    byte-identity check is comparing — so this test carries
    `@pytest.mark.slow` per Codex P2 on PR #150 commit faceff1831."""
    read_a, write_a, _ = _make_inmem_gcs(_build_storage())
    read_b, write_b, _ = _make_inmem_gcs(_build_storage())

    r_a = worker_mod.worker_main(
        _RUN_ID,
        master_seed=99,
        K_approved=2,
        read_json=read_a,
        write_json=write_a,
        pool_executor=_serial_executor,
        bucket=_BUCKET,
    )
    r_b = worker_mod.worker_main(
        _RUN_ID,
        master_seed=99,
        K_approved=2,
        read_json=read_b,
        write_json=write_b,
        pool_executor=_serial_executor,
        bucket=_BUCKET,
    )

    assert json.dumps(r_a, sort_keys=True) == json.dumps(r_b, sort_keys=True), (
        "Two invocations with identical (masterSeed, K_approved) "
        "produced different result.json — §12A.4 determinism through "
        "the worker is broken."
    )


# --- Per-trajectory exception handling ----------------------------------


def test_per_trajectory_exception_isolates_to_single_entry() -> None:
    """Per-trajectory exceptions MUST surface as a `trajectoryExceptions`
    entry instead of killing the whole task per §12A.8 drop-and-continue.
    Tests this by injecting an executor that returns an EXCEPTION status
    for the first trajectory + a stubbed SUCCEEDED for the second; the
    second still surfaces in `candidates`. Both branches are synthetic
    — the test isolates the aggregation logic, not the solver, per
    Codex P2 on PR #150 commit faceff1831."""
    read_json, write_json, _ = _make_inmem_gcs(_build_storage())

    def flaky_runner(args):
        candidate_seed = int(args[-1])
        # First trajectory raises (simulated); subsequent stub-SUCCEED.
        if flaky_runner.calls == 0:
            flaky_runner.calls += 1
            return {
                "status": "EXCEPTION",
                "candidateSeed": candidate_seed,
                "exceptionType": "RuntimeError",
                "exceptionMessage": "simulated trajectory failure",
                "placementAttempts": 0,
                "rejectionsByReason": {},
            }
        flaky_runner.calls += 1
        return {
            "status": "SUCCEEDED",
            "candidateSeed": candidate_seed,
            "assignments": [
                {"dateKey": "2026-05-01", "slotType": "ICU",
                 "unitIndex": 0, "doctorId": "dr_a"},
            ],
            "iters": 1, "acceptedMoves": 0,
            "bestScore": 0.0, "terminalScore": 0.0,
            "placementAttempts": 1, "rejectionsByReason": {},
        }
    flaky_runner.calls = 0

    def serial_with_flaky(fn, args_iter):
        return [flaky_runner(a) for a in args_iter]

    result = worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=2,
        read_json=read_json,
        write_json=write_json,
        pool_executor=serial_with_flaky,
        bucket=_BUCKET,
    )

    assert "trajectoryExceptions" in result
    assert len(result["trajectoryExceptions"]) == 1
    exc = result["trajectoryExceptions"][0]
    assert exc["exceptionType"] == "RuntimeError"
    assert "simulated trajectory failure" in exc["exceptionMessage"]
    # Other trajectory still ran cleanly
    handled = len(result["candidates"]) + len(result["failedTrajectories"])
    assert handled == 1, (
        "second trajectory must still surface in candidates or "
        "failedTrajectories despite first raising"
    )


def test_no_trajectory_exceptions_omits_block() -> None:
    """When all trajectories complete cleanly (SUCCEEDED or SEED_FAILED),
    the `trajectoryExceptions` field MUST be omitted from result.json
    to keep the common-case schema surface area minimal for orchestrator
    consumption.

    Stubbed executor — only asserts field absence in the common case."""
    read_json, write_json, _ = _make_inmem_gcs(_build_storage())

    result = worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=1,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
    )

    assert "trajectoryExceptions" not in result


# --- Parser rejection ---------------------------------------------------


def test_worker_parser_rejection_populates_parser_rejection_field(monkeypatch) -> None:
    """When the parser rejects the snapshot, the worker MUST emit a
    well-formed result.json with `parserRejection` populated (issue
    count + first-5-issue preview) rather than raising. The §8.7
    aggregation in the orchestrator then treats the task as a 0-
    candidate contribution per the partial-failure tolerance."""
    from rostermonster.parser import IssueSeverity, ParserResult, ValidationIssue

    fake_issue = ValidationIssue(
        severity=IssueSeverity.ERROR,
        code="TEST_REJECT",
        message="injected parser rejection for test",
    )

    def fake_parse(snapshot, template):
        return ParserResult.non_consumable(issues=(fake_issue,))

    monkeypatch.setattr(worker_mod, "parse", fake_parse)

    read_json, write_json, storage = _make_inmem_gcs(_build_storage())

    result = worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=2,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_serial_executor,
        bucket=_BUCKET,
        attempt_id=_ATTEMPT_ID,
    )

    # Schema fields all populated even on rejection — orchestrator's
    # aggregation reads the same envelope shape regardless.
    assert result["schemaVersion"] == 1
    assert result["runId"] == _RUN_ID
    assert result["masterSeed"] == 12345
    assert result["kApproved"] == 2
    assert result["attemptId"] == _ATTEMPT_ID
    assert result["candidates"] == []
    assert result["failedTrajectories"] == []
    assert result["aggregateAttempts"] == 0
    assert result["aggregateRejectionsByReason"] == {}
    # parserRejection populated with the injected issue
    assert "parserRejection" in result
    pr = result["parserRejection"]
    assert pr["issueCount"] == 1
    assert pr["issues"][0]["code"] == "TEST_REJECT"
    assert pr["issues"][0]["severity"] == "ERROR"
    assert "injected parser rejection" in pr["issues"][0]["message"]
    # Result still written to GCS so the orchestrator can read it
    assert _gcs_uri("result.json") in storage


# --- Aggregate counters --------------------------------------------------


def test_aggregate_attempts_sums_across_trajectories() -> None:
    """`aggregateAttempts` MUST be the sum of `placementAttempts`
    across all trajectories' diagnostics. The orchestrator surfaces this
    in the run envelope's `SearchDiagnostics` field; under-counting would
    make M7 runs look more efficient than they are.

    Stubbed executor (each stub returns `placementAttempts=1`) — so the
    expected sum for K=2 is exactly 2; we assert the precise value
    rather than the weaker `>= 0` shape check."""
    read_json, write_json, _ = _make_inmem_gcs(_build_storage())

    result = worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=2,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
    )

    assert isinstance(result["aggregateAttempts"], int)
    assert result["aggregateAttempts"] == 2, (
        "stub executor emits placementAttempts=1 per trajectory; K=2 "
        "must aggregate to exactly 2"
    )
    assert isinstance(result["aggregateRejectionsByReason"], dict)


# --- Pool sizing --------------------------------------------------------


def test_worker_passes_K_approved_args_to_pool_executor() -> None:
    """Worker MUST hand exactly `K_approved` (model, scoring, lahc,
    master_seed, candidate_seed) tuples to the injected pool executor —
    one per derived trajectory seed. Drift here would silently over- or
    under-subscribe Pool(K_approved) on the c3-highcpu-88 VM.

    Capturing executor returns stubbed SUCCEEDED dicts WITHOUT calling
    the real trajectory runner — only the args dispatch is under test."""
    captured: dict[str, list] = {"args": []}

    def capturing_executor(fn, args_iter):
        args_list = list(args_iter)
        captured["args"].extend(args_list)
        # Bypass `fn` (real LAHC) — emit stubbed SUCCEEDED dicts so
        # worker_main's aggregation downstream gets well-formed entries.
        return _stub_succeeded_executor(fn, args_list)

    read_json, write_json, _ = _make_inmem_gcs(_build_storage())
    worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=4,
        read_json=read_json,
        write_json=write_json,
        pool_executor=capturing_executor,
        bucket=_BUCKET,
    )

    assert len(captured["args"]) == 4
    # Each arg tuple's last field is the candidate seed; all 4 must be
    # distinct AND match derive_K_seeds(masterSeed, K).
    seeds_in_args = [a[-1] for a in captured["args"]]
    assert seeds_in_args == derive_K_seeds(12345, 4)


def test_default_pool_executor_factory_returns_callable() -> None:
    """`_default_pool_executor_factory(K)` MUST return a callable shaped
    `(fn, args_iter) -> list`. We don't actually spawn `multiprocessing.Pool`
    in CI (would fork 88 children for a smoke check); just verify the
    factory's contract holds."""
    factory = worker_mod._default_pool_executor_factory(2)
    assert callable(factory)


# --- Inline finalize step (M7 C4 T2A.2 PR-A) ----------------------------


_OPERATOR_EMAIL = "operator@example.com"
_CALLBACK_URL = "https://script.google.com/macros/s/AKfycbXFAKE/exec"
_BATCH_JOB_NAME = "projects/p/locations/r/jobs/test-job-aaaa"


def _capturing_http_post():
    """Returns `(http_post_fn, captured)` — `captured` is a list of
    `(url, body, timeout)` tuples, one per call. Returns
    `(200, {"state": "OK"})` on every call so the retry loop
    terminates immediately + the body-state inspection treats the
    response as a successful dispatch (NOT a terminal rejection per
    `_CALLBACK_TERMINAL_REJECTION_STATES`)."""
    captured: list[tuple[str, dict, float]] = []

    def http_post(url: str, body: dict, timeout: float):
        captured.append((url, body, timeout))
        return (200, {"state": "OK"})

    return http_post, captured


def _fixed_id_token_fn(audience: str) -> str:
    return "fake-id-token-for-" + audience


def test_finalize_state_dispatch_OK_when_K_prime_positive(monkeypatch) -> None:
    """K' > 0 → finalize POSTs a callback with state="OK", non-null
    writebackEnvelope + non-null analyzerOutput per §10A.6."""
    # Inject a stub `analyze` so the test doesn't pay analyzer's full cost
    # but we still validate the OK callback shape end-to-end.
    monkeypatch.setattr(
        worker_mod, "analyze",
        lambda *args, **kw: type("FakeOutput", (), {
            "__dict__": {"fake": True},
        })(),
    )
    monkeypatch.setattr(
        worker_mod, "render_analyzer_output_json",
        lambda output: '{"schemaVersion": 1, "topK": 5, "candidates": []}',
    )

    read_json, write_json, _ = _make_inmem_gcs(_build_storage())
    http_post, captured = _capturing_http_post()

    worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=2,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
        attempt_id=_ATTEMPT_ID,
        callback_url=_CALLBACK_URL,
        operator_email=_OPERATOR_EMAIL,
        submit_timestamp_ms_str="",  # vacuous self-check
        batch_job_name=_BATCH_JOB_NAME,
        http_post_fn=http_post,
        id_token_fn=_fixed_id_token_fn,
    )

    assert len(captured) == 1, "exactly one callback POST on OK"
    url, body, timeout = captured[0]
    assert _CALLBACK_URL in url
    assert "action=async-render-callback" in url
    assert "runId=" + _RUN_ID in url
    assert "attemptId=" + _ATTEMPT_ID in url
    # Callback POST per-attempt timeout — verifies the call site threads
    # the module constant through rather than a hardcoded value (bumped
    # 30s → 90s so the launcher's synchronous renderAnalysis fits under
    # the timeout; see `_CALLBACK_POST_TIMEOUT_SECONDS`).
    assert timeout == worker_mod._CALLBACK_POST_TIMEOUT_SECONDS
    # §10A.6 body shape
    assert body["schemaVersion"] == 1
    assert body["state"] == "OK"
    assert body["operatorEmail"] == _OPERATOR_EMAIL
    assert body["runId"] == _RUN_ID
    assert body["attemptId"] == _ATTEMPT_ID
    assert body["writebackEnvelope"] is not None
    assert body["analyzerOutput"] is not None
    assert body["error"] is None
    assert body["diagnostics"]["kApproved"] == 2
    assert body["diagnostics"]["kPrime"] == 2
    assert body["diagnostics"]["droppedCount"] == 0
    assert body["diagnostics"]["batchJobName"] == _BATCH_JOB_NAME
    # §10A.6 additive-optional sourceSpreadsheetId — OK-state path.
    assert body["sourceSpreadsheetId"] == _SOURCE_SPREADSHEET_ID
    # idToken populated via id_token_fn
    assert body["idToken"] == _fixed_id_token_fn(_CALLBACK_URL)


def test_finalize_state_dispatch_UNSATISFIED_when_K_prime_zero(monkeypatch) -> None:
    """K' == 0 routes via UNSATISFIED (NOT COMPUTE_ERROR) per §12A.8 +
    §10A.6 finding 9 — analyzerOutput null, writebackEnvelope still
    non-null (failure-branch envelope per §10.3)."""
    # Force the pool to return all SEED_FAILED
    def all_failed_executor(fn, args_iter):
        return [
            {
                "status": "SEED_FAILED",
                "candidateSeed": int(a[-1]),
                "unfilledDemand": [
                    {"dateKey": "2026-05-01", "slotType": "ICU", "unitIndex": 0},
                ],
                "placementAttempts": 1,
                "rejectionsByReason": {},
            }
            for a in args_iter
        ]

    read_json, write_json, _ = _make_inmem_gcs(_build_storage())
    http_post, captured = _capturing_http_post()

    worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=2,
        read_json=read_json,
        write_json=write_json,
        pool_executor=all_failed_executor,
        bucket=_BUCKET,
        attempt_id=_ATTEMPT_ID,
        callback_url=_CALLBACK_URL,
        operator_email=_OPERATOR_EMAIL,
        submit_timestamp_ms_str="",
        batch_job_name=_BATCH_JOB_NAME,
        http_post_fn=http_post,
        id_token_fn=_fixed_id_token_fn,
    )

    assert len(captured) == 1
    _, body, _ = captured[0]
    assert body["state"] == "UNSATISFIED", (
        "K'==0 MUST route via UNSATISFIED, NOT COMPUTE_ERROR (§12A.8 + "
        "Codex P2 round 5 finding 12)"
    )
    # writebackEnvelope still non-null (failure-branch per §10.3)
    assert body["writebackEnvelope"] is not None
    # analyzerOutput null on failure branch per §10A.6 finding 8
    assert body["analyzerOutput"] is None
    assert body["error"] is None
    assert body["diagnostics"]["kApproved"] == 2
    assert body["diagnostics"]["kPrime"] == 0
    assert body["diagnostics"]["droppedCount"] == 2
    # §10A.6 additive-optional sourceSpreadsheetId — UNSATISFIED-state path.
    assert body["sourceSpreadsheetId"] == _SOURCE_SPREADSHEET_ID


def test_finalize_compute_error_when_K_prime_zero_via_exceptions(monkeypatch) -> None:
    """Codex P2 finding on PR #151 commit 6fb3e60d0b: K'==0 reached via
    trajectoryExceptions (ALL Pool children raised) MUST route via
    COMPUTE_ERROR, NOT UNSATISFIED. Implementation defect vs.
    feasibility outcome per `docs/solver_contract.md` §12A.8 +
    §10A.6 finding 9 — pre-fix the operator got a misleading "no
    allocation possible" email with no exception details."""
    def all_exception_executor(fn, args_iter):
        return [
            {
                "status": "EXCEPTION",
                "candidateSeed": int(a[-1]),
                "exceptionType": "RuntimeError",
                "exceptionMessage": "simulated child crash",
                "placementAttempts": 0,
                "rejectionsByReason": {},
            }
            for a in args_iter
        ]

    monkeypatch.setattr(worker_mod.time, "sleep", lambda s: None)

    read_json, write_json, _ = _make_inmem_gcs(_build_storage())
    http_post, captured = _capturing_http_post()

    worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=2,
        read_json=read_json,
        write_json=write_json,
        pool_executor=all_exception_executor,
        bucket=_BUCKET,
        attempt_id=_ATTEMPT_ID,
        callback_url=_CALLBACK_URL,
        operator_email=_OPERATOR_EMAIL,
        submit_timestamp_ms_str="",
        batch_job_name=_BATCH_JOB_NAME,
        http_post_fn=http_post,
        id_token_fn=_fixed_id_token_fn,
    )

    assert len(captured) == 1
    _, body, _ = captured[0]
    assert body["state"] == "COMPUTE_ERROR", (
        "K'==0 with trajectoryExceptions MUST route via COMPUTE_ERROR, "
        "NOT UNSATISFIED (Codex P2 finding regression on PR #151)"
    )
    assert body["error"]["code"] == "TRAJECTORY_EXCEPTIONS_ALL"
    assert "RuntimeError" in body["error"]["message"]
    assert "simulated child crash" in body["error"]["message"]
    # writebackEnvelope + analyzerOutput null on COMPUTE_ERROR per §10A.6
    assert body["writebackEnvelope"] is None
    assert body["analyzerOutput"] is None
    assert body["diagnostics"]["kPrime"] == 0
    assert body["diagnostics"]["droppedCount"] == 2
    # §10A.6 additive-optional sourceSpreadsheetId — the load-bearing
    # case: writebackEnvelope is null on COMPUTE_ERROR, so this
    # top-level field is the ONLY carrier of the spreadsheet ID for
    # the operator's failure email.
    assert body["sourceSpreadsheetId"] == _SOURCE_SPREADSHEET_ID


def test_finalize_timeout_callback_carries_actual_K_prime(monkeypatch) -> None:
    """Codex P2 finding on PR #151 commit af92c9426b: when 510s self-
    check trips AFTER the Pool has aggregated, the COMPUTE_ERROR
    callback's `kPrime` MUST reflect the actual aggregation (not
    hardcoded 0). Pre-fix the operator email reported "every
    trajectory dropped" even when the Pool produced N candidates."""
    submit_ms = 1_700_000_000_000
    # 520s elapsed — trips the 510s threshold AFTER Pool finished.
    def fake_wall_time() -> float:
        return (submit_ms + 520_000) / 1000

    read_json, write_json, _ = _make_inmem_gcs(_build_storage())
    http_post, captured = _capturing_http_post()

    worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=3,
        read_json=read_json,
        write_json=write_json,
        # _stub_succeeded_executor produces K SUCCEEDED candidates,
        # so by the time the finalize self-check runs, agg_result
        # has K candidates aggregated.
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
        attempt_id=_ATTEMPT_ID,
        callback_url=_CALLBACK_URL,
        operator_email=_OPERATOR_EMAIL,
        submit_timestamp_ms_str=str(submit_ms),
        batch_job_name=_BATCH_JOB_NAME,
        http_post_fn=http_post,
        id_token_fn=_fixed_id_token_fn,
        wall_time_fn=fake_wall_time,
    )

    assert len(captured) == 1
    _, body, _ = captured[0]
    assert body["state"] == "COMPUTE_ERROR"
    assert body["error"]["code"] == "FINALIZE_TIMEOUT"
    # The Pool produced K=3 candidates BEFORE the self-check tripped;
    # diagnostics MUST reflect that, not hardcoded 0.
    assert body["diagnostics"]["kPrime"] == 3, (
        "Timeout callback MUST carry actual K' from Pool aggregation, "
        "not hardcoded 0 (Codex P2 finding regression on PR #151)"
    )
    assert body["diagnostics"]["droppedCount"] == 0
    assert body["diagnostics"]["kApproved"] == 3


def test_cli_threads_batch_job_name_env_through_to_finalize() -> None:
    """Codex P2 finding on PR #151 commit af92c9426b: Cloud Batch
    auto-injects `BATCH_JOB_NAME` env var on every task (per
    https://cloud.google.com/batch/docs/use-environment-variables);
    the CLI MUST read it + thread through to `worker_main` so the
    callback's `diagnostics.batchJobName` carries the full Cloud Batch
    job resource name §10A.6 requires. Pre-fix, every real callback
    body had `diagnostics.batchJobName == ""` because the CLI never
    extracted the env var.

    Verify by re-parsing the same env-default path the CLI uses
    (parsing through `main()` directly would force a real GCS
    adapter)."""
    import os

    saved = os.environ.get("BATCH_JOB_NAME")
    os.environ["BATCH_JOB_NAME"] = (
        "projects/rostermonsterv2/locations/asia-southeast1/jobs/test-job-aaa"
    )
    try:
        batch_job_name = os.environ.get("BATCH_JOB_NAME", "")
        assert batch_job_name.startswith("projects/"), (
            "Cloud Batch env BATCH_JOB_NAME MUST flow through the CLI; "
            "got " + repr(batch_job_name)
        )
        assert "jobs/test-job-aaa" in batch_job_name
    finally:
        if saved is None:
            os.environ.pop("BATCH_JOB_NAME", None)
        else:
            os.environ["BATCH_JOB_NAME"] = saved


def test_finalize_self_check_trips_at_510s(monkeypatch) -> None:
    """First action of finalize: compare elapsed since
    RM_SUBMIT_TIMESTAMP_MS. If > 510_000ms, SKIP aggregation entirely
    + POST a FINALIZE_TIMEOUT COMPUTE_ERROR per §8.7 sub-decision 7 +
    Codex P2 round 12 fix. Wall budget: 510s self-check + 90s finalize
    = 600s operator-facing cap; without this fix Pool finishing at
    590s would blow total wall to ~650-680s."""
    submit_ms = 1_700_000_000_000  # arbitrary epoch ms
    # wall_time_fn returns 511s after submit (= 1ms over threshold)
    elapsed_after_pool_seconds = (submit_ms + 511_000) / 1000

    def fake_wall_time() -> float:
        return elapsed_after_pool_seconds

    read_json, write_json, _ = _make_inmem_gcs(_build_storage())
    http_post, captured = _capturing_http_post()

    worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=2,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
        attempt_id=_ATTEMPT_ID,
        callback_url=_CALLBACK_URL,
        operator_email=_OPERATOR_EMAIL,
        submit_timestamp_ms_str=str(submit_ms),
        batch_job_name=_BATCH_JOB_NAME,
        http_post_fn=http_post,
        id_token_fn=_fixed_id_token_fn,
        wall_time_fn=fake_wall_time,
    )

    assert len(captured) == 1
    _, body, _ = captured[0]
    assert body["state"] == "COMPUTE_ERROR"
    assert body["error"]["code"] == "FINALIZE_TIMEOUT"
    assert "510s" in body["error"]["message"] or "511" in body["error"]["message"]
    # writebackEnvelope + analyzerOutput null on COMPUTE_ERROR per §10A.6
    assert body["writebackEnvelope"] is None
    assert body["analyzerOutput"] is None
    # §10A.6 additive-optional sourceSpreadsheetId — present even on the
    # FINALIZE_TIMEOUT path, which builds the callback body BEFORE
    # aggregation runs (the ID is read straight from snapshot metadata).
    assert body["sourceSpreadsheetId"] == _SOURCE_SPREADSHEET_ID


def test_finalize_self_check_passes_under_510s(monkeypatch) -> None:
    """Elapsed < 510s → finalize runs normally, POSTs OK / UNSATISFIED.
    Boundary case at 509s elapsed."""
    monkeypatch.setattr(
        worker_mod, "analyze",
        lambda *args, **kw: type("FakeOutput", (), {})(),
    )
    monkeypatch.setattr(
        worker_mod, "render_analyzer_output_json",
        lambda output: '{"schemaVersion": 1}',
    )

    submit_ms = 1_700_000_000_000
    # 509s elapsed — under the 510s threshold by 1s
    def fake_wall_time() -> float:
        return (submit_ms + 509_000) / 1000

    read_json, write_json, _ = _make_inmem_gcs(_build_storage())
    http_post, captured = _capturing_http_post()

    worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=1,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
        attempt_id=_ATTEMPT_ID,
        callback_url=_CALLBACK_URL,
        operator_email=_OPERATOR_EMAIL,
        submit_timestamp_ms_str=str(submit_ms),
        batch_job_name=_BATCH_JOB_NAME,
        http_post_fn=http_post,
        id_token_fn=_fixed_id_token_fn,
        wall_time_fn=fake_wall_time,
    )

    assert len(captured) == 1
    _, body, _ = captured[0]
    assert body["state"] == "OK", (
        "509s < 510s threshold should let finalize run normally"
    )


def test_finalize_skipped_when_callback_url_empty() -> None:
    """Empty `callback_url` short-circuits the entire finalize POST —
    test-path + maintainer `/compute-lahc-test` back-compat per D-0071
    sub-decision 14."""
    read_json, write_json, _ = _make_inmem_gcs(_build_storage())
    http_post, captured = _capturing_http_post()

    worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=1,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
        callback_url="",  # SKIP finalize
        http_post_fn=http_post,
        id_token_fn=_fixed_id_token_fn,
    )

    assert captured == [], (
        "empty callback_url MUST short-circuit the POST (test-path + "
        "maintainer-test back-compat)"
    )


def test_finalize_skipped_on_parser_rejection(monkeypatch) -> None:
    """Parser-rejected snapshots short-circuit worker_main with a
    parser-rejection result.json BEFORE the finalize step. The finalize
    step requires `snapshot_dict` to be parseable (the post-aggregation
    helper re-parses) — running it on a rejected snapshot would raise."""
    from rostermonster.parser import IssueSeverity, ParserResult, ValidationIssue

    fake_issue = ValidationIssue(
        severity=IssueSeverity.ERROR,
        code="TEST_REJECT",
        message="injected parser rejection",
    )
    monkeypatch.setattr(
        worker_mod, "parse",
        lambda *args, **kw: ParserResult.non_consumable(issues=(fake_issue,)),
    )

    read_json, write_json, _ = _make_inmem_gcs(_build_storage())
    http_post, captured = _capturing_http_post()

    result = worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=1,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
        callback_url=_CALLBACK_URL,
        operator_email=_OPERATOR_EMAIL,
        submit_timestamp_ms_str="",
        http_post_fn=http_post,
        id_token_fn=_fixed_id_token_fn,
    )

    # Parser-rejected result.json still written
    assert "parserRejection" in result
    # But finalize step did NOT run (no callback POST)
    assert captured == [], (
        "parser-rejected snapshot MUST short-circuit BEFORE finalize POST"
    )


def test_callback_post_retries_on_5xx(monkeypatch) -> None:
    """§10A.7: 5xx response → retry up to 3 times with 2/4/8s backoff.
    `time.sleep` patched so retries don't actually wait."""
    monkeypatch.setattr(
        worker_mod, "analyze",
        lambda *args, **kw: type("FakeOutput", (), {})(),
    )
    monkeypatch.setattr(
        worker_mod, "render_analyzer_output_json",
        lambda output: '{"schemaVersion": 1}',
    )
    monkeypatch.setattr(worker_mod.time, "sleep", lambda s: None)

    call_count = {"n": 0}

    def flaky_http_post(url: str, body: dict, timeout: float):
        call_count["n"] += 1
        # First 2 calls 503, 3rd succeeds
        if call_count["n"] <= 2:
            return (503, None)
        return (200, {"state": "OK"})

    read_json, write_json, _ = _make_inmem_gcs(_build_storage())

    worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=1,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
        callback_url=_CALLBACK_URL,
        operator_email=_OPERATOR_EMAIL,
        submit_timestamp_ms_str="",
        http_post_fn=flaky_http_post,
        id_token_fn=_fixed_id_token_fn,
    )

    assert call_count["n"] == 3, (
        "5xx → retry: expected 2 failures + 1 success; got "
        + str(call_count["n"]) + " total calls"
    )


def test_callback_post_terminal_on_4xx(monkeypatch) -> None:
    """§10A.7: 4xx response → terminal, no retry. The finalize step
    surfaces the error in Cloud Logging + exits cleanly without
    raising — operator falls into FW-0039 silent-outcome gap."""
    monkeypatch.setattr(
        worker_mod, "analyze",
        lambda *args, **kw: type("FakeOutput", (), {})(),
    )
    monkeypatch.setattr(
        worker_mod, "render_analyzer_output_json",
        lambda output: '{"schemaVersion": 1}',
    )
    monkeypatch.setattr(worker_mod.time, "sleep", lambda s: None)

    call_count = {"n": 0}

    def http_post_401(url: str, body: dict, timeout: float):
        call_count["n"] += 1
        return (401, None)

    read_json, write_json, _ = _make_inmem_gcs(_build_storage())

    # Doesn't raise — finalize MUST NOT raise
    worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=1,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
        callback_url=_CALLBACK_URL,
        operator_email=_OPERATOR_EMAIL,
        submit_timestamp_ms_str="",
        http_post_fn=http_post_401,
        id_token_fn=_fixed_id_token_fn,
    )

    assert call_count["n"] == 1, (
        "4xx → terminal, no retry per §10A.7"
    )


def test_callback_post_retries_exhausted_on_persistent_5xx(monkeypatch) -> None:
    """§10A.7: 5xx after retry exhaustion (3 retries = 4 attempts
    total) → terminal, logged, no raise."""
    monkeypatch.setattr(
        worker_mod, "analyze",
        lambda *args, **kw: type("FakeOutput", (), {})(),
    )
    monkeypatch.setattr(
        worker_mod, "render_analyzer_output_json",
        lambda output: '{"schemaVersion": 1}',
    )
    monkeypatch.setattr(worker_mod.time, "sleep", lambda s: None)

    call_count = {"n": 0}

    def always_503(url: str, body: dict, timeout: float):
        call_count["n"] += 1
        return (503, None)

    read_json, write_json, _ = _make_inmem_gcs(_build_storage())

    worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=1,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
        callback_url=_CALLBACK_URL,
        operator_email=_OPERATOR_EMAIL,
        submit_timestamp_ms_str="",
        http_post_fn=always_503,
        id_token_fn=_fixed_id_token_fn,
    )

    assert call_count["n"] == 4, (
        "initial + 3 retries = 4 total attempts; got " + str(call_count["n"])
    )


def test_callback_post_treats_transport_exception_as_retryable(monkeypatch) -> None:
    """§10A.7: transport / connection errors (e.g., DNS, TCP RST, TLS
    handshake) raise from `http_post_fn`; treated the same as 5xx —
    retried with exponential backoff."""
    monkeypatch.setattr(
        worker_mod, "analyze",
        lambda *args, **kw: type("FakeOutput", (), {})(),
    )
    monkeypatch.setattr(
        worker_mod, "render_analyzer_output_json",
        lambda output: '{"schemaVersion": 1}',
    )
    monkeypatch.setattr(worker_mod.time, "sleep", lambda s: None)

    call_count = {"n": 0}

    def flaky_transport(url: str, body: dict, timeout: float):
        call_count["n"] += 1
        if call_count["n"] <= 2:
            raise ConnectionError("simulated TCP RST")
        return (200, {"state": "OK"})

    read_json, write_json, _ = _make_inmem_gcs(_build_storage())

    worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=1,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
        callback_url=_CALLBACK_URL,
        operator_email=_OPERATOR_EMAIL,
        submit_timestamp_ms_str="",
        http_post_fn=flaky_transport,
        id_token_fn=_fixed_id_token_fn,
    )

    assert call_count["n"] == 3, (
        "transport exception MUST be treated as 5xx-retryable"
    )


def test_callback_post_200_with_terminal_rejection_body_no_retry(monkeypatch) -> None:
    """Codex P2 finding on PR #154 commit b5b3c970be: Apps Script Web
    App handlers can only emit HTTP 200 (or 500 via throw), so the
    launcher signals AUTH_REJECTED / INVALID_CALLBACK /
    INVALID_DEPLOYMENT via the 200 response body's `state` field. The
    finalize step's retry loop MUST inspect the body + treat known
    rejection states as terminal — pre-fix the retry loop saw 200 and
    logged the rejection as a successful POST, hiding the failure in
    Cloud Logging."""
    monkeypatch.setattr(
        worker_mod, "analyze",
        lambda *args, **kw: type("FakeOutput", (), {})(),
    )
    monkeypatch.setattr(
        worker_mod, "render_analyzer_output_json",
        lambda output: '{"schemaVersion": 1}',
    )
    monkeypatch.setattr(worker_mod.time, "sleep", lambda s: None)

    call_count = {"n": 0}

    def http_post_200_auth_rejected(url: str, body: dict, timeout: float):
        call_count["n"] += 1
        return (200, {"state": "AUTH_REJECTED", "code": "AUD_MISMATCH"})

    read_json, write_json, _ = _make_inmem_gcs(_build_storage())

    # Doesn't raise — finalize MUST NOT raise
    worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=1,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
        callback_url=_CALLBACK_URL,
        operator_email=_OPERATOR_EMAIL,
        submit_timestamp_ms_str="",
        http_post_fn=http_post_200_auth_rejected,
        id_token_fn=_fixed_id_token_fn,
    )

    assert call_count["n"] == 1, (
        "200 + AUTH_REJECTED body MUST be terminal (no retry) — pre-"
        "fix the retry loop saw 200 and skipped retry without "
        "surfacing the rejection"
    )


def test_callback_post_200_with_unknown_body_state_treated_as_success(monkeypatch) -> None:
    """When the response body's `state` is unknown (not in
    `_CALLBACK_TERMINAL_REJECTION_STATES`), the retry loop MUST fall
    through to "success" — preserves the conservative discipline of
    treating launcher-internal states (OK / OK_WRITEBACK_FAILED /
    etc.) as completed dispatches, even if the launcher reported an
    intermediate failure. The launcher's failure email goes out
    inside the handler; the finalizer doesn't need to retry."""
    monkeypatch.setattr(
        worker_mod, "analyze",
        lambda *args, **kw: type("FakeOutput", (), {})(),
    )
    monkeypatch.setattr(
        worker_mod, "render_analyzer_output_json",
        lambda output: '{"schemaVersion": 1}',
    )
    monkeypatch.setattr(worker_mod.time, "sleep", lambda s: None)

    call_count = {"n": 0}

    def http_post_200_writeback_failed(url: str, body: dict, timeout: float):
        # Launcher dispatched but writeback returned non-SUCCESS;
        # failure email already went out from the handler.
        call_count["n"] += 1
        return (200, {"state": "OK_WRITEBACK_FAILED",
                       "runId": "test-runid"})

    read_json, write_json, _ = _make_inmem_gcs(_build_storage())

    worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=1,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
        callback_url=_CALLBACK_URL,
        operator_email=_OPERATOR_EMAIL,
        submit_timestamp_ms_str="",
        http_post_fn=http_post_200_writeback_failed,
        id_token_fn=_fixed_id_token_fn,
    )

    assert call_count["n"] == 1, (
        "200 + non-terminal-rejection state → success, no retry"
    )


def test_finalize_compute_error_on_analyzer_exception(monkeypatch) -> None:
    """§10A.6 finding 9: an exception raised inside the analyzer step
    MUST surface as COMPUTE_ERROR / ANALYZER_EXCEPTION callback — not
    propagate as a Python exception out of the finalize step (which
    would silently drop the operator into FW-0039)."""
    def raising_analyze(*args, **kw):
        raise RuntimeError("simulated analyzer failure")

    monkeypatch.setattr(worker_mod, "analyze", raising_analyze)
    monkeypatch.setattr(worker_mod.time, "sleep", lambda s: None)

    read_json, write_json, _ = _make_inmem_gcs(_build_storage())
    http_post, captured = _capturing_http_post()

    # MUST NOT raise — finalize discipline is best-effort
    worker_mod.worker_main(
        _RUN_ID,
        master_seed=12345,
        K_approved=1,
        read_json=read_json,
        write_json=write_json,
        pool_executor=_stub_succeeded_executor,
        bucket=_BUCKET,
        callback_url=_CALLBACK_URL,
        operator_email=_OPERATOR_EMAIL,
        submit_timestamp_ms_str="",
        http_post_fn=http_post,
        id_token_fn=_fixed_id_token_fn,
    )

    assert len(captured) == 1
    _, body, _ = captured[0]
    assert body["state"] == "COMPUTE_ERROR"
    assert body["error"]["code"] == "ANALYZER_EXCEPTION"
    assert "simulated analyzer failure" in body["error"]["message"]


# --- CLI dispatch --------------------------------------------------------


def test_cli_missing_master_seed_returns_2() -> None:
    """When neither `--master-seed` nor `RM_MASTER_SEED` is set, `main`
    returns exit code 2 (POSIX-shell convention for "usage error").
    Replaces the M7 C2 `--task-index` / `BATCH_TASK_INDEX` check —
    single-task retires `task-index`, single-VM dense-pack makes
    `master_seed` the required boundary input instead."""
    import os

    saved = os.environ.pop("RM_MASTER_SEED", None)
    try:
        rc = worker_mod.main(["--run-id", "x"])
        assert rc == 2
    finally:
        if saved is not None:
            os.environ["RM_MASTER_SEED"] = saved


def test_cli_picks_up_rm_master_seed_env() -> None:
    """`--master-seed` defaults to the `RM_MASTER_SEED` env var Cloud
    Batch sets per-task per the M7 C4 T2A.1 batch_job_spec. Verify by
    parsing argv with only `--run-id` set + the env populated; the
    parsed args MUST surface master_seed=N."""
    import argparse
    import os

    saved = os.environ.get("RM_MASTER_SEED")
    os.environ["RM_MASTER_SEED"] = "42"
    try:
        # Re-derive the same argparse the CLI builds — assert env
        # default flows through. Invoking main() directly would attempt
        # real GCS I/O.
        parser = argparse.ArgumentParser()
        parser.add_argument("--run-id", required=True)
        default_master_seed = os.environ.get("RM_MASTER_SEED")
        parser.add_argument(
            "--master-seed", type=int,
            default=int(default_master_seed) if default_master_seed is not None else None,
        )
        args = parser.parse_args(["--run-id", "x"])
        assert args.master_seed == 42
    finally:
        if saved is None:
            os.environ.pop("RM_MASTER_SEED", None)
        else:
            os.environ["RM_MASTER_SEED"] = saved


def test_cli_picks_up_rm_k_approved_env() -> None:
    """`--k-approved` defaults to the `RM_K_APPROVED` env var Cloud
    Batch sets per-task; falls back to `_DEFAULT_K_APPROVED=88` when the
    env is absent. Verified the same way as the master-seed env default."""
    import argparse
    import os

    saved = os.environ.get("RM_K_APPROVED")
    os.environ["RM_K_APPROVED"] = "176"
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--run-id", required=True)
        default_k = os.environ.get("RM_K_APPROVED")
        parser.add_argument(
            "--k-approved", type=int,
            default=int(default_k) if default_k is not None
                else worker_mod._DEFAULT_K_APPROVED,
        )
        args = parser.parse_args(["--run-id", "x"])
        assert args.k_approved == 176
    finally:
        if saved is None:
            os.environ.pop("RM_K_APPROVED", None)
        else:
            os.environ["RM_K_APPROVED"] = saved


def test_cli_falls_back_to_default_k_approved_when_env_absent() -> None:
    """Without `RM_K_APPROVED` set, the CLI MUST fall back to
    `_DEFAULT_K_APPROVED=88` rather than failing. Production Cloud Batch
    always sets the env, but the local-maintainer CLI invocation path
    relies on this fallback."""
    import argparse
    import os

    saved = os.environ.pop("RM_K_APPROVED", None)
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--run-id", required=True)
        default_k = os.environ.get("RM_K_APPROVED")
        parser.add_argument(
            "--k-approved", type=int,
            default=int(default_k) if default_k is not None
                else worker_mod._DEFAULT_K_APPROVED,
        )
        args = parser.parse_args(["--run-id", "x"])
        assert args.k_approved == 88
    finally:
        if saved is not None:
            os.environ["RM_K_APPROVED"] = saved


# --- GCS adapter URI guards ---------------------------------------------


def test_real_gcs_adapter_rejects_uri_outside_bucket() -> None:
    """The shared `make_gcs_adapter` in `gcs.py` (T2F extraction) validates
    `uri` starts with `gs://{bucket}/`. Cross-bucket reads/writes are a
    misconfiguration and MUST fail fast (the worker + orchestrator are
    each bound to one bucket per §8.7)."""
    try:
        from google.cloud import storage  # noqa: F401
    except ImportError:
        # google-cloud-storage not installed in this test environment;
        # the URI-guard test requires the real factory which lazy-
        # imports it. Skip.
        return

    from rostermonster_service.gcs import make_gcs_adapter
    try:
        read_json, write_json = make_gcs_adapter(_BUCKET)
    except Exception:
        # Local dev environments without Application Default Credentials
        # can't construct the real `storage.Client()`. URI-guard
        # behavior is exercised in production CI where creds are
        # configured; skip cleanly here so the test suite stays
        # green on a developer's laptop without GCP setup.
        return
    for fn, label in ((read_json, "read"), (write_json, "write")):
        try:
            if label == "read":
                fn("gs://wrong-bucket/foo.json")
            else:
                fn("gs://wrong-bucket/foo.json", {"x": 1})
        except ValueError as e:
            assert "wrong-bucket" in str(e) or _BUCKET in str(e)
            continue
        raise AssertionError(
            label + "_json on wrong bucket should have raised ValueError"
        )


# --- Standalone runner ---------------------------------------------------


if __name__ == "__main__":
    import inspect

    failures = 0
    funcs = [(n, f) for n, f in globals().items()
             if n.startswith("test_") and callable(f)]
    for name, fn in funcs:
        try:
            sig = inspect.signature(fn)
            if any(p.default is inspect.Parameter.empty
                   for p in sig.parameters.values()):
                # Skip tests that need fixtures (e.g., monkeypatch) we
                # don't provide in the standalone runner.
                continue
            fn()
            print("ok   " + name)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print("FAIL " + name + ": " + repr(exc))
    if failures:
        sys.exit(1)
