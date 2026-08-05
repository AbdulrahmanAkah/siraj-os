from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src.application.artifact_dependency_graph_v1 import (
    build_scope_dependency_graph,
)
from src.application.automatic_research_script_storyboard_runner_v1 import (
    load_editorial_runner_state,
    run_editorial_pipeline,
)
from src.application.openai_luna_editorial_v1 import (
    EditorialLunaResult,
    evidence_schema,
    script_schema,
    storyboard_schema,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _scope(episode_id: str) -> dict:
    events = [
        {
            "event_id": f"EV-{index:03d}",
            "title_ar": f"الحدث {index}",
            "description_ar": f"وصف الحدث {index}",
            "chronology_order": index,
        }
        for index in range(1, 4)
    ]
    return {
        "schema_version": "siraj-episode-scope-proposal-v1",
        "episode_id": episode_id,
        "slug_en": "test-episode",
        "topic_title_ar": "حلقة اختبار",
        "working_title_ar": "حلقة اختبار",
        "central_question_ar": "ماذا حدث؟",
        "estimated_duration_minutes": 12,
        "events": events,
        "human_approval": True,
    }


def _evidence(episode_id: str) -> dict:
    sources = [
        {
            "source_id": f"SRC-{index:03d}",
            "title": f"المصدر {index}",
            "url": f"https://example.com/{index}",
            "source_type": "REFERENCE_WORK",
            "publisher_or_author": "مؤلف",
            "date_or_edition": "2026",
            "reliability_ar": "مصدر اختبار موثوق",
        }
        for index in range(1, 4)
    ]
    events = []
    for index in range(1, 4):
        events.append(
            {
                "event_id": f"EV-{index:03d}",
                "chronology_summary_ar": (
                    f"ملخص زمني موثق للحدث رقم {index}."
                ),
                "claims": [
                    {
                        "claim_id": f"CL-{index:03d}",
                        "claim_ar": f"ادعاء موثق {index}",
                        "evidence_posture": "QUALIFIED_REPORT",
                        "confidence": "HIGH",
                        "source_ids": [f"SRC-{index:03d}"],
                        "use_policy": "ALLOWED",
                        "qualification_ar": "",
                        "contradictions_ar": [],
                    }
                ],
                "unresolved_questions_ar": [],
                "production_safety_ar": [],
            }
        )
    return {
        "episode_id": episode_id,
        "research_summary_ar": (
            "حزمة بحث اختبارية تربط كل حدث بادعائه ومصدره."
        ),
        "source_register": sources,
        "events": events,
        "global_uncertainties_ar": [],
        "excluded_claims_ar": [],
        "research_quality_score": 95,
    }


def _script(episode_id: str) -> dict:
    segments = [
        {
            "segment_id": "SEG-001",
            "segment_type": "INTRO",
            "event_id": "GLOBAL",
            "title_ar": "المقدمة",
            "narration_ar": "مقدمة طويلة " * 10,
            "estimated_duration_seconds": 60,
            "claim_ids": [],
            "source_ids": [],
            "transition_ar": "ننتقل إلى الحدث الأول.",
            "visual_intent_ar": "افتتاح بصري تمهيدي.",
            "uncertainty_language_ar": "",
        }
    ]
    for index in range(1, 4):
        segments.append(
            {
                "segment_id": f"SEG-{index + 1:03d}",
                "segment_type": "EVENT",
                "event_id": f"EV-{index:03d}",
                "title_ar": f"الحدث {index}",
                "narration_ar": (
                    f"سرد تاريخي موثق للحدث رقم {index}. " * 12
                ),
                "estimated_duration_seconds": 180,
                "claim_ids": [f"CL-{index:03d}"],
                "source_ids": [f"SRC-{index:03d}"],
                "transition_ar": "انتقال زمني واضح.",
                "visual_intent_ar": "تجسيد مادي غير غيبي.",
                "uncertainty_language_ar": "",
            }
        )
    segments.append(
        {
            "segment_id": "SEG-005",
            "segment_type": "OUTRO",
            "event_id": "GLOBAL",
            "title_ar": "الخاتمة",
            "narration_ar": "خاتمة تربط الأحداث بمعنى الحلقة. " * 10,
            "estimated_duration_seconds": 60,
            "claim_ids": [],
            "source_ids": [],
            "transition_ar": "",
            "visual_intent_ar": "ختام بصري هادئ.",
            "uncertainty_language_ar": "",
        }
    )
    return {
        "episode_id": episode_id,
        "title_ar": "حلقة اختبار",
        "opening_hook_ar": "افتتاح مشوق ومحدد للحلقة التاريخية.",
        "central_thesis_ar": (
            "تتابع الأحداث يكشف أثر القرار في المسار التاريخي."
        ),
        "target_duration_seconds": 660,
        "segments": segments,
        "closing_ar": (
            "خاتمة كاملة تحفظ الدقة وتفتح الطريق للحلقة التالية."
        ),
        "editorial_notes_ar": [],
        "music": "FORBIDDEN",
        "sound_effects": "ALLOWED_ANY_SCENE_APPROPRIATE_TYPE",
    }


def _storyboard(episode_id: str) -> dict:
    segment_ids = [f"SEG-{index:03d}" for index in range(1, 6)]
    sequences = [
        {
            "sequence_id": f"SEQ-{index:02d}",
            "title_ar": f"المتتالية {index}",
            "narrative_function_ar": "تطوير السرد والمعلومة.",
            "segment_ids": [segment_ids[index - 1]],
        }
        for index in range(1, 6)
    ]
    shots = []
    for index in range(1, 71):
        if index <= 20:
            treatment = "GENERATED_VIDEO"
            generated = 8
        elif index <= 64:
            treatment = "ANIMATED_STILL_COMPOSITING"
            generated = 0
        else:
            treatment = "GRAPHICS"
            generated = 0
        segment = segment_ids[(index - 1) % len(segment_ids)]
        sequence_index = (index - 1) % 5 + 1
        event_index = (index - 1) % 3 + 1
        shots.append(
            {
                "queue_index": index,
                "shot_id": f"SH-{index:03d}",
                "sequence_id": f"SEQ-{sequence_index:02d}",
                "event_id": f"EV-{event_index:03d}",
                "segment_ids": [segment],
                "label_ar": f"اللقطة {index}",
                "dramatic_function_ar": (
                    "تقدم معلومة أو ضغطًا دراميًا جديدًا."
                ),
                "final_budget_treatment": treatment,
                "editorial_duration_seconds": 9,
                "planned_generated_video_seconds": generated,
                "visual_brief_ar": (
                    "مشهد تاريخي مادي منضبط بلا تجسيد للغيب."
                ),
                "camera_motion_ar": "حركة بطيئة مبررة.",
                "runware_positive_prompt_en": (
                    "Cinematic historical material environment, "
                    "grounded realistic lighting and physical detail."
                ),
                "runware_negative_prompt_en": (
                    "No text, no logo, no music, no unseen beings."
                ),
                "sfx_cues_ar": ["حركة هواء خفيفة"],
                "sound_policy": "SFX_ONLY_NO_MUSIC",
                "depicts_unseen_beings": False,
                "contains_music": False,
                "safety_notes_ar": [],
            }
        )
    return {
        "episode_id": episode_id,
        "storyboard_version": 1,
        "total_shots": 70,
        "generated_video_target_seconds": {
            "minimum": 120,
            "maximum": 180,
            "planned": 160,
        },
        "treatment_counts": {
            "GENERATED_VIDEO": 20,
            "ANIMATED_STILL_COMPOSITING": 44,
            "GRAPHICS": 6,
        },
        "sequences": sequences,
        "shots": shots,
        "music": "FORBIDDEN",
        "sound_effects": "ALLOWED_ANY_SCENE_APPROPRIATE_TYPE",
        "flat_slideshow": "FORBIDDEN",
        "production_notes_ar": [],
    }


def _result(payload: dict, response_id: str) -> EditorialLunaResult:
    return EditorialLunaResult(
        response_id=response_id,
        payload=payload,
        raw_output_text=json.dumps(payload, ensure_ascii=False),
        input_tokens=1000,
        output_tokens=500,
        cached_input_tokens=0,
        estimated_text_cost_usd=0.0008,
        web_search_calls=1 if "evidence" in response_id else 0,
    )


def _prepare_repo(tmp_path: Path) -> tuple[str, Path]:
    episode_id = "episode-002-test-episode"
    episode_root = tmp_path / "projects" / episode_id
    scope = _scope(episode_id)
    _write(
        tmp_path
        / "projects"
        / "_orchestrator"
        / "autonomous-episode-orchestrator-state-v1.json",
        {
            "status": "SCOPE_APPROVED_AUTOMATIC_PIPELINE_QUEUED",
            "stage": "EVIDENCE_RESEARCH",
            "current_episode_id": episode_id,
            "luna_usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_input_tokens": 0,
                "estimated_text_cost_usd": 0.0,
            },
        },
    )
    _write(
        episode_root / "contracts" / "approved-scope-v1.json",
        scope,
    )
    graph = build_scope_dependency_graph(episode_id, scope)
    _write(
        episode_root
        / "orchestration"
        / "artifact-dependency-graph-v1.json",
        graph,
    )
    stages = [
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
    ]
    _write(
        episode_root
        / "orchestration"
        / "stage-ledger-v1.json",
        {
            "schema_version": "siraj-autonomous-stage-ledger-v1",
            "episode_id": episode_id,
            "status": "AUTOMATIC_PIPELINE_QUEUED",
            "stages": [
                {
                    "order": index,
                    "stage": stage,
                    "status": (
                        "COMPLETE"
                        if stage
                        in {
                            "TOPIC_AND_EVENT_PROPOSAL",
                            "HUMAN_SCOPE_REVIEW",
                        }
                        else "QUEUED"
                    ),
                }
                for index, stage in enumerate(stages, start=1)
            ],
            "resume_from": "EVIDENCE_RESEARCH",
        },
    )
    return episode_id, episode_root


