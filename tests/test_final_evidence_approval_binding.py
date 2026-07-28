from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.application.storyboard_runtime.evidence_binding import (
    ApprovedEventEvidenceAdjudication,
    ApprovedEvidencePackage,
    EVIDENCE_GATE_OPEN,
    LIVE_EXECUTION_STATUS,
    canonical_json_sha256,
)
from src.application.storyboard_runtime.final_evidence_approval_binding import (
    APPROVAL_PHRASE,
    APPROVED_AT_BAGHDAD,
    APPROVED_AT_UTC,
    APPROVED_BY,
    AUTOMATIC_EVIDENCE_APPROVAL,
    DIRECTION_SCHEMA,
    DIRECT_EXECUTION,
    EXPECTED_ADJUDICATION_FINGERPRINT,
    EXPECTED_APPROVAL_PHRASE_SHA256,
    EXPECTED_EVIDENCE_FINGERPRINT,
    EXPECTED_EVIDENCE_ITEM_COUNT,
    EXPECTED_EVENT_COUNT,
    EXPECTED_SOURCE_COUNT,
    EXPECTED_SOURCE_FINGERPRINT,
    FINAL_APPROVAL_SCHEMA,
    LIVE_EXECUTION_STATUS as FINAL_LIVE_STATUS,
    PAID_EXECUTION,
    TIMEZONE,
    build_all,
    build_direction_contract,
    build_final_human_approval,
    build_human_approval_record,
    canonical_sha256,
    read_json,
    read_json_list,
    text_sha256,
    validate_approval_inputs,
    write_report,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode-001-adam"
EVIDENCE = EPISODE / "evidence"
CONTRACTS = EPISODE / "contracts"
CINEMATIC = EPISODE / "cinematic"
CLI = (
    ROOT
    / "scripts"
    / "fast_track"
    / "build_adam_final_evidence_approval_binding_v1.py"
)


class FinalEvidenceApprovalBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_candidate = read_json(
            CONTRACTS / "source-package-v1.approval-candidate.json"
        )
        cls.evidence_candidate = read_json(
            EVIDENCE / "approved-evidence-package-v1.candidate.json"
        )
        cls.adjudication_candidate = read_json(
            EVIDENCE / "event-evidence-adjudication-v1.candidate.json"
        )
        cls.approval_request = read_json(
            EVIDENCE / "final-evidence-human-approval-request-v1.json"
        )
        cls.definition = read_json(
            CONTRACTS / "episode-definition-v1.json"
        )
        cls.event_map = read_json_list(
            EPISODE / "editorial/event-map.json"
        )
        cls.blueprint = read_json(
            CINEMATIC / "editorial-cinematic-blueprint-v1.json"
        )
        cls.artifacts = build_all(
            source_candidate=cls.source_candidate,
            evidence_candidate=cls.evidence_candidate,
            adjudication_candidate=cls.adjudication_candidate,
            approval_request=cls.approval_request,
            episode_definition=cls.definition,
            event_map=cls.event_map,
            editorial_blueprint=cls.blueprint,
        )

    def test_exact_approval_phrase(self):
        self.assertEqual(
            self.approval_request["exact_approval_phrase"],
            APPROVAL_PHRASE,
        )

    def test_approval_phrase_hash(self):
        self.assertEqual(
            text_sha256(APPROVAL_PHRASE),
            EXPECTED_APPROVAL_PHRASE_SHA256,
        )

    def test_source_fingerprint(self):
        self.assertEqual(
            self.source_candidate["input_fingerprint"],
            EXPECTED_SOURCE_FINGERPRINT,
        )

    def test_evidence_fingerprint(self):
        self.assertEqual(
            self.evidence_candidate["candidate_fingerprint"],
            EXPECTED_EVIDENCE_FINGERPRINT,
        )

    def test_adjudication_fingerprint(self):
        self.assertEqual(
            self.adjudication_candidate["candidate_fingerprint"],
            EXPECTED_ADJUDICATION_FINGERPRINT,
        )

    def test_candidate_validation_passes(self):
        validate_approval_inputs(
            source_candidate=self.source_candidate,
            evidence_candidate=self.evidence_candidate,
            adjudication_candidate=self.adjudication_candidate,
            approval_request=self.approval_request,
        )

    def test_approval_schema(self):
        self.assertEqual(
            self.artifacts["approval"]["schema_version"],
            FINAL_APPROVAL_SCHEMA,
        )

    def test_human_approval_true(self):
        self.assertTrue(
            self.artifacts["approval"]["human_approval"]
        )

    def test_approved_by_is_creator(self):
        self.assertEqual(
            self.artifacts["approval"]["approved_by"], APPROVED_BY
        )

    def test_baghdad_timestamp(self):
        self.assertEqual(
            self.artifacts["approval"]["approved_at_baghdad"],
            APPROVED_AT_BAGHDAD,
        )

    def test_timezone_is_baghdad(self):
        self.assertEqual(
            self.artifacts["approval"]["timezone"], TIMEZONE
        )

    def test_utc_timestamp_for_strict_binder(self):
        self.assertEqual(
            self.artifacts["approval"]["approved_at"],
            APPROVED_AT_UTC,
        )
        self.assertTrue(APPROVED_AT_UTC.endswith("Z"))

    def test_no_automatic_approval(self):
        self.assertEqual(
            self.artifacts["approval"]["automatic_evidence_approval"],
            AUTOMATIC_EVIDENCE_APPROVAL,
        )

    def test_paid_execution_blocked(self):
        self.assertEqual(
            self.artifacts["approval"]["paid_execution"],
            PAID_EXECUTION,
        )

    def test_direct_execution_blocked(self):
        self.assertEqual(
            self.artifacts["approval"]["direct_execution"],
            DIRECT_EXECUTION,
        )

    def test_live_provider_execution_blocked(self):
        self.assertEqual(
            self.artifacts["approval"]["live_provider_execution"],
            FINAL_LIVE_STATUS,
        )

    def test_source_package_approved(self):
        package = self.artifacts["source_package"]
        self.assertEqual(package["package_status"], "APPROVED")
        self.assertTrue(package["human_approval"])

    def test_source_count(self):
        self.assertEqual(
            self.artifacts["source_package"]["source_count"],
            EXPECTED_SOURCE_COUNT,
        )

    def test_source_fingerprint_preserved(self):
        self.assertEqual(
            self.artifacts["source_package"]["input_fingerprint"],
            EXPECTED_SOURCE_FINGERPRINT,
        )

    def test_evidence_package_contract(self):
        ApprovedEvidencePackage.from_mapping(
            self.artifacts["evidence_package"]
        )

    def test_evidence_item_count(self):
        self.assertEqual(
            len(self.artifacts["evidence_package"]["evidence_items"]),
            EXPECTED_EVIDENCE_ITEM_COUNT,
        )

    def test_adjudication_contract(self):
        ApprovedEventEvidenceAdjudication.from_mapping(
            self.artifacts["adjudication"]
        )

    def test_adjudication_decision_count(self):
        self.assertEqual(
            len(self.artifacts["adjudication"]["decisions"]),
            EXPECTED_EVENT_COUNT,
        )

    def test_adjudication_points_to_final_package(self):
        self.assertEqual(
            self.artifacts["adjudication"]["evidence_package_id"],
            self.artifacts["evidence_package"]["package_id"],
        )

    def test_episode_source_reference_approved(self):
        source_ref = self.artifacts["episode_definition"][
            "source_package"
        ]
        self.assertEqual(source_ref["approval_status"], "APPROVED")

    def test_episode_evidence_fingerprint_matches(self):
        evidence_ref = self.artifacts["episode_definition"][
            "evidence_package"
        ]
        self.assertEqual(
            evidence_ref["input_fingerprint"],
            canonical_json_sha256(
                self.artifacts["evidence_package"]
            ),
        )

    def test_episode_adjudication_fingerprint_matches(self):
        ref = self.artifacts["episode_definition"][
            "event_evidence_adjudication"
        ]
        self.assertEqual(
            ref["input_fingerprint"],
            canonical_json_sha256(
                self.artifacts["adjudication"]
            ),
        )

    def test_historical_scope_approved(self):
        self.assertEqual(
            self.artifacts["episode_definition"][
                "historical_scope"
            ]["status"],
            "APPROVED",
        )

    def test_evidence_gate_open(self):
        self.assertEqual(
            self.artifacts["bound_blueprint"][
                "evidence_gate_status"
            ],
            EVIDENCE_GATE_OPEN,
        )

    def test_episode_gate_open(self):
        self.assertEqual(
            self.artifacts["episode_definition"][
                "evidence_gate_status"
            ],
            EVIDENCE_GATE_OPEN,
        )

    def test_binding_live_execution_blocked(self):
        self.assertEqual(
            self.artifacts["bound_blueprint"][
                "live_execution_status"
            ],
            LIVE_EXECUTION_STATUS,
        )

    def test_binding_runware_blocked(self):
        self.assertTrue(
            self.artifacts["bound_blueprint"][
                "runware_execution_status"
            ].startswith("BLOCKED")
        )

    def test_binding_has_36_included_events(self):
        self.assertEqual(
            len(
                self.artifacts["bound_blueprint"][
                    "event_resolution"
                ]["included_event_ids"]
            ),
            36,
        )

    def test_binding_has_7_qualified_events(self):
        self.assertEqual(
            len(
                self.artifacts["bound_blueprint"][
                    "event_resolution"
                ]["qualified_event_ids"]
            ),
            7,
        )

    def test_binding_has_no_omitted_events(self):
        self.assertEqual(
            self.artifacts["bound_blueprint"][
                "event_resolution"
            ]["omitted_event_ids"],
            [],
        )

    def test_binding_has_one_editorial_event(self):
        self.assertEqual(
            self.artifacts["bound_blueprint"][
                "event_resolution"
            ]["editorial_event_ids"],
            ["EV-ADAM-099"],
        )

    def test_storyboard_frame_count_preserved(self):
        self.assertEqual(
            self.artifacts["bound_blueprint"]["storyboard"][
                "frame_count"
            ],
            14,
        )

    def test_direction_schema(self):
        self.assertEqual(
            self.artifacts["direction"]["schema_version"],
            DIRECTION_SCHEMA,
        )

    def test_format_is_prestige_historical_series(self):
        self.assertEqual(
            self.artifacts["direction"]["format_identity"],
            "PRESTIGE_HISTORICAL_CINEMATIC_SERIES",
        )

    def test_dry_documentary_is_forbidden(self):
        forbidden = self.artifacts["direction"][
            "forbidden_failure_modes"
        ]
        self.assertIn("Dry explanatory documentary voice", forbidden)
        self.assertIn("Lecture structure", forbidden)
        self.assertIn("Slide-show montage", forbidden)

    def test_world_class_ambition_recorded(self):
        self.assertIn(
            "greatest historical cinema",
            self.artifacts["direction"]["quality_ambition"],
        )

    def test_direction_keeps_paid_execution_blocked(self):
        self.assertEqual(
            self.artifacts["direction"]["paid_execution"],
            PAID_EXECUTION,
        )

    def test_binding_receipt_status(self):
        self.assertEqual(
            self.artifacts["binding_receipt"]["status"],
            "PASS_APPROVED_EVIDENCE_STRICT_OFFLINE_BINDING",
        )

    def test_binding_receipt_uses_baghdad_timezone(self):
        self.assertEqual(
            self.artifacts["binding_receipt"]["timezone"],
            TIMEZONE,
        )

    def test_next_stage_is_script_and_storyboard(self):
        self.assertEqual(
            self.artifacts["episode_definition"]["next_stage"],
            "EVIDENCE_BOUND_CINEMATIC_SCRIPT_AND_STORYBOARD_DEVELOPMENT",
        )

    def test_build_is_deterministic(self):
        second = build_all(
            source_candidate=self.source_candidate,
            evidence_candidate=self.evidence_candidate,
            adjudication_candidate=self.adjudication_candidate,
            approval_request=self.approval_request,
            episode_definition=self.definition,
            event_map=self.event_map,
            editorial_blueprint=self.blueprint,
        )
        self.assertEqual(self.artifacts, second)

    def test_report_outputs_and_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_report(
                output_root=Path(tmp) / "report",
                artifacts=self.artifacts,
            )
            for path in outputs.values():
                self.assertTrue(path.is_file())

    def test_report_json_uses_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_report(
                output_root=Path(tmp) / "report",
                artifacts=self.artifacts,
            )
            for key in (
                "approval",
                "direction",
                "source_package",
                "evidence_package",
                "adjudication",
                "bound_blueprint",
                "binding_receipt",
                "episode_definition",
            ):
                raw = outputs[key].read_bytes()
                self.assertTrue(raw.endswith(b"\n"))
                self.assertNotIn(b"\r\n", raw)

    def test_cli_runs_from_arbitrary_cwd_without_raw_arabic_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_root = Path(tmp) / "report"
            with tempfile.TemporaryDirectory() as cwd:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        str(CLI),
                        "--repo-root",
                        str(ROOT),
                        "--output-root",
                        str(output_root),
                    ],
                    cwd=cwd,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
            self.assertIn(
                "STATUS=PASS_ADAM_FINAL_EVIDENCE_APPROVAL_AND_STRICT_BINDING",
                result.stdout,
            )
            self.assertNotIn(APPROVAL_PHRASE, result.stdout)
            self.assertTrue(output_root.is_dir())


if __name__ == "__main__":
    unittest.main()
