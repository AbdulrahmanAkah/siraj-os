from pathlib import Path

from src.application.siraj_audio_timeline_authority_v6_6_r8_2 import (
    deterministic_alignment_failure,
)


def test_current_episode_uses_audio_bound_storyboard_as_authority():
    repo = Path(__file__).resolve().parents[1]
    module = (
        repo
        / "src/application/"
        "siraj_audio_timeline_authority_v6_6_r8_2.py"
    ).read_text(encoding="utf-8-sig")

    assert "AUTHORITATIVE_AUDIO_BOUND_STORYBOARD_RANGES" in module
    assert "NO_LAST_SHOT_STRETCH" in module
    assert "canonical_audio_duration" in module


def test_r6_1_no_longer_stretches_last_shot_to_fill_tail():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo
        / "src/application/"
        "siraj_alignment_structural_repair_v6_6_r6.py"
    ).read_text(encoding="utf-8-sig")

    assert "SIRAJ_AUDIO_TIMELINE_AUTHORITY_V6_6_R8_2" in source
    assert "LAST_END_MISMATCH_REQUIRES_AUDIO_BOUND_REPAIR" in source


def test_r3_has_convergence_guard_before_paid_luna_repair():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo
        / "src/application/"
        "siraj_alignment_semantic_autorepair_v6_6_r3.py"
    ).read_text(encoding="utf-8-sig")

    assert "SIRAJ_ALIGNMENT_CONVERGENCE_GUARD_V6_6_R8_2" in source
    assert "guard_alignment_failure_before_luna" in source


def test_deterministic_timeline_failure_is_not_sent_to_luna():
    audit = {
        "blocking_findings": [
            {
                "severity": "CRITICAL",
                "type": "timeline_duration_conflict",
                "location": "prompts.self_review",
            }
        ]
    }

    assert deterministic_alignment_failure(audit) is True
