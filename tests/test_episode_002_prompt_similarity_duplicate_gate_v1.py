from __future__ import annotations

from pathlib import Path

from src.application.episode_002_prompt_similarity_duplicate_gate_v1 import analyze_promoted_plan
from src.application.siraj_prompt_duplicate_gate_v6_1 import prompt_text


def test_provider_ready_prompt_is_the_canonical_duplicate_gate_input():
    assert prompt_text({"provider_ready_prompt": "promoted direction", "prompt": "legacy"}) == "promoted direction"


def test_promoted_episode_002_plan_passes_local_duplicate_analysis_without_resume():
    result = analyze_promoted_plan(Path(__file__).resolve().parents[1])
    assert result["status"] == "PASS"
    assert result["promoted_overlay_sha256"] == "254c600144032f621d44ff38b33409fc0875da1aaf9310f106fb347b86205509"
    assert not result["exact_duplicates"]
    assert not result["near_duplicates"]
    assert not result["semantic_repetition_findings"]
    assert result["luna_gate_001"] == "CLOSED_BY_LOCAL_DUPLICATE_GATE"
    assert result["next_stage_executed"] is False
    assert result["production_resume_entrypoint"] == "DESKTOP_UI_ONLY"


def test_committed_gate_is_stopped_before_media_cost_preflight_execution():
    import json

    root = Path(__file__).resolve().parents[1]
    gate = json.loads((root / "projects" / "episode-002-adam-temptation-fall-repentance" / "orchestration" / "prompt-similarity-duplicate-gate-promoted-v1.json").read_text(encoding="utf-8-sig"))
    assert gate["status"] == "PASS"
    assert gate["luna_gate_001"] == "CLOSED_BY_LOCAL_DUPLICATE_GATE"
    assert gate["next_stage"] == "MEDIA_COST_PREFLIGHT"
    assert gate["next_stage_executed"] is False
    assert gate["production_resume_entrypoint"] == "DESKTOP_UI_ONLY"