def test_editorial_schemas_are_strict_and_storyboard_is_exact() -> None:
    for schema in (
        evidence_schema(),
        script_schema(),
        storyboard_schema(),
    ):
        assert schema["additionalProperties"] is False
    storyboard = storyboard_schema()
    assert storyboard["properties"]["shots"]["minItems"] == 70
    assert storyboard["properties"]["shots"]["maxItems"] == 70


def test_runner_executes_three_stages_and_persists_costs(
    tmp_path: Path,
) -> None:
    episode_id, episode_root = _prepare_repo(tmp_path)
    with (
        patch(
            "src.application."
            "automatic_research_script_storyboard_runner_v1."
            "request_evidence_package",
            return_value=_result(
                _evidence(episode_id),
                "resp_evidence",
            ),
        ),
        patch(
            "src.application."
            "automatic_research_script_storyboard_runner_v1."
            "request_script_package",
            return_value=_result(
                _script(episode_id),
                "resp_script",
            ),
        ),
        patch(
            "src.application."
            "automatic_research_script_storyboard_runner_v1."
            "request_storyboard_plan",
            return_value=_result(
                _storyboard(episode_id),
                "resp_storyboard",
            ),
        ),
    ):
        result = run_editorial_pipeline(
            tmp_path,
            "test-key",
        )

    assert result.status == "EDITORIAL_PIPELINE_COMPLETE"
    assert result.completed_stages == (
        "EVIDENCE_RESEARCH",
        "SCRIPT_WRITING",
        "STORYBOARD_AND_MEDIA_PLANNING",
    )
    assert (
        episode_root / "research/evidence-package-v1.json"
    ).is_file()
    assert (
        episode_root / "script/episode-script-v1.json"
    ).is_file()
    assert (
        episode_root
        / "cinematic/storyboard-and-media-plan-v1.json"
    ).is_file()

    receipts = list(
        (
            episode_root
            / "orchestration"
            / "cost-receipts"
        ).glob("*receipt*.json")
    )
    assert len(receipts) == 3
    state = load_editorial_runner_state(tmp_path)
    assert state["status"] == "EDITORIAL_PIPELINE_COMPLETE"
    assert state["usage"]["estimated_text_cost_usd"] == 0.0024

    orchestrator = json.loads(
        (
            tmp_path
            / "projects"
            / "_orchestrator"
            / "autonomous-episode-orchestrator-state-v1.json"
        ).read_text(encoding="utf-8")
    )
    assert orchestrator["stage"] == "BUDGET_PREFLIGHT"
    assert (
        orchestrator["status"]
        == "EDITORIAL_PIPELINE_COMPLETE_BUDGET_PREFLIGHT_QUEUED"
    )


