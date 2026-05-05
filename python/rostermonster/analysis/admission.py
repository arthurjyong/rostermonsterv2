"""Fail-loud analyzer admission checks per `docs/analysis_contract.md`
§9.1 / §9.2 / §9.5 + §11 K-bounds + §10.0 doctorId resolvability.

Mirrors the parser/normalizer fail-loud discipline (D-0038): mismatched
or out-of-range inputs raise a structured `AnalyzerInputError` at
admission rather than silently producing degenerate output.
"""

from __future__ import annotations

from typing import Any

from rostermonster.selector.result import RetentionMode

# K bounds per §11 step 5 + step 6.
TOP_K_MIN = 1
TOP_K_MAX = 20


class AnalyzerInputError(Exception):
    """Structured rejection for analyzer input violations.

    Surfaces enough detail for the operator to identify which file is
    mismatched per §9.5 ("snapshot.metadata.snapshotId = X;
    envelope.runEnvelope.snapshotRef = Y") so they can re-run with the
    correct triple.
    """


def validate_top_k(requested: int) -> None:
    """§11 step 5/6: K must be in `[1, 20]`. Out-of-range is fail-loud
    per D-0056."""
    if not isinstance(requested, int) or isinstance(requested, bool):
        raise AnalyzerInputError(
            f"top-K must be an integer; got {type(requested).__name__}"
        )
    if requested < TOP_K_MIN:
        raise AnalyzerInputError(
            f"top-K must be ≥ {TOP_K_MIN}; got {requested}"
        )
    if requested > TOP_K_MAX:
        raise AnalyzerInputError(
            f"top-K must be ≤ {TOP_K_MAX}; got {requested}"
        )


def validate_full_retention(envelope: dict[str, Any]) -> None:
    """§9.1: analyzer MUST be invoked against a FULL-retention envelope.
    BEST_ONLY is fail-loud — the FULL sidecar would be absent and there
    is no top-K to compute."""
    final = envelope.get("finalResultEnvelope")
    if not isinstance(final, dict):
        raise AnalyzerInputError(
            "envelope is missing 'finalResultEnvelope' field"
        )
    mode = final.get("retentionMode")
    if mode != RetentionMode.FULL.value:
        raise AnalyzerInputError(
            f"analyzer requires retentionMode == FULL; got {mode!r} "
            f"(BEST_ONLY rejected per analysis_contract §9.1)"
        )


def validate_success_branch(envelope: dict[str, Any]) -> None:
    """§9.2: analyzer rejects the failure branch fail-loud.

    Detection: an `UnsatisfiedResultEnvelope` payload carries
    `unfilledDemand` + `reasons`; an `AllocationResult` carries
    `winnerAssignment` + `winnerScore`. If `winnerAssignment` is absent
    we treat that as the failure branch.
    """
    final = envelope.get("finalResultEnvelope")
    if not isinstance(final, dict):
        raise AnalyzerInputError(
            "envelope is missing 'finalResultEnvelope' field"
        )
    result = final.get("result")
    if not isinstance(result, dict):
        raise AnalyzerInputError(
            "envelope.finalResultEnvelope is missing 'result' field"
        )
    if "winnerAssignment" not in result:
        # UnsatisfiedResultEnvelope branch — analyzer rejects per §9.2.
        raise AnalyzerInputError(
            "analyzer requires the success branch (AllocationResult); "
            "got UnsatisfiedResultEnvelope per §9.2 — render via "
            "writeback's diagnostic surface instead"
        )


