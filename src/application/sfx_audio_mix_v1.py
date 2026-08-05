from __future__ import annotations

import hashlib
import json
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

RELEASE = "SFX_AND_AUDIO_MIX_V1"

ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
MEDIA_QUEUE_REL = Path("orchestration/media-production-queue-v1.json")
STORYBOARD_REL = Path("cinematic/storyboard-and-media-plan-v1.json")
SCRIPT_REL = Path("script/episode-script-v1.json")
STAGE_LEDGER_REL = Path("orchestration/stage-ledger-v1.json")
DEPENDENCY_GRAPH_REL = Path("orchestration/artifact-dependency-graph-v1.json")

SFX_PLAN_REL = Path("audio/sfx/sfx-audio-plan-v1.json")
SFX_ASSET_DIR_REL = Path("audio/sfx/generated")
SFX_RECEIPT_DIR_REL = Path("audio/sfx/receipts")
SFX_LICENSE_MANIFEST_REL = Path("audio/sfx/sfx-license-manifest-v1.json")
AUDIO_MIX_DIR_REL = Path("audio/mix")
NARRATION_STEM_REL = AUDIO_MIX_DIR_REL / "narration-stem-v1.wav"
SFX_STEM_REL = AUDIO_MIX_DIR_REL / "sfx-stem-v1.wav"
MASTER_WAV_REL = AUDIO_MIX_DIR_REL / "episode-audio-master-v1.wav"
MASTER_M4A_REL = AUDIO_MIX_DIR_REL / "episode-audio-master-v1.m4a"
MASTER_RECEIPT_REL = AUDIO_MIX_DIR_REL / "episode-audio-master-v1-receipt.json"
RUN_STATE_REL = Path("orchestration/sfx-audio-mix-state-v1.json")
RUN_LOCK_REL = Path("orchestration/sfx-audio-mix-v1.lock.json")
CATALOG_REL = Path("assets/sfx/catalog-v1.json")

SAMPLE_RATE = 48_000
CHANNELS = 2
NARRATION_TARGET_LUFS = -18.0
MASTER_TARGET_LUFS = -16.0
MASTER_TRUE_PEAK_DB = -1.5
MASTER_LRA = 11.0
SFX_DUCK_RATIO = 7.0
SFX_DUCK_ATTACK_MS = 18
SFX_DUCK_RELEASE_MS = 360
MAX_EVENTS = 240
BATCH_SIZE = 20

REQUIRED_FILTERS = frozenset(
    {
        "amix",
        "adelay",
        "loudnorm",
        "sidechaincompress",
        "anoisesrc",
        "sine",
        "highpass",
        "lowpass",
        "afade",
        "apad",
        "atrim",
        "aformat",
        "volume",
        "anullsrc",
        "tremolo",
        "acompressor",
        "vibrato",
    }
)

MUSIC_TERMS = (
    "music",
    "musical",
    "song",
    "score",
    "melody",
    "موسيقى",
    "موسيقية",
    "أغنية",
    "اغنية",
    "لحن",
)

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "AMBIENCE_WIND": (
        "wind",
        "breeze",
        "storm",
        "air",
        "ريح",
        "رياح",
        "نسيم",
        "عاصفة",
        "هواء",
    ),
    "RUMBLE": (
        "rumble",
        "thunder",
        "quake",
        "roar",
        "هدير",
        "رعد",
        "زلزال",
        "رجفة",
        "دوي",
    ),
    "IMPACT": (
        "impact",
        "hit",
        "crash",
        "slam",
        "fall",
        "break",
        "اصطدام",
        "ضربة",
        "سقوط",
        "تحطم",
        "ارتطام",
    ),
    "WATER": (
        "water",
        "river",
        "rain",
        "sea",
        "splash",
        "ماء",
        "نهر",
        "مطر",
        "بحر",
        "موج",
    ),
    "FIRE": (
        "fire",
        "flame",
        "crackle",
        "burn",
        "نار",
        "لهب",
        "احتراق",
        "اشتعال",
    ),
    "FOOTSTEPS": (
        "footstep",
        "footsteps",
        "walk",
        "steps",
        "خطى",
        "خطوات",
        "مشي",
    ),
    "WHOOSH": (
        "whoosh",
        "swoosh",
        "transition",
        "sweep",
        "انتقال",
        "اندفاع",
        "مرور سريع",
    ),
    "HEARTBEAT": (
        "heartbeat",
        "pulse",
        "heart",
        "نبض",
        "قلب",
    ),
    "BIRDS": (
        "bird",
        "birds",
        "طيور",
        "طائر",
    ),
    "CROWD": (
        "crowd",
        "people",
        "murmur",
        "حشد",
        "همهمة",
        "جمهور",
    ),
    "WOOD_CREAK": (
        "door",
        "wood",
        "creak",
        "باب",
        "خشب",
        "صرير",
    ),
    "CLOTH": (
        "cloth",
        "robe",
        "fabric",
        "ثوب",
        "قماش",
        "رداء",
    ),
}

CATEGORY_DEFAULTS: dict[str, dict[str, float | str]] = {
    "AMBIENCE_WIND": {"duration": 8.0, "gain_db": -24.0, "role": "AMBIENCE"},
    "RUMBLE": {"duration": 3.0, "gain_db": -18.0, "role": "ACCENT"},
    "IMPACT": {"duration": 1.4, "gain_db": -13.0, "role": "ACCENT"},
    "WATER": {"duration": 7.0, "gain_db": -23.0, "role": "AMBIENCE"},
    "FIRE": {"duration": 6.0, "gain_db": -24.0, "role": "AMBIENCE"},
    "FOOTSTEPS": {"duration": 3.5, "gain_db": -19.0, "role": "FOLEY"},
    "WHOOSH": {"duration": 1.2, "gain_db": -16.0, "role": "TRANSITION"},
    "HEARTBEAT": {"duration": 4.0, "gain_db": -21.0, "role": "FOLEY"},
    "BIRDS": {"duration": 7.0, "gain_db": -26.0, "role": "AMBIENCE"},
    "CROWD": {"duration": 7.0, "gain_db": -27.0, "role": "AMBIENCE"},
    "WOOD_CREAK": {"duration": 2.2, "gain_db": -18.0, "role": "FOLEY"},
    "CLOTH": {"duration": 2.0, "gain_db": -22.0, "role": "FOLEY"},
    "GENERIC_TEXTURE": {"duration": 3.0, "gain_db": -24.0, "role": "TEXTURE"},
}

