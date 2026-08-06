"""Linguistically hardened actual-stop waqf processing for SIRAJ TTS.

Policies:
- Only TTS performance text is modified.
- Sentence-ending punctuation, ellipsis, semicolon, and explicit block-end
  pauses are actual stops.
- Commas remain connected by default.
- The single comma stop explicitly confirmed by the user is applied through
  a narrow manual override.
- Final taa marbuta is rendered phonetically as haa with sukun at an actual
  stop.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import unicodedata
from typing import Any, Mapping

from src.application.arabic_performance_script_v2 import (
    validate_performance_script,
)
from src.application.elevenlabs_voice_casting_v1 import (
    build_episode_voice_cast_plan,
)

RELEASE = "SIRAJ_ARABIC_ACTUAL_STOP_WAQF_V3"
SCHEMA_VERSION = "siraj-arabic-actual-stop-waqf-v3"

ACTUAL_BLOCK_PAUSE_THRESHOLD_MS = 400
INTERNAL_RESERVE_USD = 3.0
SAMPLE_BLOCK_ID = "VB-001-01"

_ARABIC_WORD = re.compile(
    r"[\u0621-\u063A\u0641-\u064A\u0671-\u06D3"
    r"\u064B-\u065F\u0670]+"
)
_HARD_STOP = re.compile(
    r"(?P<word>[\u0621-\u063A\u0641-\u064A\u0671-\u06D3"
    r"\u064B-\u065F\u0670]+)"
    r"(?P<punct>\.\.\.|…|[.!؟؛])"
)
_COMMA = re.compile(
    r"(?P<word>[\u0621-\u063A\u0641-\u064A\u0671-\u06D3"
    r"\u064B-\u065F\u0670]+)،"
)

_DIACRITICS = {
    chr(value)
    for value in range(0x064B, 0x0660)
} | {"\u0670"}
_SHORT_VOWELS_AND_TANWIN = {
    "\u064B",
    "\u064C",
    "\u064D",
    "\u064E",
    "\u064F",
    "\u0650",
}
_FATHATAN = "\u064B"
_FATHA = "\u064E"
_SHADDA = "\u0651"
_SUKUN = "\u0652"

# Narrow user-confirmed actual comma stop. No connector-wide heuristic.
_MANUAL_COMMA_OVERRIDES = (
    {
        "block_id": "VB-001-01",
        "word_plain": "منعه",
        "next_plain_prefix": "ولا غموض الأمر",
        "reason": "USER_CONFIRMED_AUDIBLE_ACTUAL_STOP",
    },
)


class ActualStopWaqfV3Error(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StopEvent:
    start: int
    end: int
    word_before: str
    word_after: str
    punctuation: str
    stop_type: str
    reason: str
    confidence: str
    phonetic_substitution: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "word_before": self.word_before,
            "word_after": self.word_after,
            "punctuation": self.punctuation,
            "stop_type": self.stop_type,
            "reason": self.reason,
            "confidence": self.confidence,
            "phonetic_substitution": self.phonetic_substitution,
        }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def strip_marks(text: str) -> str:
    # Remove Arabic vocalization only. Do not decompose and erase hamza,
    # because manual performance overrides must match lexical spelling.
    return "".join(
        character
        for character in text
        if character not in _DIACRITICS
    )


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", strip_marks(text)).strip()


def _next_plain_after(text: str, index: int, limit: int = 80) -> str:
    return _plain(text[index:index + limit]).lstrip(" ،؛:.!؟…")


def _previous_base_index(chars: list[str], before: int) -> int | None:
    for index in range(before - 1, -1, -1):
        if chars[index] not in _DIACRITICS:
            return index
    return None


def _marks_after(chars: list[str], base_index: int) -> tuple[int, int]:
    end = base_index + 1
    while end < len(chars) and chars[end] in _DIACRITICS:
        end += 1
    return base_index + 1, end


def phonetic_waqf_word(word: str) -> tuple[str, str | None]:
    """Return the TTS pause form plus any intentional base-letter change."""
    if not word:
        return word, None

    chars = list(word)
    bases = [
        index
        for index, character in enumerate(chars)
        if character not in _DIACRITICS
    ]
    if not bases:
        return word, None

    final_index = bases[-1]
    final_letter = chars[final_index]
    mark_start, mark_end = _marks_after(chars, final_index)
    final_marks = chars[mark_start:mark_end]

    # At waqf, taa marbuta is pronounced as haa. This is a TTS-only
    # phonetic substitution; canonical/display Arabic remains unchanged.
    if final_letter == "ة":
        chars[final_index] = "ه"
        chars[mark_start:mark_end] = [_SUKUN]
        return "".join(chars), "TA_MARBUTA_TO_HAA_AT_WAQF"

    # Fathatan before its supporting final alif becomes a long /aa/.
    if final_letter == "ا":
        previous_index = _previous_base_index(chars, final_index)
        if previous_index is not None:
            previous_start, previous_end = _marks_after(
                chars,
                previous_index,
            )
            previous_marks = chars[previous_start:previous_end]
            chars[previous_start:previous_end] = [
                _FATHA if mark == _FATHATAN else mark
                for mark in previous_marks
            ]

        final_index = max(
            index
            for index, character in enumerate(chars)
            if character not in _DIACRITICS
        )
        mark_start, mark_end = _marks_after(chars, final_index)
        chars[mark_start:mark_end] = [
            mark
            for mark in chars[mark_start:mark_end]
            if mark not in _SHORT_VOWELS_AND_TANWIN
            and mark != _SUKUN
        ]
        return "".join(chars), None

    # Alif maqsura and madda are already pause-safe long vowels.
    if final_letter in {"ى", "آ"}:
        chars[mark_start:mark_end] = [
            mark
            for mark in final_marks
            if mark not in _SHORT_VOWELS_AND_TANWIN
            and mark != _SUKUN
        ]
        return "".join(chars), None

    retained = [
        mark
        for mark in final_marks
        if mark not in _SHORT_VOWELS_AND_TANWIN
        and mark != _SUKUN
    ]

    # Final waw/yaa without a short-vowel mark is treated as a long vowel.
    if (
        final_letter in {"و", "ي"}
        and not any(
            mark in _SHORT_VOWELS_AND_TANWIN
            for mark in final_marks
        )
    ):
        replacement = retained
    elif _SHADDA in retained:
        replacement = retained
    else:
        replacement = retained + [_SUKUN]

    chars[mark_start:mark_end] = replacement
    return "".join(chars), None


def _manual_override_for(
    block_id: str,
    word: str,
    next_plain: str,
) -> Mapping[str, str] | None:
    word_plain = _plain(word)
    for override in _MANUAL_COMMA_OVERRIDES:
        if str(override["block_id"]) != block_id:
            continue
        if str(override["word_plain"]) != word_plain:
            continue
        if not next_plain.startswith(
            str(override["next_plain_prefix"])
        ):
            continue
        return override
    return None


def _hard_stop_events(
    text: str,
) -> list[tuple[int, int, str, str, str, str, str]]:
    events: list[tuple[int, int, str, str, str, str, str]] = []
    for match in _HARD_STOP.finditer(text):
        punctuation = match.group("punct")
        events.append(
            (
                match.start("word"),
                match.end("word"),
                match.group("word"),
                punctuation,
                "HARD_PUNCTUATION",
                (
                    "SEMICOLON_ACTUAL_STOP"
                    if punctuation == "؛"
                    else "EXPLICIT_SENTENCE_OR_ELLIPSIS_STOP"
                ),
                "HIGH",
            )
        )
    return events


def _comma_decisions(
    block_id: str,
    text: str,
) -> tuple[
    list[tuple[int, int, str, str, str, str, str]],
    list[dict[str, Any]],
]:
    actual: list[
        tuple[int, int, str, str, str, str, str]
    ] = []
    preserved: list[dict[str, Any]] = []

    for match in _COMMA.finditer(text):
        after = _next_plain_after(text, match.end())
        override = _manual_override_for(
            block_id,
            match.group("word"),
            after,
        )
        if override is not None:
            actual.append(
                (
                    match.start("word"),
                    match.end("word"),
                    match.group("word"),
                    "،",
                    "MANUAL_CONFIRMED_COMMA_STOP",
                    str(override["reason"]),
                    "USER_CONFIRMED",
                )
            )
            continue

        preserved.append(
            {
                "word": match.group("word"),
                "word_plain": _plain(match.group("word")),
                "next_context_plain": after,
                "position": match.start("word"),
                "decision": "CONNECTED_READING_PRESERVED",
                "reason": (
                    "COMMA_IS_NOT_AN_ACTUAL_STOP_WITHOUT_"
                    "EXPLICIT_PERFORMANCE_EVIDENCE"
                ),
            }
        )

    return actual, preserved


def _block_end_event(
    text: str,
    pause_after_ms: int,
    occupied: set[tuple[int, int]],
) -> tuple[int, int, str, str, str, str, str] | None:
    if pause_after_ms < ACTUAL_BLOCK_PAUSE_THRESHOLD_MS:
        return None

    matches = list(_ARABIC_WORD.finditer(text))
    if not matches:
        return None

    match = matches[-1]
    span = (match.start(), match.end())
    if span in occupied:
        return None

    return (
        match.start(),
        match.end(),
        match.group(0),
        "<BLOCK_END>",
        "EXPLICIT_BLOCK_END_PAUSE",
        (
            f"PAUSE_AFTER_{pause_after_ms}MS_"
            f"MEETS_{ACTUAL_BLOCK_PAUSE_THRESHOLD_MS}MS_THRESHOLD"
        ),
        "HIGH",
    )


def process_block(
    block: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    output = deepcopy(dict(block))
    block_id = str(block.get("block_id") or "")
    original = str(
        block.get("tts_text_ar")
        or block.get("text_ar")
        or ""
    )
    if not original.strip():
        raise ActualStopWaqfV3Error(
            f"TTS_TEXT_REQUIRED:{block_id}"
        )

    raw_events = _hard_stop_events(original)
    comma_actual, comma_preserved = _comma_decisions(
        block_id,
        original,
    )
    raw_events.extend(comma_actual)

    occupied = {(start, end) for start, end, *_ in raw_events}
    end_event = _block_end_event(
        original,
        int(block.get("pause_after_ms", 0) or 0),
        occupied,
    )
    if end_event is not None:
        raw_events.append(end_event)

    merged: dict[
        tuple[int, int],
        tuple[int, int, str, str, str, str, str],
    ] = {}
    priority = {
        "MANUAL_CONFIRMED_COMMA_STOP": 3,
        "HARD_PUNCTUATION": 2,
        "EXPLICIT_BLOCK_END_PAUSE": 1,
    }
    for event in raw_events:
        key = (event[0], event[1])
        current = merged.get(key)
        if (
            current is None
            or priority[event[4]] > priority[current[4]]
        ):
            merged[key] = event

    processed = original
    stop_events: list[StopEvent] = []
    for (
        start,
        end,
        word,
        punctuation,
        stop_type,
        reason,
        confidence,
    ) in sorted(
        merged.values(),
        key=lambda value: value[0],
        reverse=True,
    ):
        transformed, substitution = phonetic_waqf_word(word)
        processed = processed[:start] + transformed + processed[end:]
        stop_events.append(
            StopEvent(
                start=start,
                end=end,
                word_before=word,
                word_after=transformed,
                punctuation=punctuation,
                stop_type=stop_type,
                reason=reason,
                confidence=confidence,
                phonetic_substitution=substitution,
            )
        )

    stop_events.reverse()

    output["tts_text_ar"] = processed
    output["actual_stop_waqf_v3"] = {
        "release": RELEASE,
        "status": "LINGUISTICALLY_HARDENED_REVIEW_CANDIDATE",
        "threshold_ms": ACTUAL_BLOCK_PAUSE_THRESHOLD_MS,
        "comma_default": "CONNECTED_READING",
        "manual_comma_override_count": sum(
            event.stop_type == "MANUAL_CONFIRMED_COMMA_STOP"
            for event in stop_events
        ),
        "actual_stop_count": len(stop_events),
        "connected_comma_count": len(comma_preserved),
        "events": [event.as_dict() for event in stop_events],
        "connected_commas_preserved": comma_preserved,
    }

    changed_events = [
        event
        for event in stop_events
        if event.word_before != event.word_after
    ]
    audit = {
        "block_id": block_id,
        "pause_before_ms": int(block.get("pause_before_ms", 0) or 0),
        "pause_after_ms": int(block.get("pause_after_ms", 0) or 0),
        "text_before": original,
        "text_after": processed,
        "actual_stop_count": len(stop_events),
        "changed_stop_count": len(changed_events),
        "connected_comma_count": len(comma_preserved),
        "manual_comma_stop_count": sum(
            event.stop_type == "MANUAL_CONFIRMED_COMMA_STOP"
            for event in stop_events
        ),
        "ta_marbuta_phonetic_substitution_count": sum(
            event.phonetic_substitution
            == "TA_MARBUTA_TO_HAA_AT_WAQF"
            for event in stop_events
        ),
        "events": [event.as_dict() for event in stop_events],
        "connected_commas_preserved": comma_preserved,
        "canonical_text_untouched": True,
    }
    return output, audit


def process_script(
    script: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = deepcopy(dict(script))
    segments = candidate.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ActualStopWaqfV3Error("SCRIPT_SEGMENTS_REQUIRED")

    block_audits: list[dict[str, Any]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            raise ActualStopWaqfV3Error("SEGMENT_OBJECT_REQUIRED")
        blocks = segment.get("performance_blocks")
        if not isinstance(blocks, list) or not blocks:
            raise ActualStopWaqfV3Error(
                "PERFORMANCE_BLOCKS_REQUIRED:"
                + str(segment.get("segment_id") or "")
            )

        processed_blocks: list[dict[str, Any]] = []
        for block in blocks:
            if not isinstance(block, Mapping):
                raise ActualStopWaqfV3Error("BLOCK_OBJECT_REQUIRED")
            processed, audit = process_block(block)
            audit["segment_id"] = str(
                segment.get("segment_id") or ""
            )
            processed_blocks.append(processed)
            block_audits.append(audit)
        segment["performance_blocks"] = processed_blocks

    candidate["status"] = "ACTUAL_STOP_WAQF_V3_REVIEW_READY"
    candidate["tts_execution_authorized"] = False
    candidate["paid_execution_authorized"] = False
    candidate["waqf_human_review_required"] = True
    candidate["actual_stop_waqf_policy_v3"] = {
        "release": RELEASE,
        "status": "ACTIVE_REVIEW_CANDIDATE",
        "actual_stop_sources": [
            "EXPLICIT_SENTENCE_END",
            "ELLIPSIS",
            "SEMICOLON",
            "EXPLICIT_BLOCK_END_AT_OR_ABOVE_400MS",
            "NARROW_USER_CONFIRMED_COMMA_OVERRIDE",
        ],
        "comma_default": "CONNECTED_READING_PRESERVED",
        "connector_heuristic_disabled": True,
        "ta_marbuta_pause_pronunciation": "HAA_WITH_SUKUN",
        "canonical_text_modified": False,
        "display_text_modified": False,
        "tts_text_ar_only": True,
    }

    validate_performance_script(candidate)

    total_stops = sum(
        item["actual_stop_count"]
        for item in block_audits
    )
    changed_stops = sum(
        item["changed_stop_count"]
        for item in block_audits
    )
    preserved_commas = sum(
        item["connected_comma_count"]
        for item in block_audits
    )
    manual_comma_stops = sum(
        item["manual_comma_stop_count"]
        for item in block_audits
    )
    ta_marbuta_substitutions = sum(
        item["ta_marbuta_phonetic_substitution_count"]
        for item in block_audits
    )
    hard_stops = sum(
        1
        for item in block_audits
        for event in item["events"]
        if event["stop_type"] == "HARD_PUNCTUATION"
    )
    block_end_stops = sum(
        1
        for item in block_audits
        for event in item["events"]
        if event["stop_type"] == "EXPLICIT_BLOCK_END_PAUSE"
    )

    sample = next(
        (
            item
            for item in block_audits
            if item["block_id"] == SAMPLE_BLOCK_ID
        ),
        None,
    )
    if sample is None:
        raise ActualStopWaqfV3Error("SAMPLE_BLOCK_NOT_FOUND")

    report = {
        "schema_version": SCHEMA_VERSION,
        "release": RELEASE,
        "episode_id": str(
            script.get("episode_id") or "episode-001-adam"
        ),
        "status": "PASS_LINGUISTIC_REVIEW_READY",
        "segment_count": len(segments),
        "performance_block_count": len(block_audits),
        "actual_stop_count": total_stops,
        "changed_stop_count": changed_stops,
        "hard_punctuation_stop_count": hard_stops,
        "manual_confirmed_comma_stop_count": manual_comma_stops,
        "performance_block_end_stop_count": block_end_stops,
        "connected_commas_preserved_count": preserved_commas,
        "ta_marbuta_phonetic_substitution_count": (
            ta_marbuta_substitutions
        ),
        "connector_heuristic_disabled": True,
        "canonical_and_display_text_preserved": True,
        "sample_block": sample,
        "blocks": block_audits,
        "tts_execution_authorized": False,
        "paid_execution_authorized": False,
        "next_stage": (
            "HUMAN_WAQF_V3_REVIEW_AND_SECOND_SAMPLE_AUTHORIZATION"
        ),
    }
    return candidate, report


def build_cast_candidate(
    episode_id: str,
    script_candidate: Mapping[str, Any],
    storyboard: Mapping[str, Any],
) -> dict[str, Any]:
    plan = build_episode_voice_cast_plan(
        episode_id,
        script_candidate,
        storyboard,
    ).as_dict()
    plan["schema_version"] = "siraj-elevenlabs-waqf-cast-plan-v3"
    plan["release"] = RELEASE
    plan["status"] = "REVIEW_READY_NO_PAID_EXECUTION"
    plan["tts_execution_authorized"] = False
    plan["paid_execution_authorized"] = False
    for item in plan.get("queue_items", []) or []:
        if isinstance(item, dict):
            item["status"] = "WAQF_V3_REVIEW_REQUIRED_NO_PAID_EXECUTION"
    return plan


def build_second_sample_request(
    episode_id: str,
    cast_plan: Mapping[str, Any],
) -> dict[str, Any]:
    queue_items = [
        item
        for item in cast_plan.get("queue_items", []) or []
        if isinstance(item, Mapping)
    ]
    sample_matches = [
        item
        for item in queue_items
        if str(item.get("block_id") or "") == SAMPLE_BLOCK_ID
    ]
    if len(sample_matches) != 1:
        raise ActualStopWaqfV3Error(
            f"SAMPLE_QUEUE_MATCH_COUNT:{len(sample_matches)}"
        )
    sample = sample_matches[0]
    total_chars = sum(
        len(str(item.get("text_ar") or ""))
        for item in queue_items
    )
    sample_chars = len(str(sample.get("text_ar") or ""))
    reserve_share = round(
        INTERNAL_RESERVE_USD * sample_chars / total_chars,
        6,
    )
    ceiling = round(
        max(0.01, math.ceil(reserve_share * 100.0) / 100.0),
        2,
    )
    return {
        "schema_version": "siraj-elevenlabs-waqf-sample-request-v3",
        "release": RELEASE,
        "episode_id": episode_id,
        "status": "AWAITING_EXPLICIT_SECOND_SAMPLE_AUTHORIZATION",
        "reason": "LINGUISTICALLY_HARDENED_ACTUAL_STOP_WAQF",
        "queue_id": "TTS-WAQF-V3-SAMPLE-VB-001-01",
        "block_id": SAMPLE_BLOCK_ID,
        "segment_id": str(sample.get("segment_id") or ""),
        "voice_slot": str(sample.get("voice_slot") or ""),
        "voice_id": str(sample.get("voice_id") or ""),
        "model_id": str(sample.get("model_id") or ""),
        "voice_settings": dict(sample.get("voice_settings") or {}),
        "output_format": "mp3_44100_128",
        "text_ar": str(sample.get("text_ar") or ""),
        "character_count_unicode": sample_chars,
        "internal_reserve_share_usd": reserve_share,
        "suggested_authorization_ceiling_usd": ceiling,
        "maximum_provider_requests": 1,
        "sample_generation_authorized": False,
        "full_episode_tts_authorized": False,
        "hidden_paid_retry": "FORBIDDEN",
        "automatic_resubmission": "FORBIDDEN",
        "output_path_relative": (
            f"projects/{episode_id}/audio/tts/samples/"
            "VB-001-01-primary-narrator-waqf-v3-sample.mp3"
        ),
        "next_stage": "EXPLICIT_SECOND_SAMPLE_AUTHORIZATION",
    }


def write_outputs(
    repo: Path,
    *,
    episode_id: str,
    source_candidate: Mapping[str, Any],
    script_candidate: Mapping[str, Any],
    report: Mapping[str, Any],
    cast_plan: Mapping[str, Any],
    sample_request: Mapping[str, Any],
) -> dict[str, str]:
    episode = repo / "projects" / episode_id
    source_path = (
        episode
        / "script"
        / "arabic-performance-source-v3-waqf-candidate.json"
    )
    script_path = (
        episode
        / "script"
        / "episode-script-v3-waqf-candidate.json"
    )
    report_path = (
        episode
        / "orchestration"
        / "arabic-actual-stop-waqf-audit-v3.json"
    )
    review_path = (
        episode
        / "script"
        / "arabic-actual-stop-waqf-review-v3.txt"
    )
    cast_path = (
        episode
        / "orchestration"
        / "elevenlabs-voice-cast-plan-v4-waqf-candidate.json"
    )
    sample_path = (
        episode
        / "audio"
        / "tts"
        / "tts-waqf-sample-authorization-request-v3.json"
    )
    readiness_path = (
        episode
        / "orchestration"
        / "full-episode-tts-waqf-readiness-v3.json"
    )

    readiness = {
        "schema_version": "siraj-full-episode-tts-waqf-readiness-v3",
        "release": RELEASE,
        "episode_id": episode_id,
        "status": "BLOCKED_PENDING_WAQF_V3_AND_SAMPLE_APPROVAL",
        "performance_block_count": report["performance_block_count"],
        "actual_stop_count": report["actual_stop_count"],
        "manual_confirmed_comma_stop_count": report[
            "manual_confirmed_comma_stop_count"
        ],
        "connected_commas_preserved_count": report[
            "connected_commas_preserved_count"
        ],
        "ta_marbuta_phonetic_substitution_count": report[
            "ta_marbuta_phonetic_substitution_count"
        ],
        "connector_heuristic_disabled": True,
        "second_sample_required": True,
        "full_episode_tts_authorized": False,
        "paid_execution_authorized": False,
        "hidden_paid_retry": "FORBIDDEN",
        "next_stage": (
            "HUMAN_WAQF_V3_REVIEW_THEN_SECOND_SAMPLE_AUTHORIZATION"
        ),
    }

    for path, payload in (
        (source_path, source_candidate),
        (script_path, script_candidate),
        (report_path, report),
        (cast_path, cast_plan),
        (sample_path, sample_request),
        (readiness_path, readiness),
    ):
        _write_json(path, payload)

    sample = report["sample_block"]
    review_lines = [
        "سراج — مراجعة الوقف الفعلي اللغوية V3",
        "",
        f"STATUS={report['status']}",
        f"PERFORMANCE_BLOCKS={report['performance_block_count']}",
        f"ACTUAL_STOPS={report['actual_stop_count']}",
        (
            "MANUAL_CONFIRMED_COMMA_STOPS="
            f"{report['manual_confirmed_comma_stop_count']}"
        ),
        (
            "CONNECTED_COMMAS_PRESERVED="
            f"{report['connected_commas_preserved_count']}"
        ),
        (
            "TA_MARBUTA_TO_HAA="
            f"{report['ta_marbuta_phonetic_substitution_count']}"
        ),
        "CONNECTOR_HEURISTIC=DISABLED",
        "",
        "العينة VB-001-01 — قبل:",
        sample["text_before"],
        "",
        "العينة VB-001-01 — بعد:",
        sample["text_after"],
        "",
        "قرارات العينة:",
    ]
    for event in sample["events"]:
        review_lines.append(
            "- "
            + event["word_before"]
            + " -> "
            + event["word_after"]
            + " | "
            + event["stop_type"]
            + " | "
            + event["reason"]
        )
    review_lines.extend(
        [
            "",
            "السياسة:",
            "- الفاصلة تبقى وصلًا ما لم يوجد دليل أداء صريح.",
            "- أُبقي فقط توقف «مَنَعَهْ، وَلَا» المثبت من مراجعة المستخدم.",
            "- التاء المربوطة تُكتب هاءً ساكنة في نص TTS عند الوقف.",
            "- النص الأصلي ونص العرض لم يتغيرا.",
            "- لا يوجد تفويض لتوليد العينة أو الحلقة الكاملة.",
            "",
        ]
    )
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(
        "\n".join(review_lines),
        encoding="utf-8",
        newline="\n",
    )

    return {
        "source_candidate": str(
            source_path.relative_to(repo)
        ).replace("\\", "/"),
        "script_candidate": str(
            script_path.relative_to(repo)
        ).replace("\\", "/"),
        "audit_report": str(
            report_path.relative_to(repo)
        ).replace("\\", "/"),
        "human_review_text": str(
            review_path.relative_to(repo)
        ).replace("\\", "/"),
        "waqf_cast_plan": str(
            cast_path.relative_to(repo)
        ).replace("\\", "/"),
        "second_sample_request": str(
            sample_path.relative_to(repo)
        ).replace("\\", "/"),
        "full_episode_readiness": str(
            readiness_path.relative_to(repo)
        ).replace("\\", "/"),
    }
