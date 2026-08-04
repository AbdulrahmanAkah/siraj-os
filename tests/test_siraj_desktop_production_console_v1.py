from __future__ import annotations

from pathlib import Path
import unittest


class DesktopProductionConsoleSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo = Path(__file__).resolve().parents[1]
        cls.main = (
            repo / "src/presentation/desktop/main_window.py"
        ).read_text(encoding="utf-8-sig")
        cls.console = (
            repo / "src/presentation/desktop/production_console.py"
        ).read_text(encoding="utf-8-sig")
        cls.core = (
            repo / "src/application/runware_execution_v1.py"
        ).read_text(encoding="utf-8-sig")

    def test_video_navigation_opens_console(self):
        self.assertIn("ProductionConsoleDialog", self.main)
        self.assertIn('label == "الفيديو"', self.main)
        self.assertIn("_open_production_console", self.main)

    def test_paid_action_requires_explicit_confirmation(self):
        self.assertIn("paidExecutionConfirmation", self.console)
        self.assertIn("QMessageBox.warning", self.console)
        self.assertIn("executeBeat01Button", self.console)

    def test_single_use_and_recovery_controls_exist(self):
        self.assertIn("recoverBeat01Button", self.console)
        self.assertIn("SUBMISSION_LOCKED_BEFORE_NETWORK", self.core)
        self.assertIn("SUBMISSION_ALREADY_LOCKED_USE_RECOVERY", self.core)
        self.assertIn("POLL_EXISTING_TASK_UUID_ONLY_NO_RESUBMISSION", (
            Path(__file__).resolve().parents[1]
            / "projects/episode-001-adam/contracts/"
            "runware-beat-01-execution-authorization-v1.json"
        ).read_text(encoding="utf-8-sig"))

    def test_api_key_is_not_persisted(self):
        self.assertIn('"api_key_persisted": False', self.core)
        self.assertNotIn("write_text(api_key", self.core)
        self.assertNotIn("json.dump(api_key", self.core)

    def test_human_review_is_inside_desktop_console(self):
        self.assertIn("saveBeat01ReviewButton", self.console)
        self.assertIn("score_total", self.core)
        self.assertIn("blocking_failures", self.core)
        self.assertIn("beat_02_execution", self.core)


if __name__ == "__main__":
    unittest.main()
