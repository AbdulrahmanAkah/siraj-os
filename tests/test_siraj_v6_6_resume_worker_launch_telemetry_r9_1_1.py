
from pathlib import Path

P = Path("src/presentation/desktop/v6_dashboard_integration.py")
TEXT = P.read_text(encoding="utf-8-sig")

def test_marker_present():
    assert "SIRAJ_R9_1_1_ADAPTIVE_RESUME_WORKER_TELEMETRY" in TEXT

def test_launch_telemetry_present():
    assert "RESUME_ACTION_RECEIVED" in TEXT
    assert "WORKER_LAUNCH_REQUESTED" in TEXT
    assert "WORKER_THREAD_ENTERED" in TEXT

def test_monitor_resume_control_present():
    assert "استئناف Autopilot من شاشة المراقبة" in TEXT

def test_emit_event_import_present():
    assert "siraj_live_telemetry_v6_6_r9 import emit_event" in TEXT

def test_no_auto_resume_marker():
    assert "R9_1_1_AUTO_RESUME" not in TEXT

def test_worker_entry_is_real_thread_event():
    assert "دخل خيط Autopilot إلى run() فعليًا" in TEXT
