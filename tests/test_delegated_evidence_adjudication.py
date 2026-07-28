from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.delegated_evidence_adjudication import (
    AUTO_APPROVAL,
    COMPLEX_EVENT_IDS,
    DOSSIER_SCHEMA,
    EVENT_SCOPE_SCHEMA,
    EXPECTED_COMPLEX_EVENT_COUNT,
    EXPECTED_DELEGATED_SOURCE_COUNT,
    EXPECTED_EVENT_COUNT,
    EXPECTED_HIGH_IMPORTANCE_SOURCE_COUNT,
    EXPECTED_ROUTINE_EVENT_COUNT,
    EXPECTED_SOURCE_COUNT,
    GATE,
    HIGH_IMPORTANCE_SOURCE_IDS,
    LIVE_EXECUTION,
    RESEARCH_SCHEMA,
    ROUTINE_EVENT_IDS,
    ROUTINE_SOURCE_IDS,
    build_event_scope_adjudication,
    build_hadith_research,
    build_high_importance_dossier,
    read_json,
    validate_inputs,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "projects/episode-001-adam/evidence"


class DelegatedEvidenceAdjudicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ingestion = read_json(
            EVIDENCE / "source-review-ingestion-v1.json"
        )
        cls.queue = read_json(
            EVIDENCE / "delegated-evidence-escalation-queue-v1.json"
        )
        cls.external = read_json(
            EVIDENCE / "external-event-source-candidate-pack-v1.json"
        )
        cls.decision = read_json(
            EVIDENCE / "source-review-human-decision-v1.json"
        )
        cls.delegation = read_json(
            EVIDENCE / "delegated-evidence-review-policy-v1.json"
        )
        validate_inputs(
            ingestion=cls.ingestion,
            queue=cls.queue,
            external_pack=cls.external,
            decision=cls.decision,
            delegation=cls.delegation,
        )
        cls.research = build_hadith_research(
            ingestion=cls.ingestion,
            queue=cls.queue,
        )
        cls.event_scope = build_event_scope_adjudication(
            ingestion=cls.ingestion,
            external_pack=cls.external,
            research=cls.research,
        )
        cls.dossier = build_high_importance_dossier(
            ingestion=cls.ingestion,
            research=cls.research,
            event_scope=cls.event_scope,
        )

    def test_research_schema(self):
        self.assertEqual(
            self.research["schema_version"], RESEARCH_SCHEMA
        )

    def test_research_source_count(self):
        self.assertEqual(
            self.research["source_count"], EXPECTED_SOURCE_COUNT
        )

    def test_exact_routine_source_set(self):
        selected = {
            item["source_candidate_id"]
            for item in self.research["records"]
            if item["delegated_ai_decision"]
        }
        self.assertEqual(selected, set(ROUTINE_SOURCE_IDS))

    def test_exact_high_importance_source_set(self):
        selected = {
            item["source_candidate_id"]
            for item in self.research["records"]
            if item["final_user_review_required"]
        }
        self.assertEqual(
            selected, set(HIGH_IMPORTANCE_SOURCE_IDS)
        )

    def test_delegated_source_count(self):
        self.assertEqual(
            self.research["delegated_source_count"],
            EXPECTED_DELEGATED_SOURCE_COUNT,
        )

    def test_high_importance_source_count(self):
        self.assertEqual(
            self.research["high_importance_source_count"],
            EXPECTED_HIGH_IMPORTANCE_SOURCE_COUNT,
        )

    def test_all_source_research_complete(self):
        self.assertEqual(
            self.research["research_complete_count"],
            EXPECTED_SOURCE_COUNT,
        )

    def test_eight_authentication_acceptances(self):
        self.assertEqual(
            self.research[
                "delegated_authentication_accepted_count"
            ],
            EXPECTED_DELEGATED_SOURCE_COUNT,
        )

    def test_bukhari_records_are_sahih_by_collection(self):
        records = {
            item["source_candidate_id"]: item
            for item in self.research["records"]
        }
        for source_id in (
            "SRC-BUKHARI-3191",
            "SRC-BUKHARI-3326",
            "SRC-BUKHARI-3331",
        ):
            self.assertEqual(
                records[source_id]["authentication_result"],
                "SAHIH_BY_COLLECTION",
            )

    def test_muslim_routine_records_are_sahih_by_collection(self):
        records = {
            item["source_candidate_id"]: item
            for item in self.research["records"]
        }
        for source_id in (
            "SRC-MUSLIM-1468A",
            "SRC-MUSLIM-2611A",
            "SRC-MUSLIM-2653B",
            "SRC-MUSLIM-2996",
        ):
            self.assertEqual(
                records[source_id]["authentication_result"],
                "SAHIH_BY_COLLECTION",
            )

    def test_tirmidhi_3076_has_dual_grade_note(self):
        record = next(
            item for item in self.research["records"]
            if item["source_candidate_id"] == "SRC-TIRMIDHI-3076"
        )
        self.assertIn(
            "HASAN_SAHIH_BY_AL_TIRMIDHI",
            record["authentication_result"],
        )
        self.assertIn(
            "HASAN_BY_DARUSSALAM",
            record["authentication_result"],
        )

    def test_all_records_are_marfu(self):
        self.assertTrue(all(
            item["origin_classification"]
            == "MARFU_PROPHETIC_HADITH"
            for item in self.research["records"]
        ))

    def test_high_importance_not_auto_accepted(self):
        self.assertTrue(all(
            not item["delegated_authentication_accepted"]
            for item in self.research["records"]
            if item["source_candidate_id"]
            in HIGH_IMPORTANCE_SOURCE_IDS
        ))

    def test_event_scope_schema(self):
        self.assertEqual(
            self.event_scope["schema_version"], EVENT_SCOPE_SCHEMA
        )

    def test_event_scope_total_count(self):
        self.assertEqual(
            self.event_scope["event_count"], EXPECTED_EVENT_COUNT
        )

    def test_routine_event_count(self):
        self.assertEqual(
            self.event_scope["routine_event_count"],
            EXPECTED_ROUTINE_EVENT_COUNT,
        )

    def test_complex_event_count(self):
        self.assertEqual(
            self.event_scope["complex_event_count"],
            EXPECTED_COMPLEX_EVENT_COUNT,
        )

    def test_exact_routine_event_set(self):
        selected = {
            item["event_id"]
            for item in self.event_scope["events"]
            if item["delegated_ai_event_scope_approved"]
        }
        self.assertEqual(selected, set(ROUTINE_EVENT_IDS))

    def test_exact_complex_event_set(self):
        selected = {
            item["event_id"]
            for item in self.event_scope["events"]
            if item["final_user_review_required"]
        }
        self.assertEqual(selected, set(COMPLEX_EVENT_IDS))

    def test_event_032_uses_bukhari_without_muslim_2841(self):
        item = next(
            event for event in self.event_scope["events"]
            if event["event_id"] == "EV-ADAM-032"
        )
        self.assertIn(
            "SRC-BUKHARI-3326",
            item["effective_source_candidate_ids"],
        )
        self.assertNotIn(
            "SRC-MUSLIM-2841",
            item["effective_source_candidate_ids"],
        )

    def test_event_033_uses_bukhari_without_muslim_2841(self):
        item = next(
            event for event in self.event_scope["events"]
            if event["event_id"] == "EV-ADAM-033"
        )
        self.assertIn(
            "SRC-BUKHARI-3326",
            item["effective_source_candidate_ids"],
        )
        self.assertNotIn(
            "SRC-MUSLIM-2841",
            item["effective_source_candidate_ids"],
        )

    def test_event_003_remains_pending(self):
        item = next(
            event for event in self.event_scope["events"]
            if event["event_id"] == "EV-ADAM-003"
        )
        self.assertFalse(
            item["delegated_ai_event_scope_approved"]
        )
        self.assertTrue(item["final_user_review_required"])

    def test_event_060_is_routine(self):
        item = next(
            event for event in self.event_scope["events"]
            if event["event_id"] == "EV-ADAM-060"
        )
        self.assertTrue(
            item["delegated_ai_event_scope_approved"]
        )

    def test_dossier_schema(self):
        self.assertEqual(
            self.dossier["schema_version"], DOSSIER_SCHEMA
        )

    def test_dossier_source_count(self):
        self.assertEqual(
            self.dossier["source_item_count"],
            EXPECTED_HIGH_IMPORTANCE_SOURCE_COUNT,
        )

    def test_dossier_event_count(self):
        self.assertEqual(
            self.dossier["event_item_count"],
            EXPECTED_COMPLEX_EVENT_COUNT,
        )

    def test_dossier_research_and_recommendations_complete(self):
        self.assertTrue(self.dossier["research_complete"])
        self.assertTrue(self.dossier["recommendations_complete"])
        self.assertFalse(
            self.dossier["final_user_decisions_complete"]
        )

    def test_global_guards(self):
        for artifact in (
            self.research,
            self.event_scope,
            self.dossier,
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

    def test_deterministic_builders(self):
        second = build_hadith_research(
            ingestion=self.ingestion,
            queue=self.queue,
        )
        self.assertEqual(self.research, second)

    def test_output_files_and_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                output_root=Path(tmp) / "report",
                research=self.research,
                event_scope=self.event_scope,
                dossier=self.dossier,
            )
            for key in (
                "research",
                "event_scope",
                "dossier",
                "summary",
                "readme",
                "archive",
            ):
                self.assertTrue(outputs[key].is_file())

    def test_json_outputs_use_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                output_root=Path(tmp) / "report",
                research=self.research,
                event_scope=self.event_scope,
                dossier=self.dossier,
            )
            for key in ("research", "event_scope", "dossier"):
                raw = outputs[key].read_bytes()
                self.assertTrue(raw.endswith(b"\n"))
                self.assertNotIn(b"\r\n", raw)


if __name__ == "__main__":
    unittest.main()
