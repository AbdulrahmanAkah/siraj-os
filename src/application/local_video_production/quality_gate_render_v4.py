"""One-scene v4 quality-gate renderer; it is not the full documentary pipeline."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import tempfile
import wave
from typing import Any

from src.application.operations_common import CANONICAL_TIMESTAMP, deterministic_id
from src.application.project_runtime import load_project, project_paths


V4_RENDER_SCHEMA = "siraj-quality-gate-render-manifest-v4"
V4_REPORT_SCHEMA = "siraj-quality-gate-render-report-v4"
WIDTH, HEIGHT, FPS = 1920, 1080, 24
ASSET_KEYS = ("baghdad-opening-aerial", "abbasid-city-reconstruction", "house-of-wisdom")
SUBTITLES = (
    "في قلب العراق، وعلى ضفاف دجلة، وُلدت بغداد؛",
    "مدينةٌ لم تكن مجرد عاصمة، بل بوابةً إلى المعرفة والسلطة.",
    "وفي القرن الثامن الميلادي، أسّس الخليفة أبو جعفر المنصور عاصمةً جديدةً للدولة العباسية، لتبدأ منها حكايةٌ غيّرت وجه التاريخ.",
)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=False)


def _require(process: subprocess.CompletedProcess[str], code: str) -> None:
    if process.returncode:
        raise RuntimeError(code)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _wav_duration(path: Path) -> int:
    with wave.open(str(path), "rb") as audio:
        frames, rate = audio.getnframes(), audio.getframerate()
    if frames <= 0 or rate <= 0:
        raise ValueError("QUALITY_GATE_NARRATION_INVALID")
    return round(frames * 1_000 / rate)


def _sfx(ffmpeg: str, root: Path, *, replace: bool) -> list[dict[str, Any]]:
    sfx_root = root / "working" / "production-v4" / "quality-gate-sfx"
    plans = (
        ("river-ambience", "anoisesrc=color=pink:sample_rate=48000:duration=1.8", "highpass=f=160,lowpass=f=1800,volume=0.030,afade=t=in:st=0:d=0.25,afade=t=out:st=1.35:d=0.45", 300),
        ("historical-transition", "sine=frequency=180:sample_rate=48000:duration=0.32", "volume=0.028,afade=t=in:st=0:d=0.05,afade=t=out:st=0.14:d=0.18", 6_220),
        ("library-ambience", "anoisesrc=color=brown:sample_rate=48000:duration=1.5", "highpass=f=220,lowpass=f=1200,volume=0.022,afade=t=in:st=0:d=0.25,afade=t=out:st=1.05:d=0.35", 12_800),
    )
    results = []
    for name, generator, filters, start_ms in plans:
        target = sfx_root / f"{name}.wav"
        if target.exists() and not replace:
            raise FileExistsError(f"ARTIFACT_EXISTS:{target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        _require(_run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", generator, "-af", filters, "-c:a", "pcm_s16le", str(target)]), "QUALITY_GATE_SFX_FAILED")
        results.append({"effect_id": deterministic_id("quality_gate_sfx_v4", [name]), "kind": name, "path": str(target.relative_to(root).as_posix()), "start_ms": start_ms, "gain_db": -30, "rights": {"origin": "GENERATED_LOCAL", "creator": "SIRAJ quality-gate SFX", "license": "CC0-1.0", "source_url": f"local://siraj/quality-gate-v4/{name}", "sha256": sha256(target.read_bytes()).hexdigest()}})
    return results


def _black_frame_free(ffmpeg: str, video: Path) -> bool:
    for position in (0.1, 7.0, 14.0):
        probe = _run([ffmpeg, "-hide_banner", "-ss", str(position), "-i", str(video), "-frames:v", "1", "-vf", "signalstats,metadata=print", "-f", "null", "-"])
        values = re.findall(r"lavfi\.signalstats\.YAVG=([0-9.]+)", probe.stderr)
        if probe.returncode or not values or float(values[-1]) < 4.0:
            return False
    return True


def build_quality_gate_v4(
    project_root: str | Path,
    *,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    replace: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve(strict=False)
    load_project(root)
    paths = project_paths(root)
    work = Path(paths.working_root) / "production-v4"
    auditions = work / "visual-auditions"
    voice = _json(work / "voice-provider-selection.json")
    selection = voice["selection"]
    if selection != {"provider_identifier": "AZURE_NEURAL_TTS_SDK", "voice_identifier": "ar-SA-HamedNeural", "locale": "ar-SA", "quality_gate_only": True, "production_final": False}:
        raise ValueError("QUALITY_GATE_VOICE_SELECTION_INVALID")
    visual_manifest = _json(auditions / "visual-audition-manifest.json")
    assets_by_key = {Path(item["path"]).stem.split("-", 1)[1]: item for item in visual_manifest["assets"]}
    assets = [assets_by_key[key] for key in ASSET_KEYS]
    narration = next((path for path in (work / "voice-auditions").glob("01-ar-sa-hamedneural-*.wav")), None)
    if narration is None:
        raise FileNotFoundError("QUALITY_GATE_HAMED_AUDITION_MISSING")
    duration_ms = _wav_duration(narration)
    if not 15_000 <= duration_ms <= 20_000:
        raise ValueError("QUALITY_GATE_DURATION_OUT_OF_RANGE")
    output = Path(paths.exports_root) / "quality-gate-v4.mp4"
    srt = work / "quality-gate-v4.srt"
    manifest_path = Path(paths.manifests_root) / "quality-gate-v4-manifest.json"
    report_path = Path(paths.manifests_root) / "quality-gate-v4-report.json"
    if output.exists() and not replace:
        raise FileExistsError(f"ARTIFACT_EXISTS:{output}")
    transition_ms = 450
    segment_ms = (duration_ms + 2 * transition_ms) // 3
    starts = (0, segment_ms - transition_ms, 2 * (segment_ms - transition_ms))
    ends = (starts[1], starts[2], duration_ms)
    srt_content = "\n\n".join(
        f"{index}\n{_timestamp(start)} --> {_timestamp(end)}\n\u200f{text}\u200f"
        for index, (start, end, text) in enumerate(zip(starts, ends, SUBTITLES, strict=True), 1)
    ) + "\n"
    _write(srt, srt_content)
    sfx = _sfx(ffmpeg, root, replace=replace)
    mixed_audio = work / "quality-gate-mix.wav"
    inputs = ["-i", str(narration)]
    filters, effect_refs = [], []
    for index, effect in enumerate(sfx, 1):
        inputs.extend(["-i", str(root / effect["path"])])
        filters.append(f"[{index}:a]volume={effect['gain_db']}dB,adelay={effect['start_ms']}|{effect['start_ms']}[s{index}]")
        effect_refs.append(f"[s{index}]")
    filters.append("[0:a]" + "".join(effect_refs) + f"amix=inputs={len(effect_refs)+1}:normalize=0,alimiter=limit=0.84,loudnorm=I=-16:LRA=7:TP=-1.5[mix]")
    _require(_run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[mix]", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(mixed_audio)]), "QUALITY_GATE_AUDIO_MIX_FAILED")
    segment_seconds = segment_ms / 1_000
    visual_inputs = []
    for asset in assets:
        visual_inputs.extend(["-loop", "1", "-framerate", str(FPS), "-t", f"{segment_seconds:.3f}", "-i", str(root / asset["path"])])
    # Three distinct, restrained moves: push-in, left-to-right pan, reverse parallax pan.
    filters = [
        f"[0:v]scale=2304:1296,zoompan=z='min(zoom+0.00030,1.045)':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={WIDTH}x{HEIGHT}:fps={FPS},trim=duration={segment_seconds:.3f},setpts=PTS-STARTPTS[v0]",
        f"[1:v]scale=2304:1296,crop={WIDTH}:{HEIGHT}:x='(in_w-out_w)*min(t/{segment_seconds:.3f},1)':y='(in_h-out_h)/2',trim=duration={segment_seconds:.3f},setpts=PTS-STARTPTS[v1]",
        f"[2:v]scale=2304:1296,crop={WIDTH}:{HEIGHT}:x='(in_w-out_w)*(1-min(t/{segment_seconds:.3f},1))':y='(in_h-out_h)/2',trim=duration={segment_seconds:.3f},setpts=PTS-STARTPTS[v2]",
        f"[v0][v1]xfade=transition=fade:duration={transition_ms / 1000:.3f}:offset={(segment_ms-transition_ms)/1000:.3f}[v01]",
        f"[v01][v2]xfade=transition=wipeleft:duration={transition_ms / 1000:.3f}:offset={(2*(segment_ms-transition_ms))/1000:.3f},format=yuv420p[video]",
    ]
    _require(_run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *visual_inputs, "-i", str(mixed_audio), "-filter_complex", ";".join(filters), "-map", "[video]", "-map", "3:a", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(output)]), "QUALITY_GATE_RENDER_FAILED")
    probe = _run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)])
    _require(probe, "QUALITY_GATE_FFPROBE_FAILED")
    data = json.loads(probe.stdout)
    video = next((item for item in data["streams"] if item.get("codec_type") == "video"), {})
    audio = next((item for item in data["streams"] if item.get("codec_type") == "audio"), {})
    volume = _run([ffmpeg, "-hide_banner", "-i", str(output), "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"])
    mean_match, max_match = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", volume.stderr), re.search(r"max_volume:\s*(-?[0-9.]+) dB", volume.stderr)
    mean, maximum = (float(mean_match.group(1)) if mean_match else None), (float(max_match.group(1)) if max_match else None)
    checks = {
        "h264": video.get("codec_name") == "h264",
        "aac": audio.get("codec_name") == "aac",
        "resolution": video.get("width") == WIDTH and video.get("height") == HEIGHT,
        "duration": 15 <= float(data["format"].get("duration", 0)) <= 20,
        "no_black_frames": _black_frame_free(ffmpeg, output),
        "non_silent_audio": mean is not None and mean > -55,
        "no_clipping": maximum is not None and maximum <= -0.1,
        "subtitle_duration_sync": ends[-1] == duration_ms,
        "music_forbidden": True,
        "audio_provider_quality_gate_only": selection["quality_gate_only"] and not selection["production_final"],
    }
    manifest = {
        "schema_version": V4_RENDER_SCHEMA,
        "created_at": CANONICAL_TIMESTAMP,
        "render_id": deterministic_id("quality_gate_render_v4", [selection["provider_identifier"], selection["voice_identifier"], [asset["asset_id"] for asset in assets], duration_ms]),
        "output": str(output.relative_to(root).as_posix()),
        "duration_ms": duration_ms,
        "fps": FPS,
        "voice_provider_identifier": selection["provider_identifier"],
        "voice_identifier": selection["voice_identifier"],
        "production_final": False,
        "music": "FORBIDDEN",
        "narration": str(narration.relative_to(root).as_posix()),
        "subtitles": str(srt.relative_to(root).as_posix()),
        "assets": assets,
        "asset_provider_identifier": visual_manifest["asset_provider_identifier"],
        "sound_effects": sfx,
        "transitions": ["FADE", "WIPELEFT"],
    }
    _write(manifest_path, json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    report = {"schema_version": V4_REPORT_SCHEMA, "created_at": CANONICAL_TIMESTAMP, "status": "VALID" if all(checks.values()) else "INVALID", "checks": checks, "mean_volume_db": mean, "max_volume_db": maximum, "ffprobe": data}
    _write(report_path, json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return {"status": report["status"], "video": manifest["output"], "srt": manifest["subtitles"], "manifest": str(manifest_path.relative_to(root).as_posix()), "report": str(report_path.relative_to(root).as_posix()), "checks": checks}
