from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.application.structural_montage_final_render_v1 as montage
from src.application.structural_montage_final_render_v1 import (
    MontageEnvironment,
    StructuralMontageError,
    build_motion_render_command,
    build_still_render_command,
    build_structural_montage_plan,
    run_structural_montage_final_render,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _environment(tmp_path: Path) -> MontageEnvironment:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffprobe = tmp_path / "ffprobe.exe"
    ffmpeg.write_bytes(b"x")
    ffprobe.write_bytes(b"x")
    return MontageEnvironment(
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        ffmpeg_version_line="ffmpeg test",
        available_filters=montage.REQUIRED_VIDEO_FILTERS,
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
            "status": "SFX_MIX_READY",
            "stage": "STRUCTURAL_MONTAGE",
        },
    )

    shots = []
    queue_images = []
    queue_videos = []
    queue_graphics = []
    durations = [18] * 69 + [78]
    for index, duration in enumerate(durations, start=1):
        shot_id = f"SH-{index:03d}"
        if index <= 44:
            treatment = "ANIMATED_STILL_COMPOSITING"
            relative = (
                f"projects/{episode_id}/cinematic/runware-images/"
                f"{shot_id}/attempt-01.jpg"
            )
            queue_images.append(
                {
                    "queue_id": f"IMG-{shot_id}",
                    "queue_index": index,
                    "shot_id": shot_id,
                    "status": "COMPLETE",
                    "output_path_relative": relative,
                }
            )
        elif index <= 64:
            treatment = "GENERATED_VIDEO"
            relative = (
                f"projects/{episode_id}/cinematic/runware-videos/"
                f"{shot_id}/attempt-01.mp4"
            )
            queue_videos.append(
                {
                    "queue_id": f"VID-{shot_id}",
                    "queue_index": index,
                    "shot_id": shot_id,
                    "status": "COMPLETE",
                    "output_path_relative": relative,
                }
            )
        else:
            treatment = "GRAPHICS"
            relative = (
                f"projects/{episode_id}/cinematic/graphics/outputs/"
                f"GFX-{index - 64:02d}.mp4"
            )
            queue_graphics.append(
                {
                    "queue_id": f"LOCAL-{shot_id}",
                    "queue_index": index,
                    "shot_id": shot_id,
                    "status": "COMPLETE",
                    "output_path_relative": relative,
                }
            )
        source = tmp_path / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes((shot_id + treatment).encode("utf-8"))
        shots.append(
            {
                "queue_index": index,
                "shot_id": shot_id,
                "sequence_id": f"SEQ-{(index - 1) // 5 + 1:02d}",
                "event_id": "EV-001",
                "segment_ids": ["SEG-001"],
                "label_ar": "لقطة اختبار",
                "dramatic_function_ar": "وظيفة درامية واضحة",
                "final_budget_treatment": treatment,
                "editorial_duration_seconds": duration,
                "planned_generated_video_seconds": (
                    8 if treatment == "GENERATED_VIDEO" else 0
                ),
                "sfx_cues_ar": [],
                "sound_policy": "SFX_ONLY_NO_MUSIC",
                "depicts_unseen_beings": False,
                "contains_music": False,
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
            "title_ar": "حلقة اختبار",
            "segments": [{"segment_id": "SEG-001"}],
            "music": "FORBIDDEN",
        },
    )
    _write(
        root / "orchestration/media-production-queue-v1.json",
        {
            "episode_id": episode_id,
            "queues": {
                "runware_images": queue_images,
                "runware_videos": queue_videos,
                "local_graphics": queue_graphics,
                "elevenlabs_tts": [
                    {
                        "queue_id": "TTS-SEG-001-B01",
                        "queue_index": 1,
                        "status": "COMPLETE",
                    }
                ],
            },
        },
    )
    audio = root / "audio/mix/episode-audio-master-v1.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"audio-master")
    _write(
        root / "orchestration/stage-ledger-v1.json",
        {
            "episode_id": episode_id,
            "stages": [
                {
                    "order": 1,
                    "stage": "STRUCTURAL_MONTAGE",
                    "status": "QUEUED",
                },
                {"order": 2, "stage": "AUTOMATIC_QA", "status": "QUEUED"},
            ],
        },
    )
    return episode_id, root


def test_plan_has_seventy_shots_and_locked_mix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode_id, _ = _prepare(tmp_path)
    monkeypatch.setattr(montage, "_probe_duration", lambda env, path: 1320.0 if path.suffix == ".wav" else 8.0)
    monkeypatch.setattr(
        montage,
        "_disk_preflight",
        lambda episode_root, duration: {
            "free_bytes": 20_000_000_000,
            "required_bytes": 8_000_000_000,
            "total_bytes": 30_000_000_000,
        },
    )
    plan = build_structural_montage_plan(
        tmp_path,
        environment=_environment(tmp_path),
    )
    assert plan["episode_id"] == episode_id
    assert plan["shot_count"] == 70
    assert plan["episode_duration_seconds"] == 1320.0
    assert plan["generated_video_seconds"] == 160
    assert plan["treatment_counts"] == {
        "ANIMATED_STILL_COMPOSITING": 44,
        "GENERATED_VIDEO": 20,
        "GRAPHICS": 6,
    }
    assert plan["music"] == "FORBIDDEN"
    assert plan["flat_slideshow"] == "FORBIDDEN"
    stills = [
        shot
        for shot in plan["shots"]
        if shot["treatment"] == "ANIMATED_STILL_COMPOSITING"
    ]
    assert all(shot["motion_profile"] in montage.MOTION_PROFILES for shot in stills)


