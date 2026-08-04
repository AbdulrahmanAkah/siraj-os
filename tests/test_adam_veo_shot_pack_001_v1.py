from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.application.storyboard_runtime.veo_shot_package_v1 import (
    BEAT_01_ID,
    BEAT_02_ID,
    BINDING_ID,
    PACKAGE_ID,
    SHOT_ID,
    validate_repository,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EPISODE = REPO_ROOT / "projects" / "episode-001-adam"
PACKAGE_PATH = (
    EPISODE
    / "cinematic"
    / "shot-packages"
    / "adam-dc2-s02-sh03"
    / "veo-shot-pack-001-v1.json"
)
BINDING_PATH = EPISODE / "contracts" / "veo-shot-pack-001-binding-v1.json"


class AdamVeoShotPack001V1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8-sig"))
        cls.binding = json.loads(BINDING_PATH.read_text(encoding="utf-8-sig"))

    def test_validator_passes(self) -> None:
        result = validate_repository(REPO_ROOT)
        self.assertEqual(result["status"], "PASS_ADAM_VEO_SHOT_PACK_001_V1")

    def test_package_and_binding_ids(self) -> None:
        self.assertEqual(self.package["shot_package_id"], PACKAGE_ID)
        self.assertEqual(self.binding["binding_id"], BINDING_ID)

    def test_target_is_exact_storyboard_shot(self) -> None:
        self.assertEqual(self.package["shot_id"], SHOT_ID)
        self.assertEqual(self.package["storyboard_source"]["editorial_duration_seconds"], 16)
        self.assertEqual(
            self.package["storyboard_source"]["screen_action_ar"],
            "تتشكل دوامة صغيرة ثم تستقر.",
        )

    def test_only_beat_01_is_authored(self) -> None:
        beats = self.package["generation_beats"]
        self.assertEqual(beats[0]["beat_id"], BEAT_01_ID)
        self.assertEqual(beats[0]["execution_status"], "NOT_AUTHORISED")
        self.assertEqual(beats[1]["beat_id"], BEAT_02_ID)
        self.assertEqual(beats[1]["status"], "DEFERRED")
        self.assertEqual(beats[1]["prompt"], "NOT_YET_AUTHORED")

    def test_text_to_video_dimensions_and_no_resolution(self) -> None:
        settings = self.package["generation_beats"][0]["settings"]
        self.assertEqual((settings["width"], settings["height"]), (1280, 720))
        self.assertEqual(
            settings["resolution_parameter"],
            "OMIT_FOR_TEXT_TO_VIDEO_WITH_WIDTH_HEIGHT",
        )
        self.assertEqual(settings["duration"], 8)

    def test_people_and_audio_are_disabled(self) -> None:
        google = self.package["generation_beats"][0]["settings"]["provider_settings"]["google"]
        self.assertFalse(google["generateAudio"])
        self.assertEqual(google["personGeneration"], "dont_allow")

    def test_negative_prompt_field_is_not_claimed(self) -> None:
        negative = self.package["generation_beats"][0]["negative_prompt"]
        self.assertEqual(
            negative["field_usage"],
            "NOT_USED_MODEL_SCHEMA_DOES_NOT_LIST_NEGATIVE_PROMPT",
        )

    def test_paid_execution_remains_blocked(self) -> None:
        execution = self.package["execution_authorization"]
        self.assertEqual(execution["automatic_provider_execution"], "BLOCKED")
        self.assertEqual(
            execution["manual_user_execution"],
            "BLOCKED_UNTIL_HUMAN_SHOT_PACKAGE_APPROVAL",
        )
        self.assertFalse(self.binding["human_shot_package_approval"])

    def test_acceptance_gate_is_strict(self) -> None:
        scoring = self.package["acceptance_gate"]["scoring"]
        self.assertEqual(scoring["pass_threshold"], 80)
        self.assertTrue(scoring["blocking_failure_overrides_score"])


if __name__ == "__main__":
    unittest.main()
