from __future__ import annotations

import json
from pathlib import Path

from src.application.desktop_provider_execution_v1 import (
    _siraj_runware_terminal_http_error_v1,
)


TASK_UUID = "9a6e7ed8-406a-4623-8f26-bf048ed0943d"


def _body():
    return {
        "data": [],
        "errors": [
            {
                "code": "invalidProviderContent",
                "message": (
                    "Invalid content detected. The generated content was flagged "
                    "and rejected by Google's content moderation system."
                ),
                "responseContent": (
                    "Your current safety settings for people/face generation "
                    "filtered out 1 videos. You will not be charged for blocked "
                    "videos. Try rephrasing the prompt."
                ),
                "taskUUID": TASK_UUID,
                "taskType": "videoInference",
                "status": "error",
            }
        ],
    }


def _write(root: Path, attempt: str, body: dict) -> Path:
    path = (
        root
        / "projects"
        / "fixture-episode"
        / "orchestration"
        / "paid-operation-attempts-v1"
        / attempt
        / "http-error-response.bin"
    )
    path.parent.mkdir(parents=True)
    path.write_bytes(json.dumps(body).encode("utf-8"))
    return path


def _task():
    return {
        "taskType": "videoInference",
        "taskUUID": TASK_UUID,
        "model": "google:veo@3.1-lite",
    }


def test_exact_veo_http400_body_is_terminal_safe_no_charge(tmp_path: Path):
    attempt = "poll-attempt"
    path = _write(tmp_path, attempt, _body())
    result = _siraj_runware_terminal_http_error_v1(
        repo_root=tmp_path,
        episode_id="fixture-episode",
        poll_attempt_id=attempt,
        task=_task(),
        expected_task_uuid=TASK_UUID,
        provider_operation_id=TASK_UUID,
    )
    assert result is not None
    assert result["status"] == "FAILED"
    assert result["submission_status"] == "PROVIDER_REJECTED_TERMINAL"
    assert result["provider_rejection_code"] == "invalidProviderContent"
    assert result["terminal_provider_rejection"] is True
    assert result["safe_to_reauthorize"] is True
    assert result["billable_output_detected"] is False
    assert result["explicit_no_charge_statement"] is True
    assert result["provider_error_task_uuid"] == TASK_UUID
    assert result["http_error_response_sha256"]
    assert path.is_file()


def test_taskuuid_mismatch_fails_closed(tmp_path: Path):
    attempt = "poll-attempt"
    body = _body()
    body["errors"][0]["taskUUID"] = "11111111-1111-4111-8111-111111111111"
    _write(tmp_path, attempt, body)
    result = _siraj_runware_terminal_http_error_v1(
        repo_root=tmp_path,
        episode_id="fixture-episode",
        poll_attempt_id=attempt,
        task=_task(),
        expected_task_uuid=TASK_UUID,
        provider_operation_id=TASK_UUID,
    )
    assert result is None


def test_missing_explicit_no_charge_fails_closed(tmp_path: Path):
    attempt = "poll-attempt"
    body = _body()
    body["errors"][0]["responseContent"] = "Blocked by content moderation."
    _write(tmp_path, attempt, body)
    result = _siraj_runware_terminal_http_error_v1(
        repo_root=tmp_path,
        episode_id="fixture-episode",
        poll_attempt_id=attempt,
        task=_task(),
        expected_task_uuid=TASK_UUID,
        provider_operation_id=TASK_UUID,
    )
    assert result is None


def test_any_materialized_data_fails_closed(tmp_path: Path):
    attempt = "poll-attempt"
    body = _body()
    body["data"] = [
        {
            "taskUUID": TASK_UUID,
            "status": "success",
            "videoURL": "https://example.invalid/output.mp4",
        }
    ]
    _write(tmp_path, attempt, body)
    result = _siraj_runware_terminal_http_error_v1(
        repo_root=tmp_path,
        episode_id="fixture-episode",
        poll_attempt_id=attempt,
        task=_task(),
        expected_task_uuid=TASK_UUID,
        provider_operation_id=TASK_UUID,
    )
    assert result is None


def test_source_routes_poll_http_error_through_terminal_bridge():
    source = Path(
        "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    assert "SIRAJ_RUNWARE_HTTP400_TERMINAL_REJECTION_BRIDGE_V2" in source
    assert "_siraj_runware_terminal_http_error_v1(" in source
    assert "poll_request.immutable_attempt_id" in source
    assert "RUNWARE_TERMINAL_PROVIDER_REJECTION_" in source
    assert '"automatic_paid_retry": False' in source
    assert '"automatic_paid_resubmission": False' in source
