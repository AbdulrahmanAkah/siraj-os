from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.master_visual_development_v1 import (
    ALLOWED_EPISODE_STAGES,
    APPROVAL_BINDING_ID,
    APPROVAL_ID,
    NEXT_STAGE,
    SCRIPT_FINGERPRINT,
    STORYBOARD_FINGERPRINT,
    VISUAL_GATE_ID,
    build_all,
    read_json,
    update_episode_definition,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode-001-adam"
CINEMATIC = EPISODE / "cinematic"
EVIDENCE = EPISODE / "evidence"
CONTRACTS = EPISODE / "contracts"


class AdamMasterVisualDevelopmentV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storyboard = read_json(CINEMATIC / "detailed-storyboard-v2-1.json")
        cls.approval = read_json(
            EVIDENCE / "final-storyboard-master-human-approval-v2-1.json"
        )
        cls.approval_binding = read_json(
            CONTRACTS / "final-storyboard-master-approval-binding-v2-1.json"
        )
        cls.visual_gate = read_json(
            CINEMATIC / "non-paid-visual-development-gate-v1.json"
        )
        cls.definition = read_json(CONTRACTS / "episode-definition-v1.json")
        cls.brief = read_json(CINEMATIC / "prestige-production-brief-v2-1.json")
        (
            cls.visual_bible,
            cls.color_script,
            cls.animatic,
            cls.audit,
            cls.binding,
            cls.updated_definition,
            cls.updated_brief,
        ) = build_all(
            storyboard=cls.storyboard,
            approval=cls.approval,
            approval_binding=cls.approval_binding,
            visual_gate=cls.visual_gate,
            episode_definition=cls.definition,
            production_brief=cls.brief,
        )

    def test_source_approval_is_exact(self):
        self.assertEqual(self.approval["approval_id"], APPROVAL_ID)

    def test_source_binding_is_exact(self):
        self.assertEqual(
            self.approval_binding["binding_id"], APPROVAL_BINDING_ID
        )

    def test_source_visual_gate_is_exact(self):
        self.assertEqual(self.visual_gate["gate_id"], VISUAL_GATE_ID)

    def test_script_fingerprint_is_preserved(self):
        self.assertEqual(
            self.binding["script_fingerprint"], SCRIPT_FINGERPRINT
        )

    def test_storyboard_fingerprint_is_preserved(self):
        self.assertEqual(
            self.binding["storyboard_fingerprint"], STORYBOARD_FINGERPRINT
        )

    def test_visual_bible_has_fourteen_sequence_profiles(self):
        self.assertEqual(len(self.visual_bible["sequence_profiles"]), 14)

    def test_visual_bible_has_full_sequence_coverage(self):
        self.assertEqual(self.visual_bible["sequence_coverage"], "14/14")

    def test_visual_bible_has_full_shot_coverage(self):
        self.assertEqual(self.visual_bible["shot_coverage"], "70/70")

    def test_color_script_has_fourteen_cards(self):
        self.assertEqual(len(self.color_script["sequence_cards"]), 14)

    def test_color_script_duration_is_exact(self):
        self.assertEqual(self.color_script["duration_seconds"], 1320)

    def test_animatic_has_seventy_shot_plans(self):
        self.assertEqual(len(self.animatic["shot_plans"]), 70)

    def test_animatic_duration_is_exact(self):
        self.assertEqual(self.animatic["duration_seconds"], 1320)

    def test_animatic_creates_no_media_assets(self):
        self.assertEqual(self.animatic["media_assets_created"], 0)

    def test_animatic_generates_no_images(self):
        self.assertTrue(
            all(
                plan["image_generation"] == "NOT_PERFORMED"
                for plan in self.animatic["shot_plans"]
            )
        )

    def test_animatic_generates_no_video(self):
        self.assertTrue(
            all(
                plan["video_generation"] == "NOT_PERFORMED"
                for plan in self.animatic["shot_plans"]
            )
        )

    def test_audit_passes(self):
        self.assertEqual(
            self.audit["status"],
            "PASS_NON_PAID_VISUAL_DEVELOPMENT_PACKAGE",
        )

    def test_audit_has_zero_construction_decisions(self):
        self.assertEqual(
            self.audit["unresolved_package_construction_decisions"], 0
        )

    def test_human_master_visual_review_is_required(self):
        self.assertTrue(self.audit["human_master_visual_review_required"])

    def test_binding_binds_audit(self):
        self.assertEqual(self.binding["audit_id"], self.audit["audit_id"])

    def test_binding_advances_to_human_visual_review(self):
        self.assertEqual(self.binding["next_stage"], NEXT_STAGE)

    def test_episode_advances_to_human_visual_review(self):
        self.assertIn(
            self.updated_definition["next_stage"],
            ALLOWED_EPISODE_STAGES,
        )

    def test_episode_binds_package(self):
        self.assertEqual(
            self.updated_definition["master_visual_development"]["binding_id"],
            self.binding["binding_id"],
        )

    def test_visual_gate_usage_records_no_execution(self):
        usage = self.updated_definition["visual_development_gate_usage"]
        self.assertEqual(usage["media_assets_created"], 0)
        self.assertEqual(usage["generated_video_planned_seconds"], 0)

    def test_production_brief_binds_package(self):
        self.assertEqual(
            self.updated_brief["visual_development_binding_id"],
            self.binding["binding_id"],
        )

    def test_master_visual_approval_remains_false(self):
        for artifact in (
            self.visual_bible,
            self.color_script,
            self.animatic,
            self.audit,
            self.binding,
        ):
            self.assertFalse(artifact["master_visual_approval"])

    def test_execution_is_uniformly_blocked(self):
        for artifact in (
            self.visual_bible,
            self.color_script,
            self.animatic,
            self.audit,
            self.binding,
            self.updated_brief,
        ):
            self.assertEqual(artifact["live_provider_execution"], "BLOCKED")
            self.assertEqual(artifact["paid_execution"], "BLOCKED")
            self.assertEqual(artifact["direct_execution"], "BLOCKED")
            self.assertEqual(artifact["runware_execution"], "BLOCKED")

    def test_generated_video_allocation_remains_zero(self):
        for artifact in (
            self.visual_bible,
            self.color_script,
            self.animatic,
            self.audit,
            self.binding,
            self.updated_brief,
        ):
            self.assertEqual(artifact["generated_video_planned_seconds"], 0)

    def test_build_is_deterministic(self):
        rebuilt = build_all(
            storyboard=self.storyboard,
            approval=self.approval,
            approval_binding=self.approval_binding,
            visual_gate=self.visual_gate,
            episode_definition=self.definition,
            production_brief=self.brief,
        )
        self.assertEqual(
            rebuilt,
            (
                self.visual_bible,
                self.color_script,
                self.animatic,
                self.audit,
                self.binding,
                self.updated_definition,
                self.updated_brief,
            ),
        )

    def test_episode_update_is_idempotent(self):
        rebuilt = update_episode_definition(
            episode_definition=self.updated_definition,
            visual_bible=self.visual_bible,
            color_script=self.color_script,
            animatic=self.animatic,
            audit=self.audit,
            binding=self.binding,
        )
        self.assertEqual(rebuilt, self.updated_definition)

    def test_build_from_materialized_definition_is_idempotent(self):
        rebuilt = build_all(
            storyboard=self.storyboard,
            approval=self.approval,
            approval_binding=self.approval_binding,
            visual_gate=self.visual_gate,
            episode_definition=self.updated_definition,
            production_brief=self.updated_brief,
        )
        self.assertEqual(
            rebuilt,
            (
                self.visual_bible,
                self.color_script,
                self.animatic,
                self.audit,
                self.binding,
                self.updated_definition,
                self.updated_brief,
            ),
        )

    def test_output_files_and_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                output_root=Path(tmp) / "report",
                visual_bible=self.visual_bible,
                color_script=self.color_script,
                animatic=self.animatic,
                audit=self.audit,
                binding=self.binding,
                episode_definition=self.updated_definition,
                production_brief=self.updated_brief,
            )
            for key, path in outputs.items():
                self.assertTrue(path.is_file(), key)

    def test_json_outputs_use_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                output_root=Path(tmp) / "report",
                visual_bible=self.visual_bible,
                color_script=self.color_script,
                animatic=self.animatic,
                audit=self.audit,
                binding=self.binding,
                episode_definition=self.updated_definition,
                production_brief=self.updated_brief,
            )
            for key in (
                "visual_bible",
                "color_script",
                "animatic",
                "audit",
                "binding",
                "episode_definition",
                "production_brief",
            ):
                self.assertNotIn(b"\r\n", outputs[key].read_bytes())


if __name__ == "__main__":
    unittest.main()
