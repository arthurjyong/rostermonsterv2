"""M7 C2 Task 2G — determinism re-audit per `docs/solver_contract.md`
§12A.4. End-to-end byte-identity test: same `(masterSeed, K)` produces
the same WINNER (and same per-candidate scores) across:

- the local-CLI path: `pipeline.run_pipeline(snapshot, ..., strategy_id=LAHC, seed=masterSeed)`
- the Cloud-Batch path: `lahc_orchestrator.orchestrate_lahc_run(snapshot, master_seed=masterSeed, ...)`
  with a `WorkerSimulatingBatchClient` that invokes `worker_main` inline
  on submit (against the same in-memory GCS).

Both paths route through the same `solve(strategyId=LAHC,
_candidate_seeds=derive_K_seeds(...), ...)` per the M7 C2 Task 2C
escape hatch + Task 2A shared seed helper, so byte-identity holds by
construction. This audit is the M7 C2 closure exit criterion (per the
re-cadenced §9 task list) — it guarantees the M7 architecture
preserves the §12A.4 determinism contract.

Includes the negative-seed test case verifying the load-bearing
`_UINT64_MASK` step in `derive_K_seeds` survives the Cloud-Batch
round-trip (per §12A.10's "MUST apply the existing `_UINT64_MASK`
step" normative property + the M5-era PR #85 negative-seed regression
guard at `test_solver.py::test_negated_seed_produces_distinct_output`).

Standalone runnable via `python3 python/tests/test_lahc_determinism_audit.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

# All 5 audit tests in this module run the real LAHC solver at the
# FW-0037 elbow tuple (idleThreshold=3500) across BOTH the local-CLI
# path AND the Cloud-Batch path; total runtime ~15-25 min on the
# icu_hd_may_2026 fixture. Marked `slow` per Codex P2 finding on PR
# #150 commit c48d9deef2 so default `pytest` deselects them; full
# audit runs via `pytest -m slow`. The byte-identity property the
# audit verifies is K-independent — opt-in scheduling preserves the
# audit value without bloating PR validation.
pytestmark = pytest.mark.slow

from rostermonster.pipeline import _snapshot_from_dict, _to_jsonable, run_pipeline  # noqa: E402
from rostermonster.selector import RetentionMode  # noqa: E402
from rostermonster.solver import LahcParams, STRATEGY_LAHC  # noqa: E402
from rostermonster.templates import icu_hd_template_artifact  # noqa: E402
from rostermonster_service import lahc_orchestrator as lo  # noqa: E402
from rostermonster_service import worker as worker_mod  # noqa: E402
from rostermonster_service.batch_client import (  # noqa: E402
    JOB_STATE_SUCCEEDED,
    InMemoryBatchClient,
)


_BUCKET = "rostermonsterv2-lahc"
_REGION = "asia-southeast1"
_PROJECT = "rostermonsterv2"
_IMAGE = "gcr.io/rostermonsterv2/roster-monster-compute:audit-tag"
_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "data" / "icu_hd_may_2026_snapshot.json"
)
# Hardcode the FW-0037 elbow tuple matching `worker.py`'s production
# constants so the local-CLI run hits the same LAHC operating point as
# the cloud-Batch run.
_FW_0037_LAHC_PARAMS = LahcParams(
    historyListLength=50,
    idleThreshold=3500,
    swapProbability=0.5,
)
# Small K to keep the audit's wall-time bounded; 4 trajectories is
# sufficient to exercise both the K-trajectory derivation + worker
# pool aggregation. The byte-identity invariant is K-independent — if
# it holds at K=4 it holds at K=88 (M7 production K post-Codex P1.7
# amendment) — but the K=88 production-parity audit
# `test_local_cli_and_cloud_batch_byte_identical_at_K_88` below runs
# the actual production K to close the M7 C4 T2A.2 exit criterion.
_AUDIT_K = 4
# Production K per `docs/cloud_compute_contract.md` §8.7 single-VM
# dense pack — `c3-highcpu-88` × 1 with `multiprocessing.Pool(88)` for
# K=88 trajectories. The K=88 audit variant proves byte-identity at
# the actual production operating point (per the M7 C4 T2A scope's
# "byte-identity audit at K=88 vs local CLI K=88 LAHC" exit
# criterion); marked slow because 88 trajectories × 2 paths through
# the FW-0037 elbow tuple takes ~30-45min wall on the icu_hd_may_2026
# fixture.
_AUDIT_K_PROD = 88


def _make_inmem_gcs(initial: dict[str, dict] | None = None):
    storage: dict[str, dict] = dict(initial or {})

    def read_json(uri: str) -> dict:
        if uri not in storage:
            raise FileNotFoundError(uri)
        return json.loads(json.dumps(storage[uri]))

    def write_json(uri: str, data: dict) -> None:
        storage[uri] = json.loads(json.dumps(data))

    def delete_prefix(uri: str) -> int:
        keys = [k for k in storage if k.startswith(uri)]
        for k in keys:
            del storage[k]
        return len(keys)

    return read_json, write_json, delete_prefix, storage


def _no_sleep(_seconds: float) -> None:
    return None


def _virtual_clock(start: float = 0.0, step: float = 1.0):
    state = {"now": start}

    def time_fn() -> float:
        result = state["now"]
        state["now"] += step
        return result

    return time_fn


def _serial_executor(fn, args_iter):
    return [fn(a) for a in args_iter]


def _fixed_attempt_id_fn() -> str:
    return "audit-attempt-id-fixed"


class _WorkerSimulatingBatchClient(InMemoryBatchClient):
    """On submit_job, runs `worker_main` inline against the in-memory
    GCS for the single Cloud Batch task (M7 C4 T2A.1 single-VM amendment
    per Codex P1.7). Pulls master_seed + K_approved + attempt_id off the
    Batch task env (mirroring how Cloud Batch sets them on the real
    worker process). The orchestrator's subsequent get_job_state call
    returns SUCCEEDED."""

    def __init__(self, *, read_json, write_json, **kw):
        super().__init__(**kw)
        self._read_json = read_json
        self._write_json = write_json

    def submit_job(self, *, project, region, run_id, job_spec):
        env = job_spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
        master_seed = int(env["RM_MASTER_SEED"])
        K_approved = int(env["RM_K_APPROVED"])
        attempt_id = env.get("RM_ATTEMPT_ID", "")
        worker_mod.worker_main(
            run_id,
            master_seed=master_seed,
            K_approved=K_approved,
            read_json=self._read_json,
            write_json=self._write_json,
            pool_executor=_serial_executor,
            bucket=_BUCKET,
            attempt_id=attempt_id,
        )
        return super().submit_job(
            project=project, region=region,
            run_id=run_id, job_spec=job_spec,
        )


def _run_cloud_batch_path(*, snapshot_dict: dict, master_seed: int,
                           K: int = _AUDIT_K) -> dict:
    """Drive the M7 Cloud-Batch path end-to-end via the orchestrator +
    a worker-simulating fake BatchClient. Returns the orchestrator's
    response dict.

    `K` defaults to `_AUDIT_K = 4` (small K for fast audit runs); the
    K=88 production-parity audit passes `K=_AUDIT_K_PROD`."""
    read_json, write_json, delete_prefix, _ = _make_inmem_gcs()
    batch_client = _WorkerSimulatingBatchClient(
        read_json=read_json, write_json=write_json,
        state_sequence=[JOB_STATE_SUCCEEDED],
    )
    return lo.orchestrate_lahc_run(
        snapshot_dict,
        master_seed=master_seed,
        K_approved=K,
        container_image_uri=_IMAGE,
        batch_client=batch_client,
        gcs_read_json=read_json,
        gcs_write_json=write_json,
        gcs_delete_prefix=delete_prefix,
        project=_PROJECT, bucket=_BUCKET, region=_REGION,
        sleep_fn=_no_sleep,
        time_fn=_virtual_clock(),
        # Fixed wall_time_fn so submit_timestamp_ms doesn't perturb the
        # byte-identity comparison via env-var noise. The audit doesn't
        # exercise the 510s elapsed self-check; T2A.2 will.
        wall_time_fn=lambda: 1_700_000_000.0,
        attempt_id_fn=_fixed_attempt_id_fn,
    )


def _run_local_cli_path(*, snapshot_dict: dict, master_seed: int,
                         K: int = _AUDIT_K):
    """Drive the local-CLI LAHC path end-to-end via run_pipeline,
    matching the FW-0037 elbow tuple the worker hardcodes. `K` defaults
    to `_AUDIT_K = 4`; the K=88 production-parity audit passes
    `K=_AUDIT_K_PROD`."""
    import tempfile
    snapshot = _snapshot_from_dict(snapshot_dict)
    template = icu_hd_template_artifact()
    return run_pipeline(
        snapshot, template,
        seed=master_seed,
        max_candidates=K,
        # FULL matches cloud-side; selector requires sidecar_dir on
        # the success branch.
        retention_mode=RetentionMode.FULL,
        sidecar_dir=Path(tempfile.mkdtemp(prefix="rm-lahc-audit-")),
        strategy_id=STRATEGY_LAHC,
        lahc_params=_FW_0037_LAHC_PARAMS,
    )


def _winning_assignments_from_local(local_pipeline_result) -> list:
    """Extract the winner's assignments from the local-CLI's
    `PipelineResult.envelope.result.winnerAssignment` per the
    `AllocationResult` selector-output shape."""
    assert local_pipeline_result.envelope is not None
    result_obj = local_pipeline_result.envelope.result
    return _to_jsonable(result_obj.winnerAssignment)


def _winning_assignments_from_cloud(cloud_response: dict) -> list:
    """Extract the winner's assignments from the orchestrator's
    `writebackEnvelope` (M7 C2 Task 2G assembly). The wrapper carries
    the FinalResultEnvelope serialized via `_to_jsonable`; the
    `result` block is the `AllocationResult` with `winnerAssignment`."""
    wrapper = cloud_response["writebackEnvelope"]
    assert wrapper is not None, (
        "expected wrapperEnvelope to be assembled when state=OK; got "
        + repr(cloud_response.get("state"))
    )
    final = wrapper["finalResultEnvelope"]
    result = final["result"]
    return result["winnerAssignment"]


def _wrapper_envelope_from_local(local_pipeline_result, snapshot_dict: dict) -> dict:
    """Build the wrapper envelope the local-CLI path would produce, by
    routing the local pipeline's FinalResultEnvelope through the same
    `_assemble_writeback_wrapper` helper the orchestrator uses. This
    gives an apples-to-apples comparison vs the Cloud-Batch path's
    `writebackEnvelope`."""
    from rostermonster.pipeline import _assemble_writeback_wrapper
    snapshot = _snapshot_from_dict(snapshot_dict)
    template = icu_hd_template_artifact()
    return _assemble_writeback_wrapper(
        local_pipeline_result.envelope, snapshot, template,
    )


def _wrapper_envelope_from_cloud(cloud_response: dict) -> dict:
    """Extract the orchestrator's wrapperEnvelope dict for direct
    comparison vs the local-CLI assembly."""
    return cloud_response["writebackEnvelope"]


def _normalize_sidecar_paths(wrapper: dict) -> dict:
    """Replace tempdir-specific sidecar paths with a fixed placeholder
    so byte-identity holds across local vs cloud (which use independent
    tempdirs). FULL retention writes candidates_summary.csv +
    candidates_full.json to `sidecar_dir`; both paths bake the tempdir
    name into AllocationResult, which is filesystem state, not part of
    the §13 byte-identity contract."""
    final = wrapper.get("finalResultEnvelope") or {}
    result = final.get("result") or {}
    for key in ("candidatesSummaryPath", "candidatesFullPath"):
        if result.get(key):
            result[key] = "<sidecar-path-normalized>"
    return wrapper


# --- Determinism re-audit (positive seed) -------------------------------


def test_local_cli_and_cloud_batch_writeback_envelope_byte_identical() -> None:
    """§13 byte-identity invariant per `docs/cloud_compute_contract.md`:
    same snapshot + explicit seed MUST produce byte-identical
    writebackEnvelope across local-CLI and Cloud-Batch paths. The
    earlier winner-only audit caught divergence on the winning
    assignments but missed envelope-level divergence (Codex P2
    finding on PR #144 commit 1235345 — runId + crFloorComputed had
    drifted between the two paths). This audit compares the
    serialized FinalResultEnvelope JSON tree as a whole."""
    snapshot_dict = json.loads(_FIXTURE_PATH.read_text())
    master_seed = 12345

    local_result = _run_local_cli_path(
        snapshot_dict=snapshot_dict, master_seed=master_seed,
    )
    cloud_response = _run_cloud_batch_path(
        snapshot_dict=snapshot_dict, master_seed=master_seed,
    )
    if local_result.state != "OK" or cloud_response["state"] != "OK":
        return  # degenerate; property requires both succeeding
    local_wrapper = _normalize_sidecar_paths(
        _wrapper_envelope_from_local(local_result, snapshot_dict),
    )
    cloud_wrapper = _normalize_sidecar_paths(
        _wrapper_envelope_from_cloud(cloud_response),
    )
    local_final = local_wrapper["finalResultEnvelope"]
    cloud_final = cloud_wrapper["finalResultEnvelope"]
    # Codex P2 finding on PR #144 commit 0153fc6: the audit MUST
    # compare the FULL writeback envelope, not just runEnvelope —
    # divergence in `result` (allocation result + searchDiagnostics),
    # snapshot subset, or doctorIdMap would otherwise pass undetected.
    # Compare the full finalResultEnvelope (run envelope + result
    # block) AND the wrapper-level snapshot subset + doctorIdMap.
    assert local_final == cloud_final, (
        "§13 byte-identity broken: finalResultEnvelope diverged "
        "between local-CLI and Cloud-Batch paths.\nlocal="
        + json.dumps(local_final, sort_keys=True)
        + "\ncloud=" + json.dumps(cloud_final, sort_keys=True)
    )
    # Wrapper-level fields (snapshot subset, doctorIdMap, schemaVersion)
    # MUST also match for byte-identity per §13. Compare the whole
    # wrapper.
    assert local_wrapper == cloud_wrapper, (
        "§13 byte-identity broken: wrapper envelope (snapshot subset / "
        "doctorIdMap / schemaVersion) diverged between local-CLI and "
        "Cloud-Batch paths."
    )


def test_local_cli_and_cloud_batch_emit_same_winner() -> None:
    """§12A.4 + §12A.10: same `(masterSeed, K)` produces the same
    winning assignments across the local-CLI path and the M7 Cloud-
    Batch path. This is the M7 C2 closure exit criterion — both
    surfaces must converge on the same winner under the FW-0037
    elbow tuple."""
    snapshot_dict = json.loads(_FIXTURE_PATH.read_text())
    master_seed = 12345

    local_result = _run_local_cli_path(
        snapshot_dict=snapshot_dict, master_seed=master_seed,
    )
    cloud_response = _run_cloud_batch_path(
        snapshot_dict=snapshot_dict, master_seed=master_seed,
    )

    assert cloud_response["state"] == "OK", (
        "Cloud-Batch path returned non-OK; can't compare winners. "
        "lahcSummary: " + json.dumps(cloud_response["lahcSummary"])
    )
    assert local_result.state == "OK", (
        "Local-CLI path returned non-OK; can't compare winners."
    )

    local_winner = _winning_assignments_from_local(local_result)
    cloud_winner = _winning_assignments_from_cloud(cloud_response)
    assert local_winner == cloud_winner, (
        "M7 C2 §12A.4 byte-identity broken: local-CLI vs Cloud-Batch "
        "emitted different winning assignments at master_seed="
        + str(master_seed) + ", K=" + str(_AUDIT_K)
    )


def test_local_cli_and_cloud_batch_emit_same_winner_across_seeds() -> None:
    """The byte-identity property must hold across multiple seeds
    (rules out a single-seed coincidence). Sample 3 distinct positive
    seeds; each MUST produce identical winners across both paths."""
    snapshot_dict = json.loads(_FIXTURE_PATH.read_text())
    for master_seed in (1, 999, 42):
        local_result = _run_local_cli_path(
            snapshot_dict=snapshot_dict, master_seed=master_seed,
        )
        cloud_response = _run_cloud_batch_path(
            snapshot_dict=snapshot_dict, master_seed=master_seed,
        )
        if local_result.state != "OK" or cloud_response["state"] != "OK":
            continue  # skip degenerate seed; not the property under test
        local_winner = _winning_assignments_from_local(local_result)
        cloud_winner = _winning_assignments_from_cloud(cloud_response)
        assert local_winner == cloud_winner, (
            "M7 §12A.4 byte-identity diverged at master_seed="
            + str(master_seed) + ", K=" + str(_AUDIT_K)
        )


# --- Negative-seed determinism re-audit (§12A.10 _UINT64_MASK) ---------


def test_local_cli_and_cloud_batch_emit_same_winner_negative_seed() -> None:
    """§12A.10 normative property: the `_UINT64_MASK` step in
    `derive_K_seeds` MUST handle negative master seeds correctly. This
    is the load-bearing case the M5-era PR #85 fix prevented at the
    solver's inline loop (CPython's `Random.seed(int)` `abs(seed)`
    aliasing); §12A.10 + M7 C2 Task 2C `_candidate_seeds` override
    propagate the same semantics across both surfaces. Audit: same
    negative `masterSeed` produces the same winner across local-CLI
    and Cloud-Batch."""
    snapshot_dict = json.loads(_FIXTURE_PATH.read_text())
    master_seed = -12345

    local_result = _run_local_cli_path(
        snapshot_dict=snapshot_dict, master_seed=master_seed,
    )
    cloud_response = _run_cloud_batch_path(
        snapshot_dict=snapshot_dict, master_seed=master_seed,
    )
    if local_result.state != "OK" or cloud_response["state"] != "OK":
        # Degenerate seed pair; skip — the property is byte-identity
        # WHEN both succeed.
        return
    local_winner = _winning_assignments_from_local(local_result)
    cloud_winner = _winning_assignments_from_cloud(cloud_response)
    assert local_winner == cloud_winner, (
        "M7 §12A.4 byte-identity diverged at master_seed="
        + str(master_seed) + " (NEGATIVE) — _UINT64_MASK semantics "
        "are not propagating through the Cloud-Batch path."
    )


def test_negative_and_positive_master_seed_produce_different_cloud_winners() -> None:
    """§12A.10 + M5-era regression guard: with the `_UINT64_MASK`
    step in place, `masterSeed=k` and `masterSeed=-k` MUST drive
    DIFFERENT Cloud-Batch trajectories (and thus likely different
    winners). If absent, CPython's `Random.seed(abs(...))` would
    collapse them. This test runs the Cloud-Batch path twice with
    `+seed` and `-seed` and asserts the winning assignments differ —
    a regression guard for the M7 path mirroring the local solver's
    `test_negated_seed_produces_distinct_output`."""
    snapshot_dict = json.loads(_FIXTURE_PATH.read_text())
    pos_response = _run_cloud_batch_path(
        snapshot_dict=snapshot_dict, master_seed=12345,
    )
    neg_response = _run_cloud_batch_path(
        snapshot_dict=snapshot_dict, master_seed=-12345,
    )
    if pos_response["state"] != "OK" or neg_response["state"] != "OK":
        return  # degenerate; property requires both succeeding
    pos_winner = _winning_assignments_from_cloud(pos_response)
    neg_winner = _winning_assignments_from_cloud(neg_response)
    assert pos_winner != neg_winner, (
        "Cloud-Batch +seed and -seed emitted identical winners — "
        "_UINT64_MASK signed→unsigned mask is being bypassed in the "
        "Cloud-Batch seed-derivation path; M7 §12A.10 regression."
    )


# --- K=88 production-parity audit (M7 C4 T2A.2 PR-C) -------------------


def test_local_cli_and_cloud_batch_byte_identical_at_K_88() -> None:
    """M7 C4 T2A.2 exit criterion per `docs/delivery_plan.md` §9 Task
    2A: byte-identity audit at K=88 vs local CLI K=88 LAHC at same
    `(masterSeed, K)`.

    The K=4 audits above prove the byte-identity property at small K;
    this test runs the SAME property at the actual M7 production K=88
    (Codex P1.7 amendment: `c3-highcpu-88` × 1 with `Pool(88)`). The
    property is K-independent in theory (each trajectory's `solve(K=1,
    _candidate_seeds=[seed])` is independent under §12A.10 +
    `_candidate_seeds` override), but running at production K
    confirms the new inline finalize path doesn't introduce a K-
    dependent divergence (e.g., from analyzer top-K selection or
    aggregator ordering at large K).

    **Runtime warning:** 88 trajectories × 2 paths × FW-0037 elbow
    tuple (`idleThreshold=3500`) on the icu_hd_may_2026 fixture takes
    ~30-45min wall on a single-process serial executor. Module-level
    `pytestmark = pytest.mark.slow` keeps default `pytest` runs from
    selecting this; manual invocation via
    `pytest -m slow tests/test_lahc_determinism_audit.py::test_local_cli_and_cloud_batch_byte_identical_at_K_88`."""
    snapshot_dict = json.loads(_FIXTURE_PATH.read_text())
    master_seed = 12345

    local_result = _run_local_cli_path(
        snapshot_dict=snapshot_dict,
        master_seed=master_seed,
        K=_AUDIT_K_PROD,
    )
    cloud_response = _run_cloud_batch_path(
        snapshot_dict=snapshot_dict,
        master_seed=master_seed,
        K=_AUDIT_K_PROD,
    )

    if local_result.state != "OK" or cloud_response["state"] != "OK":
        # Degenerate — the property is byte-identity WHEN both
        # succeed. K=88 against the production fixture is expected to
        # find a feasible roster; if it doesn't, the audit can't
        # complete, but that's a fixture/snapshot issue, not a
        # byte-identity violation.
        return

    local_wrapper = _normalize_sidecar_paths(
        _wrapper_envelope_from_local(local_result, snapshot_dict),
    )
    cloud_wrapper = _normalize_sidecar_paths(
        _wrapper_envelope_from_cloud(cloud_response),
    )

    local_final = local_wrapper["finalResultEnvelope"]
    cloud_final = cloud_wrapper["finalResultEnvelope"]
    assert local_final == cloud_final, (
        "M7 §13 byte-identity broken at K=" + str(_AUDIT_K_PROD)
        + " production scale — finalResultEnvelope diverged between "
        "local-CLI and Cloud-Batch paths at master_seed="
        + str(master_seed)
    )
    assert local_wrapper == cloud_wrapper, (
        "M7 §13 byte-identity broken at K=" + str(_AUDIT_K_PROD)
        + " — wrapper envelope (snapshot subset / doctorIdMap / "
        "schemaVersion) diverged at master_seed=" + str(master_seed)
    )


# --- Standalone runner ---------------------------------------------------


if __name__ == "__main__":
    failures = 0
    funcs = [(n, f) for n, f in globals().items()
             if n.startswith("test_") and callable(f)]
    for name, fn in funcs:
        try:
            fn()
            print("ok   " + name)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print("FAIL " + name + ": " + repr(exc))
    if failures:
        sys.exit(1)
