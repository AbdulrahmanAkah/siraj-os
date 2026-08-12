"""V6.2.1 montage: video + locally animated stills, duplicate-safe."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from src.application.siraj_final_tts_queue_selector_v6_3_2 import resolve_final_tts_queue_path
import shutil
import subprocess
from typing import Mapping

# SIRAJ_MONTAGE_TRUE_TELEMETRY_V6_6_R9
from src.application.siraj_live_telemetry_v6_6_r9 import emit_event
from src.application.siraj_duplicate_gates_v6_2_1 import (
    audit_completed_assets,
)


class MontageV621Error(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise MontageV621Error(
            "JSON_OBJECT_REQUIRED:" + str(path)
        )
    return value


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)
    return digest.hexdigest()


def _exe(name, env_name):
    configured = os.environ.get(
        env_name,
        "",
    ).strip()
    if configured and Path(configured).is_file():
        return Path(configured)
    found = shutil.which(name)
    if not found:
        raise MontageV621Error(
            name.upper() + "_NOT_AVAILABLE"
        )
    return Path(found)


def _run(args):
    process = subprocess.run(
        [str(x) for x in args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if process.returncode:
        raise MontageV621Error(
            "COMMAND_FAILED:"
            + " ".join(str(x) for x in args)
            + "\n"
            + process.stderr[-4000:]
        )
    return process


def _duration(path):
    result = _run(
        [
            _exe(
                "ffprobe",
                "SIRAJ_FFPROBE_EXE",
            ),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ]
    )
    try:
        return float(result.stdout.strip())
    except ValueError as exc:
        raise MontageV621Error(
            "DURATION_INVALID:" + str(path)
        ) from exc


def _build_narration(repo, tts, output):
    items = sorted(
        tts["items"],
        key=lambda x: int(
            x.get("queue_index", 0) or 0
        ),
    )
    inputs = []
    filters = []
    labels = []
    input_index = 0

    for index, item in enumerate(items):
        if item.get("status") != "COMPLETE":
            raise MontageV621Error(
                "FINAL_TTS_NOT_COMPLETE:"
                + str(item.get("queue_id"))
            )
        path = repo / str(
            item.get("output_path_relative") or ""
        )
        if not path.is_file():
            raise MontageV621Error(
                "TTS_AUDIO_MISSING:" + str(path)
            )

        inputs.extend(["-i", path])
        label = f"a{index}"
        filters.append(
            f"[{input_index}:a]"
            "aformat=sample_rates=48000:"
            "channel_layouts=stereo,"
            "asetpts=PTS-STARTPTS"
            f"[{label}]"
        )
        labels.append(f"[{label}]")
        input_index += 1

        pause = float(
            item.get("pause_after_seconds", 0) or 0
        )
        if pause > 0:
            pause_label = f"p{index}"
            filters.append(
                "anullsrc=r=48000:cl=stereo:"
                f"d={pause:.6f}[{pause_label}]"
            )
            labels.append(f"[{pause_label}]")

    filters.append(
        "".join(labels)
        + f"concat=n={len(labels)}:v=0:a=1,"
        "loudnorm=I=-18:LRA=11:TP=-1.5[narr]"
    )
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    _run(
        [
            _exe(
                "ffmpeg",
                "SIRAJ_FFMPEG_EXE",
            ),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[narr]",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s24le",
            output,
        ]
    )


def _still_motion_filter(
    duration: float,
    ordinal: int,
) -> str:
    # Vary motion deterministically between stills so the one-third
    # non-video share remains visually alive without reusing a shot.
    frame_count = max(2, int(round(duration * 30)))
    total = frame_count - 1
    profile = ordinal % 6

    if profile == 0:
        zoom = f"min(1.0+on/{total}*0.10,1.10)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif profile == 1:
        zoom = "1.08"
        x = f"(iw-iw/zoom)*on/{total}"
        y = "ih/2-(ih/zoom/2)"
    elif profile == 2:
        zoom = "1.08"
        x = f"(iw-iw/zoom)*(1-on/{total})"
        y = "ih/2-(ih/zoom/2)"
    elif profile == 3:
        zoom = "1.08"
        x = "iw/2-(iw/zoom/2)"
        y = f"(ih-ih/zoom)*on/{total}"
    elif profile == 4:
        zoom = "1.08"
        x = "iw/2-(iw/zoom/2)"
        y = f"(ih-ih/zoom)*(1-on/{total})"
    else:
        zoom = f"max(1.11-on/{total}*0.09,1.02)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"

    return (
        "scale=2304:1296:"
        "force_original_aspect_ratio=increase,"
        "crop=2304:1296,"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':"
        "d=1:s=1920x1080:fps=30,"
        f"trim=duration={duration:.6f},"
        "setpts=PTS-STARTPTS,"
        "format=yuv420p"
    )


def _render_shot(
    source,
    kind,
    duration,
    output,
    ordinal,
):
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if kind == "RUNWARE_IMAGE":
        args = [
            _exe(
                "ffmpeg",
                "SIRAJ_FFMPEG_EXE",
            ),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-framerate",
            "30",
            "-i",
            source,
            "-vf",
            _still_motion_filter(
                duration,
                ordinal,
            ),
            "-t",
            f"{duration:.6f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "17",
            "-pix_fmt",
            "yuv420p",
            output,
        ]
    else:
        base = (
            "scale=1920:1080:"
            "force_original_aspect_ratio=increase,"
            "crop=1920:1080,"
            "fps=30,"
            f"tpad=stop_mode=clone:"
            f"stop_duration={duration:.6f},"
            f"trim=duration={duration:.6f},"
            "setpts=PTS-STARTPTS,"
            "format=yuv420p"
        )
        args = [
            _exe(
                "ffmpeg",
                "SIRAJ_FFMPEG_EXE",
            ),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            source,
            "-vf",
            base,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "17",
            "-pix_fmt",
            "yuv420p",
            output,
        ]

    _run(args)


def assemble_episode_master(
    repo_root: Path,
    episode_id: str,
):
    repo = Path(repo_root).resolve()
    episode = repo / "projects" / episode_id

    tts = _read(
        resolve_final_tts_queue_path(repo, episode_id)
    )
    media = _read(
        episode
        / "orchestration/media-production-queue-v6-2-1.json"
    )
    items = media.get("items")
    if not isinstance(items, list) or not items:
        raise MontageV621Error(
            "MEDIA_QUEUE_ITEMS_REQUIRED"
        )
    if not all(
        isinstance(item, Mapping)
        and item.get("status") == "COMPLETE"
        for item in items
    ):
        raise MontageV621Error(
            "MEDIA_QUEUE_NOT_COMPLETE"
        )

    duplicate_problems = audit_completed_assets(
        repo,
        items,
    )
    if duplicate_problems:
        raise MontageV621Error(
            "MONTAGE_BLOCKED_BY_DUPLICATE_GATE:"
            + json.dumps(
                duplicate_problems,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

    policy = media.get("generated_video_policy") or {}
    planned = float(
        policy.get("planned_seconds", 0) or 0
    )
    maximum = float(
        policy.get("maximum_seconds", 0) or 0
    )
    if planned > maximum + 1e-9:
        raise MontageV621Error(
            "GENERATED_VIDEO_TWO_THIRDS_POLICY_FAILED"
        )

    work = episode / "orchestration/montage-v6-2-1"
    deliverable = (
        episode
        / "deliverables/autopilot-v6-2-1"
    )
    narration = (
        work / "narration-master-v6-2-1.wav"
    )
    emit_event(
        repo,
        episode_id,
        "MONTAGE_NARRATION_BUILD_STARTED",
        stage="LOCAL_ASSEMBLY_AND_MONTAGE",
        message_ar="بدأ بناء مسار السرد النهائي",
        operation="دمج مقاطع TTS والوقفات",
        output_path=str(narration.relative_to(repo)).replace("\\", "/"),
        provider="LOCAL",
        model="FFmpeg",
        status="RUNNING",
    )
    _build_narration(
        repo,
        tts,
        narration,
    )
    narration_duration = _duration(narration)
    emit_event(
        repo,
        episode_id,
        "FILE_WRITTEN",
        stage="LOCAL_ASSEMBLY_AND_MONTAGE",
        message_ar="اكتمل مسار السرد النهائي",
        operation="بدء رندر اللقطات",
        output_path=str(narration.relative_to(repo)).replace("\\", "/"),
        last_completed_file=str(narration.relative_to(repo)).replace("\\", "/"),
        provider="LOCAL",
        model="FFmpeg",
        status="COMPLETE",
    )

    concat_lines = []
    visual_duration = 0.0
    ordered = sorted(
        items,
        key=lambda x: int(
            x.get("queue_index", 0) or 0
        ),
    )

    for ordinal, item in enumerate(
        ordered,
        1,
    ):
        source = repo / str(
            item.get("output_path_relative") or ""
        )
        if not source.is_file():
            raise MontageV621Error(
                "VISUAL_ASSET_MISSING:" + str(source)
            )
        duration = float(
            item.get("duration_seconds", 0) or 0
        )
        if duration <= 0:
            raise MontageV621Error(
                "VISUAL_DURATION_REQUIRED:"
                + str(item.get("queue_id"))
            )

        shot = (
            work
            / "shots"
            / f"{ordinal:04d}.mp4"
        )
        emit_event(
            repo,
            episode_id,
            "MONTAGE_SHOT_RENDERING",
            stage="LOCAL_ASSEMBLY_AND_MONTAGE",
            message_ar=f"رندر اللقطة {ordinal} من {len(ordered)}",
            operation="تحويل الأصل إلى لقطة مونتاج 1080p/30fps",
            progress_current=ordinal - 1,
            progress_total=len(ordered),
            input_path=str(source.relative_to(repo)).replace("\\", "/"),
            output_path=str(shot.relative_to(repo)).replace("\\", "/"),
            provider="LOCAL",
            model="FFmpeg",
            request_current=ordinal,
            request_total=len(ordered),
            status="RUNNING",
        )
        _render_shot(
            source,
            str(item.get("media_kind") or ""),
            duration,
            shot,
            ordinal,
        )
        emit_event(
            repo,
            episode_id,
            "FILE_WRITTEN",
            stage="LOCAL_ASSEMBLY_AND_MONTAGE",
            message_ar=f"اكتملت لقطة المونتاج {ordinal}",
            operation="الانتقال إلى اللقطة التالية",
            progress_current=ordinal,
            progress_total=len(ordered),
            output_path=str(shot.relative_to(repo)).replace("\\", "/"),
            last_completed_file=str(shot.relative_to(repo)).replace("\\", "/"),
            provider="LOCAL",
            model="FFmpeg",
            request_current=ordinal,
            request_total=len(ordered),
            status="COMPLETE",
        )
        concat_lines.append(
            "file '"
            + shot.as_posix().replace(
                "'",
                "'\\''",
            )
            + "'"
        )
        visual_duration += duration

    if abs(
        visual_duration - narration_duration
    ) > 2.0:
        raise MontageV621Error(
            "AUDIO_VISUAL_TOTAL_DURATION_MISMATCH:"
            f"audio={narration_duration:.3f}:"
            f"visual={visual_duration:.3f}"
        )

    concat = work / "shots-concat-v6-2-1.txt"
    concat.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    concat.write_text(
        "\n".join(concat_lines) + "\n",
        encoding="utf-8",
    )

    video_only = (
        work / "episode-video-only-v6-2-1.mp4"
    )
    _run(
        [
            _exe(
                "ffmpeg",
                "SIRAJ_FFMPEG_EXE",
            ),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat,
            "-c",
            "copy",
            video_only,
        ]
    )

    final = (
        deliverable
        / "episode-master-autopilot-v6-2-1.mp4"
    )
    final.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    emit_event(
        repo,
        episode_id,
        "MONTAGE_FINAL_ASSEMBLY",
        stage="LOCAL_ASSEMBLY_AND_MONTAGE",
        message_ar="بدأ تجميع الفيديو النهائي مع السرد",
        operation="Mux نهائي للفيديو والصوت",
        input_path=str(video_only.relative_to(repo)).replace("\\", "/"),
        output_path=str(final.relative_to(repo)).replace("\\", "/"),
        provider="LOCAL",
        model="FFmpeg",
        status="RUNNING",
    )
    _run(
        [
            _exe(
                "ffmpeg",
                "SIRAJ_FFMPEG_EXE",
            ),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            video_only,
            "-i",
            narration,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-shortest",
            "-movflags",
            "+faststart",
            final,
        ]
    )

    receipt = (
        deliverable
        / "episode-master-autopilot-v6-2-1-receipt.json"
    )
    _write(
        receipt,
        {
            "schema_version": (
                "siraj-local-assembly-montage-v6.2.1"
            ),
            "status": "PASS",
            "episode_id": episode_id,
            "master_path_relative": str(
                final.relative_to(repo)
            ).replace("\\", "/"),
            "master_sha256": _sha(final),
            "duration_seconds": round(
                _duration(final),
                3,
            ),
            "generated_video_policy": policy,
            "duplicate_gate": "PASS",
            "animated_stills_motion": "ACTIVE",
            "video": {
                "width": 1920,
                "height": 1080,
                "fps": 30,
                "pixel_format": "yuv420p",
            },
            "audio": {
                "sample_rate": 48000,
                "channels": 2,
                "codec": "aac",
                "music": "FORBIDDEN",
            },
            "next_stage": (
                "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA"
            ),
            "completed_at_utc": _now(),
        },
    )
    emit_event(
        repo,
        episode_id,
        "MONTAGE_TASK_COMPLETED",
        stage="LOCAL_ASSEMBLY_AND_MONTAGE",
        message_ar="اكتمل المونتاج المحلي",
        operation="الفيديو الرئيسي جاهز لمرحلة الجودة",
        progress_current=len(ordered),
        progress_total=len(ordered),
        output_path=str(final.relative_to(repo)).replace("\\", "/"),
        last_completed_file=str(final.relative_to(repo)).replace("\\", "/"),
        provider="LOCAL",
        model="FFmpeg",
        status="COMPLETE",
    )
    return receipt
