from __future__ import annotations

from pathlib import Path
import unittest


class EpisodeProductionDesktopV1SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo = Path(__file__).resolve().parents[1]
        cls.console = (
            repo / "src/presentation/desktop/production_console.py"
        ).read_text(encoding="utf-8-sig")
        cls.workflow = (
            repo / "src/application/automatic_video_workflow_v1.py"
        ).read_text(encoding="utf-8-sig")
        cls.control = (
            repo / "src/application/episode_production_control_v1.py"
        ).read_text(encoding="utf-8-sig")

    def test_plan_and_clip_tabs_exist(self):
        self.assertIn("episodeProductionTabs", self.console)
        self.assertIn("episodePlanTab", self.console)
        self.assertIn("clipProductionTab", self.console)
        self.assertIn("episodeProductionQueueTable", self.console)

    def test_policy_summary_is_visible(self):
        self.assertIn("40$", self.console)
        self.assertIn("120–180", self.console)
        self.assertIn("الموسيقى ممنوعة", self.console)
        self.assertIn("المؤثرات الصوتية", self.console)

    def test_paid_submission_calls_budget_gate(self):
        self.assertIn(
            "assert_budget_allows_new_paid_request",
            self.workflow,
        )
        self.assertIn("EPISODE_BUDGET_HARD_CAP_BLOCKED", self.control)

    def test_existing_one_score_review_and_output_actions_remain(self):
        self.assertIn("viewVideoButton", self.console)
        self.assertIn("showVideoLocationButton", self.console)
        self.assertIn("finalScoreSpinBox", self.console)
        self.assertIn("saveFinalScoreButton", self.console)


if __name__ == "__main__":
    unittest.main()
