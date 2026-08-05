from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from src.application.artifact_dependency_graph_v1 import canonical_sha256
from src.application.structural_montage_final_render_v1 import (
    AUDIO_MASTER_REL,
    CONCAT_LIST_REL,
    FINAL_MASTER_REL,
    FINAL_RECEIPT_REL,
    FINAL_DURATION_TOLERANCE_SECONDS,
    FPS,
    HEIGHT,
    PIXEL_FORMAT,
    RENDER_PLAN_REL,
    SHOT_DIR_REL,
    SHOT_RECEIPT_DIR_REL,
    VIDEO_ONLY_REL,
    WIDTH,
    StructuralMontageError,
    inspect_montage_environment,
    run_structural_montage_final_render,
)

RELEASE = "AUTOMATIC_QA_AND_PARTIAL_REPAIR_V1"

ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
STAGE_LEDGER_REL = Path("orchestration/stage-ledger-v1.json")
DEPENDENCY_GRAPH_REL = Path("orchestration/artifact-dependency-graph-v1.json")
QA_REPORT_REL = Path("qa/automatic-qa-report-v1.json")
QA_STATE_REL = Path("orchestration/automatic-qa-partial-repair-state-v1.json")
QA_LOCK_REL = Path("orchestration/automatic-qa-partial-repair-v1.lock.json")

MAX_REPAIR_PASSES = 2
SHOT_DURATION_TOLERANCE_SECONDS = 0.25
MAX_UNPLANNED_BLACK_SECONDS = 1.0
MAX_STILL_FREEZE_SECONDS = 2.5
MAX_UNPLANNED_MOTION_FREEZE_SECONDS = 1.25
MAX_CONTINUOUS_SILENCE_SECONDS = 15.0
LOUDNESS_TARGET_LUFS = -16.0
LOUDNESS_TOLERANCE_LU = 2.0
MAX_TRUE_PEAK_DBTP = -0.8
MIN_AUDIO_BITRATE = 160_000

REQUIRED_QA_FILTERS = frozenset(
    {
        "blackdetect",
        "freezedetect",
        "silencedetect",
        "loudnorm",
    }
)

LOCAL_SHOT_REPAIR_CODES = frozenset(
    {
        "SHOT_OUTPUT_MISSING",
        "SHOT_RECEIPT_MISSING",
        "SHOT_RECEIPT_INVALID",
        "SHOT_OUTPUT_HASH_MISMATCH",
        "SHOT_SOURCE_HASH_CHANGED",
        "SHOT_DURATION_MISMATCH",
        "SHOT_VIDEO_PROFILE_INVALID",
        "STILL_MOTION_FLAT_OR_FROZEN",
    }
)
LOCAL_FINAL_REPAIR_CODES = frozenset(
    {
        "FINAL_MASTER_MISSING",
        "FINAL_RECEIPT_MISSING",
        "FINAL_RECEIPT_INVALID",
        "FINAL_MASTER_HASH_MISMATCH",
        "FINAL_VIDEO_PROFILE_INVALID",
        "FINAL_AUDIO_PROFILE_INVALID",
        "FINAL_DURATION_MISMATCH",
        "FINAL_STREAM_LAYOUT_INVALID",
        "AUDIO_MASTER_CHANGED_AFTER_MUX",
    }
)
UPSTREAM_MEDIA_CODES = frozenset(
    {
        "SHOT_SOURCE_MISSING",
        "GENERATED_SOURCE_VISUAL_DEFECT",
        "GRAPHICS_SOURCE_VISUAL_DEFECT",
    }
)
UPSTREAM_AUDIO_CODES = frozenset(
    {
        "AUDIO_MASTER_MISSING",
        "AUDIO_MASTER_HASH_MISMATCH",
        "LOUDNESS_OUTSIDE_CONTRACT",
        "TRUE_PEAK_OUTSIDE_CONTRACT",
        "EXCESSIVE_CONTINUOUS_SILENCE",
    }
)

ProgressCallback = Callable[[str, int | None], None]


class AutomaticQAError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class QAEnvironment:
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
class QAIssue:
    code: str
    severity: str
    scope: str
    detail: str
    repair_class: str
    shot_id: str | None = None
    observed: Any = None
    expected: Any = None


@dataclass(frozen=True, slots=True)
class AutomaticQAResult:
    episode_id: str
    status: str
    report_path: Path
    final_master_path: Path
    blocking_issue_count: int
    warning_count: int
    repair_passes: int
    repaired_shot_count: int
    reused_shot_count: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AutomaticQAError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise AutomaticQAError(f"JSON_OBJECT_REQUIRED:{path}")
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


def _relative(repo: Path, path: Path) -> str:
    return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return value
    return ()


