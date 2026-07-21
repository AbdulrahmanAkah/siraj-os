from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


REPO = Path(r"C:\SIRAJ\Repositories\siraj-os")

TARGET_VIDEO = Path(
    r"C:\SIRAJ\Workspace\first-project"
    r"\exports\quality-gate-v4.mp4"
)

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


from scripts.project_progress.recorder import (
    atomic_write_json,
    atomic_write_text,
    record_milestone,
)


TEXT_EXTENSIONS = {
    ".py",
    ".ps1",
    ".bat",
    ".cmd",
    ".sh",
    ".json",
    ".jsonl",
    ".md",
    ".txt",
    ".log",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".csv",
    ".srt",
    ".vtt",
    ".ass",
}

MEDIA_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
    ".avi",
    ".m4v",
    ".wav",
    ".mp3",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}

EXCLUDED_DIRECTORIES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "site-packages",
    ".venv",
    "venv",
    "historical-fixture-venv-20260716",
    "Backups",
    "archive",
}

SEARCH_NEEDLES = (
    "quality-gate-v4",
    "quality-gate-v4.mp4",
    str(TARGET_VIDEO),
    str(TARGET_VIDEO).replace("\\", "/"),
)

FFMPEG_NEEDLES = (
    "ffmpeg",
    "ffprobe",
    "-filter_complex",
    "-vf ",
    "-af ",
    "subtitles=",
    "drawtext=",
    "libx264",
    "aac",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def decode_text(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""

    if not data:
        return ""

    for encoding in (
        "utf-8-sig",
        "utf-8",
        "utf-16",
        "cp1252",
    ):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue

    return data.decode(
        "utf-8",
        errors="ignore",
    )


def ffprobe(path: Path) -> dict[str, Any]:
    executable = shutil.which("ffprobe")

    if not executable:
        return {
            "available": False,
        }

    command = [
        executable,
        "-v",
        "error",
        "-show_entries",
        (
            "format=filename,format_name,duration,"
            "size,bit_rate:"
            "stream=index,codec_type,codec_name,"
            "width,height,r_frame_rate,"
            "sample_rate,channels"
        ),
        "-of",
        "json",
        str(path),
    ]

    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )

    if process.returncode != 0:
        return {
            "available": True,
            "status": "FAILED",
            "stderr": process.stderr[-2000:],
        }

    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError:
        return {
            "available": True,
            "status": "INVALID_JSON",
        }

    return {
        "available": True,
        "status": "PASS",
        **payload,
    }


def ffmpeg_environment() -> dict[str, Any]:
    executable = shutil.which("ffmpeg")
    probe = shutil.which("ffprobe")

    result = {
        "ffmpeg_path": executable,
        "ffprobe_path": probe,
    }

    if executable:
        process = subprocess.run(
            [executable, "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )

        result["version"] = (
            process.stdout.splitlines()[0]
            if process.stdout
            else ""
        )

    return result


def candidate_roots() -> list[Path]:
    roots = [
        Path(r"C:\SIRAJ\Workspace\first-project"),
        Path(r"C:\SIRAJ\Logs"),
        Path(r"C:\SIRAJ\Reports"),
        REPO,
    ]

    result = []
    seen = set()

    for root in roots:
        if not root.exists():
            continue

        try:
            key = str(root.resolve()).lower()
        except OSError:
            key = str(root).lower()

        if key in seen:
            continue

        seen.add(key)
        result.append(root)

    return result


def powershell_history_files() -> list[Path]:
    paths = []

    appdata = os.environ.get("APPDATA")

    if appdata:
        paths.append(
            Path(appdata)
            / "Microsoft"
            / "Windows"
            / "PowerShell"
            / "PSReadLine"
            / "ConsoleHost_history.txt"
        )

    user_profile = os.environ.get("USERPROFILE")

    if user_profile:
        paths.append(
            Path(user_profile)
            / "AppData"
            / "Roaming"
            / "Microsoft"
            / "Windows"
            / "PowerShell"
            / "PSReadLine"
            / "ConsoleHost_history.txt"
        )

    unique = []
    seen = set()

    for path in paths:
        key = str(path).lower()

        if path.is_file() and key not in seen:
            seen.add(key)
            unique.append(path)

    return unique


def collect_files() -> list[Path]:
    collected = []
    seen = set()

    for root in candidate_roots():
        for current, directories, files in os.walk(root):
            directories[:] = [
                directory
                for directory in directories
                if directory not in EXCLUDED_DIRECTORIES
            ]

            for filename in files:
                path = Path(current) / filename
                suffix = path.suffix.lower()

                if (
                    suffix not in TEXT_EXTENSIONS
                    and suffix not in MEDIA_EXTENSIONS
                ):
                    continue

                try:
                    resolved = str(path.resolve()).lower()
                except OSError:
                    resolved = str(path).lower()

                if resolved in seen:
                    continue

                seen.add(resolved)
                collected.append(path)

    return collected


def search_text_files(
    files: list[Path],
    target_timestamp: float,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    exact_references = []
    ffmpeg_references = []

    for path in files:
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue

        try:
            stat = path.stat()
        except OSError:
            continue

        if stat.st_size > 8 * 1024 * 1024:
            continue

        text = decode_text(path)

        if not text:
            continue

        lowered = text.lower()

        exact_hits = [
            needle
            for needle in SEARCH_NEEDLES
            if needle.lower() in lowered
        ]

        ffmpeg_hits = [
            needle
            for needle in FFMPEG_NEEDLES
            if needle.lower() in lowered
        ]

        if exact_hits:
            matching_lines = [
                {
                    "line_number": index,
                    "text": line.strip()[:1000],
                }
                for index, line in enumerate(
                    text.splitlines(),
                    start=1,
                )
                if any(
                    needle.lower() in line.lower()
                    for needle in SEARCH_NEEDLES
                )
            ][:30]

            exact_references.append(
                {
                    "path": str(path),
                    "modified_at": datetime.fromtimestamp(
                        stat.st_mtime,
                        timezone.utc,
                    ).isoformat(),
                    "seconds_from_target": (
                        stat.st_mtime
                        - target_timestamp
                    ),
                    "hits": exact_hits,
                    "matching_lines": matching_lines,
                }
            )

        if ffmpeg_hits:
            distance = abs(
                stat.st_mtime
                - target_timestamp
            )

            if (
                distance <= 7 * 24 * 60 * 60
                or exact_hits
            ):
                matching_lines = [
                    {
                        "line_number": index,
                        "text": line.strip()[:1000],
                    }
                    for index, line in enumerate(
                        text.splitlines(),
                        start=1,
                    )
                    if any(
                        needle.lower() in line.lower()
                        for needle in FFMPEG_NEEDLES
                    )
                ][:50]

                ffmpeg_references.append(
                    {
                        "path": str(path),
                        "modified_at": datetime.fromtimestamp(
                            stat.st_mtime,
                            timezone.utc,
                        ).isoformat(),
                        "seconds_from_target": (
                            stat.st_mtime
                            - target_timestamp
                        ),
                        "hits": ffmpeg_hits,
                        "matching_lines": matching_lines,
                    }
                )

    exact_references.sort(
        key=lambda item: (
            abs(item["seconds_from_target"]),
            item["path"],
        )
    )

    ffmpeg_references.sort(
        key=lambda item: (
            abs(item["seconds_from_target"]),
            item["path"],
        )
    )

    return exact_references, ffmpeg_references


def collect_nearby_files(
    files: list[Path],
    target_timestamp: float,
) -> list[dict[str, Any]]:
    nearby = []

    before_seconds = 24 * 60 * 60
    after_seconds = 2 * 60 * 60

    for path in files:
        if path == TARGET_VIDEO:
            continue

        try:
            stat = path.stat()
        except OSError:
            continue

        delta = stat.st_mtime - target_timestamp

        if (
            delta < -before_seconds
            or delta > after_seconds
        ):
            continue

        nearby.append(
            {
                "path": str(path),
                "extension": path.suffix.lower(),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(
                    stat.st_mtime,
                    timezone.utc,
                ).isoformat(),
                "seconds_from_target": delta,
                "kind": (
                    "MEDIA"
                    if path.suffix.lower()
                    in MEDIA_EXTENSIONS
                    else "TEXT"
                ),
            }
        )

    nearby.sort(
        key=lambda item: (
            abs(item["seconds_from_target"]),
            item["path"],
        )
    )

    return nearby[:200]


def search_history() -> list[dict[str, Any]]:
    results = []

    for path in powershell_history_files():
        text = decode_text(path)
        lines = text.splitlines()

        for index, line in enumerate(
            lines,
            start=1,
        ):
            lowered = line.lower()

            if (
                "quality-gate-v4" in lowered
                or (
                    "ffmpeg" in lowered
                    and "first-project" in lowered
                )
            ):
                results.append(
                    {
                        "path": str(path),
                        "line_number": index,
                        "text": line.strip(),
                    }
                )

    return results[-100:]


def build_markdown(
    report: dict[str, Any],
) -> str:
    lines = [
        "# quality-gate-v4 Render Lineage Audit",
        "",
        f"- Status: {report['status']}",
        f"- Confidence: {report['lineage_confidence']}",
        f"- Target: `{report['target']['path']}`",
        f"- SHA-256: `{report['target']['sha256']}`",
        f"- Exact references: {len(report['exact_references'])}",
        f"- FFmpeg-related references: {len(report['ffmpeg_references'])}",
        f"- PowerShell history matches: {len(report['history_matches'])}",
        f"- Nearby candidate files: {len(report['nearby_files'])}",
        "",
        "## Interpretation",
        "",
        report["interpretation"],
        "",
        "## Exact references",
        "",
    ]

    if not report["exact_references"]:
        lines.append("- None found.")

    for item in report["exact_references"][:20]:
        lines.append(f"- `{item['path']}`")

        for match in item["matching_lines"][:5]:
            lines.append(
                f"  - L{match['line_number']}: "
                f"`{match['text']}`"
            )

    lines.extend(
        [
            "",
            "## PowerShell history",
            "",
        ]
    )

    if not report["history_matches"]:
        lines.append("- None found.")

    for item in report["history_matches"][-30:]:
        lines.append(
            f"- `{item['path']}` L{item['line_number']}: "
            f"`{item['text']}`"
        )

    lines.extend(
        [
            "",
            "## Closest candidate files",
            "",
        ]
    )

    for item in report["nearby_files"][:50]:
        lines.append(
            "- "
            f"`{item['path']}` — "
            f"{item['seconds_from_target']:+.1f}s"
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

    return "\n".join(lines)


def main() -> int:
    if not TARGET_VIDEO.is_file():
        raise RuntimeError(
            f"TARGET_VIDEO_NOT_FOUND:{TARGET_VIDEO}"
        )

    target_stat = TARGET_VIDEO.stat()
    target_timestamp = target_stat.st_mtime

    files = collect_files()

    exact_references, ffmpeg_references = (
        search_text_files(
            files,
            target_timestamp,
        )
    )

    nearby_files = collect_nearby_files(
        files,
        target_timestamp,
    )

    history_matches = search_history()

    exact_history = [
        item
        for item in history_matches
        if "quality-gate-v4" in item["text"].lower()
    ]

    if exact_history or exact_references:
        confidence = "HIGH"
        status = "LINEAGE_REFERENCES_FOUND"
        interpretation = (
            "Direct references to the target render were found. "
            "These references should be converted into the first "
            "reproducible render manifest and adapter."
        )

    elif ffmpeg_references and nearby_files:
        confidence = "MEDIUM"
        status = "PROBABLE_LINEAGE_FOUND"
        interpretation = (
            "No direct target reference was found, but FFmpeg-related "
            "files and timestamp-adjacent assets were located. "
            "The render recipe can likely be reconstructed."
        )

    else:
        confidence = "LOW"
        status = "LINEAGE_NOT_YET_RESOLVED"
        interpretation = (
            "The video is confirmed, but its producing command or "
            "manifest was not found in the searched locations. "
            "A clean reproducible adapter must be built from the "
            "confirmed media inputs."
        )

    report = {
        "schema_version": (
            "siraj-render-lineage-audit-v1"
        ),
        "generated_at": utc_now(),
        "status": status,
        "lineage_confidence": confidence,
        "target": {
            "path": str(TARGET_VIDEO),
            "size_bytes": target_stat.st_size,
            "modified_at": datetime.fromtimestamp(
                target_timestamp,
                timezone.utc,
            ).isoformat(),
            "sha256": sha256_file(TARGET_VIDEO),
            "ffprobe": ffprobe(TARGET_VIDEO),
        },
        "ffmpeg_environment": ffmpeg_environment(),
        "searched_roots": [
            str(root)
            for root in candidate_roots()
        ],
        "scanned_file_count": len(files),
        "exact_references": exact_references,
        "ffmpeg_references": ffmpeg_references,
        "history_matches": history_matches,
        "nearby_files": nearby_files,
        "interpretation": interpretation,
        "next_action": (
            "Build render-adapter-v1 from the highest-confidence "
            "command, script, manifest, and input candidates found "
            "by this audit."
        ),
    }

    artifact_root = (
        REPO
        / "artifacts"
        / "fast-track"
    )

    json_path = (
        artifact_root
        / "quality-gate-v4-lineage.json"
    )

    markdown_path = (
        artifact_root
        / "quality-gate-v4-lineage.md"
    )

    atomic_write_json(
        json_path,
        report,
    )

    atomic_write_text(
        markdown_path,
        build_markdown(report),
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
            "2026-07-21-quality-gate-v4-lineage-audit"
        ),
        title_ar=(
            "\u062a\u062f\u0642\u064a\u0642 "
            "\u0645\u0633\u0627\u0631 "
            "\u0625\u0646\u062a\u0627\u062c "
            "quality-gate-v4.mp4"
        ),
        status=(
            "COMPLETED"
            if confidence in {"HIGH", "MEDIUM"}
            else "COMPLETED_WITH_LIMITATIONS"
        ),
        summary_ar=(
            "\u062a\u0645 \u0641\u062d\u0635 "
            "\u0627\u0644\u0641\u064a\u062f\u064a\u0648 "
            "\u0627\u0644\u062a\u062c\u0631\u064a\u0628\u064a "
            "\u0648\u0627\u0644\u0628\u062d\u062b "
            "\u0639\u0646 \u0627\u0644\u0623\u0648\u0627\u0645\u0631 "
            "\u0648\u0627\u0644\u0633\u0643\u0631\u0628\u062a\u0627\u062a "
            "\u0648\u0627\u0644\u0645\u0644\u0641\u0627\u062a "
            "\u0627\u0644\u062a\u064a \u0623\u0646\u062a\u062c\u062a\u0647. "
            f"\u062f\u0631\u062c\u0629 \u0627\u0644\u062b\u0642\u0629: "
            f"{confidence}."
        ),
        next_action_ar=(
            "\u0628\u0646\u0627\u0621 "
            "render-adapter-v1 "
            "\u0645\u0646 \u0623\u0639\u0644\u0649 "
            "\u0627\u0644\u0645\u0631\u0634\u062d\u0627\u062a "
            "\u062b\u0642\u0629\u060c \u062b\u0645 "
            "\u0625\u0639\u0627\u062f\u0629 "
            "\u0625\u0646\u062a\u0627\u062c "
            "\u0645\u0642\u0637\u0639 \u0645\u0637\u0627\u0628\u0642 "
            "\u0645\u0646 manifest \u0645\u062d\u0641\u0648\u0638."
        ),
        changed_files=[
            (
                "artifacts/fast-track/"
                "quality-gate-v4-lineage.json"
            ),
            (
                "artifacts/fast-track/"
                "quality-gate-v4-lineage.md"
            ),
            "PROJECT_PROGRESS.md",
        ],
        metadata={
            "status": status,
            "lineage_confidence": confidence,
            "exact_reference_count": len(
                exact_references
            ),
            "ffmpeg_reference_count": len(
                ffmpeg_references
            ),
            "history_match_count": len(
                history_matches
            ),
            "nearby_file_count": len(
                nearby_files
            ),
            "target_sha256": report[
                "target"
            ]["sha256"],
        },
    )

    summary = {
        "status": status,
        "lineage_confidence": confidence,
        "scanned_file_count": len(files),
        "exact_reference_count": len(
            exact_references
        ),
        "ffmpeg_reference_count": len(
            ffmpeg_references
        ),
        "history_match_count": len(
            history_matches
        ),
        "nearby_file_count": len(
            nearby_files
        ),
        "target_sha256": report[
            "target"
        ]["sha256"],
        "json_report": str(json_path),
        "markdown_report": str(markdown_path),
    }

    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())