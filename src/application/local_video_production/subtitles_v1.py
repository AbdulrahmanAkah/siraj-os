"""Deterministic Arabic subtitle generation aligned to mastered PCM WAV audio."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Iterable
import wave

from .production_tts_v1 import inspect_pcm_wav
from .voice_provider_v1 import atomic_write_json, file_sha256


SUBTITLE_SCHEMA_V1 = "siraj-production-subtitles-v1"
SUBTITLE_VALIDATION_SCHEMA_V1 = "siraj-production-subtitles-validation-v1"
SUBTITLE_TIMING_EXACT = "TTS_METADATA_EXACT"
SUBTITLE_TIMING_ESTIMATED = "MASTERED_AUDIO_ESTIMATED"


@dataclass(frozen=True)
class SubtitleTimingConfig:
    maximum_lines_per_cue: int = 2
    maximum_characters_per_line: int = 40
    minimum_cue_duration_ms: int = 850
    maximum_cue_duration_ms: int = 7000
    minimum_gap_ms: int = 80
    maximum_reading_speed_cps: float = 18.0
    minimum_reading_speed_cps: float = 1.2
    preferred_words_per_cue: int = 10
    punctuation_pause_weights_ms: dict[str, int] = field(
        default_factory=lambda: {
            ".": 300, "؟": 360, "!": 300, "،": 150,
            "؛": 220, ":": 180, "…": 320, "-": 110,
        }
    )


@dataclass(frozen=True)
class SubtitleStyleConfig:
    font_family: str = "Arial"
    play_res_x: int = 1920
    play_res_y: int = 1080
    font_size: int = 52
    margin_v: int = 66
    outline: int = 2
    shadow: int = 1
    include_speaker_prefix: bool = False


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    speaker_id: str | None = None
    speaker_name: str | None = None
    role: str = "PRIMARY_NARRATOR"
    voice_id: str | None = None
    scene_id: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None


@dataclass(frozen=True)
class SubtitleRequest:
    mastered_audio_path: Path
    transcript: str | None
    transcript_segments: tuple[TranscriptSegment, ...] = ()
    output_directory: Path = Path(".")
    manifest_path: Path | None = None
    language: str = "ar"
    timing_config: SubtitleTimingConfig = field(default_factory=SubtitleTimingConfig)
    style_config: SubtitleStyleConfig = field(default_factory=SubtitleStyleConfig)


@dataclass(frozen=True)
class SubtitleCue:
    index: int
    start_ms: int
    end_ms: int
    text: str
    lines: tuple[str, ...]
    speaker_id: str | None
    speaker_name: str | None
    role: str
    voice_id: str | None
    scene_id: str | None
    timing_source: str
    confidence: str


@dataclass(frozen=True)
class SubtitleTrack:
    cues: tuple[SubtitleCue, ...]
    audio_duration_ms: int
    timing_source: str
    timing_mode: str
    input_fingerprint: str
    source_audio_sha256: str


@dataclass(frozen=True)
class SubtitleExportResult:
    status: str
    srt_path: Path
    vtt_path: Path
    ass_path: Path
    manifest_path: Path
    validation_path: Path
    cache_hit: bool


@dataclass(frozen=True)
class SubtitleValidationResult:
    status: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    drift_ms: int
    overlaps: int
    reading_speed_summary: dict[str, Any]
    line_length_summary: dict[str, Any]


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!؟!؛…])\s+")
_WORD = re.compile(r"\S+", re.UNICODE)
_BIDI_CONTROL = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_NO_BREAK_PREFIXES = {"و", "ف", "ب", "ك", "ل", "ال", "من", "إلى", "عن", "في", "على"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_config(config: SubtitleTimingConfig) -> None:
    if config.maximum_lines_per_cue != 2:
        raise ValueError("SUBTITLE_MAXIMUM_LINES_MUST_BE_TWO")
    if not 38 <= config.maximum_characters_per_line <= 42:
        raise ValueError("SUBTITLE_LINE_LIMIT_OUT_OF_RANGE")
    if config.minimum_cue_duration_ms <= 0 or config.maximum_cue_duration_ms < config.minimum_cue_duration_ms:
        raise ValueError("SUBTITLE_DURATION_CONFIGURATION_INVALID")
    if config.minimum_gap_ms < 0 or config.maximum_reading_speed_cps <= 0:
        raise ValueError("SUBTITLE_TIMING_CONFIGURATION_INVALID")


def _clean_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("SUBTITLE_TEXT_MUST_BE_STRING")
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    value = _BIDI_CONTROL.sub("", value)
    return re.sub(r"\s+", " ", value).strip()


def _source_segments(request: SubtitleRequest) -> tuple[TranscriptSegment, ...]:
    if request.transcript_segments:
        segments = request.transcript_segments
    elif request.transcript:
        segments = (TranscriptSegment(text=request.transcript),)
    else:
        raise ValueError("SUBTITLE_TRANSCRIPT_REQUIRED")
    result = tuple(
        TranscriptSegment(
            text=_clean_text(item.text), speaker_id=item.speaker_id,
            speaker_name=item.speaker_name, role=item.role or "PRIMARY_NARRATOR",
            voice_id=item.voice_id, scene_id=item.scene_id,
            start_ms=item.start_ms, end_ms=item.end_ms,
        )
        for item in segments
    )
    if not all(item.text for item in result):
        raise ValueError("SUBTITLE_TRANSCRIPT_SEGMENT_EMPTY")
    return result


def _split_words(words: list[str], config: SubtitleTimingConfig) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    for word in words:
        candidate = current + [word]
        if current and (len(" ".join(candidate)) > config.maximum_characters_per_line * 2 or len(candidate) > config.preferred_words_per_cue):
            if len(current) == 1 and current[0] in _NO_BREAK_PREFIXES:
                current.append(word)
                continue
            chunks.append(current)
            current = [word]
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def segment_arabic_text(text: str, config: SubtitleTimingConfig) -> list[str]:
    """Split on Arabic-aware sentence boundaries, then deterministic word chunks."""
    value = _clean_text(text)
    if not value:
        return []
    result: list[str] = []
    for sentence in _SENTENCE_BOUNDARY.split(value):
        sentence = sentence.strip()
        if not sentence:
            continue
        words = _WORD.findall(sentence)
        if len(sentence) <= config.maximum_characters_per_line * 2 and len(words) <= config.preferred_words_per_cue:
            result.append(sentence)
        else:
            result.extend(" ".join(chunk) for chunk in _split_words(words, config))
    merged: list[str] = []
    for cue in result:
        words = _WORD.findall(cue)
        if (
            merged
            and len(words) <= 2
            and len(f"{merged[-1]} {cue}") <= config.maximum_characters_per_line * 2
        ):
            merged[-1] = f"{merged[-1]} {cue}"
        else:
            merged.append(cue)
    return merged


def wrap_arabic_lines(text: str, config: SubtitleTimingConfig) -> tuple[str, ...]:
    """Keep whole words and choose the most balanced valid two-line split."""
    words = _WORD.findall(_clean_text(text))
    if not words:
        raise ValueError("SUBTITLE_CUE_TEXT_REQUIRED")
    joined = " ".join(words)
    if len(joined) <= config.maximum_characters_per_line:
        return (joined,)
    candidates: list[tuple[int, tuple[str, str]]] = []
    for index in range(1, len(words)):
        first, second = " ".join(words[:index]), " ".join(words[index:])
        if words[index - 1] in _NO_BREAK_PREFIXES or len(first) > config.maximum_characters_per_line or len(second) > config.maximum_characters_per_line:
            continue
        candidates.append((abs(len(first) - len(second)), (first, second)))
    if not candidates:
        raise ValueError("SUBTITLE_LINE_WRAP_IMPOSSIBLE")
    return min(candidates, key=lambda item: (item[0], item[1]))[1]


def _weight(text: str, config: SubtitleTimingConfig) -> float:
    word_count = len(_WORD.findall(text))
    punctuation = sum(text.count(mark) * weight for mark, weight in config.punctuation_pause_weights_ms.items())
    return max(1.0, word_count * 4.0 + len(text.replace(" ", "")) * 0.35 + punctuation / 100.0)


def _allocate_durations(texts: list[str], available_ms: int, config: SubtitleTimingConfig) -> list[int]:
    if available_ms <= 0:
        raise ValueError("SUBTITLE_AUDIO_DURATION_INSUFFICIENT")
    weights = [_weight(text, config) for text in texts]
    total = sum(weights)
    raw = [max(config.minimum_cue_duration_ms, round(available_ms * item / total)) for item in weights]
    if sum(raw) > available_ms:
        raw = [max(1, round(available_ms * item / total)) for item in weights]
    difference = available_ms - sum(raw)
    raw[-1] += difference
    if raw[-1] <= 0:
        raise ValueError("SUBTITLE_TIMING_ALLOCATION_FAILED")
    return raw


def _cues_for_segment(segment: TranscriptSegment, config: SubtitleTimingConfig, timing_source: str, duration_ms: int | None = None) -> list[dict[str, Any]]:
    texts = segment_arabic_text(segment.text, config)
    if not texts:
        raise ValueError("SUBTITLE_TRANSCRIPT_SEGMENT_EMPTY")
    if duration_ms is None:
        return [{"text": text, "segment": segment} for text in texts]
    durations = _allocate_durations(texts, duration_ms, config)
    return [{"text": text, "segment": segment, "duration_ms": current} for text, current in zip(texts, durations, strict=True)]


def _build_fingerprint(audio_sha: str, segments: Iterable[TranscriptSegment], request: SubtitleRequest) -> str:
    payload = {
        "schema_version": SUBTITLE_SCHEMA_V1,
        "generator_revision": "1",
        "audio_sha256": audio_sha,
        "segments": [asdict(item) for item in segments],
        "language": request.language,
        "timing_config": asdict(request.timing_config),
        "style_config": asdict(request.style_config),
    }
    return sha256(_canonical(payload).encode("utf-8")).hexdigest()


def build_subtitle_track(request: SubtitleRequest) -> SubtitleTrack:
    _validate_config(request.timing_config)
    if not request.mastered_audio_path.is_file():
        raise FileNotFoundError(f"SUBTITLE_MASTERED_AUDIO_NOT_FOUND:{request.mastered_audio_path}")
    try:
        audio_info = inspect_pcm_wav(request.mastered_audio_path)
    except (EOFError, OSError, ValueError, wave.Error) as error:
        raise ValueError("SUBTITLE_MASTERED_AUDIO_INVALID") from error
    duration = audio_info["duration_ms"]
    if duration <= 0:
        raise ValueError("SUBTITLE_MASTERED_AUDIO_DURATION_INVALID")
    segments = _source_segments(request)
    exact = all(item.start_ms is not None and item.end_ms is not None for item in segments)
    cue_specs: list[dict[str, Any]] = []
    if exact:
        timing_source, confidence = SUBTITLE_TIMING_EXACT, "HIGH"
        for segment in segments:
            assert segment.start_ms is not None and segment.end_ms is not None
            if segment.start_ms < 0 or segment.end_ms <= segment.start_ms or segment.end_ms > duration:
                raise ValueError("SUBTITLE_TTS_TIMING_INVALID")
            pieces = _cues_for_segment(segment, request.timing_config, timing_source, segment.end_ms - segment.start_ms)
            cursor = segment.start_ms
            for piece in pieces:
                piece["start_ms"] = cursor
                piece["end_ms"] = cursor + piece["duration_ms"]
                cursor = piece["end_ms"]
                cue_specs.append(piece)
    else:
        timing_source, confidence = SUBTITLE_TIMING_ESTIMATED, "ESTIMATED"
        for segment in segments:
            cue_specs.extend(_cues_for_segment(segment, request.timing_config, timing_source))
        gap_total = request.timing_config.minimum_gap_ms * max(0, len(cue_specs) - 1)
        durations = _allocate_durations([item["text"] for item in cue_specs], duration - gap_total, request.timing_config)
        cursor = 0
        for piece, cue_duration in zip(cue_specs, durations, strict=True):
            piece["start_ms"] = cursor
            piece["end_ms"] = cursor + cue_duration
            cursor = piece["end_ms"] + request.timing_config.minimum_gap_ms
        cue_specs[-1]["end_ms"] = duration
    cues: list[SubtitleCue] = []
    for index, item in enumerate(cue_specs, start=1):
        segment = item["segment"]
        cues.append(SubtitleCue(
            index=index, start_ms=int(item["start_ms"]), end_ms=int(item["end_ms"]),
            text=item["text"], lines=wrap_arabic_lines(item["text"], request.timing_config),
            speaker_id=segment.speaker_id, speaker_name=segment.speaker_name, role=segment.role,
            voice_id=segment.voice_id, scene_id=segment.scene_id,
            timing_source=timing_source, confidence=confidence,
        ))
    audio_sha = file_sha256(request.mastered_audio_path)
    return SubtitleTrack(tuple(cues), duration, timing_source, "EXACT" if exact else "ESTIMATED", _build_fingerprint(audio_sha, segments, request), audio_sha)


def _srt_timestamp(value: int) -> str:
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def _vtt_timestamp(value: int) -> str:
    return _srt_timestamp(value).replace(",", ".")


def _ass_timestamp(value: int) -> str:
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours}:{minutes:02}:{seconds:02}.{milliseconds // 10:02}"


def _cue_text(cue: SubtitleCue, include_prefix: bool) -> str:
    text = "\n".join(cue.lines)
    if include_prefix and cue.speaker_name:
        return f"{cue.speaker_name}: {text}"
    return text


def export_srt(track: SubtitleTrack, path: Path, style: SubtitleStyleConfig) -> None:
    text = "\n\n".join(
        f"{cue.index}\n{_srt_timestamp(cue.start_ms)} --> {_srt_timestamp(cue.end_ms)}\n{_cue_text(cue, style.include_speaker_prefix)}"
        for cue in track.cues
    ) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def export_vtt(track: SubtitleTrack, path: Path, style: SubtitleStyleConfig) -> None:
    blocks = []
    for cue in track.cues:
        identifier = cue.speaker_id or str(cue.index)
        text = _cue_text(cue, style.include_speaker_prefix)
        if cue.speaker_name:
            safe_name = cue.speaker_name.replace(">", "").replace("<", "")
            text = f"<v {safe_name}>{text}</v>"
        blocks.append(f"{identifier}\n{_vtt_timestamp(cue.start_ms)} --> {_vtt_timestamp(cue.end_ms)}\n{text}")
    path.write_text("WEBVTT\n\n" + "\n\n".join(blocks) + "\n", encoding="utf-8", newline="\n")


def _ass_style(role: str) -> str:
    if role in {"HISTORICAL_CHARACTER", "DIALOGUE", "QUOTATION", "FEMALE_CHARACTER"}:
        return "Dialogue"
    if role == "SECONDARY_NARRATOR":
        return "SecondaryNarrator"
    return "Narrator"


def export_ass(track: SubtitleTrack, path: Path, style: SubtitleStyleConfig) -> None:
    header = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {style.play_res_x}", f"PlayResY: {style.play_res_y}", "Collisions: Normal", "", "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
    ]
    for name in ("Narrator", "SecondaryNarrator", "Dialogue"):
        header.append(f"Style: {name},{style.font_family},{style.font_size},&H00FFFFFF,&H000000FF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,{style.outline},{style.shadow},2,70,70,{style.margin_v},1")
    header.extend(["", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"])
    for cue in track.cues:
        text = _cue_text(cue, style.include_speaker_prefix).replace("\n", r"\N").replace("{", r"\{").replace("}", r"\}")
        header.append(f"Dialogue: 0,{_ass_timestamp(cue.start_ms)},{_ass_timestamp(cue.end_ms)},{_ass_style(cue.role)},{cue.speaker_name or ''},0,0,{style.margin_v},,{text}")
    path.write_text("\n".join(header) + "\n", encoding="utf-8", newline="\n")


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"minimum": 0, "median": 0, "maximum": 0}
    ordered = sorted(values)
    return {"minimum": round(ordered[0], 3), "median": round(ordered[len(ordered) // 2], 3), "maximum": round(ordered[-1], 3)}


def validate_subtitle_track(track: SubtitleTrack, config: SubtitleTimingConfig, exports: dict[str, Path] | None = None) -> SubtitleValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    previous_end = 0
    overlaps = 0
    speeds: list[float] = []
    lengths: list[float] = []
    for cue in track.cues:
        if not cue.text.strip() or _BIDI_CONTROL.search(cue.text): errors.append(f"CUE_TEXT_INVALID:{cue.index}")
        if cue.start_ms < 0 or cue.end_ms <= cue.start_ms or cue.end_ms > track.audio_duration_ms: errors.append(f"CUE_TIMING_INVALID:{cue.index}")
        if cue.start_ms < previous_end:
            overlaps += 1; errors.append(f"CUE_OVERLAP:{cue.index}")
        if cue.start_ms > previous_end and cue.start_ms - previous_end < config.minimum_gap_ms and previous_end:
            warnings.append(f"CUE_GAP_SHORT:{cue.index}")
        duration = cue.end_ms - cue.start_ms
        if duration < config.minimum_cue_duration_ms or duration > config.maximum_cue_duration_ms: warnings.append(f"CUE_DURATION_OUTSIDE_PREFERENCE:{cue.index}")
        if len(cue.lines) > config.maximum_lines_per_cue or any(len(line) > config.maximum_characters_per_line for line in cue.lines): errors.append(f"CUE_LINE_LIMIT_INVALID:{cue.index}")
        speed = len(cue.text.replace(" ", "")) / max(duration / 1000, 0.001)
        speeds.append(speed); lengths.extend(float(len(line)) for line in cue.lines)
        if speed > config.maximum_reading_speed_cps: warnings.append(f"CUE_READING_SPEED_HIGH:{cue.index}")
        if speed < config.minimum_reading_speed_cps: warnings.append(f"CUE_READING_SPEED_LOW:{cue.index}")
        previous_end = cue.end_ms
    if not track.cues: errors.append("SUBTITLE_CUES_REQUIRED")
    drift = track.audio_duration_ms - (track.cues[-1].end_ms if track.cues else 0)
    if abs(drift) > 50: errors.append("SUBTITLE_AUDIO_DRIFT_EXCEEDED")
    if exports:
        for label, path in exports.items():
            try:
                content = path.read_text(encoding="utf-8")
                if not content.strip(): raise ValueError()
                cue_count = content.count(" --> ")
                if label == "vtt" and not content.startswith("WEBVTT"): errors.append("VTT_HEADER_INVALID")
                if label == "ass" and ("[Events]" not in content or content.count("Dialogue: ") != len(track.cues)): errors.append("ASS_HEADER_INVALID")
                if label in {"srt", "vtt"} and cue_count != len(track.cues): errors.append(f"{label.upper()}_FORMAT_INVALID")
            except (OSError, UnicodeError, ValueError): errors.append(f"EXPORT_INVALID:{label}")
    status = "FAIL" if errors else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    return SubtitleValidationResult(status, tuple(errors), tuple(warnings), drift, overlaps, _summary(speeds), _summary(lengths))


def _manifest(track: SubtitleTrack, validation: SubtitleValidationResult, request: SubtitleRequest, paths: dict[str, Path], cache_hit: bool) -> dict[str, Any]:
    speakers = {cue.speaker_id for cue in track.cues if cue.speaker_id}
    return {
        "schema_version": SUBTITLE_SCHEMA_V1, "status": validation.status,
        "source_audio": str(request.mastered_audio_path), "source_audio_sha256": track.source_audio_sha256,
        "source_audio_duration_ms": track.audio_duration_ms,
        "source_transcript": request.transcript if request.transcript is not None else "SEGMENTED_TRANSCRIPT",
        "timing_source": track.timing_source, "timing_mode": track.timing_mode,
        "cue_count": len(track.cues), "speaker_count": len(speakers), "language": request.language, "direction": "RTL",
        "exports": {key: str(value) for key, value in paths.items()}, "validation": asdict(validation),
        "drift_ms": validation.drift_ms, "reading_speed_summary": validation.reading_speed_summary,
        "line_length_summary": validation.line_length_summary, "overlaps": validation.overlaps,
        "warnings": list(validation.warnings), "errors": list(validation.errors),
        "deterministic_input_fingerprint": track.input_fingerprint, "cache_status": "HIT" if cache_hit else "MISS",
        "render_integration": {"preferred_burn_in_format": "ASS", "burned_in_path": str(paths["ass"]), "sidecar_paths": [str(paths["srt"]), str(paths["vtt"])]},
    }


def _cache_valid(manifest_path: Path, fingerprint: str, paths: dict[str, Path]) -> bool:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return manifest.get("deterministic_input_fingerprint") == fingerprint and all(path.is_file() and path.stat().st_size > 0 for path in paths.values())


def generate_subtitles(request: SubtitleRequest) -> tuple[SubtitleTrack, SubtitleExportResult, SubtitleValidationResult]:
    track = build_subtitle_track(request)
    request.output_directory.mkdir(parents=True, exist_ok=True)
    paths = {"srt": request.output_directory / "production-subtitles-v1.srt", "vtt": request.output_directory / "production-subtitles-v1.vtt", "ass": request.output_directory / "production-subtitles-v1.ass"}
    manifest_path = request.manifest_path or request.output_directory / "production-subtitles-v1.json"
    validation_path = request.output_directory / "production-subtitles-v1-validation.json"
    cache_hit = _cache_valid(manifest_path, track.input_fingerprint, paths)
    if not cache_hit:
        export_srt(track, paths["srt"], request.style_config)
        export_vtt(track, paths["vtt"], request.style_config)
        export_ass(track, paths["ass"], request.style_config)
    validation = validate_subtitle_track(track, request.timing_config, paths)
    atomic_write_json(validation_path, {"schema_version": SUBTITLE_VALIDATION_SCHEMA_V1, **asdict(validation)})
    atomic_write_json(manifest_path, _manifest(track, validation, request, paths, cache_hit))
    return track, SubtitleExportResult(validation.status, paths["srt"], paths["vtt"], paths["ass"], manifest_path, validation_path, cache_hit), validation


def render_subtitle_configuration(result: SubtitleExportResult, *, burn_in: bool = True) -> dict[str, str]:
    """Return an Episode Render Manifest v2-compatible subtitle configuration."""
    return {"mode": "BURNED_IN" if burn_in else "SIDECAR", "path": str(result.ass_path if burn_in else result.srt_path)}
