from __future__ import annotations

from pathlib import Path
import unittest


class AutonomousEpisodeOrchestratorDesktopV1SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo = Path(__file__).resolve().parents[1]
        cls.console = (
            repo / "src/presentation/desktop/production_console.py"
        ).read_text(encoding="utf-8-sig")
        cls.credentials = (
            repo / "src/application/provider_credentials_v1.py"
        ).read_text(encoding="utf-8-sig")
        cls.orchestrator = (
            repo / "src/application/autonomous_episode_orchestrator_v1.py"
        ).read_text(encoding="utf-8-sig")

    def test_autonomous_tab_and_controls_exist(self):
        for marker in (
            "autonomousOrchestratorTab",
            "produceNextEpisodeButton",
            "scopeProposalView",
            "scopeEventsTable",
            "scopeDiscussionInput",
            "sendScopeDiscussionButton",
            "approveEpisodeScopeButton",
        ):
            self.assertIn(marker, self.console)

    def test_keys_use_windows_credential_manager(self):
        self.assertIn("SIRAJ/OPENAI_API_KEY", self.credentials)
        self.assertIn("SIRAJ/ELEVENLABS_API_KEY", self.credentials)
        self.assertIn("CredWriteW", self.credentials)
        self.assertNotIn("dotenv", self.credentials)
        self.assertNotIn("write_text", self.credentials)

    def test_partial_rebuild_and_human_gates_are_explicit(self):
        self.assertIn("partial_rebuild_only", self.orchestrator)
        self.assertIn("HUMAN_SCOPE_REVIEW", self.orchestrator)
        self.assertIn("HUMAN_FINAL_REVIEW", self.orchestrator)
        self.assertIn("manual_youtube_upload", self.orchestrator)


if __name__ == "__main__":
    unittest.main()
