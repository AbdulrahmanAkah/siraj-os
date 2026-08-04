from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from src.application.episode_production_control_v1 import (
    ANIMATED_STILL_SHOT_COUNT,
    EDITORIAL_SHOT_COUNT,
    GRAPHICS_SHOT_COUNT,
    HARD_CAP_USD,
    VIDEO_PLANNED_SECONDS,
    VIDEO_SHOT_COUNT,
    EpisodeProductionPolicyError,
    assert_budget_allows_new_paid_request,
    load_episode_plan,
    load_episode_policy,
    scan_actual_paid_spend,
)


class EpisodeProductionControlV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[1]

    def _temp_repo(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        for relative in (
            "projects/episode-001-adam/contracts/"
            "episode-production-policy-v1.json",
            "projects/episode-001-adam/cinematic/"
            "episode-production-plan-v1.json",
        ):
            source = self.repo / relative
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        return temporary, root

    def test_policy_is_strict_40_dollars_and_no_music(self):
        policy = load_episode_policy(self.repo)
        self.assertEqual(HARD_CAP_USD, 40.0)
        self.assertEqual(policy["budget"]["episode_hard_cap_usd"], 40.0)
        self.assertEqual(policy["budget"]["headroom_usd"], 0.0)
        self.assertEqual(policy["budget"]["cap_override"], "FORBIDDEN")
        self.assertEqual(policy["audio"]["music"], "FORBIDDEN")
        self.assertEqual(policy["audio"]["musical_score"], "FORBIDDEN")
        self.assertEqual(policy["audio"]["songs"], "FORBIDDEN")
        self.assertEqual(policy["audio"]["sound_effects"], "ALLOWED")
        self.assertEqual(
            policy["audio"]["sound_effect_type_restriction"],
            "NONE_WHEN_SCENE_APPROPRIATE",
        )

    def test_plan_has_required_hybrid_mix(self):
        plan = load_episode_plan(self.repo)
        self.assertEqual(len(plan["shots"]), EDITORIAL_SHOT_COUNT)
        self.assertEqual(
            plan["treatment_counts"]["GENERATED_VIDEO"],
            VIDEO_SHOT_COUNT,
        )
        self.assertEqual(
            plan["treatment_counts"]["ANIMATED_STILL_COMPOSITING"],
            ANIMATED_STILL_SHOT_COUNT,
        )
        self.assertEqual(
            plan["treatment_counts"]["GRAPHICS"],
            GRAPHICS_SHOT_COUNT,
        )
        self.assertEqual(
            plan["generated_video_target_seconds"]["planned"],
            VIDEO_PLANNED_SECONDS,
        )
        self.assertEqual(VIDEO_PLANNED_SECONDS, 160)

    def test_receipts_are_deduplicated_by_task_uuid(self):
        temporary, root = self._temp_repo()
        try:
            receipt_a = (
                root
                / "projects/episode-001-adam/runtime/a/receipt-a.json"
            )
            receipt_b = (
                root
                / "projects/episode-001-adam/runtime/b/receipt-b.json"
            )
            receipt_a.parent.mkdir(parents=True, exist_ok=True)
            receipt_b.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "task_uuid": "same-task",
                "actual_cost_usd": 0.40,
            }
            receipt_a.write_text(json.dumps(payload), encoding="utf-8")
            receipt_b.write_text(json.dumps(payload), encoding="utf-8")
            snapshot = scan_actual_paid_spend(root)
            self.assertEqual(snapshot.actual_spent_usd, 0.40)
            self.assertEqual(snapshot.unique_paid_tasks, 1)
        finally:
            temporary.cleanup()

    def test_budget_gate_blocks_projected_breach(self):
        temporary, root = self._temp_repo()
        try:
            receipt = (
                root
                / "projects/episode-001-adam/runtime/receipt.json"
            )
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(
                json.dumps(
                    {
                        "task_uuid": "spent-task",
                        "actual_cost_usd": 39.80,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(EpisodeProductionPolicyError):
                assert_budget_allows_new_paid_request(root, 0.40)
            allowed = assert_budget_allows_new_paid_request(root, 0.20)
            self.assertEqual(allowed.actual_spent_usd, 39.80)
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
