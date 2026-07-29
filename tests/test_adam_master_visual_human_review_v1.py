from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.master_visual_human_review_v1 import (
    ANCHOR_SHOT_IDS,
    APPROVED_NEXT_STAGE,
    DEVELOPMENT_BINDING_ID,
    DECISION_OPTIONS,
    EXACT_APPROVAL_PHRASE,
    EXACT_APPROVAL_PHRASE_SHA256,
    NEXT_STAGE,
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


class AdamMasterVisualHumanReviewV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storyboard = read_json(CINEMATIC / "detailed-storyboard-v2-1.json")
        cls.visual_bible = read_json(CINEMATIC / "master-visual-bible-v1.json")
        cls.color_script = read_json(CINEMATIC / "color-script-v1.json")
        cls.animatic = read_json(CINEMATIC / "non-paid-animatic-development-v1.json")
        cls.development_audit = read_json(
            CINEMATIC / "master-visual-development-audit-v1.json"
        )
        cls.development_binding = read_json(
            CONTRACTS / "master-visual-development-binding-v1.json"
        )
        cls.definition = read_json(CONTRACTS / "episode-definition-v1.json")
        cls.brief = read_json(CINEMATIC / "prestige-production-brief-v2-1.json")
        (
            cls.dossier,
            cls.critical_review,
            cls.prototype_plan,
            cls.approval_request,
            cls.review_binding,
            cls.updated_definition,
            cls.updated_brief,
            cls.markdown,
        ) = build_all(
            storyboard=cls.storyboard,
            visual_bible=cls.visual_bible,
            color_script=cls.color_script,
            animatic=cls.animatic,
            development_audit=cls.development_audit,
            development_binding=cls.development_binding,
            episode_definition=cls.definition,
            production_brief=cls.brief,
        )

    def test_source_development_binding_is_exact(self):
        self.assertEqual(
            self.development_binding["binding_id"], DEVELOPMENT_BINDING_ID
        )

    def test_dossier_is_ready_for_human_decision(self):
        self.assertEqual(
            self.dossier["status"],
            "READY_FOR_HUMAN_DECISION_ON_DEVELOPMENT_BASELINE",
        )

    def test_dossier_has_fourteen_sequence_cards(self):
        self.assertEqual(len(self.dossier["sequence_review_cards"]), 14)

    def test_dossier_has_seventy_shot_entries(self):
        self.assertEqual(len(self.dossier["shot_review_index"]), 70)

    def test_dossier_duration_is_exact(self):
        self.assertEqual(self.dossier["duration_seconds"], 1320)

    def test_development_baseline_is_eligible(self):
        self.assertTrue(
            self.dossier["executive_verdict"][
                "development_baseline_approval_eligible"
            ]
        )

    def test_final_master_visual_is_not_eligible(self):
        self.assertFalse(
            self.dossier["executive_verdict"][
                "final_master_visual_approval_eligible"
            ]
        )

    def test_critical_review_passes_with_final_blockers(self):
        self.assertEqual(
            self.critical_review["status"],
            "PASS_REVIEW_READY_WITH_FINAL_APPROVAL_BLOCKERS",
        )

    def test_development_baseline_has_zero_blockers(self):
        self.assertEqual(
            self.critical_review["development_baseline_blocker_count"], 0
        )

    def test_final_visual_has_three_blockers(self):
        self.assertEqual(
            self.critical_review["final_master_visual_approval_blocker_count"],
            3,
        )

    def test_religious_rules_have_no_failure(self):
        self.assertEqual(
            self.critical_review["religious_rule_failure_count"], 0
        )

    def test_prototype_plan_has_eight_anchor_frames(self):
        self.assertEqual(self.prototype_plan["prototype_count"], 8)

    def test_anchor_shot_selection_is_exact(self):
        self.assertEqual(
            self.prototype_plan["anchor_shot_ids"], list(ANCHOR_SHOT_IDS)
        )

    def test_prototype_images_are_not_authorised_automatically(self):
        self.assertEqual(
            self.prototype_plan["image_generation_authorisation"],
            "PENDING_HUMAN_APPROVAL",
        )

    def test_prototype_video_is_blocked(self):
        self.assertEqual(self.prototype_plan["video_generation"], "BLOCKED")

    def test_exact_approval_phrase(self):
        self.assertEqual(
            self.approval_request["exact_approval_phrase"],
            EXACT_APPROVAL_PHRASE,
        )

    def test_exact_approval_phrase_hash(self):
        self.assertEqual(
            self.approval_request["exact_approval_phrase_sha256"],
            EXACT_APPROVAL_PHRASE_SHA256,
        )

    def test_human_approval_remains_false(self):
        self.assertFalse(self.approval_request["human_approval"])

    def test_decision_options_are_exact(self):
        self.assertEqual(
            self.approval_request["decision_options"], list(DECISION_OPTIONS)
        )

    def test_approval_effect_is_non_paid_style_frames(self):
        self.assertEqual(
            self.approval_request["approval_effect_next_stage"],
            APPROVED_NEXT_STAGE,
        )

    def test_request_does_not_approve_final_identity(self):
        self.assertEqual(
            self.approval_request["approval_scope"][
                "final_master_visual_identity"
            ],
            "NOT_APPROVED",
        )

    def test_review_binding_binds_request(self):
        self.assertEqual(
            self.review_binding["approval_request_id"],
            self.approval_request["request_id"],
        )

    def test_review_binding_advances_to_human_decision(self):
        self.assertEqual(self.review_binding["next_stage"], NEXT_STAGE)

    def test_episode_advances_to_human_decision(self):
        self.assertEqual(self.updated_definition["next_stage"], NEXT_STAGE)

    def test_episode_binds_review_package(self):
        self.assertEqual(
            self.updated_definition["master_visual_human_review"][
                "review_binding_id"
            ],
            self.review_binding["review_binding_id"],
        )

    def test_episode_final_master_visual_remains_false(self):
        self.assertFalse(self.updated_definition["master_visual_approval"])

    def test_production_brief_binds_review(self):
        self.assertEqual(
            self.updated_brief["master_visual_human_review_binding_id"],
            self.review_binding["review_binding_id"],
        )

    def test_all_review_artifacts_create_no_media(self):
        for artifact in (
            self.dossier,
            self.critical_review,
            self.prototype_plan,
            self.approval_request,
            self.review_binding,
        ):
            self.assertEqual(artifact["media_assets_created"], 0)

    def test_execution_is_uniformly_blocked(self):
        for artifact in (
            self.dossier,
            self.critical_review,
            self.prototype_plan,
            self.approval_request,
            self.review_binding,
            self.updated_brief,
        ):
            self.assertEqual(artifact["live_provider_execution"], "BLOCKED")
            self.assertEqual(artifact["paid_execution"], "BLOCKED")
            self.assertEqual(artifact["direct_execution"], "BLOCKED")
            self.assertEqual(artifact["runware_execution"], "BLOCKED")

    def test_generated_video_allocation_remains_zero(self):
        for artifact in (
            self.dossier,
            self.critical_review,
            self.prototype_plan,
            self.approval_request,
            self.review_binding,
            self.updated_brief,
        ):
            self.assertEqual(artifact["generated_video_planned_seconds"], 0)

    def test_markdown_contains_exact_phrase(self):
        self.assertIn(EXACT_APPROVAL_PHRASE, self.markdown)

    def test_build_is_deterministic(self):
        rebuilt = build_all(
            storyboard=self.storyboard,
            visual_bible=self.visual_bible,
            color_script=self.color_script,
            animatic=self.animatic,
            development_audit=self.development_audit,
            development_binding=self.development_binding,
            episode_definition=self.definition,
            production_brief=self.brief,
        )
        self.assertEqual(
            rebuilt,
            (
                self.dossier,
                self.critical_review,
                self.prototype_plan,
                self.approval_request,
                self.review_binding,
                self.updated_definition,
                self.updated_brief,
                self.markdown,
            ),
        )

    def test_episode_update_is_idempotent(self):
        rebuilt = update_episode_definition(
            episode_definition=self.updated_definition,
            dossier=self.dossier,
            critical_review=self.critical_review,
            prototype_plan=self.prototype_plan,
            approval_request=self.approval_request,
            review_binding=self.review_binding,
        )
        self.assertEqual(rebuilt, self.updated_definition)

    def test_build_from_materialized_state_is_idempotent(self):
        rebuilt = build_all(
            storyboard=self.storyboard,
            visual_bible=self.visual_bible,
            color_script=self.color_script,
            animatic=self.animatic,
            development_audit=self.development_audit,
            development_binding=self.development_binding,
            episode_definition=self.updated_definition,
            production_brief=self.updated_brief,
        )
        self.assertEqual(
            rebuilt,
            (
                self.dossier,
                self.critical_review,
                self.prototype_plan,
                self.approval_request,
                self.review_binding,
                self.updated_definition,
                self.updated_brief,
                self.markdown,
            ),
        )

    def test_output_files_and_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                output_root=Path(tmp) / "report",
                dossier=self.dossier,
                critical_review=self.critical_review,
                prototype_plan=self.prototype_plan,
                approval_request=self.approval_request,
                review_binding=self.review_binding,
                episode_definition=self.updated_definition,
                production_brief=self.updated_brief,
                markdown=self.markdown,
            )
            for key, path in outputs.items():
                self.assertTrue(path.is_file(), key)

    def test_json_outputs_use_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                output_root=Path(tmp) / "report",
                dossier=self.dossier,
                critical_review=self.critical_review,
                prototype_plan=self.prototype_plan,
                approval_request=self.approval_request,
                review_binding=self.review_binding,
                episode_definition=self.updated_definition,
                production_brief=self.updated_brief,
                markdown=self.markdown,
            )
            for key in (
                "dossier",
                "critical_review",
                "prototype_plan",
                "approval_request",
                "review_binding",
                "episode_definition",
                "production_brief",
            ):
                self.assertNotIn(b"\r\n", outputs[key].read_bytes())


if __name__ == "__main__":
    unittest.main()
