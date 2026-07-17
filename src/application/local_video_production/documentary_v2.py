"""Deterministic Windows-local documentary v2 production path.

The v1 vertical slice remains untouched.  This path adds only local speech,
meaningful card assets, timing from generated WAV files, and FFmpeg rendering.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave
from typing import Any

from src.application.operations_common import CANONICAL_TIMESTAMP, deterministic_id
from src.application.project_runtime import load_project, project_paths


DOCUMENTARY_V2_SCHEMA_VERSION = "siraj-local-documentary-v2"
BRIEF_V2_SCHEMA_VERSION = "siraj-production-brief-v2"
SCRIPT_V2_SCHEMA_VERSION = "siraj-production-script-v2"
STORYBOARD_V2_SCHEMA_VERSION = "siraj-production-storyboard-v2"
SUBTITLE_V2_SCHEMA_VERSION = "siraj-production-subtitles-v2"
RENDER_MANIFEST_V2_SCHEMA_VERSION = "siraj-production-render-manifest-v2"
RENDER_VERIFICATION_V2_SCHEMA_VERSION = "siraj-production-render-verification-v2"

WIDTH, HEIGHT, FRAME_RATE = 1920, 1080, 25
MIN_SCENES, MAX_SCENES = 5, 8
SCENE_AUDIO_PAD_MS = 350
_COLORS = ("10233F", "193A5A", "244E55", "4A394E", "344E41", "5D3A2B", "203A43")
_LOUDNORM = "loudnorm=I=-16:LRA=11:TP=-1.5"


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _write(path: Path, content: str, *, replace: bool) -> None:
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


def _write_json(path: Path, payload: Any, *, replace: bool) -> None:
    _write(path, _json(payload), replace=replace)


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
    work = Path(paths.working_root) / "production-v2"
    return {
        "brief": Path(paths.manifests_root) / "production-brief-v2.json",
        "script": work / "script-v2.json",
        "storyboard": work / "storyboard-v2.json",
        "subtitles": work / "subtitles-v2.srt",
        "manifest": Path(paths.manifests_root) / "render-manifest-v2.json",
        "verification": Path(paths.manifests_root) / "render-verification-v2.json",
        "assets": work / "assets",
        "texts": work / "texts",
        "audio": work / "audio",
        "narration": work / "audio" / "narration-v2.wav",
        "video": Path(paths.exports_root) / "first-documentary-v2.mp4",
    }


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _resolve_binary(configured: str | None, name: str) -> str:
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file():
            return str(candidate)
        found = shutil.which(configured)
        if found:
            return found
        raise FileNotFoundError(f"{name.upper()}_NOT_FOUND:{configured}")
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(f"{name.upper()}_NOT_FOUND")


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=False)


def _require(process: subprocess.CompletedProcess[str], code: str) -> None:
    if process.returncode:
        detail = process.stderr.strip().splitlines()[-1] if process.stderr.strip() else "NO_STDERR"
        raise RuntimeError(f"{code}:{process.returncode}:{detail}")


def _claims(root: Path) -> list[dict[str, Any]]:
    payload = _read_json(root / "working" / "knowledge" / "claims.json")
    claims = payload.get("claims")
    if not isinstance(claims, list):
        raise ValueError("INVALID_CLAIMS_ARTIFACT")
    selected = [item for item in claims if isinstance(item, dict) and isinstance(item.get("claim_id"), str) and isinstance(item.get("claim_text"), str) and item["claim_text"].strip()]
    selected.sort(key=lambda item: item["claim_id"])
    if len(selected) < MIN_SCENES:
        raise ValueError("INSUFFICIENT_CLAIMS_FOR_DOCUMENTARY")
    return selected[: MAX_SCENES - 1]


def _spoken_scenes(project: dict[str, Any], claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    intro = {
        "claim_id": "intro",
        "claim_text": f"This is a short documentary about {project['topic']}. It follows documented claims.",
        "evidence_ids": [],
        "visual_role": "TITLE_CARD",
    }
    scenes = [intro]
    for position, claim in enumerate(claims, start=1):
        bridge = f"Historical record {position}. {claim['claim_text']} The evidence anchors this history."
        scenes.append({
            "claim_id": claim["claim_id"],
            "claim_text": bridge,
            "evidence_ids": sorted(str(value) for value in claim.get("evidence_ids", []) if isinstance(value, str)),
            "visual_role": ("TIMELINE" if position == 1 else "MAP_STYLE" if position == 2 else "HISTORICAL_CARD"),
        })
    return scenes


def _wav_duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as audio:
        frames = audio.getnframes()
        rate = audio.getframerate()
    if frames <= 0 or rate <= 0:
        raise ValueError(f"INVALID_NARRATION_WAV:{path}")
    return max(1, round(frames * 1000 / rate))


def _speak_windows(text_path: Path, wav_path: Path, *, powershell: str) -> None:
    output_literal = str(wav_path).replace("'", "''")
    input_literal = str(text_path).replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$speaker.Rate = 2; "
        "$speaker.Volume = 100; "
        f"$speaker.SetOutputToWaveFile('{output_literal}'); "
        f"$speaker.Speak([System.IO.File]::ReadAllText('{input_literal}', [System.Text.Encoding]::UTF8)); "
        "$speaker.Dispose()"
    )
    process = _run([powershell, "-NoProfile", "-NonInteractive", "-Command", script])
    _require(process, "LOCAL_TTS_FAILED")
    if not wav_path.is_file() or wav_path.stat().st_size == 0:
        raise RuntimeError("LOCAL_TTS_EMPTY_OUTPUT")


def initialize_documentary_v2(
    project_root: str | Path,
    *,
    powershell: str = "powershell.exe",
    replace: bool = False,
) -> dict[str, Any]:
    root = _root(project_root)
    project = load_project(root)
    layout = _layout(root)
    claims = _claims(root)
    production_id = deterministic_id("local_documentary_v2", [project["project_id"], [item["claim_id"] for item in claims]])
    scenes = []
    for position, source in enumerate(_spoken_scenes(project, claims)):
        scene_id = deterministic_id("local_documentary_v2_scene", [production_id, position, source["claim_id"]])
        text_path = layout["texts"] / f"scene-{position + 1:02d}.txt"
        wav_path = layout["audio"] / f"scene-{position + 1:02d}.wav"
        _write(text_path, source["claim_text"] + "\n", replace=replace)
        if wav_path.exists() and not replace:
            raise FileExistsError(f"ARTIFACT_EXISTS:{wav_path}")
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        _speak_windows(text_path, wav_path, powershell=powershell)
        narration_ms = _wav_duration_ms(wav_path)
        scenes.append({
            "scene_id": scene_id,
            "position": position,
            "claim_id": source["claim_id"],
            "evidence_ids": source["evidence_ids"],
            "narration_text": source["claim_text"],
            "narration_audio": _relative(root, wav_path),
            "narration_duration_ms": narration_ms,
            "duration_ms": narration_ms + SCENE_AUDIO_PAD_MS,
            "visual_role": source["visual_role"],
        })
    total_duration = sum(scene["duration_ms"] for scene in scenes)
    brief = {
        "schema_version": BRIEF_V2_SCHEMA_VERSION,
        "production_id": production_id,
        "project_id": project["project_id"],
        "title": project["topic"],
        "created_at": CANONICAL_TIMESTAMP,
        "target": {"width": WIDTH, "height": HEIGHT, "frame_rate": FRAME_RATE, "duration_ms": total_duration},
        "audio": {"mode": "WINDOWS_SPEECHSYNTHESIZER", "loudness_normalization": _LOUDNORM, "fallback": "NO_SILENT_FALLBACK"},
    }
    script = {"schema_version": SCRIPT_V2_SCHEMA_VERSION, "production_id": production_id, "created_at": CANONICAL_TIMESTAMP, "scenes": scenes}
    _write_json(layout["brief"], brief, replace=replace)
    _write_json(layout["script"], script, replace=replace)
    return {"production_id": production_id, "brief": _relative(root, layout["brief"]), "script": _relative(root, layout["script"]), "narration_root": _relative(root, layout["audio"]), "scene_count": len(scenes), "duration_ms": total_duration}


def _font_path(configured: str | None) -> str:
    candidates = [Path(configured)] if configured else [Path(r"C:\Windows\Fonts\segoeui.ttf"), Path(r"C:\Windows\Fonts\arial.ttf")]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.as_posix().replace(":", "\\:")
    raise FileNotFoundError("LOCAL_FONT_NOT_FOUND")


def _drawtext_path(path: Path) -> str:
    return path.as_posix().replace(":", "\\:").replace("'", "\\'")


def _visual_caption(scene: dict[str, Any], title: str) -> str:
    role = scene["visual_role"].replace("_", " ")
    if role == "TITLE CARD":
        return f"{title}\nA deterministic local documentary\nDocumented claims only"
    if role == "TIMELINE":
        return f"TIMELINE\n{scene['narration_text']}"
    if role == "MAP STYLE":
        return f"MAP STYLE: BAGHDAD\n{scene['narration_text']}"
    return f"HISTORICAL NOTE\n{scene['narration_text']}"


def _asset_filter(position: int, font: str, text_file: Path) -> str:
    text = _drawtext_path(text_file)
    base = (
        f"color=c=0x{_COLORS[position % len(_COLORS)]}:s={WIDTH}x{HEIGHT}:r={FRAME_RATE},"
        "drawbox=x=85:y=85:w=1750:h=910:color=white@0.15:t=5,"
        "drawbox=x=130:y=760:w=1660:h=150:color=black@0.42:t=fill,"
    )
    if position == 1:
        decoration = "drawbox=x=210:y=460:w=1500:h=8:color=white@0.75:t=fill,drawbox=x=420:y=420:w=26:h=86:color=F4D35E:t=fill,drawbox=x=940:y=420:w=26:h=86:color=F4D35E:t=fill,drawbox=x=1450:y=420:w=26:h=86:color=F4D35E:t=fill,"
    elif position == 2:
        decoration = "drawbox=x=250:y=230:w=1420:h=460:color=6C8EAD@0.28:t=fill,drawbox=x=900:y=240:w=45:h=440:color=5BC0BE@0.85:t=fill,drawbox=x=390:y=330:w=250:h=140:color=white@0.16:t=fill,drawbox=x=1200:y=440:w=230:h=160:color=white@0.16:t=fill,"
    else:
        decoration = "drawbox=x=250:y=205:w=620:h=440:color=F4D35E@0.26:t=fill,drawbox=x=300:y=250:w=520:h=350:color=black@0.30:t=fill,"
    return base + decoration + f"drawtext=fontfile='{font}':textfile='{text}':fontcolor=white:fontsize=46:line_spacing=16:x=170:y=155,drawtext=fontfile='{font}':text='SIRAJ | DOCUMENTED HISTORY':fontcolor=white@0.90:fontsize=28:x=170:y=815"


def build_documentary_v2_storyboard(
    project_root: str | Path,
    *,
    ffmpeg: str | None = None,
    font_path: str | None = None,
    replace: bool = False,
) -> dict[str, Any]:
    root = _root(project_root)
    layout = _layout(root)
    ffmpeg_binary = _resolve_binary(ffmpeg, "ffmpeg")
    font = _font_path(font_path)
    script = _read_json(layout["script"])
    if script.get("schema_version") != SCRIPT_V2_SCHEMA_VERSION:
        raise ValueError("INVALID_DOCUMENTARY_V2_SCRIPT")
    title = _read_json(layout["brief"]).get("title", "SIRAJ Documentary")
    frames = []
    for scene in sorted(script.get("scenes", []), key=lambda item: int(item["position"])):
        position = int(scene["position"])
        caption_path = layout["texts"] / f"visual-{position + 1:02d}.txt"
        asset_path = layout["assets"] / f"scene-{position + 1:02d}.png"
        _write(caption_path, _visual_caption(scene, str(title)) + "\n", replace=replace)
        if asset_path.exists() and not replace:
            raise FileExistsError(f"ARTIFACT_EXISTS:{asset_path}")
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        process = _run([ffmpeg_binary, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", _asset_filter(position, font, caption_path), "-frames:v", "1", str(asset_path)])
        _require(process, "VISUAL_ASSET_RENDER_FAILED")
        frames.append({
            "frame_id": deterministic_id("local_documentary_v2_frame", [scene["scene_id"], position]),
            "scene_id": scene["scene_id"],
            "position": position,
            "asset_path": _relative(root, asset_path),
            "asset_type": "LOCAL_COMPOSITED_DOCUMENTARY_CARD",
            "visual_role": scene["visual_role"],
            "duration_ms": scene["duration_ms"],
            "claim_id": scene["claim_id"],
            "evidence_ids": scene["evidence_ids"],
        })
    result = {"schema_version": STORYBOARD_V2_SCHEMA_VERSION, "production_id": script["production_id"], "created_at": CANONICAL_TIMESTAMP, "frames": frames}
    _write_json(layout["storyboard"], result, replace=replace)
    return {"storyboard": _relative(root, layout["storyboard"]), "asset_root": _relative(root, layout["assets"]), "asset_count": len(frames)}


def _srt_time(milliseconds: int) -> str:
    hours, remaining = divmod(milliseconds, 3_600_000)
    minutes, remaining = divmod(remaining, 60_000)
    seconds, millis = divmod(remaining, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def build_documentary_v2_subtitles(project_root: str | Path, *, replace: bool = False) -> dict[str, Any]:
    root = _root(project_root)
    layout = _layout(root)
    script = _read_json(layout["script"])
    scenes = sorted(script.get("scenes", []), key=lambda item: int(item["position"]))
    if not scenes:
        raise ValueError("DOCUMENTARY_V2_SCENES_REQUIRED")
    start = 0
    blocks = []
    for index, scene in enumerate(scenes, start=1):
        end = start + int(scene["duration_ms"])
        blocks.append(f"{index}\n{_srt_time(start)} --> {_srt_time(end)}\n{scene['narration_text']}")
        start = end
    _write(layout["subtitles"], "\n\n".join(blocks) + "\n", replace=replace)
    return {"schema_version": SUBTITLE_V2_SCHEMA_VERSION, "subtitles": _relative(root, layout["subtitles"]), "cue_count": len(scenes), "duration_ms": start}


def _audio_filter(scenes: list[dict[str, Any]], *, audio_start: int) -> str:
    sections = []
    references = []
    for index, scene in enumerate(scenes):
        duration = scene["duration_ms"] / 1000
        sections.append(f"[{audio_start + index}:a]apad=pad_dur={SCENE_AUDIO_PAD_MS / 1000:.3f},atrim=duration={duration:.3f}[a{index}]")
        references.append(f"[a{index}]")
    sections.append("".join(references) + f"concat=n={len(scenes)}:v=0:a=1,{_LOUDNORM}[narration]")
    return ";".join(sections)


def _video_filter(frames: list[dict[str, Any]]) -> str:
    sections = []
    references = []
    for index, frame in enumerate(frames):
        duration = frame["duration_ms"] / 1000
        fade_start = max(0.0, duration - 0.35)
        sections.append(
            f"[{index}:v]scale=2304:1296,zoompan=z='min(1+0.0005*on\\,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={WIDTH}x{HEIGHT}:fps={FRAME_RATE},trim=duration={duration:.3f},setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.35,fade=t=out:st={fade_start:.3f}:d=0.35[v{index}]"
        )
        references.append(f"[v{index}]")
    sections.append("".join(references) + f"concat=n={len(frames)}:v=1:a=0,format=yuv420p[video]")
    return ";".join(sections)


def build_documentary_v2_render(
    project_root: str | Path,
    *,
    ffmpeg: str | None = None,
    replace: bool = False,
) -> dict[str, Any]:
    root = _root(project_root)
    layout = _layout(root)
    ffmpeg_binary = _resolve_binary(ffmpeg, "ffmpeg")
    storyboard = _read_json(layout["storyboard"])
    script = _read_json(layout["script"])
    frames = sorted(storyboard.get("frames", []), key=lambda item: int(item["position"]))
    scenes = sorted(script.get("scenes", []), key=lambda item: int(item["position"]))
    if not frames or len(frames) != len(scenes):
        raise ValueError("DOCUMENTARY_V2_FRAME_AUDIO_MISMATCH")
    if not layout["subtitles"].is_file():
        raise FileNotFoundError(f"ARTIFACT_NOT_FOUND:{layout['subtitles']}")
    if layout["video"].exists() and not replace:
        raise FileExistsError(f"ARTIFACT_EXISTS:{layout['video']}")
    if layout["narration"].exists() and not replace:
        raise FileExistsError(f"ARTIFACT_EXISTS:{layout['narration']}")
    audio_inputs: list[str] = []
    for scene in scenes:
        audio = root / scene["narration_audio"]
        if not audio.is_file():
            raise FileNotFoundError(f"NARRATION_NOT_FOUND:{audio}")
        audio_inputs.extend(["-i", str(audio)])
    layout["narration"].parent.mkdir(parents=True, exist_ok=True)
    narration_command = [ffmpeg_binary, "-hide_banner", "-loglevel", "error", "-y", *audio_inputs, "-filter_complex", _audio_filter(scenes, audio_start=0), "-map", "[narration]", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(layout["narration"])]
    _require(_run(narration_command), "DOCUMENTARY_V2_NARRATION_MIX_FAILED")
    inputs: list[str] = []
    for frame in frames:
        asset = root / frame["asset_path"]
        if not asset.is_file():
            raise FileNotFoundError(f"ASSET_NOT_FOUND:{asset}")
        inputs.extend(["-loop", "1", "-framerate", str(FRAME_RATE), "-t", f"{frame['duration_ms'] / 1000:.3f}", "-i", str(asset)])
    inputs.extend(["-i", str(layout["narration"])])
    command = [ffmpeg_binary, "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", _video_filter(frames), "-map", "[video]", "-map", f"{len(frames)}:a", "-r", str(FRAME_RATE), "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(layout["video"])]
    manifest = {"schema_version": RENDER_MANIFEST_V2_SCHEMA_VERSION, "production_id": storyboard["production_id"], "created_at": CANONICAL_TIMESTAMP, "output": _relative(root, layout["video"]), "subtitles": _relative(root, layout["subtitles"]), "narration_audio": _relative(root, layout["narration"]), "video": {"codec": "h264", "width": WIDTH, "height": HEIGHT, "ken_burns": True, "fade_transitions": True}, "audio": {"codec": "aac", "tts": "WINDOWS_SPEECHSYNTHESIZER", "loudness_normalization": _LOUDNORM}, "duration_ms": sum(scene["duration_ms"] for scene in scenes), "frames": frames}
    _write_json(layout["manifest"], manifest, replace=replace)
    process = _run(command)
    _require(process, "DOCUMENTARY_V2_RENDER_FAILED")
    if not layout["video"].is_file() or layout["video"].stat().st_size == 0:
        raise RuntimeError("DOCUMENTARY_V2_EMPTY_VIDEO")
    return {"manifest": _relative(root, layout["manifest"]), "video": _relative(root, layout["video"]), "size_bytes": layout["video"].stat().st_size, "duration_ms": manifest["duration_ms"], "command_sha256": sha256("\0".join(command[:-1]).encode("utf-8")).hexdigest()}


def _mean_volume(ffmpeg: str, video: Path) -> float | None:
    process = _run([ffmpeg, "-hide_banner", "-i", str(video), "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"])
    if process.returncode:
        return None
    match = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", process.stderr)
    return float(match.group(1)) if match else None


def verify_documentary_v2_render(
    project_root: str | Path,
    *,
    ffprobe: str | None = None,
    ffmpeg: str | None = None,
    replace: bool = False,
) -> dict[str, Any]:
    root = _root(project_root)
    layout = _layout(root)
    ffprobe_binary = _resolve_binary(ffprobe, "ffprobe")
    ffmpeg_binary = _resolve_binary(ffmpeg, "ffmpeg")
    if not layout["video"].is_file():
        raise FileNotFoundError(f"ARTIFACT_NOT_FOUND:{layout['video']}")
    process = _run([ffprobe_binary, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(layout["video"])])
    _require(process, "DOCUMENTARY_V2_FFPROBE_FAILED")
    probe = json.loads(process.stdout)
    streams = probe.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    duration = float(probe.get("format", {}).get("duration", "0") or 0)
    volume = _mean_volume(ffmpeg_binary, layout["video"])
    checks = {
        "h264_video": video.get("codec_name") == "h264",
        "aac_audio": audio.get("codec_name") == "aac",
        "resolution_1920x1080": video.get("width") == WIDTH and video.get("height") == HEIGHT,
        "duration_30_to_60_seconds": 30 <= duration <= 60,
        "video_stream_present": bool(video),
        "audio_stream_present": bool(audio),
        "narration_audible": volume is not None and volume > -60.0,
        "subtitles_present": layout["subtitles"].is_file() and layout["subtitles"].stat().st_size > 0,
    }
    report = {"schema_version": RENDER_VERIFICATION_V2_SCHEMA_VERSION, "created_at": CANONICAL_TIMESTAMP, "video": _relative(root, layout["video"]), "status": "VALID" if all(checks.values()) else "INVALID", "checks": checks, "mean_volume_db": volume, "duration_seconds": duration, "ffprobe": probe}
    _write_json(layout["verification"], report, replace=replace)
    return {"verification": _relative(root, layout["verification"]), "status": report["status"], "checks": checks, "duration_seconds": duration, "mean_volume_db": volume}
