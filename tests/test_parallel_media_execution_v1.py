from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from src.application import desktop_media_execution_v1 as desktop
from src.application import end_to_end_production_v1 as e2e


def _row(index: int) -> desktop.MediaQueueRow:
    return desktop.MediaQueueRow(
        queue_id=f"VID-TEST-{index:03d}",
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


def test_runware_executor_uses_bounded_parallelism(monkeypatch, tmp_path):
    rows = tuple(_row(i) for i in range(1, 9))
    pending_calls = {"count": 0}

    def fake_pending(_repo):
        pending_calls["count"] += 1
        return rows if pending_calls["count"] == 1 else ()

    lock = threading.Lock()
    active = 0
    peak = 0

    def fake_execute(
        _repo,
        queue_id,
        _key,
        *,
        confirmed_maximum_usd,
        recovery_only=False,
        progress=None,
    ):
        nonlocal active, peak
        row = next(value for value in rows if value.queue_id == queue_id)
        assert confirmed_maximum_usd == row.maximum_authorized_usd
        assert recovery_only is False
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.08)
        with lock:
            active -= 1
        return _result(row)

    monkeypatch.setattr(e2e, "_pending_rows", fake_pending)
    monkeypatch.setattr(e2e, "execute_runware_item", fake_execute)

    results, recovered = e2e._execute_media_queue(
        tmp_path,
        runware_api_key="test-key",
        elevenlabs_api_key="",
        confirmed_maximum_usd=0.8,
        progress=None,
    )

    assert len(results) == 8
    assert recovered == 0
    assert 2 <= peak <= e2e.RUNWARE_PARALLELISM
    assert e2e.RUNWARE_PARALLELISM == 4


def test_failed_wave_does_not_start_next_wave(monkeypatch, tmp_path):
    rows = tuple(_row(i) for i in range(1, 6))
    pending_calls = {"count": 0}
    started = []
    start_lock = threading.Lock()

    def fake_pending(_repo):
        pending_calls["count"] += 1
        return rows

    def fake_execute(
        _repo,
        queue_id,
        _key,
        *,
        confirmed_maximum_usd,
        recovery_only=False,
        progress=None,
    ):
        with start_lock:
            started.append(queue_id)
        time.sleep(0.04)
        if queue_id == "VID-TEST-002":
            raise desktop.DesktopMediaExecutionError(
                "SIMULATED_PROVIDER_REJECTION"
            )
        row = next(value for value in rows if value.queue_id == queue_id)
        return _result(row)

    monkeypatch.setattr(e2e, "_pending_rows", fake_pending)
    monkeypatch.setattr(e2e, "execute_runware_item", fake_execute)

    with pytest.raises(
        e2e.EndToEndProductionError,
        match="PARALLEL_RUNWARE_WAVE_FAILED",
    ):
        e2e._execute_media_queue(
            tmp_path,
            runware_api_key="test-key",
            elevenlabs_api_key="",
            confirmed_maximum_usd=0.5,
            progress=None,
        )

    assert set(started) == {
        "VID-TEST-001",
        "VID-TEST-002",
        "VID-TEST-003",
        "VID-TEST-004",
    }
    assert "VID-TEST-005" not in started


def test_atomic_queue_item_updates_do_not_lose_other_item(tmp_path):
    queue_path = tmp_path / "media-production-queue-v1.json"
    payload = {
        "queues": {
            "runware_images": [],
            "runware_videos": [
                {"queue_id": "A", "status": "READY"},
                {"queue_id": "B", "status": "READY"},
            ],
            "local_graphics": [],
            "elevenlabs_tts": [],
        }
    }
    queue_path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    barrier = threading.Barrier(2)

    def update(queue_id):
        barrier.wait()
        desktop._update_queue_item_atomic(
            queue_path,
            queue_id,
            updates={
                "status": "SUBMISSION_LOCKED",
                "task_uuid": f"task-{queue_id}",
            },
        )

    first = threading.Thread(target=update, args=("A",))
    second = threading.Thread(target=update, args=("B",))
    first.start()
    second.start()
    first.join(timeout=5)
    second.join(timeout=5)

    value = json.loads(queue_path.read_text(encoding="utf-8"))
    rows = {
        item["queue_id"]: item
        for item in value["queues"]["runware_videos"]
    }
    assert rows["A"]["status"] == "SUBMISSION_LOCKED"
    assert rows["B"]["status"] == "SUBMISSION_LOCKED"
    assert rows["A"]["task_uuid"] == "task-A"
    assert rows["B"]["task_uuid"] == "task-B"

