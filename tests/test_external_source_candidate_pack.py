from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.external_source_candidate_pack import (
    AUTO_APPROVAL,
    CATALOG_SCHEMA,
    FACTUAL_EVENTS,
    GATE,
    LIVE_EXECUTION,
    MATCH_SCHEMA,
    PACK_SCHEMA,
    POLICY_SCHEMA,
    RECORD_SCHEMA,
    REVIEW_SCHEMA,
    ExternalSourceCandidateError,
    _candidate_match_score,
    build_auto_match_ledger,
    build_candidate_records,
    build_catalog,
    build_event_pack,
    build_policy,
    build_review_template,
    canonical_sha256,
    text_sha256,
    validate_candidate_record,
    validate_catalog,
    validate_event_pack,
    validate_match_ledger,
    validate_policy,
    validate_review_template,
    write_local_outputs,
)

ROOT = Path(__file__).resolve().parents[1]


class ExternalSourceCandidatePackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = build_policy()
        cls.catalog = build_catalog(cls.policy)
        cls.pack = build_event_pack(cls.catalog, cls.policy)
        cls.review = build_review_template(cls.pack, cls.policy)
        cls.records = build_candidate_records(
            cls.pack, cls.catalog, cls.policy
        )

    def test_policy_schema(self):
        self.assertEqual(self.policy["schema_version"], POLICY_SCHEMA)

    def test_policy_forbids_automatic_hadith_grading(self):
        self.assertIn(
            "automatic hadith grading", self.policy["prohibitions"]
        )

    def test_catalog_schema(self):
        self.assertEqual(self.catalog["schema_version"], CATALOG_SCHEMA)

    def test_exact_22_source_candidates(self):
        self.assertEqual(self.catalog["source_candidate_count"], 22)

    def test_exact_quran_and_hadith_counts(self):
        self.assertEqual(self.catalog["quran_candidate_count"], 11)
        self.assertEqual(self.catalog["hadith_candidate_count"], 11)

    def test_source_candidate_ids_unique(self):
        ids = [
            item["source_candidate_id"]
            for item in self.catalog["source_candidates"]
        ]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_anchor_checksums(self):
        for item in self.catalog["source_candidates"]:
            self.assertEqual(
                item["arabic_anchor_sha256"],
                text_sha256(item["arabic_anchor_text"]),
            )

    def test_no_source_candidate_is_verified(self):
        for item in self.catalog["source_candidates"]:
            self.assertFalse(item["human_compared_to_source"])
            self.assertFalse(item["source_verified"])
            self.assertFalse(item["authentication_verified"])
            self.assertFalse(item["origin_classification_verified"])
            self.assertFalse(item["approved_for_event_binding"])

    def test_remote_source_hashes_are_blank(self):
        self.assertTrue(all(
            not item["source_material_sha256"]
            for item in self.catalog["source_candidates"]
        ))

    def test_pack_schema(self):
        self.assertEqual(self.pack["schema_version"], PACK_SCHEMA)

    def test_exact_14_event_coverage(self):
        self.assertEqual(tuple(self.pack["event_ids"]), FACTUAL_EVENTS)
        self.assertEqual(self.pack["event_count"], 14)

    def test_exact_28_event_source_links(self):
        self.assertEqual(self.pack["event_source_link_count"], 28)

    def test_disposition_counts(self):
        self.assertEqual(
            self.pack["proposed_disposition_counts"],
            {"include_assertive": 8, "include_qualified": 6},
        )

    def test_every_event_has_claim_layers(self):
        self.assertTrue(all(
            event["claim_layers"] for event in self.pack["events"]
        ))

    def test_every_event_has_scope_limitations(self):
        self.assertTrue(all(
            event["scope_limitations"] for event in self.pack["events"]
        ))

    def test_no_event_is_approved(self):
        for event in self.pack["events"]:
            self.assertFalse(event["human_decision"])
            self.assertFalse(event["event_approved"])
            self.assertFalse(event["source_verification_complete"])
            self.assertFalse(event["binding_ready"])

    def test_pen_event_is_qualified(self):
        event = next(
            item for item in self.pack["events"]
            if item["event_id"] == "EV-ADAM-003"
        )
        self.assertEqual(event["proposed_disposition"], "include_qualified")
        treatments = {
            layer["treatment"] for layer in event["claim_layers"]
        }
        self.assertIn(
            "chronology_interpretation_review_required", treatments
        )

    def test_iblis_preexistence_is_synthesis(self):
        event = next(
            item for item in self.pack["events"]
            if item["event_id"] == "EV-ADAM-007"
        )
        self.assertTrue(any(
            layer["treatment"]
            == "supported_synthesis_human_review_required"
            for layer in event["claim_layers"]
        ))

    def test_clay_sequence_is_interpretive(self):
        event = next(
            item for item in self.pack["events"]
            if item["event_id"] == "EV-ADAM-021"
        )
        self.assertTrue(any(
            layer["treatment"]
            == "scholarly_interpretation_review_required"
            for layer in event["claim_layers"]
        ))

    def test_spouse_event_excludes_left_rib(self):
        event = next(
            item for item in self.pack["events"]
            if item["event_id"] == "EV-ADAM-070"
        )
        self.assertTrue(any(
            "الضلع الأيسر" in value
            for value in event["scope_limitations"]
        ))

    def test_review_schema(self):
        self.assertEqual(self.review["schema_version"], REVIEW_SCHEMA)

    def test_review_template_is_blank(self):
        self.assertTrue(all(
            not item["approved_source_candidate_ids"]
            and not item["rejected_source_candidate_ids"]
            and not item["source_verification_complete"]
            and not item["approved"]
            and not item["human_decision"]
            for item in self.review["decisions"]
        ))

    def test_exact_28_candidate_records(self):
        self.assertEqual(len(self.records), 28)

    def test_candidate_record_schema_and_blank_fields(self):
        for record in self.records.values():
            self.assertEqual(record["schema_version"], RECORD_SCHEMA)
            self.assertFalse(record["exact_excerpt"])
            self.assertFalse(record["source_material_sha256"])
            self.assertFalse(record["source_verified"])
            self.assertEqual(record["origin_classification"], "unresolved")

    def test_catalog_is_deterministic(self):
        self.assertEqual(
            canonical_sha256(build_catalog(self.policy)),
            canonical_sha256(self.catalog),
        )

    def test_pack_is_deterministic(self):
        catalog = build_catalog(self.policy)
        self.assertEqual(
            canonical_sha256(build_event_pack(catalog, self.policy)),
            canonical_sha256(self.pack),
        )

    def test_match_score_source_number_and_alias(self):
        source = next(
            item for item in self.catalog["source_candidates"]
            if item["source_candidate_id"] == "SRC-BUKHARI-3191"
        )
        local = {
            "detected_numbers": ["3191"],
            "detected_source_names": ["صحيح البخاري"],
            "candidate_excerpt": "صحيح البخاري 3191",
        }
        score, reasons = _candidate_match_score(local, source)
        self.assertGreaterEqual(score, 100)
        self.assertIn("record_number_match", reasons)

    def test_match_score_event_scope_only(self):
        source = next(
            item for item in self.catalog["source_candidates"]
            if item["source_candidate_id"] == "SRC-BUKHARI-3191"
        )
        score, reasons = _candidate_match_score({
            "detected_numbers": [],
            "detected_source_names": [],
            "candidate_excerpt": "ملاحظة عامة",
        }, source)
        self.assertEqual(score, 0)
        self.assertFalse(reasons)

    def test_validation_rejects_verified_catalog_item(self):
        changed = copy.deepcopy(self.catalog)
        changed["source_candidates"][0]["source_verified"] = True
        with self.assertRaises(ExternalSourceCandidateError):
            validate_catalog(changed)

    def test_validation_rejects_event_approval(self):
        changed = copy.deepcopy(self.pack)
        changed["events"][0]["event_approved"] = True
        with self.assertRaises(ExternalSourceCandidateError):
            validate_event_pack(changed, self.catalog)

    def test_validation_rejects_review_preapproval(self):
        changed = copy.deepcopy(self.review)
        changed["decisions"][0]["approved"] = True
        with self.assertRaises(ExternalSourceCandidateError):
            validate_review_template(changed)

    def test_validation_rejects_prefilled_exact_excerpt(self):
        record = copy.deepcopy(next(iter(self.records.values())))
        record["exact_excerpt"] = "prefilled"
        with self.assertRaises(ExternalSourceCandidateError):
            validate_candidate_record(record)

    def test_global_guards(self):
        for data in (
            self.policy, self.catalog, self.pack, self.review
        ):
            self.assertEqual(data["evidence_gate_status"], GATE)
            self.assertEqual(
                data["automatic_evidence_approval"], AUTO_APPROVAL
            )
            self.assertEqual(
                data["live_provider_execution"], LIVE_EXECUTION
            )

    def test_write_outputs_with_synthetic_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            execution_root = root / "execution"
            record_root = execution_root / "verification-records/EV-ADAM-001"
            record_root.mkdir(parents=True)
            local_record = {
                "schema_version": "siraj-source-verification-record-template-v1",
                "record_template_id": "local-1",
                "event_id": "EV-ADAM-001",
                "candidate_id": "candidate-1",
                "candidate_path": "evidence/a.md",
                "candidate_excerpt": "صحيح البخاري 3191",
                "candidate_excerpt_sha256": text_sha256(
                    "صحيح البخاري 3191"
                ),
                "detected_numbers": ["3191"],
                "detected_source_names": ["صحيح البخاري"],
            }
            (record_root / "local-1.json").write_text(
                json.dumps(local_record, ensure_ascii=False),
                encoding="utf-8",
            )
            execution = {
                "schema_version": (
                    "siraj-non-quran-source-verification-execution-v1"
                ),
                "execution_id": "synthetic",
                "record_template_count": 1,
            }
            (execution_root / "source-verification-execution-v1.json").write_text(
                json.dumps(execution), encoding="utf-8"
            )
            ledger = build_auto_match_ledger(
                execution_report_root=execution_root,
                pack=self.pack,
                catalog=self.catalog,
            )
            self.assertEqual(ledger["schema_version"], MATCH_SCHEMA)
            self.assertEqual(ledger["local_record_count"], 1)
            self.assertEqual(
                ledger["matches"][0]["confidence"], "HIGH"
            )
            outputs = write_local_outputs(
                output_root=root / "report",
                catalog=self.catalog,
                pack=self.pack,
                policy=self.policy,
                review=self.review,
                candidate_records=self.records,
                match_ledger=ledger,
            )
            self.assertTrue(outputs["archive"].is_file())
            self.assertEqual(
                len(list((root / "report/event-dossiers").glob("*.md"))),
                14,
            )
            self.assertEqual(
                len(list((root / "report/candidate-records").rglob("*.json"))),
                28,
            )

    def test_json_outputs_use_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            from src.application.storyboard_runtime.external_source_candidate_pack import write_json
            path = Path(tmp) / "catalog.json"
            write_json(path, self.catalog)
            raw = path.read_bytes()
            self.assertNotIn(b"\r\n", raw)
            self.assertTrue(raw.endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