def validate_coherence(
    snapshot: dict[str, Any],
    envelope: dict[str, Any],
    full_sidecar: dict[str, Any],
) -> None:
    """§9.5: snapshot ↔ envelope ↔ sidecar coherence.

    Two checks:
    1. envelope.finalResultEnvelope.runEnvelope.snapshotRef ==
       snapshot.metadata.snapshotId
    2. fullSidecar.runId == envelope.finalResultEnvelope.runEnvelope.runId

    Mismatches are fail-loud per D-0038's discipline. Error messages
    surface both sides of the mismatch so the operator can diagnose
    which file is wrong.
    """
    snapshot_meta = snapshot.get("metadata")
    if not isinstance(snapshot_meta, dict):
        raise AnalyzerInputError(
            "snapshot.metadata is missing or not a JSON object"
        )
    snapshot_id = snapshot_meta.get("snapshotId")
    if not snapshot_id:
        raise AnalyzerInputError(
            "snapshot is missing metadata.snapshotId"
        )

    final = envelope.get("finalResultEnvelope")
    if not isinstance(final, dict):
        raise AnalyzerInputError(
            "envelope.finalResultEnvelope is missing or not a JSON object"
        )
    run_env = final.get("runEnvelope")
    if not isinstance(run_env, dict):
        raise AnalyzerInputError(
            "envelope.finalResultEnvelope.runEnvelope is missing or "
            "not a JSON object"
        )
    envelope_snapshot_ref = run_env.get("snapshotRef")
    envelope_run_id = run_env.get("runId")

    if not envelope_snapshot_ref:
        raise AnalyzerInputError(
            "envelope.finalResultEnvelope.runEnvelope.snapshotRef is "
            "missing; cannot validate snapshot↔envelope coherence"
        )
    if envelope_snapshot_ref != snapshot_id:
        raise AnalyzerInputError(
            f"snapshot↔envelope coherence violated: "
            f"snapshot.metadata.snapshotId = {snapshot_id!r}; "
            f"envelope.finalResultEnvelope.runEnvelope.snapshotRef = "
            f"{envelope_snapshot_ref!r}"
        )

    if not envelope_run_id:
        raise AnalyzerInputError(
            "envelope.finalResultEnvelope.runEnvelope.runId is missing; "
            "cannot validate envelope↔sidecar coherence"
        )
    sidecar_run_id = full_sidecar.get("runId")
    if not sidecar_run_id:
        raise AnalyzerInputError(
            "fullSidecar.runId is missing; cannot validate "
            "envelope↔sidecar coherence"
        )
    if sidecar_run_id != envelope_run_id:
        raise AnalyzerInputError(
            f"envelope↔sidecar coherence violated: "
            f"envelope.finalResultEnvelope.runEnvelope.runId = "
            f"{envelope_run_id!r}; "
            f"fullSidecar.runId = {sidecar_run_id!r}"
        )


def validate_non_empty_candidates(full_sidecar: dict[str, Any]) -> None:
    """Reject success-branch envelopes paired with empty
    `fullSidecar.candidates`.

    A coherent FULL-retention success-branch envelope never emits zero
    candidates — the upstream pipeline routes empty results to the
    failure branch (UnsatisfiedResultEnvelope) which §9.2 already
    rejects. An empty `candidates` array therefore signals a
    truncated/manually-mixed sidecar that slipped past `runId`
    coherence; the analyzer fails-loud rather than producing
    degenerate output (e.g., misclassifying every day as HOT with
    `distinctAssignments=0`).
    """
    candidates = full_sidecar.get("candidates")
    if not isinstance(candidates, list):
        raise AnalyzerInputError(
            "fullSidecar.candidates is missing or not a list"
        )
    if len(candidates) == 0:
        raise AnalyzerInputError(
            "fullSidecar.candidates is empty; success-branch envelope "
            "cannot have zero candidates (failure branch is rejected "
            "separately per §9.2). Likely a truncated or mixed sidecar."
        )


def validate_doctor_resolvability(
    snapshot: dict[str, Any],
    full_sidecar: dict[str, Any],
) -> None:
    """§10.0: every sidecar `doctorId` MUST appear as a key in the
    analyzer's constructed `doctorIdMap`. Snapshot↔sidecar doctor-
    identity drift is a producer defect; analyzer surfaces it fail-loud.
    """
    doctor_keys = {
        rec.get("sourceDoctorKey")
        for rec in snapshot.get("doctorRecords", [])
    }
    candidates = full_sidecar.get("candidates", [])
    if not isinstance(candidates, list):
        raise AnalyzerInputError(
            "fullSidecar.candidates is missing or not a list"
        )
    seen: set[Any] = set()
    for cand in candidates:
        for assignment in cand.get("assignments", []):
            doctor_id = assignment.get("doctorId")
            if doctor_id is None:
                continue
            seen.add(doctor_id)

    missing = sorted(
        x for x in seen
        if x not in doctor_keys
        # `doctorId == sourceDoctorKey` is the v1 identity rule per §10.0;
        # any sidecar doctorId without a matching snapshot doctor record
        # signals upstream drift.
    )
    if missing:
        raise AnalyzerInputError(
            f"sidecar references doctorId values not present in "
            f"snapshot.doctorRecords (snapshot↔sidecar doctor-identity "
            f"drift): {missing}"
        )


def admit(
    snapshot: dict[str, Any],
    envelope: dict[str, Any],
    full_sidecar: dict[str, Any],
    requested_top_k: int,
) -> None:
    """Run all admission checks in §9 + §10.0 + §11 order.

    Order matters: validate cheap structural fields first (top-K,
    retention, success-branch) before expensive cross-file coherence.
    """
    validate_top_k(requested_top_k)
    validate_full_retention(envelope)
    validate_success_branch(envelope)
    validate_coherence(snapshot, envelope, full_sidecar)
    validate_non_empty_candidates(full_sidecar)
    validate_doctor_resolvability(snapshot, full_sidecar)
