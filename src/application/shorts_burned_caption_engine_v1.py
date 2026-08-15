"""Offline, fail-closed burned narration captions for SIRAJ Shorts.

This module is intentionally independent of the existing Shorts engine.  It
owns the caption planning contract only; an integrator can pass its returned
contract to a renderer after the normal human/local-render gates have passed.

The module never performs ASR, network work, provider work, paid work, retry,
publication, or video rendering.  Caption text is accepted only from a
hash-bound canonical/trusted narration transcript.  Source timing is mapped
to the Shorts local timebase only through an explicit extractive edit plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
import math
import re
import unicodedata
from typing import Any, Mapping, Sequence


ENGINE_ID = "SIRAJ_SHORTS_BURNED_CAPTION_ENGINE_V1"
ENGINE_VERSION = "1.0.0"
SCHEMA_VERSION = "SIRAJ_SHORTS_BURNED_CAPTION_PLAN_V1"
SHORTS_SCOPE = "SHORT_DERIVATIVE"
LONGFORM_SCOPE = "LONGFORM"
SHORT_LOCAL_TIMEBASE = "SHORT_LOCAL_TIMEBASE"
TEXT_AUTHORITY_NARRATION_ONLY = "NARRATION_ONLY"
CAPTION_MODE = "BURNED_NARRATION_CAPTIONS"

CAPTIONS_DEFAULT_ENABLED = True
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_ASPECT_RATIO = "9:16"
MAX_LINES = 2
MAX_CHARS_PER_LINE = 42
MAX_WORDS_PER_CUE = 8
COARSE_MAX_DURATION_SECONDS = 8.0
COARSE_MAX_CHARACTERS = 120
EPSILON = 1e-6
HASH_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)

TIMING_AUTHORITY_WORD = "WORD_BOUNDARY"
TIMING_AUTHORITY_PHRASE = "PHRASE_CLAUSE_BOUNDARY"
TIMING_AUTHORITY_SENTENCE = "SENTENCE_BOUNDARY"
TIMING_AUTHORITIES = (
    TIMING_AUTHORITY_WORD,
    TIMING_AUTHORITY_PHRASE,
    TIMING_AUTHORITY_SENTENCE,
)

_PROVENANCE_ALLOWED = frozenset(
    {
        "CANONICAL_TIMED_TRANSCRIPT",
        "SIRAJ_CANONICAL_TIMED_TRANSCRIPT_V1",
        "TRUSTED_TIMING_SOURCE",
        "NARRATION_TRANSCRIPT",
        "NARRATION_TIMING_SOURCE",
    }
)
_PROVENANCE_FORBIDDEN = frozenset(
    {
        "ASR",
        "CLOUD_ASR",
        "INVENTED",
        "PARAPHRASE",
        "SUMMARY",
        "HOOK",
        "CTA",
        "PROMOTIONAL",
        "TITLE_CARD",
        "FACT_OVERLAY",
        "DECORATIVE",
    }
)


class CaptionEngineError(RuntimeError):
    """Base error for the offline caption planner."""


class CaptionBlockedError(CaptionEngineError):
    """Raised when a caption contract cannot be proven safe."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical_json(value)
    return hashlib.sha256(payload).hexdigest()


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and HASH_RE.fullmatch(value.strip()) is not None


def _require_hash(value: Any, field_name: str) -> str:
    if not _is_hash(value):
        raise CaptionBlockedError("CAPTION_HASH_BINDING_REQUIRED", field_name)
    return str(value).strip().lower()


def _number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CaptionBlockedError("CAPTION_TIMING_INVALID", f"{field_name}:NUMBER_REQUIRED")
    result = float(value)
    if not math.isfinite(result):
        raise CaptionBlockedError("CAPTION_TIMING_INVALID", f"{field_name}:FINITE_REQUIRED")
    return result


def _non_empty_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaptionBlockedError("CAPTION_TEXT_INVALID", f"{field_name}:NON_EMPTY_REQUIRED")
    return value


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "to_dict"):
        converted = value.to_dict()
        if isinstance(converted, Mapping):
            return converted
    raise CaptionBlockedError("CAPTION_INPUT_INVALID", f"{field_name}:OBJECT_REQUIRED")


def _as_list(value: Any, field_name: str) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    raise CaptionBlockedError("CAPTION_INPUT_INVALID", f"{field_name}:ARRAY_REQUIRED")


def _pick(value: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in value:
            return value[key]
    return None


def _normalize_scope(scope: Any) -> str:
    normalized = str(scope or "").strip().upper().replace("-", "_")
    if normalized in {"SHORT", "SHORTS", "SHORT_DERIVATIVE", "SHORT_DERIVATIVE_VIDEO"}:
        return SHORTS_SCOPE
    if normalized in {"LONGFORM", "LONG_FORM", "EPISODE"}:
        return LONGFORM_SCOPE
    return normalized


def validate_caption_scope(
    scope: str,
    *,
    burned_captions: bool,
    on_screen_subtitles: bool,
    narration_only: bool = True,
) -> None:
    """Enforce the constitutional scope without a Shorts bypass."""

    normalized = _normalize_scope(scope)
    if normalized == LONGFORM_SCOPE and (burned_captions or on_screen_subtitles):
        raise CaptionBlockedError(
            "LONGFORM_BURNED_CAPTIONS_FORBIDDEN",
            "LONGFORM_BURNED_OR_ON_SCREEN_TEXT",
        )
    if normalized != SHORTS_SCOPE and (burned_captions or on_screen_subtitles):
        raise CaptionBlockedError("CAPTION_SCOPE_FORBIDDEN", normalized or "UNKNOWN_SCOPE")
    if normalized == SHORTS_SCOPE and burned_captions and not narration_only:
        raise CaptionBlockedError("CAPTION_TEXT_AUTHORITY_FORBIDDEN", "NARRATION_ONLY_REQUIRED")
    if normalized == SHORTS_SCOPE and on_screen_subtitles:
        raise CaptionBlockedError("SHORTS_ON_SCREEN_SUBTITLES_FORBIDDEN", "NARRATION_CAPTIONS_ONLY")


@dataclass(frozen=True, slots=True)
class CaptionTranscript:
    """Hash-bound transcript envelope accepted by the caption planner."""

    episode_id: str
    segments: tuple[Mapping[str, Any], ...]
    canonical_transcript_sha256: str
    timing_source_sha256: str
    timing_source_type: str = "CANONICAL_TIMED_TRANSCRIPT"
    source_audio_sha256: str | None = None
    source_video_sha256: str | None = None
    text_provenance: str = "CANONICAL_TIMED_TRANSCRIPT"
    duration_seconds: float | None = None
    schema_version: str = "SIRAJ_CANONICAL_TIMED_TRANSCRIPT_V1"

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        canonical_transcript_sha256: str | None = None,
        timing_source_sha256: str | None = None,
    ) -> "CaptionTranscript":
        segments_value = _pick(value, "segments", "cues", "transcript")
        segments = tuple(
            _mapping(item, f"segments[{index}]")
            for index, item in enumerate(_as_list(segments_value, "segments"))
        )
        transcript_hash = canonical_transcript_sha256 or _pick(
            value,
            "canonical_transcript_sha256",
            "transcript_sha256",
            "source_transcript_sha256",
        )
        timing_hash = timing_source_sha256 or _pick(
            value,
            "timing_source_sha256",
            "source_timing_sha256",
        )
        audio_hash = _pick(value, "source_audio_sha256", "final_narration_sha256")
        video_hash = _pick(value, "source_video_sha256", "episode_video_sha256")
        if audio_hash is not None:
            audio_hash = _require_hash(audio_hash, "source_audio_sha256")
        if video_hash is not None:
            video_hash = _require_hash(video_hash, "source_video_sha256")
        duration = _pick(value, "duration_seconds", "source_duration_seconds")
        raw_provenance = _pick(value, "text_provenance", "text_authority", "provenance")
        if isinstance(raw_provenance, Mapping):
            raw_provenance = "CANONICAL_TIMED_TRANSCRIPT"
        normalized_provenance = str(raw_provenance or "CANONICAL_TIMED_TRANSCRIPT")
        if normalized_provenance.strip().upper() == TEXT_AUTHORITY_NARRATION_ONLY:
            normalized_provenance = "NARRATION_TRANSCRIPT"
        return cls(
            episode_id=str(_pick(value, "episode_id", "source_episode_id") or ""),
            segments=segments,
            canonical_transcript_sha256=_require_hash(
                transcript_hash,
                "canonical_transcript_sha256",
            ),
            timing_source_sha256=_require_hash(timing_hash, "timing_source_sha256"),
            timing_source_type=str(
                _pick(value, "timing_source_type", "source_type")
                or "CANONICAL_TIMED_TRANSCRIPT"
            ),
            source_audio_sha256=audio_hash,
            source_video_sha256=video_hash,
            text_provenance=normalized_provenance,
            duration_seconds=None if duration is None else _number(duration, "duration_seconds"),
            schema_version=str(value.get("schema_version") or "SIRAJ_CANONICAL_TIMED_TRANSCRIPT_V1"),
        )

    @classmethod
    def from_segments(
        cls,
        segments: Sequence[Mapping[str, Any]],
        *,
        episode_id: str,
        canonical_transcript_sha256: str,
        timing_source_sha256: str,
        timing_source_type: str = "CANONICAL_TIMED_TRANSCRIPT",
        source_audio_sha256: str | None = None,
        source_video_sha256: str | None = None,
        text_provenance: str = "CANONICAL_TIMED_TRANSCRIPT",
        duration_seconds: float | None = None,
    ) -> "CaptionTranscript":
        return cls(
            episode_id=str(episode_id),
            segments=tuple(_mapping(item, "segments") for item in segments),
            canonical_transcript_sha256=_require_hash(
                canonical_transcript_sha256,
                "canonical_transcript_sha256",
            ),
            timing_source_sha256=_require_hash(timing_source_sha256, "timing_source_sha256"),
            timing_source_type=str(timing_source_type),
            source_audio_sha256=(
                None
                if source_audio_sha256 is None
                else _require_hash(source_audio_sha256, "source_audio_sha256")
            ),
            source_video_sha256=(
                None
                if source_video_sha256 is None
                else _require_hash(source_video_sha256, "source_video_sha256")
            ),
            text_provenance=str(text_provenance),
            duration_seconds=(
                None if duration_seconds is None else _number(duration_seconds, "duration_seconds")
            ),
        )


