from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import textwrap
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

RELEASE = "SIRAJ_END_TO_END_PRODUCTION_AND_YOUTUBE_HANDOFF_V1"

ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
THUMBNAIL_POLICY_REL = Path(
    "projects/_orchestrator/contracts/thumbnail-era-policy-v1.json"
)
EPISODE_DEFINITION_REL = Path("contracts/episode-definition-v1.json")
APPROVED_SCOPE_REL = Path("contracts/approved-scope-v1.json")
EVIDENCE_REL = Path("research/evidence-package-v1.json")
SCRIPT_REL = Path("script/episode-script-v1.json")
STORYBOARD_REL = Path("cinematic/storyboard-and-media-plan-v1.json")
MEDIA_QUEUE_REL = Path("orchestration/media-production-queue-v1.json")
SFX_PLAN_REL = Path("audio/sfx/sfx-audio-plan-v1.json")
PUBLISH_ROOT_REL = Path("publishing/publish-package-v1")
PUBLISH_MANIFEST_REL = PUBLISH_ROOT_REL / "publish-manifest-v1.json"
YOUTUBE_METADATA_REL = PUBLISH_ROOT_REL / "youtube-metadata-v1.json"
TITLE_REL = PUBLISH_ROOT_REL / "youtube-title.txt"
DESCRIPTION_REL = PUBLISH_ROOT_REL / "youtube-description.txt"
TAGS_REL = PUBLISH_ROOT_REL / "youtube-tags.txt"
CHECKLIST_REL = PUBLISH_ROOT_REL / "manual-upload-checklist.md"
CHECKSUMS_REL = PUBLISH_ROOT_REL / "SHA256SUMS.txt"
ARCHIVE_REL = PUBLISH_ROOT_REL / "publish-metadata-v1.zip"
CHAPTERS_REL = PUBLISH_ROOT_REL / "youtube-chapters.txt"
SUBTITLES_REL = PUBLISH_ROOT_REL / "youtube-subtitles-ar.srt"
DISCLOSURE_REL = PUBLISH_ROOT_REL / "altered-content-disclosure-ar.txt"
UPLOAD_SHEET_REL = PUBLISH_ROOT_REL / "youtube-upload-sheet.md"
UPLOAD_MANIFEST_REL = PUBLISH_ROOT_REL / "youtube-upload-manifest-v1.json"
THUMBNAIL_ASSIGNMENT_REL = PUBLISH_ROOT_REL / "thumbnail-era-assignment-v1.json"
THUMBNAIL_COPY_REL = PUBLISH_ROOT_REL / "youtube-thumbnail.png"
YOUTUBE_STUDIO_SHORTCUT_REL = PUBLISH_ROOT_REL / "Open YouTube Studio.url"
FINAL_MASTER_REL = Path("deliverables/episode-master-v1.mp4")
FINAL_REVIEW_RUN_STATE_REL = Path(
    "orchestration/final-review-publish-package-state-v1.json"
)


class YouTubePublishHandoffError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class YouTubePublishHandoffResult:
    episode_id: str
    status: str
    package_root: Path
    upload_manifest_path: Path
    chapters_path: Path
    subtitles_path: Path
    upload_sheet_path: Path
    thumbnail_status: str
    thumbnail_path: Path | None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "package_root",
            "upload_manifest_path",
            "chapters_path",
            "subtitles_path",
            "upload_sheet_path",
            "thumbnail_path",
        ):
            value = payload[key]
            payload[key] = str(value) if value is not None else None
        return payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise YouTubePublishHandoffError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise YouTubePublishHandoffError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative(repo: Path, path: Path) -> str:
    return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return value
    return ()


