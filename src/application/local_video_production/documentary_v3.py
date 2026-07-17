"""Arabic, local-only documentary v3 pipeline.

All TTS input is ``narration_tts``.  Screen/editorial/citation fields are
deliberately separate and never reach a voice provider.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import wave
from typing import Any, Protocol

from src.application.operations_common import CANONICAL_TIMESTAMP, deterministic_id
from src.application.project_runtime import load_project, project_paths


V3_SCHEMA = "siraj-arabic-documentary-v3"
V3_BRIEF = "siraj-production-brief-v3"
V3_SCRIPT = "siraj-production-script-v3"
V3_ASSETS = "siraj-production-assets-v3"
V3_SUBTITLES = "siraj-production-subtitles-v3"
V3_SFX = "siraj-production-sfx-v3"
V3_RENDER = "siraj-production-render-manifest-v3"
V3_VERIFY = "siraj-production-render-verification-v3"
WIDTH, HEIGHT, FPS = 1920, 1080, 25
PACING_HOLD_MS = 1_100
_BANNED = ("historical fact number", "this fact is documented", "supported by source", "claim id", "source id")


@dataclass(frozen=True)
class AudioPolicy:
    music: str = "FORBIDDEN"
    sound_effects: str = "ALLOWED"
    ambient_sound: str = "ALLOWED"
    narration: str = "REQUIRED"


@dataclass(frozen=True)
class DocumentaryV3Config:
    ffmpeg: str | None = None
    ffprobe: str | None = None
    voice_provider: str = "ESPEAK_NG_ARABIC"
    language: str = "ar"
    output_profile: str = "PRODUCTION"
    audio_policy: AudioPolicy = AudioPolicy()


@dataclass(frozen=True)
class VoiceSynthesisRequest:
    text: str
    output_wav: str
    language: str
    pronunciation_dictionary: dict[str, str]


@dataclass(frozen=True)
class VoiceSynthesisResult:
    provider_id: str
    output_wav: str
    duration_ms: int


class VoiceProvider(Protocol):
    provider_id: str

    def synthesize(self, request: VoiceSynthesisRequest) -> VoiceSynthesisResult: ...


def _canonical_json(payload: Any) -> str:
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
    _write(path, _canonical_json(payload), replace=replace)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"ARTIFACT_NOT_FOUND:{path}")
    result = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(result, dict):
        raise ValueError(f"INVALID_ARTIFACT:{path}")
    return result


def _root(value: str | Path) -> Path:
    root = Path(value).expanduser()
    if not root.is_absolute():
        raise ValueError("PROJECT_ROOT_MUST_BE_ABSOLUTE")
    root = root.resolve(strict=False)
    load_project(root)
    return root


def _layout(root: Path) -> dict[str, Path]:
    paths = project_paths(root)
    work = Path(paths.working_root) / "production-v3"
    return {"brief": Path(paths.manifests_root) / "production-brief-v3.json", "script": work / "script-v3.json", "assets": work / "assets-v3.json", "asset_root": work / "assets", "audio_root": work / "audio", "narration": work / "audio" / "narration-v3.wav", "mix": work / "audio" / "production-mix-v3.wav", "sfx": work / "sfx-v3.json", "sfx_root": work / "sfx", "srt": work / "subtitles-v3.srt", "vtt": work / "subtitles-v3.vtt", "manifest": Path(paths.manifests_root) / "render-manifest-v3.json", "verify": Path(paths.manifests_root) / "render-verification-v3.json", "video": Path(paths.exports_root) / "first-documentary-v3.mp4"}


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _binary(value: str | None, name: str) -> str:
    if value:
        candidate = Path(value).expanduser()
        if candidate.is_file():
            return str(candidate)
        if found := shutil.which(value):
            return found
        raise FileNotFoundError(f"{name.upper()}_NOT_FOUND:{value}")
    if found := shutil.which(name):
        return found
    raise FileNotFoundError(f"{name.upper()}_NOT_FOUND")


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=False)


def _require(process: subprocess.CompletedProcess[str], code: str) -> None:
    if process.returncode:
        detail = process.stderr.strip().splitlines()[-1] if process.stderr.strip() else "NO_STDERR"
        raise RuntimeError(f"{code}:{process.returncode}:{detail}")


def _wav_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as wav:
        frames, rate = wav.getnframes(), wav.getframerate()
    if frames <= 0 or rate <= 0:
        raise ValueError(f"INVALID_WAV:{path}")
    return max(1, round(frames * 1000 / rate))


def _pace_arabic_wav(ffmpeg: str, wav_path: Path) -> None:
    paced = wav_path.with_name(wav_path.stem + ".paced.wav")
    process = _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav_path), "-af", "atempo=0.5,atempo=0.5,atempo=0.5,atempo=0.5", "-c:a", "pcm_s16le", str(paced)])
    _require(process, "ARABIC_TTS_PACING_FAILED")
    paced.replace(wav_path)


class EspeakArabicVoiceProvider:
    provider_id = "ESPEAK_NG_ARABIC_LOCAL"

    def __init__(self, executable: str | None = None) -> None:
        if executable is None:
            bundled = Path(r"C:\Program Files\eSpeak NG\espeak-ng.exe")
            executable = str(bundled) if bundled.is_file() else None
        self.executable = _binary(executable, "espeak-ng")

    def synthesize(self, request: VoiceSynthesisRequest) -> VoiceSynthesisResult:
        text = request.text
        for source, spoken in sorted(request.pronunciation_dictionary.items(), key=lambda item: len(item[0]), reverse=True):
            text = text.replace(source, spoken)
        if any(item in text.lower() for item in _BANNED):
            raise ValueError("NARRATION_CONTAINS_METADATA_TEMPLATE")
        output = Path(request.output_wav)
        output.parent.mkdir(parents=True, exist_ok=True)
        process = _run([self.executable, "-v", "ar", "-s", "115", "-w", str(output), text])
        _require(process, "ARABIC_TTS_FAILED")
        return VoiceSynthesisResult(self.provider_id, str(output), _wav_ms(output))


def _pronunciation_dictionary() -> dict[str, str]:
    return {
        "Baghdad": "بغداد",
        "Tigris": "دجلة",
        "Al-Mansur": "المنصور",
        "762": "سنة سبعمئة واثنتين وستين للميلاد",
        "Iraq": "العراق",
        "House of Wisdom": "بيت الحكمة",
        "SIRAJ": "سراج",
    }


def _claims(root: Path) -> list[dict[str, Any]]:
    claims = _read_json(root / "working" / "knowledge" / "claims.json").get("claims")
    if not isinstance(claims, list):
        raise ValueError("INVALID_CLAIMS_ARTIFACT")
    valid = [item for item in claims if isinstance(item, dict) and isinstance(item.get("claim_id"), str)]
    valid.sort(key=lambda item: item["claim_id"])
    if len(valid) < 5:
        raise ValueError("INSUFFICIENT_CLAIMS_FOR_V3")
    return valid


def _arabic_scenes(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_text = " ".join(str(item.get("claim_text", "")) for item in claims)
    required = {"762", "Al-Mansur", "Tigris", "House of Wisdom", "capital of Iraq"}
    if not all(token in by_text for token in required):
        raise ValueError("V3_REQUIRED_BAGHDAD_CLAIMS_MISSING")
    ids = [item["claim_id"] for item in claims]
    return [
        {"narration_ar": "حين نتأمل تاريخ بغداد، لا نرى مدينة عابرة، بل نرى نقطة التقاء بين النهر والمعرفة والذاكرة. ومن هذه البداية القصيرة نتابع خيوط حكايتها كما تحفظها المصادر المتاحة.", "screen_title": "بغداد: مدينة النهر والمعرفة", "lower_third": "مقدمة وثائقية", "editorial_note": "افتتاحية", "claim_ids": [], "citation_ids": [], "layout": "TITLE_CARD"},
        {"narration_ar": "تبدأ الحكاية في سنة 762، حين أسس الخليفة العباسي المنصور بغداد. كان ذلك التأسيس لحظة فارقة رسمت إطار المدينة التي ستتسع لاحقاً لمعانٍ سياسية وثقافية أعمق.", "screen_title": "762 م — تأسيس بغداد", "lower_third": "الخليفة العباسي المنصور", "editorial_note": "التأسيس", "claim_ids": ids, "citation_ids": ["evidence_dfb4a0f18c04c2b7", "evidence_b4c3cf491ba6b04e"], "layout": "TIMELINE"},
        {"narration_ar": "ويمر نهر دجلة في قلب بغداد، فيمنح المكان حضوره الجغرافي الواضح. فالنهر هنا ليس خلفية صامتة، بل جزء من الصورة التي تتصل بها حياة المدينة وذاكرتها اليومية.", "screen_title": "نهر دجلة", "lower_third": "الجغرافيا تصنع المشهد", "editorial_note": "خريطة مبسطة", "claim_ids": ids, "citation_ids": ["evidence_acd598236f328438"], "layout": "MAP"},
        {"narration_ar": "ومع الزمن أصبحت بغداد مركزاً مهماً للتعلم. لا تختزل هذه العبارة تاريخ المدينة كله، لكنها تفتح نافذة على مكانتها في تداول المعرفة واحتضان النشاط الفكري.", "screen_title": "مركز للتعلم", "lower_third": "المعرفة في بغداد", "editorial_note": "وثيقة ومعرفة", "claim_ids": ids, "citation_ids": ["evidence_571e76d39ea10eb1"], "layout": "DOCUMENT"},
        {"narration_ar": "وفي بغداد عمل بيت الحكمة، وهو اسم يرتبط في الذاكرة التاريخية بفكرة المعرفة المنظمة. ويظهر هذا الحضور في المصادر بوصفه علامة من علامات الصلة بين المدينة والعلم.", "screen_title": "بيت الحكمة", "lower_third": "المعرفة المنظمة", "editorial_note": "بطاقة وثائقية", "claim_ids": ids, "citation_ids": ["evidence_e9d47df93efc4d5c"], "layout": "PORTRAIT"},
        {"narration_ar": "أما اليوم، فبغداد هي عاصمة العراق. وهكذا تمتد الحكاية من تأسيس مبكر، إلى نهر حاضر، إلى ذاكرة علمية وثقافية، ثم إلى مدينة ما زالت تحمل اسمها ومكانتها.", "screen_title": "بغداد اليوم", "lower_third": "عاصمة العراق", "editorial_note": "خاتمة", "claim_ids": ids, "citation_ids": ["evidence_431f1c60aff4b558"], "layout": "QUOTATION"},
        {"narration_ar": "هذه ليست إلا لمحة أولى من تاريخ بغداد؛ لمحة تضع الوقائع الأساسية في مسار واحد، وتترك المجال لمصادر أوسع تكشف طبقات أخرى من قصة المدينة.", "screen_title": "بغداد — ذاكرة مستمرة", "lower_third": "نهاية المقطع", "editorial_note": "خاتمة قصيرة", "claim_ids": [], "citation_ids": [], "layout": "LOCATION"},
    ]


def initialize_documentary_v3(project_root: str | Path, *, config: DocumentaryV3Config = DocumentaryV3Config(), replace: bool = False) -> dict[str, Any]:
    if config.output_profile == "PRODUCTION" and config.audio_policy.music != "FORBIDDEN":
        raise ValueError("PRODUCTION_MUSIC_MUST_BE_FORBIDDEN")
    root, layout = _root(project_root), _layout(_root(project_root))
    project, claims = load_project(root), _claims(root)
    ffmpeg = _binary(config.ffmpeg, "ffmpeg")
    production_id = deterministic_id("arabic_documentary_v3", [project["project_id"], [item["claim_id"] for item in claims]])
    provider: VoiceProvider = EspeakArabicVoiceProvider(config.voice_provider if config.voice_provider != "ESPEAK_NG_ARABIC" else None)
    dictionary = _pronunciation_dictionary()
    scenes = []
    for position, item in enumerate(_arabic_scenes(claims)):
        narration = item["narration_ar"]
        if any(token in narration.lower() for token in _BANNED):
            raise ValueError("NARRATION_CONTAINS_METADATA_TEMPLATE")
        wav = layout["audio_root"] / f"scene-{position + 1:02d}.wav"
        result = provider.synthesize(VoiceSynthesisRequest(narration, str(wav), "ar", dictionary))
        _pace_arabic_wav(ffmpeg, wav)
        narration_duration = _wav_ms(wav)
        scene = {"scene_id": deterministic_id("arabic_documentary_v3_scene", [production_id, position]), "position": position, **item, "narration_tts": narration, "narration_audio": _relative(root, wav), "narration_duration_ms": narration_duration, "duration_ms": narration_duration + PACING_HOLD_MS, "voice_provider": result.provider_id}
        scenes.append(scene)
    total = sum(item["duration_ms"] for item in scenes)
    if not 60_000 <= total <= 90_000:
        raise ValueError(f"ARABIC_NARRATION_DURATION_OUT_OF_RANGE:{total}")
    brief = {"schema_version": V3_BRIEF, "production_id": production_id, "created_at": CANONICAL_TIMESTAMP, "language": "ar", "config": asdict(config), "target_duration_ms": total, "audio_policy": asdict(config.audio_policy)}
    script = {"schema_version": V3_SCRIPT, "production_id": production_id, "created_at": CANONICAL_TIMESTAMP, "pronunciation_dictionary": dictionary, "scenes": scenes}
    _write_json(layout["brief"], brief, replace=replace)
    _write_json(layout["script"], script, replace=replace)
    return {"production_id": production_id, "script": _relative(root, layout["script"]), "brief": _relative(root, layout["brief"]), "duration_ms": total, "voice_provider": provider.provider_id}


class AssetProvider(Protocol):
    provider_id: str

    def create(self, *, scene: dict[str, Any], output: Path, ffmpeg: str, replace: bool) -> dict[str, Any]: ...


def _font() -> str:
    for path in (Path(r"C:\Windows\Fonts\segoeui.ttf"), Path(r"C:\Windows\Fonts\arial.ttf")):
        if path.is_file():
            return path.as_posix().replace(":", "\\:")
    raise FileNotFoundError("LOCAL_FONT_NOT_FOUND")


def _layout_filter(kind: str, position: int, font: str) -> str:
    color = ("172A3A", "1C3B57", "3B2C4A", "254E58", "4E3B31", "203A43", "334E3B")[position % 7]
    base = f"color=c=0x{color}:s={WIDTH}x{HEIGHT}:r={FPS},drawbox=x=70:y=70:w=1780:h=940:color=E8DAB2@0.18:t=4,"
    lower = f"drawbox=x=110:y=830:w=1700:h=100:color=000000@0.52:t=fill,drawtext=fontfile='{font}':text='SIRAJ | BAGHDAD DOCUMENTARY':fontcolor=white:fontsize=28:x=150:y=865"
    if kind == "TITLE_CARD":
        shape = "drawbox=x=260:y=250:w=1400:h=330:color=000000@0.32:t=fill,drawbox=x=350:y=630:w=1220:h=6:color=E8DAB2:t=fill,drawtext=fontfile='" + font + "':text='BAGHDAD':fontcolor=E8DAB2:fontsize=140:x=570:y=325,"
    elif kind == "TIMELINE":
        shape = "drawbox=x=190:y=480:w=1540:h=8:color=E8DAB2:t=fill,drawbox=x=460:y=430:w=32:h=105:color=DDA15E:t=fill,drawbox=x=950:y=430:w=32:h=105:color=DDA15E:t=fill,drawbox=x=1450:y=430:w=32:h=105:color=DDA15E:t=fill,drawtext=fontfile='" + font + "':text='762 CE':fontcolor=white:fontsize=76:x=780:y=290,"
    elif kind == "MAP":
        shape = "drawbox=x=250:y=210:w=1420:h=500:color=90BE6D@0.18:t=fill,drawbox=x=900:y=235:w=58:h=450:color=48CAE4@0.90:t=fill,drawbox=x=340:y=320:w=290:h=160:color=F1FAEE@0.15:t=fill,drawbox=x=1210:y=450:w=260:h=150:color=F1FAEE@0.15:t=fill,drawtext=fontfile='" + font + "':text='TIGRIS RIVER':fontcolor=white:fontsize=44:x=985:y=400,"
    elif kind == "DOCUMENT":
        shape = "drawbox=x=420:y=170:w=1080:h=590:color=E8DAB2@0.92:t=fill,drawbox=x=500:y=270:w=760:h=10:color=3D405B:t=fill,drawbox=x=500:y=350:w=850:h=8:color=3D405B:t=fill,drawbox=x=500:y=430:w=720:h=8:color=3D405B:t=fill,drawtext=fontfile='" + font + "':text='DOCUMENT':fontcolor=3D405B:fontsize=70:x=690:y=570,"
    elif kind == "PORTRAIT":
        shape = "drawbox=x=320:y=180:w=520:h=590:color=000000@0.34:t=fill,drawbox=x=470:y=270:w=220:h=260:color=DDA15E@0.60:t=fill,drawbox=x=1050:y=260:w=520:h=260:color=F1FAEE@0.13:t=fill,drawtext=fontfile='" + font + "':text='HOUSE OF WISDOM':fontcolor=white:fontsize=56:x=980:y=590,"
    elif kind == "QUOTATION":
        shape = "drawbox=x=270:y=220:w=1380:h=500:color=000000@0.30:t=fill,drawtext=fontfile='" + font + "':text='BAGHDAD':fontcolor=E8DAB2:fontsize=112:x=620:y=330,drawtext=fontfile='" + font + "':text='A CITY OF MEMORY':fontcolor=white:fontsize=58:x=590:y=510,"
    else:
        shape = "drawbox=x=280:y=180:w=1360:h=570:color=F1FAEE@0.14:t=fill,drawbox=x=590:y=310:w=740:h=180:color=000000@0.25:t=fill,drawtext=fontfile='" + font + "':text='BAGHDAD TODAY':fontcolor=white:fontsize=82:x=530:y=560,"
    return base + shape + lower


class LocalDiagramAssetProvider:
    provider_id = "LOCAL_DIAGRAM_ASSET_PROVIDER"

    def create(self, *, scene: dict[str, Any], output: Path, ffmpeg: str, replace: bool) -> dict[str, Any]:
        if output.exists() and not replace:
            raise FileExistsError(f"ARTIFACT_EXISTS:{output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        process = _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", _layout_filter(scene["layout"], scene["position"], _font()), "-frames:v", "1", str(output)])
        _require(process, "V3_ASSET_RENDER_FAILED")
        digest = sha256(output.read_bytes()).hexdigest()
        return {"asset_id": deterministic_id("arabic_documentary_v3_asset", [scene["scene_id"], digest]), "scene_id": scene["scene_id"], "path": str(output), "asset_type": scene["layout"], "origin": "GENERATED_LOCAL_DIAGRAM", "source_url": "local://siraj/documentary-v3", "creator": "SIRAJ local diagram provider", "license": "CC0-1.0", "authenticity_classification": "diagram", "sha256": digest, "provider_id": self.provider_id}


def build_documentary_v3_assets(project_root: str | Path, *, config: DocumentaryV3Config = DocumentaryV3Config(), replace: bool = False) -> dict[str, Any]:
    if config.output_profile == "PRODUCTION" and config.audio_policy.music != "FORBIDDEN":
        raise ValueError("PRODUCTION_MUSIC_MUST_BE_FORBIDDEN")
    root, layout = _root(project_root), _layout(_root(project_root))
    ffmpeg = _binary(config.ffmpeg, "ffmpeg")
    script = _read_json(layout["script"])
    provider: AssetProvider = LocalDiagramAssetProvider()
    assets = []
    for scene in sorted(script["scenes"], key=lambda item: item["position"]):
        asset = provider.create(scene=scene, output=layout["asset_root"] / f"scene-{scene['position'] + 1:02d}.png", ffmpeg=ffmpeg, replace=replace)
        asset["path"] = _relative(root, Path(asset["path"]))
        if asset["authenticity_classification"] == "placeholder" and config.output_profile == "PRODUCTION":
            raise ValueError("PLACEHOLDER_ASSET_FORBIDDEN_IN_PRODUCTION")
        assets.append(asset)
    payload = {"schema_version": V3_ASSETS, "production_id": script["production_id"], "created_at": CANONICAL_TIMESTAMP, "assets": assets}
    _write_json(layout["assets"], payload, replace=replace)
    return {"assets": _relative(root, layout["assets"]), "asset_count": len(assets), "provider_id": provider.provider_id}


def _timestamp(milliseconds: int, separator: str) -> str:
    hours, remain = divmod(milliseconds, 3_600_000)
    minutes, remain = divmod(remain, 60_000)
    seconds, millis = divmod(remain, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{millis:03d}"


def build_documentary_v3_subtitles(project_root: str | Path, *, replace: bool = False) -> dict[str, Any]:
    root, layout = _root(project_root), _layout(_root(project_root))
    scenes = sorted(_read_json(layout["script"])["scenes"], key=lambda item: item["position"])
    start, srt, vtt = 0, [], ["WEBVTT", ""]
    for index, scene in enumerate(scenes, 1):
        end = start + scene["duration_ms"]
        text = "\u200f" + scene["narration_ar"] + "\u200f"
        srt.append(f"{index}\n{_timestamp(start, ',')} --> {_timestamp(end, ',')}\n{text}")
        vtt.extend([str(index), f"{_timestamp(start, '.')} --> {_timestamp(end, '.')}", text, ""])
        start = end
    _write(layout["srt"], "\n\n".join(srt) + "\n", replace=replace)
    _write(layout["vtt"], "\n".join(vtt), replace=replace)
    return {"schema_version": V3_SUBTITLES, "srt": _relative(root, layout["srt"]), "vtt": _relative(root, layout["vtt"]), "cue_count": len(scenes), "duration_ms": start}


def _make_effect(ffmpeg: str, output: Path, *, replace: bool) -> None:
    if output.exists() and not replace:
        raise FileExistsError(f"ARTIFACT_EXISTS:{output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    process = _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=color=pink:sample_rate=48000:duration=0.65", "-af", "volume=0.10,afade=t=in:st=0:d=0.08,afade=t=out:st=0.42:d=0.20", "-c:a", "pcm_s16le", str(output)])
    _require(process, "SFX_GENERATION_FAILED")


def _make_sfx_plan(root: Path, layout: dict[str, Path], scenes: list[dict[str, Any]], ffmpeg: str, *, replace: bool) -> dict[str, Any]:
    effects = []
    offset = 0
    for scene in scenes:
        effect = layout["sfx_root"] / f"scene-{scene['position'] + 1:02d}-page-turn.wav"
        _make_effect(ffmpeg, effect, replace=replace)
        effects.append({"effect_id": deterministic_id("arabic_documentary_v3_sfx", [scene["scene_id"]]), "scene_id": scene["scene_id"], "path": _relative(root, effect), "start_ms": offset + 180, "gain_db": -24, "fade_in_ms": 80, "fade_out_ms": 200, "rights": {"origin": "GENERATED_LOCAL", "creator": "SIRAJ local SFX generator", "license": "CC0-1.0", "source_url": "local://siraj/sfx-v3", "sha256": sha256(effect.read_bytes()).hexdigest()}, "kind": "PAGE_RUSTLE"})
        offset += scene["duration_ms"]
    result = {"schema_version": V3_SFX, "created_at": CANONICAL_TIMESTAMP, "music": "FORBIDDEN", "effects": effects, "ambient_sound": []}
    _write_json(layout["sfx"], result, replace=replace)
    return result


def _concat_narration_filter(scenes: list[dict[str, Any]]) -> str:
    sections, refs = [], []
    for index, scene in enumerate(scenes):
        seconds = scene["duration_ms"] / 1000
        sections.append(f"[{index}:a]apad=pad_dur={PACING_HOLD_MS / 1000:.3f},atrim=duration={seconds:.3f}[n{index}]")
        refs.append(f"[n{index}]")
    sections.append("".join(refs) + f"concat=n={len(scenes)}:v=0:a=1,loudnorm=I=-16:LRA=11:TP=-1.5[narration]")
    return ";".join(sections)


def _video_filter(assets: list[dict[str, Any]], scenes: list[dict[str, Any]]) -> str:
    sections, refs = [], []
    for index, (asset, scene) in enumerate(zip(assets, scenes, strict=True)):
        duration = scene["duration_ms"] / 1000
        sections.append(f"[{index}:v]scale=2304:1296,zoompan=z='min(1+0.00045*on\\,1.075)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={WIDTH}x{HEIGHT}:fps={FPS},trim=duration={duration:.3f},setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.35,fade=t=out:st={max(0,duration-0.35):.3f}:d=0.35[v{index}]")
        refs.append(f"[v{index}]")
    sections.append("".join(refs) + f"concat=n={len(assets)}:v=1:a=0,format=yuv420p[video]")
    return ";".join(sections)


def build_documentary_v3_render(project_root: str | Path, *, config: DocumentaryV3Config = DocumentaryV3Config(), replace: bool = False) -> dict[str, Any]:
    if config.output_profile == "PRODUCTION" and config.audio_policy.music != "FORBIDDEN":
        raise ValueError("PRODUCTION_MUSIC_MUST_BE_FORBIDDEN")
    root, layout = _root(project_root), _layout(_root(project_root))
    ffmpeg = _binary(config.ffmpeg, "ffmpeg")
    script = _read_json(layout["script"])
    asset_manifest = _read_json(layout["assets"])
    scenes = sorted(script["scenes"], key=lambda item: item["position"])
    assets = sorted(asset_manifest["assets"], key=lambda item: item["scene_id"])
    assets_by_scene = {item["scene_id"]: item for item in assets}
    assets = [assets_by_scene[scene["scene_id"]] for scene in scenes]
    if any(asset["authenticity_classification"] == "placeholder" for asset in assets):
        raise ValueError("PLACEHOLDER_ASSET_FORBIDDEN_IN_PRODUCTION")
    if layout["video"].exists() and not replace:
        raise FileExistsError(f"ARTIFACT_EXISTS:{layout['video']}")
    narration_inputs = []
    for scene in scenes:
        narration_inputs.extend(["-i", str(root / scene["narration_audio"])])
    if layout["narration"].exists() and not replace:
        raise FileExistsError(f"ARTIFACT_EXISTS:{layout['narration']}")
    layout["narration"].parent.mkdir(parents=True, exist_ok=True)
    narration_cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *narration_inputs, "-filter_complex", _concat_narration_filter(scenes), "-map", "[narration]", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(layout["narration"])]
    _require(_run(narration_cmd), "V3_NARRATION_MIX_FAILED")
    sfx = _make_sfx_plan(root, layout, scenes, ffmpeg, replace=replace)
    if layout["mix"].exists() and not replace:
        raise FileExistsError(f"ARTIFACT_EXISTS:{layout['mix']}")
    mix_inputs = ["-i", str(layout["narration"])]
    mix_filters, effect_refs = [], []
    for index, effect in enumerate(sfx["effects"], start=1):
        mix_inputs.extend(["-i", str(root / effect["path"])])
        delay = effect["start_ms"]
        mix_filters.append(f"[{index}:a]volume={effect['gain_db']}dB,adelay={delay}|{delay}[e{index}]")
        effect_refs.append(f"[e{index}]")
    mix_filters.append("[0:a]" + "".join(effect_refs) + f"amix=inputs={len(effect_refs)+1}:normalize=0,loudnorm=I=-16:LRA=11:TP=-1.5[mix]")
    mix_cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *mix_inputs, "-filter_complex", ";".join(mix_filters), "-map", "[mix]", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(layout["mix"])]
    _require(_run(mix_cmd), "V3_SFX_MIX_FAILED")
    video_inputs = []
    for asset, scene in zip(assets, scenes, strict=True):
        video_inputs.extend(["-loop", "1", "-framerate", str(FPS), "-t", f"{scene['duration_ms']/1000:.3f}", "-i", str(root / asset["path"])])
    video_inputs.extend(["-i", str(layout["mix"])])
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *video_inputs, "-filter_complex", _video_filter(assets, scenes), "-map", "[video]", "-map", f"{len(assets)}:a", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(layout["video"])]
    manifest = {"schema_version": V3_RENDER, "production_id": script["production_id"], "created_at": CANONICAL_TIMESTAMP, "config": asdict(config), "output": _relative(root, layout["video"]), "narration_audio": _relative(root, layout["narration"]), "mixed_audio": _relative(root, layout["mix"]), "subtitles": {"srt": _relative(root, layout["srt"]), "vtt": _relative(root, layout["vtt"])}, "assets": assets, "sound_effect_plan": _relative(root, layout["sfx"]), "music": "FORBIDDEN", "duration_ms": sum(scene["duration_ms"] for scene in scenes)}
    _write_json(layout["manifest"], manifest, replace=replace)
    _require(_run(command), "V3_RENDER_FAILED")
    return {"video": _relative(root, layout["video"]), "manifest": _relative(root, layout["manifest"]), "narration_audio": _relative(root, layout["narration"]), "mixed_audio": _relative(root, layout["mix"]), "duration_ms": manifest["duration_ms"], "size_bytes": layout["video"].stat().st_size}


def verify_documentary_v3_render(project_root: str | Path, *, config: DocumentaryV3Config = DocumentaryV3Config(), replace: bool = False) -> dict[str, Any]:
    root, layout = _root(project_root), _layout(_root(project_root))
    ffprobe, ffmpeg = _binary(config.ffprobe, "ffprobe"), _binary(config.ffmpeg, "ffmpeg")
    probe_process = _run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(layout["video"])])
    _require(probe_process, "V3_FFPROBE_FAILED")
    probe = json.loads(probe_process.stdout)
    streams = probe.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
    duration = float(probe.get("format", {}).get("duration", "0") or 0)
    volume = _run([ffmpeg, "-hide_banner", "-i", str(layout["video"]), "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"])
    match = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", volume.stderr)
    mean = float(match.group(1)) if match else None
    asset_manifest, sfx = _read_json(layout["assets"]), _read_json(layout["sfx"])
    checks = {"h264_video": video.get("codec_name") == "h264", "aac_audio": audio.get("codec_name") == "aac", "resolution_1920x1080": video.get("width") == WIDTH and video.get("height") == HEIGHT, "duration_60_to_90_seconds": 60 <= duration <= 90, "narration_audible": mean is not None and mean > -60, "music_forbidden": sfx.get("music") == "FORBIDDEN", "sound_effects_present": bool(sfx.get("effects")), "assets_not_placeholders": all(asset.get("authenticity_classification") != "placeholder" for asset in asset_manifest["assets"]), "asset_license_metadata": all(asset.get("license") and asset.get("sha256") for asset in asset_manifest["assets"]), "srt_present": layout["srt"].is_file(), "vtt_present": layout["vtt"].is_file(), "video_stream_present": bool(video), "audio_stream_present": bool(audio)}
    report = {"schema_version": V3_VERIFY, "created_at": CANONICAL_TIMESTAMP, "status": "VALID" if all(checks.values()) else "INVALID", "checks": checks, "duration_seconds": duration, "mean_volume_db": mean, "ffprobe": probe}
    _write_json(layout["verify"], report, replace=replace)
    return {"verification": _relative(root, layout["verify"]), "status": report["status"], "checks": checks, "duration_seconds": duration, "mean_volume_db": mean}
