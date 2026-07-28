from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.delegated_source_review_ingestion import (
    AUDIT_SCHEMA,
    AUTO_APPROVAL,
    BINDING_SCHEMA,
    DECISION_SCHEMA,
    DELEGATION_SCHEMA,
    ESCALATION_SCHEMA,
    GATE,
    INGESTION_SCHEMA,
    LIVE_EXECUTION,
    USER_ESCALATION_SOURCE_IDS,
    build_binding_candidate,
    build_escalation_queue,
    build_ingestion,
    file_sha256,
    normalized_json_document_sha256,
    read_json,
    validate_delegation_policy,
    validate_external_pack,
    validate_human_review_document,
    validate_normalization_audit,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "projects/episode-001-adam/evidence"
DECISION = EVIDENCE / "source-review-human-decision-v1.json"
DELEGATION = EVIDENCE / "delegated-evidence-review-policy-v1.json"
AUDIT = EVIDENCE / "source-review-normalization-audit-v1.json"
EXTERNAL = EVIDENCE / "external-event-source-candidate-pack-v1.json"


class DelegatedSourceReviewIngestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decision = read_json(DECISION)
        cls.delegation = read_json(DELEGATION)
        cls.audit = read_json(AUDIT)
        cls.external = read_json(EXTERNAL)
        validate_human_review_document(cls.decision)
        validate_delegation_policy(cls.delegation)
        validate_normalization_audit(
            cls.audit,
            decision_sha256=normalized_json_document_sha256(
                cls.decision
            ),
        )
        validate_external_pack(cls.external)
        cls.ingestion = build_ingestion(
            decision=cls.decision,
            delegation=cls.delegation,
            audit=cls.audit,
            external_pack=cls.external,
        )
        cls.binding = build_binding_candidate(
            decision=cls.decision,
            external_pack=cls.external,
            ingestion=cls.ingestion,
        )
        cls.escalation = build_escalation_queue(
            decision=cls.decision,
            external_pack=cls.external,
            ingestion=cls.ingestion,
        )

    def test_decision_schema(self):
        self.assertEqual(
            self.decision["schema_version"], DECISION_SCHEMA
        )

    def test_delegation_schema(self):
        self.assertEqual(
            self.delegation["schema_version"], DELEGATION_SCHEMA
        )

    def test_audit_schema(self):
        self.assertEqual(self.audit["schema_version"], AUDIT_SCHEMA)

    def test_human_review_is_approved(self):
        self.assertTrue(self.decision["human_approval"])
        self.assertTrue(self.decision["human_comparison_complete"])
        self.assertTrue(self.decision["source_verification_complete"])

    def test_exact_22_unique_sources(self):
        records = self.decision["decisions"]
        ids = [item["source_candidate_id"] for item in records]
        self.assertEqual(len(ids), 22)
        self.assertEqual(len(set(ids)), 22)

    def test_exact_source_kind_counts(self):
        kinds = [item["source_kind"] for item in self.decision["decisions"]]
        self.assertEqual(
            sum(kind.startswith("QURAN") for kind in kinds), 11
        )
        self.assertEqual(
            sum(kind == "HADITH_COLLECTION_RECORD" for kind in kinds),
            11,
        )

    def test_exact_decision_counts(self):
        counts = {}
        for item in self.decision["decisions"]:
            counts[item["decision"]] = counts.get(item["decision"], 0) + 1
        self.assertEqual(
            counts,
            {
                "confirm_with_correction": 1,
                "defer_authentication": 21,
            },
        )

    def test_all_excerpt_hashes(self):
        for item in self.decision["decisions"]:
            expected = hashlib.sha256(
                item["approved_exact_excerpt"].encode("utf-8")
            ).hexdigest()
            self.assertEqual(
                item["approved_exact_excerpt_sha256"], expected
            )

    def test_authentication_and_binding_remain_false(self):
        for item in self.decision["decisions"]:
            self.assertFalse(item["authentication_verified"])
            self.assertFalse(item["origin_classification_verified"])
            self.assertFalse(item["approved_for_event_binding"])

    def test_audit_rejects_ten_incompatible_normalizations(self):
        self.assertEqual(self.audit["status"], "PASS")
        self.assertEqual(self.audit["normalizations_applied"], 0)
        self.assertEqual(self.audit["rejected_normalizations"], 10)
        self.assertEqual(self.audit["validation_issues"], [])

    def test_audit_matches_normalized_decision_document(self):
        self.assertEqual(
            self.audit["output_sha256"],
            normalized_json_document_sha256(self.decision),
        )

    def test_normalized_hash_ignores_lf_vs_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lf = root / "lf.json"
            crlf = root / "crlf.json"
            payload = (
                json.dumps(
                    self.decision,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            lf.write_bytes(payload.encode("utf-8"))
            crlf.write_bytes(
                payload.replace("\n", "\r\n").encode("utf-8")
            )
            self.assertNotEqual(file_sha256(lf), file_sha256(crlf))
            self.assertEqual(
                normalized_json_document_sha256(read_json(lf)),
                normalized_json_document_sha256(read_json(crlf)),
            )

    def test_normalized_hash_matches_original_audit_hash(self):
        self.assertEqual(
            normalized_json_document_sha256(self.decision),
            "c9399ee483169c18b0421cbe6ecbe1e92b8d329e6c233b77782536d3c9d036e3",
        )

    def test_delegation_scope(self):
        scope = self.delegation["delegation_scope"]
        self.assertEqual(
            scope["routine_evidence"], "AI_DECISION_AUTHORIZED"
        )
        self.assertEqual(
            scope["complex_or_high_importance_evidence"],
            "USER_REVIEW_REQUIRED",
        )

    def test_ingestion_schema_and_counts(self):
        self.assertEqual(
            self.ingestion["schema_version"], INGESTION_SCHEMA
        )
        self.assertEqual(self.ingestion["source_count"], 22)
        self.assertEqual(self.ingestion["quran_source_count"], 11)
        self.assertEqual(self.ingestion["hadith_source_count"], 11)

    def test_ingestion_marks_text_locator_complete(self):
        self.assertTrue(
            self.ingestion[
                "source_text_locator_verification_complete"
            ]
        )
        self.assertFalse(
            self.ingestion["source_authentication_complete"]
        )

    def test_ingestion_records_cover_event_links(self):
        linked = sum(
            len(item["event_ids"])
            for item in self.ingestion["records"]
        )
        self.assertEqual(linked, 28)

    def test_binding_schema_and_quran_count(self):
        self.assertEqual(
            self.binding["schema_version"], BINDING_SCHEMA
        )
        self.assertEqual(self.binding["source_count"], 11)

    def test_binding_never_approves_event(self):
        self.assertFalse(self.binding["event_binding_complete"])
        self.assertTrue(all(
            not item["event_binding_approved"]
            for item in self.binding["sources"]
        ))
        self.assertTrue(all(
            not item["event_binding_approved"]
            for item in self.binding["events"]
        ))

    def test_escalation_schema_and_hadith_count(self):
        self.assertEqual(
            self.escalation["schema_version"], ESCALATION_SCHEMA
        )
        self.assertEqual(self.escalation["hadith_source_count"], 11)

    def test_exact_user_escalation_sources(self):
        selected = {
            item["source_candidate_id"]
            for item in self.escalation["source_items"]
            if item["route"] == "USER_REVIEW_REQUIRED_HIGH_IMPORTANCE"
        }
        self.assertEqual(selected, set(USER_ESCALATION_SOURCE_IDS))

    def test_ai_delegated_hadith_count(self):
        self.assertEqual(
            self.escalation["ai_delegated_source_count"], 8
        )
        self.assertEqual(
            self.escalation["user_escalation_source_count"], 3
        )

    def test_external_event_counts(self):
        self.assertEqual(self.external["event_count"], 14)
        self.assertEqual(self.external["event_source_link_count"], 28)

    def test_global_guards(self):
        for artifact in (
            self.ingestion,
            self.binding,
            self.escalation,
        ):
            self.assertFalse(artifact["opens_evidence_gate"])
            self.assertEqual(artifact["evidence_gate_status"], GATE)
            self.assertEqual(
                artifact["automatic_evidence_approval"], AUTO_APPROVAL
            )
            self.assertEqual(
                artifact["live_provider_execution"], LIVE_EXECUTION
            )

    def test_outputs_are_deterministic(self):
        one = build_ingestion(
            decision=self.decision,
            delegation=self.delegation,
            audit=self.audit,
            external_pack=self.external,
        )
        two = build_ingestion(
            decision=self.decision,
            delegation=self.delegation,
            audit=self.audit,
            external_pack=self.external,
        )
        self.assertEqual(one, two)

    def test_write_outputs_and_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                output_root=Path(tmp) / "report",
                ingestion=self.ingestion,
                binding=self.binding,
                escalation=self.escalation,
            )
            self.assertTrue(outputs["archive"].is_file())
            for key in ("ingestion", "binding", "escalation"):
                raw = outputs[key].read_bytes()
                self.assertTrue(raw.endswith(b"\n"))
                self.assertNotIn(b"\r\n", raw)


if __name__ == "__main__":
    unittest.main()
