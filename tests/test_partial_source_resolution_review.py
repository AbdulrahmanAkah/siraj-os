from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.partial_source_resolution_review import (
    ALLOWED_HUMAN_DECISIONS,
    AUTO_APPROVAL,
    DECISION_SCHEMA,
    DOCKET_SCHEMA,
    EVENT_SCHEMA,
    GATE,
    LIVE_EXECUTION,
    NOTEBOOKLM_SCHEMA,
    POLICY_SCHEMA,
    READY,
    REFINED_READY,
    RESOLUTION_REQUIRED,
    RESOLUTION_SCHEMA,
    PartialSourceResolutionError,
    build_decision_template,
    build_human_approval_text,
    build_policy,
    build_resolution_and_docket,
    canonical_sha256,
    char_ngram_jaccard,
    enhanced_resolution_metrics,
    fuzzy_token_alignment,
    normalize_arabic,
    refined_readiness,
    soft_stem,
    text_sha256,
    token_equivalence_score,
    validate_decision_template,
    validate_docket,
    validate_event_readiness,
    validate_notebooklm,
    validate_policy,
    validate_resolution,
    write_local_outputs,
)


def synthetic_materialization():
    sources = []
    for index in range(22):
        anchor = f"هذا نص المصدر رقم {index} وفيه معنى ثابت"
        if index < 17:
            extracted = f"مقدمة {anchor} خاتمة"
            status = "FETCHED_EXTRACTED_ANCHOR_MATCH"
        else:
            extracted = (
                f"هذا نص للمصدر رقم {index} وفيه المعنى الثابت"
                if index < 20
                else f"كلام مختلف تماما عن المصدر {index}"
            )
            status = "FETCHED_EXTRACTED_PARTIAL_MATCH"
        sources.append({
            "source_candidate_id": f"SRC-{index:02d}",
            "source_kind": (
                "QURAN_VERSE" if index < 11
                else "HADITH_COLLECTION_RECORD"
            ),
            "locator": f"Locator {index}",
            "research_anchor_text": anchor,
            "research_anchor_sha256": text_sha256(anchor),
            "machine_extracted_text": extracted,
            "machine_extracted_text_sha256": text_sha256(extracted),
            "materialization_record_id": f"mat-{index}",
        })
    return {
        "schema_version": "siraj-remote-source-materialization-v1",
        "materialization_id": "synthetic-materialization",
        "source_count": 22,
        "status_counts": {
            "FETCHED_EXTRACTED_ANCHOR_MATCH": 17,
            "FETCHED_EXTRACTED_PARTIAL_MATCH": 5,
        },
        "sources": sources,
    }


def synthetic_packet(materialization):
    sources = []
    for index, item in enumerate(materialization["sources"]):
        readiness = (
            "READY_FOR_HUMAN_CONFIRMATION"
            if index < 17
            else "NEEDS_TARGETED_HUMAN_RESOLUTION"
        )
        sources.append({
            "source_candidate_id": item["source_candidate_id"],
            "locator": item["locator"],
            "source_kind": item["source_kind"],
            "materialization_status": (
                "FETCHED_EXTRACTED_ANCHOR_MATCH"
                if index < 17
                else "FETCHED_EXTRACTED_PARTIAL_MATCH"
            ),
            "comparison_id": f"comparison-{index}",
            "comparison_readiness": readiness,
        })
    return {
        "schema_version": "siraj-source-human-comparison-packet-v1",
        "comparison_packet_id": "synthetic-comparison",
        "source_count": 22,
        "comparison_readiness_counts": {
            "NEEDS_TARGETED_HUMAN_RESOLUTION": 5,
            "READY_FOR_HUMAN_CONFIRMATION": 17,
        },
        "sources": sources,
    }


def synthetic_comparisons(materialization, packet):
    result = {}
    for index, source in enumerate(materialization["sources"]):
        result[source["source_candidate_id"]] = {
            "schema_version": "siraj-source-text-comparison-v1",
            "source_candidate_id": source["source_candidate_id"],
            "locator": source["locator"],
            "source_kind": source["source_kind"],
            "research_anchor_text": source["research_anchor_text"],
            "research_anchor_sha256": source["research_anchor_sha256"],
            "machine_extracted_text": source["machine_extracted_text"],
            "machine_extracted_text_sha256": source[
                "machine_extracted_text_sha256"
            ],
            "comparison": {
                "window_text": source["machine_extracted_text"],
                "window_sha256": text_sha256(
                    source["machine_extracted_text"]
                ),
            },
        }
    return result


