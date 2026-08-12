from pathlib import Path

from src.application.siraj_alignment_structural_repair_v6_6_r6 import (
    canonicalize_timeline_partition,
)


def test_partition_normalizer_repairs_gap_and_overlap():
    items = [
        {
            "shot_id": "S1",
            "start_seconds": 0.0,
            "end_seconds": 10.0,
            "final_budget_treatment": "ANIMATED_STILL_COMPOSITING",
        },
        {
            "shot_id": "S2",
            "start_seconds": 11.0,
            "end_seconds": 20.0,
            "final_budget_treatment": "ANIMATED_STILL_COMPOSITING",
        },
        {
            "shot_id": "S3",
            "start_seconds": 19.0,
            "end_seconds": 30.0,
            "final_budget_treatment": "ANIMATED_STILL_COMPOSITING",
        },
    ]

    repaired, report = canonicalize_timeline_partition(
        items,
        30.0,
    )

    assert repaired[0]["start_seconds"] == 0.0
    assert repaired[-1]["end_seconds"] == 30.0
    assert repaired[0]["end_seconds"] == repaired[1]["start_seconds"]
    assert repaired[1]["end_seconds"] == repaired[2]["start_seconds"]
    assert report["discontinuity_count"] == 2
    assert report["status"] == "PASS"


def test_r6_validator_uses_partition_normalizer_before_queue_validation():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo
        / "src/application/"
        "siraj_alignment_structural_repair_v6_6_r6.py"
    ).read_text(encoding="utf-8-sig")

    assert "SIRAJ_ALIGNMENT_TIMELINE_PARTITION_RECOVERY_V6_6_R6_1" in source
    assert "def canonicalize_timeline_partition(" in source
    assert "items, partition_report = canonicalize_timeline_partition(" in source
    assert '"timeline_partition_normalization"' in source


def test_paid_retry_law_is_unchanged():
    repo = Path(__file__).resolve().parents[1]
    master = (
        repo
        / "src/application/"
        "siraj_episode_master_authorization_v6_6.py"
    ).read_text(encoding="utf-8-sig")

    assert "PAID_RETRY_CONFIRMATION_PHRASE" in master
    assert "automatic_paid_retry" in master
    assert "automatic_paid_resubmission" in master