ProgressCallback = Callable[[str, int | None], None]


class SfxAudioMixError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AudioEnvironment:
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
class SfxAudioMixResult:
    episode_id: str
    plan_path: Path
    narration_stem_path: Path
    sfx_stem_path: Path
    master_wav_path: Path
    master_m4a_path: Path
    receipt_path: Path
    event_count: int
    narration_clip_count: int
    duration_seconds: float
    status: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SfxAudioMixError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise SfxAudioMixError(f"JSON_OBJECT_REQUIRED:{path}")
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


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


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
        raise SfxAudioMixError(
            "COMMAND_FAILED:"
            + " ".join(str(value) for value in args)
            + "\nSTDOUT:\n"
            + process.stdout
            + "\nSTDERR:\n"
            + process.stderr
        )
    return process


def _tool_candidate(environment_name: str, executable: str) -> Path | None:
    configured = os.environ.get(environment_name, "").strip()
    if configured:
        path = Path(configured)
        if path.is_file():
            return path.resolve()
    found = shutil.which(executable)
    return Path(found).resolve() if found else None


@lru_cache(maxsize=4)
def _inspect_audio_tools(
    ffmpeg_text: str,
    ffprobe_text: str,
) -> AudioEnvironment:
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
    missing = tuple(sorted(REQUIRED_FILTERS - filters))
    return AudioEnvironment(
        ffmpeg_path=ffmpeg,
        ffprobe_path=ffprobe,
        ffmpeg_version_line=version_line,
        available_filters=frozenset(filters),
        missing_filters=missing,
    )


def inspect_audio_environment(repo_root: Path | None = None) -> AudioEnvironment:
    del repo_root
    ffmpeg = _tool_candidate("SIRAJ_FFMPEG_EXE", "ffmpeg")
    ffprobe = _tool_candidate("SIRAJ_FFPROBE_EXE", "ffprobe")
    if ffprobe is None and ffmpeg is not None:
        candidate = ffmpeg.with_name(
            "ffprobe.exe" if os.name == "nt" else "ffprobe"
        )
        if candidate.is_file():
            ffprobe = candidate
    return _inspect_audio_tools(
        str(ffmpeg) if ffmpeg is not None else "",
        str(ffprobe) if ffprobe is not None else "",
    )


