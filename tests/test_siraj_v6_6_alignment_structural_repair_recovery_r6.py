from pathlib import Path

from src.application.siraj_alignment_structural_repair_v6_6_r6 import (
    next_iteration_number,
)


def test_r6_allows_structural_alignment_repair_under_hard_validation():
    repo = Path(__file__).resolve().parents[1]
    r3 = (
        repo
        / "src/application/"
        "siraj_alignment_semantic_autorepair_v6_6_r3.py"
    ).read_text(encoding="utf-8-sig")

    assert "SIRAJ_ALIGNMENT_STRUCTURAL_REPAIR_V6_6_R6" in r3
    assert "validate_structural_repair_candidate" in r3
    assert (
        "ALIGNMENT_REPAIR_SHOT_ID_OR_ORDER_CHANGE_FORBIDDEN"
        not in r3
    )
    assert (
        '"structural_change_allowed_when_alignment_requires": True'
        in r3
    )


def test_iteration_allocator_skips_existing_failed_iteration(tmp_path):
    root = tmp_path / "r3"
    (root / "iteration-001").mkdir(parents=True)
    (root / "iteration-002").mkdir()
    rows = [{"iteration": 1}]
    assert next_iteration_number(root, rows) == 3


def test_r6_reuses_existing_paid_response_and_preserves_retry_law():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo
        / "src/application/"
        "siraj_alignment_structural_repair_v6_6_r6.py"
    ).read_text(encoding="utf-8-sig")
    master = (
        repo
        / "src/application/"
        "siraj_episode_master_authorization_v6_6.py"
    ).read_text(encoding="utf-8-sig")

    assert "reused_existing_paid_response" in source
    assert "new_paid_provider_request" in source
    assert "MAX_GENERATED_VIDEO_RATIO" in source
    assert "_validate_full_timeline" in source
    assert "PAID_RETRY_CONFIRMATION_PHRASE" in master
    assert "automatic_paid_retry" in master
