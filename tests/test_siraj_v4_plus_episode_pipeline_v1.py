import json
from pathlib import Path
import pytest

from src.application.siraj_v4_plus_episode_pipeline_v1 import (
    V4PlusEpisodePipelineError,
    validate_stage_artifact,
)

def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

def test_script_cannot_fix_duration_before_tts(tmp_path):
    root = tmp_path
    path = root / "script/final-script-v3.json"
    _write(path, {
        "status": "FINAL",
        "target_duration_seconds": 900,
        "narration_blocks": [{"text_ar": "نص"}],
    })
    with pytest.raises(V4PlusEpisodePipelineError):
        validate_stage_artifact(root, "FINAL_SCRIPT")

def test_storyboard_requires_final_tts_hash(tmp_path):
    _write(tmp_path / "audio/final-tts-manifest-v3.json", {
        "status": "FINAL",
        "tts_sha256": "abc",
    })
    _write(tmp_path / "cinematic/audio-bound-storyboard-v3.json", {
        "status": "PASS",
        "source_tts_sha256": "wrong",
        "shots": [],
    })
    with pytest.raises(V4PlusEpisodePipelineError):
        validate_stage_artifact(tmp_path, "AUDIO_BOUND_STORYBOARD")

def test_pronunciation_gate_requires_performance_markers(tmp_path):
    _write(tmp_path / "audio/pronunciation-performance-gate-v1.json", {
        "status": "PASS",
        "all_ambiguous_terms_reviewed": True,
        "hook_intro_pause_directed": True,
        "closing_performance_directed": False,
        "pre_outro_pause_directed": True,
    })
    with pytest.raises(V4PlusEpisodePipelineError):
        validate_stage_artifact(tmp_path, "PRONUNCIATION_AND_PERFORMANCE_GATE")