@dataclass(frozen=True, slots=True)
class EditRange:
    """One explicit source-to-Short mapping in local timebase order."""

    range_id: str
    source_start: float
    source_end: float
    short_start: float
    short_end: float | None = None

    @property
    def destination_end(self) -> float:
        if self.short_end is not None:
            return self.short_end
        return self.short_start + (self.source_end - self.source_start)

    @property
    def source_duration(self) -> float:
        return self.source_end - self.source_start

    @property
    def destination_duration(self) -> float:
        return self.destination_end - self.short_start

    def to_dict(self) -> dict[str, Any]:
        return {
            "range_id": self.range_id,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "short_start": self.short_start,
            "short_end": self.short_end,
        }


@dataclass(frozen=True, slots=True)
class ShortEditPlan:
    """Explicit extractive edit map; ordering is Short output ordering."""

    short_id: str
    source_episode_id: str
    ranges: tuple[EditRange, ...]
    edit_plan_sha256: str
    short_duration_seconds: float
    source_video_sha256: str | None = None
    source_audio_sha256: str | None = None
    operation: str = "EXTRACTIVE_TIMEBASE_MAP"

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ShortEditPlan":
        raw_ranges = _pick(
            value,
            "ranges",
            "segments",
            "cuts",
            "edit_ranges",
            "selected_source_ranges",
        )
        raw_list = _as_list(raw_ranges, "edit_plan.ranges")
        ranges: list[EditRange] = []
        for index, raw in enumerate(raw_list, start=1):
            item = _mapping(raw, f"edit_plan.ranges[{index}]")
            source_start = _pick(item, "source_start", "start", "longform_start")
            source_end = _pick(item, "source_end", "end", "longform_end")
            short_start = _pick(item, "short_start", "destination_start", "output_start")
            short_end = _pick(item, "short_end", "destination_end", "output_end")
            if short_start is None:
                raise CaptionBlockedError("EDIT_PLAN_INVALID", f"RANGE_SHORT_START_REQUIRED:{index}")
            range_item = EditRange(
                range_id=str(_pick(item, "range_id", "id") or f"RANGE-{index:04d}"),
                source_start=_number(source_start, f"range[{index}].source_start"),
                source_end=_number(source_end, f"range[{index}].source_end"),
                short_start=_number(short_start, f"range[{index}].short_start"),
                short_end=(
                    None
                    if short_end is None
                    else _number(short_end, f"range[{index}].short_end")
                ),
            )
            ranges.append(range_item)
        short_duration = _pick(value, "short_duration_seconds", "duration_seconds", "output_duration")
        if short_duration is None:
            short_duration = max(item.destination_end for item in ranges) if ranges else None
        source_video = _pick(value, "source_video_sha256", "source_episode_sha256")
        source_audio = _pick(value, "source_audio_sha256", "final_narration_sha256")
        if source_video is not None:
            source_video = _require_hash(source_video, "source_video_sha256")
        if source_audio is not None:
            source_audio = _require_hash(source_audio, "source_audio_sha256")
        normalized = {
            "short_id": str(_pick(value, "short_id", "id") or ""),
            "source_episode_id": str(_pick(value, "source_episode_id", "episode_id") or ""),
            "ranges": [item.to_dict() for item in ranges],
            "short_duration_seconds": _number(short_duration, "short_duration_seconds"),
            "source_video_sha256": source_video,
            "source_audio_sha256": source_audio,
            "operation": str(value.get("operation") or "EXTRACTIVE_TIMEBASE_MAP"),
        }
        declared_hash = value.get("edit_plan_sha256")
        computed_hash = _sha256(normalized)
        if declared_hash is not None and _require_hash(declared_hash, "edit_plan_sha256") != computed_hash:
            raise CaptionBlockedError("EDIT_PLAN_HASH_MISMATCH", "DECLARED_EDIT_PLAN_HASH")
        return cls(
            short_id=normalized["short_id"],
            source_episode_id=normalized["source_episode_id"],
            ranges=tuple(ranges),
            edit_plan_sha256=computed_hash,
            short_duration_seconds=normalized["short_duration_seconds"],
            source_video_sha256=source_video,
            source_audio_sha256=source_audio,
            operation=normalized["operation"],
        )

    @classmethod
    def from_ranges(
        cls,
        ranges: Sequence[Mapping[str, Any] | EditRange],
        *,
        short_id: str,
        source_episode_id: str,
        short_duration_seconds: float | None = None,
        source_video_sha256: str | None = None,
        source_audio_sha256: str | None = None,
    ) -> "ShortEditPlan":
        payload: dict[str, Any] = {
            "short_id": short_id,
            "source_episode_id": source_episode_id,
            "ranges": [
                item.to_dict() if isinstance(item, EditRange) else dict(item)
                for item in ranges
            ],
        }
        if short_duration_seconds is not None:
            payload["short_duration_seconds"] = short_duration_seconds
        if source_video_sha256 is not None:
            payload["source_video_sha256"] = source_video_sha256
        if source_audio_sha256 is not None:
            payload["source_audio_sha256"] = source_audio_sha256
        return cls.from_mapping(payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "short_id": self.short_id,
            "source_episode_id": self.source_episode_id,
            "ranges": [item.to_dict() for item in self.ranges],
            "edit_plan_sha256": self.edit_plan_sha256,
            "short_duration_seconds": self.short_duration_seconds,
            "source_video_sha256": self.source_video_sha256,
            "source_audio_sha256": self.source_audio_sha256,
            "operation": self.operation,
        }


