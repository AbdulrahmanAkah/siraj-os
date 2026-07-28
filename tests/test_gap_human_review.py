from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.application.storyboard_runtime.gap_human_review import (
    APPROVAL_TEMPLATE_SCHEMA,
    APPROVAL_TEMPLATE_STATUS,
    AUTOMATIC_APPROVAL_STATUS,
    EVIDENCE_GATE_STATUS,
    REVIEW_PACKET_SCHEMA,
    REVIEW_PACKET_STATUS,
    GapHumanReviewError,
    approval_template,
    build_review_packet,
    canonical_json_sha256,
    load_and_build,
    validate_approval_template,
    validate_review_packet,
    write_json,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "projects/episode-001-adam/evidence"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


class GapHumanReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.classification = read_json(EVIDENCE / "source-origin-classification-v1.json")
        self.proposal = read_json(EVIDENCE / "proposed-gap-adjudication-v1.json")
        self.packet = build_review_packet(
            classification=self.classification,
            proposal=self.proposal,
        )
        self.template = approval_template(self.packet)

    def test_schemas_and_statuses(self) -> None:
        self.assertEqual(self.packet["schema_version"], REVIEW_PACKET_SCHEMA)
        self.assertEqual(self.packet["status"], REVIEW_PACKET_STATUS)
        self.assertEqual(self.template["schema_version"], APPROVAL_TEMPLATE_SCHEMA)
        self.assertEqual(self.template["status"], APPROVAL_TEMPLATE_STATUS)

    def test_exact_three_events(self) -> None:
        self.assertEqual(
            [item["event_id"] for item in self.packet["review_items"]],
            ["EV-ADAM-031", "EV-ADAM-071", "EV-ADAM-091"],
        )

    def test_expected_dispositions(self) -> None:
        self.assertEqual(
            [item["proposed_disposition"] for item in self.packet["review_items"]],
            ["include_assertive", "include_qualified", "include_qualified"],
        )

    def test_each_event_has_source_records(self) -> None:
        for item in self.packet["review_items"]:
            self.assertTrue(item["source_record_ids"])
            self.assertEqual(
                len(item["source_record_ids"]), len(item["source_summaries"])
            )

    def test_sneeze_uses_only_sound_hadith_record(self) -> None:
        first = self.packet["review_items"][0]
        self.assertEqual(
            first["source_record_ids"],
            ["SRCREC-ADAM-SNEEZE-TIRMIDHI-3368"],
        )

    def test_hawa_includes_two_premises_and_qualified_loneliness(self) -> None:
        second = self.packet["review_items"][1]
        self.assertIn("SRCREC-HAWA-NAME-BUKHARI-3330-MUSLIM-1470", second["source_record_ids"])
        self.assertIn("SRCREC-WOMAN-RIB-BUKHARI-3331-MUSLIM-1468", second["source_record_ids"])
        self.assertIn("SRCREC-TABARI-8406-SUDDI-LONELINESS", second["source_record_ids"])

    def test_tree_has_non_determination_sources(self) -> None:
        third = self.packet["review_items"][2]
        self.assertEqual(
            third["source_record_ids"],
            [
                "SRCREC-TABARI-TREE-NONDETERMINATION",
                "SRCREC-IBN-KATHIR-TREE-NONDETERMINATION",
            ],
        )

    def test_packet_does_not_approve_or_bind(self) -> None:
        self.assertFalse(self.packet["human_evidence_approval"])
        self.assertFalse(self.packet["binding"])
        self.assertEqual(self.packet["automatic_evidence_approval"], AUTOMATIC_APPROVAL_STATUS)
        self.assertEqual(self.packet["evidence_gate_status"], EVIDENCE_GATE_STATUS)
        self.assertFalse(self.packet["evidence_binding_readiness"]["ready"])

    def test_template_is_blank(self) -> None:
        self.assertFalse(self.template["human_approval"])
        self.assertEqual(self.template["approved_by"], "")
        self.assertEqual(self.template["approved_at"], "")
        self.assertFalse(self.template["opens_evidence_gate"])
        for item in self.template["decisions"]:
            self.assertFalse(item["approved"])
            self.assertFalse(item["human_decision"])

    def test_template_is_bound_to_packet_hash(self) -> None:
        self.assertEqual(
            self.template["review_packet_sha256"],
            canonical_json_sha256(self.packet),
        )

    def test_stale_proposal_hash_is_rejected(self) -> None:
        changed = copy.deepcopy(self.proposal)
        changed["classification_sha256"] = "0" * 64
        with self.assertRaises(GapHumanReviewError):
            build_review_packet(classification=self.classification, proposal=changed)

    def test_auto_approval_is_rejected(self) -> None:
        changed = copy.deepcopy(self.packet)
        changed["automatic_evidence_approval"] = "ALLOWED"
        with self.assertRaises(GapHumanReviewError):
            validate_review_packet(changed)

    def test_human_approval_in_packet_is_rejected(self) -> None:
        changed = copy.deepcopy(self.packet)
        changed["human_evidence_approval"] = True
        with self.assertRaises(GapHumanReviewError):
            validate_review_packet(changed)

    def test_binding_readiness_cannot_be_claimed(self) -> None:
        changed = copy.deepcopy(self.packet)
        changed["evidence_binding_readiness"]["ready"] = True
        with self.assertRaises(GapHumanReviewError):
            validate_review_packet(changed)

    def test_template_cannot_be_preapproved(self) -> None:
        changed = copy.deepcopy(self.template)
        changed["human_approval"] = True
        with self.assertRaises(GapHumanReviewError):
            validate_approval_template(changed, packet=self.packet)

    def test_template_cannot_open_gate(self) -> None:
        changed = copy.deepcopy(self.template)
        changed["opens_evidence_gate"] = True
        with self.assertRaises(GapHumanReviewError):
            validate_approval_template(changed, packet=self.packet)

    def test_raw_source_text_field_is_rejected(self) -> None:
        changed = copy.deepcopy(self.packet)
        changed["raw_text"] = "forbidden"
        with self.assertRaises(GapHumanReviewError):
            validate_review_packet(changed)

    def test_secret_like_field_is_rejected(self) -> None:
        changed = copy.deepcopy(self.packet)
        changed["api_key"] = "forbidden"
        with self.assertRaises(GapHumanReviewError):
            validate_review_packet(changed)

    def test_deterministic_packet(self) -> None:
        second = build_review_packet(
            classification=self.classification,
            proposal=self.proposal,
        )
        self.assertEqual(self.packet, second)

    def test_load_and_build(self) -> None:
        packet, template = load_and_build(
            classification_path=EVIDENCE / "source-origin-classification-v1.json",
            proposal_path=EVIDENCE / "proposed-gap-adjudication-v1.json",
        )
        self.assertEqual(packet, self.packet)
        self.assertEqual(template, self.template)

    def test_write_json_is_utf8_lf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "packet.json"
            write_json(path, self.packet)
            data = path.read_bytes()
        self.assertNotIn(b"\r\n", data)
        self.assertTrue(data.endswith(b"\n"))
        json.loads(data.decode("utf-8"))

    def test_cli_runs_from_arbitrary_cwd(self) -> None:
        script = ROOT / "scripts/fast_track/build_adam_gap_human_review_packet_v1.py"
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(script),
                    "--repo-root",
                    str(ROOT),
                    "--output-root",
                    temporary,
                ],
                cwd=temporary,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("STATUS=PASS_ADAM_GAP_HUMAN_REVIEW_PACKET", result.stdout)
        self.assertIn("HUMAN_EVIDENCE_APPROVAL=PENDING", result.stdout)


if __name__ == "__main__":
    unittest.main()
