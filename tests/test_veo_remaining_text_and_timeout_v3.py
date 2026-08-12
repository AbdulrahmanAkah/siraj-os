from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from src.application import desktop_media_execution_v1 as desktop
from src.application import end_to_end_production_v1 as e2e


def _row(index: int) -> desktop.MediaQueueRow:
    return desktop.MediaQueueRow(
        queue_id=f"VID-TXT-{index:03d}",
        queue_index=index,
        media_kind="RUNWARE_VIDEO",
        source_id=f"SH-{index:03d}",
        provider="RUNWARE",
        model_or_voice="google:veo@3.1-lite",
        status="READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED",
        maximum_authorized_usd=0.10,
        output_path_relative=f"out/{index}.mp4",
    )


def _result(row: desktop.MediaQueueRow) -> desktop.MediaExecutionResult:
    return desktop.MediaExecutionResult(
        queue_id=row.queue_id,
        media_kind=row.media_kind,
        status="COMPLETE",
        output_path=Path(row.output_path_relative),
        receipt_path=Path("receipts") / f"{row.queue_id}.json",
        task_uuid=f"task-{row.queue_id}",
        actual_cost_usd=0.05,
        estimated_cost_usd=None,
    )


def test_provider_prompt_removes_arabic_and_visible_text_instructions():
    task, cert = desktop._siraj_prepare_veo_final_submission_v1(
        {
            "taskType": "videoInference",
            "model": "google:veo@3.1-lite",
            "positivePrompt": (
                "Polished obsidian reflections. "
                "The exact supplied Arabic word «أنا» is legible in each "
                "reflection. Successive reflections enlarge the word. "
                "Finish with stable negative space for supplied warning text. "
                "Camera moves right to left with controlled parallax."
            ),
            "negativePrompt": (
                "faces, bodies, misspelled Arabic, illegible text"
            ),
            "providerSettings": {
                "google": {
                    "generateAudio": False,
                    "personGeneration": "dont_allow",
                }
            },
        },
        {"status": "PASS"},
        "VID-SH-048-C03",
    )
    prompt = task["positivePrompt"]
    tokens = desktop._siraj_veo_prompt_tokens_v2(prompt)
    assert not desktop._SIRAJ_ARABIC_CHAR_RE_V3.search(prompt)
    assert not (tokens & desktop._SIRAJ_VEO_VISIBLE_TEXT_TOKENS_V3)
    assert "controlled parallax" in prompt
    assert "obsidian" in tokens
    assert "clean unbranded surfaces" in prompt
    assert "reflection" not in tokens
    assert "reflections" not in tokens
    assert cert is not None
    assert cert["provider_visible_text_generation"] == "FORBIDDEN"
    assert cert["deterministic_text_overlay_required"] is True


def test_poll_timeout_does_not_prevent_next_wave(monkeypatch, tmp_path):
    rows = tuple(_row(i) for i in range(1, 6))
    locked = desktop.MediaQueueRow(
        queue_id="VID-TXT-002",
        queue_index=2,
        media_kind="RUNWARE_VIDEO",
        source_id="SH-002",
        provider="RUNWARE",
        model_or_voice="google:veo@3.1-lite",
        status="SUBMISSION_LOCKED",
        maximum_authorized_usd=0.10,
        output_path_relative="out/2.mp4",
    )
    pending_calls = {"count": 0}
    started = []
    guard = threading.Lock()

    def fake_pending(_repo):
        pending_calls["count"] += 1
        if pending_calls["count"] == 1:
            return rows
        return (locked,)

    def fake_execute(
        _repo,
        queue_id,
        _key,
        *,
        confirmed_maximum_usd,
        recovery_only=False,
        progress=None,
    ):
        with guard:
            started.append(queue_id)
        time.sleep(0.03)
        if queue_id == "VID-TXT-002":
            raise desktop.DesktopMediaExecutionError(
                "RUNWARE_POLL_TIMEOUT_USE_RECOVERY"
            )
        row = next(value for value in rows if value.queue_id == queue_id)
        return _result(row)

    monkeypatch.setattr(e2e, "_pending_rows", fake_pending)
    monkeypatch.setattr(e2e, "execute_runware_item", fake_execute)

    with pytest.raises(
        e2e.EndToEndProductionError,
        match="RUNWARE_RECOVERY_REQUIRED_AFTER_AUTHORIZED_RUN",
    ):
        e2e._execute_media_queue(
            tmp_path,
            runware_api_key="test-key",
            elevenlabs_api_key="",
            confirmed_maximum_usd=0.5,
            progress=None,
        )
    assert "VID-TXT-005" in started
