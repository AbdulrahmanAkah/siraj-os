
from pathlib import Path
from src.presentation.desktop.v6_dashboard_state_adapter import (
    build_v6_dashboard_snapshot,
)


def test_episode002_canonical_working_title():
    repo = Path(__file__).resolve().parents[1]
    snapshot = build_v6_dashboard_snapshot(repo)
    active = snapshot.active_episode
    assert active is not None
    assert active.episode_id == (
        "episode-002-adam-temptation-fall-repentance"
    )
    assert active.title_ar == "من الوسوسة إلى التوبة"


def test_episode001_completed_private_history():
    repo = Path(__file__).resolve().parents[1]
    snapshot = build_v6_dashboard_snapshot(repo)
    episode1 = next(
        item
        for item in snapshot.episodes
        if item.episode_id == "episode-001-adam"
    )
    assert episode1.stage_label_ar == "مكتملة — خاصة"
    assert episode1.next_action_ar == "فتح الحلقة المكتملة"


def test_active_metrics_and_order_are_v6():
    repo = Path(__file__).resolve().parents[1]
    snapshot = build_v6_dashboard_snapshot(repo)
    active = snapshot.active_episode
    assert active is not None
    assert snapshot.episodes[0].episode_id == snapshot.active_episode_id
    assert snapshot.total_shot_count == active.shot_count
    assert snapshot.generated_clip_count == active.generated_shot_count


def test_main_window_v65_contract():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo / "src/presentation/desktop/main_window.py"
    ).read_text(encoding="utf-8-sig")
    assert "        install_series_standard_v2_dock(self)\n" not in source
    assert 'SIRAJ_PRODUCTION_STUDIO_V6_5' in source
    assert 'Production Studio — V6.5' in source
    assert "اللقطات: تُبنى بعد اكتمال الصوت" in source
    assert "بانتظار مرحلة الوسائط" in source
    assert "مكتملة / للمراجعة" in source
    assert "قيد الإنتاج" in source


def test_v2_dock_compatibility_symbol_is_disabled():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo / "src/presentation/desktop/series_standard_v2_panel.py"
    ).read_text(encoding="utf-8-sig")
    assert "LEGACY_V2_DOCK_DISABLED_BY_V6_5 = True" in source
    assert "Legacy compatibility no-op for V6.5." in source
