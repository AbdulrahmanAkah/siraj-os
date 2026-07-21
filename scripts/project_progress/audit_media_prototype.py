from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


REPO = Path(__file__).resolve().parents[2]

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


from scripts.project_progress.recorder import (
    atomic_write_json,
    atomic_write_text,
    record_milestone,
)


VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
    ".avi",
    ".m4v",
}

AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
}

SUBTITLE_EXTENSIONS = {
    ".srt",
    ".vtt",
    ".ass",
}

EXCLUDED_DIRECTORIES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "site-packages",
    "dist",
    "build",
    ".venv",
    "venv",
    "historical-fixture-venv-20260716",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def scan_roots() -> list[Path]:
    candidates = [
        Path(r"C:\SIRAJ\Workspace"),
        Path(r"C:\SIRAJ\Outputs"),
        Path(r"C:\SIRAJ\Output"),
        Path(r"C:\SIRAJ\Artifacts"),
        REPO / "outputs",
        REPO / "output",
        REPO / "artifacts",
        REPO,
    ]

    result = []
    seen = set()

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate

        key = str(resolved).lower()

        if candidate.exists() and key not in seen:
            seen.add(key)
            result.append(candidate)

    return result


def scan_media() -> list[dict[str, Any]]:
    discovered: dict[str, dict[str, Any]] = {}

    accepted = (
        VIDEO_EXTENSIONS
        | AUDIO_EXTENSIONS
        | SUBTITLE_EXTENSIONS
    )

    for root in scan_roots():
        for current, directories, files in os.walk(root):
            directories[:] = [
                directory
                for directory in directories
                if directory not in EXCLUDED_DIRECTORIES
                and not directory.startswith(".tox")
            ]

            for filename in files:
                path = Path(current) / filename
                suffix = path.suffix.lower()

                if suffix not in accepted:
                    continue

                try:
                    stat = path.stat()
                except OSError:
                    continue

                key = str(path.resolve()).lower()

                kind = (
                    "VIDEO"
                    if suffix in VIDEO_EXTENSIONS
                    else "AUDIO"
                    if suffix in AUDIO_EXTENSIONS
                    else "SUBTITLE"
                )

                discovered[key] = {
                    "path": str(path),
                    "kind": kind,
                    "extension": suffix,
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(
                        stat.st_mtime,
                        timezone.utc,
                    ).isoformat(),
                    "modified_timestamp": stat.st_mtime,
                }

    items = list(discovered.values())

    items.sort(
        key=lambda item: (
            item["modified_timestamp"],
            item["path"],
        ),
        reverse=True,
    )

    return items


def ffprobe_details(path: Path) -> dict[str, Any]:
    executable = shutil.which("ffprobe")

    if not executable:
        return {
            "ffprobe_available": False,
        }

    command = [
        executable,
        "-v",
        "error",
        "-show_entries",
        (
            "format=duration:"
            "stream=index,codec_type,codec_name,"
            "width,height,sample_rate,channels"
        ),
        "-of",
        "json",
        str(path),
    ]

    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )

    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "ffprobe_available": True,
            "probe_status": "FAILED",
            "error": type(error).__name__,
        }

    if process.returncode != 0:
        return {
            "ffprobe_available": True,
            "probe_status": "FAILED",
            "stderr": process.stderr[-2000:],
        }

    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError:
        return {
            "ffprobe_available": True,
            "probe_status": "INVALID_JSON",
        }

    streams = payload.get("streams", [])

    video_streams = [
        stream
        for stream in streams
        if stream.get("codec_type") == "video"
    ]

    audio_streams = [
        stream
        for stream in streams
        if stream.get("codec_type") == "audio"
    ]

    duration_value = (
        payload.get("format", {})
        .get("duration")
    )

    try:
        duration_seconds = float(duration_value)
    except (TypeError, ValueError):
        duration_seconds = None

    return {
        "ffprobe_available": True,
        "probe_status": "PASS",
        "duration_seconds": duration_seconds,
        "has_video_stream": bool(video_streams),
        "has_audio_stream": bool(audio_streams),
        "video_streams": video_streams,
        "audio_streams": audio_streams,
    }