def _command(
    args: Sequence[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        [str(value) for value in args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and process.returncode != 0:
        raise AutomaticQAError(
            "COMMAND_FAILED:"
            + " ".join(str(value) for value in args)
            + "\nSTDOUT:\n"
            + process.stdout
            + "\nSTDERR:\n"
            + process.stderr
        )
    return process


def inspect_qa_environment(repo_root: Path | None = None) -> QAEnvironment:
    montage = inspect_montage_environment(repo_root)
    missing = tuple(sorted(REQUIRED_QA_FILTERS - montage.available_filters))
    return QAEnvironment(
        ffmpeg_path=montage.ffmpeg_path,
        ffprobe_path=montage.ffprobe_path,
        ffmpeg_version_line=montage.ffmpeg_version_line,
        available_filters=montage.available_filters,
        missing_filters=missing,
    )


def require_qa_environment(repo_root: Path | None = None) -> QAEnvironment:
    environment = inspect_qa_environment(repo_root)
    errors: list[str] = []
    if environment.ffmpeg_path is None:
        errors.append("FFMPEG_NOT_AVAILABLE")
    if environment.ffprobe_path is None:
        errors.append("FFPROBE_NOT_AVAILABLE")
    if environment.missing_filters:
        errors.append("FFMPEG_QA_FILTERS_MISSING:" + ",".join(environment.missing_filters))
    if errors:
        raise AutomaticQAError("QA_ENVIRONMENT_NOT_READY:" + "|".join(errors))
    return environment


def _active_episode(
    repo: Path,
) -> tuple[str, Path, Path, dict[str, Any]]:
    state_path = repo / ORCHESTRATOR_STATE_REL
    state = _read(state_path)
    episode_id = state.get("current_episode_id")
    if not isinstance(episode_id, str) or not episode_id.strip():
        raise AutomaticQAError("CURRENT_EPISODE_REQUIRED_FOR_AUTOMATIC_QA")
    episode_root = repo / "projects" / episode_id.strip()
    if not episode_root.is_dir():
        raise AutomaticQAError("CURRENT_EPISODE_DIRECTORY_MISSING")
    return episode_id.strip(), episode_root, state_path, state


def _probe(environment: QAEnvironment, path: Path) -> dict[str, Any]:
    if environment.ffprobe_path is None:
        raise AutomaticQAError("FFPROBE_NOT_AVAILABLE")
    result = _command(
        [
            str(environment.ffprobe_path),
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ]
    )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AutomaticQAError(f"FFPROBE_JSON_INVALID:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise AutomaticQAError(f"FFPROBE_OBJECT_REQUIRED:{path}")
    return value


def _float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _rate(value: Any) -> float:
    text = str(value or "")
    if "/" not in text:
        return _float(text)
    numerator, denominator = text.split("/", 1)
    den = _float(denominator)
    return _float(numerator) / den if den else 0.0


def _streams(probe: Mapping[str, Any], kind: str) -> list[dict[str, Any]]:
    return [
        dict(stream)
        for stream in _sequence(probe.get("streams"))
        if isinstance(stream, Mapping) and stream.get("codec_type") == kind
    ]


def _duration(probe: Mapping[str, Any]) -> float:
    value = _float((probe.get("format") or {}).get("duration"))
    if value > 0:
        return value
    return max(
        (_float(stream.get("duration")) for stream in _sequence(probe.get("streams")) if isinstance(stream, Mapping)),
        default=0.0,
    )


def _detector(
    environment: QAEnvironment,
    path: Path,
    filter_name: str,
) -> str:
    if environment.ffmpeg_path is None:
        raise AutomaticQAError("FFMPEG_NOT_AVAILABLE")
    result = _command(
        [
            str(environment.ffmpeg_path),
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af" if filter_name.startswith(("silencedetect", "loudnorm")) else "-vf",
            filter_name,
            "-f",
            "null",
            "-",
        ],
        check=False,
    )
    if result.returncode != 0:
        raise AutomaticQAError(
            f"QA_DETECTOR_FAILED:{path}:{filter_name}:" + result.stderr[-2000:]
        )
    return result.stdout + "\n" + result.stderr


def _black_segments(environment: QAEnvironment, path: Path) -> list[dict[str, float]]:
    text = _detector(
        environment,
        path,
        "blackdetect=d=0.10:pic_th=0.98:pix_th=0.10",
    )
    pattern = re.compile(
        r"black_start:(?P<start>-?[0-9.]+)\s+black_end:(?P<end>-?[0-9.]+)\s+black_duration:(?P<duration>[0-9.]+)"
    )
    return [
        {key: float(match.group(key)) for key in ("start", "end", "duration")}
        for match in pattern.finditer(text)
    ]


def _freeze_segments(environment: QAEnvironment, path: Path) -> list[dict[str, float]]:
    text = _detector(environment, path, "freezedetect=n=-50dB:d=0.75")
    starts = [float(value) for value in re.findall(r"freeze_start:\s*(-?[0-9.]+)", text)]
    durations = [float(value) for value in re.findall(r"freeze_duration:\s*([0-9.]+)", text)]
    ends = [float(value) for value in re.findall(r"freeze_end:\s*(-?[0-9.]+)", text)]
    result: list[dict[str, float]] = []
    for index, duration in enumerate(durations):
        end = ends[index] if index < len(ends) else 0.0
        start = starts[index] if index < len(starts) else max(0.0, end - duration)
        result.append({"start": start, "end": end, "duration": duration})
    return result


def _silence_segments(environment: QAEnvironment, path: Path) -> list[dict[str, float]]:
    text = _detector(environment, path, "silencedetect=n=-45dB:d=1.0")
    starts = [float(value) for value in re.findall(r"silence_start:\s*(-?[0-9.]+)", text)]
    durations = [float(value) for value in re.findall(r"silence_duration:\s*([0-9.]+)", text)]
    ends = [float(value) for value in re.findall(r"silence_end:\s*(-?[0-9.]+)", text)]
    result: list[dict[str, float]] = []
    for index, duration in enumerate(durations):
        end = ends[index] if index < len(ends) else 0.0
        start = starts[index] if index < len(starts) else max(0.0, end - duration)
        result.append({"start": start, "end": end, "duration": duration})
    return result


def _loudness(environment: QAEnvironment, path: Path) -> dict[str, float | None]:
    text = _detector(
        environment,
        path,
        "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
    )
    candidates = re.findall(r"\{\s*\"input_i\".*?\}", text, flags=re.DOTALL)
    if not candidates:
        return {"integrated_lufs": None, "true_peak_dbtp": None, "lra_lu": None}
    try:
        payload = json.loads(candidates[-1])
    except json.JSONDecodeError:
        return {"integrated_lufs": None, "true_peak_dbtp": None, "lra_lu": None}
    return {
        "integrated_lufs": _float(payload.get("input_i"), float("nan")),
        "true_peak_dbtp": _float(payload.get("input_tp"), float("nan")),
        "lra_lu": _float(payload.get("input_lra"), float("nan")),
    }


def _issue(
    code: str,
    severity: str,
    scope: str,
    detail: str,
    repair_class: str,
    *,
    shot_id: str | None = None,
    observed: Any = None,
    expected: Any = None,
) -> QAIssue:
    return QAIssue(
        code=code,
        severity=severity,
        scope=scope,
        detail=detail,
        repair_class=repair_class,
        shot_id=shot_id,
        observed=observed,
        expected=expected,
    )


def _video_profile_issues(
    probe: Mapping[str, Any],
    *,
    scope: str,
    shot_id: str | None,
    expected_duration: float,
    require_audio: bool,
) -> list[QAIssue]:
    issues: list[QAIssue] = []
    videos = _streams(probe, "video")
    audios = _streams(probe, "audio")
    repair_class = "LOCAL_SHOT_RERENDER" if shot_id else "LOCAL_FINAL_REMUX"
    duration_code = "SHOT_DURATION_MISMATCH" if shot_id else "FINAL_DURATION_MISMATCH"
    video_code = "SHOT_VIDEO_PROFILE_INVALID" if shot_id else "FINAL_VIDEO_PROFILE_INVALID"
    if len(videos) != 1 or (require_audio and len(audios) != 1) or (not require_audio and audios):
        issues.append(
            _issue(
                "FINAL_STREAM_LAYOUT_INVALID" if not shot_id else video_code,
                "BLOCKING",
                scope,
                f"video_streams={len(videos)} audio_streams={len(audios)}",
                repair_class,
                shot_id=shot_id,
                observed={"video": len(videos), "audio": len(audios)},
                expected={"video": 1, "audio": 1 if require_audio else 0},
            )
        )
    if videos:
        video = videos[0]
        observed = {
            "codec": video.get("codec_name"),
            "width": _int(video.get("width")),
            "height": _int(video.get("height")),
            "fps": round(_rate(video.get("avg_frame_rate") or video.get("r_frame_rate")), 4),
            "pixel_format": video.get("pix_fmt"),
        }
        valid = (
            observed["codec"] == "h264"
            and observed["width"] == WIDTH
            and observed["height"] == HEIGHT
            and abs(float(observed["fps"]) - FPS) <= 0.02
            and observed["pixel_format"] == PIXEL_FORMAT
        )
        if not valid:
            issues.append(
                _issue(
                    video_code,
                    "BLOCKING",
                    scope,
                    "Video profile differs from the locked delivery profile.",
                    repair_class,
                    shot_id=shot_id,
                    observed=observed,
                    expected={
                        "codec": "h264",
                        "width": WIDTH,
                        "height": HEIGHT,
                        "fps": FPS,
                        "pixel_format": PIXEL_FORMAT,
                    },
                )
            )
    actual_duration = _duration(probe)
    tolerance = SHOT_DURATION_TOLERANCE_SECONDS if shot_id else FINAL_DURATION_TOLERANCE_SECONDS
    if abs(actual_duration - expected_duration) > tolerance:
        issues.append(
            _issue(
                duration_code,
                "BLOCKING",
                scope,
                "Media duration differs from the editorial timeline.",
                repair_class,
                shot_id=shot_id,
                observed=round(actual_duration, 6),
                expected=round(expected_duration, 6),
            )
        )
    if require_audio and audios:
        audio = audios[0]
        observed_audio = {
            "codec": audio.get("codec_name"),
            "sample_rate": _int(audio.get("sample_rate")),
            "channels": _int(audio.get("channels")),
            "bit_rate": _int(audio.get("bit_rate") or (probe.get("format") or {}).get("bit_rate")),
        }
        valid_audio = (
            observed_audio["codec"] == "aac"
            and observed_audio["sample_rate"] == 48_000
            and observed_audio["channels"] == 2
            and observed_audio["bit_rate"] >= MIN_AUDIO_BITRATE
        )
        if not valid_audio:
            issues.append(
                _issue(
                    "FINAL_AUDIO_PROFILE_INVALID",
                    "BLOCKING",
                    scope,
                    "Audio profile differs from AAC 48 kHz stereo 192 kbps contract.",
                    "LOCAL_FINAL_REMUX",
                    observed=observed_audio,
                    expected={
                        "codec": "aac",
                        "sample_rate": 48_000,
                        "channels": 2,
                        "minimum_bit_rate": MIN_AUDIO_BITRATE,
                    },
                )
            )
    return issues


def _check_shot(
    repo: Path,
    environment: QAEnvironment,
    shot: Mapping[str, Any],
) -> tuple[list[QAIssue], dict[str, Any]]:
    issues: list[QAIssue] = []
    shot_id = str(shot.get("shot_id", ""))
    output = repo / str(shot.get("output_path_relative", ""))
    receipt_path = repo / str(shot.get("receipt_path_relative", ""))
    source = repo / str(shot.get("source_path_relative", ""))
    summary: dict[str, Any] = {
        "shot_id": shot_id,
        "treatment": shot.get("treatment"),
        "output_path_relative": shot.get("output_path_relative"),
        "status": "PASS",
        "black_segments": [],
        "freeze_segments": [],
    }
    if not source.is_file():
        issues.append(
            _issue(
                "SHOT_SOURCE_MISSING",
                "BLOCKING",
                "SHOT",
                "The approved source media is missing.",
                "UPSTREAM_MEDIA_REQUIRED",
                shot_id=shot_id,
                observed=str(source),
            )
        )
        summary["status"] = "BLOCKED"
        return issues, summary
    if not output.is_file():
        issues.append(
            _issue(
                "SHOT_OUTPUT_MISSING",
                "BLOCKING",
                "SHOT",
                "The local montage clip is missing.",
                "LOCAL_SHOT_RERENDER",
                shot_id=shot_id,
                observed=str(output),
            )
        )
        summary["status"] = "REPAIRABLE"
        return issues, summary
    if not receipt_path.is_file():
        issues.append(
            _issue(
                "SHOT_RECEIPT_MISSING",
                "BLOCKING",
                "SHOT",
                "The montage receipt is missing.",
                "LOCAL_SHOT_RERENDER",
                shot_id=shot_id,
            )
        )
    receipt: dict[str, Any] = {}
    if receipt_path.is_file():
        try:
            receipt = _read(receipt_path)
        except AutomaticQAError as exc:
            issues.append(
                _issue(
                    "SHOT_RECEIPT_INVALID",
                    "BLOCKING",
                    "SHOT",
                    str(exc),
                    "LOCAL_SHOT_RERENDER",
                    shot_id=shot_id,
                )
            )
        else:
            actual_hash = _sha256(output)
            if receipt.get("output_sha256") != actual_hash:
                issues.append(
                    _issue(
                        "SHOT_OUTPUT_HASH_MISMATCH",
                        "BLOCKING",
                        "SHOT",
                        "Rendered shot no longer matches its receipt.",
                        "LOCAL_SHOT_RERENDER",
                        shot_id=shot_id,
                        observed=actual_hash,
                        expected=receipt.get("output_sha256"),
                    )
                )
            source_hash = _sha256(source)
            if receipt.get("source_sha256") != source_hash or shot.get("source_sha256") != source_hash:
                issues.append(
                    _issue(
                        "SHOT_SOURCE_HASH_CHANGED",
                        "BLOCKING",
                        "SHOT",
                        "Source media changed after the montage receipt was created.",
                        "LOCAL_SHOT_RERENDER",
                        shot_id=shot_id,
                        observed=source_hash,
                        expected=receipt.get("source_sha256"),
                    )
                )
            if receipt.get("render_fingerprint_sha256") != shot.get("render_fingerprint_sha256"):
                issues.append(
                    _issue(
                        "SHOT_RECEIPT_INVALID",
                        "BLOCKING",
                        "SHOT",
                        "Receipt fingerprint differs from the current render plan.",
                        "LOCAL_SHOT_RERENDER",
                        shot_id=shot_id,
                    )
                )
    try:
        probe = _probe(environment, output)
        issues.extend(
            _video_profile_issues(
                probe,
                scope="SHOT",
                shot_id=shot_id,
                expected_duration=_float(shot.get("duration_seconds")),
                require_audio=False,
            )
        )
        black = _black_segments(environment, output)
        freeze = _freeze_segments(environment, output)
        summary["black_segments"] = black
        summary["freeze_segments"] = freeze
        longest_black = max((item["duration"] for item in black), default=0.0)
        if longest_black > MAX_UNPLANNED_BLACK_SECONDS:
            treatment = str(shot.get("treatment", ""))
            repair_class = (
                "UPSTREAM_MEDIA_REQUIRED"
                if treatment in {"GENERATED_VIDEO", "GRAPHICS"}
                else "MANUAL_VISUAL_REVIEW_REQUIRED"
            )
            code = (
                "GENERATED_SOURCE_VISUAL_DEFECT"
                if treatment == "GENERATED_VIDEO"
                else "GRAPHICS_SOURCE_VISUAL_DEFECT"
                if treatment == "GRAPHICS"
                else "UNPLANNED_BLACK_VISUAL"
            )
            issues.append(
                _issue(
                    code,
                    "BLOCKING",
                    "SHOT",
                    "Black interval exceeds the sequence-fade allowance.",
                    repair_class,
                    shot_id=shot_id,
                    observed=round(longest_black, 6),
                    expected=f"<= {MAX_UNPLANNED_BLACK_SECONDS}",
                )
            )
        longest_freeze = max((item["duration"] for item in freeze), default=0.0)
        treatment = str(shot.get("treatment", ""))
        if treatment == "ANIMATED_STILL_COMPOSITING":
            if longest_freeze > MAX_STILL_FREEZE_SECONDS:
                issues.append(
                    _issue(
                        "STILL_MOTION_FLAT_OR_FROZEN",
                        "BLOCKING",
                        "SHOT",
                        "Animated still contains a long frozen interval.",
                        "LOCAL_SHOT_RERENDER",
                        shot_id=shot_id,
                        observed=round(longest_freeze, 6),
                        expected=f"<= {MAX_STILL_FREEZE_SECONDS}",
                    )
                )
        else:
            extension = max(
                0.0,
                _float(shot.get("duration_seconds"))
                - _float(shot.get("source_duration_seconds")),
            )
            allowed = extension + MAX_UNPLANNED_MOTION_FREEZE_SECONDS
            if longest_freeze > allowed:
                code = (
                    "GENERATED_SOURCE_VISUAL_DEFECT"
                    if treatment == "GENERATED_VIDEO"
                    else "GRAPHICS_SOURCE_VISUAL_DEFECT"
                )
                issues.append(
                    _issue(
                        code,
                        "BLOCKING",
                        "SHOT",
                        "Frozen interval exceeds the planned last-frame extension.",
                        "UPSTREAM_MEDIA_REQUIRED",
                        shot_id=shot_id,
                        observed=round(longest_freeze, 6),
                        expected=f"<= {allowed:.3f}",
                    )
                )
    except AutomaticQAError as exc:
        issues.append(
            _issue(
                "SHOT_VIDEO_PROFILE_INVALID",
                "BLOCKING",
                "SHOT",
                str(exc),
                "LOCAL_SHOT_RERENDER",
                shot_id=shot_id,
            )
        )
    blocking = [issue for issue in issues if issue.severity == "BLOCKING"]
    summary["status"] = "PASS" if not blocking else "BLOCKED"
    return issues, summary


def _check_final(
    repo: Path,
    environment: QAEnvironment,
    episode_root: Path,
    plan: Mapping[str, Any],
) -> tuple[list[QAIssue], dict[str, Any]]:
    issues: list[QAIssue] = []
    final_path = episode_root / FINAL_MASTER_REL
    final_receipt_path = episode_root / FINAL_RECEIPT_REL
    audio_master = episode_root / AUDIO_MASTER_REL
    summary: dict[str, Any] = {
        "final_master_path_relative": _relative(repo, final_path),
        "black_segments": [],
        "silence_segments": [],
        "loudness": {},
    }
    if not audio_master.is_file():
        issues.append(
            _issue(
                "AUDIO_MASTER_MISSING",
                "BLOCKING",
                "AUDIO_MASTER",
                "Locked narration/SFX master is missing.",
                "UPSTREAM_AUDIO_REQUIRED",
            )
        )
    if not final_path.is_file():
        issues.append(
            _issue(
                "FINAL_MASTER_MISSING",
                "BLOCKING",
                "FINAL_MASTER",
                "Final episode file is missing.",
                "LOCAL_FINAL_REMUX",
            )
        )
        return issues, summary
    receipt: dict[str, Any] = {}
    if not final_receipt_path.is_file():
        issues.append(
            _issue(
                "FINAL_RECEIPT_MISSING",
                "BLOCKING",
                "FINAL_MASTER",
                "Final render receipt is missing.",
                "LOCAL_FINAL_REMUX",
            )
        )
    else:
        try:
            receipt = _read(final_receipt_path)
        except AutomaticQAError as exc:
            issues.append(
                _issue(
                    "FINAL_RECEIPT_INVALID",
                    "BLOCKING",
                    "FINAL_MASTER",
                    str(exc),
                    "LOCAL_FINAL_REMUX",
                )
            )
        else:
            actual_hash = _sha256(final_path)
            if receipt.get("final_master_sha256") != actual_hash:
                issues.append(
                    _issue(
                        "FINAL_MASTER_HASH_MISMATCH",
                        "BLOCKING",
                        "FINAL_MASTER",
                        "Final episode no longer matches its receipt.",
                        "LOCAL_FINAL_REMUX",
                        observed=actual_hash,
                        expected=receipt.get("final_master_sha256"),
                    )
                )
            if audio_master.is_file():
                actual_audio_hash = _sha256(audio_master)
                receipt_audio_hash = receipt.get("audio_master_sha256")
                if receipt_audio_hash != actual_audio_hash:
                    issues.append(
                        _issue(
                            "AUDIO_MASTER_CHANGED_AFTER_MUX",
                            "BLOCKING",
                            "FINAL_MASTER",
                            "Locked audio master changed after final mux.",
                            "LOCAL_FINAL_REMUX",
                            observed=actual_audio_hash,
                            expected=receipt_audio_hash,
                        )
                    )
    expected_duration = _float(plan.get("episode_duration_seconds"))
    try:
        probe = _probe(environment, final_path)
        issues.extend(
            _video_profile_issues(
                probe,
                scope="FINAL_MASTER",
                shot_id=None,
                expected_duration=expected_duration,
                require_audio=True,
            )
        )
        black = _black_segments(environment, final_path)
        summary["black_segments"] = black
        longest_black = max((item["duration"] for item in black), default=0.0)
        if longest_black > MAX_UNPLANNED_BLACK_SECONDS:
            issues.append(
                _issue(
                    "FINAL_UNPLANNED_BLACK_INTERVAL",
                    "WARNING",
                    "FINAL_MASTER",
                    "Final timeline contains a long black interval; shot-level report identifies the source.",
                    "MANUAL_VISUAL_REVIEW_REQUIRED",
                    observed=round(longest_black, 6),
                    expected=f"<= {MAX_UNPLANNED_BLACK_SECONDS}",
                )
            )
        silence = _silence_segments(environment, final_path)
        summary["silence_segments"] = silence
        longest_silence = max((item["duration"] for item in silence), default=0.0)
        if longest_silence > MAX_CONTINUOUS_SILENCE_SECONDS:
            issues.append(
                _issue(
                    "EXCESSIVE_CONTINUOUS_SILENCE",
                    "BLOCKING",
                    "AUDIO_MASTER",
                    "Continuous silence exceeds the conservative automatic-QA allowance.",
                    "UPSTREAM_AUDIO_REQUIRED",
                    observed=round(longest_silence, 6),
                    expected=f"<= {MAX_CONTINUOUS_SILENCE_SECONDS}",
                )
            )
        loudness = _loudness(environment, final_path)
        summary["loudness"] = loudness
        integrated = loudness.get("integrated_lufs")
        true_peak = loudness.get("true_peak_dbtp")
        if isinstance(integrated, float) and math.isfinite(integrated):
            if abs(integrated - LOUDNESS_TARGET_LUFS) > LOUDNESS_TOLERANCE_LU:
                issues.append(
                    _issue(
                        "LOUDNESS_OUTSIDE_CONTRACT",
                        "BLOCKING",
                        "AUDIO_MASTER",
                        "Integrated loudness is outside the locked delivery window.",
                        "UPSTREAM_AUDIO_REQUIRED",
                        observed=round(integrated, 3),
                        expected=f"{LOUDNESS_TARGET_LUFS} ± {LOUDNESS_TOLERANCE_LU} LU",
                    )
                )
        else:
            issues.append(
                _issue(
                    "LOUDNESS_MEASUREMENT_UNAVAILABLE",
                    "WARNING",
                    "AUDIO_MASTER",
                    "FFmpeg did not return a usable integrated loudness measurement.",
                    "MANUAL_AUDIO_REVIEW_REQUIRED",
                )
            )
        if isinstance(true_peak, float) and math.isfinite(true_peak) and true_peak > MAX_TRUE_PEAK_DBTP:
            issues.append(
                _issue(
                    "TRUE_PEAK_OUTSIDE_CONTRACT",
                    "BLOCKING",
                    "AUDIO_MASTER",
                    "True peak exceeds the delivery ceiling.",
                    "UPSTREAM_AUDIO_REQUIRED",
                    observed=round(true_peak, 3),
                    expected=f"<= {MAX_TRUE_PEAK_DBTP} dBTP",
                )
            )
    except AutomaticQAError as exc:
        issues.append(
            _issue(
                "FINAL_VIDEO_PROFILE_INVALID",
                "BLOCKING",
                "FINAL_MASTER",
                str(exc),
                "LOCAL_FINAL_REMUX",
            )
        )
    return issues, summary


def evaluate_automatic_qa(
    repo_root: Path,
    *,
    environment: QAEnvironment | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    environment = environment or require_qa_environment(repo)
    episode_id, episode_root, _, _ = _active_episode(repo)
    plan_path = episode_root / RENDER_PLAN_REL
    if not plan_path.is_file():
        raise AutomaticQAError("STRUCTURAL_MONTAGE_RENDER_PLAN_REQUIRED")
    plan = _read(plan_path)
    shots = [dict(value) for value in _sequence(plan.get("shots")) if isinstance(value, Mapping)]
    if len(shots) != 70:
        raise AutomaticQAError("QA_REQUIRES_SEVENTY_PLANNED_SHOTS")
    if plan.get("music") != "FORBIDDEN" or plan.get("flat_slideshow") != "FORBIDDEN":
        raise AutomaticQAError("QA_POLICY_CONTRACT_CHANGED")
    issues: list[QAIssue] = []
    shot_results: list[dict[str, Any]] = []
    for index, shot in enumerate(shots, start=1):
        if progress:
            progress(
                f"فحص اللقطة {index}/70 — {shot.get('shot_id')}",
                5 + int(70 * index / len(shots)),
            )
        shot_issues, summary = _check_shot(repo, environment, shot)
        issues.extend(shot_issues)
        shot_results.append(summary)
    if progress:
        progress("فحص ملف الحلقة والصوت والتزامن.", 82)
    final_issues, final_summary = _check_final(repo, environment, episode_root, plan)
    issues.extend(final_issues)
    adjacent_duplicates: list[dict[str, str]] = []
    for previous, current in zip(shots, shots[1:]):
        left = repo / str(previous.get("output_path_relative", ""))
        right = repo / str(current.get("output_path_relative", ""))
        if left.is_file() and right.is_file() and _sha256(left) == _sha256(right):
            pair = {"left": str(previous.get("shot_id")), "right": str(current.get("shot_id"))}
            adjacent_duplicates.append(pair)
            issues.append(
                _issue(
                    "ADJACENT_IDENTICAL_SHOT_OUTPUTS",
                    "WARNING",
                    "TIMELINE",
                    "Two adjacent montage clips are byte-identical.",
                    "MANUAL_VISUAL_REVIEW_REQUIRED",
                    observed=pair,
                )
            )
    blocking = [issue for issue in issues if issue.severity == "BLOCKING"]
    warnings = [issue for issue in issues if issue.severity == "WARNING"]
    local_shots = sorted(
        {
            str(issue.shot_id)
            for issue in blocking
            if issue.shot_id and issue.code in LOCAL_SHOT_REPAIR_CODES
        }
    )
    local_final = any(issue.code in LOCAL_FINAL_REPAIR_CODES for issue in blocking)
    upstream_media = sorted(
        {
            str(issue.shot_id)
            for issue in blocking
            if issue.shot_id and issue.code in UPSTREAM_MEDIA_CODES
        }
    )
    upstream_audio = any(issue.code in UPSTREAM_AUDIO_CODES for issue in blocking)
    manual_blocking = any(
        issue.repair_class.startswith("MANUAL_") and issue.severity == "BLOCKING"
        for issue in issues
    )
    score = max(0, 100 - 20 * len(blocking) - 2 * len(warnings))
    return {
        "schema_version": "siraj-automatic-qa-evaluation-v1",
        "release": RELEASE,
        "episode_id": episode_id,
        "status": "PASS" if not blocking else "BLOCKED",
        "quality_score": score,
        "blocking_issue_count": len(blocking),
        "warning_count": len(warnings),
        "issues": [asdict(issue) for issue in issues],
        "shot_results": shot_results,
        "final_summary": final_summary,
        "adjacent_identical_outputs": adjacent_duplicates,
        "repair_plan": {
            "local_shot_ids": local_shots,
            "local_final_remux": local_final,
            "upstream_media_shot_ids": upstream_media,
            "upstream_audio_required": upstream_audio,
            "manual_blocking_review_required": manual_blocking,
            "paid_provider_requests_authorized": 0,
        },
        "policy": {
            "music": "FORBIDDEN",
            "full_regeneration_for_local_defect": "FORBIDDEN",
            "automatic_paid_regeneration": "FORBIDDEN",
            "maximum_local_repair_passes": MAX_REPAIR_PASSES,
        },
        "ffmpeg_version": environment.ffmpeg_version_line,
        "evaluated_at_utc": _now(),
    }


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _exclusive_lock(path: Path, payload: Mapping[str, Any]) -> None:
    if path.is_file():
        try:
            existing = _read(path)
        except AutomaticQAError:
            existing = {}
        pid = existing.get("pid")
        if isinstance(pid, int) and _pid_alive(pid):
            raise AutomaticQAError("AUTOMATIC_QA_ALREADY_RUNNING")
        path.unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise AutomaticQAError("AUTOMATIC_QA_ALREADY_RUNNING") from exc
    try:
        os.write(descriptor, raw)
    finally:
        os.close(descriptor)


def _invalidate_local_outputs(
    repo: Path,
    episode_root: Path,
    plan: Mapping[str, Any],
    shot_ids: Sequence[str],
    final_only: bool,
) -> None:
    selected = set(shot_ids)
    if not final_only:
        for shot in _sequence(plan.get("shots")):
            if not isinstance(shot, Mapping) or str(shot.get("shot_id")) not in selected:
                continue
            (repo / str(shot.get("output_path_relative", ""))).unlink(missing_ok=True)
            (repo / str(shot.get("receipt_path_relative", ""))).unlink(missing_ok=True)
    for relative in (
        FINAL_MASTER_REL,
        FINAL_RECEIPT_REL,
        VIDEO_ONLY_REL,
        CONCAT_LIST_REL,
    ):
        (episode_root / relative).unlink(missing_ok=True)


def _update_stage_ledger(
    episode_root: Path,
    *,
    status: str,
    report_path: Path,
    next_stage: str,
) -> None:
    path = episode_root / STAGE_LEDGER_REL
    if not path.is_file():
        return
    ledger = _read(path)
    stages = ledger.get("stages")
    if not isinstance(stages, list):
        raise AutomaticQAError("STAGE_LEDGER_STAGES_REQUIRED")
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        if stage.get("stage") == "AUTOMATIC_QA":
            stage["status"] = "COMPLETE" if status == "PASS" else "BLOCKED"
            stage["artifact_path_relative"] = str(report_path.relative_to(episode_root.parent.parent)).replace("\\", "/")
            stage["updated_at_utc"] = _now()
        elif stage.get("stage") == "HUMAN_FINAL_REVIEW":
            stage["status"] = "AWAITING_HUMAN" if status == "PASS" else "QUEUED"
    ledger["status"] = (
        "AWAITING_HUMAN_FINAL_REVIEW" if status == "PASS" else "AUTOMATIC_QA_BLOCKED"
    )
    ledger["resume_from"] = next_stage
    ledger["updated_at_utc"] = _now()
    _write(path, ledger)


def _update_dependency_graph(
    repo: Path,
    episode_id: str,
    episode_root: Path,
    report_path: Path,
    status: str,
) -> None:
    path = episode_root / DEPENDENCY_GRAPH_REL
    if not path.is_file():
        return
    graph = _read(path)
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise AutomaticQAError("DEPENDENCY_GRAPH_STRUCTURE_INVALID")
    node_id = f"{episode_id}:AUTOMATIC_QA_REPORT"
    payload = {
        "node_id": node_id,
        "kind": "AUTOMATIC_QA_REPORT",
        "source_id": episode_id,
        "status": "COMPLETE" if status == "PASS" else "BLOCKED",
        "version": 1,
        "artifact_path_relative": _relative(repo, report_path),
        "artifact_sha256": _sha256(report_path),
        "invalidated_at_utc": None,
        "invalidation_reason": None,
    }
    existing = next(
        (node for node in nodes if isinstance(node, dict) and node.get("node_id") == node_id),
        None,
    )
    if existing is None:
        nodes.append(payload)
    else:
        existing.update(payload)
    edge = {"from": f"{episode_id}:FINAL_RENDER", "to": node_id}
    if edge not in edges:
        edges.append(edge)
    graph["status"] = "AUTOMATIC_QA_PASS" if status == "PASS" else "AUTOMATIC_QA_BLOCKED"
    graph["updated_at_utc"] = _now()
    graph.pop("graph_sha256", None)
    graph["graph_sha256"] = canonical_sha256(graph)
    _write(path, graph)


def _next_stage_for_block(evaluation: Mapping[str, Any]) -> str:
    repair = evaluation.get("repair_plan")
    if not isinstance(repair, Mapping):
        return "REVIEW_AUTOMATIC_QA_REPORT"
    if repair.get("upstream_audio_required"):
        return "SFX_DESIGN"
    if _sequence(repair.get("upstream_media_shot_ids")):
        return "DESKTOP_MEDIA_EXECUTION"
    return "HUMAN_FINAL_REVIEW"


def run_automatic_qa_and_partial_repair(
    repo_root: Path,
    *,
    progress: ProgressCallback | None = None,
) -> AutomaticQAResult:
    repo = repo_root.resolve()
    environment = require_qa_environment(repo)
    episode_id, episode_root, state_path, state = _active_episode(repo)
    allowed = {
        "FINAL_RENDER_READY_FOR_QA",
        "AUTOMATIC_QA_FAILED",
        "AUTOMATIC_QA_BLOCKED",
        "AWAITING_HUMAN_FINAL_REVIEW",
        "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED",
    }
    if str(state.get("status")) not in allowed:
        raise AutomaticQAError(f"AUTOMATIC_QA_NOT_ALLOWED:{state.get('status')}")
    lock_path = episode_root / QA_LOCK_REL
    _exclusive_lock(
        lock_path,
        {
            "schema_version": "siraj-automatic-qa-lock-v1",
            "release": RELEASE,
            "episode_id": episode_id,
            "pid": os.getpid(),
            "paid_provider_requests": 0,
            "created_at_utc": _now(),
        },
    )
    report_path = episode_root / QA_REPORT_REL
    run_state_path = episode_root / QA_STATE_REL
    repair_passes = 0
    repaired_shots: set[str] = set()
    reused_shots = 0
    state.update(
        {
            "status": "AUTOMATIC_QA_ACTIVE",
            "stage": "AUTOMATIC_QA",
            "next_stage": "RUN_AUTOMATIC_QA_AND_LOCAL_REPAIR",
            "last_error": None,
            "updated_at_utc": _now(),
        }
    )
    _write(state_path, state)
    try:
        if progress:
            progress("بدء الفحص الآلي الحتمي للحلقة.", 1)
        evaluation = evaluate_automatic_qa(repo, environment=environment, progress=progress)
        history: list[dict[str, Any]] = [evaluation]
        while evaluation["status"] != "PASS" and repair_passes < MAX_REPAIR_PASSES:
            repair = evaluation.get("repair_plan")
            if not isinstance(repair, Mapping):
                break
            upstream = bool(repair.get("upstream_audio_required")) or bool(
                _sequence(repair.get("upstream_media_shot_ids"))
            ) or bool(repair.get("manual_blocking_review_required"))
            shot_ids = [str(value) for value in _sequence(repair.get("local_shot_ids"))]
            final_only = bool(repair.get("local_final_remux")) and not shot_ids
            if upstream or (not shot_ids and not final_only):
                break
            repair_passes += 1
            repaired_shots.update(shot_ids)
            if progress:
                label = ", ".join(shot_ids) if shot_ids else "الملف النهائي"
                progress(
                    f"إصلاح محلي جزئي — المرور {repair_passes}/{MAX_REPAIR_PASSES}: {label}",
                    86,
                )
            plan = _read(episode_root / RENDER_PLAN_REL)
            _invalidate_local_outputs(repo, episode_root, plan, shot_ids, final_only)
            montage_result = run_structural_montage_final_render(repo)
            reused_shots += montage_result.reused_shot_count
            evaluation = evaluate_automatic_qa(repo, environment=environment, progress=progress)
            history.append(evaluation)
        final_status = "PASS" if evaluation["status"] == "PASS" else "BLOCKED"
        report = {
            "schema_version": "siraj-automatic-qa-report-v1",
            "release": RELEASE,
            "episode_id": episode_id,
            "status": final_status,
            "repair_passes": repair_passes,
            "repaired_shot_ids": sorted(repaired_shots),
            "reused_shot_count_during_repairs": reused_shots,
            "latest_evaluation": evaluation,
            "evaluation_history": history,
            "automatic_paid_regeneration": "FORBIDDEN",
            "paid_provider_requests": 0,
            "local_api_cost_usd": 0.0,
            "completed_at_utc": _now(),
        }
        report["report_sha256"] = canonical_sha256(report)
        _write(report_path, report)
        if final_status == "PASS":
            next_stage = "HUMAN_FINAL_REVIEW"
            state.update(
                {
                    "status": "AWAITING_HUMAN_FINAL_REVIEW",
                    "stage": "HUMAN_FINAL_REVIEW",
                    "next_stage": "HUMAN_FINAL_REVIEW_AND_PUBLISHING_V1",
                    "automatic_qa_report_path_relative": _relative(repo, report_path),
                    "automatic_qa_report_sha256": _sha256(report_path),
                    "last_error": None,
                    "updated_at_utc": _now(),
                }
            )
        else:
            next_stage = _next_stage_for_block(evaluation)
            state.update(
                {
                    "status": "AUTOMATIC_QA_BLOCKED",
                    "stage": "AUTOMATIC_QA",
                    "next_stage": next_stage,
                    "automatic_qa_report_path_relative": _relative(repo, report_path),
                    "automatic_qa_report_sha256": _sha256(report_path),
                    "last_error": "AUTOMATIC_QA_BLOCKING_ISSUES_REMAIN",
                    "updated_at_utc": _now(),
                }
            )
        _write(state_path, state)
        _update_stage_ledger(
            episode_root,
            status=final_status,
            report_path=report_path,
            next_stage=next_stage,
        )
        _update_dependency_graph(
            repo,
            episode_id,
            episode_root,
            report_path,
            final_status,
        )
        _write(
            run_state_path,
            {
                "schema_version": "siraj-automatic-qa-partial-repair-state-v1",
                "release": RELEASE,
                "episode_id": episode_id,
                "status": final_status,
                "repair_passes": repair_passes,
                "repaired_shot_ids": sorted(repaired_shots),
                "blocking_issue_count": evaluation["blocking_issue_count"],
                "warning_count": evaluation["warning_count"],
                "report_path_relative": _relative(repo, report_path),
                "paid_provider_requests": 0,
                "updated_at_utc": _now(),
            },
        )
        if progress:
            progress(
                "نجح الفحص الآلي وانتقلت الحلقة إلى المراجعة البشرية النهائية."
                if final_status == "PASS"
                else "توقف الفحص عند عيوب مصدرية أو بشرية لا يجوز إصلاحها تلقائيًا.",
                100,
            )
        return AutomaticQAResult(
            episode_id=episode_id,
            status=(
                "AWAITING_HUMAN_FINAL_REVIEW"
                if final_status == "PASS"
                else "AUTOMATIC_QA_BLOCKED"
            ),
            report_path=report_path,
            final_master_path=episode_root / FINAL_MASTER_REL,
            blocking_issue_count=int(evaluation["blocking_issue_count"]),
            warning_count=int(evaluation["warning_count"]),
            repair_passes=repair_passes,
            repaired_shot_count=len(repaired_shots),
            reused_shot_count=reused_shots,
        )
    except Exception as exc:
        state.update(
            {
                "status": "AUTOMATIC_QA_FAILED",
                "stage": "AUTOMATIC_QA",
                "next_stage": "RESUME_AUTOMATIC_QA_AND_PARTIAL_REPAIR_V1",
                "last_error": str(exc),
                "updated_at_utc": _now(),
            }
        )
        _write(state_path, state)
        _write(
            run_state_path,
            {
                "schema_version": "siraj-automatic-qa-partial-repair-state-v1",
                "release": RELEASE,
                "episode_id": episode_id,
                "status": "FAILED",
                "last_error": str(exc),
                "paid_provider_requests": 0,
                "updated_at_utc": _now(),
            },
        )
        if isinstance(exc, AutomaticQAError):
            raise
        if isinstance(exc, StructuralMontageError):
            raise AutomaticQAError(str(exc)) from exc
        raise AutomaticQAError(str(exc)) from exc
    finally:
        lock_path.unlink(missing_ok=True)


def load_automatic_qa_status(repo_root: Path) -> dict[str, Any]:
    repo = repo_root.resolve()
    try:
        episode_id, episode_root, _, state = _active_episode(repo)
    except AutomaticQAError as exc:
        return {"status": "NOT_READY", "ready": False, "last_error": str(exc)}
    report_path = episode_root / QA_REPORT_REL
    run_state_path = episode_root / QA_STATE_REL
    run_state = _read(run_state_path) if run_state_path.is_file() else {}
    status = str(state.get("status", "UNKNOWN"))
    return {
        "episode_id": episode_id,
        "status": status,
        "stage": str(state.get("stage", "")),
        "last_error": state.get("last_error"),
        "ready": status in {
            "FINAL_RENDER_READY_FOR_QA",
            "AUTOMATIC_QA_FAILED",
            "AUTOMATIC_QA_BLOCKED",
            "AWAITING_HUMAN_FINAL_REVIEW",
            "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED",
            "READY_TO_PUBLISH",
        },
        "complete": status in {
            "AWAITING_HUMAN_FINAL_REVIEW",
            "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED",
            "READY_TO_PUBLISH",
        } and report_path.is_file(),
        "report_path": str(report_path),
        "final_master_path": str(episode_root / FINAL_MASTER_REL),
        "blocking_issue_count": run_state.get("blocking_issue_count", 0),
        "warning_count": run_state.get("warning_count", 0),
        "repair_passes": run_state.get("repair_passes", 0),
        "repaired_shot_ids": run_state.get("repaired_shot_ids", []),
    }


def run_qa_smoke_test(
    repo_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    environment = require_qa_environment(repo_root)
    if environment.ffmpeg_path is None:
        raise AutomaticQAError("FFMPEG_NOT_AVAILABLE")
    output_root.mkdir(parents=True, exist_ok=True)
    sample = output_root / "qa-smoke.mp4"
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
            "testsrc2=size=1920x1080:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=2",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(sample),
        ]
    )
    probe = _probe(environment, sample)
    black = _black_segments(environment, sample)
    freeze = _freeze_segments(environment, sample)
    silence = _silence_segments(environment, sample)
    loudness = _loudness(environment, sample)
    profile_issues = _video_profile_issues(
        probe,
        scope="SMOKE",
        shot_id=None,
        expected_duration=2.0,
        require_audio=True,
    )
    return {
        "status": "PASS" if not profile_issues else "FAIL",
        "ffmpeg_version": environment.ffmpeg_version_line,
        "sample_sha256": _sha256(sample),
        "black_segments": black,
        "freeze_segments": freeze,
        "silence_segments": silence,
        "loudness": loudness,
        "profile_issue_count": len(profile_issues),
        "paid_provider_requests": 0,
    }
