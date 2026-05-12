"""Tests for `python/rostermonster_service/batch_job_spec.py` —
M7 C4 T2A.1 single-task pattern per `docs/cloud_compute_contract.md`
§8.7 (post-Codex-P1.7 amendment).

Covers:
- `normalize_label_value()` Cloud Batch label-value normalization.
- `build_lahc_batch_job_spec()` single-task shape: taskCount=1,
  parallelism=1, machine c3-highcpu-88, maxRunDuration 660s,
  maxRetryCount 0, env vars (RM_MASTER_SEED / RM_K_APPROVED /
  RM_OPERATOR_EMAIL / RM_LAUNCHER_CALLBACK_URL / RM_SUBMIT_TIMESTAMP_MS
  / LAHC_BUCKET), labels.spreadsheet_id normalized.
"""
from __future__ import annotations

import re

import pytest

from rostermonster_service.batch_job_spec import (
    build_lahc_batch_job_spec,
    normalize_label_value,
)


# -------------------- normalize_label_value -------------------------

def test_normalize_label_value_lowercases_uppercase() -> None:
    assert normalize_label_value("AbCdEf") == "abcdef"


def test_normalize_label_value_replaces_non_alphanumeric_with_hyphen() -> None:
    assert normalize_label_value("foo@bar.com") == "foo-bar-com"


def test_normalize_label_value_preserves_hyphen_and_underscore() -> None:
    assert normalize_label_value("a_b-c") == "a_b-c"


def test_normalize_label_value_truncates_to_63_chars() -> None:
    raw = "x" * 100
    result = normalize_label_value(raw)
    assert len(result) == 63
    assert result == "x" * 63


def test_normalize_label_value_drive_spreadsheet_id_typical() -> None:
    raw = "10p2TvME4gmPB39PFCsmAB6tCrPo96zSbpnTvKKKOAvI"
    result = normalize_label_value(raw)
    assert result == "10p2tvme4gmpb39pfcsmab6tcrpo96zsbpntvkkkoavi"
    assert len(result) <= 63
    assert re.fullmatch(r"[a-z0-9_-]+", result)


def test_normalize_label_value_rejects_non_string() -> None:
    with pytest.raises(ValueError, match="label-value input must be a string"):
        normalize_label_value(123)  # type: ignore[arg-type]


def test_normalize_label_value_rejects_empty_result() -> None:
    with pytest.raises(ValueError, match="empty string"):
        normalize_label_value("")


def test_normalize_label_value_handles_all_invalid_chars_input() -> None:
    # All chars get replaced to '-'; result is non-empty so passes.
    result = normalize_label_value("@@@")
    assert result == "---"


# -------------------- build_lahc_batch_job_spec ---------------------

_BASE_KWARGS = dict(
    run_id="test-run",
    container_image_uri="gcr.io/project/img:tag",
    master_seed=12345,
    source_spreadsheet_id="SHEET_ID_xyz",
)


def test_spec_has_single_task_group() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS)
    assert len(spec["taskGroups"]) == 1


def test_spec_taskcount_is_one() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS)
    tg = spec["taskGroups"][0]
    assert tg["taskCount"] == 1
    assert tg["parallelism"] == 1
    assert tg["taskCountPerNode"] == 1


def test_spec_machine_type_is_c3_highcpu_88() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS)
    assert spec["allocationPolicy"]["instances"][0]["policy"]["machineType"] == "c3-highcpu-88"


def test_spec_max_run_duration_is_660s() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS)
    assert spec["taskGroups"][0]["taskSpec"]["maxRunDuration"] == "660s"


def test_spec_max_retry_count_is_zero() -> None:
    """Codex P2 round 8 amendment: retry × 660s = 1320s blows the 10-min cap."""
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS)
    assert spec["taskGroups"][0]["taskSpec"]["maxRetryCount"] == 0


def test_spec_provisioning_model_is_standard() -> None:
    """On-demand only per D-0070 sub-decision 4 — NOT Spot."""
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS)
    assert spec["allocationPolicy"]["instances"][0]["policy"]["provisioningModel"] == "STANDARD"


