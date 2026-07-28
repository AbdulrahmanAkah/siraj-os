from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.quran_source_binding import (
    AUTO_APPROVAL,
    BINDING_SCHEMA,
    EXPECTED_EVENTS,
    GATE,
    LIVE_EXECUTION,
    REVIEW_SCHEMA,
    SOURCE_SCHEMA,
    STATUS,
    QuranBindingError,
    build_event_bindings,
    build_human_review_template,
    build_source_materialization,
    canonical_sha256,
    text_sha256,
    validate_event_bindings,
    validate_human_review_template,
    validate_source_materialization,
    write_json,
)

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = (
    ROOT
    / "projects/episode-001-adam/evidence/full-episode-adjudication-inventory-v1.json"
)


class QuranSourceBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = build_source_materialization()
        cls.binding = build_event_bindings(INVENTORY, cls.source)
        cls.review = build_human_review_template(cls.binding)

    def test_schemas_and_status(self):
        self.assertEqual(self.source["schema_version"], SOURCE_SCHEMA)
        self.assertEqual(self.binding["schema_version"], BINDING_SCHEMA)
        self.assertEqual(self.review["schema_version"], REVIEW_SCHEMA)
        self.assertEqual(self.source["status"], STATUS)

    def test_exact_14_source_records(self):
        self.assertEqual(self.source["source_record_count"], 14)
        self.assertEqual(len(self.source["source_records"]), 14)

    def test_exact_19_quran_events(self):
        self.assertEqual(tuple(self.binding["event_ids"]), EXPECTED_EVENTS)
        self.assertEqual(self.binding["event_count"], 19)

    def test_inventory_has_same_quran_event_set(self):
        inventory = json.loads(INVENTORY.read_text(encoding="utf-8-sig"))
        actual = tuple(
            item["event_id"]
            for item in inventory["events"]
            if item["verification_status"] == "quran_explicit"
        )
        self.assertEqual(actual, EXPECTED_EVENTS)

    def test_every_binding_has_evidence(self):
        self.assertTrue(all(item["evidence_items"] for item in self.binding["bindings"]))

    def test_only_quran_sources(self):
        self.assertTrue(all(
            item["source_type"] == "QURAN"
            and item["origin_classification"] == "QURAN_EXPLICIT"
            for item in self.source["source_records"]
        ))

    def test_no_translation_or_tafsir_materialized(self):
        provenance = self.source["provenance"]
        self.assertFalse(provenance["translation_included"])
        self.assertFalse(provenance["tafsir_included"])

    def test_anchor_checksums(self):
        for item in self.source["source_records"]:
            self.assertEqual(
                item["arabic_anchor_sha256"],
                text_sha256(item["arabic_anchor_text"]),
            )

    def test_binding_checksums_reference_sources(self):
        index = {
            item["source_record_id"]: item
            for item in self.source["source_records"]
        }
        for binding in self.binding["bindings"]:
            for evidence in binding["evidence_items"]:
                source = index[evidence["source_record_id"]]
                self.assertEqual(
                    evidence["source_materialization_sha256"],
                    canonical_sha256(source),
                )
                self.assertEqual(
                    evidence["excerpt_sha256"],
                    source["arabic_anchor_sha256"],
                )

    def test_all_proposals_are_assertive_but_unapproved(self):
        self.assertTrue(all(
            item["proposed_disposition"] == "include_assertive"
            and item["human_decision"] is False
            for item in self.binding["bindings"]
        ))

    def test_claim_scopes_are_nonempty(self):
        self.assertTrue(all(item["claim_scope"].strip() for item in self.binding["bindings"]))

    def test_excluded_scope_blocks_tafsir_and_unseen_visuals(self):
        for item in self.binding["bindings"]:
            joined = " ".join(item["excluded_scope"])
            self.assertIn("tafsir", joined)
            self.assertIn("visual reconstruction", joined)

    def test_review_template_is_blank(self):
        self.assertEqual(self.review["status"], "TEMPLATE_NOT_APPROVED")
        self.assertFalse(self.review["human_approval"])
        self.assertFalse(self.review["approved_by"])
        self.assertFalse(self.review["approved_at"])
        self.assertTrue(all(
            item["approved"] is False and item["human_decision"] is False
            for item in self.review["decisions"]
        ))

    def test_gate_and_provider_guards(self):
        for data in (self.source, self.binding, self.review):
            self.assertEqual(data["evidence_gate_status"], GATE)
            self.assertEqual(data["automatic_evidence_approval"], AUTO_APPROVAL)
            self.assertEqual(data["live_provider_execution"], LIVE_EXECUTION)

    def test_no_full_episode_completion_claim(self):
        self.assertFalse(self.binding["full_episode_adjudication_complete"])
        self.assertFalse(self.binding["binding_ready"])
        self.assertFalse(self.binding["opens_evidence_gate"])

    def test_deterministic(self):
        source = build_source_materialization()
        binding = build_event_bindings(INVENTORY, source)
        review = build_human_review_template(binding)
        self.assertEqual(canonical_sha256(source), canonical_sha256(self.source))
        self.assertEqual(canonical_sha256(binding), canonical_sha256(self.binding))
        self.assertEqual(canonical_sha256(review), canonical_sha256(self.review))

    def test_rejects_modified_anchor_checksum(self):
        changed = copy.deepcopy(self.source)
        changed["source_records"][0]["arabic_anchor_text"] += "x"
        with self.assertRaises(QuranBindingError):
            validate_source_materialization(changed)

    def test_rejects_extra_event(self):
        changed = copy.deepcopy(self.binding)
        changed["event_ids"].append("EV-ADAM-099")
        with self.assertRaises(QuranBindingError):
            validate_event_bindings(changed, self.source)

    def test_rejects_preapproved_review(self):
        changed = copy.deepcopy(self.review)
        changed["decisions"][0]["approved"] = True
        with self.assertRaises(QuranBindingError):
            validate_human_review_template(changed)

    def test_json_writer_is_utf8_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.json"
            write_json(path, self.binding)
            raw = path.read_bytes()
            self.assertNotIn(b"\r\n", raw)
            self.assertTrue(raw.endswith(b"\n"))
            json.loads(raw.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
