"""Actual-stop Arabic waqf processing for SIRAJ TTS performance text.

Only ``tts_text_ar`` is changed. Canonical/display text remains untouched.
Hard sentence stops, semicolons, approved strong-clause commas, and real block
boundaries are processed. Incidental commas remain in connected-reading form.
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
from typing import Any, Iterable, Mapping

from src.application.arabic_performance_script_v2 import (
    validate_performance_script,
)
from src.application.elevenlabs_voice_casting_v1 import (
    build_episode_voice_cast_plan,
)

RELEASE = "SIRAJ_ARABIC_ACTUAL_STOP_WAQF_V2"
SCHEMA_VERSION = "siraj-arabic-actual-stop-waqf-v2"

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
    "\u064B",  # fathatan
    "\u064C",  # dammatan
    "\u064D",  # kasratan
    "\u064E",  # fatha
    "\u064F",  # damma
    "\u0650",  # kasra
}
_SHADDA = "\u0651"
_SUKUN = "\u0652"
_LONG_FINALS = {"ا", "ى", "و", "ي", "آ"}
_STRONG_CONNECTORS = (
    "ولا ",
    "ولكن ",
    "لكن ",
    "بل ",
    "أما ",
    "غير أن ",
    "إلا أن ",
    "ومع ذلك ",
    "على أن ",
)


class ActualStopWaqfError(RuntimeError):
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
    return "".join(
        character
        for character in unicodedata.normalize("NFD", text)
        if unicodedata.category(character) != "Mn"
    )


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", strip_marks(text)).strip()


def _next_plain_after(text: str, index: int, limit: int = 42) -> str:
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


def waqf_word(word: str) -> str:
    """Return a TTS-only pause form while preserving Arabic base letters."""
    if not word:
        return word

    chars = list(word)
    bases = [
        index for index, character in enumerate(chars)
        if character not in _DIACRITICS
    ]
    if not bases:
        return word

    final_index = bases[-1]
    final_letter = chars[final_index]

    # Fathatan before a final supporting alif becomes a long /aa/ at pause.
    if final_letter == "ا":
        previous_index = _previous_base_index(chars, final_index)
        if previous_index is not None:
            mark_start, mark_end = _marks_after(chars, previous_index)
            marks = chars[mark_start:mark_end]
            if "\u064B" in marks:
                chars[mark_start:mark_end] = [
                    "\u064E" if mark == "\u064B" else mark
                    for mark in marks
                ]
        # A final alif is already a pause-safe long vowel.
        final_index = max(
            index for index, character in enumerate(chars)
            if character not in _DIACRITICS
        )
        mark_start, mark_end = _marks_after(chars, final_index)
        chars[mark_start:mark_end] = [
            mark for mark in chars[mark_start:mark_end]
            if mark not in _SHORT_VOWELS_AND_TANWIN
        ]
        return "".join(chars)

    mark_start, mark_end = _marks_after(chars, final_index)
    marks = chars[mark_start:mark_end]
    retained = [
        mark for mark in marks
        if mark not in _SHORT_VOWELS_AND_TANWIN
        and mark != _SUKUN
    ]

    # Long final letters and alif maqsura do not receive an added sukun.
    if final_letter in _LONG_FINALS:
        replacement = retained
    elif _SHADDA in retained:
        # Keep the gemination marker without a final short vowel.
        replacement = retained
    else:
        replacement = retained + [_SUKUN]

    chars[mark_start:mark_end] = replacement
    return "".join(chars)


def _hard_stop_events(text: str) -> list[tuple[int, int, str, str, str, str]]:
    events: list[tuple[int, int, str, str, str, str]] = []
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
                    else "SENTENCE_OR_ELLIPSIS_ACTUAL_STOP"
                ),
            )
        )
    return events


def _strong_comma_events(
    text: str,
) -> tuple[
    list[tuple[int, int, str, str, str, str]],
    list[dict[str, Any]],
]:
    actual: list[tuple[int, int, str, str, str, str]] = []
    preserved: list[dict[str, Any]] = []

    for match in _COMMA.finditer(text):
        after = _next_plain_after(text, match.end())
        is_strong = any(after.startswith(value) for value in _STRONG_CONNECTORS)
        entry = {
            "word": match.group("word"),
            "word_plain": _plain(match.group("word")),
            "next_context_plain": after,
            "position": match.start("word"),
        }
        if is_strong:
            actual.append(
                (
                    match.start("word"),
                    match.end("word"),
                    match.group("word"),
                    "،",
                    "STRONG_CLAUSE_COMMA",
                    "COMPLETE_CLAUSE_BEFORE_STRONG_DISCOURSE_CONNECTOR",
                )
            )
        else:
            entry["decision"] = "CONNECTED_READING_PRESERVED"
            entry["reason"] = "INCIDENTAL_OR_ENUMERATIVE_COMMA"
            preserved.append(entry)
    return actual, preserved


def _block_end_event(
    text: str,
    pause_after_ms: int,
    occupied: set[tuple[int, int]],
) -> tuple[int, int, str, str, str, str] | None:
    if pause_after_ms < ACTUAL_BLOCK_PAUSE_THRESHOLD_MS:
        return None

    matches = list(_ARABIC_WORD.finditer(text))
    if not matches:
        return None
    match = matches[-1]
    span = (match.start(), match.end())
    if span in occupied:
        return None

    suffix = text[match.end():].strip()
    punctuation = suffix[:3] if suffix else "<BLOCK_END>"
    return (
        match.start(),
        match.end(),
        match.group(0),
        punctuation,
        "PERFORMANCE_BLOCK_END",
        (
            f"PAUSE_AFTER_{pause_after_ms}MS_"
            f"MEETS_{ACTUAL_BLOCK_PAUSE_THRESHOLD_MS}MS_THRESHOLD"
        ),
    )


def process_block(block: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    output = deepcopy(dict(block))
    original = str(
        block.get("tts_text_ar")
        or block.get("text_ar")
        or ""
    )
    if not original.strip():
        raise ActualStopWaqfError(
            "TTS_TEXT_REQUIRED:"
            + str(block.get("block_id") or "")
        )

    raw_events = _hard_stop_events(original)
    comma_actual, comma_preserved = _strong_comma_events(original)
    raw_events.extend(comma_actual)

    occupied = {(start, end) for start, end, *_ in raw_events}
    end_event = _block_end_event(
        original,
        int(block.get("pause_after_ms", 0) or 0),
        occupied,
    )
    if end_event is not None:
        raw_events.append(end_event)

    # Merge duplicate word spans and preserve the strongest reason.
    merged: dict[tuple[int, int], tuple[int, int, str, str, str, str]] = {}
    priority = {
        "STRONG_CLAUSE_COMMA": 3,
        "HARD_PUNCTUATION": 2,
        "PERFORMANCE_BLOCK_END": 1,
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
    for start, end, word, punctuation, stop_type, reason in sorted(
        merged.values(),
        key=lambda value: value[0],
        reverse=True,
    ):
        transformed = waqf_word(word)
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
                confidence="HIGH",
            )
        )

    stop_events.reverse()

    if strip_marks(processed) != strip_marks(original):
        raise ActualStopWaqfError(
            "BASE_TEXT_CHANGED:"
            + str(block.get("block_id") or "")
        )

    output["tts_text_ar"] = processed
    output["actual_stop_waqf_v2"] = {
        "release": RELEASE,
        "status": "HIGH_CONFIDENCE_STOPS_APPLIED",
        "threshold_ms": ACTUAL_BLOCK_PAUSE_THRESHOLD_MS,
        "actual_stop_count": len(stop_events),
        "connected_comma_count": len(comma_preserved),
        "events": [event.as_dict() for event in stop_events],
        "connected_commas_preserved": comma_preserved,
    }

    changed_events = [
        event for event in stop_events
        if event.word_before != event.word_after
    ]
    audit = {
        "block_id": str(block.get("block_id") or ""),
        "pause_before_ms": int(block.get("pause_before_ms", 0) or 0),
        "pause_after_ms": int(block.get("pause_after_ms", 0) or 0),
        "text_before": original,
        "text_after": processed,
        "actual_stop_count": len(stop_events),
        "changed_stop_count": len(changed_events),
        "connected_comma_count": len(comma_preserved),
        "events": [event.as_dict() for event in stop_events],
        "connected_commas_preserved": comma_preserved,
        "base_text_preserved": True,
    }
    return output, audit


def process_script(
    script: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate = deepcopy(dict(script))
    segments = candidate.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ActualStopWaqfError("SCRIPT_SEGMENTS_REQUIRED")

    block_audits: list[dict[str, Any]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            raise ActualStopWaqfError("SEGMENT_OBJECT_REQUIRED")
        blocks = segment.get("performance_blocks")
        if not isinstance(blocks, list) or not blocks:
            raise ActualStopWaqfError(
                "PERFORMANCE_BLOCKS_REQUIRED:"
                + str(segment.get("segment_id") or "")
            )

        processed_blocks: list[dict[str, Any]] = []
        for block in blocks:
            if not isinstance(block, Mapping):
                raise ActualStopWaqfError("BLOCK_OBJECT_REQUIRED")
            processed, audit = process_block(block)
            audit["segment_id"] = str(segment.get("segment_id") or "")
            processed_blocks.append(processed)
            block_audits.append(audit)
        segment["performance_blocks"] = processed_blocks

    candidate["status"] = "ACTUAL_STOP_WAQF_V2_REVIEW_READY"
    candidate["tts_execution_authorized"] = False
    candidate["paid_execution_authorized"] = False
    candidate["waqf_human_review_required"] = True
    candidate["actual_stop_waqf_policy_v2"] = {
        "release": RELEASE,
        "status": "ACTIVE_REVIEW_CANDIDATE",
        "actual_stop_sources": [
            "SENTENCE_END",
            "ELLIPSIS",
            "SEMICOLON",
            "STRONG_CLAUSE_COMMA",
            "PERFORMANCE_BLOCK_END_AT_OR_ABOVE_400MS",
        ],
        "incidental_comma_policy": "CONNECTED_READING_PRESERVED",
        "canonical_text_modified": False,
        "display_text_modified": False,
        "tts_text_ar_only": True,
    }

    # The existing validator must still accept every resulting TTS block.
    validate_performance_script(candidate)

    total_stops = sum(item["actual_stop_count"] for item in block_audits)
    changed_stops = sum(item["changed_stop_count"] for item in block_audits)
    preserved_commas = sum(
        item["connected_comma_count"] for item in block_audits
    )
    strong_commas = sum(
        1
        for item in block_audits
        for event in item["events"]
        if event["stop_type"] == "STRONG_CLAUSE_COMMA"
    )
    block_end_stops = sum(
        1
        for item in block_audits
        for event in item["events"]
        if event["stop_type"] == "PERFORMANCE_BLOCK_END"
    )
    hard_stops = sum(
        1
        for item in block_audits
        for event in item["events"]
        if event["stop_type"] == "HARD_PUNCTUATION"
    )

    sample = next(
        (
            item for item in block_audits
            if item["block_id"] == SAMPLE_BLOCK_ID
        ),
        None,
    )
    if sample is None:
        raise ActualStopWaqfError("SAMPLE_BLOCK_NOT_FOUND")

    report = {
        "schema_version": SCHEMA_VERSION,
        "release": RELEASE,
        "episode_id": str(script.get("episode_id") or "episode-001-adam"),
        "status": "PASS_REVIEW_READY",
        "segment_count": len(segments),
        "performance_block_count": len(block_audits),
        "actual_stop_count": total_stops,
        "changed_stop_count": changed_stops,
        "hard_punctuation_stop_count": hard_stops,
        "strong_clause_comma_stop_count": strong_commas,
        "performance_block_end_stop_count": block_end_stops,
        "connected_commas_preserved_count": preserved_commas,
        "canonical_base_text_preserved": True,
        "modified_fields": [
            "segments[].performance_blocks[].tts_text_ar",
            "segments[].performance_blocks[].actual_stop_waqf_v2",
        ],
        "sample_block": sample,
        "blocks": block_audits,
        "tts_execution_authorized": False,
        "paid_execution_authorized": False,
        "next_stage": "HUMAN_WAQF_DIFF_REVIEW_AND_SECOND_SAMPLE_AUTHORIZATION",
    }
    return candidate, report


def _all_blocks(script: Mapping[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for segment in script.get("segments", []) or []:
        if not isinstance(segment, Mapping):
            continue
        for block in segment.get("performance_blocks", []) or []:
            if isinstance(block, Mapping):
                output.append(dict(block))
    return output


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
    plan["schema_version"] = "siraj-elevenlabs-waqf-cast-plan-v2"
    plan["release"] = RELEASE
    plan["status"] = "REVIEW_READY_NO_PAID_EXECUTION"
    plan["tts_execution_authorized"] = False
    plan["paid_execution_authorized"] = False
    for item in plan.get("queue_items", []) or []:
        if isinstance(item, dict):
            item["status"] = "WAQF_REVIEW_REQUIRED_NO_PAID_EXECUTION"
    return plan


def build_second_sample_request(
    episode_id: str,
    cast_plan: Mapping[str, Any],
) -> dict[str, Any]:
    queue_items = [
        item for item in cast_plan.get("queue_items", []) or []
        if isinstance(item, Mapping)
    ]
    sample_matches = [
        item for item in queue_items
        if str(item.get("block_id") or "") == SAMPLE_BLOCK_ID
    ]
    if len(sample_matches) != 1:
        raise ActualStopWaqfError(
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
        "schema_version": "siraj-elevenlabs-waqf-sample-request-v2",
        "release": RELEASE,
        "episode_id": episode_id,
        "status": "AWAITING_EXPLICIT_SECOND_SAMPLE_AUTHORIZATION",
        "supersedes_sample": (
            "VB-001-01-primary-narrator-sample.mp3"
        ),
        "reason": "ACTUAL_STOP_WAQF_CORRECTION",
        "queue_id": "TTS-WAQF-SAMPLE-VB-001-01",
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
            "VB-001-01-primary-narrator-waqf-sample-v2.mp3"
        ),
        "next_stage": "EXPLICIT_SECOND_SAMPLE_AUTHORIZATION",
    }


def build_full_episode_readiness(
    episode_id: str,
    script_candidate: Mapping[str, Any],
    cast_plan: Mapping[str, Any],
    report: Mapping[str, Any],
) -> dict[str, Any]:
    blocks = _all_blocks(script_candidate)
    return {
        "schema_version": "siraj-full-episode-tts-waqf-readiness-v2",
        "release": RELEASE,
        "episode_id": episode_id,
        "status": "BLOCKED_PENDING_WAQF_REVIEW_AND_SAMPLE_APPROVAL",
        "performance_block_count": len(blocks),
        "voice_cast_queue_item_count": len(
            cast_plan.get("queue_items", []) or []
        ),
        "actual_stop_count": report["actual_stop_count"],
        "changed_stop_count": report["changed_stop_count"],
        "connected_commas_preserved_count": (
            report["connected_commas_preserved_count"]
        ),
        "canonical_base_text_preserved": True,
        "human_waqf_review_required": True,
        "second_sample_required": True,
        "full_episode_tts_authorized": False,
        "paid_execution_authorized": False,
        "hidden_paid_retry": "FORBIDDEN",
        "next_stage": (
            "HUMAN_WAQF_REVIEW_THEN_SECOND_SAMPLE_AUTHORIZATION"
        ),
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
    readiness: Mapping[str, Any],
) -> dict[str, str]:
    episode = repo / "projects" / episode_id
    source_path = (
        episode
        / "script"
        / "arabic-performance-source-v2-waqf-candidate.json"
    )
    script_path = (
        episode
        / "script"
        / "episode-script-v2-waqf-candidate.json"
    )
    report_path = (
        episode
        / "orchestration"
        / "arabic-actual-stop-waqf-audit-v2.json"
    )
    review_path = (
        episode
        / "script"
        / "arabic-actual-stop-waqf-review-v2.txt"
    )
    cast_path = (
        episode
        / "orchestration"
        / "elevenlabs-voice-cast-plan-v3-waqf-candidate.json"
    )
    sample_path = (
        episode
        / "audio"
        / "tts"
        / "tts-waqf-sample-authorization-request-v2.json"
    )
    readiness_path = (
        episode
        / "orchestration"
        / "full-episode-tts-waqf-readiness-v2.json"
    )
    sample_review_path = (
        episode
        / "audio"
        / "tts"
        / "samples"
        / "VB-001-01-human-review-v2.json"
    )

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
        "سراج — مراجعة الوقف الفعلي V2",
        "",
        f"STATUS={report['status']}",
        f"PERFORMANCE_BLOCKS={report['performance_block_count']}",
        f"ACTUAL_STOPS={report['actual_stop_count']}",
        f"CHANGED_STOPS={report['changed_stop_count']}",
        (
            "STRONG_CLAUSE_COMMA_STOPS="
            f"{report['strong_clause_comma_stop_count']}"
        ),
        (
            "CONNECTED_COMMAS_PRESERVED="
            f"{report['connected_commas_preserved_count']}"
        ),
        "",
        "العينة VB-001-01 — قبل:",
        sample["text_before"],
        "",
        "العينة VB-001-01 — بعد:",
        sample["text_after"],
        "",
        "مواضع العينة:",
    ]
    for event in sample["events"]:
        review_lines.append(
            "- "
            + event["word_before"]
            + "  ->  "
            + event["word_after"]
            + " | "
            + event["stop_type"]
            + " | "
            + event["reason"]
        )
    review_lines.extend(
        [
            "",
            "مبدأ التنفيذ:",
            "- الوقف الفعلي وحده يُحوِّل آخر الكلمة إلى صورة الوقف.",
            "- الفاصلة العارضة والتعداد يبقيان على صورة الوصل.",
            "- النص الأصلي ونص العرض لم يتغيرا.",
            "- توليد الصوت الكامل غير مصرح به.",
            "",
        ]
    )
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(
        "\n".join(review_lines),
        encoding="utf-8",
        newline="\n",
    )

    _write_json(
        sample_review_path,
        {
            "schema_version": "siraj-tts-sample-human-review-v2",
            "episode_id": episode_id,
            "block_id": SAMPLE_BLOCK_ID,
            "status": (
                "CONDITIONALLY_APPROVED_"
                "VOICE_ACCEPTED_WAQF_CORRECTION_REQUIRED"
            ),
            "review_source": "USER_REVIEWED_IN_CHAT",
            "voice_quality_decision": "ACCEPTED",
            "linguistic_decision": "WAQF_CORRECTION_REQUIRED",
            "feedback_ar": (
                "الصوت جيد. عند الوقف الفعلي يجب إسكان آخر الكلمة "
                "وعدم إبقاء حركة الوصل، مع عدم تعميم ذلك على كل فاصلة عارضة."
            ),
            "example_before": "مَنَعَهُ،",
            "example_after": "مَنَعَهْ،",
            "second_sample_required": True,
            "full_episode_tts_authorized": False,
        },
    )

    return {
        "source_candidate": str(source_path.relative_to(repo)).replace("\\", "/"),
        "script_candidate": str(script_path.relative_to(repo)).replace("\\", "/"),
        "audit_report": str(report_path.relative_to(repo)).replace("\\", "/"),
        "human_review_text": str(review_path.relative_to(repo)).replace("\\", "/"),
        "waqf_cast_plan": str(cast_path.relative_to(repo)).replace("\\", "/"),
        "second_sample_request": str(sample_path.relative_to(repo)).replace("\\", "/"),
        "full_episode_readiness": str(
            readiness_path.relative_to(repo)
        ).replace("\\", "/"),
        "first_sample_review": str(
            sample_review_path.relative_to(repo)
        ).replace("\\", "/"),
    }