def test_terminal_provider_rejection_is_deferred_and_next_wave_runs(monkeypatch, tmp_path):
    rows = tuple(_row(i) for i in range(1, 6))
    failed = desktop.MediaQueueRow(
        queue_id="VID-TEST-002", queue_index=2, media_kind="RUNWARE_VIDEO",
        source_id="SH-002", provider="RUNWARE", model_or_voice="google:veo@3.1-lite",
        status="FAILED_PROVIDER_REJECTED_REAUTHORIZATION_REQUIRED",
        maximum_authorized_usd=0.10, output_path_relative="out/2.mp4",
    )
    calls = {"n": 0}
    started = []
    lock = threading.Lock()
    def fake_pending(_repo):
        calls["n"] += 1
        return rows if calls["n"] == 1 else (failed,)
    def fake_execute(_repo, queue_id, _key, *, confirmed_maximum_usd, recovery_only=False, progress=None):
        with lock:
            started.append(queue_id)
        time.sleep(0.03)
        if queue_id == "VID-TEST-002":
            raise desktop.DesktopMediaExecutionError(
                "RUNWARE_TERMINAL_PROVIDER_REJECTION_REAUTHORIZATION_REQUIRED:invalidProviderContent"
            )
        row = next(v for v in rows if v.queue_id == queue_id)
        return _result(row)
    monkeypatch.setattr(e2e, "_pending_rows", fake_pending)
    monkeypatch.setattr(e2e, "execute_runware_item", fake_execute)
    with pytest.raises(e2e.EndToEndProductionError, match="TERMINAL_PROVIDER_REJECTIONS_REQUIRE_EXPLICIT_REAUTHORIZATION"):
        e2e._execute_media_queue(tmp_path, runware_api_key="key", elevenlabs_api_key="", confirmed_maximum_usd=0.5, progress=None)
    assert "VID-TEST-005" in started


def test_polling_terminal_rejection_is_persisted(monkeypatch, tmp_path):
    queue_path = tmp_path / "queue.json"
    lock_path = tmp_path / "lock.json"
    queue_path.write_text(json.dumps({"queues": {"runware_images": [], "runware_videos": [{"queue_id": "VID-X", "status": "SUBMISSION_LOCKED"}], "local_graphics": [], "elevenlabs_tts": []}}), encoding="utf-8")
    lock_path.write_text(json.dumps({"queue_id": "VID-X", "task_uuid": "00000000-0000-0000-0000-000000000001", "status": "SUBMITTED_POLLING"}), encoding="utf-8")
    def fake_poll(*args, **kwargs):
        raise desktop.DesktopMediaExecutionError("RUNWARE_HTTP_ERROR:400:invalidProviderContent:Google content moderation system:people/face generation filtered out")
    monkeypatch.setattr(desktop, "_poll_runware", fake_poll)
    with pytest.raises(desktop.DesktopMediaExecutionError, match="RUNWARE_TERMINAL_PROVIDER_REJECTION_REAUTHORIZATION_REQUIRED"):
        desktop._siraj_poll_runware_with_terminal_rejection_capture_v1(
            "key", "00000000-0000-0000-0000-000000000001", "RUNWARE_VIDEO",
            progress=None, task={"taskType": "videoInference", "model": "google:veo@3.1-lite"},
            queue_path=queue_path, queue_id="VID-X", lock_path=lock_path,
        )
    item = json.loads(queue_path.read_text(encoding="utf-8"))["queues"]["runware_videos"][0]
    assert item["status"] == "FAILED_PROVIDER_REJECTED_REAUTHORIZATION_REQUIRED"
