from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.final_storyboard_master_approval_binding_v2_1 import (
    ALLOWED_DOWNSTREAM_STAGES,
    ALLOWED_NON_PAID_STAGES,
    APPROVAL_REQUEST_ID,
    DIRECTORIAL_AUDIT_ID,
    EXACT_APPROVAL_PHRASE,
    EXACT_APPROVAL_PHRASE_SHA256,
    FORBIDDEN_EXECUTION_MODES,
    NEXT_STAGE,
    SCRIPT_FINGERPRINT,
    SCRIPT_ID,
    STORYBOARD_FINGERPRINT,
    STORYBOARD_ID,
    build_all,
    build_approval_record,
    build_binding_receipt,
    build_approval_binding,
    build_visual_development_gate,
    count_unresolved_directorial_decisions,
    read_json,
    update_episode_definition,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode-001-adam"
EDITORIAL = EPISODE / "editorial"
CINEMATIC = EPISODE / "cinematic"
EVIDENCE = EPISODE / "evidence"
CONTRACTS = EPISODE / "contracts"


class FinalStoryboardMasterApprovalBindingV21Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = read_json(
            EDITORIAL / "prestige-cinematic-script-v2-1.json"
        )
        cls.storyboard = read_json(
            CINEMATIC / "detailed-storyboard-v2-1.json"
        )
        cls.trace = read_json(
            EVIDENCE / "script-storyboard-evidence-trace-v2-1.json"
        )
        cls.request = read_json(
            EVIDENCE
            / "script-storyboard-human-approval-request-v2-1.json"
        )
        cls.audit = read_json(
            CINEMATIC / "storyboard-master-directorial-audit-v2-1.json"
        )
        cls.definition = read_json(
            CONTRACTS / "episode-definition-v1.json"
        )
        (
            cls.approval,
            cls.receipt,
            cls.binding,
            cls.visual_gate,
            cls.updated,
        ) = build_all(
            script=cls.script,
            storyboard=cls.storyboard,
            trace=cls.trace,
            approval_request=cls.request,
            audit=cls.audit,
            episode_definition=cls.definition,
        )

    def test_exact_approval_phrase(self):
        self.assertEqual(
            self.approval["approval_phrase"],
            EXACT_APPROVAL_PHRASE,
        )

    def test_exact_approval_phrase_hash(self):
        self.assertEqual(
            self.approval["approval_phrase_sha256"],
            EXACT_APPROVAL_PHRASE_SHA256,
        )

    def test_request_id_is_exact(self):
        self.assertEqual(
            self.approval["approval_request_id"],
            APPROVAL_REQUEST_ID,
        )

    def test_request_remains_immutable_pending_record(self):
        self.assertFalse(self.request["human_approval"])

    def test_script_id_is_exact(self):
        self.assertEqual(self.binding["script_id"], SCRIPT_ID)

    def test_script_fingerprint_is_exact(self):
        self.assertEqual(
            self.binding["script_fingerprint"],
            SCRIPT_FINGERPRINT,
        )

    def test_storyboard_id_is_exact(self):
        self.assertEqual(self.binding["storyboard_id"], STORYBOARD_ID)

    def test_storyboard_fingerprint_is_exact(self):
        self.assertEqual(
            self.binding["storyboard_fingerprint"],
            STORYBOARD_FINGERPRINT,
        )

    def test_directorial_audit_is_exact(self):
        self.assertEqual(
            self.approval["directorial_audit_id"],
            DIRECTORIAL_AUDIT_ID,
        )

    def test_persisted_audit_schema_needs_no_synthetic_field(self):
        self.assertNotIn(
            "unresolved_directorial_decisions",
            self.audit,
        )

    def test_persisted_audit_derives_zero_unresolved_decisions(self):
        self.assertEqual(
            count_unresolved_directorial_decisions(self.audit),
            0,
        )

    def test_build_is_deterministic(self):
        rebuilt = build_all(
            script=self.script,
            storyboard=self.storyboard,
            trace=self.trace,
            approval_request=self.request,
            audit=self.audit,
            episode_definition=self.definition,
        )
        self.assertEqual(
            rebuilt,
            (
                self.approval,
                self.receipt,
                self.binding,
                self.visual_gate,
                self.updated,
            ),
        )

    def test_human_approval_is_true(self):
        self.assertTrue(self.approval["human_approval"])

    def test_approval_has_top_level_live_block(self):
        self.assertEqual(
            self.approval["live_provider_execution"],
            "BLOCKED",
        )

    def test_approval_has_top_level_paid_block(self):
        self.assertEqual(
            self.approval["paid_execution"],
            "BLOCKED",
        )

    def test_approval_has_top_level_direct_and_runware_blocks(self):
        self.assertEqual(
            self.approval["direct_execution"],
            "BLOCKED",
        )
        self.assertEqual(
            self.approval["runware_execution"],
            "BLOCKED",
        )

    def test_script_scope_is_approved(self):
        self.assertEqual(
            self.approval["approval_scope"][
                "final_cinematic_script_v2_1"
            ],
            "APPROVED",
        )

    def test_religious_safety_scope_is_approved(self):
        self.assertEqual(
            self.approval["approval_scope"][
                "religious_safety_of_final_script_v2_1"
            ],
            "APPROVED",
        )

    def test_storyboard_scope_is_approved(self):
        self.assertEqual(
            self.approval["approval_scope"][
                "final_storyboard_master_v2_1"
            ],
            "APPROVED",
        )

    def test_visual_bible_is_non_paid_only(self):
        self.assertEqual(
            self.approval["approval_scope"][
                "master_visual_bible_development"
            ],
            "ALLOWED_NON_PAID_ONLY",
        )

    def test_paid_execution_remains_blocked(self):
        self.assertEqual(
            self.approval["approval_scope"]["paid_execution"],
            "BLOCKED",
        )

    def test_live_execution_remains_blocked(self):
        self.assertEqual(
            self.approval["approval_scope"][
                "live_provider_execution"
            ],
            "BLOCKED",
        )

    def test_runware_execution_remains_blocked(self):
        self.assertEqual(
            self.approval["approval_scope"]["runware_execution"],
            "BLOCKED",
        )

    def test_approval_id_is_deterministic_identifier(self):
        self.assertTrue(
            self.approval["approval_id"].startswith(
                "adam_final_storyboard_master_human_approval_v2_1_"
            )
        )

    def test_receipt_binds_approval(self):
        self.assertEqual(
            self.receipt["approval_id"],
            self.approval["approval_id"],
        )

    def test_receipt_binds_script(self):
        self.assertEqual(
            self.receipt["script_fingerprint"],
            SCRIPT_FINGERPRINT,
        )

    def test_receipt_binds_storyboard(self):
        self.assertEqual(
            self.receipt["storyboard_fingerprint"],
            STORYBOARD_FINGERPRINT,
        )

    def test_receipt_binds_audit(self):
        self.assertEqual(
            self.receipt["directorial_audit_id"],
            DIRECTORIAL_AUDIT_ID,
        )

    def test_binding_status_is_final(self):
        self.assertEqual(
            self.binding["status"],
            "BOUND_HUMAN_APPROVED_FINAL_STORYBOARD_MASTER_V2_1",
        )

    def test_visual_gate_is_open(self):
        self.assertEqual(
            self.visual_gate["status"],
            "OPEN_NON_PAID_VISUAL_DEVELOPMENT_ONLY",
        )

    def test_visual_gate_allowed_stages_are_exact(self):
        self.assertEqual(
            self.visual_gate["allowed_non_paid_stages"],
            list(ALLOWED_NON_PAID_STAGES),
        )

    def test_visual_gate_forbids_paid(self):
        self.assertIn(
            "PAID_EXECUTION",
            self.visual_gate["forbidden_execution_modes"],
        )

    def test_visual_gate_forbids_direct(self):
        self.assertIn(
            "DIRECT_PROVIDER_EXECUTION",
            self.visual_gate["forbidden_execution_modes"],
        )

    def test_visual_gate_forbids_live(self):
        self.assertIn(
            "LIVE_PROVIDER_EXECUTION",
            self.visual_gate["forbidden_execution_modes"],
        )

    def test_visual_gate_forbids_runware(self):
        self.assertIn(
            "RUNWARE_EXECUTION",
            self.visual_gate["forbidden_execution_modes"],
        )

    def test_script_definition_is_approved(self):
        self.assertTrue(
            self.updated["cinematic_script"]["human_approval"]
        )

    def test_storyboard_definition_is_approved(self):
        self.assertTrue(
            self.updated["detailed_storyboard"]["human_approval"]
        )

    def test_religious_safety_definition_is_approved(self):
        self.assertEqual(
            self.updated["script_storyboard_human_approval"][
                "religious_safety_approval"
            ],
            "APPROVED_FOR_FINAL_SCRIPT_V2_1",
        )

    def test_storyboard_completion_is_approved(self):
        self.assertEqual(
            self.updated["storyboard_completion_status"],
            "COMPLETE_HUMAN_APPROVED",
        )

    def test_next_stage_is_visual_development(self):
        self.assertIn(self.updated["next_stage"], ALLOWED_DOWNSTREAM_STAGES)

    def test_master_visual_approval_remains_pending(self):
        self.assertIn(
            self.updated["master_visual_status"],
            (
                "NOT_STARTED_HUMAN_APPROVAL_REQUIRED",
                "DEVELOPED_AWAITING_HUMAN_APPROVAL",
                "HUMAN_REVIEW_PACKAGE_READY_FINAL_APPROVAL_STILL_BLOCKED",
                "DEVELOPMENT_BASELINE_HUMAN_APPROVED_STYLE_FRAME_PROTOTYPING_AUTHORISED_FINAL_APPROVAL_BLOCKED",
            ),
        )

    def test_episode_update_is_idempotent(self):
        rebuilt = update_episode_definition(
            episode_definition=self.updated,
            approval=self.approval,
            receipt=self.receipt,
            binding=self.binding,
            visual_gate=self.visual_gate,
        )
        self.assertEqual(rebuilt, self.updated)

    def test_build_from_approved_definition_is_idempotent(self):
        rebuilt = build_all(
            script=self.script,
            storyboard=self.storyboard,
            trace=self.trace,
            approval_request=self.request,
            audit=self.audit,
            episode_definition=self.updated,
        )
        self.assertEqual(
            rebuilt,
            (
                self.approval,
                self.receipt,
                self.binding,
                self.visual_gate,
                self.updated,
            ),
        )

    def test_output_files_and_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "report"
            outputs = write_outputs(
                output_root=root,
                approval=self.approval,
                receipt=self.receipt,
                binding=self.binding,
                visual_gate=self.visual_gate,
                episode_definition=self.updated,
            )
            for key, path in outputs.items():
                self.assertTrue(path.is_file(), key)

    def test_json_outputs_use_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "report"
            outputs = write_outputs(
                output_root=root,
                approval=self.approval,
                receipt=self.receipt,
                binding=self.binding,
                visual_gate=self.visual_gate,
                episode_definition=self.updated,
            )
            for key in (
                "approval",
                "receipt",
                "binding",
                "visual_gate",
                "episode_definition",
            ):
                data = outputs[key].read_bytes()
                self.assertNotIn(b"\r\n", data)

    def test_execution_prohibition_set_is_exact(self):
        self.assertEqual(
            self.visual_gate["forbidden_execution_modes"],
            list(FORBIDDEN_EXECUTION_MODES),
        )


if __name__ == "__main__":
    unittest.main()