def test_runner_reuses_saved_provider_envelope_without_new_call(
    tmp_path: Path,
) -> None:
    episode_id, episode_root = _prepare_repo(tmp_path)
    evidence_result = _result(
        _evidence(episode_id),
        "resp_evidence",
    )
    envelope = {
        "schema_version": "siraj-luna-editorial-response-envelope-v1",
        "episode_id": episode_id,
        "stage": "EVIDENCE_RESEARCH",
        "provider": "OPENAI",
        "model": "gpt-5.6-luna",
        "provider_response_id": evidence_result.response_id,
        "payload": evidence_result.payload,
        "usage": {
            "input_tokens": evidence_result.input_tokens,
            "output_tokens": evidence_result.output_tokens,
            "cached_input_tokens": 0,
            "estimated_text_cost_usd": 0.0008,
            "web_search_calls": 1,
        },
    }
    _write(
        episode_root
        / "orchestration"
        / "provider-responses"
        / "evidence-research-response-v1.json",
        envelope,
    )

    with (
        patch(
            "src.application."
            "automatic_research_script_storyboard_runner_v1."
            "request_evidence_package",
            side_effect=AssertionError(
                "must recover saved response"
            ),
        ),
        patch(
            "src.application."
            "automatic_research_script_storyboard_runner_v1."
            "request_script_package",
            return_value=_result(
                _script(episode_id),
                "resp_script",
            ),
        ),
        patch(
            "src.application."
            "automatic_research_script_storyboard_runner_v1."
            "request_storyboard_plan",
            return_value=_result(
                _storyboard(episode_id),
                "resp_storyboard",
            ),
        ),
    ):
        result = run_editorial_pipeline(
            tmp_path,
            "test-key",
        )

    assert result.status == "EDITORIAL_PIPELINE_COMPLETE"
    assert (
        episode_root / "research/evidence-package-v1.json"
    ).is_file()
