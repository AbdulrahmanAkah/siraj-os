"""Offline source discovery for the user-facing Shorts episode picker.

This module only inspects local files.  It never contacts a provider, submits a
request, retries an operation, or changes the source package.  The result is a
conservative discovery record: an ambiguous or weak relationship is surfaced
for human choice instead of being silently selected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from src.application.shorts_legacy_timing_resolver_v1 import (
    LegacyTimingResolution,
    LegacyTimingResolverError,
    resolve_legacy_timing,
)


VIDEO_SUFFIXES = (".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi")
SUBTITLE_SUFFIXES = (".srt", ".vtt")
JSON_SUFFIX = ".json"
IGNORED_TOKENS = ("preserved", "backup", "provenance-history", ".git")
MAX_DISCOVERY_FILES = 1200


def _sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _has_timing(value: Mapping[str, Any]) -> bool:
    for key in ("segments", "cues", "transcript", "narration_blocks", "beats"):
        item = value.get(key)
        if isinstance(item, list) and bool(item):
            return True
    return False


def _contains_video_reference(value: Mapping[str, Any], video_path: Path) -> bool:
    target = video_path.name.casefold()
    for key in ("video_path", "episode_video", "source_video_path", "source_video"):
        raw = value.get(key)
        if isinstance(raw, str) and (target in Path(raw).name.casefold() or target in raw.casefold()):
            return True
    return False


def _format_modified(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except OSError:
        return "غير متاح"


@dataclass(frozen=True, slots=True)
class SourceCandidate:
    """One local metadata or timing file that may belong to the chosen video."""

    path: Path
    episode_id: str | None
    episode_display_name: str | None
    has_timing: bool
    relation: str
    relationship_score: int
    source_hash_match: bool | None
    modified_time: str

    @property
    def is_metadata(self) -> bool:
        return self.path.suffix.casefold() == JSON_SUFFIX and self.episode_id is not None

    @property
    def is_timing(self) -> bool:
        return self.path.suffix.casefold() in SUBTITLE_SUFFIXES or (self.path.suffix.casefold() == JSON_SUFFIX and self.has_timing)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "episode_id": self.episode_id,
            "episode_display_name": self.episode_display_name,
            "has_timing": self.has_timing,
            "relation": self.relation,
            "relationship_score": self.relationship_score,
            "source_hash_match": self.source_hash_match,
            "modified_time": self.modified_time,
        }


@dataclass(frozen=True, slots=True)
class SourceDiscoveryResult:
    video_path: Path
    metadata_candidates: tuple[SourceCandidate, ...]
    transcript_candidates: tuple[SourceCandidate, ...]
    matched_metadata: SourceCandidate | None
    matched_transcript: SourceCandidate | None
    scanned_files: int
    status: str
    legacy_timing_resolution: LegacyTimingResolution | None = None

    @property
    def metadata_ambiguous(self) -> bool:
        return len(self.metadata_candidates) > 1 and self.matched_metadata is None

    @property
    def ready_without_manual_file(self) -> bool:
        return bool(
            self.legacy_timing_resolution is not None
            or (
                self.matched_metadata is not None
                and (self.matched_metadata.has_timing or self.matched_transcript is not None)
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_path": str(self.video_path),
            "metadata_candidates": [item.to_dict() for item in self.metadata_candidates],
            "transcript_candidates": [item.to_dict() for item in self.transcript_candidates],
            "matched_metadata": None if self.matched_metadata is None else self.matched_metadata.to_dict(),
            "matched_transcript": None if self.matched_transcript is None else self.matched_transcript.to_dict(),
            "scanned_files": self.scanned_files,
            "status": self.status,
            "legacy_timing_resolution": (
                None
                if self.legacy_timing_resolution is None
                else self.legacy_timing_resolution.to_dict()
            ),
        }


def _search_roots(video_path: Path) -> tuple[Path, ...]:
    roots: list[Path] = [video_path.parent]
    known_output_names = {"cinematic", "final-render", "final", "render", "renders", "outputs", "video", "videos", "deliverables"}
    current = video_path.parent
    # SIRAJ packages commonly keep a final video below a cinematic/final-render
    # directory.  Only the direct package parent is inspected in that case;
    # recursively scanning broad ancestors could collect another episode's
    # metadata and would turn an unrelated file into a silent match.
    if current.name.casefold() in known_output_names:
        roots.append(current.parent)
        if current.parent.name.casefold() in known_output_names:
            roots.append(current.parent.parent)
    return tuple(dict.fromkeys(root.resolve() for root in roots))


def _iter_local_files(video_path: Path) -> list[Path]:
    files: list[Path] = []
    roots = _search_roots(video_path)
    for index, root in enumerate(roots):
        try:
            iterator = root.rglob("*") if index == 0 else root.glob("*")
            for path in iterator:
                if len(files) >= MAX_DISCOVERY_FILES:
                    return files
                if not path.is_file() or any(token in part.casefold() for part in path.parts for token in IGNORED_TOKENS):
                    continue
                suffix = path.suffix.casefold()
                if suffix in SUBTITLE_SUFFIXES or suffix == JSON_SUFFIX:
                    files.append(path.resolve())
        except OSError:
            continue
    return sorted(set(files), key=lambda item: str(item).casefold())


def _candidate_for(path: Path, video_path: Path, *, video_sha: str | None) -> SourceCandidate | None:
    suffix = path.suffix.casefold()
    value = _read_json(path) if suffix == JSON_SUFFIX else None
    if suffix == JSON_SUFFIX and value is None:
        return None
    episode_id = None if value is None else (str(value.get("episode_id") or "").strip() or None)
    display_name = None if value is None else (str(value.get("episode_display_name") or value.get("title_ar") or "").strip() or None)
    timing = suffix in SUBTITLE_SUFFIXES or (value is not None and _has_timing(value))
    if suffix == JSON_SUFFIX and episode_id is None and not timing:
        return None
    same_directory = path.parent == video_path.parent
    references_video = value is not None and _contains_video_reference(value, video_path)
    metadata_hash = None if value is None else value.get("source_episode_sha256", value.get("video_sha256"))
    hash_match = bool(video_sha and isinstance(metadata_hash, str) and metadata_hash.casefold() == video_sha.casefold())
    stem_match = path.stem.casefold() in {video_path.stem.casefold(), "metadata", "episode_metadata", "episode-manifest", "manifest"}
    if references_video or hash_match:
        score, relation = 100, "video-reference-or-hash"
    elif same_directory and timing:
        score, relation = 80, "same-directory-timed-package"
    elif same_directory and episode_id is not None:
        score, relation = 65, "same-directory-package"
    elif stem_match and episode_id is not None:
        score, relation = 40, "nearby-named-package"
    elif suffix in SUBTITLE_SUFFIXES and same_directory:
        score, relation = 60, "same-directory-transcript"
    else:
        score, relation = 0, "nearby-unverified"
    if score <= 0:
        return None
    return SourceCandidate(path, episode_id, display_name, timing, relation, score, (hash_match if metadata_hash else None), _format_modified(path))


def discover_episode_sources(
    video_path: Path,
    *,
    repo_root: Path | None = None,
) -> SourceDiscoveryResult:
    """Discover local metadata/timing related to one explicitly chosen video."""

    video = Path(video_path).resolve()
    video_sha = _sha256(video) if video.is_file() else None
    local_files = _iter_local_files(video)
    candidates = [item for path in local_files if (item := _candidate_for(path, video, video_sha=video_sha)) is not None]
    metadata = sorted((item for item in candidates if item.is_metadata), key=lambda item: (-item.relationship_score, str(item.path).casefold()))
    transcripts = sorted((item for item in candidates if item.is_timing and not item.is_metadata), key=lambda item: (-item.relationship_score, str(item.path).casefold()))
    stale_metadata = any(item.source_hash_match is False for item in metadata)
    matched_metadata = metadata[0] if len(metadata) == 1 and not stale_metadata else None
    if len(metadata) == 1 and metadata[0].has_timing:
        matched_transcript = None
    else:
        matched_transcript = transcripts[0] if len(transcripts) == 1 else None
    legacy_resolution: LegacyTimingResolution | None = None
    if (
        repo_root is not None
        and not stale_metadata
        and not (matched_metadata is not None and (matched_metadata.has_timing or matched_transcript is not None))
        and not (len(metadata) > 1)
    ):
        try:
            legacy_resolution = resolve_legacy_timing(repo_root, video)
        except LegacyTimingResolverError:
            legacy_resolution = None
    status = (
        "STALE_SOURCE"
        if stale_metadata
        else "READY"
        if legacy_resolution is not None
        or (matched_metadata is not None and (matched_metadata.has_timing or matched_transcript is not None))
        else "AMBIGUOUS"
        if len(metadata) > 1
        else "TRANSCRIPT_REQUIRED"
        if matched_metadata is not None
        else "METADATA_REQUIRED"
    )
    return SourceDiscoveryResult(
        video,
        tuple(metadata),
        tuple(transcripts),
        matched_metadata,
        matched_transcript,
        len(local_files),
        status,
        legacy_resolution,
    )


__all__ = [
    "SourceCandidate",
    "SourceDiscoveryResult",
    "SUBTITLE_SUFFIXES",
    "VIDEO_SUFFIXES",
    "discover_episode_sources",
]