EditPlan = ShortEditPlan


@dataclass(frozen=True, slots=True)
class CaptionCue:
    cue_id: str
    source_segment_id: str
    source_start_seconds: float
    source_end_seconds: float
    start_seconds: float
    end_seconds: float
    text: str
    timing_authority: str
    text_provenance: str
    canonical_transcript_sha256: str
    timing_source_sha256: str
    source_range_id: str | None = None
    direction: str = "RTL"
    line_count: int = 1
    display_lines: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "cue_id": self.cue_id,
            "source_segment_id": self.source_segment_id,
            "source_start_seconds": self.source_start_seconds,
            "source_end_seconds": self.source_end_seconds,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "text": self.text,
            "timing_authority": self.timing_authority,
            "text_provenance": self.text_provenance,
            "canonical_transcript_sha256": self.canonical_transcript_sha256,
            "timing_source_sha256": self.timing_source_sha256,
            "source_range_id": self.source_range_id,
            "direction": self.direction,
            "line_count": self.line_count,
            "display_lines": list(self.display_lines),
        }


@dataclass(frozen=True, slots=True)
class CaptionPlan:
    schema_version: str
    engine_id: str
    engine_version: str
    scope: str
    caption_mode: str
    captions_enabled: bool
    default_enabled: bool
    episode_id: str
    short_id: str
    source_video_sha256: str | None
    source_audio_sha256: str | None
    canonical_transcript_sha256: str
    timing_source_sha256: str
    edit_plan_sha256: str
    timing_authority: str
    timing_authorities_used: tuple[str, ...]
    timebase: str
    short_duration_seconds: float
    cues: tuple[CaptionCue, ...]
    safe_area_profile: Mapping[str, Any]
    placement: Mapping[str, Any]
    style: Mapping[str, Any]
    visual_policy_status: str
    text_authority: str
    on_screen_subtitles: bool = False
    status: str = "READY"
    plan_sha256: str = field(default="")

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "engine_id": self.engine_id,
            "engine_version": self.engine_version,
            "scope": self.scope,
            "caption_mode": self.caption_mode,
            "captions_enabled": self.captions_enabled,
            "default_enabled": self.default_enabled,
            "episode_id": self.episode_id,
            "short_id": self.short_id,
            "source_video_sha256": self.source_video_sha256,
            "source_audio_sha256": self.source_audio_sha256,
            "canonical_transcript_sha256": self.canonical_transcript_sha256,
            "timing_source_sha256": self.timing_source_sha256,
            "edit_plan_sha256": self.edit_plan_sha256,
            "timing_authority": self.timing_authority,
            "timing_authorities_used": list(self.timing_authorities_used),
            "timebase": self.timebase,
            "short_duration_seconds": self.short_duration_seconds,
            "cues": [item.to_dict() for item in self.cues],
            "safe_area_profile": dict(self.safe_area_profile),
            "placement": dict(self.placement),
            "style": dict(self.style),
            "visual_policy_status": self.visual_policy_status,
            "text_authority": self.text_authority,
            "on_screen_subtitles": self.on_screen_subtitles,
            "status": self.status,
        }
        if include_hash:
            payload["plan_sha256"] = self.plan_sha256
        return payload

    @property
    def render_contract(self) -> dict[str, Any]:
        return build_render_contract(self)


@dataclass(frozen=True, slots=True)
class CaptionQAResult:
    status: str
    plan_sha256: str
    checks: Mapping[str, Any]
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "plan_sha256": self.plan_sha256,
            "checks": dict(self.checks),
            "failures": list(self.failures),
        }


SAFE_AREA_PROFILE_V1: dict[str, Any] = {
    "profile_id": "SHORTS_CAPTION_SAFE_AREA_PROFILE_V1",
    "version": "1.0.0",
    "frame": {
        "width": TARGET_WIDTH,
        "height": TARGET_HEIGHT,
        "aspect_ratio": TARGET_ASPECT_RATIO,
    },
    "normalized_coordinates": True,
    "forbidden_regions": {
        "top_channel_title": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.14},
        "right_shorts_controls": {"x": 0.86, "y": 0.10, "width": 0.14, "height": 0.72},
        "bottom_navigation": {"x": 0.0, "y": 0.86, "width": 1.0, "height": 0.14},
    },
    "candidate_regions": (
        {"region_id": "LOWER_CENTER", "x": 0.08, "y": 0.64, "width": 0.76, "height": 0.16},
        {"region_id": "MIDDLE_CENTER", "x": 0.08, "y": 0.42, "width": 0.76, "height": 0.16},
        {"region_id": "UPPER_CENTER", "x": 0.08, "y": 0.24, "width": 0.76, "height": 0.16},
    ),
}

CAPTION_STYLE_V1: dict[str, Any] = {
    "style_id": "SHORTS_RESTRAINED_CAPTION_STYLE_V1",
    "font_policy": "SYSTEM_OR_PROJECT_APPROVED_ARABIC_CAPABLE_FONT",
    "font_binary_bundled": False,
    "fill": "HIGH_CONTRAST_LIGHT",
    "outline": "SUBTLE_DARK_OUTLINE",
    "shadow": "SUBTLE",
    "background": "SIMPLE_SEMI_TRANSPARENT_BACKPLATE_IF_NEEDED",
    "animation": "NONE",
    "karaoke": False,
    "emoji_animation": False,
    "max_lines": MAX_LINES,
}


def safe_area_profile_v1() -> dict[str, Any]:
    """Return a copy so callers cannot mutate the canonical profile."""

    return json.loads(json.dumps(SAFE_AREA_PROFILE_V1, ensure_ascii=False))


def _direction_for_text(text: str) -> str:
    has_arabic = any("ARABIC" in unicodedata.name(char, "") for char in text)
    has_latin = any("LATIN" in unicodedata.name(char, "") for char in text)
    has_number = any(char.isdigit() for char in text)
    if has_arabic and (has_latin or has_number):
        return "RTL_MIXED"
    if has_arabic:
        return "RTL"
    if has_latin or has_number:
        return "LTR"
    return "UNKNOWN"


def _wrap_text(text: str) -> tuple[str, ...]:
    """Wrap only at source whitespace; the stored cue text stays untouched."""

    explicit_lines = text.replace("\r\n", "\n").split("\n")
    output: list[str] = []
    for explicit_line in explicit_lines:
        tokens = explicit_line.split()
        if not tokens:
            continue
        current: list[str] = []
        current_length = 0
        for token in tokens:
            if len(token) > MAX_CHARS_PER_LINE:
                raise CaptionBlockedError("CAPTION_TEXT_TOO_LONG", "TOKEN_EXCEEDS_LINE_WIDTH")
            projected = len(token) if not current else current_length + 1 + len(token)
            if current and projected > MAX_CHARS_PER_LINE:
                output.append(" ".join(current))
                current = [token]
                current_length = len(token)
            else:
                current.append(token)
                current_length = projected
        if current:
            output.append(" ".join(current))
    if not output:
        raise CaptionBlockedError("CAPTION_TEXT_INVALID", "EMPTY_DISPLAY_LINES")
    if len(output) > MAX_LINES:
        raise CaptionBlockedError("CAPTION_MAX_LINES_EXCEEDED", str(len(output)))
    return tuple(output)


def _text_tokens(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"\S+", text, flags=re.UNICODE))


