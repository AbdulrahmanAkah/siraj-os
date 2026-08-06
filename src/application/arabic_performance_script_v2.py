"""Arabic narration preparation and validation for Siraj V2."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

from src.application.series_production_quality_v2 import (
    MAX_NARRATION_WORDS_PER_MINUTE,
    MIN_NARRATION_WORDS_PER_MINUTE,
    TARGET_NARRATION_WORDS_PER_MINUTE,
    SeriesProductionQualityError,
    assert_tts_text_ready,
    diacritic_coverage,
)

SCHEMA_VERSION = "siraj-arabic-performance-script-v2"
_ALLOWED_PACES = {
    "SLOW_DOCUMENTARY",
    "REFLECTIVE",
    "MEASURED",
    "DRAMATIC_RESTRAINED",
}
_ARABIC_WORD = re.compile(r"[\u0621-\u064A\u064B-\u0652\u0670]+")


class ArabicPerformanceScriptError(SeriesProductionQualityError):
    pass


@dataclass(frozen=True, slots=True)
class PerformanceBlock:
    block_id: str
    canonical_text_ar: str
    tts_text_ar: str
    pace: str = "SLOW_DOCUMENTARY"
    pause_before_ms: int = 200
    pause_after_ms: int = 500
    emphasis_words: tuple[str, ...] = ()
    emotion: str = "MEASURED_AWE"
    speaker_key: str = "NARRATOR"

    def validate(self) -> None:
        if not self.block_id.strip():
            raise ArabicPerformanceScriptError("PERFORMANCE_BLOCK_ID_REQUIRED")
        if not self.canonical_text_ar.strip():
            raise ArabicPerformanceScriptError("CANONICAL_TEXT_REQUIRED")
        assert_tts_text_ready(self.tts_text_ar)
        if self.pace not in _ALLOWED_PACES:
            raise ArabicPerformanceScriptError(f"INVALID_PACE:{self.pace}")
        if not 0 <= self.pause_before_ms <= 3000:
            raise ArabicPerformanceScriptError("INVALID_PAUSE_BEFORE")
        if not 80 <= self.pause_after_ms <= 5000:
            raise ArabicPerformanceScriptError("INVALID_PAUSE_AFTER")
        if not self.speaker_key.strip():
            raise ArabicPerformanceScriptError("SPEAKER_KEY_REQUIRED")

    @property
    def word_count(self) -> int:
        return len(_ARABIC_WORD.findall(self.canonical_text_ar))

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "block_id": self.block_id,
            "canonical_text_ar": self.canonical_text_ar,
            "tts_text_ar": self.tts_text_ar,
            "text_ar": self.tts_text_ar,
            "pace": self.pace,
            "pause_before_ms": self.pause_before_ms,
            "pause_after_ms": self.pause_after_ms,
            "emphasis_words": list(self.emphasis_words),
            "emotion": self.emotion,
            "speaker_key": self.speaker_key,
            "diacritic_coverage": round(diacritic_coverage(self.tts_text_ar), 6),
        }


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return value
    return ()


def block_from_mapping(value: Mapping[str, Any], index: int) -> PerformanceBlock:
    canonical = str(
        value.get("canonical_text_ar")
        or value.get("display_text_ar")
        or value.get("text_ar")
        or value.get("text")
        or ""
    ).strip()
    tts = str(
        value.get("tts_text_ar")
        or value.get("tts_narration_ar")
        or ""
    ).strip()
    if not tts:
        raise ArabicPerformanceScriptError(
            f"TTS_TEXT_AR_REQUIRED:block={index}"
        )
    block = PerformanceBlock(
        block_id=str(value.get("block_id") or f"VB-{index:04d}"),
        canonical_text_ar=canonical,
        tts_text_ar=tts,
        pace=str(value.get("pace") or "SLOW_DOCUMENTARY").upper(),
        pause_before_ms=int(value.get("pause_before_ms", 200)),
        pause_after_ms=int(value.get("pause_after_ms", 500)),
        emphasis_words=tuple(
            str(item).strip()
            for item in _sequence(value.get("emphasis_words"))
            if str(item).strip()
        ),
        emotion=str(value.get("emotion") or "MEASURED_AWE"),
        speaker_key=str(value.get("speaker_key") or "NARRATOR"),
    )
    block.validate()
    return block


def validate_performance_script(script: Mapping[str, Any]) -> dict[str, Any]:
    segments = script.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ArabicPerformanceScriptError("SCRIPT_SEGMENTS_REQUIRED")
    output_segments: list[dict[str, Any]] = []
    total_words = 0
    total_planned_seconds = 0.0
    block_count = 0
    for segment_index, segment in enumerate(segments, start=1):
        if not isinstance(segment, Mapping):
            raise ArabicPerformanceScriptError(
                f"SCRIPT_SEGMENT_OBJECT_REQUIRED:{segment_index}"
            )
        raw_blocks = (
            segment.get("performance_blocks")
            or segment.get("voice_blocks")
        )
        if not isinstance(raw_blocks, list) or not raw_blocks:
            raise ArabicPerformanceScriptError(
                f"PERFORMANCE_BLOCKS_REQUIRED:{segment_index}"
            )
        parsed = [
            block_from_mapping(item, block_count + offset)
            for offset, item in enumerate(raw_blocks, start=1)
            if isinstance(item, Mapping)
        ]
        if len(parsed) != len(raw_blocks):
            raise ArabicPerformanceScriptError(
                f"PERFORMANCE_BLOCK_OBJECT_REQUIRED:{segment_index}"
            )
        block_count += len(parsed)
        total_words += sum(item.word_count for item in parsed)
        planned = float(
            segment.get("planned_narration_seconds")
            or segment.get("duration_seconds")
            or 0
        )
        if planned <= 0:
            planned = sum(
                (item.word_count / TARGET_NARRATION_WORDS_PER_MINUTE) * 60.0
                + (item.pause_before_ms + item.pause_after_ms) / 1000.0
                for item in parsed
            )
        total_planned_seconds += planned
        copied = dict(segment)
        copied["performance_blocks"] = [item.to_dict() for item in parsed]
        copied["narration_policy"] = {
            "fully_diacritized": True,
            "explicit_pauses": True,
            "target_words_per_minute": TARGET_NARRATION_WORDS_PER_MINUTE,
        }
        output_segments.append(copied)

    wpm = (total_words * 60.0 / total_planned_seconds) if total_planned_seconds else 0
    if not MIN_NARRATION_WORDS_PER_MINUTE <= wpm <= MAX_NARRATION_WORDS_PER_MINUTE:
        raise ArabicPerformanceScriptError(
            f"NARRATION_PACE_OUT_OF_RANGE:wpm={wpm:.3f}"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "VALIDATED_AWAITING_HUMAN_LANGUAGE_AND_PERFORMANCE_APPROVAL",
        "segments": output_segments,
        "metrics": {
            "performance_block_count": block_count,
            "word_count": total_words,
            "planned_narration_seconds": round(total_planned_seconds, 3),
            "planned_words_per_minute": round(wpm, 3),
        },
        "human_language_review_required": True,
        "human_performance_review_required": True,
    }
