from pathlib import Path

p = Path("src/presentation/desktop/v6_dashboard_integration.py")
text = p.read_text(encoding="utf-8-sig")

def test_r921_markers():
    assert "SIRAJ_R9_2_1_QTHREAD_START_PROBE" in text
    assert "WORKER_RUN_RAW_ENTERED" in text
    assert "WORKER_BEFORE_RUN_UNTIL_GATE" in text
    assert "WORKER_START_RETURNED" in text
    assert 'QTimer.singleShot(250, lambda: _r92_probe_worker_state("250MS"))' in text
    assert 'QTimer.singleShot(2000, lambda: _r92_probe_worker_state("2000MS"))' in text
    assert 'f"WORKER_STATE_PROBE_{label}"' in text

def test_no_auto_retry_or_resume():
    assert "R9_2_1_AUTO_RESUME" not in text
    assert "R9_2_1_AUTO_RETRY" not in text
