"""Offline recovery of trusted timing for legacy SIRAJ Shorts sources.

The resolver is deliberately an ingestion/compatibility boundary.  It does
not perform ASR, network work, provider work, retries, rendering, or
publication.  It only promotes timing that is already present in local,
hash-bound evidence into one canonical timed-transcript representation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from pathlib import Path
import shutil
import subprocess
from typing import Any, Iterable, Mapping, Sequence

from src.application.artifact_provenance_v1 import atomic_write_json

RESOLVER_ID = "SIRAJ_SHORTS_LEGACY_TIMING_RESOLVER_V1"
RESOLVER_VERSION = "1.0.4"
CANONICAL_SCHEMA_VERSION = "SIRAJ_CANONICAL_TIMED_TRANSCRIPT_V1"
CACHE_RELATIVE_ROOT = Path("artifacts/shorts-derivatives/_legacy-timing-cache")
DURATION_TOLERANCE_SECONDS = 0.25
MAX_EVIDENCE_FILES = 2500
MAX_AUDIO_FINGERPRINT_SECONDS = 600

AUTHORITY_ORDER = (
    "LEVEL_1_CANONICAL_BOUND_TIMED_SOURCE",
    "LEVEL_2_NATIVE_NARRATION_TIMING",
    "LEVEL_3_ABSOLUTE_TTS_TIMELINE_REPAIR",
    "LEVEL_4_TRUSTED_SENTENCE_SEGMENT_TIMING",
    "LEVEL_5_EXPLICIT_USER_SELECTED_TIMED_SOURCE",
)

VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi"})
AUDIO_SUFFIXES = frozenset({".m4a", ".wav", ".mp3", ".aac", ".flac", ".ogg"})
TIMED_SUFFIXES = frozenset({".srt", ".vtt"})
JSON_SUFFIX = ".json"
HASH_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
TIME_RE = re.compile(
    r"(?P<start>\d{1,3}:\d{2}(?::\d{2})?[\.,]\d{3})\s+-->\s+"
    r"(?P<end>\d{1,3}:\d{2}(?::\d{2})?[\.,]\d{3})(?:[^\r\n]*)\r?\n"
    r"(?P<body>.*?)(?=\r?\n\s*\r?\n|\Z)",
    re.DOTALL,
)
IGNORED_PARTS = frozenset(
    {
        ".git",
        "provenance-history-v1",
        "preserved",
        "backups",
        "backup",
        "attempts",
        "locks",
        "raw-provider-responses",
        "media-execution",
        "sfx",
        "_legacy-timing-cache",
    }
)
RELEVANT_NAME_TOKENS = (
    "audio", "canonical", "cue", "definition", "episode", "final", "filter",
    "manifest", "metadata", "narration", "performance", "receipt", "repair",
    "script", "segment", "subtitle", "tim", "transcript", "tts", "vtt",
)


class LegacyTimingResolverError(RuntimeError):
    """A fail-closed resolver decision."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}")


@dataclass(frozen=True, slots=True)
class CanonicalTimedSegment:
    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class TimingCandidate:
    authority_level: int
    authority_name: str
    source_type: str
    timing_source_path: Path
    timing_source_sha256: str
    segments: tuple[CanonicalTimedSegment, ...]
    source_audio_path: Path
    source_audio_sha256: str
    script_source_path: Path | None
    script_source_sha256: str | None
    duration_seconds: float
    timebase: str
    offset_seconds: float
    evidence_paths: tuple[Path, ...]
    audio_binding: Mapping[str, Any]
    canonical_explicit: bool
    binding_reason: str


@dataclass(frozen=True, slots=True)
class LegacyTimingResolution:
    status: str
    episode_id: str
    episode_display_name: str
    canonical_path: Path
    canonical_transcript_sha256: str
    canonical_document: Mapping[str, Any]
    candidate: TimingCandidate
    bound_hashes: Mapping[str, str]
    episode_metadata: Mapping[str, Any]
    cache_key: str

    @property
    def segments(self) -> tuple[CanonicalTimedSegment, ...]:
        return self.candidate.segments

    def to_dict(self) -> dict[str, Any]:
        candidate = self.candidate
        return {
            "status": self.status,
            "episode_id": self.episode_id,
            "episode_display_name": self.episode_display_name,
            "canonical_path": str(self.canonical_path),
            "canonical_transcript_sha256": self.canonical_transcript_sha256,
            "cache_key": self.cache_key,
            "timing_source_type": candidate.source_type,
            "timing_source_path": str(candidate.timing_source_path),
            "timing_source_sha256": candidate.timing_source_sha256,
            "source_audio_path": str(candidate.source_audio_path),
            "source_audio_sha256": candidate.source_audio_sha256,
            "script_source_path": (
                None if candidate.script_source_path is None else str(candidate.script_source_path)
            ),
            "script_source_sha256": candidate.script_source_sha256,
            "duration_seconds": candidate.duration_seconds,
            "timebase": candidate.timebase,
            "offset_seconds": candidate.offset_seconds,
            "segment_count": len(candidate.segments),
            "first_timestamp": candidate.segments[0].start_seconds,
            "last_timestamp": candidate.segments[-1].end_seconds,
            "audio_binding": dict(candidate.audio_binding),
            "bound_hashes": dict(self.bound_hashes),
        }

    def admission_fields(self) -> dict[str, Any]:
        candidate = self.candidate
        return {
            "timing_discovery": (
                "AUTO_DISCOVERED" if self.status == "AUTO_DISCOVERED" else "CACHE_REUSED"
            ),
            "timing_source_type": candidate.source_type,
            "timing_source_path": str(candidate.timing_source_path),
            "timing_source_sha256": candidate.timing_source_sha256,
            "source_audio_path": str(candidate.source_audio_path),
            "source_audio_sha256": candidate.source_audio_sha256,
            "canonical_timed_transcript_path": str(self.canonical_path),
            "canonical_timed_transcript_sha256": self.canonical_transcript_sha256,
            "timing_timebase": candidate.timebase,
            "timing_offset_seconds": candidate.offset_seconds,
            "timing_segment_count": len(candidate.segments),
            "timing_cache_key": self.cache_key,
            "timing_evidence_status": "TRUSTED_HASH_BOUND",
        }


@dataclass(frozen=True, slots=True)
class _EvidenceRecord:
    path: Path
    value: Any | None
    raw_text: str
    sha256: str
    parse_error: str | None = None


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        raise LegacyTimingResolverError("TIMING_EVIDENCE_INSUFFICIENT", "TIME_REQUIRED")
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        text = value.strip().replace(",", ".")
        parts = text.split(":")
        try:
            if len(parts) == 1:
                result = float(parts[0])
            elif len(parts) == 2:
                result = float(parts[0]) * 60.0 + float(parts[1])
            elif len(parts) == 3:
                result = float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
            else:
                raise ValueError
        except ValueError as exc:
            raise LegacyTimingResolverError(
                "TIMING_EVIDENCE_INSUFFICIENT", f"INVALID_TIME:{value}"
            ) from exc
    else:
        raise LegacyTimingResolverError("TIMING_EVIDENCE_INSUFFICIENT", f"INVALID_TIME:{value}")
    if not math.isfinite(result) or result < 0:
        raise LegacyTimingResolverError("TIMING_EVIDENCE_INSUFFICIENT", f"INVALID_TIME:{value}")
    return result


