from pathlib import Path
import json
import hashlib

from src.application.siraj_mp3_duration_v6_5_2 import (
    mp3_duration_seconds,
)
from src.application.siraj_final_tts_duration_recovery_v6_5_2 import (
    recover_and_build_audio_timeline,
)

def _synthetic_mp3(path: Path, frames: int = 100):
    header = bytes.fromhex("FFFB9000")
    frame_length = 417
    frame = header + (b"\x00" * (frame_length - 4))
    path.write_bytes(frame * frames)

def test_pure_python_mp3_duration(tmp_path):
    path = tmp_path / "sample.mp3"
    _synthetic_mp3(path, 100)
    duration = mp3_duration_seconds(path)
    expected = round(100 * 1152 / 44100, 3)
    assert duration == expected

def test_local_recovery_and_timeline_without_provider(tmp_path):
    repo = tmp_path
    ep = (
        repo
        / "projects/episode-002-adam-temptation-fall-repentance"
    )
    orchestration = ep / "orchestration"
    audio_dir = ep / "audio"
    receipts = (
        orchestration
        / "final-tts-execution-v5-4-3/receipts"
    )
    orchestration.mkdir(parents=True)
    audio_dir.mkdir(parents=True)
    receipts.mkdir(parents=True)

    audio = audio_dir / "seg001.mp3"
    _synthetic_mp3(audio, 80)
    sha = hashlib.sha256(audio.read_bytes()).hexdigest()

    receipt_rel = (
        "projects/episode-002-adam-temptation-fall-repentance/"
        "orchestration/final-tts-execution-v5-4-3/receipts/"
        "EP002-FINAL-TTS-SEG-001-attempt-01-receipt.json"
    )
    receipt_path = repo / receipt_rel
    receipt_path.write_text(
        json.dumps(
            {
                "output_sha256": sha,
                "duration_seconds": None,
            }
        ),
        encoding="utf-8",
    )

    queue = {
        "status": "COMPLETE",
        "items": [
            {
                "queue_index": 1,
                "queue_id": "EP002-FINAL-TTS-SEG-001",
                "segment_id": "SEG001",
                "beat_id": "B001",
                "status": "COMPLETE",
                "output_path_relative": (
                    "projects/episode-002-adam-temptation-fall-repentance/"
                    "audio/seg001.mp3"
                ),
                "output_sha256": sha,
                "receipt_path_relative": receipt_rel,
                "duration_seconds": None,
                "pause_after_seconds": 0.25,
            }
        ],
    }
    (
        orchestration / "final-tts-queue-v5-4-3.json"
    ).write_text(
        json.dumps(queue),
        encoding="utf-8",
    )

    result = recover_and_build_audio_timeline(repo)
    assert result["paid_provider_requests"] == 0
    assert result["network_calls"] == 0
    assert result["recovered_duration_count"] == 1
    assert result["audio_timeline_status"] == "PASS"
    assert result["next_stage"] == "AUDIO_BOUND_STORYBOARD"
