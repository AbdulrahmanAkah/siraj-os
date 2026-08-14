from pathlib import Path
import inspect

import pytest

from src.application.artifact_provenance_v1 import sha256_file


REPO = Path(__file__).resolve().parents[1]
EPISODE = "episode-002-adam-temptation-fall-repentance"


def test_app_launcher_selects_full_designed_window() -> None:
    source = (REPO / "src/presentation/desktop/app.py").read_text(encoding="utf-8")
    assert "from .main_window import SirajDesktopWindow" in source
    assert "from src.presentation.desktop.main_window import SirajDesktopWindow" in source
    assert "CanonicalProductionDesktopWindow" not in source
    assert "window = SirajDesktopWindow(repo_root)" in source


def test_full_ui_resume_binding_is_canonical_and_not_legacy_autopilot() -> None:
    from src.presentation.desktop.main_window import SirajDesktopWindow

    source = inspect.getsource(SirajDesktopWindow._open_production_console)
    assert "DesktopProductionResumeController" not in source
    assert "prepare_resume" in source
    assert "CanonicalDesktopResumeWorker" in source
    assert "primary_action()" not in source
    assert "Canonical Desktop resume is not configured for this episode" in source


def test_full_ui_opens_idle_with_authoritative_ep002_state(monkeypatch) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from src.presentation.desktop.main_window import SirajDesktopWindow

    ledger = (
        REPO
        / "projects"
        / EPISODE
        / "orchestration"
        / "episode-transition-ledger-v1.jsonl"
    )
    before = sha256_file(ledger)
    app = QApplication.instance() or QApplication([])
    window = SirajDesktopWindow(REPO)
    try:
        assert window.__class__.__name__ == "SirajDesktopWindow"
        assert window.windowTitle() != "SIRAJ Production Review"
        assert window.complete_workspace is not None
        assert window.v6_command_center is not None
        assert window._canonical_state is not None
        assert window._canonical_state.current_stage == "READY_FOR_FINAL_HUMAN_REVIEW"
        assert window._canonical_state.alignment_gate == "PASS"
        assert window._canonical_state.duplicate_gate == "PASS"
        assert window.snapshot.active_episode is not None
        assert window.snapshot.active_episode.duration_seconds == 623.584
        assert window.snapshot.active_episode.shot_count == 55
        assert window._resume_worker is None
        assert "duration=623.584s" in window.v6_command_center.authority_value.text()
        assert "shots=55" in window.v6_command_center.authority_value.text()
        assert "DISCONTINUITIES=0" in window.v6_command_center.gates_value.text()
        assert window.v6_command_center.request_metric.text().endswith("—")
        assert window.v6_command_center.character_metric.text().endswith("—")
        assert window.v6_command_center.primary.text() == "Resume current stage (Desktop UI)"
        approval_page = window.complete_workspace._pages["approvals"]
        assert "episode-transition-ledger-v1.jsonl" in approval_page.current_directive.text()
        assert "DESKTOP_UI_ONLY" in approval_page.current_directive.text()
        assert sha256_file(ledger) == before
    finally:
        window.close()
        app.processEvents()


def test_full_command_center_guards_direct_legacy_primary_action() -> None:
    source = (
        REPO / "src/presentation/desktop/v6_dashboard_integration.py"
    ).read_text(encoding="utf-8")
    assert "primary_action_callback" in source
    assert "programmatic calls to" in source
    assert "run_until_gate" in source  # retained historical implementation only
