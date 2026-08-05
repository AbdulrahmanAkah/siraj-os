from __future__ import annotations

import json
from pathlib import Path

from src.application.artifact_dependency_graph_v1 import (
    build_scope_dependency_graph,
)
from src.application.graphics_storyboard_media_queue_v1 import (
    integrate_graphics_and_build_media_queue,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _prepare(tmp_path: Path) -> tuple[str, Path]:
    episode_id = "episode-002-test"
    root = tmp_path / "projects" / episode_id
    scope = {
        "episode_id": episode_id,
        "slug_en": "test",
        "events": [
            {"event_id": f"EV-{index:03d}", "title_ar": f"الحدث {index}"}
            for index in range(1, 4)
        ],
    }
    sources = [
        {
            "source_id": f"SRC-{index:03d}",
            "title": f"المصدر {index}",
            "url": f"shamela://local/book/{index}/row/1",
            "source_type": "SHAMELA_LOCAL_BOOK",
            "publisher_or_author": "مؤلف",
            "date_or_edition": "طبعة",
            "reliability_ar": "مصدر معتمد",
        }
        for index in range(1, 7)
    ]
    evidence = {
        "episode_id": episode_id,
        "source_register": sources,
        "events": [
            {
                "event_id": f"EV-{index:03d}",
                "claims": [
                    {
                        "claim_id": f"CL-{index:03d}",
                        "source_ids": [f"SRC-{index:03d}"],
                        "use_policy": "ALLOWED",
                    }
                ],
            }
            for index in range(1, 4)
        ],
    }
    segments = []
    for index in range(1, 7):
        event = (index - 1) % 3 + 1
        segments.append(
            {
                "segment_id": f"SEG-{index:03d}",
                "event_id": f"EV-{event:03d}",
                "title_ar": f"المرحلة {index}",
                "narration_ar": f"سرد موثق للمرحلة {index}. " * 12,
                "source_ids": [f"SRC-{event:03d}"],
                "uncertainty_language_ar": "لا يزاد على القدر المثبت.",
            }
        )
    script = {
        "episode_id": episode_id,
        "segments": segments,
        "music": "FORBIDDEN",
    }
    shots = []
    for index in range(1, 71):
        if index <= 20:
            treatment, generated = "GENERATED_VIDEO", 8
        elif index <= 64:
            treatment, generated = "ANIMATED_STILL_COMPOSITING", 0
        else:
            treatment, generated = "GRAPHICS", 0
        event = (index - 1) % 3 + 1
        shots.append(
            {
                "queue_index": index,
                "shot_id": f"SH-{index:03d}",
                "sequence_id": f"SEQ-{(index - 1) % 6 + 1:02d}",
                "event_id": f"EV-{event:03d}",
                "segment_ids": [f"SEG-{(index - 1) % 6 + 1:03d}"],
                "label_ar": (
                    "خط زمني للمراحل"
                    if index == 65
                    else (
                        "بطاقة مصدر موثق"
                        if index == 66
                        else f"اللقطة {index}"
                    )
                ),
                "dramatic_function_ar": "تقدم معلومة جديدة موثقة.",
                "final_budget_treatment": treatment,
                "editorial_duration_seconds": 12,
                "planned_generated_video_seconds": generated,
                "visual_brief_ar": (
                    "بيئة تاريخية واسعة."
                    if treatment != "GRAPHICS"
                    else "شرح بصري للمعلومة."
                ),
                "camera_motion_ar": "حركة مبررة.",
                "runware_positive_prompt_en": (
                    "Cinematic historical environment with realistic "
                    "physical materials and lighting."
                ),
                "runware_negative_prompt_en": (
                    "No text, no logo, no modern objects."
                ),
                "sfx_cues_ar": [],
                "sound_policy": "SFX_ONLY_NO_MUSIC",
                "depicts_unseen_beings": False,
                "contains_music": False,
                "safety_notes_ar": [],
            }
        )
    storyboard = {
        "episode_id": episode_id,
        "total_shots": 70,
        "shots": shots,
        "music": "FORBIDDEN",
        "flat_slideshow": "FORBIDDEN",
    }

    _write(
        tmp_path / "projects/_orchestrator/"
        "autonomous-episode-orchestrator-state-v1.json",
        {
            "status": (
                "EDITORIAL_PIPELINE_COMPLETE_"
                "BUDGET_PREFLIGHT_QUEUED"
            ),
            "stage": "BUDGET_PREFLIGHT",
            "current_episode_id": episode_id,
        },
    )
    _write(root / "research/evidence-package-v1.json", evidence)
    _write(root / "script/episode-script-v1.json", script)
    _write(
        root / "cinematic/storyboard-and-media-plan-v1.json",
        storyboard,
    )
    stages = (
        "TOPIC_AND_EVENT_PROPOSAL",
        "HUMAN_SCOPE_REVIEW",
        "EVIDENCE_RESEARCH",
        "SCRIPT_WRITING",
        "STORYBOARD_AND_MEDIA_PLANNING",
        "BUDGET_PREFLIGHT",
        "RUNWARE_IMAGE_GENERATION",
        "RUNWARE_VIDEO_GENERATION",
        "ELEVENLABS_TTS",
        "SFX_DESIGN",
        "STRUCTURAL_MONTAGE",
        "AUTOMATIC_QA",
        "HUMAN_FINAL_REVIEW",
        "READY_TO_PUBLISH",
    )
    _write(
        root / "orchestration/stage-ledger-v1.json",
        {
            "episode_id": episode_id,
            "stages": [
                {
                    "order": index,
                    "stage": stage,
                    "status": (
                        "COMPLETE" if index <= 5 else "QUEUED"
                    ),
                }
                for index, stage in enumerate(stages, start=1)
            ],
        },
    )
    _write(
        root / "orchestration/artifact-dependency-graph-v1.json",
        build_scope_dependency_graph(episode_id, scope),
    )
    _write(
        root / "orchestration/editorial-runner-state-v1.json",
        {
            "episode_id": episode_id,
            "status": "EDITORIAL_PIPELINE_COMPLETE",
            "artifacts": {},
        },
    )
    return episode_id, root


def test_exact_queues_graphics_specs_and_state(tmp_path: Path) -> None:
    episode_id, root = _prepare(tmp_path)
    result = integrate_graphics_and_build_media_queue(
        tmp_path,
        recorded_total_usd_override=2.0,
    )
    assert result.episode_id == episode_id
    assert (result.image_count, result.video_count, result.graphics_count) == (
        44,
        20,
        6,
    )
    assert result.tts_segment_count == 6
    assert result.seedream_count + result.nano_banana_count == 44
    assert result.reserved_max_usd == 17.6
    assert result.projected_total_usd == 19.6

    storyboard = json.loads(
        (root / "cinematic/storyboard-and-media-plan-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert sum(
        isinstance(shot["graphics_spec"], dict)
        for shot in storyboard["shots"]
    ) == 6
    assert sum(
        shot["graphics_spec"] is None
        for shot in storyboard["shots"]
    ) == 64

    queue = json.loads(
        (root / "orchestration/media-production-queue-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert queue["counts"]["runware_images"] == 44
    assert queue["counts"]["runware_videos"] == 20
    assert queue["counts"]["local_graphics"] == 6
    assert all(
        item["task_draft"]["includeCost"] is True
        for item in queue["queues"]["runware_images"]
    )
    assert all(
        item["status"] == "READY_LOCAL_RENDER"
        for item in queue["queues"]["local_graphics"]
    )
    assert all(
        item["voice_id"] == "XdoLPWNt7ytn6BtU4FBf"
        for item in queue["queues"]["elevenlabs_tts"]
    )
    assert all(
        item["model_id"] == "eleven_multilingual_v2"
        for item in queue["queues"]["elevenlabs_tts"]
    )
    assert result.tts_voice_selection_required is False

    ledger = json.loads(
        (root / "orchestration/stage-ledger-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["status"] == "MEDIA_QUEUE_READY"
    assert any(
        item["stage"] == "LOCAL_GRAPHICS_RENDER"
        for item in ledger["stages"]
    )


def test_integration_is_idempotent(tmp_path: Path) -> None:
    _prepare(tmp_path)
    first = integrate_graphics_and_build_media_queue(
        tmp_path,
        recorded_total_usd_override=1.0,
    )
    second = integrate_graphics_and_build_media_queue(
        tmp_path,
        recorded_total_usd_override=1.0,
    )
    assert first.image_count == second.image_count == 44
    assert first.graphics_count == second.graphics_count == 6