def test_spec_region_is_asia_southeast1() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS)
    assert spec["allocationPolicy"]["location"]["allowedLocations"] == ["regions/asia-southeast1"]


def test_spec_logs_destination_is_cloud_logging() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS)
    assert spec["logsPolicy"]["destination"] == "CLOUD_LOGGING"


def test_spec_compute_resource_claims_whole_vm() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS)
    cr = spec["taskGroups"][0]["taskSpec"]["computeResource"]
    assert cr["cpuMilli"] == 88000
    assert 100_000 <= cr["memoryMib"] <= 176_000


def test_spec_commands_invoke_worker_with_run_id() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS)
    cmd = spec["taskGroups"][0]["taskSpec"]["runnables"][0]["container"]["commands"]
    assert cmd[:5] == ["python", "-m", "rostermonster_service.worker", "--run-id", "test-run"]


def test_spec_image_uri_passed_through() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS)
    img = spec["taskGroups"][0]["taskSpec"]["runnables"][0]["container"]["imageUri"]
    assert img == "gcr.io/project/img:tag"


def test_spec_env_carries_master_seed_and_k() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS, K_approved=88)
    env = spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    assert env["RM_MASTER_SEED"] == "12345"
    assert env["RM_K_APPROVED"] == "88"


def test_spec_env_carries_negative_master_seed() -> None:
    spec = build_lahc_batch_job_spec(**{**_BASE_KWARGS, "master_seed": -42})
    env = spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    assert env["RM_MASTER_SEED"] == "-42"


def test_spec_env_carries_operator_email_when_set() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS, operator_email="op@example.com")
    env = spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    assert env["RM_OPERATOR_EMAIL"] == "op@example.com"


def test_spec_env_carries_empty_operator_email_for_compute_lahc_test() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS)
    env = spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    assert env["RM_OPERATOR_EMAIL"] == ""


def test_spec_env_carries_launcher_callback_url_when_set() -> None:
    spec = build_lahc_batch_job_spec(
        **_BASE_KWARGS,
        launcher_callback_url="https://script.google.com/macros/s/ID/exec",
    )
    env = spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    assert env["RM_LAUNCHER_CALLBACK_URL"] == "https://script.google.com/macros/s/ID/exec"


def test_spec_env_carries_empty_callback_url_for_compute_lahc_test() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS)
    env = spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    assert env["RM_LAUNCHER_CALLBACK_URL"] == ""


def test_spec_env_carries_submit_timestamp_ms() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS, submit_timestamp_ms=1234567890)
    env = spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    assert env["RM_SUBMIT_TIMESTAMP_MS"] == "1234567890"


def test_spec_env_carries_attempt_id_when_set() -> None:
    """Per Codex P2 round 2 finding 4: attempt_id closes the
    concurrent-replay overwrite race on the deterministic runId."""
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS, attempt_id="abc123def456")
    env = spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    assert env["RM_ATTEMPT_ID"] == "abc123def456"


def test_spec_env_carries_empty_attempt_id_when_not_provided() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS)
    env = spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    assert env["RM_ATTEMPT_ID"] == ""


def test_spec_env_carries_bucket() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS, bucket="custom-bucket")
    env = spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    assert env["LAHC_BUCKET"] == "custom-bucket"


def test_spec_default_bucket_is_production() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS)
    env = spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    assert env["LAHC_BUCKET"] == "rostermonsterv2-lahc"


def test_spec_labels_spreadsheet_id_normalized() -> None:
    """Per D-0071 sub-decision 8: labels.spreadsheet_id is the normalized
    form of source_spreadsheet_id."""
    spec = build_lahc_batch_job_spec(**{
        **_BASE_KWARGS, "source_spreadsheet_id": "AbCd_123.xyz",
    })
    assert spec["labels"]["spreadsheet_id"] == "abcd_123-xyz"


