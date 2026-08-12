from pathlib import Path

from src.presentation.desktop.v6_dashboard_state_adapter import (
    build_v6_dashboard_snapshot,
)


def test_polish_keeps_original_dashboard_and_active_episode():
    repo = Path(__file__).resolve().parents[1]
    snapshot = build_v6_dashboard_snapshot(repo)
    active = snapshot.active_episode
    assert active is not None
    assert active.episode_id == (
        "episode-002-adam-temptation-fall-repentance"
    )
    assert active.title_ar == "من الوسوسة إلى التوبة"


def test_main_window_v651_polish_contract():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo / "src/presentation/desktop/main_window.py"
    ).read_text(encoding="utf-8-sig")

    assert (
        'UI_POLISH_RELEASE = '
        '"SIRAJ_ORIGINAL_DASHBOARD_UI_POLISH_V6_5_1"'
    ) in source
    assert "self.project_combo.setItemText(" in source
    assert "Qt.ItemDataRole.ToolTipRole" in source
    assert '"بانتظار الصوت"' in source
    assert 'return "تفويض الصوت"' in source
    assert 'return "مكتملة — خاصة"' in source
    assert (
        '"المعاينة ستُفتح تلقائيًا بعد الوصول إلى توليد الوسائط"'
        in source
    )


def test_v651_retains_historical_v13_contract_without_runtime_reversion():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo / "src/presentation/desktop/main_window.py"
    ).read_text(encoding="utf-8-sig")

    assert 'setWindowTitle("سراج — إدارة إنتاج الحلقات — v1.3")' in source
    assert 'self.setWindowTitle("سراج — Production Studio — V6.5")' in source


def test_command_center_has_tts_metrics_phase_strip_and_v66_one_auth():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo / "src/presentation/desktop/v6_dashboard_integration.py"
    ).read_text(encoding="utf-8-sig")

    assert 'self.request_metric = self._metric_chip("الطلبات", "—")' in source
    assert 'self.character_metric = self._metric_chip("الأحرف", "—")' in source
    assert 'self.percent_metric = self._metric_chip("التقدم", "0%")' in source
    assert "self.phase_labels" in source

    # V6.6 intentionally replaces the old per-stage FINAL_TTS authorization
    # prompt with one episode-wide authorization.
    assert '"تفويض الإنتاج الكامل للحلقة"' in source
    assert "FULL_EPISODE_CONFIRMATION_PHRASE" in source
    assert "LiveProductionMonitorV66" in source
    assert "EventReviewDialogV66" in source
    assert '"شاشة الإنتاج المباشر"' in source

    # Paid retry is still a separate explicit exception.
    assert "PAID_RETRY_CONFIRMATION_PHRASE" in source
    assert '"تفويض إعادة المحاولة المدفوعة"' in source
