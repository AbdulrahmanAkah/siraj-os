from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.full_episode_evidence_candidate import (
    ADJUDICATION_CANDIDATE_SCHEMA,
    APPROVAL_PHRASE,
    APPROVAL_REQUEST_SCHEMA,
    AUTO_APPROVAL,
    EDITORIAL_DECISION_SCHEMA,
    EDITORIAL_EVENT_ID,
    EVIDENCE_CANDIDATE_SCHEMA,
    EXPECTED_EVENT_COUNT,
    EXPECTED_EXTERNAL_EVENT_COUNT,
    EXPECTED_GAP_EVENT_COUNT,
    EXPECTED_QURAN_EVENT_COUNT,
    GAP_EVENT_IDS,
    GATE,
    INTEGRATION_SCHEMA,
    LIVE_EXECUTION,
    SOURCE_CANDIDATE_SCHEMA,
    build_approval_request,
    build_candidates,
    build_editorial_decision,
    build_integration,
    read_json,
    text_sha256,
    validate_candidates,
    validate_inputs,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode-001-adam"
EVIDENCE = EPISODE / "evidence"


class FullEpisodeEvidenceCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = read_json(
            EVIDENCE / "full-episode-adjudication-inventory-v1.json"
        )
        cls.event_map = read_json_list(
            EPISODE / "editorial/event-map.json"
        )
        cls.quran = read_json(
            EVIDENCE / "quran-event-binding-candidate-v1.json"
        )
        cls.external_scope = read_json(
            EVIDENCE / "external-event-scope-final-adjudication-v1.json"
        )
        cls.external_pack = read_json(
            EVIDENCE / "external-event-source-candidate-pack-v1.json"
        )
        cls.gap = read_json(EVIDENCE / "gap-human-approval-v1.json")
        cls.origin = read_json(
            EVIDENCE / "source-origin-classification-v1.json"
        )
        cls.delegation = read_json(
            EVIDENCE / "delegated-evidence-review-policy-v1.json"
        )
        cls.episode_definition = read_json(
            EPISODE / "contracts/episode-definition-v1.json"
        )
        validate_inputs(
            inventory=cls.inventory,
            event_map=cls.event_map,
            quran_candidate=cls.quran,
            external_scope=cls.external_scope,
            external_pack=cls.external_pack,
            gap_approval=cls.gap,
            origin_classification=cls.origin,
            delegation=cls.delegation,
            episode_definition=cls.episode_definition,
        )
        cls.editorial = build_editorial_decision()
        cls.integration = build_integration(
            inventory=cls.inventory,
            quran_candidate=cls.quran,
            external_scope=cls.external_scope,
            gap_approval=cls.gap,
            editorial_decision=cls.editorial,
        )
        (
            cls.source_candidate,
            cls.evidence_candidate,
            cls.adjudication_candidate,
        ) = build_candidates(
            integration=cls.integration,
            quran_candidate=cls.quran,
            external_scope=cls.external_scope,
            external_pack=cls.external_pack,
            gap_approval=cls.gap,
            origin_classification=cls.origin,
            editorial_decision=cls.editorial,
        )
        cls.approval_request = build_approval_request(
            integration=cls.integration,
            source_candidate=cls.source_candidate,
            evidence_candidate=cls.evidence_candidate,
            adjudication_candidate=cls.adjudication_candidate,
        )

    def test_editorial_schema(self):
        self.assertEqual(
            self.editorial["schema_version"],
            EDITORIAL_DECISION_SCHEMA,
        )

    def test_editorial_event_id(self):
        self.assertEqual(
            self.editorial["event_id"], EDITORIAL_EVENT_ID
        )

    def test_editorial_has_no_human_impersonation(self):
        self.assertFalse(self.editorial["human_decision"])
        self.assertTrue(self.editorial["delegated_ai_decision"])

    def test_integration_schema(self):
        self.assertEqual(
            self.integration["schema_version"], INTEGRATION_SCHEMA
        )

    def test_integration_has_37_events(self):
        self.assertEqual(
            self.integration["event_count"], EXPECTED_EVENT_COUNT
        )

    def test_integration_quran_count(self):
        self.assertEqual(
            self.integration["quran_event_count"],
            EXPECTED_QURAN_EVENT_COUNT,
        )

    def test_integration_external_count(self):
        self.assertEqual(
            self.integration["external_event_count"],
            EXPECTED_EXTERNAL_EVENT_COUNT,
        )

    def test_integration_gap_count(self):
        self.assertEqual(
            self.integration["gap_human_event_count"],
            EXPECTED_GAP_EVENT_COUNT,
        )

    def test_integration_editorial_count(self):
        self.assertEqual(
            self.integration["editorial_event_count"], 1
        )

    def test_integration_event_order_matches_inventory(self):
        self.assertEqual(
            [item["event_id"] for item in self.integration["events"]],
            [item["event_id"] for item in self.inventory["events"]],
        )

    def test_exact_gap_event_set(self):
        selected = {
            item["event_id"]
            for item in self.integration["events"]
            if item["route"] == "PRIOR_GAP_HUMAN_APPROVAL"
        }
        self.assertEqual(selected, set(GAP_EVENT_IDS))

    def test_only_099_is_editorial(self):
        selected = [
            item["event_id"]
            for item in self.integration["events"]
            if item["disposition"] == "editorial_only"
        ]
        self.assertEqual(selected, [EDITORIAL_EVENT_ID])

    def test_source_candidate_schema(self):
        self.assertEqual(
            self.source_candidate["schema_version"],
            SOURCE_CANDIDATE_SCHEMA,
        )

    def test_source_candidate_not_approved(self):
        self.assertEqual(
            self.source_candidate["package_status"],
            "CANDIDATE_NOT_APPROVED",
        )
        self.assertFalse(self.source_candidate["human_approval"])

    def test_source_candidate_has_sources(self):
        self.assertGreater(self.source_candidate["source_count"], 0)

    def test_source_ids_unique(self):
        ids = [
            item["source_id"]
            for item in self.source_candidate["source_items"]
        ]
        self.assertEqual(len(ids), len(set(ids)))

    def test_source_support_lists_nonempty(self):
        self.assertTrue(all(
            item["notes"]["supports_event_ids"]
            for item in self.source_candidate["source_items"]
        ))

    def test_evidence_candidate_schema(self):
        self.assertEqual(
            self.evidence_candidate["schema_version"],
            EVIDENCE_CANDIDATE_SCHEMA,
        )

    def test_evidence_candidate_not_approved(self):
        self.assertFalse(
            self.evidence_candidate["approval"]["human_approval"]
        )
        self.assertEqual(
            self.evidence_candidate["approval"]["approval_status"],
            "PENDING",
        )

    def test_evidence_items_exist(self):
        self.assertGreater(
            self.evidence_candidate["evidence_item_count"], 0
        )

    def test_evidence_ids_unique(self):
        ids = [
            item["evidence_id"]
            for item in self.evidence_candidate["evidence_items"]
        ]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_evidence_source_exists(self):
        source_ids = {
            item["source_id"]
            for item in self.source_candidate["source_items"]
        }
        self.assertTrue(all(
            item["source_id"] in source_ids
            for item in self.evidence_candidate["evidence_items"]
        ))

    def test_every_evidence_checksum_matches_source(self):
        source_index = {
            item["source_id"]: item
            for item in self.source_candidate["source_items"]
        }
        for item in self.evidence_candidate["evidence_items"]:
            self.assertEqual(
                item["source_checksum_sha256"],
                source_index[item["source_id"]]["checksum"],
            )

    def test_adjudication_candidate_schema(self):
        self.assertEqual(
            self.adjudication_candidate["schema_version"],
            ADJUDICATION_CANDIDATE_SCHEMA,
        )

    def test_adjudication_has_37_decisions(self):
        self.assertEqual(
            self.adjudication_candidate["decision_count"], 37
        )

    def test_adjudication_event_order_matches_inventory(self):
        self.assertEqual(
            [
                item["event_id"]
                for item in self.adjudication_candidate["decisions"]
            ],
            [item["event_id"] for item in self.inventory["events"]],
        )

    def test_quran_explicit_events_are_assertive(self):
        quran_ids = set(self.quran["event_ids"])
        for item in self.adjudication_candidate["decisions"]:
            if item["event_id"] in quran_ids:
                self.assertEqual(
                    item["disposition"], "include_assertive"
                )

    def test_qualified_events_have_labels(self):
        for item in self.adjudication_candidate["decisions"]:
            if item["disposition"] == "include_qualified":
                self.assertTrue(item["qualification_label"])

    def test_nonqualified_events_have_no_labels(self):
        for item in self.adjudication_candidate["decisions"]:
            if item["disposition"] != "include_qualified":
                self.assertIsNone(item["qualification_label"])

    def test_editorial_decision_has_zero_evidence(self):
        item = next(
            item for item in self.adjudication_candidate["decisions"]
            if item["event_id"] == EDITORIAL_EVENT_ID
        )
        self.assertEqual(item["evidence_ids"], [])

    def test_no_orphan_evidence(self):
        referenced = {
            evidence_id
            for item in self.adjudication_candidate["decisions"]
            for evidence_id in item["evidence_ids"]
        }
        available = {
            item["evidence_id"]
            for item in self.evidence_candidate["evidence_items"]
        }
        self.assertEqual(referenced, available)

    def test_candidate_contract_validation(self):
        validate_candidates(
            source_candidate=self.source_candidate,
            evidence_candidate=self.evidence_candidate,
            adjudication_candidate=self.adjudication_candidate,
        )

    def test_approval_request_schema(self):
        self.assertEqual(
            self.approval_request["schema_version"],
            APPROVAL_REQUEST_SCHEMA,
        )

    def test_approval_request_exact_phrase(self):
        self.assertEqual(
            self.approval_request["exact_approval_phrase"],
            APPROVAL_PHRASE,
        )

    def test_approval_phrase_hash(self):
        self.assertEqual(
            self.approval_request[
                "exact_approval_phrase_sha256"
            ],
            text_sha256(APPROVAL_PHRASE),
        )

    def test_approval_request_has_candidate_fingerprints(self):
        for key in (
            "source_package_input_fingerprint",
            "evidence_candidate_fingerprint",
            "adjudication_candidate_fingerprint",
        ):
            self.assertEqual(len(self.approval_request[key]), 64)

    def test_approval_request_is_not_approved(self):
        self.assertFalse(self.approval_request["human_approval"])

    def test_global_guards(self):
        for artifact in (
            self.editorial,
            self.integration,
            self.source_candidate,
            self.evidence_candidate,
            self.adjudication_candidate,
            self.approval_request,
        ):
            self.assertFalse(artifact["opens_evidence_gate"])
            self.assertEqual(
                artifact["evidence_gate_status"], GATE
            )
            self.assertEqual(
                artifact["automatic_evidence_approval"],
                AUTO_APPROVAL,
            )
            self.assertEqual(
                artifact["live_provider_execution"],
                LIVE_EXECUTION,
            )

    def test_deterministic_integration(self):
        second = build_integration(
            inventory=self.inventory,
            quran_candidate=self.quran,
            external_scope=self.external_scope,
            gap_approval=self.gap,
            editorial_decision=self.editorial,
        )
        self.assertEqual(self.integration, second)

    def test_deterministic_candidates(self):
        second = build_candidates(
            integration=self.integration,
            quran_candidate=self.quran,
            external_scope=self.external_scope,
            external_pack=self.external_pack,
            gap_approval=self.gap,
            origin_classification=self.origin,
            editorial_decision=self.editorial,
        )
        self.assertEqual(
            (
                self.source_candidate,
                self.evidence_candidate,
                self.adjudication_candidate,
            ),
            second,
        )

    def test_cli_avoids_raw_arabic_approval_phrase_on_stdout(self):
        script = (
            ROOT
            / "scripts/fast_track"
            / "build_adam_full_episode_evidence_candidate_v1.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('f"EXACT_APPROVAL_PHRASE="', script)
        self.assertIn('f"EXACT_APPROVAL_PHRASE_SHA256="', script)

    def test_cli_reports_approval_request_file(self):
        script = (
            ROOT
            / "scripts/fast_track"
            / "build_adam_full_episode_evidence_candidate_v1.py"
        ).read_text(encoding="utf-8")
        self.assertIn('f"EXACT_APPROVAL_PHRASE_FILE="', script)
        self.assertIn("outputs['approval_request']", script)

    def test_outputs_and_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                output_root=Path(tmp) / "report",
                editorial_decision=self.editorial,
                integration=self.integration,
                source_candidate=self.source_candidate,
                evidence_candidate=self.evidence_candidate,
                adjudication_candidate=self.adjudication_candidate,
                approval_request=self.approval_request,
            )
            for path in outputs.values():
                self.assertTrue(path.is_file())

    def test_json_outputs_use_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                output_root=Path(tmp) / "report",
                editorial_decision=self.editorial,
                integration=self.integration,
                source_candidate=self.source_candidate,
                evidence_candidate=self.evidence_candidate,
                adjudication_candidate=self.adjudication_candidate,
                approval_request=self.approval_request,
            )
            for key in (
                "editorial",
                "integration",
                "source_candidate",
                "evidence_candidate",
                "adjudication_candidate",
                "approval_request",
            ):
                raw = outputs[key].read_bytes()
                self.assertTrue(raw.endswith(b"\n"))
                self.assertNotIn(b"\r\n", raw)


def read_json_list(path: Path) -> list[dict]:
    import json

    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, list):
        raise AssertionError(f"Expected list: {path}")
    return value


if __name__ == "__main__":
    unittest.main()
