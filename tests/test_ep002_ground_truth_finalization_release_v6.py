from pathlib import Path


def test_ground_truth_finalization_v6_source_contract():
    repo = Path(__file__).resolve().parents[1]
    bridge = (
        repo
        / "src/application/episode002_finalization_compatibility_v6.py"
    ).read_text(encoding="utf-8-sig")
    renderer = (
        repo
        / "src/application/episode002_local_graphics_ground_truth_v5.py"
    ).read_text(encoding="utf-8-sig")
    local_executor = (
        repo
        / "src/application/desktop_local_assembly_montage_v1.py"
    ).read_text(encoding="utf-8-sig")
    readiness = (
        repo
        / "src/application/desktop_resume_readiness_v1.py"
    ).read_text(encoding="utf-8-sig")
    main = (
        repo
        / "src/presentation/desktop/main_window.py"
    ).read_text(encoding="utf-8-sig")
    v6 = (
        repo
        / "src/presentation/desktop/v6_dashboard_integration.py"
    ).read_text(encoding="utf-8-sig")

    assert "SIRAJ_EP002_GROUND_TRUTH_FINALIZATION_COMPATIBILITY_V6" in bridge
    assert "GROUND_TRUTH_COMPATIBILITY_PROVENANCE" in bridge
    assert "_repair_duplicate_assets_locally" in bridge
    assert "gate_bypass_used" in bridge
    assert '"reuse_justification_added": False' in bridge
    assert "materialize_v6_media_queue" not in bridge
    assert "siraj_media_queue_v6_2_1" not in bridge
    assert "SIRAJ_EP002_GROUND_TRUTH_LOCAL_GRAPHICS_V5" in renderer
    assert "ensure_montage_media_queue" in local_executor
    assert "episode002_finalization_compatibility_v6" in local_executor
    assert "SIRAJ_EP002_CANONICAL_DESKTOP_SEMANTIC_QA_V3" in readiness
    assert "CANONICAL_SEMANTIC_EDITORIAL_AND_TECHNICAL_QA_REQUESTED" in main
    assert "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA" in v6


def test_v6_duplicate_rescue_is_local_and_fail_closed():
    repo = Path(__file__).resolve().parents[1]
    bridge = (
        repo
        / "src/application/episode002_finalization_compatibility_v6.py"
    ).read_text(encoding="utf-8-sig")
    assert "provider_regeneration_used" in bridge
    assert '"provider_calls": 0' in bridge
    assert '"paid_calls": 0' in bridge
    assert "LOCAL_EDITORIAL_RESCUE_NO_GATE_CLEARING_VARIANT" in bridge
    assert "DUPLICATE_GATE_RUNTIME_AUDIT_FAILED_AFTER_LOCAL_RESCUE" in bridge
    assert "audit_completed_assets(repo, items)" in bridge
