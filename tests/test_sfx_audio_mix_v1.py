from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.application.sfx_audio_mix_v1 as audio
from src.application.sfx_audio_mix_v1 import (
    AudioEnvironment,
    SfxAudioMixError,
    build_sfx_audio_plan,
    classify_sfx_cue,
    run_sfx_audio_mix,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _environment(tmp_path: Path) -> AudioEnvironment:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffprobe = tmp_path / "ffprobe.exe"
    ffmpeg.write_bytes(b"x")
    ffprobe.write_bytes(b"x")
    return AudioEnvironment(
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        ffmpeg_version_line="ffmpeg test",
        available_filters=audio.REQUIRED_FILTERS,
        missing_filters=(),
    )


def _prepare(tmp_path: Path) -> tuple[str, Path]:
    episode_id = "episode-002-test"
    root = tmp_path / "projects" / episode_id
    _write(
        tmp_path
        / "projects/_orchestrator/"
        "autonomous-episode-orchestrator-state-v1.json",
        {
            "current_episode_id": episode_id,
            "status": "MEDIA_ASSETS_COMPLETE",
            "stage": "SFX_DESIGN",
        },
    )

    durations = [18.0] * 69 + [78.0]
    shots = []
    for index, duration in enumerate(durations, start=1):
        cues = []
        if index == 1:
            cues = ["رياح خفيفة تمر في فضاء واسع"]
        elif index == 2:
            cues = ["دوي اصطدام عميق وقصير"]
        shots.append(
            {
                "queue_index": index,
                "shot_id": f"SH-{index:03d}",
                "sequence_id": f"SEQ-{(index - 1) // 5 + 1:02d}",
                "segment_ids": [
                    "SEG-001" if index <= 35 else "SEG-002"
                ],
                "editorial_duration_seconds": duration,
                "sfx_cues_ar": cues,
                "sound_policy": "SFX_ONLY_NO_MUSIC",
            }
        )
    _write(
        root / "cinematic/storyboard-and-media-plan-v1.json",
        {
            "episode_id": episode_id,
            "shots": shots,
            "music": "FORBIDDEN",
        },
    )
    _write(
        root / "script/episode-script-v1.json",
        {
            "episode_id": episode_id,
            "segments": [
                {"segment_id": "SEG-001"},
                {"segment_id": "SEG-002"},
            ],
            "music": "FORBIDDEN",
        },
    )

    tts_items = []
    for index, segment_id in enumerate(("SEG-001", "SEG-002"), start=1):
        relative = (
            f"projects/{episode_id}/audio/tts/"
            f"{segment_id}-B01.mp3"
        )
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        tts_items.append(
            {
                "queue_id": f"TTS-{segment_id}-B01",
                "queue_index": index,
                "segment_id": segment_id,
                "block_id": "VB-01",
                "speaker_key": "NARRATOR",
                "voice_slot": "PRIMARY",
                "status": "COMPLETE",
                "output_path_relative": relative,
            }
        )

    def complete_item(queue_id: str, index: int) -> dict:
        return {
            "queue_id": queue_id,
            "queue_index": index,
            "status": "COMPLETE",
        }

    _write(
        root / "orchestration/media-production-queue-v1.json",
        {
            "episode_id": episode_id,
            "queues": {
                "runware_images": [complete_item("IMG-1", 1)],
                "runware_videos": [complete_item("VID-1", 2)],
                "local_graphics": [complete_item("GFX-1", 3)],
                "elevenlabs_tts": tts_items,
            },
        },
    )
    _write(
        root / "orchestration/stage-ledger-v1.json",
        {
            "episode_id": episode_id,
            "stages": [
                {"order": 1, "stage": "SFX_DESIGN", "status": "QUEUED"},
                {
                    "order": 2,
                    "stage": "STRUCTURAL_MONTAGE",
                    "status": "QUEUED",
                },
            ],
        },
    )
    return episode_id, root


def test_classification_covers_arabic_cues() -> None:
    assert classify_sfx_cue("صوت رياح بعيدة") == "AMBIENCE_WIND"
    assert classify_sfx_cue("خطوات على التراب") == "FOOTSTEPS"
    assert classify_sfx_cue("ماء يجري") == "WATER"


def test_plan_builds_timeline_and_local_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode_id, _ = _prepare(tmp_path)
    monkeypatch.setattr(audio, "_probe_duration", lambda env, path: 21.0)
    plan = build_sfx_audio_plan(
        tmp_path,
        environment=_environment(tmp_path),
    )
    assert plan["episode_id"] == episode_id
    assert plan["episode_duration_seconds"] == 1320.0
    assert plan["music"] == "FORBIDDEN"
    assert len(plan["narration_clips"]) == 2
    assert len(plan["sfx_events"]) == 2
    assert plan["sfx_events"][0]["source_mode"] == "PROCEDURAL_LOCAL"
    assert plan["sfx_events"][0]["api_cost_usd"] == 0.0
    assert len(plan["authored_silence_shot_ids"]) == 68


def test_music_cue_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, root = _prepare(tmp_path)
    storyboard_path = root / "cinematic/storyboard-and-media-plan-v1.json"
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    storyboard["shots"][0]["sfx_cues_ar"] = ["موسيقى ملحمية"]
    _write(storyboard_path, storyboard)
    monkeypatch.setattr(audio, "_probe_duration", lambda env, path: 21.0)
    with pytest.raises(SfxAudioMixError, match="MUSIC_OR_MUSICAL_CUE_FORBIDDEN"):
        build_sfx_audio_plan(
            tmp_path,
            environment=_environment(tmp_path),
        )


def test_run_completes_and_advances_to_montage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode_id, root = _prepare(tmp_path)
    environment = _environment(tmp_path)
    monkeypatch.setattr(audio, "require_audio_environment", lambda repo: environment)
    monkeypatch.setattr(audio, "_probe_duration", lambda env, path: 21.0)

    def fake_render_event(repo, episode_root, env, event):
        output = repo / event["asset_path_relative"]
        receipt = repo / event["receipt_path_relative"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"sfx")
        _write(receipt, {"actual_cost_usd": 0.0})
        return output, receipt, {"actual_cost_usd": 0.0}

    def fake_mix(env, clips, output_path, duration, narration):
        del env, clips, duration, narration
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"stem")

    def fake_master(env, narration, sfx, wav, m4a, duration):
        del env, narration, sfx, duration
        wav.parent.mkdir(parents=True, exist_ok=True)
        wav.write_bytes(b"wav")
        m4a.write_bytes(b"m4a")

    monkeypatch.setattr(audio, "_render_event_asset", fake_render_event)
    monkeypatch.setattr(audio, "_mix_clips_to_stem", fake_mix)
    monkeypatch.setattr(audio, "_render_master", fake_master)

    result = run_sfx_audio_mix(tmp_path)
    assert result.episode_id == episode_id
    assert result.status == "SFX_MIX_READY"
    assert result.master_wav_path.is_file()

    state = json.loads(
        (
            tmp_path
            / "projects/_orchestrator/"
            "autonomous-episode-orchestrator-state-v1.json"
        ).read_text(encoding="utf-8")
    )
    assert state["status"] == "SFX_MIX_READY"
    assert state["stage"] == "STRUCTURAL_MONTAGE"
    assert state["next_stage"] == (
        "STRUCTURAL_MONTAGE_AND_FINAL_RENDER_V1"
    )

    ledger = json.loads(
        (root / "orchestration/stage-ledger-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["status"] == "SFX_MIX_READY"
    sfx_stage = next(
        item for item in ledger["stages"] if item["stage"] == "SFX_DESIGN"
    )
    assert sfx_stage["status"] == "COMPLETE"


def test_master_filter_uses_ducking_and_loudness() -> None:
    source = Path(audio.__file__).read_text(encoding="utf-8")
    assert "sidechaincompress" in source
    assert "loudnorm" in source
    assert "MASTER_TARGET_LUFS = -16.0" in source
    assert "MUSIC_TERMS" in source
