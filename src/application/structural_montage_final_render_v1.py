from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from src.application.artifact_dependency_graph_v1 import canonical_sha256
from src.application.sfx_audio_mix_v1 import inspect_audio_environment

RELEASE = "STRUCTURAL_MONTAGE_AND_FINAL_RENDER_V1"

ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
MEDIA_QUEUE_REL = Path("orchestration/media-production-queue-v1.json")
STORYBOARD_REL = Path("cinematic/storyboard-and-media-plan-v1.json")
SCRIPT_REL = Path("script/episode-script-v1.json")
STAGE_LEDGER_REL = Path("orchestration/stage-ledger-v1.json")
DEPENDENCY_GRAPH_REL = Path("orchestration/artifact-dependency-graph-v1.json")
AUDIO_MASTER_REL = Path("audio/mix/episode-audio-master-v1.wav")

RENDER_PLAN_REL = Path("orchestration/structural-montage-render-plan-v1.json")
RUN_STATE_REL = Path("orchestration/structural-montage-render-state-v1.json")
RUN_LOCK_REL = Path("orchestration/structural-montage-final-render-v1.lock.json")
SHOT_DIR_REL = Path("cinematic/final-render/shots")
SHOT_RECEIPT_DIR_REL = Path("cinematic/final-render/shot-receipts")
CONCAT_LIST_REL = Path("cinematic/final-render/shot-concat-v1.txt")
VIDEO_ONLY_REL = Path("cinematic/final-render/episode-video-only-v1.mp4")
FINAL_MASTER_REL = Path("deliverables/episode-master-v1.mp4")
FINAL_RECEIPT_REL = Path("deliverables/episode-master-v1-receipt.json")

WIDTH = 1920
HEIGHT = 1080
FPS = 30
VIDEO_CODEC = "libx264"
PIXEL_FORMAT = "yuv420p"
H264_PROFILE = "high"
H264_LEVEL = "4.1"
COLOR_RANGE = "tv"
COLOR_SPACE = "bt709"
SHOT_CRF = 17
SHOT_PRESET = "medium"
AUDIO_CODEC = "aac"
AUDIO_BITRATE = "192k"
AUDIO_SAMPLE_RATE = 48_000
AUDIO_CHANNELS = 2
SEQUENCE_FADE_SECONDS = 0.35
MAX_LAST_FRAME_EXTENSION_SECONDS = 1.25
MIN_FREE_BYTES = 8 * 1024 * 1024 * 1024
BYTES_PER_EPISODE_SECOND_RESERVE = 5 * 1024 * 1024
DURATION_TOLERANCE_SECONDS = 0.20
FINAL_DURATION_TOLERANCE_SECONDS = 0.75

REQUIRED_VIDEO_FILTERS = frozenset(
    {
        "scale",
        "crop",
        "pad",
        "split",
        "overlay",
        "gblur",
        "zoompan",
        "fade",
        "eq",
        "vignette",
        "format",
        "fps",
        "trim",
        "setpts",
        "tpad",
    }
)

MOTION_PROFILES = (
    "SLOW_PUSH_IN",
    "PAN_LEFT_TO_RIGHT",
    "PAN_RIGHT_TO_LEFT",
    "PAN_TOP_TO_BOTTOM",
    "PAN_BOTTOM_TO_TOP",
    "SLOW_PULL_OUT",
    "DIAGONAL_DOWN_RIGHT",
    "DIAGONAL_UP_LEFT",
)

ProgressCallback = Callable[[str, int | None], None]


class StructuralMontageError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MontageEnvironment:
    ffmpeg_path: Path | None
    ffprobe_path: Path | None
    ffmpeg_version_line: str
    available_filters: frozenset[str]
    missing_filters: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return (
            self.ffmpeg_path is not None
            and self.ffprobe_path is not None
            and not self.missing_filters
        )


@dataclass(frozen=True, slots=True)
class StructuralMontageResult:
    episode_id: str
    render_plan_path: Path
    final_master_path: Path
    final_receipt_path: Path
    rendered_shot_count: int
    reused_shot_count: int
    duration_seconds: float
    status: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StructuralMontageError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise StructuralMontageError(f"JSON_OBJECT_REQUIRED:{path}")
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


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return value
    return ()


def _relative(repo: Path, path: Path) -> str:
    return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")


def _command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        [str(value) for value in args],
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if process.returncode != 0:
        raise StructuralMontageError(
            "COMMAND_FAILED:"
            + " ".join(str(value) for value in args)
            + "\nSTDOUT:\n"
            + process.stdout
            + "\nSTDERR:\n"
            + process.stderr
        )
    return process