def patch_legacy_progress_status() -> None:
    path = REPO / "PROJECT_PROGRESS.md"
    text = path.read_text(encoding="utf-8-sig")

    replacements = {
        "Voice ................... 0%": (
            "Voice ................... "
            "PROTOTYPE WORKING "
            "(temporary narration)"
        ),
        "Video ................... 0%": (
            "Video ................... "
            "PROTOTYPE WORKING "
            "(short experimental clip)"
        ),
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    atomic_write_text(path, text)


def update_readiness(
    audit: dict[str, Any],
) -> None:
    json_path = (
        REPO
        / "artifacts"
        / "fast-track"
        / "pipeline-readiness.json"
    )

    markdown_path = (
        REPO
        / "artifacts"
        / "fast-track"
        / "pipeline-readiness.md"
    )

    if json_path.is_file():
        report = json.loads(
            json_path.read_text(encoding="utf-8-sig")
        )
    else:
        report = {
            "schema_version": "siraj-fast-track-readiness-v1",
            "stage_status": {},
        }

    report.setdefault(
        "stage_status",
        {},
    )

    report["stage_status"][
        "media_execution"
    ] = "PROTOTYPE_WORKING"

    report["stage_status"][
        "publishable_media_execution"
    ] = "BLOCKED"

    report.setdefault(
        "document_signals",
        {},
    )

    report["document_signals"].update(
        {
            "experimental_video_confirmed": True,
            "local_video_artifact_located": (
                audit["video_count"] > 0
            ),
            "temporary_voiceover_detected": (
                audit.get(
                    "latest_video_probe",
                    {},
                ).get(
                    "has_audio_stream"
                )
            ),
            "reusable_voice_adapter_validated": False,
            "reproducible_render_adapter_validated": False,
        }
    )

    report["immediate_blockers"] = [
        (
            "The video prototype exists, but the reusable and "
            "reproducible render adapter is not yet validated."
        ),
        (
            "Temporary narration exists, but the production voice "
            "adapter and quality profile are not yet validated."
        ),
        (
            "The visual asset execution path is not yet validated "
            "for repeatable episode production."
        ),
        (
            "Episode 001 source pack is not populated or reviewed."
        ),
    ]

    report["next_action"] = (
        "Convert the confirmed short-video prototype into a "
        "reproducible render path while populating the reviewed "
        "Episode 001 source pack."
    )

    report["media_prototype_audit"] = audit

    atomic_write_json(
        json_path,
        report,
    )

    stage = report["stage_status"]

    lines = [
        "# SIRAJ Fast-Track Readiness",
        "",
        (
            "- Knowledge foundation: "
            f"{stage.get('knowledge_foundation', 'UNKNOWN')}"
        ),
        (
            "- Documentary logic: "
            f"{stage.get('documentary_logic', 'UNKNOWN')}"
        ),
        "- Media execution: PROTOTYPE_WORKING",
        "- Publishable media execution: BLOCKED",
        (
            "- First episode: "
            f"{stage.get('first_episode', 'STARTED')}"
        ),
        "",
        "## Confirmed progress",
        "",
        (
            "- A short experimental video was produced with "
            "simple editing and temporary narration."
        ),
        (
            f"- Local video artifacts located: "
            f"{audit['video_count']}"
        ),
        "",
        "## Immediate blockers",
        "",
    ]

    lines.extend(
        f"- {blocker}"
        for blocker in report["immediate_blockers"]
    )

    lines.extend(
        [
            "",
            "## Next action",
            "",
            report["next_action"],
            "",
        ]
    )

    atomic_write_text(
        markdown_path,
        "\n".join(lines),
    )


def main() -> int:
    media = scan_media()

    videos = [
        item
        for item in media
        if item["kind"] == "VIDEO"
    ]

    audios = [
        item
        for item in media
        if item["kind"] == "AUDIO"
    ]

    subtitles = [
        item
        for item in media
        if item["kind"] == "SUBTITLE"
    ]

    latest_video = (
        videos[0]
        if videos
        else None
    )

    latest_probe = (
        ffprobe_details(
            Path(latest_video["path"])
        )
        if latest_video
        else {
            "ffprobe_available": (
                shutil.which("ffprobe") is not None
            ),
            "probe_status": "NO_VIDEO_LOCATED",
        }
    )

    audit = {
        "schema_version": "siraj-media-prototype-audit-v1",
        "generated_at": utc_now(),
        "user_confirmed_video_prototype": True,
        "status": (
            "CONFIRMED_BY_LOCAL_ARTIFACT"
            if videos
            else "USER_CONFIRMED_ARTIFACT_NOT_LOCATED"
        ),
        "video_pipeline_status": "PROTOTYPE_WORKING",
        "publishable_pipeline_status": "BLOCKED",
        "video_count": len(videos),
        "audio_count": len(audios),
        "subtitle_count": len(subtitles),
        "latest_video": latest_video,
        "latest_video_probe": latest_probe,
        "recent_media": media[:30],
        "limitations": [
            "Editing quality is still minimal.",
            "Narration is temporary.",
            "Repeatable production adapter is not yet validated.",
            "Publishable-quality verification is not yet complete.",
        ],
    }

    artifact_root = (
        REPO
        / "artifacts"
        / "fast-track"
    )

    atomic_write_json(
        artifact_root
        / "media-prototype-audit.json",
        audit,
    )

    markdown = [
        "# Media Prototype Audit",
        "",
        f"- Status: {audit['status']}",
        "- Video pipeline: PROTOTYPE_WORKING",
        "- Publishable pipeline: BLOCKED",
        f"- Videos found: {len(videos)}",
        f"- Audio files found: {len(audios)}",
        f"- Subtitle files found: {len(subtitles)}",
        "",
    ]

    if latest_video:
        markdown.extend(
            [
                "## Latest video",
                "",
                f"- Path: `{latest_video['path']}`",
                f"- Size: {latest_video['size_bytes']} bytes",
                f"- Modified: {latest_video['modified_at']}",
                (
                    "- Audio stream detected: "
                    f"{latest_probe.get('has_audio_stream')}"
                ),
                (
                    "- Duration seconds: "
                    f"{latest_probe.get('duration_seconds')}"
                ),
                "",
            ]
        )

    markdown.extend(
        [
            "## Current interpretation",
            "",
            (
                "The project has crossed the initial media threshold: "
                "a video prototype exists. The remaining work is to "
                "make the path reproducible, higher quality, verified, "
                "and episode-driven."
            ),
            "",
        ]
    )

    atomic_write_text(
        artifact_root
        / "media-prototype-audit.md",
        "\n".join(markdown),
    )

    patch_legacy_progress_status()
    update_readiness(audit)

    evidence = []

    if latest_video:
        evidence.append(
            {
                "type": "LOCAL_VIDEO_ARTIFACT",
                "path": latest_video["path"],
                "size_bytes": latest_video["size_bytes"],
                "probe": latest_probe,
            }
        )
    else:
        evidence.append(
            {
                "type": "USER_CONFIRMED_MILESTONE",
                "statement": (
                    "A short experimental video with simple editing "
                    "and temporary narration was previously produced."
                ),
            }
        )

    record_milestone(
        project_progress_path=(
            REPO / "PROJECT_PROGRESS.md"
        ),
        ledger_path=(
            REPO
            / "docs"
            / "execution"
            / "project-milestones.json"
        ),
        milestone_id=(
            "2026-07-21-media-video-prototype"
        ),
        title_ar=(
            "إثبات عمل خط إنتاج الفيديو مبدئيًا"
        ),
        status="COMPLETED_WITH_LIMITATIONS",
        summary_ar=(
            "تم إنتاج مقطع فيديو قصير تجريبي بمونتاج بسيط جدًا "
            "وتعليق صوتي مؤقت. هذا يثبت أن مسار إنتاج الفيديو "
            "يعمل مبدئيًا، لكنه لم يصل بعد إلى جودة النشر أو "
            "التشغيل القابل للتكرار."
        ),
        next_action_ar=(
            "تحويل النموذج التجريبي إلى مسار Render قابل لإعادة "
            "التشغيل، مع تحسين الصوت والمونتاج وربطه بحزمة مصادر "
            "وأدلة الحلقة الأولى."
        ),
        changed_files=[
            "PROJECT_PROGRESS.md",
            "artifacts/fast-track/pipeline-readiness.json",
            "artifacts/fast-track/media-prototype-audit.json",
        ],
        evidence=evidence,
        metadata={
            "video_count": len(videos),
            "audio_count": len(audios),
            "subtitle_count": len(subtitles),
        },
    )

    record_milestone(
        project_progress_path=(
            REPO / "PROJECT_PROGRESS.md"
        ),
        ledger_path=(
            REPO
            / "docs"
            / "execution"
            / "project-milestones.json"
        ),
        milestone_id=(
            "2026-07-21-progress-automation-installed"
        ),
        title_ar=(
            "تثبيت التحديث الآلي لسجل تقدم المشروع"
        ),
        status="COMPLETED",
        summary_ar=(
            "أصبح PROJECT_PROGRESS.md مرتبطًا بسجل milestones "
            "منظم، ويمكن تحديثه آليًا من مشغلات المراحل الكبيرة، "
            "مع Git hook يمنع نسيان التحديث عند الـcommit."
        ),
        next_action_ar=(
            "ربط جميع مشغلات الحلقة الأولى ومسار الوسائط بمسجل "
            "التقدم، ثم بدء تثبيت مسار الفيديو القابل للتكرار."
        ),
        changed_files=[
            "PROJECT_PROGRESS.md",
            "docs/execution/project-milestones.json",
            "scripts/project_progress/recorder.py",
        ],
    )

    print(
        json.dumps(
            {
                "status": audit["status"],
                "video_pipeline_status": (
                    audit["video_pipeline_status"]
                ),
                "video_count": len(videos),
                "audio_count": len(audios),
                "subtitle_count": len(subtitles),
                "latest_video": (
                    latest_video["path"]
                    if latest_video
                    else None
                ),
                "latest_video_probe": latest_probe,
                "audit": str(
                    artifact_root
                    / "media-prototype-audit.json"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