def _active_episode(
    repo_root: Path,
    *,
    require_ready: bool,
) -> tuple[Path, str, Path, Path, dict[str, Any]]:
    repo = repo_root.resolve()
    state_path = repo / ORCHESTRATOR_STATE_REL
    if not state_path.is_file():
        raise YouTubePublishHandoffError("ORCHESTRATOR_STATE_REQUIRED")
    state = _read(state_path)
    episode_id = state.get("current_episode_id")
    if not isinstance(episode_id, str) or not episode_id.strip():
        raise YouTubePublishHandoffError("CURRENT_EPISODE_REQUIRED")
    episode_id = episode_id.strip()
    episode_root = repo / "projects" / episode_id
    if not episode_root.is_dir():
        raise YouTubePublishHandoffError("CURRENT_EPISODE_DIRECTORY_MISSING")
    if require_ready and str(state.get("status", "")) != "READY_TO_PUBLISH":
        raise YouTubePublishHandoffError(
            "READY_TO_PUBLISH_REQUIRED:" + str(state.get("status", ""))
        )
    return repo, episode_id, episode_root, state_path, state


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _format_chapter_time(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _format_srt_time(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _script_and_storyboard(episode_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    script_path = episode_root / SCRIPT_REL
    storyboard_path = episode_root / STORYBOARD_REL
    if not script_path.is_file():
        raise YouTubePublishHandoffError("SCRIPT_REQUIRED_FOR_YOUTUBE_ASSETS")
    if not storyboard_path.is_file():
        raise YouTubePublishHandoffError("STORYBOARD_REQUIRED_FOR_YOUTUBE_ASSETS")
    return _read(script_path), _read(storyboard_path)


def build_youtube_chapters(episode_root: Path) -> tuple[str, list[dict[str, Any]]]:
    script, storyboard = _script_and_storyboard(episode_root)
    shots = sorted(
        (
            dict(item)
            for item in _sequence(storyboard.get("shots"))
            if isinstance(item, Mapping)
        ),
        key=lambda item: int(item.get("queue_index", 0)),
    )
    segment_starts: dict[str, float] = {}
    cursor = 0.0
    for shot in shots:
        for segment_id in _sequence(shot.get("segment_ids")):
            segment_starts.setdefault(str(segment_id), cursor)
        cursor += float(shot.get("editorial_duration_seconds", 0.0))

    chapters: list[dict[str, Any]] = []
    fallback = 0.0
    for segment in _sequence(script.get("segments")):
        if not isinstance(segment, Mapping):
            continue
        segment_id = str(segment.get("segment_id", ""))
        title = _clean(segment.get("title_ar")) or segment_id or "فصل"
        start = float(segment_starts.get(segment_id, fallback))
        if chapters and start < chapters[-1]["start_seconds"] + 10.0:
            fallback += float(segment.get("estimated_duration_seconds", 0.0))
            continue
        chapters.append(
            {
                "segment_id": segment_id,
                "title_ar": title,
                "start_seconds": round(start, 3),
                "timecode": _format_chapter_time(start),
            }
        )
        fallback += float(segment.get("estimated_duration_seconds", 0.0))
    if not chapters:
        chapters = [
            {
                "segment_id": "INTRO",
                "title_ar": _clean(script.get("title_ar")) or "بداية الحلقة",
                "start_seconds": 0.0,
                "timecode": "00:00",
            }
        ]
    chapters[0]["start_seconds"] = 0.0
    chapters[0]["timecode"] = "00:00"
    text = "\n".join(
        f"{item['timecode']} {item['title_ar']}" for item in chapters
    ) + "\n"
    return text, chapters


def _queue_text_map(episode_root: Path) -> dict[str, str]:
    path = episode_root / MEDIA_QUEUE_REL
    if not path.is_file():
        return {}
    queue = _read(path)
    queues = queue.get("queues")
    if not isinstance(queues, Mapping):
        return {}
    result: dict[str, str] = {}
    for item in _sequence(queues.get("elevenlabs_tts")):
        if not isinstance(item, Mapping):
            continue
        queue_id = str(item.get("queue_id", ""))
        text = _clean(item.get("text_ar"))
        if queue_id and text:
            result[queue_id] = text
    return result


def _split_caption(text: str, width: int = 48) -> str:
    wrapped = textwrap.wrap(
        _clean(text),
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return "\n".join(wrapped) if wrapped else ""


def build_arabic_subtitles(episode_root: Path) -> tuple[str, int]:
    plan_path = episode_root / SFX_PLAN_REL
    if not plan_path.is_file():
        raise YouTubePublishHandoffError("SFX_AUDIO_PLAN_REQUIRED_FOR_SUBTITLES")
    plan = _read(plan_path)
    text_by_queue = _queue_text_map(episode_root)
    clips = sorted(
        (
            dict(item)
            for item in _sequence(plan.get("narration_clips"))
            if isinstance(item, Mapping)
        ),
        key=lambda item: float(item.get("start_seconds", 0.0)),
    )
    cues: list[str] = []
    cue_number = 0
    for clip in clips:
        queue_id = str(clip.get("queue_id", ""))
        text = text_by_queue.get(queue_id, "")
        if not text:
            continue
        start = float(clip.get("start_seconds", 0.0))
        end = float(clip.get("end_seconds", start))
        if end <= start:
            continue
        cue_number += 1
        cues.append(
            f"{cue_number}\n"
            f"{_format_srt_time(start)} --> {_format_srt_time(end)}\n"
            f"{_split_caption(text)}\n"
        )
    if not cues:
        raise YouTubePublishHandoffError("NO_NARRATION_CUES_FOR_SUBTITLES")
    return "\n".join(cues).rstrip() + "\n", cue_number


def _source_lines(episode_root: Path, maximum: int = 12) -> list[str]:
    path = episode_root / EVIDENCE_REL
    if not path.is_file():
        return []
    evidence = _read(path)
    result = []
    for source in _sequence(evidence.get("source_register")):
        if not isinstance(source, Mapping):
            continue
        title = _clean(source.get("title"))
        url = _clean(source.get("url"))
        if title and url.startswith(("http://", "https://")):
            result.append(f"– {title}: {url}")
        elif title:
            result.append(f"– {title}")
        if len(result) >= maximum:
            break
    return result


def suggest_complete_publish_metadata(repo_root: Path) -> dict[str, Any]:
    repo, episode_id, episode_root, _, _ = _active_episode(
        repo_root,
        require_ready=False,
    )
    del repo
    definition_path = episode_root / EPISODE_DEFINITION_REL
    scope_path = episode_root / APPROVED_SCOPE_REL
    definition = _read(definition_path) if definition_path.is_file() else {}
    scope = _read(scope_path) if scope_path.is_file() else {}
    script_path = episode_root / SCRIPT_REL
    script = _read(script_path) if script_path.is_file() else {}

    title = _clean(
        definition.get("working_title_ar")
        or scope.get("working_title_ar")
        or script.get("title_ar")
        or definition.get("title_ar")
        or episode_id
    )[:100]
    central_question = _clean(
        definition.get("central_question_ar")
        or scope.get("central_question_ar")
        or script.get("central_thesis_ar")
    )
    research_summary = ""
    evidence_path = episode_root / EVIDENCE_REL
    if evidence_path.is_file():
        research_summary = _clean(_read(evidence_path).get("research_summary_ar"))

    chapters_text = ""
    try:
        chapters_text, _ = build_youtube_chapters(episode_root)
    except YouTubePublishHandoffError:
        chapters_text = ""

    lines: list[str] = []
    if central_question:
        lines.append(central_question)
    if research_summary:
        lines.extend(["", research_summary])
    if chapters_text:
        lines.extend(["", "الفصول:", chapters_text.rstrip()])
    sources = _source_lines(episode_root)
    if sources:
        lines.extend(["", "المصادر الأساسية:", *sources])
    lines.extend(
        [
            "",
            "تنبيه بصري:",
            "تتضمن الحلقة مشاهد تاريخية معاد بناؤها رقميًا وباستخدام أدوات ذكاء اصطناعي للتوضيح البصري، وليست تسجيلات حقيقية للأحداث.",
            "",
            "إعداد وإنتاج: سراج التاريخ",
            "الموسيقى: لا تُستخدم موسيقى.",
            "المؤثرات: تصميم صوتي ومؤثرات مناسبة للمشهد.",
            "",
            "#سراج_التاريخ #التاريخ #وثائقي",
        ]
    )
    description = "\n".join(lines).strip()
    if len(description) > 5000:
        description = description[:4997].rstrip() + "..."
    return {
        "title": title,
        "description": description,
        "tags": ["سراج التاريخ", "وثائقي", "التاريخ", "التاريخ الإسلامي"],
        "visibility_preference": "PRIVATE",
        "language": "ar",
        "audience": "NOT_MADE_FOR_KIDS",
        "altered_content_disclosure": "YES",
    }


def _thumbnail_assignment(
    repo: Path,
    episode_id: str,
    episode_root: Path,
    package_root: Path,
) -> tuple[dict[str, Any], Path | None]:
    policy_path = repo / THUMBNAIL_POLICY_REL
    policy = _read(policy_path) if policy_path.is_file() else {
        "default_era_id": "UNASSIGNED",
        "eras": [],
        "custom_thumbnail_required_before_publication": False,
    }
    definition_path = episode_root / EPISODE_DEFINITION_REL
    definition = _read(definition_path) if definition_path.is_file() else {}
    era_id = _clean(
        definition.get("thumbnail_era_id")
        or definition.get("era_id")
        or policy.get("default_era_id")
        or "UNASSIGNED"
    )
    selected: Mapping[str, Any] | None = None
    for era in _sequence(policy.get("eras")):
        if isinstance(era, Mapping) and _clean(era.get("era_id")) == era_id:
            selected = era
            break
    source_path: Path | None = None
    if selected is not None:
        relative = _clean(selected.get("thumbnail_path_relative"))
        if relative:
            candidate = repo / relative
            if candidate.is_file():
                source_path = candidate
    copied: Path | None = None
    if source_path is not None:
        copied = package_root / THUMBNAIL_COPY_REL.name
        shutil.copy2(source_path, copied)
        status = "ERA_TEMPLATE_ATTACHED"
    else:
        status = "ERA_TEMPLATE_NOT_CONFIGURED"
    assignment = {
        "schema_version": "siraj-thumbnail-era-assignment-v1",
        "release": RELEASE,
        "episode_id": episode_id,
        "selection_policy": "STATIC_TEMPLATE_PER_HISTORICAL_ERA",
        "era_id": era_id,
        "status": status,
        "custom_thumbnail_required_before_publication": bool(
            policy.get("custom_thumbnail_required_before_publication", False)
        ),
        "source_path_relative": (
            _relative(repo, source_path) if source_path is not None else None
        ),
        "package_thumbnail_relative": (
            _relative(repo, copied) if copied is not None else None
        ),
        "design_deferred_by_creator": source_path is None,
        "created_at_utc": _now(),
    }
    return assignment, copied


def _append_checksum_entries(
    repo: Path,
    checksums_path: Path,
    paths: Sequence[Path],
) -> None:
    existing: dict[str, str] = {}
    if checksums_path.is_file():
        for line in checksums_path.read_text(encoding="utf-8-sig").splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                existing[parts[1].strip()] = parts[0].strip()
    for path in paths:
        if path.is_file():
            existing[_relative(repo, path)] = _sha256(path)
    text = "".join(
        f"{digest}  {relative}\n"
        for relative, digest in sorted(existing.items())
    )
    _write_text(checksums_path, text)


def _rebuild_archive(package_root: Path, archive_path: Path) -> None:
    members = [
        path
        for path in package_root.iterdir()
        if path.is_file()
        and path.name not in {
            archive_path.name,
            "publish-manifest-v1.json",
            "SHA256SUMS.txt",
        }
    ]
    temporary = archive_path.with_suffix(archive_path.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(members):
            bundle.write(path, path.name)
    os.replace(temporary, archive_path)


def _upload_sheet(
    *,
    episode_id: str,
    video_relative: str,
    title_relative: str,
    description_relative: str,
    tags_relative: str,
    chapters_relative: str,
    subtitles_relative: str,
    thumbnail_relative: str | None,
    thumbnail_status: str,
    visibility: str,
) -> str:
    thumbnail_line = (
        f"- Thumbnail: `{thumbnail_relative}`"
        if thumbnail_relative
        else "- Thumbnail: استخدم صورة YouTube التلقائية مؤقتًا؛ قالب الحقبة لم يُضف بعد."
    )
    return f"""# YouTube Manual Upload Sheet\n\nEpisode: `{episode_id}`\n\n## Exact files\n\n- Video: `{video_relative}`\n- Title: `{title_relative}`\n- Description: `{description_relative}`\n- Tags: `{tags_relative}`\n- Chapters: `{chapters_relative}`\n- Arabic subtitles: `{subtitles_relative}`\n{thumbnail_line}\n- Thumbnail status: `{thumbnail_status}`\n\n## YouTube settings\n\n- Initial visibility: `{visibility}`\n- Audience: **Not made for kids**\n- Video language: **Arabic**\n- Title and description language: **Arabic**\n- Altered/synthetic content disclosure: **Yes**\n- Category: review manually; Education is the default recommendation\n- Automatic upload: **forbidden**\n\n## Final sequence\n\n1. Open YouTube Studio from `Open YouTube Studio.url`.\n2. Upload the exact MP4 above.\n3. Paste title, description and tags from this folder.\n4. Upload the Arabic SRT file.\n5. Verify chapters in the description.\n6. Select the thumbnail if an era template is attached.\n7. Wait for HD processing and copyright checks.\n8. Watch the uploaded version while Private.\n9. Choose the intended visibility and press Publish manually.\n\nSIRAJ stores no YouTube credentials and makes zero YouTube API requests.\n"""


def can_complete_youtube_publish_handoff(repo_root: Path) -> bool:
    try:
        _, _, episode_root, _, state = _active_episode(
            repo_root,
            require_ready=False,
        )
    except YouTubePublishHandoffError:
        return False
    if str(state.get("status", "")) != "READY_TO_PUBLISH":
        return False
    required = (
        episode_root / PUBLISH_MANIFEST_REL,
        episode_root / YOUTUBE_METADATA_REL,
        episode_root / FINAL_MASTER_REL,
        episode_root / SCRIPT_REL,
        episode_root / STORYBOARD_REL,
        episode_root / MEDIA_QUEUE_REL,
        episode_root / SFX_PLAN_REL,
    )
    return all(path.is_file() for path in required)


def complete_youtube_publish_handoff(
    repo_root: Path,
) -> YouTubePublishHandoffResult:
    repo, episode_id, episode_root, state_path, state = _active_episode(
        repo_root,
        require_ready=True,
    )
    package_root = episode_root / PUBLISH_ROOT_REL
    manifest_path = episode_root / PUBLISH_MANIFEST_REL
    metadata_path = episode_root / YOUTUBE_METADATA_REL
    final_path = episode_root / FINAL_MASTER_REL
    for path, code in (
        (package_root, "PUBLISH_PACKAGE_REQUIRED"),
        (manifest_path, "PUBLISH_MANIFEST_REQUIRED"),
        (metadata_path, "YOUTUBE_METADATA_REQUIRED"),
        (final_path, "FINAL_MASTER_REQUIRED"),
    ):
        if not path.exists():
            raise YouTubePublishHandoffError(code)

    chapters_text, chapters = build_youtube_chapters(episode_root)
    subtitles_text, subtitle_count = build_arabic_subtitles(episode_root)
    chapters_path = episode_root / CHAPTERS_REL
    subtitles_path = episode_root / SUBTITLES_REL
    disclosure_path = episode_root / DISCLOSURE_REL
    upload_sheet_path = episode_root / UPLOAD_SHEET_REL
    upload_manifest_path = episode_root / UPLOAD_MANIFEST_REL
    assignment_path = episode_root / THUMBNAIL_ASSIGNMENT_REL
    shortcut_path = episode_root / YOUTUBE_STUDIO_SHORTCUT_REL

    description_path = episode_root / DESCRIPTION_REL
    description_text = (
        description_path.read_text(encoding="utf-8-sig").strip()
        if description_path.is_file()
        else ""
    )
    if chapters_text.strip() and chapters_text.strip() not in description_text:
        description_text = (
            description_text.rstrip()
            + ("\n\n" if description_text else "")
            + "الفصول:\n"
            + chapters_text.strip()
        )
        if len(description_text) > 5000:
            raise YouTubePublishHandoffError(
                "YOUTUBE_DESCRIPTION_EXCEEDS_LIMIT_AFTER_CHAPTERS"
            )
        _write_text(description_path, description_text + "\n")

    _write_text(chapters_path, chapters_text)
    _write_text(subtitles_path, subtitles_text)
    _write_text(
        disclosure_path,
        "نعم — تتضمن الحلقة مشاهد تاريخية معاد بناؤها رقميًا وباستخدام أدوات ذكاء اصطناعي، وليست تسجيلات حقيقية للأحداث.\n",
    )
    assignment, thumbnail_path = _thumbnail_assignment(
        repo,
        episode_id,
        episode_root,
        package_root,
    )
    _write(assignment_path, assignment)
    _write_text(
        shortcut_path,
        "[InternetShortcut]\nURL=https://studio.youtube.com\n",
    )

    metadata = _read(metadata_path)
    if description_text:
        metadata["description"] = description_text
    visibility = _clean(metadata.get("visibility_preference")) or "PRIVATE"
    metadata.update(
        {
            "language": "ar",
            "title_and_description_language": "ar",
            "audience_setting": "NOT_MADE_FOR_KIDS",
            "altered_content_disclosure": "YES",
            "category_recommendation": "EDUCATION_REVIEW_MANUALLY",
            "chapters_relative": _relative(repo, chapters_path),
            "subtitles_ar_relative": _relative(repo, subtitles_path),
            "thumbnail_assignment_relative": _relative(repo, assignment_path),
            "thumbnail_status": assignment["status"],
            "manual_upload_only": True,
            "youtube_api_requests": 0,
            "updated_at_utc": _now(),
        }
    )
    metadata.pop("metadata_sha256", None)
    metadata["metadata_sha256"] = hashlib.sha256(
        json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    _write(metadata_path, metadata)

    _write_text(
        upload_sheet_path,
        _upload_sheet(
            episode_id=episode_id,
            video_relative=_relative(repo, final_path),
            title_relative=_relative(repo, episode_root / TITLE_REL),
            description_relative=_relative(repo, episode_root / DESCRIPTION_REL),
            tags_relative=_relative(repo, episode_root / TAGS_REL),
            chapters_relative=_relative(repo, chapters_path),
            subtitles_relative=_relative(repo, subtitles_path),
            thumbnail_relative=(
                _relative(repo, thumbnail_path)
                if thumbnail_path is not None
                else None
            ),
            thumbnail_status=str(assignment["status"]),
            visibility=visibility,
        ),
    )

    upload_manifest = {
        "schema_version": "siraj-youtube-manual-upload-manifest-v1",
        "release": RELEASE,
        "episode_id": episode_id,
        "status": "READY_FOR_MANUAL_YOUTUBE_UPLOAD",
        "manual_upload_only": True,
        "automatic_upload": "FORBIDDEN",
        "youtube_api_requests": 0,
        "youtube_credentials_storage": "FORBIDDEN",
        "final_video": {
            "path_relative": _relative(repo, final_path),
            "sha256": _sha256(final_path),
            "bytes": final_path.stat().st_size,
        },
        "title_relative": _relative(repo, episode_root / TITLE_REL),
        "description_relative": _relative(repo, episode_root / DESCRIPTION_REL),
        "tags_relative": _relative(repo, episode_root / TAGS_REL),
        "chapters_relative": _relative(repo, chapters_path),
        "chapters_count": len(chapters),
        "subtitles_ar_relative": _relative(repo, subtitles_path),
        "subtitle_cue_count": subtitle_count,
        "altered_content_disclosure": "YES",
        "audience_setting": "NOT_MADE_FOR_KIDS",
        "language": "ar",
        "thumbnail": assignment,
        "upload_sheet_relative": _relative(repo, upload_sheet_path),
        "youtube_studio_shortcut_relative": _relative(repo, shortcut_path),
        "created_at_utc": _now(),
    }
    _write(upload_manifest_path, upload_manifest)

    archive_path = episode_root / ARCHIVE_REL
    _rebuild_archive(package_root, archive_path)
    checksums_path = episode_root / CHECKSUMS_REL
    handoff_files = [
        chapters_path,
        subtitles_path,
        disclosure_path,
        upload_sheet_path,
        upload_manifest_path,
        assignment_path,
        shortcut_path,
        metadata_path,
        archive_path,
    ]
    if thumbnail_path is not None:
        handoff_files.append(thumbnail_path)
    _append_checksum_entries(repo, checksums_path, handoff_files)

    manifest = _read(manifest_path)
    manifest["youtube_handoff"] = {
        "status": "READY_FOR_MANUAL_YOUTUBE_UPLOAD",
        "upload_manifest_relative": _relative(repo, upload_manifest_path),
        "upload_manifest_sha256": _sha256(upload_manifest_path),
        "chapters_relative": _relative(repo, chapters_path),
        "subtitles_ar_relative": _relative(repo, subtitles_path),
        "upload_sheet_relative": _relative(repo, upload_sheet_path),
        "thumbnail_status": assignment["status"],
        "thumbnail_relative": (
            _relative(repo, thumbnail_path)
            if thumbnail_path is not None
            else None
        ),
        "manual_upload_only": True,
        "youtube_api_requests": 0,
    }
    metadata_section = manifest.setdefault("metadata", {})
    if isinstance(metadata_section, dict):
        metadata_section["archive_relative"] = _relative(repo, archive_path)
        metadata_section["archive_sha256"] = _sha256(archive_path)
    manifest["updated_at_utc"] = _now()
    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    _write(manifest_path, manifest)

    state.update(
        {
            "status": "READY_TO_PUBLISH",
            "stage": "READY_TO_PUBLISH",
            "next_stage": "OPEN_YOUTUBE_STUDIO_AND_MANUAL_UPLOAD",
            "youtube_handoff_status": "READY_FOR_MANUAL_YOUTUBE_UPLOAD",
            "youtube_upload_manifest_path_relative": _relative(
                repo, upload_manifest_path
            ),
            "youtube_upload_manifest_sha256": _sha256(upload_manifest_path),
            "publish_package_manifest_sha256": _sha256(manifest_path),
            "manual_youtube_upload": True,
            "automatic_upload": "FORBIDDEN",
            "youtube_api_requests": 0,
            "updated_at_utc": _now(),
        }
    )
    _write(state_path, state)

    run_state_path = episode_root / FINAL_REVIEW_RUN_STATE_REL
    if run_state_path.is_file():
        run_state = _read(run_state_path)
        run_state.update(
            {
                "youtube_handoff_status": "READY_FOR_MANUAL_YOUTUBE_UPLOAD",
                "youtube_upload_manifest_path_relative": _relative(
                    repo, upload_manifest_path
                ),
                "youtube_upload_manifest_sha256": _sha256(
                    upload_manifest_path
                ),
                "youtube_api_requests": 0,
                "updated_at_utc": _now(),
            }
        )
        _write(run_state_path, run_state)

    return YouTubePublishHandoffResult(
        episode_id=episode_id,
        status="READY_FOR_MANUAL_YOUTUBE_UPLOAD",
        package_root=package_root,
        upload_manifest_path=upload_manifest_path,
        chapters_path=chapters_path,
        subtitles_path=subtitles_path,
        upload_sheet_path=upload_sheet_path,
        thumbnail_status=str(assignment["status"]),
        thumbnail_path=thumbnail_path,
    )


def load_youtube_handoff_status(repo_root: Path) -> dict[str, Any]:
    try:
        repo, episode_id, episode_root, _, state = _active_episode(
            repo_root,
            require_ready=False,
        )
    except YouTubePublishHandoffError as exc:
        return {"status": "NOT_READY", "ready": False, "last_error": str(exc)}
    upload_manifest_path = episode_root / UPLOAD_MANIFEST_REL
    package_root = episode_root / PUBLISH_ROOT_REL
    return {
        "episode_id": episode_id,
        "status": str(
            state.get("youtube_handoff_status")
            or state.get("status")
            or "UNKNOWN"
        ),
        "ready": (
            state.get("youtube_handoff_status")
            == "READY_FOR_MANUAL_YOUTUBE_UPLOAD"
            and upload_manifest_path.is_file()
        ),
        "package_root": str(package_root),
        "upload_manifest_path": str(upload_manifest_path),
        "chapters_path": str(episode_root / CHAPTERS_REL),
        "subtitles_path": str(episode_root / SUBTITLES_REL),
        "upload_sheet_path": str(episode_root / UPLOAD_SHEET_REL),
        "thumbnail_assignment_path": str(
            episode_root / THUMBNAIL_ASSIGNMENT_REL
        ),
        "youtube_studio_url": "https://studio.youtube.com",
        "manual_upload_only": True,
        "youtube_api_requests": 0,
        "repo_root": str(repo),
    }


def run_youtube_handoff_smoke_test(output_root: Path) -> dict[str, Any]:
    root = output_root.resolve() / "youtube-handoff-smoke"
    episode_id = "episode-999-smoke"
    episode_root = root / "projects" / episode_id
    package_root = episode_root / PUBLISH_ROOT_REL
    state_path = root / ORCHESTRATOR_STATE_REL
    state_path.parent.mkdir(parents=True, exist_ok=True)
    package_root.mkdir(parents=True, exist_ok=True)
    (episode_root / FINAL_MASTER_REL).parent.mkdir(parents=True, exist_ok=True)
    (episode_root / SCRIPT_REL).parent.mkdir(parents=True, exist_ok=True)
    (episode_root / STORYBOARD_REL).parent.mkdir(parents=True, exist_ok=True)
    (episode_root / SFX_PLAN_REL).parent.mkdir(parents=True, exist_ok=True)
    (episode_root / MEDIA_QUEUE_REL).parent.mkdir(parents=True, exist_ok=True)
    (episode_root / EPISODE_DEFINITION_REL).parent.mkdir(parents=True, exist_ok=True)

    _write(
        state_path,
        {
            "status": "READY_TO_PUBLISH",
            "stage": "READY_TO_PUBLISH",
            "current_episode_id": episode_id,
        },
    )
    final_path = episode_root / FINAL_MASTER_REL
    final_path.write_bytes(b"siraj-youtube-handoff-smoke-video")
    _write(
        episode_root / EPISODE_DEFINITION_REL,
        {
            "episode_id": episode_id,
            "working_title_ar": "حلقة اختبار سراج",
            "central_question_ar": "ما الذي تختبره هذه الحلقة؟",
        },
    )
    _write(
        episode_root / SCRIPT_REL,
        {
            "title_ar": "حلقة اختبار سراج",
            "segments": [
                {
                    "segment_id": "SEG-001",
                    "title_ar": "المقدمة",
                    "estimated_duration_seconds": 20,
                },
                {
                    "segment_id": "SEG-002",
                    "title_ar": "الموضوع",
                    "estimated_duration_seconds": 20,
                },
            ],
        },
    )
    _write(
        episode_root / STORYBOARD_REL,
        {
            "shots": [
                {
                    "queue_index": 1,
                    "segment_ids": ["SEG-001"],
                    "editorial_duration_seconds": 20,
                },
                {
                    "queue_index": 2,
                    "segment_ids": ["SEG-002"],
                    "editorial_duration_seconds": 20,
                },
            ]
        },
    )
    _write(
        episode_root / MEDIA_QUEUE_REL,
        {
            "queues": {
                "elevenlabs_tts": [
                    {
                        "queue_id": "TTS-001",
                        "text_ar": "هذا هو النص الأول للاختبار.",
                    },
                    {
                        "queue_id": "TTS-002",
                        "text_ar": "وهذا هو النص الثاني للاختبار.",
                    },
                ]
            }
        },
    )
    _write(
        episode_root / SFX_PLAN_REL,
        {
            "narration_clips": [
                {
                    "queue_id": "TTS-001",
                    "start_seconds": 0.25,
                    "end_seconds": 4.25,
                },
                {
                    "queue_id": "TTS-002",
                    "start_seconds": 20.25,
                    "end_seconds": 24.25,
                },
            ]
        },
    )
    _write(
        episode_root / PUBLISH_MANIFEST_REL,
        {
            "status": "READY_TO_PUBLISH",
            "metadata": {},
        },
    )
    _write(
        episode_root / YOUTUBE_METADATA_REL,
        {
            "title": "حلقة اختبار سراج",
            "description": "اختبار",
            "tags": ["سراج"],
            "visibility_preference": "PRIVATE",
        },
    )
    _write_text(episode_root / TITLE_REL, "حلقة اختبار سراج\n")
    _write_text(episode_root / DESCRIPTION_REL, "اختبار\n")
    _write_text(episode_root / TAGS_REL, "سراج\n")
    _write_text(episode_root / CHECKLIST_REL, "# Checklist\n")
    _write_text(episode_root / CHECKSUMS_REL, "")
    _write_text(episode_root / ARCHIVE_REL, "temporary")

    result = complete_youtube_publish_handoff(root)
    upload = _read(result.upload_manifest_path)
    return {
        "status": (
            "PASS"
            if upload.get("status") == "READY_FOR_MANUAL_YOUTUBE_UPLOAD"
            else "FAIL"
        ),
        "chapters_count": upload.get("chapters_count"),
        "subtitle_cue_count": upload.get("subtitle_cue_count"),
        "thumbnail_status": result.thumbnail_status,
        "manual_upload_only": upload.get("manual_upload_only"),
        "youtube_api_requests": upload.get("youtube_api_requests"),
        "upload_manifest_sha256": _sha256(result.upload_manifest_path),
    }
