
from pathlib import Path

P = Path("src/presentation/desktop/v6_dashboard_integration.py")
TEXT = P.read_text(encoding="utf-8-sig")
LINES = TEXT.splitlines()

def test_future_import_precedes_r911_import():
    future_idx = [i for i, line in enumerate(LINES) if line.startswith("from __future__ import ")]
    emit_idx = [i for i, line in enumerate(LINES) if line.strip() == "from src.application.siraj_live_telemetry_v6_6_r9 import emit_event"]
    assert future_idx
    assert len(emit_idx) == 1
    assert emit_idx[0] > max(future_idx)

def test_r911_marker_present_once():
    assert TEXT.count("SIRAJ_R9_1_1_ADAPTIVE_RESUME_WORKER_TELEMETRY") == 1

def test_resume_telemetry_contract():
    assert "RESUME_ACTION_RECEIVED" in TEXT
    assert "WORKER_LAUNCH_REQUESTED" in TEXT
    assert "WORKER_THREAD_ENTERED" in TEXT
    assert "استئناف Autopilot من شاشة المراقبة" in TEXT

def test_no_installer_auto_resume():
    assert "R9_1_2_AUTO_RESUME" not in TEXT
