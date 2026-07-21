"""Render Episode Render Manifest v2 through local FFmpeg."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from .episode_render_v2 import (
    validate_episode_render_manifest_v2,
)


RENDER_ADAPTER_V2_REPORT_SCHEMA = (
    "siraj-local-video-render-report-v2"
)


@dataclass(frozen=True)
class EpisodeRenderV2Result:
    status: str
    output: str
    report: str
    manifest: str
    checks: dict[str, bool]


def _run(
    command: list[str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )


def _require_success(
    process: subprocess.CompletedProcess[str],
    error_code: str,
) -> None:
    if process.returncode == 0:
        return

    detail = (
        process.stderr[-6000:]
        or process.stdout[-6000:]
    )

    raise RuntimeError(
        f"{error_code}:{detail}"
    )


def _resolve_executable(name: str) -> str:
    candidate = Path(name)

    if candidate.is_file():
        return str(candidate)

    resolved = shutil.which(name)

    if not resolved:
        raise FileNotFoundError(
            f"EXECUTABLE_NOT_FOUND:{name}"
        )

    return resolved


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8-sig")
    )

    if not isinstance(value, dict):
        raise ValueError(
            "EPISODE_RENDER_MANIFEST_NOT_OBJECT"
        )

    return value


def _write_json(
    path: Path,
    value: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    text = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(text)

    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _resolve_project_file(
    project_root: Path,
    relative_path: str,
    error_code: str,
) -> Path:
    candidate = (
        project_root / relative_path
    ).resolve(strict=False)

    try:
        candidate.relative_to(project_root)
    except ValueError as error:
        raise ValueError(
            f"{error_code}_OUTSIDE_PROJECT"
        ) from error

    if not candidate.is_file():
        raise FileNotFoundError(
            f"{error_code}_NOT_FOUND:{candidate}"
        )

    return candidate


def _resolve_output_file(
    project_root: Path,
    relative_path: str,
) -> Path:
    candidate = (
        project_root / relative_path
    ).resolve(strict=False)

    try:
        candidate.relative_to(project_root)
    except ValueError as error:
        raise ValueError(
            "OUTPUT_OUTSIDE_PROJECT"
        ) from error

    candidate.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return candidate

def _probe_media(
    ffprobe: str,
    path: Path,
) -> dict[str, Any]:
    process = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )

    _require_success(
        process,
        "FFPROBE_FAILED",
    )

    result = json.loads(process.stdout)

    if not isinstance(result, dict):
        raise RuntimeError(
            "FFPROBE_RESULT_INVALID"
        )

    return result


def _ffmpeg_filter_path(path: Path) -> str:
    value = path.resolve().as_posix()
    value = value.replace(":", r"\:")
    value = value.replace("'", r"\'")
    return value


def _motion_filter(
    input_index: int,
    motion: str,
    width: int,
    height: int,
    fps: int,
    duration_seconds: float,
) -> str:
    source = f"[{input_index}:v]"

    oversized_width = width + 320
    oversized_height = height + 180

    base = (
        f"{source}"
        f"scale={oversized_width}:{oversized_height}:"
        "force_original_aspect_ratio=increase,"
    )

    if motion == "PUSH_IN":
        motion_filter = (
            "zoompan="
            "z='min(zoom+0.00035,1.06)':"
            "x='iw/2-iw/zoom/2':"
            "y='ih/2-ih/zoom/2':"
            f"d=1:s={width}x{height}:fps={fps}"
        )

    elif motion == "PULL_OUT":
        motion_filter = (
            "zoompan="
            "z='if(eq(on,1),1.06,max(zoom-0.00035,1.0))':"
            "x='iw/2-iw/zoom/2':"
            "y='ih/2-ih/zoom/2':"
            f"d=1:s={width}x{height}:fps={fps}"
        )

    elif motion == "PAN_LEFT_TO_RIGHT":
        motion_filter = (
            f"crop={width}:{height}:"
            "x='(in_w-out_w)*"
            f"min(t/{duration_seconds:.6f},1)':"
            "y='(in_h-out_h)/2'"
        )

    elif motion == "PAN_RIGHT_TO_LEFT":
        motion_filter = (
            f"crop={width}:{height}:"
            "x='(in_w-out_w)*"
            f"(1-min(t/{duration_seconds:.6f},1))':"
            "y='(in_h-out_h)/2'"
        )

    else:
        motion_filter = (
            f"crop={width}:{height}:"
            "x='(in_w-out_w)/2':"
            "y='(in_h-out_h)/2'"
        )

    return (
        base
        + motion_filter
        + f",trim=duration={duration_seconds:.6f}"
        + ",setpts=PTS-STARTPTS"
        + ",format=yuv420p"
        + f"[scene{input_index}]"
    )


def _transition_filters(
    label: str,
    transition: str,
    duration_seconds: float,
) -> str:
    fade_duration = min(
        0.45,
        max(0.12, duration_seconds / 5),
    )

    fade_out_start = max(
        0,
        duration_seconds - fade_duration,
    )

    if transition == "CUT":
        return f"[{label}]null[{label}out]"

    if transition == "DIP_TO_BLACK":
        return (
            f"[{label}]"
            f"fade=t=in:st=0:d={fade_duration:.3f}:color=black,"
            f"fade=t=out:st={fade_out_start:.3f}:"
            f"d={fade_duration:.3f}:color=black"
            f"[{label}out]"
        )

    return (
        f"[{label}]"
        f"fade=t=in:st=0:d={fade_duration:.3f},"
        f"fade=t=out:st={fade_out_start:.3f}:"
        f"d={fade_duration:.3f}"
        f"[{label}out]"
    )

def _build_audio_filters(
    audio_layers: list[dict[str, Any]],
    first_audio_input: int,
    total_duration_seconds: float,
) -> tuple[list[str], str]:
    filters: list[str] = []
    output_labels: list[str] = []

    for index, layer in enumerate(
        audio_layers
    ):
        input_index = first_audio_input + index
        output_label = f"audio{index}"

        output_labels.append(
            f"[{output_label}]"
        )

        start_ms = int(
            layer.get("start_ms", 0)
        )

        gain_db = float(
            layer.get("gain_db", 0)
        )

        delay_expression = (
            f"{start_ms}|{start_ms}"
        )

        filters.append(
            f"[{input_index}:a]"
            f"adelay={delay_expression},"
            f"volume={gain_db}dB,"
            "apad,"
            f"atrim=duration={total_duration_seconds:.6f},"
            "asetpts=PTS-STARTPTS"
            f"[{output_label}]"
        )

    if len(output_labels) == 1:
        filters.append(
            f"{output_labels[0]}"
            "anull[finalaudio]"
        )

        return filters, "finalaudio"

    filters.append(
        "".join(output_labels)
        + f"amix=inputs={len(output_labels)}:"
        + "duration=longest:"
        + "dropout_transition=0:"
        + "normalize=0,"
        + "alimiter=limit=0.95"
        + "[finalaudio]"
    )

    return filters, "finalaudio"


def _subtitle_filter(
    subtitle_mode: str,
    subtitle_path: Path | None,
) -> str | None:
    if subtitle_mode != "BURNED_IN":
        return None

    if subtitle_path is None:
        raise ValueError(
            "BURNED_SUBTITLE_PATH_REQUIRED"
        )

    escaped = _ffmpeg_filter_path(
        subtitle_path
    )

    return (
        f"subtitles='{escaped}':"
        "charenc=UTF-8"
    )


def _copy_sidecar_subtitles(
    source: Path,
    output_video: Path,
) -> Path:
    extension = (
        source.suffix
        if source.suffix
        else ".srt"
    )

    target = output_video.with_suffix(
        extension
    )

    shutil.copy2(
        source,
        target,
    )

    return target

class EpisodeRenderAdapterV2:
    """Render exact timed scenes, audio layers and subtitles."""

    def __init__(
        self,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
    ) -> None:
        self.ffmpeg = _resolve_executable(
            ffmpeg
        )

        self.ffprobe = _resolve_executable(
            ffprobe
        )

    def render(
        self,
        project_root: str | Path,
        manifest_path: str | Path,
        replace: bool = False,
    ) -> EpisodeRenderV2Result:
        root = Path(project_root).resolve()

        if not root.is_dir():
            raise FileNotFoundError(
                f"PROJECT_ROOT_NOT_FOUND:{root}"
            )

        manifest_file = Path(
            manifest_path
        )

        if not manifest_file.is_absolute():
            manifest_file = (
                root / manifest_file
            )

        manifest_file = (
            manifest_file.resolve()
        )

        if not manifest_file.is_file():
            raise FileNotFoundError(
                f"MANIFEST_NOT_FOUND:{manifest_file}"
            )

        manifest = _read_json(
            manifest_file
        )

        validate_episode_render_manifest_v2(
            manifest
        )

        scenes = manifest["scenes"]
        audio_layers = manifest[
            "audio_layers"
        ]

        subtitles = manifest.get(
            "subtitles",
            {"mode": "NONE"},
        )

        video_config = manifest.get(
            "video",
            {},
        )

        width = int(
            video_config.get(
                "width",
                1920,
            )
        )

        height = int(
            video_config.get(
                "height",
                1080,
            )
        )

        fps = int(
            video_config.get(
                "fps",
                24,
            )
        )

        total_duration_seconds = (
            int(scenes[-1]["end_ms"])
            / 1000
        )

        scene_paths = [
            _resolve_project_file(
                root,
                str(
                    scene[
                        "visual_asset_path"
                    ]
                ),
                f"SCENE_{index}_ASSET",
            )
            for index, scene in enumerate(
                scenes
            )
        ]

        audio_paths = [
            _resolve_project_file(
                root,
                str(layer["path"]),
                f"AUDIO_{index}",
            )
            for index, layer in enumerate(
                audio_layers
            )
        ]

        subtitle_mode = str(
            subtitles.get(
                "mode",
                "NONE",
            )
        )

        subtitle_path: Path | None = None

        if subtitle_mode != "NONE":
            subtitle_path = (
                _resolve_project_file(
                    root,
                    str(subtitles["path"]),
                    "SUBTITLE",
                )
            )

        output_path = (
            _resolve_output_file(
                root,
                str(
                    manifest[
                        "output"
                    ]["video"]
                ),
            )
        )

        report_path = (
            _resolve_output_file(
                root,
                str(
                    manifest[
                        "output"
                    ]["report"]
                ),
            )
        )

        if output_path.exists():
            if not replace:
                raise FileExistsError(
                    f"ARTIFACT_EXISTS:{output_path}"
                )

            output_path.unlink()

        command: list[str] = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
        ]

        for scene, scene_path in zip(
            scenes,
            scene_paths,
            strict=True,
        ):
            duration_seconds = (
                int(scene["duration_ms"])
                / 1000
            )

            command.extend(
                [
                    "-loop",
                    "1",
                    "-framerate",
                    str(fps),
                    "-t",
                    f"{duration_seconds:.6f}",
                    "-i",
                    str(scene_path),
                ]
            )

        for audio_path in audio_paths:
            command.extend(
                [
                    "-i",
                    str(audio_path),
                ]
            )

        filters: list[str] = []
        concat_labels: list[str] = []

        for index, scene in enumerate(
            scenes
        ):
            duration_seconds = (
                int(scene["duration_ms"])
                / 1000
            )

            filters.append(
                _motion_filter(
                    input_index=index,
                    motion=str(
                        scene.get(
                            "motion",
                            "STATIC",
                        )
                    ),
                    width=width,
                    height=height,
                    fps=fps,
                    duration_seconds=(
                        duration_seconds
                    ),
                )
            )

            label = f"scene{index}"

            filters.append(
                _transition_filters(
                    label=label,
                    transition=str(
                        scene.get(
                            "transition",
                            "CUT",
                        )
                    ),
                    duration_seconds=(
                        duration_seconds
                    ),
                )
            )

            concat_labels.append(
                f"[{label}out]"
            )

        filters.append(
            "".join(concat_labels)
            + f"concat=n={len(scenes)}:"
            + "v=1:a=0"
            + "[joinedvideo]"
        )

        subtitle_expression = (
            _subtitle_filter(
                subtitle_mode,
                subtitle_path,
            )
        )

        if subtitle_expression:
            filters.append(
                "[joinedvideo]"
                + subtitle_expression
                + "[finalvideo]"
            )
        else:
            filters.append(
                "[joinedvideo]"
                "null[finalvideo]"
            )

        (
            audio_filters,
            audio_label,
        ) = _build_audio_filters(
            audio_layers=audio_layers,
            first_audio_input=len(
                scenes
            ),
            total_duration_seconds=(
                total_duration_seconds
            ),
        )

        filters.extend(
            audio_filters
        )

        command.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[finalvideo]",
                "-map",
                f"[{audio_label}]",
                "-t",
                f"{total_duration_seconds:.6f}",
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )

        process = _run(
            command
        )

        _require_success(
            process,
            "EPISODE_RENDER_V2_FAILED",
        )

        sidecar_output: str | None = None

        if (
            subtitle_mode == "SIDECAR"
            and subtitle_path is not None
        ):
            copied = (
                _copy_sidecar_subtitles(
                    subtitle_path,
                    output_path,
                )
            )

            sidecar_output = str(
                copied
            )

        probe = _probe_media(
            self.ffprobe,
            output_path,
        )

        video_stream = next(
            (
                stream
                for stream in probe.get(
                    "streams",
                    [],
                )
                if stream.get(
                    "codec_type"
                )
                == "video"
            ),
            {},
        )

        audio_stream = next(
            (
                stream
                for stream in probe.get(
                    "streams",
                    [],
                )
                if stream.get(
                    "codec_type"
                )
                == "audio"
            ),
            {},
        )

        actual_duration = float(
            probe.get(
                "format",
                {},
            ).get(
                "duration",
                0,
            )
        )

        checks = {
            "video_codec": (
                video_stream.get(
                    "codec_name"
                )
                == "h264"
            ),
            "audio_codec": (
                audio_stream.get(
                    "codec_name"
                )
                == "aac"
            ),
            "resolution": (
                video_stream.get(
                    "width"
                )
                == width
                and video_stream.get(
                    "height"
                )
                == height
            ),
            "duration": (
                abs(
                    actual_duration
                    - total_duration_seconds
                )
                <= 0.75
            ),
            "scene_count": (
                len(scene_paths)
                == len(scenes)
            ),
            "audio_layer_count": (
                len(audio_paths)
                == len(audio_layers)
            ),
            "subtitle_mode": (
                subtitle_mode
                in {
                    "NONE",
                    "SIDECAR",
                    "BURNED_IN",
                }
            ),
            "sidecar_created": (
                subtitle_mode
                != "SIDECAR"
                or (
                    sidecar_output
                    is not None
                    and Path(
                        sidecar_output
                    ).is_file()
                )
            ),
        }

        status = (
            "VALID"
            if all(checks.values())
            else "INVALID"
        )

        report = {
            "schema_version": (
                RENDER_ADAPTER_V2_REPORT_SCHEMA
            ),
            "episode_id": (
                manifest["episode_id"]
            ),
            "status": status,
            "manifest": str(
                manifest_file
            ),
            "output": str(
                output_path
            ),
            "sidecar_subtitles": (
                sidecar_output
            ),
            "planned_duration_seconds": (
                total_duration_seconds
            ),
            "actual_duration_seconds": (
                actual_duration
            ),
            "scene_count": len(
                scenes
            ),
            "audio_layer_count": len(
                audio_layers
            ),
            "subtitle_mode": (
                subtitle_mode
            ),
            "checks": checks,
            "output_sha256": sha256(
                output_path.read_bytes()
            ).hexdigest(),
            "ffmpeg_command": command,
            "ffprobe": probe,
        }

        _write_json(
            report_path,
            report,
        )

        return EpisodeRenderV2Result(
            status=status,
            output=str(output_path),
            report=str(report_path),
            manifest=str(
                manifest_file
            ),
            checks=checks,
        )


def render_episode_manifest_v2(
    project_root: str | Path,
    manifest_path: str | Path,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    replace: bool = False,
) -> dict[str, Any]:
    adapter = EpisodeRenderAdapterV2(
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
    )

    result = adapter.render(
        project_root=project_root,
        manifest_path=manifest_path,
        replace=replace,
    )

    return {
        "status": result.status,
        "output": result.output,
        "report": result.report,
        "manifest": result.manifest,
        "checks": result.checks,
    }