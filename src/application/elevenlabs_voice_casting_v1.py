from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

RELEASE = "ELEVENLABS_FOUR_PERFORMER_CASTING_LOCK_V1"

MODEL_ID = "eleven_multilingual_v2"
VOICE_SETTINGS = {
    "stability": 0.55,
    "similarity_boost": 0.75,
    "style": 0.15,
    "use_speaker_boost": True,
}

PRIMARY_VOICE_ID = "XdoLPWNt7ytn6BtU4FBf"
SUPPORT_VOICE_1_ID = "pCKbQ4EPGE06zpEPGNvS"
SUPPORT_VOICE_2_ID = "fkqevZRU7Xj52dY1CTkq"
SUPPORT_VOICE_3_ID = "t8atLZaWuCcW6gENDwwa"

VOICE_SLOTS = ("PRIMARY", "SUPPORT_1", "SUPPORT_2", "SUPPORT_3")
SUPPORT_SLOTS = ("SUPPORT_1", "SUPPORT_2", "SUPPORT_3")
VOICE_ID_BY_SLOT = {
    "PRIMARY": PRIMARY_VOICE_ID,
    "SUPPORT_1": SUPPORT_VOICE_1_ID,
    "SUPPORT_2": SUPPORT_VOICE_2_ID,
    "SUPPORT_3": SUPPORT_VOICE_3_ID,
}
VOICE_ROSTER = (
    {
        "slot": "PRIMARY",
        "voice_id": PRIMARY_VOICE_ID,
        "role": "PRIMARY_NARRATOR",
        "label": "Primary selected ElevenLabs performer",
    },
    {
        "slot": "SUPPORT_1",
        "voice_id": SUPPORT_VOICE_1_ID,
        "role": "BACKUP_AND_ADDITIONAL_PERFORMER",
        "label": "Selected supporting performer 1",
    },
    {
        "slot": "SUPPORT_2",
        "voice_id": SUPPORT_VOICE_2_ID,
        "role": "BACKUP_AND_ADDITIONAL_PERFORMER",
        "label": "Hijazi - Professional, and Expressive",
    },
    {
        "slot": "SUPPORT_3",
        "voice_id": SUPPORT_VOICE_3_ID,
        "role": "BACKUP_AND_ADDITIONAL_PERFORMER",
        "label": "Selected supporting performer 3",
    },
)

NARRATOR_KEYS = frozenset({"", "NARRATOR", "PRIMARY_NARRATOR", "الراوي", "السارد"})
SUPPORTING_TYPES = frozenset(
    {
        "QUOTED_SPEECH",
        "DIALOGUE",
        "HISTORICAL_CHARACTER",
        "SECONDARY_NARRATION",
        "LETTER_READING",
        "DOCUMENT_READING",
    }
)
MULTI_VOICE_TERMS = (
    "dialogue",
    "quoted speech",
    "character voice",
    "second voice",
    "multiple voices",
    "حوار",
    "صوت شخصية",
    "صوت ثان",
    "عدة أصوات",
    "اقتباس بصوت",
)


class VoiceCastingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VoiceCastingPlan:
    episode_id: str
    queue_items: tuple[dict[str, Any], ...]
    performer_slots_used: tuple[str, ...]
    speaker_slot_map: dict[str, str]
    multi_performer_required: bool

    @property
    def performer_count(self) -> int:
        return len(self.performer_slots_used)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "siraj-elevenlabs-voice-cast-plan-v1",
            "release": RELEASE,
            "episode_id": self.episode_id,
            "provider": "ELEVENLABS",
            "model_id": MODEL_ID,
            "voice_settings": dict(VOICE_SETTINGS),
            "roster": [dict(item) for item in VOICE_ROSTER],
            "primary_voice_id": PRIMARY_VOICE_ID,
            "backup_voice_ids": [
                SUPPORT_VOICE_1_ID,
                SUPPORT_VOICE_2_ID,
                SUPPORT_VOICE_3_ID,
            ],
            "performer_slots_used": list(self.performer_slots_used),
            "performer_count": self.performer_count,
            "speaker_slot_map": dict(self.speaker_slot_map),
            "multi_performer_required": self.multi_performer_required,
            "voice_selection_required": False,
            "assignment_source": "SCRIPT_PERFORMANCE_BLOCKS_AND_STORYBOARD_REQUIREMENTS",
            "fallback_policy": (
                "PREPARE_NEXT_EXPLICITLY_AUTHORIZED_ATTEMPT_"
                "NO_HIDDEN_PAID_RETRY"
            ),
            "queue_items": [dict(item) for item in self.queue_items],
        }


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return value
    return ()


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalized(value: Any) -> str:
    text = _clean(value)
    return text.upper() if text.isascii() else text


