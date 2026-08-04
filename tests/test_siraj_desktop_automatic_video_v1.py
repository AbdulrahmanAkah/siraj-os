from __future__ import annotations

from pathlib import Path
import unittest


class DesktopAutomaticVideoV1SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo = Path(__file__).resolve().parents[1]
        cls.console = (
            repo / "src/presentation/desktop/production_console.py"
        ).read_text(encoding="utf-8-sig")
        cls.workflow = (
            repo / "src/application/automatic_video_workflow_v1.py"
        ).read_text(encoding="utf-8-sig")
        cls.credentials = (
            repo / "src/application/windows_credentials_v1.py"
        ).read_text(encoding="utf-8-sig")
        cls.authorization = (
            repo / "projects/episode-001-adam/contracts/"
            "automatic-video-user-authorization-v1.json"
        ).read_text(encoding="utf-8-sig")

    def test_one_click_generation_control_exists(self):
        self.assertIn("generateVideoButton", self.console)
        self.assertIn("إنشاء الفيديو", self.console)
        self.assertIn("generate_or_resume", self.console)

    def test_exact_two_output_actions_exist(self):
        self.assertIn("viewVideoButton", self.console)
        self.assertIn("showVideoLocationButton", self.console)
        self.assertIn("عرض الفيديو", self.console)
        self.assertIn("عرض مكانه في الجهاز", self.console)

    def test_review_is_single_score_only(self):
        self.assertIn("finalScoreSpinBox", self.console)
        self.assertIn("saveFinalScoreButton", self.console)
        self.assertIn("ONE_INTEGER_ONLY_0_TO_100", self.workflow)
        self.assertNotIn("material_transformation_notes", self.console)
        self.assertNotIn("blocking_failures = QPlainTextEdit", self.console)

    def test_paid_retry_requires_another_explicit_click(self):
        self.assertIn(
            "background_paid_retry_without_click",
            self.authorization,
        )
        self.assertIn('"BLOCKED"', self.authorization)
        self.assertIn("READY_TO_GENERATE", self.workflow)

    def test_api_key_uses_windows_credential_manager(self):
        self.assertIn("CredWriteW", self.credentials)
        self.assertIn("CredReadW", self.credentials)
        self.assertIn("Windows Credential Manager", self.console)
        self.assertNotIn("write_text(api_key", self.credentials)
        self.assertNotIn("json.dump(api_key", self.credentials)

    def test_output_location_selects_generated_file(self):
        self.assertIn("explorer.exe", self.console)
        self.assertIn('["/select,", native]', self.console)


if __name__ == "__main__":
    unittest.main()
