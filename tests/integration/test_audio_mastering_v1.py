from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.local_video_production.audio_mastering_v1 import (
    _extract_json_object,
    _project_path,
)


def test_extract_loudnorm_json() -> None:
    text = """
    ffmpeg output
    {
        "input_i": "-22.48",
        "input_tp": "-18.40",
        "input_lra": "0.70",
        "input_thresh": "-32.50",
        "target_offset": "0.01"
    }
    """

    result = _extract_json_object(
        text
    )

    assert result["input_i"] == "-22.48"
    assert result["input_tp"] == "-18.40"


def test_extract_json_rejects_missing_object() -> None:
    with pytest.raises(
        RuntimeError,
        match="LOUDNORM_JSON_MISSING",
    ):
        _extract_json_object(
            "no loudnorm result"
        )


def test_project_path_accepts_internal_output(
    tmp_path: Path,
) -> None:
    result = _project_path(
        tmp_path,
        "audio/mastered.wav",
        must_exist=False,
    )

    assert result == (
        tmp_path
        / "audio"
        / "mastered.wav"
    ).resolve()


def test_project_path_rejects_escape(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ValueError,
        match="AUDIO_PATH_OUTSIDE_PROJECT",
    ):
        _project_path(
            tmp_path,
            "../outside.wav",
            must_exist=False,
        )


def test_live_mastering_report_is_valid() -> None:
    report_path = Path(
        r"C:\SIRAJ\Workspace\first-project"
        r"\manifests"
        r"\diagnostic-voice-v1-mastering-report.json"
    )

    if not report_path.is_file():
        pytest.skip(
            "Live mastering fixture unavailable"
        )

    report = json.loads(
        report_path.read_text(
            encoding="utf-8-sig"
        )
    )

    assert report["status"] == "VALID"
    assert (
        report["checks"][
            "integrated_loudness"
        ]
        is True
    )
    assert (
        report["checks"][
            "true_peak"
        ]
        is True
    )