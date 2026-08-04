from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from src.application.storyboard_runtime.veo_production_manifest_v1 import (
    BINDING_ID,
    MANIFEST_ID,
    MANIFEST_BINDING_ID,
    MODEL,
    POLICY_ID,
    validate_repository,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects" / "episode-001-adam"


class AdamVeoProductionManifestV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(
            (EPISODE / "cinematic" / "veo-production-manifest-v1.json").read_text(
                encoding="utf-8-sig"
            )
        )
        cls.manifest_binding = json.loads(
            (EPISODE / "contracts" / "veo-production-manifest-binding-v1.json").read_text(
                encoding="utf-8-sig"
            )
        )
        cls.result = validate_repository(ROOT)

    def test_validator_passes(self):
        self.assertEqual(
            self.result["status"],
            "PASS_ADAM_VEO_PRODUCTION_MANIFEST_V1",
        )

    def test_manifest_binding_chain(self):
        self.assertEqual(self.manifest["manifest_id"], MANIFEST_ID)
        self.assertEqual(self.manifest["visual_safety_policy_id"], POLICY_ID)
        self.assertEqual(
            self.manifest["visual_safety_policy_binding_id"],
            BINDING_ID,
        )
        self.assertEqual(self.manifest_binding["binding_id"], MANIFEST_BINDING_ID)
        self.assertEqual(
            self.manifest_binding["manifest_id"],
            self.manifest["manifest_id"],
        )

    def test_primary_model_is_veo_31_lite(self):
        model = self.manifest["primary_video_model"]
        self.assertEqual(model["model"], MODEL)
        self.assertEqual(model["provider"], "RUNWARE")
        self.assertFalse(model["generate_audio"])
        self.assertEqual(model["number_results_per_attempt"], 1)

    def test_seventy_shots_and_duration(self):
        shots = self.manifest["shots"]
        self.assertEqual(len(shots), 70)
        self.assertEqual(len({shot["shot_id"] for shot in shots}), 70)
        self.assertEqual(
            sum(shot["editorial_duration_seconds"] for shot in shots),
            1320,
        )

    def test_primary_mode_counts(self):
        counts = Counter(
            shot["primary_production_mode"] for shot in self.manifest["shots"]
        )
        self.assertEqual(
            dict(counts),
            {
                "IMAGE_TO_VIDEO": 29,
                "COMPOSITING": 25,
                "GRAPHICS": 6,
                "TEXT_TO_VIDEO": 10,
            },
        )

    def test_direct_generation_units_use_only_supported_durations(self):
        for shot in self.manifest["shots"]:
            for duration in shot["recommended_veo_generation_units_seconds"]:
                self.assertIn(duration, {4, 6, 8})

    def test_graphics_never_invokes_veo(self):
        for shot in self.manifest["shots"]:
            if shot["primary_production_mode"] == "GRAPHICS":
                self.assertEqual(
                    shot["recommended_veo_generation_units_seconds"],
                    [],
                )

    def test_image_to_video_requires_source(self):
        for shot in self.manifest["shots"]:
            if shot["primary_production_mode"] == "IMAGE_TO_VIDEO":
                self.assertEqual(shot["source_image_requirement"], "REQUIRED")

    def test_text_to_video_does_not_require_source(self):
        for shot in self.manifest["shots"]:
            if shot["primary_production_mode"] == "TEXT_TO_VIDEO":
                self.assertEqual(
                    shot["source_image_requirement"],
                    "NOT_REQUIRED",
                )

    def test_every_shot_binds_face_and_modesty_policy(self):
        for shot in self.manifest["shots"]:
            self.assertEqual(
                shot["face_policy"],
                "NO_COMPLETE_IDENTIFIABLE_FACE_FOR_ANY_CHARACTER",
            )
            self.assertIn(
                "NO_TABARRUJ",
                shot["women_modesty_policy"],
            )

    def test_paid_bulk_execution_remains_blocked(self):
        execution = self.manifest["execution_policy"]
        self.assertEqual(execution["automatic_paid_execution"], "BLOCKED")
        self.assertEqual(
            execution["full_episode_bulk_generation"],
            "BLOCKED_UNTIL_BATCH_GATE",
        )

    def test_first_batch_contains_all_ten_text_to_video_shots(self):
        batch = set(self.manifest["first_authoring_batch"]["shot_ids"])
        t2v = {
            shot["shot_id"]
            for shot in self.manifest["shots"]
            if shot["primary_production_mode"] == "TEXT_TO_VIDEO"
        }
        self.assertEqual(batch, t2v)


if __name__ == "__main__":
    unittest.main()