@lru_cache(maxsize=4)
def _inspect_filters(ffmpeg_text: str, ffprobe_text: str) -> MontageEnvironment:
    ffmpeg = Path(ffmpeg_text) if ffmpeg_text else None
    ffprobe = Path(ffprobe_text) if ffprobe_text else None
    version_line = ""
    filters: set[str] = set()
    if ffmpeg is not None and ffmpeg.is_file():
        version = subprocess.run(
            [str(ffmpeg), "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if version.returncode == 0:
            version_line = version.stdout.splitlines()[0] if version.stdout else ""
            listed = subprocess.run(
                [str(ffmpeg), "-hide_banner", "-filters"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if listed.returncode == 0:
                for line in listed.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and re.fullmatch(r"[A-Za-z0-9_]+", parts[1]):
                        filters.add(parts[1])
        else:
            ffmpeg = None
    if ffprobe is not None and ffprobe.is_file():
        probe = subprocess.run(
            [str(ffprobe), "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if probe.returncode != 0:
            ffprobe = None
    missing = tuple(sorted(REQUIRED_VIDEO_FILTERS - filters))
    return MontageEnvironment(
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        ffmpeg_version_line=version_line,
        available_filters=frozenset(filters),
        missing_filters=missing,
    )


def inspect_montage_environment(
    repo_root: Path | None = None,
) -> MontageEnvironment:
    audio = inspect_audio_environment(repo_root)
    return _inspect_filters(
        str(audio.ffmpeg_path) if audio.ffmpeg_path is not None else "",
        str(audio.ffprobe_path) if audio.ffprobe_path is not None else "",
    )


def require_montage_environment(
    repo_root: Path | None = None,
) -> MontageEnvironment:
    environment = inspect_montage_environment(repo_root)
    errors: list[str] = []
    if environment.ffmpeg_path is None:
        errors.append("FFMPEG_NOT_AVAILABLE")
    if environment.ffprobe_path is None:
        errors.append("FFPROBE_NOT_AVAILABLE")
    if environment.missing_filters:
        errors.append(
            "FFMPEG_VIDEO_FILTERS_MISSING:"
            + ",".join(environment.missing_filters)
        )
    if errors:
        raise StructuralMontageError(
            "MONTAGE_ENVIRONMENT_NOT_READY:" + "|".join(errors)
        )
    return environment


def _active_episode(
    repo_root: Path,
) -> tuple[str, Path, Path, dict[str, Any], dict[str, Any]]:
    repo = repo_root.resolve()
    state_path = repo / ORCHESTRATOR_STATE_REL
    state = _read(state_path)
    episode_id = state.get("current_episode_id")
    if not isinstance(episode_id, str) or not episode_id.strip():
        raise StructuralMontageError("CURRENT_EPISODE_REQUIRED_FOR_MONTAGE")
    episode_root = repo / "projects" / episode_id.strip()
    queue_path = episode_root / MEDIA_QUEUE_REL
    if not queue_path.is_file():
        raise StructuralMontageError("MEDIA_PRODUCTION_QUEUE_NOT_FOUND")
    status = str(state.get("status", ""))
    allowed = {
        "SFX_MIX_READY",
        "STRUCTURAL_MONTAGE_ACTIVE",
        "STRUCTURAL_MONTAGE_FAILED",
        "FINAL_RENDER_READY_FOR_QA",
    }
    if status not in allowed:
        raise StructuralMontageError(f"STRUCTURAL_MONTAGE_NOT_ALLOWED:{status}")
    return episode_id.strip(), episode_root, queue_path, state, _read(queue_path)


def _all_media_complete(queue: Mapping[str, Any]) -> bool:
    queues = queue.get("queues")
    if not isinstance(queues, Mapping):
        return False
    seen = 0
    for key in (
        "runware_images",
        "runware_videos",
        "local_graphics",
        "elevenlabs_tts",
    ):
        items = queues.get(key)
        if not isinstance(items, list):
            return False
        for item in items:
            if not isinstance(item, Mapping):
                return False
            seen += 1
            if str(item.get("status", "")) != "COMPLETE":
                return False
    return seen > 0


def _queue_by_shot(queue: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    queues = queue.get("queues")
    if not isinstance(queues, Mapping):
        raise StructuralMontageError("MEDIA_QUEUE_COLLECTIONS_REQUIRED")
    result: dict[str, dict[str, Any]] = {}
    for key, treatment in (
        ("runware_images", "ANIMATED_STILL_COMPOSITING"),
        ("runware_videos", "GENERATED_VIDEO"),
        ("local_graphics", "GRAPHICS"),
    ):
        items = queues.get(key)
        if not isinstance(items, list):
            raise StructuralMontageError(f"MEDIA_QUEUE_LIST_REQUIRED:{key}")
        for item in items:
            if not isinstance(item, Mapping):
                raise StructuralMontageError(f"MEDIA_QUEUE_ITEM_OBJECT_REQUIRED:{key}")
            shot_id = str(item.get("shot_id", ""))
            if not shot_id:
                raise StructuralMontageError(f"MEDIA_QUEUE_SHOT_ID_REQUIRED:{key}")
            if shot_id in result:
                raise StructuralMontageError(f"DUPLICATE_SHOT_MEDIA:{shot_id}")
            copy = dict(item)
            copy["treatment"] = treatment
            result[shot_id] = copy
    return result


def _music_forbidden(payload: Mapping[str, Any], label: str) -> None:
    if str(payload.get("music", "FORBIDDEN")) != "FORBIDDEN":
        raise StructuralMontageError(f"MUSIC_POLICY_INVALID:{label}")
    if payload.get("contains_music") not in (None, False):
        raise StructuralMontageError(f"MUSIC_CONTENT_FORBIDDEN:{label}")


def _probe_json(environment: MontageEnvironment, path: Path) -> dict[str, Any]:
    if environment.ffprobe_path is None:
        raise StructuralMontageError("FFPROBE_NOT_AVAILABLE")
    process = _command(
        [
            str(environment.ffprobe_path),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ]
    )
    try:
        value = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise StructuralMontageError(f"FFPROBE_JSON_INVALID:{path}") from exc
    if not isinstance(value, dict):
        raise StructuralMontageError(f"FFPROBE_OBJECT_REQUIRED:{path}")
    return value


def _probe_duration(environment: MontageEnvironment, path: Path) -> float:
    payload = _probe_json(environment, path)
    format_info = payload.get("format")
    if isinstance(format_info, Mapping):
        try:
            duration = float(format_info.get("duration", 0.0))
        except (TypeError, ValueError):
            duration = 0.0
        if duration > 0:
            return duration
    durations = []
    for stream in _sequence(payload.get("streams")):
        if isinstance(stream, Mapping):
            try:
                value = float(stream.get("duration", 0.0))
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                durations.append(value)
    if durations:
        return max(durations)
    raise StructuralMontageError(f"MEDIA_DURATION_INVALID:{path}")


def _fps_value(value: Any) -> float:
    text = str(value or "0/1")
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        try:
            denominator_value = float(denominator)
            return float(numerator) / denominator_value if denominator_value else 0.0
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _validate_video_file(
    environment: MontageEnvironment,
    path: Path,
    expected_duration: float,
    *,
    require_audio: bool,
    tolerance: float,
) -> dict[str, Any]:
    payload = _probe_json(environment, path)
    streams = [
        stream for stream in _sequence(payload.get("streams")) if isinstance(stream, Mapping)
    ]
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(videos) != 1:
        raise StructuralMontageError(f"VIDEO_STREAM_COUNT_INVALID:{path}:{len(videos)}")
    video = videos[0]
    if int(video.get("width", 0)) != WIDTH or int(video.get("height", 0)) != HEIGHT:
        raise StructuralMontageError(f"VIDEO_GEOMETRY_INVALID:{path}")
    if str(video.get("pix_fmt", "")) != PIXEL_FORMAT:
        raise StructuralMontageError(f"VIDEO_PIXEL_FORMAT_INVALID:{path}")
    fps = _fps_value(video.get("avg_frame_rate"))
    if abs(fps - FPS) > 0.05:
        raise StructuralMontageError(f"VIDEO_FPS_INVALID:{path}:{fps}")
    if require_audio and len(audios) != 1:
        raise StructuralMontageError(f"AUDIO_STREAM_REQUIRED:{path}")
    if not require_audio and audios:
        raise StructuralMontageError(f"SOURCE_AUDIO_MUST_BE_STRIPPED:{path}")
    duration = _probe_duration(environment, path)
    if abs(duration - expected_duration) > tolerance:
        raise StructuralMontageError(
            f"VIDEO_DURATION_INVALID:{path}:expected={expected_duration:.3f}:actual={duration:.3f}"
        )
    return {
        "duration_seconds": duration,
        "video_codec": video.get("codec_name"),
        "audio_codec": audios[0].get("codec_name") if audios else None,
        "pixel_format": video.get("pix_fmt"),
        "color_range": video.get("color_range"),
        "colorspace": video.get("color_space"),
        "fps": fps,
        "width": WIDTH,
        "height": HEIGHT,
    }


def _motion_expression(profile: str, frame_count: int) -> tuple[str, str, str]:
    total = max(2, frame_count - 1)
    if profile == "SLOW_PUSH_IN":
        return (
            f"min(1.0+on/{total}*0.10,1.10)",
            "iw/2-(iw/zoom/2)",
            "ih/2-(ih/zoom/2)",
        )
    if profile == "PAN_LEFT_TO_RIGHT":
        return (
            "1.08",
            f"(iw-iw/zoom)*on/{total}",
            "ih/2-(ih/zoom/2)",
        )
    if profile == "PAN_RIGHT_TO_LEFT":
        return (
            "1.08",
            f"(iw-iw/zoom)*(1-on/{total})",
            "ih/2-(ih/zoom/2)",
        )
    if profile == "PAN_TOP_TO_BOTTOM":
        return (
            "1.08",
            "iw/2-(iw/zoom/2)",
            f"(ih-ih/zoom)*on/{total}",
        )
    if profile == "PAN_BOTTOM_TO_TOP":
        return (
            "1.08",
            "iw/2-(iw/zoom/2)",
            f"(ih-ih/zoom)*(1-on/{total})",
        )
    if profile == "SLOW_PULL_OUT":
        return (
            f"max(1.12-on/{total}*0.10,1.02)",
            "iw/2-(iw/zoom/2)",
            "ih/2-(ih/zoom/2)",
        )
    if profile == "DIAGONAL_DOWN_RIGHT":
        return (
            "1.09",
            f"(iw-iw/zoom)*on/{total}",
            f"(ih-ih/zoom)*on/{total}",
        )
    return (
        "1.09",
        f"(iw-iw/zoom)*(1-on/{total})",
        f"(ih-ih/zoom)*(1-on/{total})",
    )


def _fade_chain(duration: float, fade_in: bool, fade_out: bool) -> str:
    filters: list[str] = []
    fade_duration = min(SEQUENCE_FADE_SECONDS, max(0.08, duration / 4.0))
    if fade_in:
        filters.append(f"fade=t=in:st=0:d={fade_duration:.4f}")
    if fade_out:
        start = max(0.0, duration - fade_duration)
        filters.append(f"fade=t=out:st={start:.4f}:d={fade_duration:.4f}")
    return ("," + ",".join(filters)) if filters else ""


def build_still_render_command(
    environment: MontageEnvironment,
    source_path: Path,
    output_path: Path,
    *,
    duration: float,
    motion_profile: str,
    fade_in: bool,
    fade_out: bool,
) -> list[str]:
    if environment.ffmpeg_path is None:
        raise StructuralMontageError("FFMPEG_NOT_AVAILABLE")
    frame_count = max(1, int(round(duration * FPS)))
    zoom, x, y = _motion_expression(motion_profile, frame_count)
    fades = _fade_chain(duration, fade_in, fade_out)
    filter_graph = (
        "[0:v]split=2[bg][fg];"
        f"[bg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},gblur=sigma=26[bg2];"
        f"[fg]scale={WIDTH-180}:{HEIGHT-112}:"
        "force_original_aspect_ratio=decrease[fg2];"
        "[bg2][fg2]overlay=(W-w)/2:(H-h)/2,"
        "scale=2304:1296,"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d=1:"
        f"s={WIDTH}x{HEIGHT}:fps={FPS},"
        f"trim=duration={duration:.6f},setpts=PTS-STARTPTS,"
        "eq=contrast=1.035:saturation=0.97:gamma=0.995,"
        "vignette=PI/5"
        + fades
        + f",scale=iw:ih:in_range=auto:out_range={COLOR_RANGE},"
        + f"format={PIXEL_FORMAT}[outv]"
    )
    return [
        str(environment.ffmpeg_path),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-loop",
        "1",
        "-framerate",
        str(FPS),
        "-i",
        str(source_path),
        "-filter_complex",
        filter_graph,
        "-map",
        "[outv]",
        "-t",
        f"{duration:.6f}",
        "-an",
        "-r",
        str(FPS),
        "-c:v",
        VIDEO_CODEC,
        "-profile:v",
        H264_PROFILE,
        "-level:v",
        H264_LEVEL,
        "-preset",
        SHOT_PRESET,
        "-crf",
        str(SHOT_CRF),
        "-pix_fmt",
        PIXEL_FORMAT,
        "-color_range",
        COLOR_RANGE,
        "-colorspace",
        COLOR_SPACE,
        "-color_primaries",
        COLOR_SPACE,
        "-color_trc",
        COLOR_SPACE,
        "-g",
        str(FPS * 2),
        "-keyint_min",
        str(FPS * 2),
        "-sc_threshold",
        "0",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def build_motion_render_command(
    environment: MontageEnvironment,
    source_path: Path,
    output_path: Path,
    *,
    duration: float,
    source_duration: float,
    fade_in: bool,
    fade_out: bool,
    graphics: bool,
) -> list[str]:
    if environment.ffmpeg_path is None:
        raise StructuralMontageError("FFMPEG_NOT_AVAILABLE")
    extension = max(0.0, duration - source_duration)
    fades = _fade_chain(duration, fade_in, fade_out)
    grade = "" if graphics else ",eq=contrast=1.025:saturation=0.98:gamma=0.995,vignette=PI/6"
    filter_graph = (
        f"[0:v]fps={FPS},"
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"tpad=stop_mode=clone:stop_duration=min({extension,MAX_LAST_FRAME_EXTENSION_SECONDS):.6f},"
        f"trim=duration={duration:.6f},setpts=PTS-STARTPTS"
        + grade
        + fades
        + f",scale=iw:ih:in_range=auto:out_range={COLOR_RANGE},"
        + f"format={PIXEL_FORMAT}[outv]"
    )
    return [
        str(environment.ffmpeg_path),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-filter_complex",
        filter_graph,
        "-map",
        "[outv]",
        "-t",
        f"{duration:.6f}",
        "-an",
        "-r",
        str(FPS),
        "-c:v",
        VIDEO_CODEC,
        "-profile:v",
        H264_PROFILE,
        "-level:v",
        H264_LEVEL,
        "-preset",
        SHOT_PRESET,
        "-crf",
        str(SHOT_CRF),
        "-pix_fmt",
        PIXEL_FORMAT,
        "-color_range",
        COLOR_RANGE,
        "-colorspace",
        COLOR_SPACE,
        "-color_primaries",
        COLOR_SPACE,
        "-color_trc",
        COLOR_SPACE,
        "-g",
        str(FPS * 2),
        "-keyint_min",
        str(FPS * 2),
        "-sc_threshold",
        "0",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def _video_pixel_format(
    environment: MontageEnvironment,
    path: Path,
) -> str:
    payload = _probe_json(environment, path)
    videos = [
        stream
        for stream in _sequence(payload.get("streams"))
        if isinstance(stream, Mapping)
        and stream.get("codec_type") == "video"
    ]
    if len(videos) != 1:
        raise StructuralMontageError(
            f"VIDEO_STREAM_COUNT_INVALID:{path}:{len(videos)}"
        )
    return str(videos[0].get("pix_fmt", "")).strip()


def build_pixel_format_normalize_command(
    environment: MontageEnvironment,
    source_path: Path,
    output_path: Path,
    *,
    duration: float,
) -> list[str]:
    if environment.ffmpeg_path is None:
        raise StructuralMontageError("FFMPEG_NOT_AVAILABLE")
    filter_graph = (
        f"fps={FPS},scale={WIDTH}:{HEIGHT}:"
        f"in_range=auto:out_range={COLOR_RANGE},"
        f"trim=duration={duration:.6f},setpts=PTS-STARTPTS,"
        f"format={PIXEL_FORMAT}"
    )
    return [
        str(environment.ffmpeg_path),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-map",
        "0:v:0",
        "-vf",
        filter_graph,
        "-t",
        f"{duration:.6f}",
        "-an",
        "-r",
        str(FPS),
        "-c:v",
        VIDEO_CODEC,
        "-profile:v",
        H264_PROFILE,
        "-level:v",
        H264_LEVEL,
        "-preset",
        SHOT_PRESET,
        "-crf",
        str(SHOT_CRF),
        "-pix_fmt",
        PIXEL_FORMAT,
        "-color_range",
        COLOR_RANGE,
        "-colorspace",
        COLOR_SPACE,
        "-color_primaries",
        COLOR_SPACE,
        "-color_trc",
        COLOR_SPACE,
        "-g",
        str(FPS * 2),
        "-keyint_min",
        str(FPS * 2),
        "-sc_threshold",
        "0",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def _normalize_video_pixel_format_if_needed(
    environment: MontageEnvironment,
    path: Path,
    expected_duration: float,
) -> dict[str, Any]:
    detected = _video_pixel_format(environment, path)
    if detected == PIXEL_FORMAT:
        return {
            "applied": False,
            "input_pixel_format": detected,
            "output_pixel_format": detected,
        }
    normalized = path.with_name(path.stem + ".pixel-normalized.mp4")
    normalized.unlink(missing_ok=True)
    command = build_pixel_format_normalize_command(
        environment,
        path,
        normalized,
        duration=expected_duration,
    )
    try:
        _command(command)
        validation = _validate_video_file(
            environment,
            normalized,
            expected_duration,
            require_audio=False,
            tolerance=DURATION_TOLERANCE_SECONDS,
        )
        output_format = _video_pixel_format(environment, normalized)
        if output_format != PIXEL_FORMAT:
            raise StructuralMontageError(
                "VIDEO_PIXEL_FORMAT_NORMALIZATION_FAILED:"
                f"input={detected}:output={output_format}:path={path}"
            )
        os.replace(normalized, path)
    finally:
        normalized.unlink(missing_ok=True)
    return {
        "applied": True,
        "input_pixel_format": detected,
        "output_pixel_format": PIXEL_FORMAT,
        "validation": validation,
    }


def _sequence_boundaries(shots: Sequence[Mapping[str, Any]]) -> dict[str, tuple[bool, bool]]:
    result: dict[str, tuple[bool, bool]] = {}
    for index, shot in enumerate(shots):
        sequence_id = str(shot.get("sequence_id", ""))
        previous_sequence = (
            str(shots[index - 1].get("sequence_id", "")) if index > 0 else None
        )
        next_sequence = (
            str(shots[index + 1].get("sequence_id", ""))
            if index + 1 < len(shots)
            else None
        )
        result[str(shot.get("shot_id", ""))] = (
            index == 0 or previous_sequence != sequence_id,
            index + 1 == len(shots) or next_sequence != sequence_id,
        )
    return result


def _receipt_reusable(
    receipt_path: Path,
    output_path: Path,
    fingerprint: str,
) -> bool:
    if not receipt_path.is_file() or not output_path.is_file():
        return False
    try:
        receipt = _read(receipt_path)
    except StructuralMontageError:
        return False
    return (
        receipt.get("status") == "COMPLETE"
        and receipt.get("render_fingerprint_sha256") == fingerprint
        and receipt.get("output_sha256") == _sha256(output_path)
    )


def _disk_preflight(episode_root: Path, duration: float) -> dict[str, Any]:
    usage = shutil.disk_usage(episode_root)
    required = max(
        MIN_FREE_BYTES,
        int(math.ceil(duration * BYTES_PER_EPISODE_SECOND_RESERVE)),
    )
    if usage.free < required:
        raise StructuralMontageError(
            "INSUFFICIENT_DISK_SPACE:"
            f"free={usage.free}:required={required}"
        )
    return {
        "free_bytes": usage.free,
        "required_bytes": required,
        "total_bytes": usage.total,
    }


def build_structural_montage_plan(
    repo_root: Path,
    *,
    environment: MontageEnvironment | None = None,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    environment = environment or require_montage_environment(repo)
    episode_id, episode_root, _, _, queue = _active_episode(repo)
    if not _all_media_complete(queue):
        raise StructuralMontageError("MEDIA_ASSETS_MUST_BE_COMPLETE_BEFORE_MONTAGE")
    storyboard = _read(episode_root / STORYBOARD_REL)
    script = _read(episode_root / SCRIPT_REL)
    _music_forbidden(storyboard, "STORYBOARD")
    _music_forbidden(script, "SCRIPT")
    raw_shots = storyboard.get("shots")
    if not isinstance(raw_shots, list) or len(raw_shots) != 70:
        raise StructuralMontageError("STORYBOARD_70_SHOTS_REQUIRED")
    shots = sorted(
        (dict(value) for value in raw_shots if isinstance(value, Mapping)),
        key=lambda value: int(value.get("queue_index", 0)),
    )
    if len(shots) != 70:
        raise StructuralMontageError("STORYBOARD_SHOT_OBJECT_REQUIRED")
    if [int(shot.get("queue_index", 0)) for shot in shots] != list(range(1, 71)):
        raise StructuralMontageError("STORYBOARD_QUEUE_INDEX_SEQUENCE_INVALID")
    media = _queue_by_shot(queue)
    boundaries = _sequence_boundaries(shots)
    audio_master = episode_root / AUDIO_MASTER_REL
    if not audio_master.is_file():
        raise StructuralMontageError("AUDIO_MASTER_REQUIRED_BEFORE_MONTAGE")
    audio_duration = _probe_duration(environment, audio_master)

    treatment_counts = {
        "ANIMATED_STILL_COMPOSITING": 0,
        "GENERATED_VIDEO": 0,
        "GRAPHICS": 0,
    }
    episode_duration = 0.0
    generated_video_seconds = 0
    plan_shots: list[dict[str, Any]] = []
    for shot in shots:
        shot_id = str(shot.get("shot_id", ""))
        _music_forbidden(shot, shot_id)
        treatment = str(shot.get("final_budget_treatment", ""))
        if treatment not in treatment_counts:
            raise StructuralMontageError(f"SHOT_TREATMENT_INVALID:{shot_id}:{treatment}")
        queue_item = media.get(shot_id)
        if queue_item is None:
            raise StructuralMontageError(f"SHOT_MEDIA_MISSING:{shot_id}")
        if queue_item.get("treatment") != treatment:
            raise StructuralMontageError(f"SHOT_MEDIA_TREATMENT_MISMATCH:{shot_id}")
        source_relative = str(queue_item.get("output_path_relative", ""))
        source_path = repo / source_relative
        if not source_path.is_file():
            raise StructuralMontageError(f"SHOT_SOURCE_FILE_MISSING:{shot_id}:{source_relative}")
        duration = float(shot.get("editorial_duration_seconds", 0.0))
        if duration <= 0:
            raise StructuralMontageError(f"SHOT_DURATION_INVALID:{shot_id}")
        episode_duration += duration
        treatment_counts[treatment] += 1
        generated_video_seconds += int(shot.get("planned_generated_video_seconds", 0))
        output_path = episode_root / SHOT_DIR_REL / f"{shot_id}.mp4"
        receipt_path = episode_root / SHOT_RECEIPT_DIR_REL / f"{shot_id}-receipt.json"
        fade_in, fade_out = boundaries[shot_id]
        motion_profile = (
            MOTION_PROFILES[(int(shot["queue_index"]) - 1) % len(MOTION_PROFILES)]
            if treatment == "ANIMATED_STILL_COMPOSITING"
            else "SOURCE_MOTION"
        )
        source_duration = (
            None
            if treatment == "ANIMATED_STILL_COMPOSITING"
            else round(_probe_duration(environment, source_path), 6)
        )
        fingerprint_payload = {
            "release": RELEASE,
            "shot_id": shot_id,
            "queue_index": int(shot["queue_index"]),
            "sequence_id": shot.get("sequence_id"),
            "treatment": treatment,
            "duration_seconds": duration,
            "source_path_relative": source_relative,
            "source_sha256": _sha256(source_path),
            "source_duration_seconds": source_duration,
            "motion_profile": motion_profile,
            "fade_in": fade_in,
            "fade_out": fade_out,
            "width": WIDTH,
            "height": HEIGHT,
            "fps": FPS,
            "video_codec": VIDEO_CODEC,
            "pixel_format": PIXEL_FORMAT,
            "crf": SHOT_CRF,
        }
        fingerprint = _canonical_sha256(fingerprint_payload)
        reusable = _receipt_reusable(receipt_path, output_path, fingerprint)
        plan_shots.append(
            {
                **fingerprint_payload,
                "render_fingerprint_sha256": fingerprint,
                "output_path_relative": _relative(repo, output_path),
                "receipt_path_relative": _relative(repo, receipt_path),
                "render_status": "REUSABLE" if reusable else "PENDING",
            }
        )

    episode_duration = round(episode_duration, 6)
    if treatment_counts != {
        "ANIMATED_STILL_COMPOSITING": 44,
        "GENERATED_VIDEO": 20,
        "GRAPHICS": 6,
    }:
        raise StructuralMontageError(
            "TREATMENT_COUNTS_INVALID:" + json.dumps(treatment_counts, sort_keys=True)
        )
    if generated_video_seconds != 160:
        raise StructuralMontageError(
            f"GENERATED_VIDEO_SECONDS_MUST_BE_160:{generated_video_seconds}"
        )
    if not 1080.0 <= episode_duration <= 1500.0:
        raise StructuralMontageError(
            f"EPISODE_DURATION_OUTSIDE_CONSTITUTION:{episode_duration:.3f}"
        )
    if abs(audio_duration - episode_duration) > FINAL_DURATION_TOLERANCE_SECONDS:
        raise StructuralMontageError(
            "AUDIO_MASTER_DURATION_MISMATCH:"
            f"audio={audio_duration:.3f}:timeline={episode_duration:.3f}"
        )
    disk = _disk_preflight(episode_root, episode_duration)
    plan: dict[str, Any] = {
        "schema_version": "siraj-structural-montage-render-plan-v1",
        "release": RELEASE,
        "episode_id": episode_id,
        "status": "READY_FOR_LOCAL_RENDER",
        "music": "FORBIDDEN",
        "flat_slideshow": "FORBIDDEN",
        "episode_duration_seconds": episode_duration,
        "generated_video_seconds": generated_video_seconds,
        "shot_count": len(plan_shots),
        "treatment_counts": treatment_counts,
        "render_profile": {
            "width": WIDTH,
            "height": HEIGHT,
            "fps": FPS,
            "video_codec": VIDEO_CODEC,
            "pixel_format": PIXEL_FORMAT,
            "shot_crf": SHOT_CRF,
            "shot_preset": SHOT_PRESET,
            "still_motion_profiles": list(MOTION_PROFILES),
            "sequence_fade_seconds": SEQUENCE_FADE_SECONDS,
            "source_audio": "STRIPPED",
            "final_audio_source_relative": _relative(repo, audio_master),
        },
        "disk_preflight": disk,
        "shots": plan_shots,
        "outputs": {
            "concat_list_relative": str((Path("projects") / episode_id / CONCAT_LIST_REL).as_posix()),
            "video_only_relative": str((Path("projects") / episode_id / VIDEO_ONLY_REL).as_posix()),
            "final_master_relative": str((Path("projects") / episode_id / FINAL_MASTER_REL).as_posix()),
            "final_receipt_relative": str((Path("projects") / episode_id / FINAL_RECEIPT_REL).as_posix()),
        },
        "ffmpeg_version": environment.ffmpeg_version_line,
        "local_api_cost_usd": 0.0,
        "paid_provider_requests": 0,
        "created_at_utc": _now(),
    }
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _exclusive_local_lock(path: Path, payload: Mapping[str, Any]) -> None:
    if path.is_file():
        try:
            existing = _read(path)
        except StructuralMontageError:
            existing = {}
        pid = int(existing.get("pid", 0)) if isinstance(existing.get("pid", 0), int) else 0
        if _pid_alive(pid):
            raise StructuralMontageError("STRUCTURAL_MONTAGE_ALREADY_RUNNING")
        path.unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise StructuralMontageError("STRUCTURAL_MONTAGE_ALREADY_RUNNING") from exc
    try:
        os.write(descriptor, raw)
    finally:
        os.close(descriptor)


def _render_shot(
    repo: Path,
    environment: MontageEnvironment,
    shot: Mapping[str, Any],
) -> tuple[Path, Path, bool]:
    output_path = repo / str(shot["output_path_relative"])
    receipt_path = repo / str(shot["receipt_path_relative"])
    fingerprint = str(shot["render_fingerprint_sha256"])
    if _receipt_reusable(receipt_path, output_path, fingerprint):
        return output_path, receipt_path, True
    source_path = repo / str(shot["source_path_relative"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".rendering.mp4")
    temporary.unlink(missing_ok=True)
    treatment = str(shot["treatment"])
    duration = float(shot["duration_seconds"])
    if treatment == "ANIMATED_STILL_COMPOSITING":
        command = build_still_render_command(
            environment,
            source_path,
            temporary,
            duration=duration,
            motion_profile=str(shot["motion_profile"]),
            fade_in=bool(shot["fade_in"]),
            fade_out=bool(shot["fade_out"]),
        )
    else:
        command = build_motion_render_command(
            environment,
            source_path,
            temporary,
            duration=duration,
            source_duration=float(shot.get("source_duration_seconds") or duration),
            fade_in=bool(shot["fade_in"]),
            fade_out=bool(shot["fade_out"]),
            graphics=treatment == "GRAPHICS",
        )
    _command(command)
    pixel_format_normalization = _normalize_video_pixel_format_if_needed(
        environment,
        temporary,
        duration,
    )
    validation = _validate_video_file(
        environment,
        temporary,
        duration,
        require_audio=False,
        tolerance=DURATION_TOLERANCE_SECONDS,
    )
    os.replace(temporary, output_path)
    receipt = {
        "schema_version": "siraj-structural-montage-shot-receipt-v1",
        "release": RELEASE,
        "episode_id": Path(str(shot["output_path_relative"])).parts[1],
        "shot_id": shot["shot_id"],
        "queue_index": shot["queue_index"],
        "sequence_id": shot.get("sequence_id"),
        "treatment": treatment,
        "status": "COMPLETE",
        "provider": "LOCAL",
        "service": "STRUCTURAL_MONTAGE_SHOT_RENDER",
        "cost_category": "OTHER",
        "actual_cost_usd": 0.0,
        "estimated_cost_usd": 0.0,
        "music": "FORBIDDEN",
        "source_audio": "STRIPPED",
        "source_path_relative": shot["source_path_relative"],
        "source_sha256": shot["source_sha256"],
        "render_fingerprint_sha256": fingerprint,
        "output_path_relative": shot["output_path_relative"],
        "output_sha256": _sha256(output_path),
        "output_bytes": output_path.stat().st_size,
        "duration_seconds": duration,
        "validation": validation,
        "pixel_format_normalization": pixel_format_normalization,
        "paid_provider_requests": 0,
        "completed_at_utc": _now(),
    }
    _write(receipt_path, receipt)
    return output_path, receipt_path, False


def _concat_escape(path: Path) -> str:
    value = str(path.resolve()).replace("\\", "/")
    return value.replace("'", "'\\''")


def _concat_video(
    environment: MontageEnvironment,
    shot_paths: Sequence[Path],
    list_path: Path,
    output_path: Path,
) -> None:
    if environment.ffmpeg_path is None:
        raise StructuralMontageError("FFMPEG_NOT_AVAILABLE")
    lines = [f"file '{_concat_escape(path)}'" for path in shot_paths]
    _write_text(list_path, "\n".join(lines) + "\n")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".rendering.mp4")
    temporary.unlink(missing_ok=True)
    _command(
        [
            str(environment.ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(temporary),
        ]
    )
    os.replace(temporary, output_path)


def _mux_audio(
    environment: MontageEnvironment,
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    duration: float,
) -> None:
    if environment.ffmpeg_path is None:
        raise StructuralMontageError("FFMPEG_NOT_AVAILABLE")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".rendering.mp4")
    temporary.unlink(missing_ok=True)
    _command(
        [
            str(environment.ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            AUDIO_CODEC,
            "-b:a",
            AUDIO_BITRATE,
            "-ar",
            str(AUDIO_SAMPLE_RATE),
            "-ac",
            str(AUDIO_CHANNELS),
            "-t",
            f"{duration:.6f}",
            "-movflags",
            "+faststart",
            str(temporary),
        ]
    )
    os.replace(temporary, output_path)


def _update_stage_ledger(
    repo: Path,
    episode_root: Path,
    plan_path: Path,
    receipt_path: Path,
) -> None:
    path = episode_root / STAGE_LEDGER_REL
    if not path.is_file():
        return
    ledger = _read(path)
    stages = ledger.get("stages")
    if not isinstance(stages, list):
        raise StructuralMontageError("STAGE_LEDGER_STAGES_REQUIRED")
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        if stage.get("stage") == "STRUCTURAL_MONTAGE":
            stage["status"] = "COMPLETE"
            stage["artifact_path_relative"] = _relative(repo, plan_path)
            stage["receipt_path_relative"] = _relative(repo, receipt_path)
            stage["updated_at_utc"] = _now()
        elif stage.get("stage") == "AUTOMATIC_QA":
            stage["status"] = "QUEUED"
    ledger["status"] = "FINAL_RENDER_READY_FOR_QA"
    ledger["resume_from"] = "AUTOMATIC_QA"
    ledger["updated_at_utc"] = _now()
    _write(path, ledger)


def _upsert_node(
    nodes: list[dict[str, Any]],
    index: dict[str, dict[str, Any]],
    node_id: str,
    kind: str,
    source_id: str,
    path_relative: str,
    sha256: str,
) -> None:
    node = index.get(node_id)
    payload = {
        "node_id": node_id,
        "kind": kind,
        "source_id": source_id,
        "status": "COMPLETE",
        "version": 1,
        "artifact_path_relative": path_relative,
        "artifact_sha256": sha256,
        "invalidated_at_utc": None,
        "invalidation_reason": None,
    }
    if node is None:
        nodes.append(payload)
        index[node_id] = payload
    else:
        node.update(payload)


def _edge(edges: list[dict[str, str]], parent: str, child: str) -> None:
    value = {"from": parent, "to": child}
    if value not in edges:
        edges.append(value)


def _update_dependency_graph(
    repo: Path,
    episode_id: str,
    episode_root: Path,
    plan_path: Path,
    final_path: Path,
    shots: Sequence[Mapping[str, Any]],
) -> None:
    path = episode_root / DEPENDENCY_GRAPH_REL
    if not path.is_file():
        return
    graph = _read(path)
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise StructuralMontageError("DEPENDENCY_GRAPH_STRUCTURE_INVALID")
    index = {
        str(node.get("node_id")): node
        for node in nodes
        if isinstance(node, dict)
    }
    plan_node = f"{episode_id}:MONTAGE_PLAN"
    final_node = f"{episode_id}:FINAL_RENDER"
    _upsert_node(
        nodes,
        index,
        plan_node,
        "STRUCTURAL_MONTAGE_PLAN",
        episode_id,
        _relative(repo, plan_path),
        _sha256(plan_path),
    )
    _upsert_node(
        nodes,
        index,
        final_node,
        "FINAL_EPISODE_RENDER",
        episode_id,
        _relative(repo, final_path),
        _sha256(final_path),
    )
    audio_node = f"{episode_id}:AUDIO_MASTER"
    if audio_node in index:
        _edge(edges, audio_node, final_node)
    _edge(edges, plan_node, final_node)
    for shot in shots:
        node_id = f"{episode_id}:MONTAGE_SHOT:{shot['shot_id']}"
        output = repo / str(shot["output_path_relative"])
        _upsert_node(
            nodes,
            index,
            node_id,
            "MONTAGE_SHOT_CLIP",
            str(shot["shot_id"]),
            _relative(repo, output),
            _sha256(output),
        )
        _edge(edges, plan_node, node_id)
        _edge(edges, node_id, final_node)
    graph["status"] = "FINAL_RENDER_READY_FOR_QA"
    graph["updated_at_utc"] = _now()
    graph.pop("graph_sha256", None)
    graph["graph_sha256"] = canonical_sha256(graph)
    _write(path, graph)


def run_structural_montage_final_render(
    repo_root: Path,
    *,
    progress: ProgressCallback | None = None,
) -> StructuralMontageResult:
    repo = repo_root.resolve()
    environment = require_montage_environment(repo)
    episode_id, episode_root, _, state, queue = _active_episode(repo)
    if not _all_media_complete(queue):
        raise StructuralMontageError("MEDIA_ASSETS_MUST_BE_COMPLETE_BEFORE_MONTAGE")
    state_path = repo / ORCHESTRATOR_STATE_REL
    lock_path = episode_root / RUN_LOCK_REL
    _exclusive_local_lock(
        lock_path,
        {
            "schema_version": "siraj-structural-montage-lock-v1",
            "release": RELEASE,
            "episode_id": episode_id,
            "pid": os.getpid(),
            "status": "LOCKED_LOCAL_EXECUTION",
            "paid_provider_requests": 0,
            "created_at_utc": _now(),
        },
    )
    state.update(
        {
            "status": "STRUCTURAL_MONTAGE_ACTIVE",
            "stage": "STRUCTURAL_MONTAGE",
            "next_stage": "STRUCTURAL_MONTAGE_AND_FINAL_RENDER_V1",
            "last_error": None,
            "updated_at_utc": _now(),
        }
    )
    _write(state_path, state)
    try:
        if progress:
            progress("بناء خطة المونتاج والتحقق من الأصول.", 3)
        plan = build_structural_montage_plan(repo, environment=environment)
        plan_path = episode_root / RENDER_PLAN_REL
        _write(plan_path, plan)
        shots = list(plan["shots"])
        rendered = reused = 0
        shot_paths: list[Path] = []
        for index, shot in enumerate(shots, start=1):
            if progress:
                progress(
                    f"رندر اللقطة {index}/70 — {shot['shot_id']}",
                    5 + int(76 * index / len(shots)),
                )
            output, _, was_reused = _render_shot(repo, environment, shot)
            shot_paths.append(output)
            if was_reused:
                reused += 1
            else:
                rendered += 1

        concat_list = episode_root / CONCAT_LIST_REL
        video_only = episode_root / VIDEO_ONLY_REL
        final_master = episode_root / FINAL_MASTER_REL
        final_receipt = episode_root / FINAL_RECEIPT_REL
        duration = float(plan["episode_duration_seconds"])
        if progress:
            progress("تجميع اللقطات السبعين دون إعادة ترميز.", 84)
        _concat_video(environment, shot_paths, concat_list, video_only)
        _validate_video_file(
            environment,
            video_only,
            duration,
            require_audio=False,
            tolerance=FINAL_DURATION_TOLERANCE_SECONDS,
        )
        if progress:
            progress("دمج الماستر الصوتي وإغلاق ملف الحلقة.", 92)
        audio_master = episode_root / AUDIO_MASTER_REL
        _mux_audio(
            environment,
            video_only,
            audio_master,
            final_master,
            duration,
        )
        validation = _validate_video_file(
            environment,
            final_master,
            duration,
            require_audio=True,
            tolerance=FINAL_DURATION_TOLERANCE_SECONDS,
        )
        receipt = {
            "schema_version": "siraj-final-render-receipt-v1",
            "release": RELEASE,
            "episode_id": episode_id,
            "status": "COMPLETE_READY_FOR_AUTOMATIC_QA",
            "provider": "LOCAL",
            "service": "STRUCTURAL_MONTAGE_AND_FINAL_RENDER",
            "cost_category": "OTHER",
            "actual_cost_usd": 0.0,
            "estimated_cost_usd": 0.0,
            "music": "FORBIDDEN",
            "flat_slideshow": "FORBIDDEN",
            "source_audio": "STRIPPED_FROM_ALL_VISUAL_INPUTS",
            "audio_master_relative": _relative(repo, audio_master),
            "audio_master_sha256": _sha256(audio_master),
            "render_plan_relative": _relative(repo, plan_path),
            "render_plan_sha256": _sha256(plan_path),
            "shot_count": 70,
            "rendered_shot_count": rendered,
            "reused_shot_count": reused,
            "duration_seconds": duration,
            "final_master_relative": _relative(repo, final_master),
            "final_master_sha256": _sha256(final_master),
            "final_master_bytes": final_master.stat().st_size,
            "validation": validation,
            "ffmpeg_version": environment.ffmpeg_version_line,
            "paid_provider_requests": 0,
            "completed_at_utc": _now(),
        }
        _write(final_receipt, receipt)
        _update_stage_ledger(repo, episode_root, plan_path, final_receipt)
        _update_dependency_graph(
            repo,
            episode_id,
            episode_root,
            plan_path,
            final_master,
            shots,
        )
        state.update(
            {
                "status": "FINAL_RENDER_READY_FOR_QA",
                "stage": "AUTOMATIC_QA",
                "next_stage": "AUTOMATIC_QA_AND_PARTIAL_REPAIR_V1",
                "structural_montage_plan_path_relative": _relative(repo, plan_path),
                "final_master_path_relative": _relative(repo, final_master),
                "final_master_sha256": _sha256(final_master),
                "last_error": None,
                "updated_at_utc": _now(),
            }
        )
        _write(state_path, state)
        _write(
            episode_root / RUN_STATE_REL,
            {
                "schema_version": "siraj-structural-montage-state-v1",
                "release": RELEASE,
                "episode_id": episode_id,
                "status": "COMPLETE",
                "rendered_shot_count": rendered,
                "reused_shot_count": reused,
                "duration_seconds": duration,
                "render_plan_path_relative": _relative(repo, plan_path),
                "final_master_path_relative": _relative(repo, final_master),
                "final_receipt_path_relative": _relative(repo, final_receipt),
                "paid_provider_requests": 0,
                "completed_at_utc": _now(),
            },
        )
        if progress:
            progress("اكتمل ملف الحلقة وانتقل إلى الفحص الآلي.", 100)
        return StructuralMontageResult(
            episode_id=episode_id,
            render_plan_path=plan_path,
            final_master_path=final_master,
            final_receipt_path=final_receipt,
            rendered_shot_count=rendered,
            reused_shot_count=reused,
            duration_seconds=duration,
            status="FINAL_RENDER_READY_FOR_QA",
        )
    except Exception as exc:
        state.update(
            {
                "status": "STRUCTURAL_MONTAGE_FAILED",
                "stage": "STRUCTURAL_MONTAGE",
                "next_stage": "RESUME_STRUCTURAL_MONTAGE_AND_FINAL_RENDER_V1",
                "last_error": str(exc),
                "updated_at_utc": _now(),
            }
        )
        _write(state_path, state)
        _write(
            episode_root / RUN_STATE_REL,
            {
                "schema_version": "siraj-structural-montage-state-v1",
                "release": RELEASE,
                "episode_id": episode_id,
                "status": "FAILED",
                "last_error": str(exc),
                "paid_provider_requests": 0,
                "updated_at_utc": _now(),
            },
        )
        if isinstance(exc, StructuralMontageError):
            raise
        raise StructuralMontageError(str(exc)) from exc
    finally:
        lock_path.unlink(missing_ok=True)


def load_structural_montage_status(repo_root: Path) -> dict[str, Any]:
    repo = repo_root.resolve()
    try:
        state = _read(repo / ORCHESTRATOR_STATE_REL)
    except StructuralMontageError:
        return {"status": "NO_ORCHESTRATOR_STATE", "ready": False}
    episode_id = state.get("current_episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        return {"status": str(state.get("status", "IDLE")), "ready": False}
    episode_root = repo / "projects" / episode_id
    run_state_path = episode_root / RUN_STATE_REL
    run_state = _read(run_state_path) if run_state_path.is_file() else {}
    final_master = episode_root / FINAL_MASTER_REL
    status = str(state.get("status", "UNKNOWN"))
    downstream = {
        "AUTOMATIC_QA_ACTIVE",
        "AUTOMATIC_QA_FAILED",
        "AUTOMATIC_QA_BLOCKED",
        "AWAITING_HUMAN_FINAL_REVIEW",
        "READY_TO_PUBLISH",
    }
    complete = final_master.is_file() and (
        run_state.get("status") == "COMPLETE"
        or status == "FINAL_RENDER_READY_FOR_QA"
        or status in downstream
    )
    return {
        "episode_id": episode_id,
        "status": status,
        "stage": str(state.get("stage", "")),
        "last_error": state.get("last_error"),
        "ready": status in {
            "SFX_MIX_READY",
            "STRUCTURAL_MONTAGE_FAILED",
            "FINAL_RENDER_READY_FOR_QA",
            *downstream,
        },
        "complete": complete,
        "final_master_path": str(final_master),
        "final_receipt_path": str(episode_root / FINAL_RECEIPT_REL),
        "rendered_shot_count": run_state.get("rendered_shot_count", 0),
        "reused_shot_count": run_state.get("reused_shot_count", 0),
        "duration_seconds": run_state.get("duration_seconds", 0.0),
    }


def run_montage_smoke_test(
    repo_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    environment = require_montage_environment(repo_root)
    if environment.ffmpeg_path is None:
        raise StructuralMontageError("FFMPEG_NOT_AVAILABLE")
    output_root.mkdir(parents=True, exist_ok=True)
    still = output_root / "still.png"
    motion = output_root / "motion.mp4"
    audio = output_root / "audio.wav"
    shot_a = output_root / "shot-a.mp4"
    shot_b = output_root / "shot-b.mp4"
    concat_list = output_root / "concat.txt"
    video_only = output_root / "video-only.mp4"
    final = output_root / "smoke-final.mp4"
    _command(
        [
            str(environment.ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x24180f:s=1600x1000",
            "-frames:v",
            "1",
            str(still),
        ]
    )
    _command(
        [
            str(environment.ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=30",
            "-t",
            "1.0",
            "-an",
            "-c:v",
            VIDEO_CODEC,
            "-pix_fmt",
            PIXEL_FORMAT,
            str(motion),
        ]
    )
    _command(
        [
            str(environment.ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r={AUDIO_SAMPLE_RATE}:cl=stereo",
            "-t",
            "2.0",
            "-c:a",
            "pcm_s24le",
            str(audio),
        ]
    )
    _command(
        build_still_render_command(
            environment,
            still,
            shot_a,
            duration=1.0,
            motion_profile="SLOW_PUSH_IN",
            fade_in=True,
            fade_out=False,
        )
    )
    _command(
        build_motion_render_command(
            environment,
            motion,
            shot_b,
            duration=1.0,
            source_duration=1.0,
            fade_in=False,
            fade_out=True,
            graphics=False,
        )
    )
    _validate_video_file(
        environment,
        shot_a,
        1.0,
        require_audio=False,
        tolerance=DURATION_TOLERANCE_SECONDS,
    )
    _validate_video_file(
        environment,
        shot_b,
        1.0,
        require_audio=False,
        tolerance=DURATION_TOLERANCE_SECONDS,
    )
    _concat_video(environment, [shot_a, shot_b], concat_list, video_only)
    _mux_audio(environment, video_only, audio, final, 2.0)
    validation = _validate_video_file(
        environment,
        final,
        2.0,
        require_audio=True,
        tolerance=FINAL_DURATION_TOLERANCE_SECONDS,
    )
    return {
        "status": "PASS",
        "ffmpeg_version": environment.ffmpeg_version_line,
        "final_sha256": _sha256(final),
        "validation": validation,
        "music": "FORBIDDEN",
        "paid_provider_requests": 0,
    }
