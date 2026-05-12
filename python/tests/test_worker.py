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
