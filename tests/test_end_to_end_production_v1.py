from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.application.end_to_end_production_v1 import (
    inspect_end_to_end_plan,
    run_end_to_end_planner_smoke_test,
)


class EndToEndProductionV1Tests(unittest.TestCase):
    def test_planner_smoke_exposes_one_consolidated_paid_gate(self) -> None:
        with TemporaryDirectory() as directory:
            result = run_end_to_end_planner_smoke_test(Path(directory))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["action"], "OPEN_MEDIA_EXECUTION")
        self.assertEqual(result["pending_media_count"], 3)
        self.assertEqual(result["pending_runware_count"], 1)
        self.assertEqual(result["pending_elevenlabs_count"], 1)
        self.assertEqual(result["pending_local_graphics_count"], 1)
        self.assertAlmostEqual(result["pending_media_maximum_usd"], 3.15)
        self.assertTrue(result["requires_paid_confirmation"])

    def test_ready_state_requires_completed_youtube_handoff(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                '{"status":"READY_TO_PUBLISH","stage":"READY_TO_PUBLISH",'
                '"current_episode_id":"episode-001-test",'
                '"youtube_handoff_status":"READY_FOR_MANUAL_YOUTUBE_UPLOAD"}',
                encoding="utf-8",
            )
            plan = inspect_end_to_end_plan(root)
        self.assertTrue(plan.ready_for_manual_youtube_upload)
        self.assertFalse(plan.requires_paid_confirmation)


if __name__ == "__main__":
    unittest.main()
