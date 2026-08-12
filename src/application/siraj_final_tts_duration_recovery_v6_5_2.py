from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.application.siraj_mp3_duration_v6_5_2 import (
    mp3_duration_seconds,
)

EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
QUEUE_REL = Path(
    "projects/episode-002-adam-temptation-fall-repentance/"
    "orchestration/final-tts-queue-v5-4-3.json"
)

class FinalTtsDurationRecoveryV652Error(RuntimeError):
    pass

def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise FinalTtsDurationRecoveryV652Error(
            "CANNOT_READ_JSON:" + str(path) + ":" + str(exc)
        ) from exc
    if not isinstance(value, dict):
        raise FinalTtsDurationRecoveryV652Error(
            "JSON_OBJECT_REQUIRED:" + str(path)
        )
    return value

def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temp, path)

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)
    return digest.hexdigest()

def recover_episode2_tts_durations(repo_root: Path) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    queue_path = repo / QUEUE_REL
    queue = _read(queue_path)

    if queue.get("status") != "COMPLETE":
        raise FinalTtsDurationRecoveryV652Error(
            "FINAL_TTS_QUEUE_NOT_COMPLETE:"
            + str(queue.get("status"))
        )

    items = queue.get("items")
    if not isinstance(items, list) or not items:
        raise FinalTtsDurationRecoveryV652Error(
            "FINAL_TTS_QUEUE_ITEMS_REQUIRED"
        )

    recovered = []
    preexisting = []

    for item in sorted(
        items,
        key=lambda value: int(
            value.get("queue_index", 0) or 0
        ),
    ):
        if not isinstance(item, dict):
            raise FinalTtsDurationRecoveryV652Error(
                "FINAL_TTS_QUEUE_ITEM_OBJECT_REQUIRED"
            )

        queue_id = str(item.get("queue_id") or "")
        if item.get("status") != "COMPLETE":
            raise FinalTtsDurationRecoveryV652Error(
                "FINAL_TTS_ITEM_NOT_COMPLETE:" + queue_id
            )

        relative = str(item.get("output_path_relative") or "")
        if not relative:
            raise FinalTtsDurationRecoveryV652Error(
                "FINAL_TTS_OUTPUT_PATH_REQUIRED:" + queue_id
            )
        output = repo / relative
        if not output.is_file() or output.stat().st_size <= 0:
            raise FinalTtsDurationRecoveryV652Error(
                "FINAL_TTS_OUTPUT_MISSING:" + queue_id
            )

        actual_sha = _sha256(output)
        expected_sha = str(item.get("output_sha256") or "")
        if expected_sha and expected_sha != actual_sha:
            raise FinalTtsDurationRecoveryV652Error(
                "FINAL_TTS_OUTPUT_SHA_MISMATCH:" + queue_id
            )

        existing = item.get("duration_seconds")
        if (
            isinstance(existing, (int, float))
            and float(existing) > 0
        ):
            duration = round(float(existing), 3)
            preexisting.append(queue_id)
        else:
            duration = mp3_duration_seconds(output)
            item["duration_seconds"] = duration
            recovered.append(queue_id)

        receipt_rel = str(item.get("receipt_path_relative") or "")
        if not receipt_rel:
            raise FinalTtsDurationRecoveryV652Error(
                "FINAL_TTS_RECEIPT_PATH_REQUIRED:" + queue_id
            )

        receipt_path = repo / receipt_rel
        receipt = _read(receipt_path)
        if receipt.get("output_sha256") not in (
            None,
            "",
            actual_sha,
        ):
            raise FinalTtsDurationRecoveryV652Error(
                "FINAL_TTS_RECEIPT_SHA_MISMATCH:" + queue_id
            )
        receipt["duration_seconds"] = duration
        _write(receipt_path, receipt)

    _write(queue_path, queue)

    report = {
        "schema_version": (
            "siraj-final-tts-duration-local-recovery-v6.5.2"
        ),
        "status": "PASS",
        "episode_id": EPISODE_ID,
        "queue_status": queue.get("status"),
        "queue_item_count": len(items),
        "recovered_duration_count": len(recovered),
        "preexisting_duration_count": len(preexisting),
        "recovered_queue_ids": recovered,
        "preexisting_queue_ids": preexisting,
        "network_calls": 0,
        "paid_provider_requests": 0,
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
        "duration_source": "PURE_PYTHON_MP3_FRAME_PARSER",
        "created_at_utc": _now(),
    }
    report_path = (
        repo
        / "projects"
        / EPISODE_ID
        / "orchestration"
        / "final-tts-duration-local-recovery-v6-5-2.json"
    )
    _write(report_path, report)
    report["report_path"] = str(report_path)
    return report

def recover_and_build_audio_timeline(
    repo_root: Path,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    recovery = recover_episode2_tts_durations(repo)

    from src.application.siraj_audio_timeline_v6_1 import (
        build_audio_timestamps_and_beats,
    )

    timeline_path = build_audio_timestamps_and_beats(
        repo,
        EPISODE_ID,
    )
    timeline = _read(timeline_path)
    if timeline.get("status") != "PASS":
        raise FinalTtsDurationRecoveryV652Error(
            "AUDIO_TIMELINE_NOT_PASS"
        )

    total = timeline.get("total_duration_seconds")
    if not isinstance(total, (int, float)) or total <= 0:
        raise FinalTtsDurationRecoveryV652Error(
            "AUDIO_TIMELINE_DURATION_INVALID"
        )

    return {
        **recovery,
        "audio_timeline_status": "PASS",
        "audio_timeline_path": str(timeline_path),
        "total_duration_seconds": float(total),
        "next_stage": timeline.get("next_stage"),
    }
