"""Manifest-driven local video rendering adapter."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any


RENDER_ADAPTER_SCHEMA_VERSION = (
    "siraj-local-video-render-manifest-v1"
)

RENDER_REPORT_SCHEMA_VERSION = (
    "siraj-local-video-render-report-v1"
)


@dataclass(frozen=True)
class LocalVideoRenderResult:
    status: str
    output: str
    report: str
    manifest: str
    checks: dict[str, bool]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8-sig")
    )

    if not isinstance(value, dict):
        raise ValueError("RENDER_MANIFEST_NOT_OBJECT")

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


def _require(
    process: subprocess.CompletedProcess[str],
    code: str,
) -> None:
    if process.returncode != 0:
        detail = (
            process.stderr[-4000:]
            or process.stdout[-4000:]
        )

        raise RuntimeError(
            f"{code}:{detail}"
        )


def _resolve_executable(
    requested: str,
) -> str:
    candidate = Path(requested)

    if candidate.is_file():
        return str(candidate)

    resolved = shutil.which(requested)

    if not resolved:
        raise FileNotFoundError(
            f"EXECUTABLE_NOT_FOUND:{requested}"
        )

    return resolved


def _project_file(
    root: Path,
    relative_path: str,
    *,
    code: str,
) -> Path:
    if not relative_path:
        raise ValueError(f"{code}_PATH_EMPTY")

    candidate = (
        root / relative_path
    ).resolve(strict=False)

    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(
            f"{code}_OUTSIDE_PROJECT"
        ) from error

    if not candidate.is_file():
        raise FileNotFoundError(
            f"{code}_NOT_FOUND:{candidate}"
        )

    return candidate


def _output_file(
    root: Path,
    relative_path: str,
) -> Path:
    candidate = (
        root / relative_path
    ).resolve(strict=False)

    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "OUTPUT_OUTSIDE_PROJECT"
        ) from error

    candidate.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return candidate


def _validate_manifest(
    manifest: dict[str, Any],
) -> None:
    if (
        manifest.get("schema_version")
        != RENDER_ADAPTER_SCHEMA_VERSION
    ):
        raise ValueError(
            "RENDER_MANIFEST_SCHEMA_INVALID"
        )

    render_id = str(
        manifest.get("render_id", "")
    ).strip()

    if not render_id:
        raise ValueError("RENDER_ID_REQUIRED")

    video = manifest.get("video")

    if not isinstance(video, dict):
        raise ValueError(
            "VIDEO_CONFIGURATION_REQUIRED"
        )

    width = video.get("width")
    height = video.get("height")
    fps = video.get("fps")

    if (
        not isinstance(width, int)
        or width < 320
        or width > 7680
    ):
        raise ValueError("VIDEO_WIDTH_INVALID")

    if (
        not isinstance(height, int)
        or height < 240
        or height > 4320
    ):
        raise ValueError("VIDEO_HEIGHT_INVALID")

    if (
        not isinstance(fps, int)
        or fps < 12
        or fps > 120
    ):
        raise ValueError("VIDEO_FPS_INVALID")

    assets = manifest.get("assets")

    if (
        not isinstance(assets, list)
        or not assets
    ):
        raise ValueError("VIDEO_ASSETS_REQUIRED")

    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            raise ValueError(
                f"VIDEO_ASSET_INVALID:{index}"
            )

        if not str(
            asset.get("path", "")
        ).strip():
            raise ValueError(
                f"VIDEO_ASSET_PATH_REQUIRED:{index}"
            )

        motion = asset.get(
            "motion",
            "STATIC",
        )

        if motion not in {
            "STATIC",
            "PUSH_IN",
            "PAN_LEFT_TO_RIGHT",
            "PAN_RIGHT_TO_LEFT",
        }:
            raise ValueError(
                f"VIDEO_ASSET_MOTION_INVALID:{index}"
            )

    audio = manifest.get("audio")

    if (
        not isinstance(audio, dict)
        or not str(
            audio.get("path", "")
        ).strip()
    ):
        raise ValueError("FINAL_AUDIO_REQUIRED")

    output = manifest.get("output")

    if (
        not isinstance(output, dict)
        or not str(
            output.get("video", "")
        ).strip()
        or not str(
            output.get("report", "")
        ).strip()
    ):
        raise ValueError(
            "RENDER_OUTPUT_CONFIGURATION_REQUIRED"
        )


def _probe(
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

    _require(
        process,
        "RENDER_FFPROBE_FAILED",
    )

    value = json.loads(process.stdout)

    if not isinstance(value, dict):
        raise RuntimeError(
            "RENDER_FFPROBE_INVALID"
        )

    return value


def _audio_volume(
    ffmpeg: str,
    path: Path,
) -> tuple[float | None, float | None]:
    process = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ]
    )

    mean_match = re.search(
        r"mean_volume:\s*(-?[0-9.]+) dB",
        process.stderr,
    )

    max_match = re.search(
        r"max_volume:\s*(-?[0-9.]+) dB",
        process.stderr,
    )

    mean = (
        float(mean_match.group(1))
        if mean_match
        else None
    )

    maximum = (
        float(max_match.group(1))
        if max_match
        else None
    )

    return mean, maximum


def _black_frame_free(
    ffmpeg: str,
    video: Path,
    duration_seconds: float,
) -> bool:
    positions = (
        max(0.1, duration_seconds * 0.05),
        duration_seconds * 0.50,
        max(0.1, duration_seconds * 0.90),
    )

    for position in positions:
        process = _run(
            [
                ffmpeg,
                "-hide_banner",
                "-ss",
                f"{position:.3f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-vf",
                "signalstats,metadata=print",
                "-f",
                "null",
                "-",
            ]
        )

        values = re.findall(
            r"lavfi\.signalstats\.YAVG=([0-9.]+)",
            process.stderr,
        )

        if (
            process.returncode != 0
            or not values
            or float(values[-1]) < 4.0
        ):
            return False

    return True


def _visual_filter(
    *,
    input_index: int,
    motion: str,
    width: int,
    height: int,
    fps: int,
    duration_seconds: float,
) -> str:
    label = f"v{input_index}"

    base = (
        f"[{input_index}:v]"
        f"scale={width + 384}:{height + 216}"
    )

    if motion == "PUSH_IN":
        operation = (
            ",zoompan="
            "z='min(zoom+0.00030,1.045)':"
            "x='iw/2-iw/zoom/2':"
            "y='ih/2-ih/zoom/2':"
            f"d=1:s={width}x{height}:fps={fps}"
        )

    elif motion == "PAN_LEFT_TO_RIGHT":
        operation = (
            f",crop={width}:{height}:"
            "x='(in_w-out_w)*"
            f"min(t/{duration_seconds:.6f},1)':"
            "y='(in_h-out_h)/2'"
        )

    elif motion == "PAN_RIGHT_TO_LEFT":
        operation = (
            f",crop={width}:{height}:"
            "x='(in_w-out_w)*"
            f"(1-min(t/{duration_seconds:.6f},1))':"
            "y='(in_h-out_h)/2'"
        )

    else:
        operation = (
            f",crop={width}:{height}:"
            "x='(in_w-out_w)/2':"
            "y='(in_h-out_h)/2'"
        )

    return (
        base
        + operation
        + f",trim=duration={duration_seconds:.6f}"
        + ",setpts=PTS-STARTPTS"
        + f"[{label}]"
    )


def _build_video_filter(
    *,
    assets: list[dict[str, Any]],
    width: int,
    height: int,
    fps: int,
    total_duration_seconds: float,
    transition_seconds: float,
) -> tuple[list[str], str]:
    count = len(assets)

    if count == 1:
        segment_duration = (
            total_duration_seconds
        )
    else:
        segment_duration = (
            total_duration_seconds
            + transition_seconds * (count - 1)
        ) / count

    filters = [
        _visual_filter(
            input_index=index,
            motion=str(
                asset.get("motion", "STATIC")
            ),
            width=width,
            height=height,
            fps=fps,
            duration_seconds=segment_duration,
        )
        for index, asset in enumerate(assets)
    ]

    if count == 1:
        filters.append(
            "[v0]format=yuv420p[video]"
        )

        return filters, "video"

    previous_label = "v0"

    for index in range(1, count):
        output_label = (
            "video"
            if index == count - 1
            else f"vx{index}"
        )

        offset = (
            index
            * (
                segment_duration
                - transition_seconds
            )
        )

        transition = (
            "fade"
            if index % 2
            else "wipeleft"
        )

        filters.append(
            f"[{previous_label}][v{index}]"
            "xfade="
            f"transition={transition}:"
            f"duration={transition_seconds:.6f}:"
            f"offset={offset:.6f},"
            "format=yuv420p"
            f"[{output_label}]"
        )

        previous_label = output_label

    return filters, "video"


class LocalVideoRenderAdapter:
    """Render an MP4 from a validated project-relative manifest."""

    def __init__(
        self,
        *,
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
        *,
        replace: bool = False,
    ) -> LocalVideoRenderResult:
        root = Path(project_root).resolve()

        if not root.is_dir():
            raise FileNotFoundError(
                f"PROJECT_ROOT_NOT_FOUND:{root}"
            )

        source_manifest_path = Path(
            manifest_path
        )

        if not source_manifest_path.is_absolute():
            source_manifest_path = (
                root / source_manifest_path
            )

        source_manifest_path = (
            source_manifest_path.resolve()
        )

        manifest = _read_json(
            source_manifest_path
        )

        _validate_manifest(manifest)

        video_config = manifest["video"]
        width = int(video_config["width"])
        height = int(video_config["height"])
        fps = int(video_config["fps"])

        transition_ms = int(
            video_config.get(
                "transition_ms",
                450,
            )
        )

        if (
            transition_ms < 0
            or transition_ms > 3000
        ):
            raise ValueError(
                "VIDEO_TRANSITION_DURATION_INVALID"
            )

        assets = manifest["assets"]

        asset_paths = [
            _project_file(
                root,
                str(asset["path"]),
                code=f"VIDEO_ASSET_{index}",
            )
            for index, asset in enumerate(
                assets
            )
        ]

        audio_path = _project_file(
            root,
            str(manifest["audio"]["path"]),
            code="FINAL_AUDIO",
        )

        output_path = _output_file(
            root,
            str(
                manifest["output"]["video"]
            ),
        )

        report_path = _output_file(
            root,
            str(
                manifest["output"]["report"]
            ),
        )

        if output_path.exists():
            if not replace:
                raise FileExistsError(
                    f"ARTIFACT_EXISTS:{output_path}"
                )

            output_path.unlink()

        audio_probe = _probe(
            self.ffprobe,
            audio_path,
        )

        duration_seconds = float(
            audio_probe.get(
                "format",
                {},
            ).get(
                "duration",
                0,
            )
        )

        if duration_seconds <= 0:
            raise ValueError(
                "FINAL_AUDIO_DURATION_INVALID"
            )

        visual_inputs: list[str] = []

        asset_segment_duration = (
            duration_seconds
            + (
                transition_ms / 1000
            )
            * (len(asset_paths) - 1)
        ) / len(asset_paths)

        for asset_path in asset_paths:
            visual_inputs.extend(
                [
                    "-loop",
                    "1",
                    "-framerate",
                    str(fps),
                    "-t",
                    f"{asset_segment_duration:.6f}",
                    "-i",
                    str(asset_path),
                ]
            )

        filters, final_label = (
            _build_video_filter(
                assets=assets,
                width=width,
                height=height,
                fps=fps,
                total_duration_seconds=(
                    duration_seconds
                ),
                transition_seconds=(
                    transition_ms / 1000
                ),
            )
        )

        command = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            *visual_inputs,
            "-i",
            str(audio_path),
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{final_label}]",
            "-map",
            f"{len(asset_paths)}:a:0",
            "-t",
            f"{duration_seconds:.6f}",
            "-r",
            str(fps),
            "-c:v",
            str(
                video_config.get(
                    "codec",
                    "libx264",
                )
            ),
            "-preset",
            str(
                video_config.get(
                    "preset",
                    "medium",
                )
            ),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            str(
                manifest["audio"].get(
                    "codec",
                    "aac",
                )
            ),
            "-b:a",
            str(
                manifest["audio"].get(
                    "bitrate",
                    "160k",
                )
            ),
            "-movflags",
            "+faststart",
            str(output_path),
        ]

        render_process = _run(command)

        _require(
            render_process,
            "LOCAL_VIDEO_RENDER_FAILED",
        )

        probe = _probe(
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
                if stream.get("codec_type")
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
                if stream.get("codec_type")
                == "audio"
            ),
            {},
        )

        output_duration = float(
            probe.get(
                "format",
                {},
            ).get(
                "duration",
                0,
            )
        )

        mean_volume, max_volume = (
            _audio_volume(
                self.ffmpeg,
                output_path,
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
                video_stream.get("width")
                == width
                and video_stream.get(
                    "height"
                )
                == height
            ),
            "duration": (
                abs(
                    output_duration
                    - duration_seconds
                )
                <= 0.75
            ),
            "no_black_frames": (
                _black_frame_free(
                    self.ffmpeg,
                    output_path,
                    output_duration,
                )
            ),
            "non_silent_audio": (
                mean_volume is not None
                and mean_volume > -55
            ),
            "no_clipping": (
                max_volume is not None
                and max_volume <= -0.1
            ),
            "assets_present": (
                len(asset_paths)
                == len(assets)
            ),
        }

        status = (
            "VALID"
            if all(checks.values())
            else "INVALID"
        )

        report = {
            "schema_version": (
                RENDER_REPORT_SCHEMA_VERSION
            ),
            "render_id": manifest["render_id"],
            "status": status,
            "source_manifest": str(
                source_manifest_path
            ),
            "output": str(output_path),
            "output_sha256": sha256(
                output_path.read_bytes()
            ).hexdigest(),
            "duration_seconds": (
                output_duration
            ),
            "mean_volume_db": mean_volume,
            "max_volume_db": max_volume,
            "checks": checks,
            "ffmpeg_command": command,
            "ffprobe": probe,
        }

        _write_json(
            report_path,
            report,
        )

        return LocalVideoRenderResult(
            status=status,
            output=str(output_path),
            report=str(report_path),
            manifest=str(
                source_manifest_path
            ),
            checks=checks,
        )


def render_local_video_manifest(
    project_root: str | Path,
    manifest_path: str | Path,
    *,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    replace: bool = False,
) -> dict[str, Any]:
    result = LocalVideoRenderAdapter(
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
    ).render(
        project_root,
        manifest_path,
        replace=replace,
    )

    return {
        "status": result.status,
        "output": result.output,
        "report": result.report,
        "manifest": result.manifest,
        "checks": result.checks,
    }
