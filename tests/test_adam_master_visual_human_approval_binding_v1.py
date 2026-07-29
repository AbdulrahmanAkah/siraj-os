from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.application.storyboard_runtime.master_visual_human_approval_binding_v1 import (
    ANCHOR_SHOT_IDS,
    DECISION,
    EXACT_APPROVAL_PHRASE,
    EXACT_APPROVAL_PHRASE_SHA256,
    NEXT_STAGE,
    STYLE_FRAME_AUTHORISATION,
    build_all,
    read_json,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode-001-adam"
CINEMATIC = EPISODE / "cinematic"
EVIDENCE = EPISODE / "evidence"
CONTRACTS = EPISODE / "contracts"


class AdamMasterVisualHumanApprovalBindingV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dossier = read_json(CINEMATIC / "master-visual-human-review-dossier-v1.json")
        cls.critical = read_json(CINEMATIC / "master-visual-critical-review-v1.json")
        cls.plan = read_json(CINEMATIC / "master-style-frame-prototype-plan-v1.json")
        cls.request = read_json(EVIDENCE / "master-visual-human-approval-request-v1.json")
        cls.review_binding = read_json(CONTRACTS / "master-visual-human-review-binding-v1.json")
        cls.definition = read_json(CONTRACTS / "episode-definition-v1.json")
        cls.brief = read_json(CINEMATIC / "prestige-production-brief-v2-1.json")
        (
            cls.approval,
            cls.receipt,
            cls.binding,
            cls.gate,
            cls.updated_plan,
            cls.updated_definition,
            cls.updated_brief,
            cls.markdown,
        ) = build_all(
            dossier=cls.dossier,
            critical_review=cls.critical,
            prototype_plan=cls.plan,
            approval_request=cls.request,
            review_binding=cls.review_binding,
            episode_definition=cls.definition,
            production_brief=cls.brief,
        )

    def test_exact_phrase_and_hash(self):
        self.assertEqual(self.approval["approval_phrase"], EXACT_APPROVAL_PHRASE)
        self.assertEqual(self.approval["approval_phrase_sha256"], EXACT_APPROVAL_PHRASE_SHA256)

    def test_human_decision_is_exact(self):
        self.assertTrue(self.approval["human_approval"])
        self.assertEqual(self.approval["human_decision"], DECISION)

    def test_scope_is_eight_non_paid_stills_only(self):
        self.assertEqual(self.gate["approved_prototype_count"], 8)
        self.assertEqual(self.gate["approved_anchor_shot_ids"], list(ANCHOR_SHOT_IDS))
        self.assertEqual(self.gate["image_generation_authorisation"], STYLE_FRAME_AUTHORISATION)
        self.assertEqual(self.gate["image_generation_scope"], "EIGHT_MASTER_STYLE_FRAME_STILL_IMAGES_ONLY")

    def test_final_master_visual_remains_unapproved(self):
        for artifact in (
            self.approval,
            self.receipt,
            self.binding,
            self.gate,
            self.updated_plan,
            self.updated_brief,
        ):
            self.assertFalse(artifact["master_visual_approval"])
        self.assertFalse(self.updated_definition["master_visual_approval"])

    def test_video_audio_and_execution_remain_blocked(self):
        self.assertEqual(self.gate["audio_generation"], "BLOCKED")
        self.assertEqual(self.gate["video_generation"], "BLOCKED")
        for artifact in (
            self.approval,
            self.receipt,
            self.binding,
            self.gate,
            self.updated_plan,
            self.updated_brief,
        ):
            self.assertEqual(artifact["generated_video_planned_seconds"], 0)
            self.assertEqual(artifact["paid_execution"], "BLOCKED")
            self.assertEqual(artifact["direct_execution"], "BLOCKED")
            self.assertEqual(artifact["live_provider_execution"], "BLOCKED")
            self.assertEqual(artifact["runware_execution"], "BLOCKED")

    def test_receipt_and_binding_chain(self):
        self.assertEqual(self.receipt["approval_id"], self.approval["approval_id"])
        self.assertEqual(self.binding["approval_receipt_id"], self.receipt["receipt_id"])
        self.assertEqual(self.gate["source_approval_binding_id"], self.binding["binding_id"])

    def test_prototype_plan_is_authorised(self):
        self.assertEqual(
            self.updated_plan["status"],
            "HUMAN_APPROVED_READY_FOR_NON_PAID_PROTOTYPE_EXECUTION",
        )
        self.assertEqual(
            self.updated_plan["image_generation_authorisation"],
            STYLE_FRAME_AUTHORISATION,
        )
        self.assertTrue(self.updated_plan["human_approval"])

    def test_episode_advances_to_prototype_stage(self):
        self.assertEqual(self.updated_definition["next_stage"], NEXT_STAGE)
        approval = self.updated_definition["master_visual_human_approval"]
        self.assertTrue(approval["development_baseline_approval"])
        self.assertFalse(approval["final_master_visual_approval"])

    def test_production_brief_binds_gate(self):
        self.assertEqual(
            self.updated_brief["style_frame_prototyping_gate_id"],
            self.gate["gate_id"],
        )
        self.assertEqual(self.updated_brief["next_non_paid_stage"], NEXT_STAGE)

    def test_build_is_deterministic(self):
        second = build_all(
            dossier=self.dossier,
            critical_review=self.critical,
            prototype_plan=self.plan,
            approval_request=self.request,
            review_binding=self.review_binding,
            episode_definition=self.definition,
            production_brief=self.brief,
        )
        self.assertEqual(second, (
            self.approval,
            self.receipt,
            self.binding,
            self.gate,
            self.updated_plan,
            self.updated_definition,
            self.updated_brief,
            self.markdown,
        ))

    def test_build_from_materialized_state_is_idempotent(self):
        second = build_all(
            dossier=self.dossier,
            critical_review=self.critical,
            prototype_plan=self.updated_plan,
            approval_request=self.request,
            review_binding=self.review_binding,
            episode_definition=self.updated_definition,
            production_brief=self.updated_brief,
        )
        self.assertEqual(
            second,
            (
                self.approval,
                self.receipt,
                self.binding,
                self.gate,
                self.updated_plan,
                self.updated_definition,
                self.updated_brief,
                self.markdown,
            ),
        )

    def test_output_files_archive_and_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                output_root=Path(tmp) / "report",
                approval=self.approval,
                receipt=self.receipt,
                binding=self.binding,
                gate=self.gate,
                prototype_plan=self.updated_plan,
                episode_definition=self.updated_definition,
                production_brief=self.updated_brief,
                markdown=self.markdown,
            )
            for path in outputs.values():
                self.assertTrue(path.is_file())
            for key in (
                "approval", "receipt", "binding", "gate", "prototype_plan",
                "episode_definition", "production_brief",
            ):
                self.assertNotIn(b"\r\n", outputs[key].read_bytes())


if __name__ == "__main__":
    unittest.main()