def test_spec_no_operator_email_label() -> None:
    """Operator email is NOT a label (emails contain @/. which fail GRM
    label validation [a-z0-9_-]{1,63})."""
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS, operator_email="op@example.com")
    assert "operator_email" not in spec["labels"]


# -------------------- Boundary validation ---------------------------

def test_run_id_must_be_non_empty_string() -> None:
    with pytest.raises(ValueError, match="run_id must be"):
        build_lahc_batch_job_spec(**{**_BASE_KWARGS, "run_id": ""})


def test_run_id_must_be_string() -> None:
    with pytest.raises(ValueError, match="run_id must be"):
        build_lahc_batch_job_spec(**{**_BASE_KWARGS, "run_id": 123})  # type: ignore[arg-type]


def test_container_image_uri_must_be_non_empty_string() -> None:
    with pytest.raises(ValueError, match="container_image_uri must be"):
        build_lahc_batch_job_spec(**{**_BASE_KWARGS, "container_image_uri": ""})


def test_master_seed_must_be_int() -> None:
    with pytest.raises(ValueError, match="master_seed must be"):
        build_lahc_batch_job_spec(**{**_BASE_KWARGS, "master_seed": 1.5})  # type: ignore[arg-type]


def test_master_seed_rejects_bool() -> None:
    """Bool is a subclass of int in Python — explicit rejection."""
    with pytest.raises(ValueError, match="master_seed must be"):
        build_lahc_batch_job_spec(**{**_BASE_KWARGS, "master_seed": True})


def test_source_spreadsheet_id_must_be_non_empty_string() -> None:
    with pytest.raises(ValueError, match="source_spreadsheet_id must be"):
        build_lahc_batch_job_spec(**{**_BASE_KWARGS, "source_spreadsheet_id": ""})


def test_operator_email_must_be_string() -> None:
    """operator_email may be empty (for /compute-lahc-test) but must be a string."""
    with pytest.raises(ValueError, match="operator_email must be"):
        build_lahc_batch_job_spec(**_BASE_KWARGS, operator_email=None)  # type: ignore[arg-type]


def test_submit_timestamp_ms_must_be_non_negative() -> None:
    with pytest.raises(ValueError, match="submit_timestamp_ms must be"):
        build_lahc_batch_job_spec(**_BASE_KWARGS, submit_timestamp_ms=-1)


def test_submit_timestamp_ms_zero_allowed_for_compute_lahc_test() -> None:
    spec = build_lahc_batch_job_spec(**_BASE_KWARGS, submit_timestamp_ms=0)
    env = spec["taskGroups"][0]["taskSpec"]["environment"]["variables"]
    assert env["RM_SUBMIT_TIMESTAMP_MS"] == "0"


def test_launcher_callback_url_must_be_string() -> None:
    with pytest.raises(ValueError, match="launcher_callback_url must be"):
        build_lahc_batch_job_spec(**_BASE_KWARGS, launcher_callback_url=None)  # type: ignore[arg-type]


def test_attempt_id_must_be_string() -> None:
    with pytest.raises(ValueError, match="attempt_id must be"):
        build_lahc_batch_job_spec(**_BASE_KWARGS, attempt_id=None)  # type: ignore[arg-type]


def test_K_approved_must_be_positive() -> None:
    with pytest.raises(ValueError, match="K_approved must be"):
        build_lahc_batch_job_spec(**_BASE_KWARGS, K_approved=0)


def test_K_approved_must_be_int() -> None:
    with pytest.raises(ValueError, match="K_approved must be"):
        build_lahc_batch_job_spec(**_BASE_KWARGS, K_approved=1.5)  # type: ignore[arg-type]


def test_bucket_must_be_non_empty_string() -> None:
    with pytest.raises(ValueError, match="bucket must be"):
        build_lahc_batch_job_spec(**_BASE_KWARGS, bucket="")


def test_per_task_max_retry_count_must_be_non_negative() -> None:
    with pytest.raises(ValueError, match="per_task_max_retry_count must be"):
        build_lahc_batch_job_spec(**_BASE_KWARGS, per_task_max_retry_count=-1)
