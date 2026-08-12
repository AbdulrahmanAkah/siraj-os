from __future__ import annotations
from pathlib import Path
import re

class FinalTtsProbePatchV652Error(RuntimeError):
    pass

def patch_episode2_probe(path: Path) -> str:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    marker = "SIRAJ_PURE_PYTHON_MP3_DURATION_V6_5_2"
    if marker in text:
        return "ALREADY_PATCHED"

    pattern = re.compile(
        r"def _probe_duration_seconds\(path: Path\) -> float \| None:\n"
        r".*?"
        r"(?=\ndef _audio_looks_valid)",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise FinalTtsProbePatchV652Error(
            "EP2_DURATION_PROBE_FUNCTION_NOT_FOUND"
        )

    replacement = '''def _probe_duration_seconds(path: Path) -> float | None:
    # SIRAJ_PURE_PYTHON_MP3_DURATION_V6_5_2
    from src.application.siraj_mp3_duration_v6_5_2 import (
        probe_audio_duration_seconds,
    )

    value = probe_audio_duration_seconds(path)
    if value is not None:
        return round(float(value), 3)

    ffprobe = os.environ.get("SIRAJ_FFPROBE_EXE", "").strip()
    if not ffprobe:
        return None

    process = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        return None
    try:
        value = float(process.stdout.strip())
    except ValueError:
        return None
    return round(value, 3) if value > 0 else None

'''
    text = (
        text[:match.start()]
        + replacement
        + text[match.end():]
    )
    path.write_text(text, encoding="utf-8")
    return "PATCHED"

def patch_generic_probe(path: Path) -> str:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    marker = "SIRAJ_PURE_PYTHON_MP3_DURATION_V6_5_2"
    if marker in text:
        return "ALREADY_PATCHED"

    pattern = re.compile(
        r"def _probe_duration\(path: Path\) -> float \| None:\n"
        r".*?"
        r"(?=\ndef _validate_series_locks)",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise FinalTtsProbePatchV652Error(
            "GENERIC_DURATION_PROBE_FUNCTION_NOT_FOUND"
        )

    replacement = '''def _probe_duration(path: Path) -> float | None:
    # SIRAJ_PURE_PYTHON_MP3_DURATION_V6_5_2
    from src.application.siraj_mp3_duration_v6_5_2 import (
        probe_audio_duration_seconds,
    )

    value = probe_audio_duration_seconds(path)
    if value is not None:
        return round(float(value), 3)

    ffprobe = os.environ.get("SIRAJ_FFPROBE_EXE", "").strip()
    if not ffprobe:
        return None

    process = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if process.returncode:
        return None
    try:
        value = float(process.stdout.strip())
    except ValueError:
        return None
    return round(value, 3) if value > 0 else None

'''
    text = (
        text[:match.start()]
        + replacement
        + text[match.end():]
    )
    path.write_text(text, encoding="utf-8")
    return "PATCHED"