def _storyboard_signals(storyboard: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for shot in _sequence(storyboard.get("shots")):
        if not isinstance(shot, Mapping):
            continue
        combined = " ".join(
            _clean(shot.get(field))
            for field in (
                "label_ar",
                "dramatic_function_ar",
                "visual_brief_ar",
                "performance_notes_ar",
                "voice_direction_ar",
            )
        ).lower()
        explicit_keys = [
            _clean(value)
            for value in _sequence(shot.get("speaker_keys") or shot.get("voice_cast"))
            if _clean(value)
        ]
        for segment_id in _sequence(shot.get("segment_ids")):
            entry = result.setdefault(
                str(segment_id),
                {"requires_multiple": False, "speaker_keys": []},
            )
            if (
                shot.get("requires_multiple_voice_performers") is True
                or len(explicit_keys) > 1
                or any(term in combined for term in MULTI_VOICE_TERMS)
            ):
                entry["requires_multiple"] = True
            for speaker_key in explicit_keys:
                if speaker_key not in entry["speaker_keys"]:
                    entry["speaker_keys"].append(speaker_key)
    return result


def _explicit_blocks(segment: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = segment.get("performance_blocks") or segment.get("voice_blocks")
    if not isinstance(raw, list) or not raw:
        return []
    result = []
    for index, block in enumerate(raw, start=1):
        if not isinstance(block, Mapping):
            raise VoiceCastingError("VOICE_PERFORMANCE_BLOCK_OBJECT_REQUIRED")
        text = _clean(block.get("text_ar") or block.get("text"))
        if not text:
            raise VoiceCastingError(
                f"VOICE_PERFORMANCE_BLOCK_TEXT_REQUIRED:{index}"
            )
        result.append(
            {
                "block_id": _clean(block.get("block_id")) or f"VB-AUTO-{index:02d}",
                "performance_type": _normalized(
                    block.get("performance_type") or "NARRATION"
                ),
                "speaker_key": _clean(
                    block.get("speaker_key")
                    or block.get("speaker_role_id")
                    or block.get("speaker_label_ar")
                    or "NARRATOR"
                ),
                "speaker_label_ar": _clean(
                    block.get("speaker_label_ar")
                    or block.get("speaker_key")
                    or "الراوي"
                ),
                "voice_slot_preference": _normalized(
                    block.get("voice_slot_preference") or "AUTO"
                ),
                "text_ar": text,
                "source_ids": [
                    str(value)
                    for value in _sequence(
                        block.get("source_ids") or segment.get("source_ids")
                    )
                    if str(value).strip()
                ],
            }
        )
    return result


def _synthetic_blocks(
    segment: Mapping[str, Any],
    signal: Mapping[str, Any],
) -> list[dict[str, Any]]:
    text = _clean(segment.get("narration_ar"))
    if not text:
        raise VoiceCastingError(
            "TTS_NARRATION_REQUIRED:" + str(segment.get("segment_id", ""))
        )
    speaker_key = _clean(
        segment.get("speaker_key")
        or segment.get("speaker_role_id")
        or segment.get("speaker_ar")
        or segment.get("quoted_speaker_ar")
    )
    segment_type = _normalized(
        segment.get("performance_type")
        or segment.get("segment_type")
        or "NARRATION"
    )
    if not speaker_key:
        speaker_key = (
            "NARRATOR"
            if segment_type not in SUPPORTING_TYPES
            else f"{segment_type}:{segment.get('event_id', '')}"
        )
    performance_type = (
        segment_type if segment_type in SUPPORTING_TYPES else "NARRATION"
    )
    explicit_speakers = [
        _clean(value)
        for value in signal.get("speaker_keys", [])
        if _clean(value)
    ]
    if explicit_speakers:
        speaker_key = explicit_speakers[0]
        if speaker_key not in NARRATOR_KEYS:
            performance_type = "HISTORICAL_CHARACTER"
    return [
        {
            "block_id": "VB-AUTO-01",
            "performance_type": performance_type,
            "speaker_key": speaker_key,
            "speaker_label_ar": _clean(
                segment.get("speaker_ar")
                or segment.get("quoted_speaker_ar")
                or ("الراوي" if speaker_key in NARRATOR_KEYS else speaker_key)
            ),
            "voice_slot_preference": _normalized(
                segment.get("voice_slot_preference") or "AUTO"
            ),
            "text_ar": text,
            "source_ids": [
                str(value)
                for value in _sequence(segment.get("source_ids"))
                if str(value).strip()
            ],
        }
    ]


def _slot_for_block(
    block: Mapping[str, Any],
    speaker_slot_map: dict[str, str],
) -> str:
    preference = _normalized(block.get("voice_slot_preference"))
    if preference in VOICE_SLOTS:
        return preference

    speaker_key = _clean(block.get("speaker_key"))
    normalized = _normalized(speaker_key)
    performance_type = _normalized(block.get("performance_type"))
    if normalized in NARRATOR_KEYS and performance_type not in SUPPORTING_TYPES:
        return "PRIMARY"
    if normalized in speaker_slot_map:
        return speaker_slot_map[normalized]

    used = {
        slot
        for key, slot in speaker_slot_map.items()
        if key not in NARRATOR_KEYS
    }
    for slot in SUPPORT_SLOTS:
        if slot not in used:
            speaker_slot_map[normalized] = slot
            return slot

    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    slot = SUPPORT_SLOTS[digest[0] % len(SUPPORT_SLOTS)]
    speaker_slot_map[normalized] = slot
    return slot


def _fallback_voice_ids(slot: str) -> list[str]:
    order = {
        "PRIMARY": ("SUPPORT_1", "SUPPORT_2", "SUPPORT_3"),
        "SUPPORT_1": ("SUPPORT_2", "SUPPORT_3", "PRIMARY"),
        "SUPPORT_2": ("SUPPORT_3", "SUPPORT_1", "PRIMARY"),
        "SUPPORT_3": ("SUPPORT_2", "SUPPORT_1", "PRIMARY"),
    }[slot]
    return [VOICE_ID_BY_SLOT[value] for value in order]


def build_episode_voice_cast_plan(
    episode_id: str,
    script: Mapping[str, Any],
    storyboard: Mapping[str, Any],
) -> VoiceCastingPlan:
    segments = script.get("segments")
    if not isinstance(segments, list) or not segments:
        raise VoiceCastingError("SCRIPT_SEGMENTS_REQUIRED_FOR_VOICE_CAST")

    signals = _storyboard_signals(storyboard)
    speaker_slot_map: dict[str, str] = {
        "NARRATOR": "PRIMARY",
        "PRIMARY_NARRATOR": "PRIMARY",
        "الراوي": "PRIMARY",
        "السارد": "PRIMARY",
    }
    queue_items: list[dict[str, Any]] = []
    used_slots: list[str] = []
    queue_index = 0

    for segment in segments:
        if not isinstance(segment, Mapping):
            raise VoiceCastingError("SCRIPT_SEGMENT_OBJECT_REQUIRED")
        segment_id = _clean(segment.get("segment_id"))
        if not segment_id:
            raise VoiceCastingError("SCRIPT_SEGMENT_ID_REQUIRED")
        blocks = _explicit_blocks(segment)
        if not blocks:
            blocks = _synthetic_blocks(
                segment,
                signals.get(segment_id, {}),
            )

        for block_number, block in enumerate(blocks, start=1):
            queue_index += 1
            slot = _slot_for_block(block, speaker_slot_map)
            voice_id = VOICE_ID_BY_SLOT[slot]
            if slot not in used_slots:
                used_slots.append(slot)
            task_uuid = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    (
                        f"siraj:{episode_id}:elevenlabs:"
                        f"{segment_id}:{block_number}:attempt-1"
                    ),
                )
            )
            queue_items.append(
                {
                    "queue_id": f"TTS-{segment_id}-B{block_number:02d}",
                    "queue_index": queue_index,
                    "segment_id": segment_id,
                    "event_id": segment.get("event_id"),
                    "block_id": str(block["block_id"]),
                    "performance_type": str(block["performance_type"]),
                    "speaker_key": str(block["speaker_key"]),
                    "speaker_label_ar": str(block["speaker_label_ar"]),
                    "source_ids": list(block["source_ids"]),
                    "status": (
                        "READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED"
                    ),
                    "provider": "ELEVENLABS",
                    "voice_slot": slot,
                    "voice_id": voice_id,
                    "fallback_voice_ids": _fallback_voice_ids(slot),
                    "model_id": MODEL_ID,
                    "voice_settings": dict(VOICE_SETTINGS),
                    "text_ar": str(block["text_ar"]),
                    "task_uuid": task_uuid,
                    "task_draft": {
                        "voice_id": voice_id,
                        "model_id": MODEL_ID,
                        "text": str(block["text_ar"]),
                        "voice_settings": dict(VOICE_SETTINGS),
                        "output_format": "mp3_44100_128",
                    },
                    "output_path_relative": (
                        f"projects/{episode_id}/audio/tts/"
                        f"{segment_id}-B{block_number:02d}.mp3"
                    ),
                    "hidden_paid_retry": "FORBIDDEN",
                }
            )

    ordered_slots = tuple(
        slot for slot in VOICE_SLOTS if slot in used_slots
    )
    return VoiceCastingPlan(
        episode_id=episode_id,
        queue_items=tuple(queue_items),
        performer_slots_used=ordered_slots,
        speaker_slot_map=dict(speaker_slot_map),
        multi_performer_required=len(ordered_slots) > 1,
    )
