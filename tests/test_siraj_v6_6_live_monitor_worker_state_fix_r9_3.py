from pathlib import Path
import ast

p = Path("src/presentation/desktop/v6_dashboard_integration.py")
text = p.read_text(encoding="utf-8-sig")
tree = ast.parse(text)

def _class(name):
    return next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)

def test_monitor_has_worker_state_method():
    cls = _class("LiveProductionMonitorV66")
    names = {
        n.name for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "set_worker_active" in names

def test_resume_button_is_instance_attribute():
    assert 'self.resume_autopilot = QPushButton("استئناف Autopilot من شاشة المراقبة")' in text
    assert "self.resume_autopilot.setEnabled(not active)" in text

def test_duplicate_resume_guard_present():
    assert "if getattr(self, \"_worker_active\", False):" in text

def test_marker_present():
    assert "SIRAJ_R9_3_LIVE_MONITOR_WORKER_STATE_FIX" in text

def test_no_auto_resume_or_retry():
    assert "R9_3_AUTO_RESUME" not in text
    assert "R9_3_AUTO_RETRY" not in text
