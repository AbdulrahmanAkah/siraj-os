"""FFmpeg-based narration loudness normalization."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any


AUDIO_MASTERING_REPORT_SCHEMA_V1 = (
    "siraj-audio-mastering-report-v1"
)


@dataclass(frozen=True)
class AudioMasteringResult:
    status: str
    input_path: str
    output_path: str
    report_path: str
    input_integrated_lufs: float
    output_integrated_lufs: float
    output_true_peak_dbtp: float


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
    code: str,
) -> None:
    if process.returncode == 0:
        return

    detail = (
        process.stderr[-6000:]
        or process.stdout[-6000:]
    )

    raise RuntimeError(
        f"{code}:{detail}"
    )


def _resolve_executable(
    name: str,
) -> str:
    resolved = shutil.which(name)

    if not resolved:
        raise FileNotFoundError(
            f"EXECUTABLE_NOT_FOUND:{name}"
        )

    return resolved


def _extract_json_object(
    text: str,
) -> dict[str, Any]:
    matches = re.findall(
        r"\{[\s\S]*?\}",
        text,
    )

    if not matches:
        raise RuntimeError(
            "LOUDNORM_JSON_MISSING"
        )

    value = json.loads(
        matches[-1]
    )

    if not isinstance(value, dict):
        raise RuntimeError(
            "LOUDNORM_JSON_INVALID"
        )

    return value


def _project_path(
    project_root: Path,
    relative_path: str,
    *,
    must_exist: bool,
) -> Path:
    root = project_root.resolve()

    candidate = (
        root / relative_path
    ).resolve(strict=False)

    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "AUDIO_PATH_OUTSIDE_PROJECT"
        ) from error

    if must_exist and not candidate.is_file():
        raise FileNotFoundError(
            f"AUDIO_FILE_NOT_FOUND:{candidate}"
        )

    candidate.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return candidate

def analyze_loudness(
    input_path: Path,
    *,
    ffmpeg: str = "ffmpeg",
    target_lufs: float = -19.0,
    true_peak_dbtp: float = -2.0,
    target_lra: float = 7.0,
) -> dict[str, Any]:
    executable = _resolve_executable(
        ffmpeg
    )

    process = _run(
        [
            executable,
            "-hide_banner",
            "-i",
            str(input_path),
            "-af",
            (
                "loudnorm="
                f"I={target_lufs}:"
                f"TP={true_peak_dbtp}:"
                f"LRA={target_lra}:"
                "print_format=json"
            ),
            "-f",
            "null",
            "NUL",
        ]
    )

    _require_success(
        process,
        "LOUDNESS_ANALYSIS_FAILED",
    )

    return _extract_json_object(
        process.stderr
    )


def verify_loudness(
    input_path: Path,
    *,
    ffmpeg: str = "ffmpeg",
    target_lufs: float = -19.0,
    true_peak_dbtp: float = -2.0,
    target_lra: float = 7.0,
) -> dict[str, Any]:
    return analyze_loudness(
        input_path,
        ffmpeg=ffmpeg,
        target_lufs=target_lufs,
        true_peak_dbtp=true_peak_dbtp,
        target_lra=target_lra,
    )

def master_audio(
    project_root: str | Path,
    input_relative_path: str,
    output_relative_path: str,
    report_relative_path: str,
    *,
    ffmpeg: str = "ffmpeg",
    target_lufs: float = -19.0,
    true_peak_dbtp: float = -2.0,
    target_lra: float = 7.0,
) -> AudioMasteringResult:
    root = Path(
        project_root
    ).resolve()

    if not root.is_dir():
        raise FileNotFoundError(
            f"PROJECT_ROOT_NOT_FOUND:{root}"
        )

    input_path = _project_path(
        root,
        input_relative_path,
        must_exist=True,
    )

    output_path = _project_path(
        root,
        output_relative_path,
        must_exist=False,
    )

    report_path = _project_path(
        root,
        report_relative_path,
        must_exist=False,
    )

    executable = _resolve_executable(
        ffmpeg
    )

    analysis = analyze_loudness(
        input_path,
        ffmpeg=executable,
        target_lufs=target_lufs,
        true_peak_dbtp=true_peak_dbtp,
        target_lra=target_lra,
    )

    measured_i = float(
        analysis["input_i"]
    )

    measured_tp = float(
        analysis["input_tp"]
    )

    measured_lra = float(
        analysis["input_lra"]
    )

    measured_thresh = float(
        analysis["input_thresh"]
    )

    offset = float(
        analysis["target_offset"]
    )

    filter_expression = (
        "loudnorm="
        f"I={target_lufs}:"
        f"TP={true_peak_dbtp}:"
        f"LRA={target_lra}:"
        f"measured_I={measured_i}:"
        f"measured_TP={measured_tp}:"
        f"measured_LRA={measured_lra}:"
        f"measured_thresh={measured_thresh}:"
        f"offset={offset}:"
        "linear=true:"
        "print_format=summary"
    )

    process = _run(
        [
            executable,
            "-hide_banner",
            "-y",
            "-i",
            str(input_path),
            "-af",
            filter_expression,
            "-ar",
            "48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )

    _require_success(
        process,
        "AUDIO_MASTERING_FAILED",
    )

    verification = verify_loudness(
        output_path,
        ffmpeg=executable,
        target_lufs=target_lufs,
        true_peak_dbtp=true_peak_dbtp,
        target_lra=target_lra,
    )

    output_i = float(
        verification["input_i"]
    )

    output_tp = float(
        verification["input_tp"]
    )

    loudness_ok = (
        abs(
            output_i - target_lufs
        )
        <= 0.6
    )

    peak_ok = (
        output_tp
        <= true_peak_dbtp + 0.2
    )

    status = (
        "VALID"
        if loudness_ok and peak_ok
        else "INVALID"
    )

    report = {
        "schema_version": (
            AUDIO_MASTERING_REPORT_SCHEMA_V1
        ),
        "status": status,
        "input": str(input_path),
        "output": str(output_path),
        "target_integrated_lufs": (
            target_lufs
        ),
        "target_true_peak_dbtp": (
            true_peak_dbtp
        ),
        "input_measurement": analysis,
        "output_measurement": verification,
        "checks": {
            "integrated_loudness": (
                loudness_ok
            ),
            "true_peak": peak_ok,
        },
    }

    report_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return AudioMasteringResult(
        status=status,
        input_path=str(input_path),
        output_path=str(output_path),
        report_path=str(report_path),
        input_integrated_lufs=(
            measured_i
        ),
        output_integrated_lufs=(
            output_i
        ),
        output_true_peak_dbtp=(
            output_tp
        ),
    )