def _resolve_path(raw: Any, *, record_path: Path, root: Path, repo_root: Path) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    raw_path = Path(raw.strip().strip('"'))
    candidates = [raw_path] if raw_path.is_absolute() else [
        record_path.parent / raw_path,
        root / raw_path,
        repo_root / raw_path,
    ]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_file():
            return resolved
    return None


def _walk_scalars(value: Any, *, key: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for name, item in value.items():
            yield from _walk_scalars(item, key=str(name))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            yield from _walk_scalars(item, key=key)
    else:
        yield key, value


def _walk_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for item in value.values():
            yield from _walk_mappings(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            yield from _walk_mappings(item)


def _find_episode_root(video_path: Path, repo_root: Path) -> Path:
    video = video_path.resolve()
    ancestors = [video.parent, *video.parents]
    try:
        repo = repo_root.resolve()
        ancestors = [
            item for item in ancestors
            if item == repo or repo in item.parents or item == video.parent
        ]
    except OSError:
        pass
    for ancestor in ancestors:
        if (ancestor / "contracts" / "episode-definition-v1.json").is_file():
            return ancestor
        if (ancestor / "episode.json").is_file() and (ancestor / "script").is_dir():
            return ancestor
    for ancestor in ancestors:
        marker_count = sum(
            (ancestor / name).is_dir()
            for name in ("contracts", "script", "evidence", "deliverables", "orchestration")
        )
        if marker_count >= 3:
            return ancestor
    return video.parent


def _is_ignored(path: Path) -> bool:
    return any(part.casefold() in IGNORED_PARTS for part in path.parts)


def _iter_evidence_files(root: Path) -> tuple[Path, ...]:
    results: list[Path] = []
    try:
        for path in root.rglob("*"):
            if len(results) >= MAX_EVIDENCE_FILES:
                break
            if not path.is_file() or _is_ignored(path):
                continue
            suffix = path.suffix.casefold()
            if suffix in TIMED_SUFFIXES:
                results.append(path.resolve())
                continue
            if suffix not in {JSON_SUFFIX, ".txt", ".md"}:
                continue
            if any(token in path.name.casefold() for token in RELEVANT_NAME_TOKENS):
                results.append(path.resolve())
    except OSError:
        pass
    return tuple(sorted(set(results), key=lambda item: str(item).casefold()))


def _read_record(path: Path) -> _EvidenceRecord:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        return _EvidenceRecord(path, None, "", _sha256_file(path), str(exc))
    if path.suffix.casefold() != JSON_SUFFIX:
        return _EvidenceRecord(path, None, raw, _sha256_file(path))
    try:
        return _EvidenceRecord(path, json.loads(raw), raw, _sha256_file(path))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return _EvidenceRecord(path, None, raw, _sha256_file(path), str(exc))


def _record_references_path(record: _EvidenceRecord, target: Path, *, root: Path, repo_root: Path) -> bool:
    target = target.resolve()
    raw = record.raw_text.casefold()
    target_name = target.name.casefold()
    if str(target).casefold() not in raw and target_name not in raw:
        return False
    for _key, scalar in _walk_scalars(record.value):
        if not isinstance(scalar, str):
            continue
        referenced = _resolve_path(scalar, record_path=record.path, root=root, repo_root=repo_root)
        if referenced == target:
            return True
        if Path(scalar).name.casefold() == target.name.casefold() and target.parent == record.path.parent:
            return True
    return False


def _record_references_hash(record: _EvidenceRecord, expected_hash: str) -> bool:
    return any(
        isinstance(value, str) and value.casefold() == expected_hash.casefold()
        for _key, value in _walk_scalars(record.value)
    )


def _record_has_episode_id(record: _EvidenceRecord) -> str | None:
    for mapping in _walk_mappings(record.value):
        for key in ("episode_id", "episodeId"):
            value = mapping.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _record_episode_ids(records: Sequence[_EvidenceRecord]) -> tuple[str, ...]:
    return tuple(sorted({value for record in records if (value := _record_has_episode_id(record))}))


def _mapping_path_values(
    records: Sequence[_EvidenceRecord],
    *,
    root: Path,
    repo_root: Path,
    key_tokens: Sequence[str],
) -> list[tuple[Path, _EvidenceRecord, str]]:
    found: list[tuple[Path, _EvidenceRecord, str]] = []
    tokens = tuple(token.casefold() for token in key_tokens)
    for record in records:
        for mapping in _walk_mappings(record.value):
            for key, raw in mapping.items():
                if not any(token in str(key).casefold() for token in tokens):
                    continue
                candidate = _resolve_path(raw, record_path=record.path, root=root, repo_root=repo_root)
                if candidate is not None:
                    found.append((candidate, record, str(key)))
    return found


def _binding_stem(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(name).casefold()).strip("_")
    for suffix in ("sha256", "hash"):
        if normalized.endswith(f"_{suffix}"):
            normalized = normalized[: -(len(suffix) + 1)]
            break
    return normalized.removesuffix("_path").removesuffix("_file").removesuffix("_uri")


def _hash_key_is_bound_to_path_key(hash_key: str, path_key: str) -> bool:
    hash_stem = _binding_stem(hash_key)
    path_stem = _binding_stem(path_key)
    if not hash_stem or not path_stem:
        return False
    if hash_stem == path_stem:
        return True
    hash_tokens = set(hash_stem.split("_"))
    path_tokens = set(path_stem.split("_"))
    return bool(hash_tokens and path_tokens and (hash_tokens <= path_tokens or path_tokens <= hash_tokens))


def _mapping_hashes_bound_to_target(
    mapping: Mapping[str, Any],
    target: Path,
    *,
    record_path: Path,
    root: Path,
    repo_root: Path,
) -> set[tuple[str, str]] | None:
    path_keys: list[str] = []
    target_text = str(target).casefold()
    target_name = target.name.casefold()
    for key, raw in mapping.items():
        if not isinstance(raw, str):
            continue
        raw_text = raw.casefold()
        if target_text not in raw_text and target_name not in raw_text:
            continue
        referenced = _resolve_path(raw, record_path=record_path, root=root, repo_root=repo_root)
        if referenced == target:
            path_keys.append(str(key))
    if not path_keys:
        return None
    candidates: list[tuple[str, str]] = []
    for key, value in mapping.items():
        name = str(key).casefold()
        if not name.endswith("sha256") or "pcm" in name:
            continue
        if "canonical" in name and "script" in name:
            continue
        if isinstance(value, str) and HASH_RE.fullmatch(value.strip()):
            candidates.append((str(key), value.strip().lower()))
    bound = {
        (key, value)
        for key, value in candidates
        if any(_hash_key_is_bound_to_path_key(key, path_key) for path_key in path_keys)
    }
    if bound:
        return bound
    if len(candidates) == 1:
        return set(candidates)
    return set()


def _declared_hash_for_path(
    records: Sequence[_EvidenceRecord],
    target: Path,
    *,
    root: Path,
    repo_root: Path,
    audio: bool,
    extra_tokens: Sequence[str] = (),
) -> str | None:
    base_tokens = (
        ("audio", "narration", "sound", "master")
        if audio
        else ("video", "episode", "candidate", "final", "output", "source", "master")
    )
    extra = tuple(token.casefold() for token in extra_tokens)
    declared: set[str] = set()
    for record in records:
        if not _record_references_path(record, target, root=root, repo_root=repo_root):
            continue
        for mapping in _walk_mappings(record.value):
            bound_hashes = _mapping_hashes_bound_to_target(
                mapping, target, record_path=record.path, root=root, repo_root=repo_root
            )
            if bound_hashes is not None:
                if bound_hashes:
                    declared.update(value for _key, value in bound_hashes)
                continue
            for key, value in mapping.items():
                name = str(key).casefold()
                if not name.endswith("sha256"):
                    continue
                if "pcm" in name:
                    continue
                if "canonical" in name and "script" in name:
                    continue
                if extra:
                    relevant = any(
                        re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", name)
                        for token in extra
                    )
                elif audio:
                    relevant = any(token in name for token in base_tokens)
                elif target.suffix.casefold() in VIDEO_SUFFIXES:
                    relevant = (
                        any(token in name for token in base_tokens)
                        and not any(
                            token in name
                            for token in ("audio", "narration", "sound", "timing", "transcript", "script")
                        )
                    )
                else:
                    relevant = any(
                        token in name
                        for token in ("timing", "transcript", "subtitle", "cue")
                    )
                if not relevant:
                    continue
                if isinstance(value, str) and HASH_RE.fullmatch(value.strip()):
                    declared.add(value.strip().lower())
    if len(declared) > 1:
        raise LegacyTimingResolverError(
            "TIMING_SOURCE_AMBIGUOUS", f"DECLARED_HASH_AMBIGUOUS:{target}"
        )
    if declared:
        return next(iter(declared))
    return None


def _find_duration(value: Any) -> float | None:
    preferred = (
        "duration_seconds",
        "final_duration_seconds",
        "source_duration_seconds",
        "episode_seconds",
        "visual_episode_seconds",
        "total_duration_seconds",
        "duration",
    )
    for mapping in _walk_mappings(value):
        for key in preferred:
            if key in mapping:
                try:
                    return _parse_time(mapping[key])
                except LegacyTimingResolverError:
                    continue
    return None


def _probe_duration_seconds(path: Path) -> float | None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return None
    try:
        completed = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    match = re.search(r"Duration:\s+(\d{2}:\d{2}:\d{2}[\.,]\d{2,3})", output)
    if match is None:
        return None
    try:
        return _parse_time(match.group(1))
    except LegacyTimingResolverError:
        return None


def _audio_fingerprint(path: Path) -> str:
    """Hash decoded PCM through the local FFmpeg binary, never a provider."""

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        try:
            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, OSError, RuntimeError):
            ffmpeg = None
    if not ffmpeg:
        raise LegacyTimingResolverError(
            "TIMING_EVIDENCE_INSUFFICIENT", "LOCAL_AUDIO_FINGERPRINT_UNAVAILABLE"
        )
    try:
        completed = subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
                "-map", "0:a:0", "-vn", "-c:a", "pcm_s16le",
                "-f", "hash", "-hash", "sha256", "-",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=MAX_AUDIO_FINGERPRINT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LegacyTimingResolverError(
            "TIMING_EVIDENCE_INSUFFICIENT", f"AUDIO_FINGERPRINT_FAILED:{path}"
        ) from exc
    match = re.search(
        r"SHA256=([0-9a-f]{64})",
        (completed.stdout or "") + "\n" + (completed.stderr or ""),
        re.IGNORECASE,
    )
    if completed.returncode != 0 or match is None:
        raise LegacyTimingResolverError(
            "TIMING_EVIDENCE_INSUFFICIENT", f"AUDIO_STREAM_REQUIRED:{path}"
        )
    return match.group(1).lower()


def _parse_srt_vtt(path: Path) -> tuple[CanonicalTimedSegment, ...]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise LegacyTimingResolverError(
            "TIMING_EVIDENCE_INSUFFICIENT", f"TIMED_SOURCE_READ_FAILED:{path}"
        ) from exc
    segments: list[CanonicalTimedSegment] = []
    for index, match in enumerate(TIME_RE.finditer(text), start=1):
        body = match.group("body").strip("\r\n")
        if not body.strip():
            raise LegacyTimingResolverError(
                "TIMING_EVIDENCE_INSUFFICIENT", f"EMPTY_TIMED_TEXT:{path}:{index}"
            )
        segments.append(
            CanonicalTimedSegment(
                segment_id=f"SEG-{index:04d}",
                start_seconds=_parse_time(match.group("start")),
                end_seconds=_parse_time(match.group("end")),
                text=body,
            )
        )
    if not segments:
        raise LegacyTimingResolverError(
            "TIMING_EVIDENCE_INSUFFICIENT", f"NO_TIMED_SEGMENTS:{path}"
        )
    return tuple(segments)


def _raw_segment_array(value: Any) -> tuple[Sequence[Any], str] | None:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value, "array"
    if not isinstance(value, Mapping):
        return None
    for key in (
        "segments", "cues", "transcript", "sentences",
        "sentence_boundaries", "narration_blocks", "beats",
    ):
        raw = value.get(key)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
            return raw, key
    for key in ("timing", "timed_transcript", "narration_timing_map"):
        result = _raw_segment_array(value.get(key))
        if result is not None:
            return result
    return None


def _segment_text(raw: Mapping[str, Any]) -> str | None:
    for key in ("text", "canonical_text_ar", "text_ar", "narration", "narration_ar", "transcript"):
        value = raw.get(key)
        if isinstance(value, str):
            return value
    return None


def _segment_bound(raw: Mapping[str, Any], *, start: bool) -> Any:
    keys = ("start_seconds", "start_time", "start", "begin") if start else (
        "end_seconds", "end_time", "end", "stop"
    )
    for key in keys:
        if key in raw:
            return raw[key]
    return None


def _parse_json_segments(value: Any, path: Path) -> tuple[CanonicalTimedSegment, ...]:
    result = _raw_segment_array(value)
    if result is None:
        raise LegacyTimingResolverError("TIMING_EVIDENCE_INSUFFICIENT", f"SEGMENTS_REQUIRED:{path}")
    raw_segments, _kind = result
    segments: list[CanonicalTimedSegment] = []
    for index, raw in enumerate(raw_segments, start=1):
        if not isinstance(raw, Mapping):
            raise LegacyTimingResolverError(
                "TIMING_EVIDENCE_INSUFFICIENT", f"SEGMENT_OBJECT_REQUIRED:{path}:{index}"
            )
        text = _segment_text(raw)
        if text is None or not text.strip():
            raise LegacyTimingResolverError(
                "TIMING_EVIDENCE_INSUFFICIENT", f"SEGMENT_TEXT_REQUIRED:{path}:{index}"
            )
        segment_id = raw.get("segment_id", raw.get("id", raw.get("block_id", f"SEG-{index:04d}")))
        if not isinstance(segment_id, str) or not segment_id.strip():
            raise LegacyTimingResolverError(
                "TIMING_EVIDENCE_INSUFFICIENT", f"SEGMENT_ID_REQUIRED:{path}:{index}"
            )
        segments.append(
            CanonicalTimedSegment(
                segment_id=segment_id,
                start_seconds=_parse_time(_segment_bound(raw, start=True)),
                end_seconds=_parse_time(_segment_bound(raw, start=False)),
                text=text,
            )
        )
    if not segments:
        raise LegacyTimingResolverError("TIMING_EVIDENCE_INSUFFICIENT", f"NO_TIMED_SEGMENTS:{path}")
    return tuple(segments)


def _classify_json(value: Any, path: Path, *, authority_hint: str | None = None) -> tuple[int, str, bool] | None:
    lower = path.name.casefold()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sample = next((item for item in value if isinstance(item, Mapping)), None)
        if isinstance(sample, Mapping) and {"canonical_text_ar", "start_seconds", "end_seconds"}.issubset(sample):
            return 3, "LEGACY_ABSOLUTE_TTS_TIMELINE", False
    if not isinstance(value, Mapping):
        return None
    hint = str(authority_hint or "").upper()
    if (
        hint in {"CANONICAL", "LEVEL_1", "LEVEL_1_CANONICAL_BOUND_TIMED_SOURCE"}
        or "canonical-timed" in lower
        or value.get("schema_version") == CANONICAL_SCHEMA_VERSION
    ):
        return 1, "CANONICAL_TIMED_JSON", True
    if any(
        key in value
        for key in ("narration_timing_map", "word_boundaries", "word_boundary", "word_boundaries_seconds", "words")
    ):
        return 2, "NATIVE_NARRATION_TIMING_MAP", False
    if "canonical_text_ar" in value or "tts-absolute-timeline" in lower or "absolute-timeline" in lower:
        return 3, "LEGACY_ABSOLUTE_TTS_TIMELINE", False
    if any(key in value for key in ("sentences", "sentence_boundaries")):
        return 4, "LEGACY_SENTENCE_TIMING", False
    if any(key in value for key in ("segments", "cues", "transcript", "narration_blocks", "beats")):
        return 1 if hint in {"CANONICAL", "LEVEL_1"} else 4, "TIMED_JSON", hint in {"CANONICAL", "LEVEL_1"}
    return None


def _json_authority_hint(records: Sequence[_EvidenceRecord], source: Path, *, root: Path, repo_root: Path) -> str | None:
    for record in records:
        if not _record_references_path(record, source, root=root, repo_root=repo_root):
            continue
        for mapping in _walk_mappings(record.value):
            for key in ("timing_authority", "authority", "timing_source_type", "source_type"):
                value = mapping.get(key)
                if isinstance(value, str):
                    return value
    return None


def _bound_records(
    records: Sequence[_EvidenceRecord],
    *,
    video: Path,
    video_sha: str,
    root: Path,
    repo_root: Path,
) -> tuple[_EvidenceRecord, ...]:
    return tuple(
        record
        for record in records
        if _record_references_path(record, video, root=root, repo_root=repo_root)
        or _record_references_hash(record, video_sha)
    )


def _script_source(
    records: Sequence[_EvidenceRecord],
    *,
    root: Path,
    repo_root: Path,
    bound: Sequence[_EvidenceRecord],
    episode_id: str | None = None,
) -> tuple[Path | None, str | None, tuple[Path, ...]]:
    candidates = _mapping_path_values(
        tuple({record.path: record for record in bound}.values()),
        root=root,
        repo_root=repo_root,
        key_tokens=("script_path", "source_script", "performance_script"),
    )
    identity_fallback = False
    if not candidates and episode_id:
        identity_records = tuple(
            record for record in records if _record_has_episode_id(record) == episode_id
        )
        candidates = _mapping_path_values(
            identity_records,
            root=root,
            repo_root=repo_root,
            key_tokens=("script_path", "source_script", "performance_script"),
        )
        identity_fallback = bool(candidates)
    ranked = list(dict.fromkeys(
        path for path, _record, _key in candidates
        if path.suffix.casefold() in {".json", ".md", ".txt"}
    ))
    if not ranked:
        return None, None, ()
    if identity_fallback:
        declared_canonical: dict[Path, set[str]] = {}
        declared_raw: dict[Path, set[str]] = {}
        for path, record, path_key in candidates:
            for mapping in _walk_mappings(record.value):
                referenced = mapping.get(path_key)
                resolved = _resolve_path(
                    referenced, record_path=record.path, root=root, repo_root=repo_root
                )
                if resolved != path:
                    continue
                for key, value in mapping.items():
                    name = str(key).casefold()
                    if not name.endswith("sha256") or not isinstance(value, str):
                        continue
                    if not HASH_RE.fullmatch(value.strip()):
                        continue
                    if "canonical" in name and "script" in name:
                        declared_canonical.setdefault(path, set()).add(value.strip().lower())
                    elif name in {"script_sha256", "source_script_sha256"}:
                        declared_raw.setdefault(path, set()).add(value.strip().lower())

        def matching_paths(declared_by_path: Mapping[Path, set[str]]) -> list[Path]:
            validated: list[Path] = []
            for path in ranked:
                declared = declared_by_path.get(path, set())
                if not declared:
                    continue
                actual_hashes = {_sha256_file(path)}
                if path.suffix.casefold() == JSON_SUFFIX:
                    try:
                        actual_hashes.add(
                            _sha256_bytes(
                                _canonical_bytes(
                                    json.loads(path.read_text(encoding="utf-8-sig"))
                                )
                            )
                        )
                    except (OSError, UnicodeError, json.JSONDecodeError):
                        pass
                if declared.intersection(actual_hashes):
                    validated.append(path)
            return validated

        canonical_validated = matching_paths(declared_canonical)
        raw_validated = matching_paths(declared_raw)
        validated = canonical_validated or raw_validated
        if len(validated) > 1:
            raise LegacyTimingResolverError(
                "TIMING_SOURCE_AMBIGUOUS",
                "SCRIPT_SOURCE_AMBIGUOUS:" + ",".join(str(path) for path in validated),
            )
        if validated:
            ranked = validated
        else:
            # Episode identity alone is insufficient when historical script versions
            # are not tied to an explicit canonical hash.
            return None, None, ()
    ranked.sort(
        key=lambda path: (
            0 if any(token in path.name.casefold() for token in ("production-standard", "final", "canonical")) else 1,
            str(path).casefold(),
        )
    )
    selected = ranked[0]
    return selected, _sha256_file(selected), (selected,)


def _find_audio_source(
    source: Path,
    *,
    video: Path,
    records: Sequence[_EvidenceRecord],
    bound: Sequence[_EvidenceRecord],
    root: Path,
    repo_root: Path,
) -> tuple[Path, str | None, tuple[Path, ...]]:
    source_records = tuple(
        record
        for record in records
        if _record_references_path(record, source, root=root, repo_root=repo_root)
    )
    evidence_records = tuple(
        {record.path: record for record in (*bound, *source_records)}.values()
    )
    references = _mapping_path_values(
        evidence_records,
        root=root,
        repo_root=repo_root,
        key_tokens=(
            "audio_path", "audio_source", "narration_audio", "source_audio",
            "final_audio", "narration_stem", "master_m4a", "master_wav",
        ),
    )
    explicit = list(dict.fromkeys(
        path for path, _record, _key in references
        if path.suffix.casefold() in AUDIO_SUFFIXES
    ))
    siblings: list[Path] = []
    for directory in (source.parent, source.parent.parent, source.parent.parent / "audio", root / "audio"):
        if not directory.is_dir():
            continue
        try:
            siblings.extend(
                path.resolve()
                for path in directory.glob("*")
                if path.is_file() and path.suffix.casefold() in AUDIO_SUFFIXES
            )
        except OSError:
            continue
    preferred = [
        path for path in siblings
        if "absolute-timeline" in path.name.casefold()
        or ("narration" in path.name.casefold() and "stem" not in path.name.casefold())
    ]
    candidates = list(dict.fromkeys(explicit or preferred))
    if not candidates:
        return video, _sha256_file(video), ()
    if len(candidates) > 1:
        exact = [path for path in candidates if "absolute-timeline" in path.name.casefold()]
        candidates = exact if len(exact) == 1 else candidates
    if len(candidates) != 1:
        raise LegacyTimingResolverError("TIMING_SOURCE_AMBIGUOUS", f"AUDIO_SOURCE_AMBIGUOUS:{source}")
    selected = candidates[0]
    declared = _declared_hash_for_path(records, selected, root=root, repo_root=repo_root, audio=True)
    actual = _sha256_file(selected)
    if declared is not None and declared != actual:
        raise LegacyTimingResolverError("TIMING_SOURCE_STALE", f"AUDIO_HASH_MISMATCH:{selected}")
    return selected, actual, (selected,)


def _filter_evidence(source: Path, segments: Sequence[CanonicalTimedSegment], duration: float) -> tuple[Path | None, float | None]:
    directories = (source.parent, source.parent.parent, source.parent.parent / "audio")
    for directory in directories:
        if not directory.is_dir():
            continue
        try:
            filters = sorted(directory.glob("*.filter.txt"), key=lambda item: str(item).casefold())
        except OSError:
            continue
        for path in filters:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            trim_match = re.search(r"atrim=0:(\d+(?:\.\d+)?)", text)
            delays = [int(value) / 1000.0 for value in re.findall(r"adelay=(\d+)\|\1", text)]
            if trim_match is None or len(delays) != len(segments):
                continue
            if abs(float(trim_match.group(1)) - duration) > DURATION_TOLERANCE_SECONDS:
                continue
            if all(abs(delay - segment.start_seconds) <= 0.005 for delay, segment in zip(delays, segments)):
                return path, 0.0
    return None, None


def _timebase_and_offset(
    value: Any,
    *,
    source: Path,
    segments: Sequence[CanonicalTimedSegment],
    duration: float,
) -> tuple[str, float, Path | None]:
    timebase: str | None = None
    offset: float | None = None
    for mapping in _walk_mappings(value):
        for key in ("timebase", "timeline_timebase", "timestamp_timebase"):
            raw = mapping.get(key)
            if isinstance(raw, str) and raw.strip():
                timebase = raw.strip().upper()
        for key in ("offset_seconds", "video_offset_seconds", "timeline_offset_seconds"):
            if key in mapping:
                try:
                    offset = _parse_time(mapping[key])
                except LegacyTimingResolverError:
                    pass
    if timebase is not None:
        if "NARRATION" in timebase and offset is None:
            raise LegacyTimingResolverError(
                "TIMING_EVIDENCE_INSUFFICIENT", "NARRATION_TIMEBASE_OFFSET_REQUIRED"
            )
        return (
            "FINAL_VIDEO" if "VIDEO" in timebase else "FINAL_VIDEO_OFFSET_APPLIED",
            float(offset or 0.0),
            None,
        )
    filter_path, filter_offset = _filter_evidence(source, segments, duration)
    if filter_path is not None:
        return "FINAL_VIDEO_ABSOLUTE", float(filter_offset or 0.0), filter_path
    if source.suffix.casefold() in TIMED_SUFFIXES:
        return "FINAL_VIDEO", 0.0, None
    raise LegacyTimingResolverError("TIMING_EVIDENCE_INSUFFICIENT", "TIMEBASE_OFFSET_UNPROVEN")


def _validate_segments(
    segments: Sequence[CanonicalTimedSegment],
    *,
    duration: float,
    offset: float,
) -> tuple[CanonicalTimedSegment, ...]:
    if not math.isfinite(duration) or duration <= 0:
        raise LegacyTimingResolverError(
            "TIMING_EVIDENCE_INSUFFICIENT", "AUTHORITATIVE_DURATION_REQUIRED"
        )
    transformed: list[CanonicalTimedSegment] = []
    seen: set[str] = set()
    previous_end = -1.0
    for segment in segments:
        start = float(segment.start_seconds) + offset
        end = float(segment.end_seconds) + offset
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise LegacyTimingResolverError(
                "TIMING_EVIDENCE_INSUFFICIENT", f"SEGMENT_RANGE_INVALID:{segment.segment_id}"
            )
        if segment.segment_id in seen:
            raise LegacyTimingResolverError(
                "TIMING_EVIDENCE_INSUFFICIENT", f"SEGMENT_ID_DUPLICATE:{segment.segment_id}"
            )
        if start < previous_end - 1e-9:
            raise LegacyTimingResolverError(
                "TIMING_EVIDENCE_INSUFFICIENT", f"SEGMENTS_OVERLAP:{segment.segment_id}"
            )
        if end > duration + DURATION_TOLERANCE_SECONDS:
            raise LegacyTimingResolverError(
                "TIMING_EVIDENCE_INSUFFICIENT", f"SEGMENT_BEYOND_DURATION:{segment.segment_id}"
            )
        if not isinstance(segment.text, str) or not segment.text.strip():
            raise LegacyTimingResolverError(
                "TIMING_EVIDENCE_INSUFFICIENT", f"SEGMENT_TEXT_EMPTY:{segment.segment_id}"
            )
        transformed.append(CanonicalTimedSegment(segment.segment_id, start, end, segment.text))
        seen.add(segment.segment_id)
        previous_end = end
    if not transformed:
        raise LegacyTimingResolverError("TIMING_EVIDENCE_INSUFFICIENT", "NO_SEGMENTS")
    return tuple(transformed)


def _audio_binding(
    video: Path,
    audio: Path,
    *,
    records: Sequence[_EvidenceRecord],
    root: Path,
    repo_root: Path,
    fingerprint_cache: dict[Path, str] | None = None,
) -> dict[str, Any]:
    cache = fingerprint_cache if fingerprint_cache is not None else {}

    def fingerprint(path: Path) -> str:
        key = path.resolve()
        if key not in cache:
            cache[key] = _audio_fingerprint(key)
        return cache[key]

    if video.resolve() == audio.resolve():
        audio_hash = fingerprint(video)
        return {
            "status": "PASS",
            "method": "EMBEDDED_FINAL_AUDIO_STREAM",
            "video_audio_pcm_sha256": audio_hash,
            "source_audio_pcm_sha256": audio_hash,
        }
    declared: list[str] = []
    for record in records:
        if not _record_references_path(record, audio, root=root, repo_root=repo_root):
            continue
        for mapping in _walk_mappings(record.value):
            for key, value in mapping.items():
                if (
                    "pcm" in str(key).casefold()
                    and "sha256" in str(key).casefold()
                    and isinstance(value, str)
                    and HASH_RE.fullmatch(value.strip())
                ):
                    declared.append(value.strip().lower())
    if len(set(declared)) == 1:
        return {
            "status": "PASS",
            "method": "HASH_BOUND_AUDIO_EVIDENCE",
            "video_audio_pcm_sha256": declared[0],
            "source_audio_pcm_sha256": declared[0],
        }
    video_fingerprint = fingerprint(video)
    audio_fingerprint = fingerprint(audio)
    if video_fingerprint != audio_fingerprint:
        raise LegacyTimingResolverError("TIMING_SOURCE_STALE", "FINAL_AUDIO_FINGERPRINT_MISMATCH")
    return {
        "status": "PASS",
        "method": "DECODED_PCM_SHA256_EQUAL",
        "video_audio_pcm_sha256": video_fingerprint,
        "source_audio_pcm_sha256": audio_fingerprint,
    }


def _cache_path(repo_root: Path, episode_id: str, cache_key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", episode_id).strip("._") or "episode"
    return repo_root / CACHE_RELATIVE_ROOT / safe / f"canonical-timed-transcript-{cache_key}.json"


def _canonical_hash(document: Mapping[str, Any]) -> str:
    payload = {
        key: value
        for key, value in document.items()
        if key not in {"canonical_transcript_sha256", "generated_at"}
    }
    return _sha256_bytes(_canonical_bytes(payload))


def _display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def _cache_resolution(
    path: Path,
    *,
    expected_cache_key: str,
    video: Path,
    video_sha: str,
    repo_root: Path,
) -> LegacyTimingResolution | None:
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(document, Mapping) or document.get("schema_version") != CANONICAL_SCHEMA_VERSION:
        return None
    if document.get("cache_key") != expected_cache_key:
        return None
    if document.get("source_video_sha256") != video_sha:
        raise LegacyTimingResolverError("TIMING_SOURCE_STALE", "CACHE_VIDEO_HASH_CHANGED")
    canonical_hash = document.get("canonical_transcript_sha256")
    if not isinstance(canonical_hash, str) or _canonical_hash(document) != canonical_hash:
        raise LegacyTimingResolverError("TIMING_EVIDENCE_INSUFFICIENT", "CACHE_CANONICAL_HASH_INVALID")
    timing_path = Path(str(document.get("timing_source_path", "")))
    audio_path = Path(str(document.get("source_audio_path", "")))
    if not timing_path.is_absolute():
        timing_path = repo_root / timing_path
    if not audio_path.is_absolute():
        audio_path = repo_root / audio_path
    if not timing_path.is_file() or not audio_path.is_file():
        raise LegacyTimingResolverError("TIMING_SOURCE_STALE", "CACHE_UPSTREAM_MISSING")
    if _sha256_file(timing_path) != document.get("timing_source_sha256"):
        raise LegacyTimingResolverError("TIMING_SOURCE_STALE", "CACHE_TIMING_HASH_CHANGED")
    if _sha256_file(audio_path) != document.get("source_audio_sha256"):
        raise LegacyTimingResolverError("TIMING_SOURCE_STALE", "CACHE_AUDIO_HASH_CHANGED")
    segments = tuple(
        CanonicalTimedSegment(
            str(item["segment_id"]),
            float(item["start_seconds"]),
            float(item["end_seconds"]),
            str(item["text"]),
        )
        for item in document.get("segments", ())
        if isinstance(item, Mapping)
    )
    provenance = document.get("provenance", {})
    if not isinstance(provenance, Mapping):
        provenance = {}
    script_raw = document.get("script_source_path")
    script_path = None
    if script_raw:
        script_path = Path(str(script_raw))
        if not script_path.is_absolute():
            script_path = repo_root / script_path
        script_path = script_path.resolve()
        if (
            not script_path.is_file()
            or _sha256_file(script_path) != document.get("script_source_sha256")
        ):
            raise LegacyTimingResolverError("TIMING_SOURCE_STALE", "CACHE_SCRIPT_HASH_CHANGED")
    candidate = TimingCandidate(
        authority_level=int(provenance.get("authority_level", 3)),
        authority_name=str(provenance.get("authority_name", AUTHORITY_ORDER[2])),
        source_type=str(document["timing_source_type"]),
        timing_source_path=timing_path.resolve(),
        timing_source_sha256=str(document["timing_source_sha256"]),
        segments=segments,
        source_audio_path=audio_path.resolve(),
        source_audio_sha256=str(document["source_audio_sha256"]),
        script_source_path=script_path,
        script_source_sha256=document.get("script_source_sha256"),
        duration_seconds=float(document["duration_seconds"]),
        timebase=str(provenance.get("timebase", "FINAL_VIDEO")),
        offset_seconds=float(provenance.get("offset_seconds", 0.0)),
        evidence_paths=tuple(),
        audio_binding=dict(provenance.get("audio_binding", {})),
        canonical_explicit=True,
        binding_reason="CACHE_KEY_AND_UPSTREAM_HASH_MATCH",
    )
    bound_hashes = {
        str(key): str(value)
        for key, value in dict(provenance.get("bound_hashes", {})).items()
    }
    metadata = dict(provenance.get("episode_metadata", {}))
    return LegacyTimingResolution(
        status="CACHE_REUSED",
        episode_id=str(document["episode_id"]),
        episode_display_name=str(metadata.get("episode_display_name", document["episode_id"])),
        canonical_path=path.resolve(),
        canonical_transcript_sha256=canonical_hash,
        canonical_document=document,
        candidate=candidate,
        bound_hashes=bound_hashes,
        episode_metadata=metadata,
        cache_key=expected_cache_key,
    )


def _candidate_from_source(
    source: Path,
    *,
    records: Sequence[_EvidenceRecord],
    bound_records: Sequence[_EvidenceRecord],
    episode_id: str | None,
    video: Path,
    root: Path,
    repo_root: Path,
    duration: float,
    fingerprint_cache: dict[Path, str] | None = None,
) -> TimingCandidate | None:
    source_record = next((record for record in records if record.path == source), None)
    if source.suffix.casefold() in TIMED_SUFFIXES:
        segments = _parse_srt_vtt(source)
        authority_level, source_type, explicit = 1, f"CANONICAL_{source.suffix[1:].upper()}", True
    else:
        if source_record is None or source_record.parse_error is not None:
            if source_record is not None and source_record.parse_error is not None:
                raise LegacyTimingResolverError(
                    "TIMING_EVIDENCE_INSUFFICIENT", f"TIMED_JSON_MALFORMED:{source}"
                )
            return None
        hint = _json_authority_hint(records, source, root=root, repo_root=repo_root)
        classification = _classify_json(source_record.value, source, authority_hint=hint)
        if classification is None:
            return None
        authority_level, source_type, explicit = classification
        segments = _parse_json_segments(source_record.value, source)
    declared_timing_hash = _declared_hash_for_path(
        records, source, root=root, repo_root=repo_root, audio=False
    )
    source_hash = _sha256_file(source)
    if declared_timing_hash is not None and declared_timing_hash != source_hash:
        raise LegacyTimingResolverError("TIMING_SOURCE_STALE", f"TIMING_HASH_MISMATCH:{source}")
    audio_path, audio_hash, audio_evidence = _find_audio_source(
        source,
        video=video,
        records=records,
        bound=bound_records,
        root=root,
        repo_root=repo_root,
    )
    if audio_hash is None:
        raise LegacyTimingResolverError("TIMING_EVIDENCE_INSUFFICIENT", f"AUDIO_SOURCE_REQUIRED:{source}")
    declared_audio_hash = _declared_hash_for_path(
        records, audio_path, root=root, repo_root=repo_root, audio=True
    )
    if declared_audio_hash is not None and declared_audio_hash != audio_hash:
        raise LegacyTimingResolverError("TIMING_SOURCE_STALE", f"AUDIO_HASH_MISMATCH:{audio_path}")
    script_path, script_hash, script_evidence = _script_source(
        records,
        root=root,
        repo_root=repo_root,
        bound=bound_records,
        episode_id=episode_id,
    )
    declared_script_hash = None
    if script_path is not None:
        declared_script_hash = _declared_hash_for_path(
            records,
            script_path,
            root=root,
            repo_root=repo_root,
            audio=False,
            extra_tokens=("script", "performance"),
        )
        if declared_script_hash is not None and declared_script_hash != script_hash:
            raise LegacyTimingResolverError(
                "TIMING_SOURCE_STALE", f"SCRIPT_HASH_MISMATCH:{script_path}"
            )
    actual_duration = duration
    source_duration = _find_duration(source_record.value if source_record is not None else None)
    if source_duration is not None and abs(source_duration - duration) <= DURATION_TOLERANCE_SECONDS:
        actual_duration = source_duration
    timebase, offset, filter_path = _timebase_and_offset(
        source_record.value if source_record is not None else {},
        source=source,
        segments=segments,
        duration=actual_duration,
    )
    transformed = _validate_segments(segments, duration=actual_duration, offset=offset)
    audio_binding = _audio_binding(
        video,
        audio_path,
        records=records,
        root=root,
        repo_root=repo_root,
        fingerprint_cache=fingerprint_cache,
    )
    evidence = [source, *audio_evidence, *script_evidence]
    if filter_path is not None:
        evidence.append(filter_path)
    evidence.extend(
        record.path for record in bound_records if record.path.suffix.casefold() == JSON_SUFFIX
    )
    return TimingCandidate(
        authority_level=authority_level,
        authority_name=AUTHORITY_ORDER[authority_level - 1],
        source_type=source_type,
        timing_source_path=source.resolve(),
        timing_source_sha256=source_hash,
        segments=transformed,
        source_audio_path=audio_path.resolve(),
        source_audio_sha256=audio_hash,
        script_source_path=script_path,
        script_source_sha256=script_hash,
        duration_seconds=actual_duration,
        timebase=timebase,
        offset_seconds=offset,
        evidence_paths=tuple(dict.fromkeys(path.resolve() for path in evidence if path.is_file())),
        audio_binding=audio_binding,
        canonical_explicit=explicit,
        binding_reason=(
            "EXPLICIT_HASH_OR_PATH_EDGE" if bound_records
            else "PACKAGE_AND_AUDIO_FINGERPRINT_EDGE"
        ),
    )


def _discover_candidates(
    *,
    video: Path,
    video_sha: str,
    records: Sequence[_EvidenceRecord],
    files: Sequence[Path],
    root: Path,
    repo_root: Path,
    duration: float,
) -> tuple[TimingCandidate, ...]:
    bound_records = _bound_records(
        records, video=video, video_sha=video_sha, root=root, repo_root=repo_root
    )
    episode_id, _episode_display_name = _episode_identity(records, bound_records, root)
    candidate_paths: list[Path] = []
    for path in files:
        suffix = path.suffix.casefold()
        if suffix in TIMED_SUFFIXES:
            if (
                path.parent == video.parent
                or any(
                    _record_references_path(record, path, root=root, repo_root=repo_root)
                    for record in bound_records
                )
            ):
                candidate_paths.append(path)
        elif suffix == JSON_SUFFIX:
            record = next((item for item in records if item.path == path), None)
            if record is None or record.parse_error is not None:
                if any(token in path.name.casefold() for token in ("timing", "timeline", "transcript", "subtitle", "cue")):
                    candidate_paths.append(path)
                continue
            classification = _classify_json(
                record.value,
                path,
                authority_hint=_json_authority_hint(records, path, root=root, repo_root=repo_root),
            )
            if classification is None:
                continue
            if (
                _record_references_path(record, video, root=root, repo_root=repo_root)
                or any(
                    _record_references_path(item, path, root=root, repo_root=repo_root)
                    for item in bound_records
                )
                or (classification[0] == 3 and bound_records)
            ):
                candidate_paths.append(path)
    candidates: list[TimingCandidate] = []
    errors: list[LegacyTimingResolverError] = []
    fingerprint_cache: dict[Path, str] = {}
    for path in dict.fromkeys(candidate_paths):
        try:
            candidate = _candidate_from_source(
                path,
                records=records,
                bound_records=bound_records,
                episode_id=episode_id,
                video=video,
                root=root,
                repo_root=repo_root,
                duration=duration,
                fingerprint_cache=fingerprint_cache,
            )
        except LegacyTimingResolverError as exc:
            errors.append(exc)
            continue
        if candidate is not None:
            candidates.append(candidate)
    if not candidates:
        stale = next((error for error in errors if error.code == "TIMING_SOURCE_STALE"), None)
        if stale is not None:
            raise stale
        if errors:
            raise errors[0]
        raise LegacyTimingResolverError("TIMING_EVIDENCE_INSUFFICIENT", "NO_TRUSTED_TIMING_SOURCE")
    return tuple(candidates)


def _select_candidate(candidates: Sequence[TimingCandidate]) -> TimingCandidate:
    minimum = min(candidate.authority_level for candidate in candidates)
    same_level = [candidate for candidate in candidates if candidate.authority_level == minimum]
    explicit = [candidate for candidate in same_level if candidate.canonical_explicit]
    if len(explicit) == 1:
        return explicit[0]
    if len(same_level) != 1:
        paths = ",".join(str(candidate.timing_source_path) for candidate in same_level)
        raise LegacyTimingResolverError("TIMING_SOURCE_AMBIGUOUS", paths)
    return same_level[0]


def _episode_identity(
    records: Sequence[_EvidenceRecord],
    bound_records: Sequence[_EvidenceRecord],
    root: Path,
) -> tuple[str, str]:
    bound_ids = _record_episode_ids(bound_records)
    if bound_ids:
        ids = bound_ids
    elif root.name:
        # The selected evidence root is a safer fallback than collecting
        # unrelated episode IDs from sibling historical reports.
        ids = (root.name,)
    else:
        ids = _record_episode_ids(records)
    if len(ids) > 1:
        raise LegacyTimingResolverError(
            "TIMING_SOURCE_AMBIGUOUS", "EPISODE_ID_AMBIGUOUS:" + ",".join(ids)
        )
    episode_id = ids[0] if ids else root.name
    display = episode_id
    for record in (*bound_records, *records):
        for mapping in _walk_mappings(record.value):
            for key in ("episode_display_name", "title_ar", "working_title_ar", "title"):
                value = mapping.get(key)
                if isinstance(value, str) and value.strip():
                    display = value
                    break
            if display != episode_id:
                break
    return episode_id, display


def _build_document(
    candidate: TimingCandidate,
    *,
    episode_id: str,
    episode_display_name: str,
    video: Path,
    video_sha: str,
    repo_root: Path,
    cache_key: str,
    bound_hashes: Mapping[str, str],
    episode_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": CANONICAL_SCHEMA_VERSION,
        "episode_id": episode_id,
        "source_video_path": _display_path(video, repo_root),
        "source_video_sha256": video_sha,
        "source_audio_path": _display_path(candidate.source_audio_path, repo_root),
        "source_audio_sha256": candidate.source_audio_sha256,
        "timing_source_type": candidate.source_type,
        "timing_source_path": _display_path(candidate.timing_source_path, repo_root),
        "timing_source_sha256": candidate.timing_source_sha256,
        "script_source_path": (
            None
            if candidate.script_source_path is None
            else _display_path(candidate.script_source_path, repo_root)
        ),
        "script_source_sha256": candidate.script_source_sha256,
        "segments": [item.to_dict() for item in candidate.segments],
        "duration_seconds": candidate.duration_seconds,
        "resolver_version": RESOLVER_VERSION,
        "generated_at": _utc_now(),
        "provenance": {
            "resolver_id": RESOLVER_ID,
            "authority_level": candidate.authority_level,
            "authority_name": candidate.authority_name,
            "binding_reason": candidate.binding_reason,
            "episode_display_name": episode_display_name,
            "timebase": candidate.timebase,
            "offset_seconds": candidate.offset_seconds,
            "audio_binding": dict(candidate.audio_binding),
            "evidence_paths": [_display_path(path, repo_root) for path in candidate.evidence_paths],
            "bound_hashes": dict(bound_hashes),
            "episode_metadata": dict(episode_metadata),
        },
        "cache_key": cache_key,
    }
    document["canonical_transcript_sha256"] = _canonical_hash(document)
    return document


def resolve_legacy_timing(
    repo_root: Path,
    video_path: Path,
    *,
    authoritative_duration_seconds: float | None = None,
    persist: bool = True,
) -> LegacyTimingResolution:
    """Discover and bind one trusted legacy timing source for a selected video."""

    repo = Path(repo_root).resolve()
    video = Path(video_path).resolve()
    if not video.is_file() or video.suffix.casefold() not in VIDEO_SUFFIXES:
        raise LegacyTimingResolverError("TIMING_EVIDENCE_INSUFFICIENT", "VIDEO_SOURCE_REQUIRED")
    video_sha = _sha256_file(video)
    root = _find_episode_root(video, repo)
    files = _iter_evidence_files(root)
    records = tuple(
        _read_record(path) for path in files if path.suffix.casefold() == JSON_SUFFIX
    )
    bound_records = _bound_records(
        records, video=video, video_sha=video_sha, root=root, repo_root=repo
    )
    declared_video_hash = _declared_hash_for_path(
        records, video, root=root, repo_root=repo, audio=False
    )
    if declared_video_hash is not None and declared_video_hash != video_sha:
        raise LegacyTimingResolverError("TIMING_SOURCE_STALE", "VIDEO_HASH_MISMATCH")
    episode_id, episode_display_name = _episode_identity(records, bound_records, root)
    duration = authoritative_duration_seconds
    if duration is None:
        duration = next(
            (
                found
                for record in bound_records
                if (found := _find_duration(record.value)) is not None
            ),
            None,
        )
    if duration is None:
        duration = _probe_duration_seconds(video)
    if duration is None:
        raise LegacyTimingResolverError(
            "TIMING_EVIDENCE_INSUFFICIENT", "AUTHORITATIVE_VIDEO_DURATION_REQUIRED"
        )
    candidates = _discover_candidates(
        video=video,
        video_sha=video_sha,
        records=records,
        files=files,
        root=root,
        repo_root=repo,
        duration=float(duration),
    )
    selected = _select_candidate(candidates)
    bound_hashes: dict[str, str] = {
        str(path): _sha256_file(path)
        for path in selected.evidence_paths
        if path.is_file()
    }
    bound_hashes[str(selected.timing_source_path)] = selected.timing_source_sha256
    bound_hashes[str(selected.source_audio_path)] = selected.source_audio_sha256
    if selected.script_source_path is not None and selected.script_source_sha256 is not None:
        bound_hashes[str(selected.script_source_path)] = selected.script_source_sha256
    episode_metadata = {
        "episode_id": episode_id,
        "episode_display_name": episode_display_name,
        "duration_seconds": selected.duration_seconds,
        "segments": [item.to_dict() for item in selected.segments],
        "constitution_version": next(
            (
                str(mapping["constitution_version"])
                for record in bound_records
                for mapping in _walk_mappings(record.value)
                if isinstance(mapping.get("constitution_version"), (str, int, float))
            ),
            "0.0.0",
        ),
    }
    cache_payload = {
        "episode_id": episode_id,
        "source_video_sha256": video_sha,
        "source_audio_sha256": selected.source_audio_sha256,
        "timing_source_sha256": selected.timing_source_sha256,
        "script_source_sha256": selected.script_source_sha256,
        "evidence_sha256s": sorted(bound_hashes.items()),
        "resolver_version": RESOLVER_VERSION,
    }
    cache_key = _sha256_bytes(_canonical_bytes(cache_payload))
    cache_path = _cache_path(repo, episode_id, cache_key)
    cached = _cache_resolution(
        cache_path,
        expected_cache_key=cache_key,
        video=video,
        video_sha=video_sha,
        repo_root=repo,
    )
    if cached is not None:
        return cached
    document = _build_document(
        selected,
        episode_id=episode_id,
        episode_display_name=episode_display_name,
        video=video,
        video_sha=video_sha,
        repo_root=repo,
        cache_key=cache_key,
        bound_hashes=bound_hashes,
        episode_metadata=episode_metadata,
    )
    if persist:
        try:
            atomic_write_json(cache_path, document, preserve_previous=True)
        except OSError as exc:
            raise LegacyTimingResolverError(
                "TIMING_EVIDENCE_INSUFFICIENT", f"TIMING_CACHE_WRITE_FAILED:{cache_path}"
            ) from exc
    return LegacyTimingResolution(
        status="AUTO_DISCOVERED",
        episode_id=episode_id,
        episode_display_name=episode_display_name,
        canonical_path=cache_path.resolve(),
        canonical_transcript_sha256=str(document["canonical_transcript_sha256"]),
        canonical_document=document,
        candidate=selected,
        bound_hashes=bound_hashes,
        episode_metadata=episode_metadata,
        cache_key=cache_key,
    )


__all__ = [
    "AUTHORITY_ORDER",
    "CANONICAL_SCHEMA_VERSION",
    "CACHE_RELATIVE_ROOT",
    "CanonicalTimedSegment",
    "LegacyTimingResolution",
    "LegacyTimingResolverError",
    "RESOLVER_ID",
    "RESOLVER_VERSION",
    "TimingCandidate",
    "resolve_legacy_timing",
]
