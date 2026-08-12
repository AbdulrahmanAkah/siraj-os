from pathlib import Path


def test_v62_bridge_persists_certified_rescue_for_production():
    repo = Path(__file__).resolve().parents[1]
    bridge = (
        repo / "src/application/episode002_finalization_compatibility_v6.py"
    ).read_text(encoding="utf-8-sig")
    assert "SIRAJ_EP002_PRODUCTION_HANDOFF_V6_2" in bridge
    assert "_apply_v6_1_certified_duplicate_rescue_for_production" in bridge
    assert "PASS_ZERO_FINDINGS_AFTER_V6_1_CERTIFIED_PRODUCTION_REBIND" in bridge
    ensure_tail = bridge[bridge.index("def ensure_montage_media_queue("):]
    assert (
        "queue = _apply_v6_1_certified_duplicate_rescue_for_production("
        in ensure_tail
    )


def test_v62_desktop_executor_still_uses_canonical_bridge_before_assembler():
    repo = Path(__file__).resolve().parents[1]
    local_executor = (
        repo / "src/application/desktop_local_assembly_montage_v1.py"
    ).read_text(encoding="utf-8-sig")
    assert (
        "ensure_montage_media_queue(self.repo_root, self.episode_id)"
        in local_executor
    )
    assert "self.assembler(self.repo_root, self.episode_id)" in local_executor
    assert local_executor.index(
        "ensure_montage_media_queue(self.repo_root, self.episode_id)"
    ) < local_executor.index(
        "self.assembler(self.repo_root, self.episode_id)"
    )
