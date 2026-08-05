from __future__ import annotations

from src.application.elevenlabs_voice_casting_v1 import (
    MODEL_ID,
    PRIMARY_VOICE_ID,
    SUPPORT_VOICE_1_ID,
    SUPPORT_VOICE_2_ID,
    SUPPORT_VOICE_3_ID,
    VOICE_SETTINGS,
    build_episode_voice_cast_plan,
)


def test_primary_narrator_is_default() -> None:
    script = {
        "segments": [
            {
                "segment_id": "SEG-001",
                "event_id": "EV-001",
                "segment_type": "EVENT",
                "narration_ar": "نص السرد الأساسي.",
                "source_ids": ["SRC-001"],
            }
        ]
    }
    plan = build_episode_voice_cast_plan(
        "episode-001-test",
        script,
        {"shots": []},
    )
    assert plan.performer_slots_used == ("PRIMARY",)
    assert plan.queue_items[0]["voice_id"] == PRIMARY_VOICE_ID
    assert plan.queue_items[0]["model_id"] == MODEL_ID
    assert plan.queue_items[0]["voice_settings"] == VOICE_SETTINGS
    assert plan.queue_items[0]["status"] == (
        "READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED"
    )


def test_multiple_script_performers_use_locked_roster() -> None:
    script = {
        "segments": [
            {
                "segment_id": "SEG-001",
                "event_id": "EV-001",
                "narration_ar": "النص الجامع للمقطع.",
                "source_ids": ["SRC-001"],
                "performance_blocks": [
                    {
                        "block_id": "VB-001-01",
                        "performance_type": "NARRATION",
                        "speaker_key": "NARRATOR",
                        "speaker_label_ar": "الراوي",
                        "voice_slot_preference": "PRIMARY",
                        "text_ar": "يبدأ الراوي.",
                        "source_ids": ["SRC-001"],
                    },
                    {
                        "block_id": "VB-001-02",
                        "performance_type": "QUOTED_SPEECH",
                        "speaker_key": "CHARACTER_A",
                        "speaker_label_ar": "الشخصية الأولى",
                        "voice_slot_preference": "AUTO",
                        "text_ar": "هذا قول الشخصية الأولى.",
                        "source_ids": ["SRC-001"],
                    },
                    {
                        "block_id": "VB-001-03",
                        "performance_type": "DIALOGUE",
                        "speaker_key": "CHARACTER_B",
                        "speaker_label_ar": "الشخصية الثانية",
                        "voice_slot_preference": "AUTO",
                        "text_ar": "وهذا جواب الشخصية الثانية.",
                        "source_ids": ["SRC-001"],
                    },
                    {
                        "block_id": "VB-001-04",
                        "performance_type": "DIALOGUE",
                        "speaker_key": "CHARACTER_C",
                        "speaker_label_ar": "الشخصية الثالثة",
                        "voice_slot_preference": "AUTO",
                        "text_ar": "وهذا صوت الشخصية الثالثة.",
                        "source_ids": ["SRC-001"],
                    },
                ],
            }
        ]
    }
    plan = build_episode_voice_cast_plan(
        "episode-001-test",
        script,
        {
            "shots": [
                {
                    "segment_ids": ["SEG-001"],
                    "requires_multiple_voice_performers": True,
                    "speaker_keys": [
                        "NARRATOR",
                        "CHARACTER_A",
                        "CHARACTER_B",
                        "CHARACTER_C",
                    ],
                }
            ]
        },
    )
    assert plan.multi_performer_required is True
    assert plan.performer_slots_used == (
        "PRIMARY",
        "SUPPORT_1",
        "SUPPORT_2",
        "SUPPORT_3",
    )
    assert [item["voice_id"] for item in plan.queue_items] == [
        PRIMARY_VOICE_ID,
        SUPPORT_VOICE_1_ID,
        SUPPORT_VOICE_2_ID,
        SUPPORT_VOICE_3_ID,
    ]


def test_same_character_keeps_same_voice() -> None:
    script = {
        "segments": [
            {
                "segment_id": "SEG-001",
                "event_id": "EV-001",
                "narration_ar": "قول أول.",
                "speaker_key": "CHARACTER_A",
                "performance_type": "QUOTED_SPEECH",
                "source_ids": ["SRC-001"],
            },
            {
                "segment_id": "SEG-002",
                "event_id": "EV-001",
                "narration_ar": "قول ثان للشخصية نفسها.",
                "speaker_key": "CHARACTER_A",
                "performance_type": "QUOTED_SPEECH",
                "source_ids": ["SRC-001"],
            },
        ]
    }
    plan = build_episode_voice_cast_plan(
        "episode-001-test",
        script,
        {"shots": []},
    )
    assert plan.queue_items[0]["voice_id"] == (
        plan.queue_items[1]["voice_id"]
    )
    assert plan.queue_items[0]["voice_id"] == SUPPORT_VOICE_1_ID
