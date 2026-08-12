from __future__ import annotations

import json
from pathlib import Path

from src.application.siraj_live_telemetry_v6_6_r9 import (
    emit_event,
    live_paths,
    read_live_state,
    recent_events,
)
from src.application.siraj_runware_provider_contract_v6_6_r9 import (
    is_veo_31_model,
    sanitize_runware_task_for_submission,
)


def test_veo_lite_detected():
    assert is_veo_31_model("google:veo@3.1-lite")


def test_veo_air_ids_detected():
    assert is_veo_31_model("google:3@2")
    assert is_veo_31_model("google:3@3")


def test_non_veo_not_detected():
    assert not is_veo_31_model("runware:400@1")


def test_veo_negative_prompt_removed_and_folded():
    task = {
        "taskType": "videoInference",
        "model": "google:veo@3.1-lite",
        "positivePrompt": "A wide cinematic horizon.",
        "negativePrompt": "text, watermark, duplicate figures",
    }
    out = sanitize_runware_task_for_submission(task)
    assert "negativePrompt" not in out
    assert "text, watermark, duplicate figures" in out["positivePrompt"]
    assert "negativePrompt" in task  # queue draft remains immutable


def test_non_veo_negative_prompt_preserved():
    task = {"model": "other:model", "negativePrompt": "text"}
    out = sanitize_runware_task_for_submission(task)
    assert out["negativePrompt"] == "text"


def test_telemetry_state_and_events(tmp_path: Path):
    repo = tmp_path / "repo"
    ep = "episode-test"
    emit_event(
        repo,
        ep,
        "STAGE_STARTED",
        stage="PROVIDER_EXECUTION",
        message_ar="بدء المرحلة",
        progress_current=2,
        progress_total=10,
    )
    emit_event(
        repo,
        ep,
        "FILE_WRITTEN",
        stage="PROVIDER_EXECUTION",
        operation="حفظ الأصل",
        output_path="projects/episode-test/media/a.mp4",
        provider="RUNWARE",
        model="google:veo@3.1-lite",
        task_uuid="abc",
        request_current=1,
        request_total=4,
    )
    state = read_live_state(repo, ep)
    assert state is not None
    assert state["stage"] == "PROVIDER_EXECUTION"
    assert state["last_completed_file"].endswith("a.mp4")
    assert state["request_current"] == 1
    assert state["request_total"] == 4
    assert state["model"] == "google:veo@3.1-lite"
    rows = recent_events(repo, ep, 10)
    assert [x["event_type"] for x in rows] == ["STAGE_STARTED", "FILE_WRITTEN"]
    state_path, event_path = live_paths(repo, ep)
    assert state_path.is_file()
    assert event_path.is_file()
    json.loads(state_path.read_text(encoding="utf-8"))