def _derived_text(parent: str, child: str) -> bool:
    if child == parent or child.strip() in parent:
        return True
    parent_tokens = _text_tokens(parent)
    child_tokens = _text_tokens(child)
    if not child_tokens or len(child_tokens) > len(parent_tokens):
        return False
    for start in range(len(parent_tokens) - len(child_tokens) + 1):
        if parent_tokens[start : start + len(child_tokens)] == child_tokens:
            return True
    return False


def _segment_fields(raw: Any, index: int) -> dict[str, Any]:
    item = _mapping(raw, f"segments[{index}]")
    start = _pick(item, "start_seconds", "start_time", "start")
    end = _pick(item, "end_seconds", "end_time", "end")
    text = _pick(item, "text", "canonical_text_ar", "text_ar", "narration", "narration_ar")
    segment_id = _pick(item, "segment_id", "id", "block_id") or f"SEG-{index:04d}"
    result = dict(item)
    result.update(
        {
            "segment_id": str(segment_id),
            "start_seconds": _number(start, f"segment[{index}].start"),
            "end_seconds": _number(end, f"segment[{index}].end"),
            "text": _non_empty_text(text, f"segment[{index}].text"),
        }
    )
    return result


def _boundaries_for_segment(item: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    options = (
        (TIMING_AUTHORITY_WORD, ("word_boundaries", "word_boundary", "words", "word_timing", "word_timings")),
        (TIMING_AUTHORITY_PHRASE, ("phrase_boundaries", "phrases", "clause_boundaries", "clauses", "phrase_timing")),
        (TIMING_AUTHORITY_SENTENCE, ("sentence_boundaries", "sentences")),
    )
    for authority, keys in options:
        raw = _pick(item, *keys)
        if raw is None:
            continue
        children = _as_list(raw, f"{item['segment_id']}.{authority}")
        normalized: list[dict[str, Any]] = []
        for index, child in enumerate(children, start=1):
            child_map = _mapping(child, f"{item['segment_id']}.{authority}[{index}]")
            start = _pick(child_map, "start_seconds", "start_time", "start")
            end = _pick(child_map, "end_seconds", "end_time", "end")
            child_text = _pick(child_map, "text", "word", "phrase", "clause", "value")
            normalized.append(
                {
                    "segment_id": str(
                        _pick(child_map, "segment_id", "id")
                        or f"{item['segment_id']}-{authority}-{index:04d}"
                    ),
                    "start_seconds": _number(start, "boundary.start"),
                    "end_seconds": _number(end, "boundary.end"),
                    "text": _non_empty_text(child_text, "boundary.text"),
                    "parent_segment_id": str(item["segment_id"]),
                    "parent_text": str(item["text"]),
                }
            )
        if normalized:
            return authority, normalized
    return TIMING_AUTHORITY_SENTENCE, [
        {
            "segment_id": str(item["segment_id"]),
            "start_seconds": float(item["start_seconds"]),
            "end_seconds": float(item["end_seconds"]),
            "text": str(item["text"]),
            "parent_segment_id": str(item["segment_id"]),
            "parent_text": str(item["text"]),
        }
    ]


def _validate_units(units: Sequence[Mapping[str, Any]]) -> None:
    previous = -1.0
    seen: set[str] = set()
    for unit in units:
        unit_id = str(unit["segment_id"])
        start = _number(unit["start_seconds"], f"{unit_id}.start")
        end = _number(unit["end_seconds"], f"{unit_id}.end")
        text = _non_empty_text(unit["text"], f"{unit_id}.text")
        if start < -EPSILON or end <= start + EPSILON:
            raise CaptionBlockedError("CAPTION_TIMING_INVALID", f"{unit_id}:RANGE")
        if unit_id in seen:
            raise CaptionBlockedError("CAPTION_TIMING_INVALID", f"{unit_id}:DUPLICATE")
        if start < previous - EPSILON:
            raise CaptionBlockedError("CAPTION_TIMING_INVALID", f"{unit_id}:OVERLAP_OR_UNORDERED")
        if not _derived_text(str(unit.get("parent_text", text)), text):
            raise CaptionBlockedError("CAPTION_TEXT_NOT_NARRATION", unit_id)
        seen.add(unit_id)
        previous = end


def _materialize_units(transcript: CaptionTranscript) -> tuple[dict[str, Any], ...]:
    provenance = str(transcript.text_provenance).strip().upper()
    if any(token in provenance for token in _PROVENANCE_FORBIDDEN) or provenance not in _PROVENANCE_ALLOWED:
        raise CaptionBlockedError("CAPTION_TEXT_AUTHORITY_FORBIDDEN", provenance or "UNKNOWN")
    units: list[dict[str, Any]] = []
    for index, raw in enumerate(transcript.segments, start=1):
        item = _segment_fields(raw, index)
        authority, boundaries = _boundaries_for_segment(item)
        for boundary in boundaries:
            if not _derived_text(item["text"], boundary["text"]):
                raise CaptionBlockedError("CAPTION_TEXT_NOT_NARRATION", str(boundary["segment_id"]))
            boundary["timing_authority"] = authority
            boundary["text_provenance"] = TEXT_AUTHORITY_NARRATION_ONLY
            units.append(boundary)
    if not units:
        raise CaptionBlockedError("CAPTION_TIMING_INSUFFICIENT", "NO_TIMED_NARRATION_UNITS")
    _validate_units(units)
    return tuple(units)


def _source_text_slice(parent: str, first: str, last: str) -> str:
    start = parent.find(first)
    if start < 0:
        return f"{first} {last}" if first != last else first
    end_start = parent.find(last, start)
    if end_start < 0:
        end_start = start + len(first)
    return parent[start : end_start + len(last)]


def _group_word_units(units: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group trusted word timings into <=2-line cues without losing words.

    AUDIENCE_GROWTH_WORD_SEGMENTATION_V1
    A line-count overflow is a cue-segmentation problem, not a reason to reject
    an otherwise good Short. Only trusted WORD_BOUNDARY units are regrouped;
    all other caption failures remain fail-closed.
    """

    grouped: list[dict[str, Any]] = []
    current: list[Mapping[str, Any]] = []

    def fits(candidate: Sequence[Mapping[str, Any]]) -> bool:
        if len(candidate) > MAX_WORDS_PER_CUE:
            return False
        parent = str(candidate[-1].get("parent_text", candidate[-1]["text"]))
        candidate_text = _source_text_slice(
            parent,
            str(candidate[0]["text"]),
            str(candidate[-1]["text"]),
        )
        try:
            _wrap_text(candidate_text)
            return True
        except CaptionBlockedError as exc:
            if exc.code == "CAPTION_MAX_LINES_EXCEEDED":
                return False
            raise

    for unit in units:
        if current and unit.get("parent_segment_id") != current[-1].get("parent_segment_id"):
            grouped.append(_word_group(current))
            current = []

        candidate = current + [unit]
        terminal = bool(re.search(r"[.!؟?؛:،]$", str(unit["text"]).strip()))

        if current and not fits(candidate):
            grouped.append(_word_group(current))
            current = [unit]
        else:
            current = candidate

        if terminal:
            grouped.append(_word_group(current))
            current = []

    if current:
        grouped.append(_word_group(current))

    # Fail closed if a single trusted word itself cannot fit the constitutional
    # two-line display contract. This should not happen for ordinary Arabic.
    for item in grouped:
        _wrap_text(str(item["text"]))
    return grouped

def _word_group(units: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    parent = str(units[0].get("parent_text", units[0]["text"]))
    text = _source_text_slice(parent, str(units[0]["text"]), str(units[-1]["text"]))
    return {
        "segment_id": f"{units[0]['parent_segment_id']}:{units[0]['segment_id']}:{units[-1]['segment_id']}",
        "start_seconds": float(units[0]["start_seconds"]),
        "end_seconds": float(units[-1]["end_seconds"]),
        "text": text,
        "parent_segment_id": str(units[0]["parent_segment_id"]),
        "parent_text": parent,
        "timing_authority": TIMING_AUTHORITY_WORD,
        "text_provenance": TEXT_AUTHORITY_NARRATION_ONLY,
    }


def _coerce_transcript(
    value: CaptionTranscript | Mapping[str, Any] | Sequence[Mapping[str, Any]],
    *,
    canonical_transcript_sha256: str | None,
    timing_source_sha256: str | None,
) -> CaptionTranscript:
    if isinstance(value, CaptionTranscript):
        if canonical_transcript_sha256 is not None and value.canonical_transcript_sha256 != _require_hash(canonical_transcript_sha256, "canonical_transcript_sha256"):
            raise CaptionBlockedError("CAPTION_HASH_MISMATCH", "CANONICAL_TRANSCRIPT")
        if timing_source_sha256 is not None and value.timing_source_sha256 != _require_hash(timing_source_sha256, "timing_source_sha256"):
            raise CaptionBlockedError("CAPTION_HASH_MISMATCH", "TIMING_SOURCE")
        return value
    if isinstance(value, Mapping):
        return CaptionTranscript.from_mapping(
            value,
            canonical_transcript_sha256=canonical_transcript_sha256,
            timing_source_sha256=timing_source_sha256,
        )
    if canonical_transcript_sha256 is None or timing_source_sha256 is None:
        raise CaptionBlockedError("CAPTION_HASH_BINDING_REQUIRED", "TRANSCRIPT_SEQUENCE")
    return CaptionTranscript.from_segments(
        value,
        episode_id="",
        canonical_transcript_sha256=canonical_transcript_sha256,
        timing_source_sha256=timing_source_sha256,
    )


def _coerce_edit_plan(value: ShortEditPlan | Mapping[str, Any]) -> ShortEditPlan:
    if isinstance(value, ShortEditPlan):
        return value
    return ShortEditPlan.from_mapping(_mapping(value, "edit_plan"))


def _validate_edit_ranges(edit_plan: ShortEditPlan) -> None:
    if not edit_plan.ranges:
        raise CaptionBlockedError("EDIT_PLAN_INVALID", "NO_RANGES")
    previous_destination_end = -1.0
    for item in edit_plan.ranges:
        if item.source_start < -EPSILON or item.source_end <= item.source_start + EPSILON:
            raise CaptionBlockedError("EDIT_PLAN_INVALID", f"{item.range_id}:SOURCE_RANGE")
        if item.short_start < -EPSILON or item.destination_end <= item.short_start + EPSILON:
            raise CaptionBlockedError("EDIT_PLAN_INVALID", f"{item.range_id}:DESTINATION_RANGE")
        if item.short_start < previous_destination_end - EPSILON:
            raise CaptionBlockedError("EDIT_PLAN_INVALID", f"{item.range_id}:DESTINATION_OVERLAP")
        previous_destination_end = item.destination_end
    if edit_plan.short_duration_seconds < previous_destination_end - EPSILON:
        raise CaptionBlockedError("EDIT_PLAN_INVALID", "DURATION_TOO_SHORT")


def _coerce_source_cues(
    units: Sequence[Mapping[str, Any]],
    transcript: CaptionTranscript,
) -> tuple[CaptionCue, ...]:
    word_units = [item for item in units if item["timing_authority"] == TIMING_AUTHORITY_WORD]
    if word_units and len(word_units) == len(units):
        materialized = _group_word_units(word_units)
    else:
        materialized = list(units)
    cues: list[CaptionCue] = []
    for index, unit in enumerate(materialized, start=1):
        text = _non_empty_text(unit["text"], f"cue[{index}].text")
        if len(text) > COARSE_MAX_CHARACTERS and unit["timing_authority"] != TIMING_AUTHORITY_WORD:
            raise CaptionBlockedError("CAPTION_TIMING_INSUFFICIENT", f"{unit['segment_id']}:TEXT_TOO_COARSE")
        if (
            float(unit["end_seconds"]) - float(unit["start_seconds"]) > COARSE_MAX_DURATION_SECONDS
            and unit["timing_authority"] != TIMING_AUTHORITY_WORD
        ):
            raise CaptionBlockedError("CAPTION_TIMING_INSUFFICIENT", f"{unit['segment_id']}:DURATION_TOO_COARSE")
        lines = _wrap_text(text)
        direction = _direction_for_text(text)
        if direction == "UNKNOWN":
            raise CaptionBlockedError("CAPTION_DIRECTION_UNRESOLVED", str(unit["segment_id"]))
        cues.append(
            CaptionCue(
                cue_id=f"CUE-{index:04d}",
                source_segment_id=str(unit["segment_id"]),
                source_start_seconds=float(unit["start_seconds"]),
                source_end_seconds=float(unit["end_seconds"]),
                start_seconds=float(unit["start_seconds"]),
                end_seconds=float(unit["end_seconds"]),
                text=text,
                timing_authority=str(unit["timing_authority"]),
                text_provenance=TEXT_AUTHORITY_NARRATION_ONLY,
                canonical_transcript_sha256=transcript.canonical_transcript_sha256,
                timing_source_sha256=transcript.timing_source_sha256,
                direction=direction,
                line_count=len(lines),
                display_lines=lines,
            )
        )
    return tuple(cues)


def _rect(value: Mapping[str, Any], field_name: str) -> dict[str, float]:
    source = value.get("geometry") if isinstance(value.get("geometry"), Mapping) else value
    result: dict[str, float] = {}
    for key in ("x", "y", "width", "height"):
        if key not in source:
            raise CaptionBlockedError("CAPTION_GEOMETRY_INVALID", f"{field_name}:{key}")
        result[key] = _number(source[key], f"{field_name}.{key}")
        if key in {"x", "y"} and not 0.0 <= result[key] <= 1.0:
            raise CaptionBlockedError("CAPTION_GEOMETRY_INVALID", field_name)
        if key in {"width", "height"} and not 0.0 < result[key] <= 1.0:
            raise CaptionBlockedError("CAPTION_GEOMETRY_INVALID", field_name)
    if result["x"] + result["width"] > 1.0 + EPSILON or result["y"] + result["height"] > 1.0 + EPSILON:
        raise CaptionBlockedError("CAPTION_GEOMETRY_INVALID", f"{field_name}:OUT_OF_FRAME")
    return result


def _overlap_area(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    x = max(0.0, min(left["x"] + left["width"], right["x"] + right["width"]) - max(left["x"], right["x"]))
    y = max(0.0, min(left["y"] + left["height"], right["y"] + right["height"]) - max(left["y"], right["y"]))
    return x * y


def choose_caption_placement(
    subject_regions: Sequence[Mapping[str, Any]] | None = None,
    *,
    profile: Mapping[str, Any] | None = None,
    visual_policy_status: str = "PASS",
) -> dict[str, Any]:
    """Choose a safe relative region or fail instead of covering the visual."""

    if str(visual_policy_status).upper() not in {"PASS", "READY", "APPROVED"}:
        raise CaptionBlockedError(
            "CAPTION_CANNOT_SALVAGE_VISUAL_FAIL",
            str(visual_policy_status),
        )
    selected_profile = profile or safe_area_profile_v1()
    candidates = _as_list(selected_profile.get("candidate_regions"), "safe_area.candidate_regions")
    forbidden_regions = [
        _rect(_mapping(raw, "safe_area.forbidden_region"), "safe_area.forbidden_region")
        for raw in dict(selected_profile.get("forbidden_regions") or {}).values()
    ]
    occupied: list[tuple[str, dict[str, float]]] = []
    for index, raw in enumerate(subject_regions or (), start=1):
        item = _mapping(raw, f"subject_regions[{index}]")
        geometry = _rect(item, f"subject_regions[{index}]")
        role = str(item.get("role") or item.get("kind") or "CRITICAL_SUBJECT").upper()
        if role not in {"BACKGROUND", "NON_CRITICAL_BACKGROUND"}:
            occupied.append((str(item.get("id") or index), geometry))
    rejected: list[dict[str, Any]] = []
    for raw in candidates:
        candidate = _mapping(raw, "safe_area.candidate_region")
        geometry = _rect(candidate, "safe_area.candidate_region")
        collisions = [identifier for identifier, region in occupied if _overlap_area(geometry, region) > EPSILON]
        if any(_overlap_area(geometry, forbidden) > EPSILON for forbidden in forbidden_regions):
            collisions.append("PROFILE_FORBIDDEN_REGION")
        if collisions:
            rejected.append({"region_id": candidate.get("region_id"), "collisions": collisions})
            continue
        return {
            "status": "PASS",
            "region_id": str(candidate.get("region_id") or "UNNAMED"),
            "geometry": geometry,
            "alternative_attempted": bool(rejected),
            "rejected_candidates": rejected,
        }
    raise CaptionBlockedError(
        "CAPTION_PLACEMENT_BLOCKED",
        json.dumps(rejected, ensure_ascii=False, sort_keys=True),
    )


def remap_cues_to_short_timebase(
    cues: Sequence[CaptionCue | Mapping[str, Any]],
    edit_plan: ShortEditPlan | Mapping[str, Any],
) -> tuple[CaptionCue, ...]:
    """Map trusted source cues through explicit single/multi-cut ordering."""

    plan = _coerce_edit_plan(edit_plan)
    _validate_edit_ranges(plan)
    source_cues: list[CaptionCue] = []
    for index, raw in enumerate(cues, start=1):
        if isinstance(raw, CaptionCue):
            source_cues.append(raw)
            continue
        item = _mapping(raw, f"cues[{index}]")
        text = _non_empty_text(item.get("text"), f"cues[{index}].text")
        direction = str(item.get("direction") or _direction_for_text(text))
        lines = tuple(item.get("display_lines") or _wrap_text(text))
        source_cues.append(
            CaptionCue(
                cue_id=str(item.get("cue_id") or f"CUE-{index:04d}"),
                source_segment_id=str(item.get("source_segment_id") or item.get("segment_id") or index),
                source_start_seconds=_number(item.get("source_start_seconds", item.get("start_seconds", item.get("start"))), "cue.source_start"),
                source_end_seconds=_number(item.get("source_end_seconds", item.get("end_seconds", item.get("end"))), "cue.source_end"),
                start_seconds=_number(item.get("start_seconds", item.get("start")), "cue.start"),
                end_seconds=_number(item.get("end_seconds", item.get("end")), "cue.end"),
                text=text,
                timing_authority=str(item.get("timing_authority") or TIMING_AUTHORITY_SENTENCE),
                text_provenance=str(item.get("text_provenance") or TEXT_AUTHORITY_NARRATION_ONLY),
                canonical_transcript_sha256=str(item.get("canonical_transcript_sha256") or ""),
                timing_source_sha256=str(item.get("timing_source_sha256") or ""),
                direction=direction,
                line_count=len(lines),
                display_lines=lines,
            )
        )
    result: list[CaptionCue] = []
    for cue in source_cues:
        if cue.source_end_seconds <= cue.source_start_seconds + EPSILON:
            raise CaptionBlockedError("CAPTION_TIMING_INVALID", f"{cue.cue_id}:SOURCE_RANGE")
        matched = False
        for edit_range in plan.ranges:
            fully_inside = (
                cue.source_start_seconds >= edit_range.source_start - EPSILON
                and cue.source_end_seconds <= edit_range.source_end + EPSILON
            )
            intersects = (
                cue.source_end_seconds > edit_range.source_start + EPSILON
                and cue.source_start_seconds < edit_range.source_end - EPSILON
            )
            if not intersects:
                continue
            if not fully_inside:
                raise CaptionBlockedError(
                    "CUT_THROUGH_CAPTION",
                    f"{cue.cue_id}:{edit_range.range_id}:LOWER_LEVEL_OR_ADJUST_CUT_REQUIRED",
                )
            scale = edit_range.destination_duration / edit_range.source_duration
            mapped_start = edit_range.short_start + (cue.source_start_seconds - edit_range.source_start) * scale
            mapped_end = edit_range.short_start + (cue.source_end_seconds - edit_range.source_start) * scale
            result.append(
                CaptionCue(
                    cue_id=f"{cue.cue_id}@{edit_range.range_id}",
                    source_segment_id=cue.source_segment_id,
                    source_start_seconds=cue.source_start_seconds,
                    source_end_seconds=cue.source_end_seconds,
                    start_seconds=mapped_start,
                    end_seconds=mapped_end,
                    text=cue.text,
                    timing_authority=cue.timing_authority,
                    text_provenance=cue.text_provenance,
                    canonical_transcript_sha256=cue.canonical_transcript_sha256,
                    timing_source_sha256=cue.timing_source_sha256,
                    source_range_id=edit_range.range_id,
                    direction=cue.direction,
                    line_count=cue.line_count,
                    display_lines=cue.display_lines,
                )
            )
            matched = True
        if not matched:
            raise CaptionBlockedError("CAPTION_SOURCE_CUE_NOT_INCLUDED", cue.cue_id)
    result.sort(key=lambda item: (item.start_seconds, item.end_seconds, item.cue_id))
    previous_end = -1.0
    for cue in result:
        if cue.start_seconds < previous_end - EPSILON:
            raise CaptionBlockedError("CAPTION_TIMING_INVALID", f"{cue.cue_id}:SHORT_OVERLAP")
        previous_end = cue.end_seconds
    return tuple(result)


def _plan_hash_payload(plan: CaptionPlan) -> dict[str, Any]:
    return plan.to_dict(include_hash=False)


def build_render_contract(plan: CaptionPlan) -> dict[str, Any]:
    """Return renderer-neutral, Shorts-only parameters; never invoke a renderer."""

    return {
        "contract_id": "SIRAJ_SHORTS_BURNED_CAPTION_RENDER_CONTRACT_V1",
        "scope": SHORTS_SCOPE,
        "caption_mode": CAPTION_MODE,
        "burned_captions": bool(plan.captions_enabled),
        "on_screen_subtitles": False,
        "source_text_authority": TEXT_AUTHORITY_NARRATION_ONLY,
        "timebase": SHORT_LOCAL_TIMEBASE,
        "frame": {"width": TARGET_WIDTH, "height": TARGET_HEIGHT, "aspect_ratio": TARGET_ASPECT_RATIO},
        "safe_area_profile": dict(plan.safe_area_profile),
        "placement": dict(plan.placement),
        "style": dict(plan.style),
        "rtl": True,
        "mixed_direction_strategy": "BIDI_AWARE_RENDERER_WITH_RTL_BASE_DIRECTION",
        "max_lines": MAX_LINES,
        "karaoke": False,
        "font_policy": CAPTION_STYLE_V1["font_policy"],
        "cues": [item.to_dict() for item in plan.cues],
        "source_hashes": {
            "canonical_transcript_sha256": plan.canonical_transcript_sha256,
            "timing_source_sha256": plan.timing_source_sha256,
            "edit_plan_sha256": plan.edit_plan_sha256,
        },
        "provider_calls": 0,
        "network_calls": 0,
        "paid_calls": 0,
        "render_invoked": False,
    }


def qa_caption_plan(
    plan: CaptionPlan,
    *,
    expected_canonical_transcript_sha256: str | None = None,
    expected_timing_source_sha256: str | None = None,
    expected_edit_plan_sha256: str | None = None,
    expected_source_audio_sha256: str | None = None,
    expected_source_video_sha256: str | None = None,
    visual_policy_status: str | None = None,
) -> CaptionQAResult:
    """Run deterministic technical QA; a failed visual policy is never rescued."""

    failures: list[str] = []
    checks: dict[str, Any] = {}

    def check(name: str, passed: bool, code: str) -> None:
        checks[name] = "PASS" if passed else "FAIL"
        if not passed:
            failures.append(code)

    check("scope", plan.scope == SHORTS_SCOPE, "CAPTION_SCOPE_FORBIDDEN")
    check("mode", plan.caption_mode == CAPTION_MODE, "CAPTION_MODE_INVALID")
    check("timebase", plan.timebase == SHORT_LOCAL_TIMEBASE, "CAPTION_TIMEBASE_INVALID")
    check("frame", (TARGET_WIDTH, TARGET_HEIGHT) == (1080, 1920), "CAPTION_FRAME_INVALID")
    check("hash_format", all(_is_hash(item) for item in (plan.canonical_transcript_sha256, plan.timing_source_sha256, plan.edit_plan_sha256)), "CAPTION_HASH_BINDING_REQUIRED")
    check("plan_freshness", plan.plan_sha256 == _sha256(_plan_hash_payload(plan)), "STALE_CAPTION_PLAN_HASH")
    if expected_canonical_transcript_sha256 is not None:
        check("transcript_freshness", plan.canonical_transcript_sha256 == _require_hash(expected_canonical_transcript_sha256, "expected_canonical_transcript_sha256"), "STALE_TRANSCRIPT_HASH")
    if expected_timing_source_sha256 is not None:
        check("timing_freshness", plan.timing_source_sha256 == _require_hash(expected_timing_source_sha256, "expected_timing_source_sha256"), "STALE_TIMING_SOURCE_HASH")
    if expected_edit_plan_sha256 is not None:
        check("edit_plan_freshness", plan.edit_plan_sha256 == _require_hash(expected_edit_plan_sha256, "expected_edit_plan_sha256"), "STALE_EDIT_PLAN_HASH")
    if expected_source_audio_sha256 is not None:
        check("audio_freshness", plan.source_audio_sha256 == _require_hash(expected_source_audio_sha256, "expected_source_audio_sha256"), "STALE_AUDIO_HASH")
    if expected_source_video_sha256 is not None:
        check("video_freshness", plan.source_video_sha256 == _require_hash(expected_source_video_sha256, "expected_source_video_sha256"), "STALE_VIDEO_HASH")
    if visual_policy_status is not None:
        check("visual_policy", str(visual_policy_status).upper() in {"PASS", "READY", "APPROVED"}, "CAPTION_CANNOT_SALVAGE_VISUAL_FAIL")
    else:
        check("visual_policy", str(plan.visual_policy_status).upper() in {"PASS", "READY", "APPROVED"}, "CAPTION_CANNOT_SALVAGE_VISUAL_FAIL")
    try:
        placement_geometry = _rect(_mapping(plan.placement.get("geometry"), "placement.geometry"), "placement.geometry")
        check("safe_area_geometry", placement_geometry["x"] + placement_geometry["width"] <= 1.0 + EPSILON and placement_geometry["y"] + placement_geometry["height"] <= 1.0 + EPSILON, "CAPTION_GEOMETRY_INVALID")
    except CaptionBlockedError:
        check("safe_area_geometry", False, "CAPTION_GEOMETRY_INVALID")

    previous_end = -1.0
    for cue in plan.cues:
        valid_range = cue.start_seconds >= -EPSILON and cue.end_seconds > cue.start_seconds + EPSILON
        check(f"range:{cue.cue_id}", valid_range, f"CAPTION_TIMING_INVALID:{cue.cue_id}")
        within_duration = cue.end_seconds <= plan.short_duration_seconds + EPSILON
        check(f"duration:{cue.cue_id}", within_duration, f"CAPTION_CUE_BEYOND_DURATION:{cue.cue_id}")
        ordered = cue.start_seconds >= previous_end - EPSILON
        check(f"order:{cue.cue_id}", ordered, f"CAPTION_OVERLAP:{cue.cue_id}")
        previous_end = cue.end_seconds
        check(f"text:{cue.cue_id}", bool(cue.text.strip()) and cue.text_provenance == TEXT_AUTHORITY_NARRATION_ONLY, f"CAPTION_TEXT_AUTHORITY_FORBIDDEN:{cue.cue_id}")
        check(f"lines:{cue.cue_id}", cue.line_count <= MAX_LINES and 0 < cue.line_count == len(cue.display_lines), f"CAPTION_MAX_LINES_EXCEEDED:{cue.cue_id}")
        check(f"direction:{cue.cue_id}", cue.direction in {"RTL", "RTL_MIXED", "LTR"}, f"CAPTION_DIRECTION_UNRESOLVED:{cue.cue_id}")
    check("render_contract_boundary", plan.render_contract["provider_calls"] == 0 and plan.render_contract["network_calls"] == 0 and plan.render_contract["paid_calls"] == 0 and plan.render_contract["render_invoked"] is False, "CAPTION_CAPABILITY_BOUNDARY")
    return CaptionQAResult(
        status="PASS" if not failures else "BLOCKED",
        plan_sha256=plan.plan_sha256,
        checks=checks,
        failures=tuple(failures),
    )


def assert_caption_plan_valid(plan: CaptionPlan, **kwargs: Any) -> CaptionPlan:
    result = qa_caption_plan(plan, **kwargs)
    if not result.passed:
        raise CaptionBlockedError("CAPTION_QA_BLOCKED", ";".join(result.failures))
    return plan


def validate_caption_plan(plan: CaptionPlan, **kwargs: Any) -> CaptionQAResult:
    """Module-level validation wrapper for integrators that prefer functions."""

    return qa_caption_plan(plan, **kwargs)


def validate_scope(
    scope: str,
    *,
    burned_captions: bool,
    on_screen_subtitles: bool,
    narration_only: bool = True,
) -> None:
    """Module-level constitutional scope wrapper."""

    validate_caption_scope(
        scope,
        burned_captions=burned_captions,
        on_screen_subtitles=on_screen_subtitles,
        narration_only=narration_only,
    )


def build_caption_cache_key(
    *,
    episode_id: str,
    short_id: str,
    source_video_sha256: str,
    source_audio_sha256: str,
    canonical_transcript_sha256: str,
    timing_source_sha256: str,
    edit_plan_sha256: str,
    engine_version: str = ENGINE_VERSION,
) -> str:
    """Build a deterministic cache key from every upstream caption dependency."""

    payload = {
        "engine_id": ENGINE_ID,
        "engine_version": str(engine_version),
        "episode_id": str(episode_id),
        "short_id": str(short_id),
        "source_video_sha256": _require_hash(source_video_sha256, "source_video_sha256"),
        "source_audio_sha256": _require_hash(source_audio_sha256, "source_audio_sha256"),
        "canonical_transcript_sha256": _require_hash(
            canonical_transcript_sha256,
            "canonical_transcript_sha256",
        ),
        "timing_source_sha256": _require_hash(timing_source_sha256, "timing_source_sha256"),
        "edit_plan_sha256": _require_hash(edit_plan_sha256, "edit_plan_sha256"),
    }
    return _sha256(payload)


caption_cache_key = build_caption_cache_key


class ShortsBurnedCaptionEngine:
    """Thin integrator facade over the pure caption planning functions."""

    engine_id = ENGINE_ID
    engine_version = ENGINE_VERSION

    def build_caption_plan(self, *args: Any, **kwargs: Any) -> CaptionPlan:
        return build_caption_plan(*args, **kwargs)

    def validate_caption_plan(self, plan: CaptionPlan, **kwargs: Any) -> CaptionQAResult:
        return qa_caption_plan(plan, **kwargs)

    def validate_scope(
        self,
        scope: str,
        *,
        burned_captions: bool,
        on_screen_subtitles: bool,
        narration_only: bool = True,
    ) -> None:
        validate_caption_scope(
            scope,
            burned_captions=burned_captions,
            on_screen_subtitles=on_screen_subtitles,
            narration_only=narration_only,
        )

    def build_caption_cache_key(
        self,
        *,
        episode_id: str,
        short_id: str,
        source_video_sha256: str,
        source_audio_sha256: str,
        canonical_transcript_sha256: str,
        timing_source_sha256: str,
        edit_plan_sha256: str,
    ) -> str:
        return build_caption_cache_key(
            episode_id=episode_id,
            short_id=short_id,
            source_video_sha256=source_video_sha256,
            source_audio_sha256=source_audio_sha256,
            canonical_transcript_sha256=canonical_transcript_sha256,
            timing_source_sha256=timing_source_sha256,
            edit_plan_sha256=edit_plan_sha256,
            engine_version=self.engine_version,
        )


def build_caption_plan(
    transcript: CaptionTranscript | Mapping[str, Any] | Sequence[Mapping[str, Any]],
    edit_plan: ShortEditPlan | Mapping[str, Any],
    *,
    scope: str = SHORTS_SCOPE,
    captions_enabled: bool = CAPTIONS_DEFAULT_ENABLED,
    human_disabled_override: bool = False,
    on_screen_subtitles: bool = False,
    visual_policy_status: str = "PASS",
    subject_regions: Sequence[Mapping[str, Any]] | None = None,
    safe_area_profile: Mapping[str, Any] | None = None,
    style: Mapping[str, Any] | None = None,
    canonical_transcript_sha256: str | None = None,
    timing_source_sha256: str | None = None,
) -> CaptionPlan:
    """Build a Shorts-only burned narration caption plan without rendering."""

    normalized_scope = _normalize_scope(scope)
    validate_caption_scope(
        normalized_scope,
        burned_captions=bool(captions_enabled),
        on_screen_subtitles=bool(on_screen_subtitles),
        narration_only=True,
    )
    if normalized_scope != SHORTS_SCOPE:
        raise CaptionBlockedError("CAPTION_SCOPE_FORBIDDEN", normalized_scope or "UNKNOWN_SCOPE")
    if not captions_enabled and not human_disabled_override:
        raise CaptionBlockedError("CAPTION_DEFAULT_OFF_REQUIRES_HUMAN_OVERRIDE", "EXPLICIT_HUMAN_OVERRIDE_REQUIRED")
    if not captions_enabled:
        raise CaptionBlockedError("CAPTION_PLAN_DISABLED", "HUMAN_DISABLED_CAPTIONS")
    transcript_value = _coerce_transcript(
        transcript,
        canonical_transcript_sha256=canonical_transcript_sha256,
        timing_source_sha256=timing_source_sha256,
    )
    edit = _coerce_edit_plan(edit_plan)
    _validate_edit_ranges(edit)
    if not transcript_value.episode_id or not edit.source_episode_id:
        raise CaptionBlockedError("CAPTION_EPISODE_BINDING_REQUIRED", "EPISODE_ID")
    if transcript_value.episode_id != edit.source_episode_id:
        raise CaptionBlockedError("CAPTION_EPISODE_BINDING_MISMATCH", "TRANSCRIPT_EDIT_PLAN")
    if transcript_value.source_audio_sha256 is None and edit.source_audio_sha256 is None:
        raise CaptionBlockedError("CAPTION_FINAL_NARRATION_BINDING_REQUIRED", "SOURCE_AUDIO_SHA256")
    if transcript_value.source_video_sha256 is None and edit.source_video_sha256 is None:
        raise CaptionBlockedError("CAPTION_SOURCE_VIDEO_BINDING_REQUIRED", "SOURCE_VIDEO_SHA256")
    if (
        transcript_value.source_audio_sha256 is not None
        and edit.source_audio_sha256 is not None
        and transcript_value.source_audio_sha256 != edit.source_audio_sha256
    ):
        raise CaptionBlockedError("CAPTION_AUDIO_HASH_MISMATCH", "TRANSCRIPT_EDIT_PLAN")
    if (
        transcript_value.source_video_sha256 is not None
        and edit.source_video_sha256 is not None
        and transcript_value.source_video_sha256 != edit.source_video_sha256
    ):
        raise CaptionBlockedError("CAPTION_VIDEO_HASH_MISMATCH", "TRANSCRIPT_EDIT_PLAN")
    units = _materialize_units(transcript_value)
    source_cues = _coerce_source_cues(units, transcript_value)
    remapped = remap_cues_to_short_timebase(source_cues, edit)
    profile = safe_area_profile_v1() if safe_area_profile is None else json.loads(json.dumps(safe_area_profile, ensure_ascii=False))
    placement = choose_caption_placement(
        subject_regions,
        profile=profile,
        visual_policy_status=visual_policy_status,
    )
    plan = CaptionPlan(
        schema_version=SCHEMA_VERSION,
        engine_id=ENGINE_ID,
        engine_version=ENGINE_VERSION,
        scope=SHORTS_SCOPE,
        caption_mode=CAPTION_MODE,
        captions_enabled=True,
        default_enabled=CAPTIONS_DEFAULT_ENABLED,
        episode_id=transcript_value.episode_id,
        short_id=edit.short_id,
        source_video_sha256=edit.source_video_sha256 or transcript_value.source_video_sha256,
        source_audio_sha256=edit.source_audio_sha256 or transcript_value.source_audio_sha256,
        canonical_transcript_sha256=transcript_value.canonical_transcript_sha256,
        timing_source_sha256=transcript_value.timing_source_sha256,
        edit_plan_sha256=edit.edit_plan_sha256,
        timing_authority=min(
            (item.timing_authority for item in remapped),
            key=lambda item: TIMING_AUTHORITIES.index(item),
        ),
        timing_authorities_used=tuple(
            authority for authority in TIMING_AUTHORITIES if any(item.timing_authority == authority for item in remapped)
        ),
        timebase=SHORT_LOCAL_TIMEBASE,
        short_duration_seconds=edit.short_duration_seconds,
        cues=tuple(remapped),
        safe_area_profile=profile,
        placement=placement,
        style=dict(CAPTION_STYLE_V1 if style is None else style),
        visual_policy_status=str(visual_policy_status).upper(),
        text_authority=TEXT_AUTHORITY_NARRATION_ONLY,
        on_screen_subtitles=False,
    )
    plan_hash = _sha256(_plan_hash_payload(plan))
    finalized = replace(plan, plan_sha256=plan_hash)
    assert_caption_plan_valid(finalized)
    return finalized


def plan_burned_captions(*args: Any, **kwargs: Any) -> CaptionPlan:
    """Clear alias for integrators wiring Shorts production/review."""

    return build_caption_plan(*args, **kwargs)


__all__ = [
    "CAPTION_MODE",
    "CAPTIONS_DEFAULT_ENABLED",
    "CaptionBlockedError",
    "CaptionCue",
    "CaptionEngineError",
    "CaptionPlan",
    "CaptionQAResult",
    "CaptionTranscript",
    "EditPlan",
    "EditRange",
    "ENGINE_ID",
    "ENGINE_VERSION",
    "LONGFORM_SCOPE",
    "MAX_LINES",
    "SHORT_LOCAL_TIMEBASE",
    "SHORTS_SCOPE",
    "ShortEditPlan",
    "ShortsBurnedCaptionEngine",
    "TIMING_AUTHORITY_PHRASE",
    "TIMING_AUTHORITY_SENTENCE",
    "TIMING_AUTHORITY_WORD",
    "build_caption_plan",
    "build_caption_cache_key",
    "build_render_contract",
    "choose_caption_placement",
    "caption_cache_key",
    "plan_burned_captions",
    "qa_caption_plan",
    "remap_cues_to_short_timebase",
    "safe_area_profile_v1",
    "validate_caption_scope",
    "validate_caption_plan",
    "validate_scope",
]
