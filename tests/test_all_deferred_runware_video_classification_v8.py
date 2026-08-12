from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from src.application import desktop_media_execution_v1 as desktop
from src.application import end_to_end_production_v1 as e2e


def _row(index: int) -> desktop.MediaQueueRow:
    return desktop.MediaQueueRow(
        queue_id=f"VID-V8-{index:03d}",
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


def test_multiple_terminal_rejections_ready_again_are_all_classified(
    monkeypatch,
    tmp_path,
):
    rows = tuple(_row(i) for i in range(1, 7))
    rejected = {"VID-V8-002", "VID-V8-004", "VID-V8-006"}
    final_rows = tuple(
        desktop.MediaQueueRow(
            queue_id=qid,
            queue_index=int(qid[-3:]),
            media_kind="RUNWARE_VIDEO",
            source_id="SH-X",
            provider="RUNWARE",
            model_or_voice="google:veo@3.1-lite",
            status="READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED",
            maximum_authorized_usd=0.10,
            output_path_relative="out/x.mp4",
        )
        for qid in sorted(rejected)
    )
    calls = {"count": 0}
    started = []
    lock = threading.Lock()

    def fake_pending(_repo):
        calls["count"] += 1
        if calls["count"] == 1:
            return rows
        return final_rows

    def fake_execute(
        _repo,
        queue_id,
        _key,
        *,
        confirmed_maximum_usd,
        recovery_only=False,
        progress=None,
    ):
        with lock:
            started.append(queue_id)
        time.sleep(0.02)
        if queue_id in rejected:
            raise desktop.DesktopMediaExecutionError(
                "RUNWARE_TERMINAL_PROVIDER_REJECTION_"
                "REAUTHORIZATION_REQUIRED:invalidProviderContent"
            )
        row = next(x for x in rows if x.queue_id == queue_id)
        return _result(row)

    monkeypatch.setattr(e2e, "_pending_rows", fake_pending)
    monkeypatch.setattr(e2e, "execute_runware_item", fake_execute)

    with pytest.raises(
        e2e.EndToEndProductionError,
        match="TERMINAL_PROVIDER_REJECTIONS_REQUIRE_EXPLICIT_REAUTHORIZATION",
    ) as caught:
        e2e._execute_media_queue(
            tmp_path,
            runware_api_key="key",
            elevenlabs_api_key="",
            confirmed_maximum_usd=0.6,
            progress=None,
        )

    message = str(caught.value)
    for qid in rejected:
        assert qid in message
    assert "VID-V8-005" in started


def test_timeout_and_terminal_are_not_generic_blockers(
    monkeypatch,
    tmp_path,
):
    rows = tuple(_row(i) for i in range(1, 6))
    final_rows = (
        desktop.MediaQueueRow(
            queue_id="VID-V8-002",
            queue_index=2,
            media_kind="RUNWARE_VIDEO",
            source_id="SH-002",
            provider="RUNWARE",
            model_or_voice="google:veo@3.1-lite",
            status="SUBMISSION_LOCKED",
            maximum_authorized_usd=0.10,
            output_path_relative="out/2.mp4",
        ),
        desktop.MediaQueueRow(
            queue_id="VID-V8-003",
            queue_index=3,
            media_kind="RUNWARE_VIDEO",
            source_id="SH-003",
            provider="RUNWARE",
            model_or_voice="google:veo@3.1-lite",
            status="READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED",
            maximum_authorized_usd=0.10,
            output_path_relative="out/3.mp4",
        ),
    )
    calls = {"count": 0}

    def fake_pending(_repo):
        calls["count"] += 1
        return rows if calls["count"] == 1 else final_rows

    def fake_execute(
        _repo,
        queue_id,
        _key,
        *,
        confirmed_maximum_usd,
        recovery_only=False,
        progress=None,
    ):
        if queue_id == "VID-V8-002":
            raise desktop.DesktopMediaExecutionError(
                "RUNWARE_POLL_TIMEOUT_USE_RECOVERY"
            )
        if queue_id == "VID-V8-003":
            raise desktop.DesktopMediaExecutionError(
                "RUNWARE_TERMINAL_PROVIDER_REJECTION_"
                "REAUTHORIZATION_REQUIRED:invalidProviderContent"
            )
        return _result(next(x for x in rows if x.queue_id == queue_id))

    monkeypatch.setattr(e2e, "_pending_rows", fake_pending)
    monkeypatch.setattr(e2e, "execute_runware_item", fake_execute)

    with pytest.raises(
        e2e.EndToEndProductionError,
        match="RUNWARE_RECOVERY_REQUIRED_AFTER_AUTHORIZED_RUN",
    ):
        e2e._execute_media_queue(
            tmp_path,
            runware_api_key="key",
            elevenlabs_api_key="",
            confirmed_maximum_usd=0.5,
            progress=None,
        )
