"""Deterministic local MP4 vertical-slice production helpers."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from src.application.operations_common import CANONICAL_TIMESTAMP, deterministic_id
from src.application.project_runtime import load_project, project_paths

PRODUCTION_SLICE_SCHEMA_VERSION = "siraj-local-production-v1"
BRIEF_SCHEMA_VERSION = "siraj-production-brief-v1"
SCRIPT_SCHEMA_VERSION = "siraj-production-script-v1"
STORYBOARD_SCHEMA_VERSION = "siraj-production-storyboard-v1"
SUBTITLE_SCHEMA_VERSION = "siraj-production-subtitles-v1"
RENDER_MANIFEST_SCHEMA_VERSION = "siraj-production-render-manifest-v1"
RENDER_VERIFICATION_SCHEMA_VERSION = "siraj-production-render-verification-v1"

WIDTH = 1920
HEIGHT = 1080
FRAME_RATE = 25
SCENE_DURATION_MS = 2000
MAX_SCENES = 8
MIN_SCENES = 5
_COLORS = ("0x14213d", "0x1d3557", "0x264653", "0x3d405b", "0x4a4e69", "0x283618", "0x5f0f40", "0x003049")


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _write_json(path: Path, payload: Any, *, replace: bool) -> None:
    if path.exists() and not replace:
        raise FileExistsError(f"ARTIFACT_EXISTS:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, prefix=".siraj-", suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(_canonical_json(payload))
        handle.flush()
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_text(path: Path, content: str, *, replace: bool) -> None:
    if path.exists() and not replace:
        raise FileExistsError(f"ARTIFACT_EXISTS:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, prefix=".siraj-", suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"ARTIFACT_NOT_FOUND:{path}")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"INVALID_ARTIFACT:{path}")
    return payload


def _root(project_root: str | Path) -> Path:
    root = Path(project_root).expanduser()
    if not root.is_absolute():
        raise ValueError("PROJECT_ROOT_MUST_BE_ABSOLUTE")
    root = root.resolve(strict=False)
    load_project(root)
    return root


def _layout(root: Path) -> dict[str, Path]:
    paths = project_paths(root)
    work = Path(paths.working_root) / "production-v1"
    return {
        "brief": Path(paths.manifests_root) / "production-brief-v1.json",
        "script": work / "script-v1.json",
        "storyboard": work / "storyboard-v1.json",
        "subtitles": work / "subtitles-v1.srt",
        "manifest": Path(paths.manifests_root) / "render-manifest-v1.json",
        "verification": Path(paths.manifests_root) / "render-verification-v1.json",
        "assets": work / "assets",
        "video": Path(paths.exports_root) / "first-documentary.mp4",
    }


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _claims(root: Path) -> list[dict[str, Any]]:
    payload = _read_json(root / "working" / "knowledge" / "claims.json")
    claims = payload.get("claims")
    if not isinstance(claims, list):
        raise ValueError("INVALID_CLAIMS_ARTIFACT")
    selected = [claim for claim in claims if isinstance(claim, dict) and isinstance(claim.get("claim_id"), str) and isinstance(claim.get("claim_text"), str) and claim["claim_text"].strip()]
    selected.sort(key=lambda claim: claim["claim_id"])
    if len(selected) < MIN_SCENES:
        raise ValueError("INSUFFICIENT_CLAIMS_FOR_PRODUCTION")
    return selected[:MAX_SCENES]


def initialize_production(project_root: str | Path, *, replace: bool = False) -> dict[str, Any]:
    root = _root(project_root)
    project = load_project(root)
    layout = _layout(root)
    claims = _claims(root)
    production_id = deterministic_id("local_production", [project["project_id"], [claim["claim_id"] for claim in claims]])
    brief = {
        "schema_version": BRIEF_SCHEMA_VERSION,
        "production_id": production_id,
        "project_id": project["project_id"],
        "title": project["topic"],
        "language": project["language"],
        "created_at": CANONICAL_TIMESTAMP,
        "target": {"width": WIDTH, "height": HEIGHT, "frame_rate": FRAME_RATE, "duration_ms": len(claims) * SCENE_DURATION_MS},
        "audio": {"mode": "SILENT_PLACEHOLDER", "stream_required": True, "fallback_reason": "LOCAL_TTS_NOT_CONFIGURED"},
    }
    scenes = []
    for position, claim in enumerate(claims):
        scene_id = deterministic_id("local_scene", [production_id, position, claim["claim_id"]])
        scenes.append({
            "scene_id": scene_id,
            "position": position,
            "claim_id": claim["claim_id"],
            "evidence_ids": sorted(str(item) for item in claim.get("evidence_ids", []) if isinstance(item, str)),
            "text": " ".join(claim["claim_text"].split()),
            "duration_ms": SCENE_DURATION_MS,
        })
    script = {"schema_version": SCRIPT_SCHEMA_VERSION, "production_id": production_id, "created_at": CANONICAL_TIMESTAMP, "scenes": scenes}
    _write_json(layout["brief"], brief, replace=replace)
    _write_json(layout["script"], script, replace=replace)
    return {"production_id": production_id, "brief": _relative(root, layout["brief"]), "script": _relative(root, layout["script"]), "scene_count": len(scenes)}


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=False)


def _require_success(process: subprocess.CompletedProcess[str], code: str) -> None:
    if process.returncode != 0:
        detail = process.stderr.strip().splitlines()[-1] if process.stderr.strip() else "NO_STDERR"
        raise RuntimeError(f"{code}:{process.returncode}:{detail}")


def build_storyboard(project_root: str | Path, *, ffmpeg: str = "ffmpeg", replace: bool = False) -> dict[str, Any]:
    root = _root(project_root)
    layout = _layout(root)
    script = _read_json(layout["script"])
    if script.get("schema_version") != SCRIPT_SCHEMA_VERSION:
        raise ValueError("INVALID_PRODUCTION_SCRIPT_SCHEMA")
    scenes = script.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("PRODUCTION_SCRIPT_SCENES_REQUIRED")
    frames = []
    for scene in sorted(scenes, key=lambda item: int(item["position"])):
        position = int(scene["position"])
        asset = layout["assets"] / f"scene-{position + 1:02d}.png"
        if asset.exists() and not replace:
            raise FileExistsError(f"ARTIFACT_EXISTS:{asset}")
        asset.parent.mkdir(parents=True, exist_ok=True)
        process = _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=c={_COLORS[position % len(_COLORS)]}:s={WIDTH}x{HEIGHT}:r={FRAME_RATE}", "-frames:v", "1", str(asset)])
        _require_success(process, "PLACEHOLDER_ASSET_FAILED")
        frames.append({
            "frame_id": deterministic_id("local_storyboard_frame", [scene["scene_id"], position]),
            "scene_id": scene["scene_id"],
            "position": position,
            "asset_path": _relative(root, asset),
            "asset_type": "LOCAL_COLOR_PLACEHOLDER",
            "claim_id": scene["claim_id"],
            "evidence_ids": scene["evidence_ids"],
            "duration_ms": int(scene["duration_ms"]),
        })
    storyboard = {"schema_version": STORYBOARD_SCHEMA_VERSION, "production_id": script["production_id"], "created_at": CANONICAL_TIMESTAMP, "frames": frames}
    _write_json(layout["storyboard"], storyboard, replace=replace)
    return {"storyboard": _relative(root, layout["storyboard"]), "asset_count": len(frames), "asset_root": _relative(root, layout["assets"])}


def _srt_time(milliseconds: int) -> str:
    hours, remaining = divmod(milliseconds, 3_600_000)
    minutes, remaining = divmod(remaining, 60_000)
    seconds, millis = divmod(remaining, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def build_subtitles(project_root: str | Path, *, replace: bool = False) -> dict[str, Any]:
    root = _root(project_root)
    layout = _layout(root)
    script = _read_json(layout["script"])
    scenes = sorted(script.get("scenes", []), key=lambda item: int(item["position"]))
    if not scenes:
        raise ValueError("PRODUCTION_SCRIPT_SCENES_REQUIRED")
    blocks = []
    start = 0
    for index, scene in enumerate(scenes, start=1):
        end = start + int(scene["duration_ms"])
        blocks.append(f"{index}\n{_srt_time(start)} --> {_srt_time(end)}\n{scene['text']}")
        start = end
    _write_text(layout["subtitles"], "\n\n".join(blocks) + "\n", replace=replace)
    return {"schema_version": SUBTITLE_SCHEMA_VERSION, "subtitles": _relative(root, layout["subtitles"]), "cue_count": len(scenes), "duration_ms": start}


def build_render(project_root: str | Path, *, ffmpeg: str = "ffmpeg", replace: bool = False) -> dict[str, Any]:
    root = _root(project_root)
    layout = _layout(root)
    storyboard = _read_json(layout["storyboard"])
    frames = sorted(storyboard.get("frames", []), key=lambda item: int(item["position"]))
    if not frames:
        raise ValueError("STORYBOARD_FRAMES_REQUIRED")
    if layout["video"].exists() and not replace:
        raise FileExistsError(f"ARTIFACT_EXISTS:{layout['video']}")
    if not layout["subtitles"].is_file():
        raise FileNotFoundError(f"ARTIFACT_NOT_FOUND:{layout['subtitles']}")
    inputs: list[str] = []
    filter_inputs: list[str] = []
    for index, frame in enumerate(frames):
        asset = root / frame["asset_path"]
        if not asset.is_file():
            raise FileNotFoundError(f"ASSET_NOT_FOUND:{asset}")
        duration = f"{int(frame['duration_ms']) / 1000:.3f}"
        inputs.extend(["-loop", "1", "-t", duration, "-i", str(asset)])
        filter_inputs.append(f"[{index}:v]")
    video_filter = "".join(filter_inputs) + f"concat=n={len(frames)}:v=1:a=0,format=yuv420p[v]"
    total_duration_ms = sum(int(frame["duration_ms"]) for frame in frames)
    audio_index = len(frames)
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inputs, "-f", "lavfi", "-t", f"{total_duration_ms / 1000:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000", "-filter_complex", video_filter, "-map", "[v]", "-map", f"{audio_index}:a", "-r", str(FRAME_RATE), "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", str(layout["video"])]
    manifest = {
        "schema_version": RENDER_MANIFEST_SCHEMA_VERSION,
        "production_id": storyboard["production_id"],
        "created_at": CANONICAL_TIMESTAMP,
        "output": _relative(root, layout["video"]),
        "subtitles": _relative(root, layout["subtitles"]),
        "video": {"codec": "h264", "width": WIDTH, "height": HEIGHT, "frame_rate": FRAME_RATE},
        "audio": {"codec": "aac", "mode": "SILENT_PLACEHOLDER", "sample_rate": 48000, "channels": 2},
        "frames": frames,
        "duration_ms": total_duration_ms,
    }
    _write_json(layout["manifest"], manifest, replace=replace)
    process = _run(command)
    _require_success(process, "FFMPEG_RENDER_FAILED")
    if not layout["video"].is_file() or layout["video"].stat().st_size == 0:
        raise RuntimeError("FFMPEG_RENDER_EMPTY_OUTPUT")
    return {"manifest": _relative(root, layout["manifest"]), "video": _relative(root, layout["video"]), "size_bytes": layout["video"].stat().st_size, "duration_ms": total_duration_ms, "command_sha256": sha256("\0".join(command[:-1]).encode("utf-8")).hexdigest()}


def verify_render(project_root: str | Path, *, ffprobe: str = "ffprobe", replace: bool = False) -> dict[str, Any]:
    root = _root(project_root)
    layout = _layout(root)
    video = layout["video"]
    if not video.is_file():
        raise FileNotFoundError(f"ARTIFACT_NOT_FOUND:{video}")
    process = _run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)])
    _require_success(process, "FFPROBE_FAILED")
    payload = json.loads(process.stdout)
    streams = payload.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    video_stream = video_streams[0] if video_streams else {}
    audio_stream = audio_streams[0] if audio_streams else {}
    duration_seconds = float(payload.get("format", {}).get("duration", "0") or 0)
    checks = {
        "h264_video": video_stream.get("codec_name") == "h264",
        "aac_audio": audio_stream.get("codec_name") == "aac",
        "resolution_1920x1080": video_stream.get("width") == WIDTH and video_stream.get("height") == HEIGHT,
        "positive_duration": duration_seconds > 0,
        "video_stream_present": bool(video_streams),
        "audio_stream_present": bool(audio_streams),
    }
    report = {"schema_version": RENDER_VERIFICATION_SCHEMA_VERSION, "created_at": CANONICAL_TIMESTAMP, "video": _relative(root, video), "status": "VALID" if all(checks.values()) else "INVALID", "checks": checks, "ffprobe": payload}
    _write_json(layout["verification"], report, replace=replace)
    return {"verification": _relative(root, layout["verification"]), "status": report["status"], "checks": checks, "duration_seconds": duration_seconds}