def synthetic_event_pack():
    source_ids = [f"SRC-{index:02d}" for index in range(22)]
    events = []
    cursor = 0
    for index in range(14):
        linked = [
            source_ids[cursor % 22],
            source_ids[(cursor + 1) % 22],
        ]
        cursor += 2
        events.append({
            "event_id": f"EV-ADAM-{index + 1:03d}",
            "title": f"Event {index}",
            "proposed_disposition": "include_qualified",
            "source_candidate_ids": linked,
        })
    return {
        "schema_version": (
            "siraj-external-event-source-candidate-pack-v1"
        ),
        "pack_id": "synthetic-event-pack",
        "event_count": 14,
        "event_source_link_count": 28,
        "events": events,
    }


class PartialSourceResolutionReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.materialization = synthetic_materialization()
        cls.packet = synthetic_packet(cls.materialization)
        cls.comparisons = synthetic_comparisons(
            cls.materialization, cls.packet
        )
        cls.events = synthetic_event_pack()
        cls.policy = build_policy()
        (
            cls.resolution,
            cls.docket,
            cls.event_readiness,
            cls.notebook,
        ) = build_resolution_and_docket(
            materialization=cls.materialization,
            comparison_packet=cls.packet,
            comparisons=cls.comparisons,
            event_pack=cls.events,
            policy=cls.policy,
        )
        cls.decision = build_decision_template(
            docket=cls.docket,
            policy=cls.policy,
        )

    def test_normalize_arabic(self):
        self.assertEqual(
            normalize_arabic("إِنَّ آدَمَ"),
            normalize_arabic("ان ادم"),
        )

    def test_soft_stem_article(self):
        self.assertEqual(soft_stem("المصدر"), "مصدر")

    def test_soft_stem_conjunction(self):
        self.assertEqual(soft_stem("والمصدر"), "مصدر")

    def test_token_exact_equivalence(self):
        self.assertEqual(
            token_equivalence_score("آدم", "ادم"), 1.0
        )

    def test_token_soft_equivalence(self):
        self.assertGreaterEqual(
            token_equivalence_score("والمصدر", "مصدر"), 0.9
        )

    def test_char_ngram_identical(self):
        self.assertEqual(
            char_ngram_jaccard("خلق آدم", "خلق آدم"), 1.0
        )

    def test_fuzzy_alignment_exact(self):
        result = fuzzy_token_alignment(
            "خلق آدم من طين", "خلق ادم من الطين"
        )
        self.assertEqual(result["fuzzy_token_recall"], 1.0)

    def test_fuzzy_alignment_partial(self):
        result = fuzzy_token_alignment(
            "خلق آدم من طين", "خلق ادم"
        )
        self.assertEqual(result["fuzzy_token_recall"], 0.5)

    def test_enhanced_metrics_has_weighted_score(self):
        result = enhanced_resolution_metrics(
            "خلق آدم من طين",
            "خلق ادم من الطين",
            "خلق ادم من الطين",
        )
        self.assertGreater(result["weighted_resolution_score"], 0.7)

    def test_refined_ready_preserves_ready(self):
        self.assertEqual(
            refined_readiness(
                READY, {"fuzzy_token_recall": 0}
            ),
            READY,
        )

    def test_refined_ready_from_strong_fuzzy(self):
        self.assertEqual(
            refined_readiness(
                "NEEDS_TARGETED_HUMAN_RESOLUTION",
                {
                    "fuzzy_token_recall": 0.95,
                    "matched_token_order_ratio": 1.0,
                    "weighted_resolution_score": 0.90,
                    "char_trigram_jaccard": 0.80,
                },
            ),
            REFINED_READY,
        )

    def test_resolution_required_from_weak_fuzzy(self):
        self.assertEqual(
            refined_readiness(
                "NEEDS_TARGETED_HUMAN_RESOLUTION",
                {
                    "fuzzy_token_recall": 0.4,
                    "matched_token_order_ratio": 0.5,
                    "weighted_resolution_score": 0.4,
                    "char_trigram_jaccard": 0.2,
                },
            ),
            RESOLUTION_REQUIRED,
        )

    def test_policy_schema(self):
        self.assertEqual(self.policy["schema_version"], POLICY_SCHEMA)

    def test_policy_exact_decisions(self):
        self.assertEqual(
            tuple(self.policy["allowed_human_decisions"]),
            ALLOWED_HUMAN_DECISIONS,
        )

    def test_resolution_schema(self):
        self.assertEqual(
            self.resolution["schema_version"], RESOLUTION_SCHEMA
        )

    def test_resolution_original_partial_count(self):
        self.assertEqual(
            self.resolution["original_partial_source_count"], 5
        )

    def test_resolution_covers_22_sources(self):
        self.assertEqual(self.resolution["source_count"], 22)
        self.assertEqual(len(self.resolution["records"]), 22)

    def test_docket_schema(self):
        self.assertEqual(self.docket["schema_version"], DOCKET_SCHEMA)

    def test_docket_covers_22_sources(self):
        self.assertEqual(self.docket["source_count"], 22)

    def test_event_schema_and_counts(self):
        self.assertEqual(
            self.event_readiness["schema_version"], EVENT_SCHEMA
        )
        self.assertEqual(self.event_readiness["event_count"], 14)
        self.assertEqual(
            self.event_readiness["event_source_link_count"], 28
        )

    def test_notebook_schema(self):
        self.assertEqual(
            self.notebook["schema_version"], NOTEBOOKLM_SCHEMA
        )

    def test_notebook_only_targets_unresolved(self):
        self.assertEqual(
            self.notebook["target_source_count"],
            self.resolution["remaining_resolution_source_count"],
        )

    def test_decision_schema(self):
        self.assertEqual(
            self.decision["schema_version"], DECISION_SCHEMA
        )

    def test_decision_template_blank(self):
        self.assertTrue(all(
            not item["decision"]
            and not item["approved_exact_excerpt"]
            and not item["human_decision"]
            and not item["source_verified"]
            for item in self.decision["decisions"]
        ))

    def test_human_approval_text_contains_scope(self):
        text = build_human_approval_text(
            docket=self.docket,
            decision_template=self.decision,
        )
        self.assertIn("لا يفتح بوابة الأدلة", text)
        self.assertIn(self.docket["docket_id"], text)
        self.assertEqual(text.count("decision=<"), 22)

    def test_artifacts_never_claim_completion(self):
        for data in (
            self.resolution,
            self.docket,
            self.event_readiness,
            self.notebook,
            self.decision,
        ):
            self.assertFalse(
                data.get("source_verification_complete", False)
            )
            self.assertFalse(data.get("human_approval", False))

    def test_validation_rejects_verified_docket_source(self):
        changed = copy.deepcopy(self.docket)
        changed["sources"][0]["source_verified"] = True
        with self.assertRaises(PartialSourceResolutionError):
            validate_docket(changed)

    def test_validation_rejects_decision_prefill(self):
        changed = copy.deepcopy(self.decision)
        changed["decisions"][0]["decision"] = (
            "confirm_exact_source_text"
        )
        with self.assertRaises(PartialSourceResolutionError):
            validate_decision_template(changed)

    def test_validation_rejects_open_gate(self):
        changed = copy.deepcopy(self.resolution)
        changed["evidence_gate_status"] = "OPEN"
        with self.assertRaises(PartialSourceResolutionError):
            validate_resolution(changed)

    def test_deterministic(self):
        second = build_resolution_and_docket(
            materialization=self.materialization,
            comparison_packet=self.packet,
            comparisons=self.comparisons,
            event_pack=self.events,
            policy=self.policy,
        )
        self.assertEqual(
            canonical_sha256(second[0]),
            canonical_sha256(self.resolution),
        )
        self.assertEqual(
            canonical_sha256(second[1]),
            canonical_sha256(self.docket),
        )

    def test_write_outputs(self):
        approval = build_human_approval_text(
            docket=self.docket,
            decision_template=self.decision,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "report"
            outputs = write_local_outputs(
                output_root=root,
                resolution=self.resolution,
                docket=self.docket,
                events=self.event_readiness,
                notebook=self.notebook,
                policy=self.policy,
                decision_template=self.decision,
                approval_text=approval,
            )
            self.assertTrue(outputs["archive"].is_file())
            self.assertEqual(
                len(list(
                    (root / "resolution-records").glob("*.json")
                )),
                22,
            )
            self.assertEqual(
                len(list(
                    (root / "source-review-cards").glob("*.md")
                )),
                22,
            )

    def test_json_outputs_use_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            from src.application.storyboard_runtime.partial_source_resolution_review import write_json
            write_json(path, self.policy)
            raw = path.read_bytes()
            self.assertNotIn(b"\r\n", raw)
            self.assertTrue(raw.endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