def require_audio_environment(repo_root: Path | None = None) -> AudioEnvironment:
    environment = inspect_audio_environment(repo_root)
    errors: list[str] = []
    if environment.ffmpeg_path is None:
        errors.append("FFMPEG_NOT_AVAILABLE")
    if environment.ffprobe_path is None:
        errors.append("FFPROBE_NOT_AVAILABLE")
    if environment.missing_filters:
        errors.append(
            "FFMPEG_AUDIO_FILTERS_MISSING:"
            + ",".join(environment.missing_filters)
        )
    if errors:
        raise SfxAudioMixError(
            "AUDIO_ENVIRONMENT_NOT_READY:" + "|".join(errors)
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
        raise SfxAudioMixError("CURRENT_EPISODE_REQUIRED_FOR_SFX_AUDIO_MIX")
    episode_root = repo / "projects" / episode_id.strip()
    queue_path = episode_root / MEDIA_QUEUE_REL
    if not queue_path.is_file():
        raise SfxAudioMixError("MEDIA_PRODUCTION_QUEUE_NOT_FOUND")
    queue = _read(queue_path)
    allowed = {
        "MEDIA_ASSETS_COMPLETE",
        "SFX_DESIGN_ACTIVE",
        "SFX_AUDIO_MIX_FAILED",
        "SFX_MIX_READY",
    }
    status = str(state.get("status", ""))
    if status not in allowed:
        raise SfxAudioMixError(f"SFX_AUDIO_MIX_NOT_ALLOWED:{status}")
    return episode_id.strip(), episode_root, queue_path, state, queue


def _all_media_complete(queue: Mapping[str, Any]) -> bool:
    queues = queue.get("queues")
    if not isinstance(queues, Mapping):
        return False
    required = (
        "runware_images",
        "runware_videos",
        "local_graphics",
        "elevenlabs_tts",
    )
    seen = 0
    for key in required:
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


def _probe_duration(environment: AudioEnvironment, path: Path) -> float:
    if environment.ffprobe_path is None:
        raise SfxAudioMixError("FFPROBE_NOT_AVAILABLE")
    process = _command(
        [
            str(environment.ffprobe_path),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    try:
        duration = float(process.stdout.strip())
    except ValueError as exc:
        raise SfxAudioMixError(f"AUDIO_DURATION_INVALID:{path}") from exc
    if duration <= 0:
        raise SfxAudioMixError(f"AUDIO_DURATION_NON_POSITIVE:{path}")
    return duration


def _shot_timeline(storyboard: Mapping[str, Any]) -> tuple[list[dict[str, Any]], float]:
    raw_shots = storyboard.get("shots")
    if not isinstance(raw_shots, list) or not raw_shots:
        raise SfxAudioMixError("STORYBOARD_SHOTS_REQUIRED")
    shots = sorted(
        (dict(item) for item in raw_shots if isinstance(item, Mapping)),
        key=lambda item: int(item.get("queue_index", 0)),
    )
    if len(shots) != len(raw_shots):
        raise SfxAudioMixError("STORYBOARD_SHOT_OBJECT_REQUIRED")
    cursor = 0.0
    result = []
    for shot in shots:
        duration = float(shot.get("editorial_duration_seconds", 0.0))
        if duration <= 0:
            raise SfxAudioMixError(
                "SHOT_DURATION_INVALID:" + str(shot.get("shot_id", ""))
            )
        start = cursor
        end = start + duration
        cursor = end
        copy = dict(shot)
        copy["timeline_start_seconds"] = round(start, 6)
        copy["timeline_end_seconds"] = round(end, 6)
        result.append(copy)
    if not 1080.0 <= cursor <= 1500.0:
        raise SfxAudioMixError(
            f"EPISODE_DURATION_OUTSIDE_CONSTITUTION:{cursor:.3f}"
        )
    return result, round(cursor, 6)


def _segment_spans(shots: Sequence[Mapping[str, Any]]) -> dict[str, tuple[float, float]]:
    spans: dict[str, tuple[float, float]] = {}
    for shot in shots:
        start = float(shot["timeline_start_seconds"])
        end = float(shot["timeline_end_seconds"])
        for segment_id in _sequence(shot.get("segment_ids")):
            key = str(segment_id)
            current = spans.get(key)
            spans[key] = (
                min(start, current[0]) if current else start,
                max(end, current[1]) if current else end,
            )
    return spans


def _music_forbidden(text: str) -> None:
    lowered = text.lower()
    if any(term in lowered for term in MUSIC_TERMS):
        raise SfxAudioMixError("MUSIC_OR_MUSICAL_CUE_FORBIDDEN:" + text)


def _cue_text(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("description_ar", "cue_ar", "text_ar", "description"):
            text = _clean(value.get(key))
            if text:
                return text
        return ""
    return _clean(value)


def classify_sfx_cue(text: str) -> str:
    lowered = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return "GENERIC_TEXTURE"


def _event_timing(
    shot_start: float,
    shot_duration: float,
    category: str,
    ordinal: int,
    cue_count: int,
) -> tuple[float, float]:
    defaults = CATEGORY_DEFAULTS[category]
    role = str(defaults["role"])
    base_duration = float(defaults["duration"])
    if role == "AMBIENCE":
        return shot_start, max(0.5, shot_duration)
    duration = min(base_duration, max(0.5, shot_duration - 0.2))
    available = max(0.0, shot_duration - duration)
    fraction = ordinal / max(1, cue_count + 1)
    start = shot_start + min(available, max(0.15, available * fraction))
    return start, duration


def _load_catalog(repo: Path) -> dict[str, Any]:
    path = repo / CATALOG_REL
    if not path.is_file():
        return {
            "schema_version": "siraj-local-sfx-catalog-v1",
            "music": "FORBIDDEN",
            "entries": [],
        }
    catalog = _read(path)
    if str(catalog.get("music", "FORBIDDEN")) != "FORBIDDEN":
        raise SfxAudioMixError("SFX_CATALOG_MUSIC_POLICY_INVALID")
    entries = catalog.get("entries")
    if not isinstance(entries, list):
        raise SfxAudioMixError("SFX_CATALOG_ENTRIES_REQUIRED")
    return catalog


def _catalog_match(
    repo: Path,
    catalog: Mapping[str, Any],
    category: str,
) -> dict[str, Any] | None:
    for entry in _sequence(catalog.get("entries")):
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("category", "")) != category:
            continue
        relative = _clean(entry.get("path_relative"))
        if not relative:
            continue
        path = repo / relative
        if path.is_file():
            result = dict(entry)
            result["resolved_path"] = path
            return result
    return None


def build_sfx_audio_plan(
    repo_root: Path,
    *,
    environment: AudioEnvironment | None = None,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    environment = environment or require_audio_environment(repo)
    episode_id, episode_root, _, _, queue = _active_episode(repo)
    if not _all_media_complete(queue):
        raise SfxAudioMixError("MEDIA_ASSETS_MUST_BE_COMPLETE_BEFORE_SFX")

    storyboard = _read(episode_root / STORYBOARD_REL)
    script = _read(episode_root / SCRIPT_REL)
    shots, episode_duration = _shot_timeline(storyboard)
    spans = _segment_spans(shots)
    queues = queue["queues"]

    narration_clips: list[dict[str, Any]] = []
    cursor_by_segment: dict[str, float] = {}
    global_cursor = 0.25
    timeline_warnings: list[str] = []
    for item in sorted(
        (value for value in queues["elevenlabs_tts"] if isinstance(value, Mapping)),
        key=lambda value: int(value.get("queue_index", 0)),
    ):
        segment_id = str(item.get("segment_id", ""))
        relative = _clean(item.get("output_path_relative"))
        if not relative:
            raise SfxAudioMixError(f"TTS_OUTPUT_PATH_REQUIRED:{segment_id}")
        path = repo / relative
        if not path.is_file():
            raise SfxAudioMixError(f"TTS_OUTPUT_MISSING:{relative}")
        duration = _probe_duration(environment, path)
        span = spans.get(segment_id)
        if span is None:
            start = global_cursor
            timeline_warnings.append(
                f"TTS_SEGMENT_NOT_REFERENCED_BY_STORYBOARD:{segment_id}"
            )
        else:
            start = cursor_by_segment.get(segment_id, span[0] + 0.25)
        end = start + duration
        if end > episode_duration + 1e-6:
            raise SfxAudioMixError(
                f"NARRATION_EXCEEDS_EPISODE_TIMELINE:{segment_id}:{end:.3f}"
            )
        if span is not None and end > span[1] + 0.25:
            timeline_warnings.append(
                f"NARRATION_SPILLS_SEGMENT_SPAN:{segment_id}:{end - span[1]:.3f}"
            )
        cursor_by_segment[segment_id] = end + 0.12
        global_cursor = max(global_cursor, end + 0.12)
        narration_clips.append(
            {
                "queue_id": str(item.get("queue_id", "")),
                "segment_id": segment_id,
                "block_id": item.get("block_id"),
                "speaker_key": item.get("speaker_key"),
                "voice_slot": item.get("voice_slot"),
                "source_path_relative": relative,
                "source_sha256": _sha256(path),
                "start_seconds": round(start, 6),
                "duration_seconds": round(duration, 6),
                "end_seconds": round(end, 6),
                "target_lufs": NARRATION_TARGET_LUFS,
            }
        )

    catalog = _load_catalog(repo)
    events: list[dict[str, Any]] = []
    authored_silence_shots: list[str] = []
    event_number = 0
    license_entries: list[dict[str, Any]] = []
    for shot in shots:
        shot_id = str(shot.get("shot_id", ""))
        cues = [
            text
            for text in (_cue_text(value) for value in _sequence(shot.get("sfx_cues_ar")))
            if text
        ]
        if not cues:
            authored_silence_shots.append(shot_id)
            continue
        for ordinal, text in enumerate(cues, start=1):
            _music_forbidden(text)
            event_number += 1
            if event_number > MAX_EVENTS:
                raise SfxAudioMixError(f"SFX_EVENT_LIMIT_EXCEEDED:{MAX_EVENTS}")
            category = classify_sfx_cue(text)
            start, duration = _event_timing(
                float(shot["timeline_start_seconds"]),
                float(shot["editorial_duration_seconds"]),
                category,
                ordinal,
                len(cues),
            )
            event_id = f"SFX-{event_number:03d}"
            match = _catalog_match(repo, catalog, category)
            if match is not None:
                mode = "LOCAL_LIBRARY"
                library_path = Path(match["resolved_path"])
                source_relative = _relative(repo, library_path)
                license_entries.append(
                    {
                        "event_id": event_id,
                        "source_mode": mode,
                        "source_path_relative": source_relative,
                        "license": match.get("license"),
                        "attribution": match.get("attribution"),
                        "source_sha256": _sha256(library_path),
                    }
                )
            else:
                mode = "PROCEDURAL_LOCAL"
                source_relative = None
                license_entries.append(
                    {
                        "event_id": event_id,
                        "source_mode": mode,
                        "license": "SIRAJ_LOCAL_PROCEDURAL_GENERATION",
                        "attribution": "Not required",
                    }
                )
            asset_relative = str(
                (SFX_ASSET_DIR_REL / f"{event_id}.wav").as_posix()
            )
            defaults = CATEGORY_DEFAULTS[category]
            events.append(
                {
                    "event_id": event_id,
                    "shot_id": shot_id,
                    "sequence_id": shot.get("sequence_id"),
                    "description_ar": text,
                    "category": category,
                    "role": defaults["role"],
                    "source_mode": mode,
                    "library_source_path_relative": source_relative,
                    "asset_path_relative": str(
                        (Path("projects") / episode_id / asset_relative).as_posix()
                    ),
                    "receipt_path_relative": str(
                        (
                            Path("projects")
                            / episode_id
                            / SFX_RECEIPT_DIR_REL
                            / f"{event_id}-receipt.json"
                        ).as_posix()
                    ),
                    "start_seconds": round(start, 6),
                    "duration_seconds": round(duration, 6),
                    "end_seconds": round(start + duration, 6),
                    "gain_db": float(defaults["gain_db"]),
                    "music": "FORBIDDEN",
                    "api_cost_usd": 0.0,
                }
            )

    plan: dict[str, Any] = {
        "schema_version": "siraj-sfx-audio-plan-v1",
        "release": RELEASE,
        "episode_id": episode_id,
        "status": "READY_FOR_LOCAL_RENDER_AND_MIX",
        "episode_duration_seconds": episode_duration,
        "sample_rate": SAMPLE_RATE,
        "channels": CHANNELS,
        "music": "FORBIDDEN",
        "sound_policy": "NARRATION_SFX_AND_AUTHORED_SILENCE_ONLY",
        "narration_target_lufs": NARRATION_TARGET_LUFS,
        "master_target_lufs": MASTER_TARGET_LUFS,
        "master_true_peak_db": MASTER_TRUE_PEAK_DB,
        "master_lra": MASTER_LRA,
        "ducking": {
            "ratio": SFX_DUCK_RATIO,
            "attack_ms": SFX_DUCK_ATTACK_MS,
            "release_ms": SFX_DUCK_RELEASE_MS,
        },
        "narration_clips": narration_clips,
        "sfx_events": events,
        "authored_silence_shot_ids": authored_silence_shots,
        "timeline_warnings": timeline_warnings,
        "license_manifest": {
            "schema_version": "siraj-sfx-license-manifest-v1",
            "episode_id": episode_id,
            "music": "FORBIDDEN",
            "entries": license_entries,
        },
        "outputs": {
            "narration_stem_relative": str(
                (Path("projects") / episode_id / NARRATION_STEM_REL).as_posix()
            ),
            "sfx_stem_relative": str(
                (Path("projects") / episode_id / SFX_STEM_REL).as_posix()
            ),
            "master_wav_relative": str(
                (Path("projects") / episode_id / MASTER_WAV_REL).as_posix()
            ),
            "master_m4a_relative": str(
                (Path("projects") / episode_id / MASTER_M4A_REL).as_posix()
            ),
        },
        "ffmpeg_version": environment.ffmpeg_version_line,
        "paid_provider_requests": 0,
        "local_api_cost_usd": 0.0,
        "created_at_utc": _now(),
    }
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def _fade_values(duration: float) -> tuple[float, float]:
    fade_in = min(0.45, max(0.05, duration * 0.18))
    fade_out = min(0.55, max(0.08, duration * 0.22))
    start_out = max(0.0, duration - fade_out)
    return fade_in, start_out


def _procedural_filter(category: str, duration: float, seed: int) -> str:
    fade_in, start_out = _fade_values(duration)
    common = (
        f",aformat=sample_rates={SAMPLE_RATE}:channel_layouts=stereo"
        f",afade=t=in:st=0:d={fade_in:.4f}"
        f",afade=t=out:st={start_out:.4f}:d={duration - start_out:.4f}"
    )
    if category == "AMBIENCE_WIND":
        return (
            f"anoisesrc=color=pink:amplitude=0.11:sample_rate={SAMPLE_RATE}:"
            f"duration={duration:.4f}:seed={seed},highpass=f=80,lowpass=f=3200,"
            "tremolo=f=0.18:d=0.32" + common
        )
    if category == "RUMBLE":
        return (
            f"anoisesrc=color=brown:amplitude=0.22:sample_rate={SAMPLE_RATE}:"
            f"duration={duration:.4f}:seed={seed},highpass=f=24,lowpass=f=240,"
            "acompressor=threshold=0.08:ratio=3:attack=15:release=240" + common
        )
    if category == "IMPACT":
        return (
            f"sine=frequency=54:sample_rate={SAMPLE_RATE}:duration={duration:.4f},"
            "volume=-4dB,lowpass=f=320" + common
        )
    if category == "WATER":
        return (
            f"anoisesrc=color=pink:amplitude=0.13:sample_rate={SAMPLE_RATE}:"
            f"duration={duration:.4f}:seed={seed},highpass=f=500,lowpass=f=6500,"
            "tremolo=f=1.4:d=0.42" + common
        )
    if category == "FIRE":
        return (
            f"anoisesrc=color=white:amplitude=0.09:sample_rate={SAMPLE_RATE}:"
            f"duration={duration:.4f}:seed={seed},highpass=f=850,lowpass=f=7600,"
            "tremolo=f=7.0:d=0.72" + common
        )
    if category == "FOOTSTEPS":
        return (
            f"anoisesrc=color=brown:amplitude=0.18:sample_rate={SAMPLE_RATE}:"
            f"duration={duration:.4f}:seed={seed},highpass=f=70,lowpass=f=900,"
            "tremolo=f=1.75:d=0.93" + common
        )
    if category == "WHOOSH":
        return (
            f"anoisesrc=color=white:amplitude=0.16:sample_rate={SAMPLE_RATE}:"
            f"duration={duration:.4f}:seed={seed},highpass=f=260,lowpass=f=9000"
            + common
        )
    if category == "HEARTBEAT":
        return (
            f"sine=frequency=62:sample_rate={SAMPLE_RATE}:duration={duration:.4f},"
            "lowpass=f=180,tremolo=f=1.25:d=0.95" + common
        )
    if category == "BIRDS":
        return (
            f"anoisesrc=color=pink:amplitude=0.055:sample_rate={SAMPLE_RATE}:"
            f"duration={duration:.4f}:seed={seed},highpass=f=2100,lowpass=f=9200,"
            "tremolo=f=4.1:d=0.82" + common
        )
    if category == "CROWD":
        return (
            f"anoisesrc=color=pink:amplitude=0.08:sample_rate={SAMPLE_RATE}:"
            f"duration={duration:.4f}:seed={seed},highpass=f=160,lowpass=f=3600,"
            "tremolo=f=0.42:d=0.25" + common
        )
    if category == "WOOD_CREAK":
        return (
            f"sine=frequency=138:sample_rate={SAMPLE_RATE}:duration={duration:.4f},"
            "vibrato=f=4.2:d=0.82,highpass=f=70,lowpass=f=1800" + common
        )
    if category == "CLOTH":
        return (
            f"anoisesrc=color=white:amplitude=0.055:sample_rate={SAMPLE_RATE}:"
            f"duration={duration:.4f}:seed={seed},highpass=f=2400,lowpass=f=9000,"
            "tremolo=f=3.2:d=0.72" + common
        )
    return (
        f"anoisesrc=color=pink:amplitude=0.07:sample_rate={SAMPLE_RATE}:"
        f"duration={duration:.4f}:seed={seed},highpass=f=120,lowpass=f=5200"
        + common
    )


def _render_silence(
    environment: AudioEnvironment,
    output_path: Path,
    duration: float,
) -> None:
    assert environment.ffmpeg_path is not None
    output_path.parent.mkdir(parents=True, exist_ok=True)
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
            f"anullsrc=r={SAMPLE_RATE}:cl=stereo",
            "-t",
            f"{duration:.6f}",
            "-c:a",
            "pcm_s24le",
            str(output_path),
        ]
    )


def _render_event_asset(
    repo: Path,
    episode_root: Path,
    environment: AudioEnvironment,
    event: Mapping[str, Any],
) -> tuple[Path, Path, dict[str, Any]]:
    assert environment.ffmpeg_path is not None
    event_id = str(event["event_id"])
    output_path = repo / str(event["asset_path_relative"])
    receipt_path = repo / str(event["receipt_path_relative"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = float(event["duration_seconds"])
    source_mode = str(event["source_mode"])
    if source_mode == "LOCAL_LIBRARY":
        source_relative = str(event.get("library_source_path_relative", ""))
        source = repo / source_relative
        if not source.is_file():
            raise SfxAudioMixError(f"SFX_LIBRARY_SOURCE_MISSING:{source_relative}")
        _command(
            [
                str(environment.ffmpeg_path),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(source),
                "-t",
                f"{duration:.6f}",
                "-af",
                (
                    f"aformat=sample_rates={SAMPLE_RATE}:channel_layouts=stereo,"
                    f"afade=t=in:st=0:d={min(0.35, duration / 4):.4f},"
                    f"afade=t=out:st={max(0.0, duration - 0.45):.4f}:"
                    f"d={min(0.45, duration):.4f}"
                ),
                "-c:a",
                "pcm_s24le",
                str(output_path),
            ]
        )
        source_sha = _sha256(source)
    else:
        seed = int(hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:8], 16)
        filter_spec = _procedural_filter(
            str(event["category"]),
            duration,
            seed,
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
                filter_spec,
                "-t",
                f"{duration:.6f}",
                "-c:a",
                "pcm_s24le",
                str(output_path),
            ]
        )
        source_sha = None
    receipt = {
        "schema_version": "siraj-local-sfx-receipt-v1",
        "release": RELEASE,
        "episode_id": episode_root.name,
        "event_id": event_id,
        "shot_id": event.get("shot_id"),
        "provider": "LOCAL",
        "service": "SFX_PROCEDURAL_OR_LICENSED_LIBRARY",
        "cost_category": "SOUND_EFFECTS",
        "source_mode": source_mode,
        "source_sha256": source_sha,
        "actual_cost_usd": 0.0,
        "estimated_cost_usd": 0.0,
        "output_path_relative": _relative(repo, output_path),
        "output_sha256": _sha256(output_path),
        "output_bytes": output_path.stat().st_size,
        "duration_seconds": duration,
        "music": "FORBIDDEN",
        "created_at_utc": _now(),
    }
    _write(receipt_path, receipt)
    return output_path, receipt_path, receipt


def _mix_batch(
    environment: AudioEnvironment,
    clips: Sequence[Mapping[str, Any]],
    output_path: Path,
    episode_duration: float,
    *,
    narration: bool,
) -> None:
    assert environment.ffmpeg_path is not None
    if not clips:
        _render_silence(environment, output_path, episode_duration)
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args: list[str] = [
        str(environment.ffmpeg_path),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
    ]
    filters: list[str] = []
    labels: list[str] = []
    for index, clip in enumerate(clips):
        source = Path(str(clip["absolute_path"]))
        args.extend(["-i", str(source)])
        delay_ms = max(0, int(round(float(clip["start_seconds"]) * 1000)))
        label = f"c{index}"
        if narration:
            chain = (
                f"[{index}:a]aformat=sample_fmts=fltp:sample_rates={SAMPLE_RATE}:"
                "channel_layouts=stereo,"
                f"loudnorm=I={NARRATION_TARGET_LUFS}:TP=-2.0:LRA=7,"
                f"adelay=delays={delay_ms}:all=1[{label}]"
            )
        else:
            gain_db = float(clip.get("gain_db", -24.0))
            chain = (
                f"[{index}:a]aformat=sample_fmts=fltp:sample_rates={SAMPLE_RATE}:"
                "channel_layouts=stereo,"
                f"volume={gain_db:.3f}dB,"
                f"adelay=delays={delay_ms}:all=1[{label}]"
            )
        filters.append(chain)
        labels.append(f"[{label}]")
    filters.append(
        "".join(labels)
        + f"amix=inputs={len(labels)}:duration=longest:normalize=0:"
        "dropout_transition=0,"
        f"apad=whole_dur={episode_duration:.6f},"
        f"atrim=0:{episode_duration:.6f}[out]"
    )
    args.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[out]",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            str(CHANNELS),
            "-c:a",
            "pcm_s24le",
            str(output_path),
        ]
    )
    _command(args)