def test_music_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, root = _prepare(tmp_path)
    storyboard_path = root / "cinematic/storyboard-and-media-plan-v1.json"
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    storyboard["shots"][0]["contains_music"] = True
    _write(storyboard_path, storyboard)
    monkeypatch.setattr(montage, "_probe_duration", lambda env, path: 1320.0 if path.suffix == ".wav" else 8.0)
    monkeypatch.setattr(montage, "_disk_preflight", lambda root, duration: {})
    with pytest.raises(StructuralMontageError, match="MUSIC_CONTENT_FORBIDDEN"):
        build_structural_montage_plan(
            tmp_path,
            environment=_environment(tmp_path),
        )


def test_render_commands_strip_source_audio_and_animate_stills(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    still = build_still_render_command(
        environment,
        tmp_path / "source.jpg",
        tmp_path / "still.mp4",
        duration=8.0,
        motion_profile="SLOW_PUSH_IN",
        fade_in=True,
        fade_out=True,
    )
    motion = build_motion_render_command(
        environment,
        tmp_path / "source.mp4",
        tmp_path / "motion.mp4",
        duration=12.0,
        source_duration=8.0,
        fade_in=False,
        fade_out=True,
        graphics=False,
    )
    assert "zoompan" in still[still.index("-filter_complex") + 1]
    assert "overlay" in still[still.index("-filter_complex") + 1]
    assert "-an" in still
    assert "tpad=stop_mode=clone" in motion[motion.index("-filter_complex") + 1]
    assert "-an" in motion


def test_run_updates_state_for_automatic_qa(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode_id, root = _prepare(tmp_path)
    environment = _environment(tmp_path)
    monkeypatch.setattr(montage, "require_montage_environment", lambda repo: environment)
    monkeypatch.setattr(montage, "_probe_duration", lambda env, path: 1320.0 if path.suffix == ".wav" else 8.0)
    monkeypatch.setattr(montage, "_disk_preflight", lambda root, duration: {})

    def fake_render(repo, env, shot):
        output = repo / shot["output_path_relative"]
        receipt = repo / shot["receipt_path_relative"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(str(shot["shot_id"]).encode("utf-8"))
        _write(receipt, {"status": "COMPLETE"})
        return output, receipt, False

    def fake_concat(env, shots, list_path, output):
        del env, shots
        list_path.parent.mkdir(parents=True, exist_ok=True)
        list_path.write_text("concat", encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"video")

    def fake_mux(env, video, audio, output, duration):
        del env, video, audio, duration
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"final")

    monkeypatch.setattr(montage, "_render_shot", fake_render)
    monkeypatch.setattr(montage, "_concat_video", fake_concat)
    monkeypatch.setattr(montage, "_mux_audio", fake_mux)
    monkeypatch.setattr(
        montage,
        "_validate_video_file",
        lambda *args, **kwargs: {
            "duration_seconds": 1320.0,
            "video_codec": "h264",
            "audio_codec": "aac" if kwargs.get("require_audio") else None,
            "fps": 30.0,
            "width": 1920,
            "height": 1080,
        },
    )
    monkeypatch.setattr(montage, "_update_dependency_graph", lambda *args: None)

    result = run_structural_montage_final_render(tmp_path)
    assert result.episode_id == episode_id
    assert result.status == "FINAL_RENDER_READY_FOR_QA"
    assert result.rendered_shot_count == 70
    assert result.final_master_path.is_file()

    state = json.loads(
        (
            tmp_path
            / "projects/_orchestrator/"
            "autonomous-episode-orchestrator-state-v1.json"
        ).read_text(encoding="utf-8")
    )
    assert state["status"] == "FINAL_RENDER_READY_FOR_QA"
    assert state["stage"] == "AUTOMATIC_QA"
    assert state["next_stage"] == "AUTOMATIC_QA_AND_PARTIAL_REPAIR_V1"

    ledger = json.loads(
        (root / "orchestration/stage-ledger-v1.json").read_text(
            encoding="utf-8"
        )
    )
    montage_stage = next(
        item
        for item in ledger["stages"]
        if item["stage"] == "STRUCTURAL_MONTAGE"
    )
    assert montage_stage["status"] == "COMPLETE"
    assert ledger["resume_from"] == "AUTOMATIC_QA"
