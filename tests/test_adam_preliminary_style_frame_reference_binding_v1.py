from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.application.storyboard_runtime.preliminary_style_frame_reference_binding_v1 import (
    MOTION_AUTHORISATION,
    OPERATIONAL_NEXT_STAGE,
    STYLE_APPROVAL_PHRASE,
    STYLE_APPROVAL_PHRASE_SHA256,
    TRANSITION_INSTRUCTION,
    TRANSITION_INSTRUCTION_SHA256,
    build_all,
    read_json,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode-001-adam"
CINEMATIC = EPISODE / "cinematic"
CONTRACTS = EPISODE / "contracts"
ASSETS = CINEMATIC / "preliminary-style-frame-reference-set-v1/assets"


class AdamPreliminaryStyleFrameReferenceBindingV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definition = read_json(CONTRACTS / "episode-definition-v1.json")
        cls.brief = read_json(CINEMATIC / "prestige-production-brief-v2-1.json")
        cls.result = build_all(
            asset_root=ASSETS,
            episode_definition=cls.definition,
            production_brief=cls.brief,
        )
        (
            cls.reference_set,
            cls.policy,
            cls.approval,
            cls.receipt,
            cls.binding,
            cls.gate,
            cls.updated_definition,
            cls.updated_brief,
            cls.markdown,
        ) = cls.result

    def test_eight_unique_approved_png_assets(self):
        self.assertEqual(self.reference_set["reference_asset_count"], 8)
        self.assertEqual(len(self.reference_set["assets"]), 8)
        self.assertEqual(len({item["sha256"] for item in self.reference_set["assets"]}), 8)
        self.assertTrue(all((item["width"], item["height"]) == (1672, 941) for item in self.reference_set["assets"]))

    def test_exact_human_messages_and_hashes(self):
        self.assertEqual(self.approval["approval_phrase"], STYLE_APPROVAL_PHRASE)
        self.assertEqual(self.approval["approval_phrase_sha256"], STYLE_APPROVAL_PHRASE_SHA256)
        self.assertEqual(self.approval["transition_instruction"], TRANSITION_INSTRUCTION)
        self.assertEqual(self.approval["transition_instruction_sha256"], TRANSITION_INSTRUCTION_SHA256)

    def test_approval_is_preliminary_not_final(self):
        self.assertTrue(self.reference_set["human_approval"])
        self.assertEqual(self.reference_set["storyboard_binding_status"], "NOT_FINAL_SHOT_BINDING")
        for artifact in (self.reference_set, self.policy, self.approval, self.receipt, self.binding, self.gate):
            self.assertFalse(artifact["master_visual_approval"])
            self.assertFalse(artifact["final_master_visual_approval"])

    def test_visual_safety_rules_are_blocking(self):
        rules = {item["rule_id"]: item for item in self.policy["rules"]}
        required = {
            "NO_ANGEL_DEPICTION",
            "NO_FEMALE_SKIN_OR_FORM_DISPLAY",
            "ADAM_DARK_SKIN_WHEN_DEPICTED",
            "NO_CLEAR_PROPHET_FACE",
            "NO_FULL_PROPHET_BODY_AFTER_DESCENT",
            "PARADISE_NO_DECAY_BARRENNESS_OR_DEPLETION",
            "TREE_SPECIES_NOT_ASSERTED",
            "PRELIMINARY_REFERENCE_NOT_FINAL_IDENTITY",
        }
        self.assertEqual(set(rules), required)
        self.assertTrue(all(rules[key]["severity"] == "BLOCKING" for key in required))

    def test_motion_gate_is_one_environment_only_non_paid_shot(self):
        self.assertEqual(self.gate["video_prototype_authorisation"], MOTION_AUTHORISATION)
        self.assertEqual(self.gate["source_asset_id"], "ADAM-PREF-001")
        self.assertFalse(self.gate["source_contains_people"])
        self.assertEqual(self.gate["output_count_limit"], 1)
        self.assertEqual((self.gate["minimum_duration_seconds"], self.gate["maximum_duration_seconds"]), (8, 12))
        self.assertEqual(self.gate["audio_generation"], "BLOCKED")
        self.assertEqual(self.gate["full_episode_video_generation"], "BLOCKED")
        for key in ("paid_execution", "live_provider_execution", "direct_execution", "runware_execution"):
            self.assertEqual(self.gate[key], "BLOCKED")

    def test_operational_transition_preserves_canonical_audit_stage(self):
        self.assertEqual(self.updated_definition["operational_next_stage"], OPERATIONAL_NEXT_STAGE)
        self.assertEqual(
            self.updated_definition["next_stage"],
            "NON_PAID_MASTER_STYLE_FRAMES_AND_KEYFRAME_PROTOTYPING_V1",
        )
        self.assertEqual(self.updated_brief["operational_next_stage"], OPERATIONAL_NEXT_STAGE)
        self.assertEqual(self.updated_brief["generated_video_planned_seconds"], 0)

    def test_binding_chain(self):
        self.assertEqual(self.receipt["approval_id"], self.approval["approval_id"])
        self.assertEqual(self.binding["approval_receipt_id"], self.receipt["receipt_id"])
        self.assertEqual(self.gate["source_approval_binding_id"], self.binding["binding_id"])
        self.assertEqual(self.gate["source_reference_set_id"], self.reference_set["reference_set_id"])

    def test_build_is_idempotent_from_materialized_state(self):
        second = build_all(
            asset_root=ASSETS,
            episode_definition=self.updated_definition,
            production_brief=self.updated_brief,
        )
        self.assertEqual(second, self.result)

    def test_output_archive_is_deterministic_and_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            one = write_outputs(
                output_root=Path(tmp) / "one",
                reference_set=self.reference_set,
                policy=self.policy,
                approval=self.approval,
                receipt=self.receipt,
                binding=self.binding,
                gate=self.gate,
                episode_definition=self.updated_definition,
                production_brief=self.updated_brief,
                markdown=self.markdown,
            )
            two = write_outputs(
                output_root=Path(tmp) / "two",
                reference_set=self.reference_set,
                policy=self.policy,
                approval=self.approval,
                receipt=self.receipt,
                binding=self.binding,
                gate=self.gate,
                episode_definition=self.updated_definition,
                production_brief=self.updated_brief,
                markdown=self.markdown,
            )
            self.assertEqual(one["archive"].read_bytes(), two["archive"].read_bytes())
            for key, path in one.items():
                if key != "archive":
                    self.assertNotIn(b"\r\n", path.read_bytes())


if __name__ == "__main__":
    unittest.main()