def _mix_clips_to_stem(
    environment: AudioEnvironment,
    clips: Sequence[Mapping[str, Any]],
    output_path: Path,
    episode_duration: float,
    *,
    narration: bool,
) -> None:
    if len(clips) <= BATCH_SIZE:
        _mix_batch(
            environment,
            clips,
            output_path,
            episode_duration,
            narration=narration,
        )
        return
    with tempfile.TemporaryDirectory(prefix="siraj-audio-batches-") as temporary:
        root = Path(temporary)
        batches: list[dict[str, Any]] = []
        for number, start in enumerate(range(0, len(clips), BATCH_SIZE), start=1):
            batch_path = root / f"batch-{number:03d}.wav"
            _mix_batch(
                environment,
                clips[start : start + BATCH_SIZE],
                batch_path,
                episode_duration,
                narration=narration,
            )
            batches.append(
                {
                    "absolute_path": str(batch_path),
                    "start_seconds": 0.0,
                    "gain_db": 0.0,
                }
            )
        _mix_batch(
            environment,
            batches,
            output_path,
            episode_duration,
            narration=False,
        )


def _render_master(
    environment: AudioEnvironment,
    narration_path: Path,
    sfx_path: Path,
    master_wav: Path,
    master_m4a: Path,
    episode_duration: float,
) -> None:
    assert environment.ffmpeg_path is not None
    master_wav.parent.mkdir(parents=True, exist_ok=True)
    filter_graph = (
        "[1:a][0:a]sidechaincompress="
        f"threshold=0.035:ratio={SFX_DUCK_RATIO}:"
        f"attack={SFX_DUCK_ATTACK_MS}:release={SFX_DUCK_RELEASE_MS}[ducked];"
        "[ducked]volume=0.78[duckedlevel];"
        "[0:a][duckedlevel]amix=inputs=2:duration=longest:normalize=0:"
        "dropout_transition=0,"
        f"loudnorm=I={MASTER_TARGET_LUFS}:TP={MASTER_TRUE_PEAK_DB}:"
        f"LRA={MASTER_LRA},"
        f"apad=whole_dur={episode_duration:.6f},"
        f"atrim=0:{episode_duration:.6f}[master]"
    )
    _command(
        [
            str(environment.ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(narration_path),
            "-i",
            str(sfx_path),
            "-filter_complex",
            filter_graph,
            "-map",
            "[master]",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            str(CHANNELS),
            "-c:a",
            "pcm_s24le",
            str(master_wav),
        ]
    )
    _command(
        [
            str(environment.ffmpeg_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(master_wav),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(master_m4a),
        ]
    )


def _exclusive_lock(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise SfxAudioMixError("SFX_AUDIO_MIX_ALREADY_RUNNING") from exc
    try:
        os.write(descriptor, raw)
    finally:
        os.close(descriptor)


def _upsert_node(
    nodes: list[dict[str, Any]],
    index: dict[str, dict[str, Any]],
    node_id: str,
    kind: str,
    source_id: str,
    status: str,
    path_relative: str | None,
    sha256: str | None,
) -> None:
    node = index.get(node_id)
    if node is None:
        node = {
            "node_id": node_id,
            "kind": kind,
            "source_id": source_id,
            "status": status,
            "version": 1,
            "artifact_path_relative": path_relative,
            "artifact_sha256": sha256,
            "invalidated_at_utc": None,
            "invalidation_reason": None,
        }
        nodes.append(node)
        index[node_id] = node
    else:
        node.update(
            {
                "kind": kind,
                "source_id": source_id,
                "status": status,
                "artifact_path_relative": path_relative,
                "artifact_sha256": sha256,
                "invalidated_at_utc": None,
                "invalidation_reason": None,
            }
        )


def _edge(edges: list[dict[str, str]], parent: str, child: str) -> None:
    candidate = {"from": parent, "to": child}
    if candidate not in edges:
        edges.append(candidate)


def _update_dependency_graph(
    repo: Path,
    episode_id: str,
    episode_root: Path,
    plan_path: Path,
    master_path: Path,
    events: Sequence[Mapping[str, Any]],
    narration_clips: Sequence[Mapping[str, Any]],
) -> None:
    path = episode_root / DEPENDENCY_GRAPH_REL
    if not path.is_file():
        return
    graph = _read(path)
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise SfxAudioMixError("DEPENDENCY_GRAPH_STRUCTURE_INVALID")
    index = {
        str(node.get("node_id")): node
        for node in nodes
        if isinstance(node, dict)
    }
    plan_node = f"{episode_id}:SFX_PLAN"
    master_node = f"{episode_id}:AUDIO_MASTER"
    _upsert_node(
        nodes,
        index,
        plan_node,
        "SFX_AUDIO_PLAN",
        episode_id,
        "COMPLETE",
        _relative(repo, plan_path),
        _sha256(plan_path),
    )
    _upsert_node(
        nodes,
        index,
        master_node,
        "AUDIO_MASTER",
        episode_id,
        "COMPLETE",
        _relative(repo, master_path),
        _sha256(master_path),
    )
    media_queue_node = f"{episode_id}:MEDIA_QUEUE"
    if media_queue_node in index:
        _edge(edges, media_queue_node, plan_node)
    _edge(edges, plan_node, master_node)
    for event in events:
        node_id = f"{episode_id}:SFX_ASSET:{event['event_id']}"
        asset_path = repo / str(event["asset_path_relative"])
        _upsert_node(
            nodes,
            index,
            node_id,
            "LOCAL_SFX_ASSET",
            str(event["event_id"]),
            "COMPLETE",
            _relative(repo, asset_path),
            _sha256(asset_path),
        )
        _edge(edges, plan_node, node_id)
        _edge(edges, node_id, master_node)
    for clip in narration_clips:
        node_id = f"{episode_id}:TTS_ASSET:{clip['queue_id']}"
        clip_path = repo / str(clip["source_path_relative"])
        _upsert_node(
            nodes,
            index,
            node_id,
            "ELEVENLABS_TTS_ASSET",
            str(clip["queue_id"]),
            "COMPLETE",
            _relative(repo, clip_path),
            _sha256(clip_path),
        )
        _edge(edges, node_id, master_node)
    graph["status"] = "SFX_MIX_READY"
    graph["updated_at_utc"] = _now()
    graph.pop("graph_sha256", None)
    graph["graph_sha256"] = canonical_sha256(graph)
    _write(path, graph)


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
        raise SfxAudioMixError("STAGE_LEDGER_STAGES_REQUIRED")
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        if stage.get("stage") == "SFX_DESIGN":
            stage["status"] = "COMPLETE"
            stage["artifact_path_relative"] = _relative(repo, plan_path)
            stage["receipt_path_relative"] = _relative(repo, receipt_path)
            stage["updated_at_utc"] = _now()
        elif stage.get("stage") == "STRUCTURAL_MONTAGE":
            stage["status"] = "QUEUED"
    ledger["status"] = "SFX_MIX_READY"
    ledger["resume_from"] = "STRUCTURAL_MONTAGE"
    ledger["updated_at_utc"] = _now()
    _write(path, ledger)


def run_sfx_audio_mix(
    repo_root: Path,
    *,
    progress: ProgressCallback | None = None,
) -> SfxAudioMixResult:
    repo = repo_root.resolve()
    environment = require_audio_environment(repo)
    episode_id, episode_root, _, state, queue = _active_episode(repo)
    if not _all_media_complete(queue):
        raise SfxAudioMixError("MEDIA_ASSETS_MUST_BE_COMPLETE_BEFORE_SFX")
    state_path = repo / ORCHESTRATOR_STATE_REL
    lock_path = episode_root / RUN_LOCK_REL
    _exclusive_lock(
        lock_path,
        {
            "schema_version": "siraj-sfx-audio-mix-lock-v1",
            "release": RELEASE,
            "episode_id": episode_id,
            "status": "LOCKED_LOCAL_EXECUTION",
            "paid_provider_requests": 0,
            "created_at_utc": _now(),
        },
    )
    state.update(
        {
            "status": "SFX_DESIGN_ACTIVE",
            "stage": "SFX_DESIGN",
            "next_stage": "SFX_AND_AUDIO_MIX_V1",
            "last_error": None,
            "updated_at_utc": _now(),
        }
    )
    _write(state_path, state)
    try:
        if progress:
            progress("بناء خطة المؤثرات والخط الزمني الصوتي.", 5)
        plan = build_sfx_audio_plan(repo, environment=environment)
        plan_path = episode_root / SFX_PLAN_REL
        _write(plan_path, plan)
        _write(
            episode_root / SFX_LICENSE_MANIFEST_REL,
            plan["license_manifest"],
        )

        events = list(plan["sfx_events"])
        for index, event in enumerate(events, start=1):
            if progress:
                progress(
                    f"إنشاء المؤثر المحلي {index}/{len(events)}.",
                    8 + int(32 * index / max(1, len(events))),
                )
            _render_event_asset(
                repo,
                episode_root,
                environment,
                event,
            )

        narration_clips = []
        for clip in plan["narration_clips"]:
            value = dict(clip)
            value["absolute_path"] = str(
                repo / str(clip["source_path_relative"])
            )
            narration_clips.append(value)
        sfx_clips = []
        for event in events:
            value = dict(event)
            value["absolute_path"] = str(
                repo / str(event["asset_path_relative"])
            )
            sfx_clips.append(value)

        narration_path = episode_root / NARRATION_STEM_REL
        sfx_path = episode_root / SFX_STEM_REL
        master_wav = episode_root / MASTER_WAV_REL
        master_m4a = episode_root / MASTER_M4A_REL
        receipt_path = episode_root / MASTER_RECEIPT_REL
        duration = float(plan["episode_duration_seconds"])

        if progress:
            progress("تركيب مسار التعليق الصوتي.", 48)
        _mix_clips_to_stem(
            environment,
            narration_clips,
            narration_path,
            duration,
            narration=True,
        )
        if progress:
            progress("تركيب مسار المؤثرات والصمت المصمم.", 65)
        _mix_clips_to_stem(
            environment,
            sfx_clips,
            sfx_path,
            duration,
            narration=False,
        )
        if progress:
            progress("خفض المؤثرات تحت الكلام وضبط جهارة الماستر.", 82)
        _render_master(
            environment,
            narration_path,
            sfx_path,
            master_wav,
            master_m4a,
            duration,
        )

        receipt = {
            "schema_version": "siraj-audio-master-receipt-v1",
            "release": RELEASE,
            "episode_id": episode_id,
            "provider": "LOCAL",
            "service": "SFX_DESIGN_NARRATION_MIX_AND_MASTER",
            "cost_category": "SOUND_EFFECTS",
            "actual_cost_usd": 0.0,
            "estimated_cost_usd": 0.0,
            "music": "FORBIDDEN",
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS,
            "episode_duration_seconds": duration,
            "narration_clip_count": len(narration_clips),
            "sfx_event_count": len(events),
            "narration_stem_relative": _relative(repo, narration_path),
            "narration_stem_sha256": _sha256(narration_path),
            "sfx_stem_relative": _relative(repo, sfx_path),
            "sfx_stem_sha256": _sha256(sfx_path),
            "master_wav_relative": _relative(repo, master_wav),
            "master_wav_sha256": _sha256(master_wav),
            "master_m4a_relative": _relative(repo, master_m4a),
            "master_m4a_sha256": _sha256(master_m4a),
            "ffmpeg_version": environment.ffmpeg_version_line,
            "paid_provider_requests": 0,
            "created_at_utc": _now(),
        }
        _write(receipt_path, receipt)
        _update_dependency_graph(
            repo,
            episode_id,
            episode_root,
            plan_path,
            master_wav,
            events,
            narration_clips,
        )
        _update_stage_ledger(
            repo,
            episode_root,
            plan_path,
            receipt_path,
        )
        state.update(
            {
                "status": "SFX_MIX_READY",
                "stage": "STRUCTURAL_MONTAGE",
                "next_stage": "STRUCTURAL_MONTAGE_AND_FINAL_RENDER_V1",
                "sfx_audio_plan_path_relative": _relative(repo, plan_path),
                "audio_master_path_relative": _relative(repo, master_wav),
                "audio_master_sha256": _sha256(master_wav),
                "last_error": None,
                "updated_at_utc": _now(),
            }
        )
        _write(state_path, state)
        _write(
            episode_root / RUN_STATE_REL,
            {
                "schema_version": "siraj-sfx-audio-mix-state-v1",
                "release": RELEASE,
                "episode_id": episode_id,
                "status": "COMPLETE",
                "plan_path_relative": _relative(repo, plan_path),
                "master_wav_path_relative": _relative(repo, master_wav),
                "master_m4a_path_relative": _relative(repo, master_m4a),
                "receipt_path_relative": _relative(repo, receipt_path),
                "event_count": len(events),
                "narration_clip_count": len(narration_clips),
                "paid_provider_requests": 0,
                "completed_at_utc": _now(),
            },
        )
        if progress:
            progress("اكتملت المؤثرات والمكساج والماستر الصوتي.", 100)
        return SfxAudioMixResult(
            episode_id=episode_id,
            plan_path=plan_path,
            narration_stem_path=narration_path,
            sfx_stem_path=sfx_path,
            master_wav_path=master_wav,
            master_m4a_path=master_m4a,
            receipt_path=receipt_path,
            event_count=len(events),
            narration_clip_count=len(narration_clips),
            duration_seconds=duration,
            status="SFX_MIX_READY",
        )
    except Exception as exc:
        state.update(
            {
                "status": "SFX_AUDIO_MIX_FAILED",
                "stage": "SFX_DESIGN",
                "next_stage": "RESUME_SFX_AND_AUDIO_MIX_V1",
                "last_error": str(exc),
                "updated_at_utc": _now(),
            }
        )
        _write(state_path, state)
        _write(
            episode_root / RUN_STATE_REL,
            {
                "schema_version": "siraj-sfx-audio-mix-state-v1",
                "release": RELEASE,
                "episode_id": episode_id,
                "status": "FAILED",
                "last_error": str(exc),
                "paid_provider_requests": 0,
                "updated_at_utc": _now(),
            },
        )
        if isinstance(exc, SfxAudioMixError):
            raise
        raise SfxAudioMixError(str(exc)) from exc
    finally:
        lock_path.unlink(missing_ok=True)


def load_sfx_audio_mix_status(repo_root: Path) -> dict[str, Any]:
    repo = repo_root.resolve()
    try:
        state = _read(repo / ORCHESTRATOR_STATE_REL)
    except SfxAudioMixError:
        return {
            "status": "NO_ORCHESTRATOR_STATE",
            "ready": False,
        }
    episode_id = state.get("current_episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        return {
            "status": str(state.get("status", "IDLE")),
            "ready": False,
        }
    episode_root = repo / "projects" / episode_id
    run_state_path = episode_root / RUN_STATE_REL
    run_state = _read(run_state_path) if run_state_path.is_file() else {}
    master = episode_root / MASTER_WAV_REL
    status = str(state.get("status", "UNKNOWN"))
    downstream = {
        "STRUCTURAL_MONTAGE_ACTIVE",
        "STRUCTURAL_MONTAGE_FAILED",
        "FINAL_RENDER_READY_FOR_QA",
        "AUTOMATIC_QA_ACTIVE",
        "AUTOMATIC_QA_FAILED",
        "AUTOMATIC_QA_COMPLETE",
        "AWAITING_HUMAN_FINAL_REVIEW",
        "READY_TO_PUBLISH",
    }
    complete = master.is_file() and (
        run_state.get("status") == "COMPLETE"
        or status == "SFX_MIX_READY"
        or status in downstream
    )
    return {
        "episode_id": episode_id,
        "status": status,
        "stage": str(state.get("stage", "")),
        "last_error": state.get("last_error"),
        "ready": status
        in {
            "MEDIA_ASSETS_COMPLETE",
            "SFX_AUDIO_MIX_FAILED",
            "SFX_MIX_READY",
            *downstream,
        },
        "complete": complete,
        "master_wav_path": str(master),
        "master_m4a_path": str(episode_root / MASTER_M4A_REL),
        "event_count": run_state.get("event_count", 0),
        "narration_clip_count": run_state.get("narration_clip_count", 0),
    }


def run_audio_smoke_test(
    repo_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    environment = require_audio_environment(repo_root)
    output_root.mkdir(parents=True, exist_ok=True)
    narration = output_root / "smoke-narration.wav"
    sfx = output_root / "smoke-sfx.wav"
    master_wav = output_root / "smoke-master.wav"
    master_m4a = output_root / "smoke-master.m4a"
    _render_silence(environment, narration, 1.2)
    assert environment.ffmpeg_path is not None
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
            _procedural_filter("AMBIENCE_WIND", 1.2, 20260805),
            "-t",
            "1.2",
            "-c:a",
            "pcm_s24le",
            str(sfx),
        ]
    )
    _render_master(
        environment,
        narration,
        sfx,
        master_wav,
        master_m4a,
        1.2,
    )
    return {
        "status": "PASS",
        "ffmpeg_version": environment.ffmpeg_version_line,
        "master_wav_sha256": _sha256(master_wav),
        "master_m4a_sha256": _sha256(master_m4a),
        "paid_provider_requests": 0,
    }
