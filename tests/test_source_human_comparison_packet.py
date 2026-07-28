from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.source_human_comparison_packet import (
    ARCHIVE_SCHEMA,
    AUTO_APPROVAL,
    DIFF_SCHEMA,
    EVENT_SCHEMA,
    GATE,
    LIVE_EXECUTION,
    PACKET_SCHEMA,
    POLICY_SCHEMA,
    READY,
    RESOLUTION,
    REVIEW_SCHEMA,
    SourceHumanComparisonError,
    best_matching_window,
    build_archive_integrity,
    build_comparison_packet,
    build_policy,
    build_review_template,
    bytes_sha256,
    canonical_sha256,
    comparison_readiness,
    normalize_arabic,
    text_sha256,
    validate_archive_integrity,
    validate_comparison_packet,
    validate_event_readiness,
    validate_policy,
    validate_review_template,
    write_local_outputs,
)


def synthetic_source(index: int, status: str):
    anchor = f"هذا نص عربي مرشح للمصدر رقم {index}"
    extracted = (
        f"مقدمة قصيرة {anchor} خاتمة"
        if status == "FETCHED_EXTRACTED_ANCHOR_MATCH"
        else f"هذا نص عربي مختلف جزئيا للمصدر {index}"
    )
    return {
        "source_candidate_id": f"SRC-{index:02d}",
        "source_kind": (
            "QURAN_VERSE" if index < 11
            else "HADITH_COLLECTION_RECORD"
        ),
        "collection": "collection",
        "locator": f"Locator {index}",
        "source_url": f"https://example.test/{index}",
        "research_anchor_text": anchor,
        "research_anchor_sha256": text_sha256(anchor),
        "materialization_status": status,
        "machine_extracted_text": extracted,
        "machine_extracted_text_sha256": text_sha256(extracted),
        "materialization_record_id": f"mat-{index}",
        "human_compared_to_source": False,
        "source_verified": False,
    }


def synthetic_materialization():
    sources = [
        synthetic_source(
            index,
            "FETCHED_EXTRACTED_ANCHOR_MATCH"
            if index < 17
            else "FETCHED_EXTRACTED_PARTIAL_MATCH",
        )
        for index in range(22)
    ]
    return {
        "schema_version": "siraj-remote-source-materialization-v1",
        "materialization_id": "synthetic-materialization",
        "fetched_source_count": 22,
        "machine_extracted_source_count": 22,
        "anchor_match_source_count": 17,
        "status_counts": {
            "FETCHED_EXTRACTED_ANCHOR_MATCH": 17,
            "FETCHED_EXTRACTED_PARTIAL_MATCH": 5,
        },
        "sources": sources,
        "source_verification_complete": False,
    }


def synthetic_event_pack():
    source_ids = [f"SRC-{index:02d}" for index in range(22)]
    events = []
    cursor = 0
    for index in range(14):
        ids = [
            source_ids[cursor % 22],
            source_ids[(cursor + 1) % 22],
        ]
        cursor += 2
        events.append({
            "event_id": f"EV-ADAM-{index + 1:03d}",
            "title": f"Event {index}",
            "proposed_disposition": "include_qualified",
            "source_candidate_ids": ids,
        })
    return {
        "schema_version": (
            "siraj-external-event-source-candidate-pack-v1"
        ),
        "pack_id": "synthetic-pack",
        "event_count": 14,
        "event_source_link_count": 28,
        "events": events,
    }


def synthetic_fetch_report(root: Path):
    raw_root = root / "raw"
    records = []
    for index in range(24):
        relative = f"raw/SRC-{index % 22:02d}/{index:02d}.html"
        data = f"raw response {index}".encode("utf-8")
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        records.append({
            "source_candidate_id": f"SRC-{index % 22:02d}",
            "requested_url": f"https://example.test/{index}",
            "final_url": f"https://example.test/{index}",
            "success": True,
            "raw_archive_path": relative,
            "response_sha256": hashlib.sha256(data).hexdigest(),
            "response_bytes_count": len(data),
        })
    return {
        "schema_version": "siraj-remote-source-fetch-manifest-v1",
        "archived_response_count": 24,
        "records": records,
    }


class SourceHumanComparisonPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.materialization = synthetic_materialization()
        cls.event_pack = synthetic_event_pack()
        cls.policy = build_policy()

    def test_normalize_arabic(self):
        self.assertEqual(
            normalize_arabic("إِنَّ آدَمَ"),
            normalize_arabic("ان ادم"),
        )

    def test_best_window_exact_anchor(self):
        result = best_matching_window(
            "كان الله ولم يكن شيء",
            "مقدمة كان الله ولم يكن شيء غيره خاتمة",
        )
        self.assertEqual(result["token_recall"], 1.0)
        self.assertIn("كان الله", result["window_text"])

    def test_best_window_partial_anchor(self):
        result = best_matching_window(
            "خلق الملائكة من نور",
            "خلقت الملائكة من النور",
        )
        self.assertGreaterEqual(result["token_recall"], 0.5)
        self.assertTrue(result["missing_anchor_tokens"])

    def test_best_window_empty_extracted(self):
        result = best_matching_window("نص", "")
        self.assertEqual(result["token_recall"], 0.0)
        self.assertFalse(result["window_text"])

    def test_ready_from_materialization_status(self):
        self.assertEqual(
            comparison_readiness(
                "FETCHED_EXTRACTED_ANCHOR_MATCH",
                {"token_recall": 0.2, "sequence_ratio": 0.2},
            ),
            READY,
        )

    def test_ready_from_enhanced_metrics(self):
        self.assertEqual(
            comparison_readiness(
                "FETCHED_EXTRACTED_PARTIAL_MATCH",
                {"token_recall": 0.9, "sequence_ratio": 0.8},
            ),
            READY,
        )

    def test_resolution_from_low_metrics(self):
        self.assertEqual(
            comparison_readiness(
                "FETCHED_EXTRACTED_PARTIAL_MATCH",
                {"token_recall": 0.4, "sequence_ratio": 0.3},
            ),
            RESOLUTION,
        )

    def test_policy_schema(self):
        self.assertEqual(self.policy["schema_version"], POLICY_SCHEMA)

    def test_policy_forbids_automatic_confirmation(self):
        self.assertIn(
            "automatic human confirmation",
            self.policy["prohibitions"],
        )

    def test_archive_integrity_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fetch = synthetic_fetch_report(root)
            integrity = build_archive_integrity(
                report_root=root,
                fetch_manifest=fetch,
            )
            self.assertEqual(integrity["schema_version"], ARCHIVE_SCHEMA)
            self.assertEqual(integrity["valid_archive_count"], 24)
            self.assertEqual(integrity["status"], "ARCHIVE_INTEGRITY_PASS")

    def test_archive_integrity_detects_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fetch = synthetic_fetch_report(root)
            (root / fetch["records"][0]["raw_archive_path"]).unlink()
            with self.assertRaises(SourceHumanComparisonError):
                build_archive_integrity(
                    report_root=root,
                    fetch_manifest=fetch,
                )

    def test_archive_integrity_detects_checksum_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fetch = synthetic_fetch_report(root)
            path = root / fetch["records"][0]["raw_archive_path"]
            path.write_bytes(b"changed")
            with self.assertRaises(SourceHumanComparisonError):
                build_archive_integrity(
                    report_root=root,
                    fetch_manifest=fetch,
                )

    def test_build_packet_covers_22_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            integrity = build_archive_integrity(
                report_root=root,
                fetch_manifest=synthetic_fetch_report(root),
            )
            packet, comparisons, events = build_comparison_packet(
                materialization=self.materialization,
                event_pack=self.event_pack,
                policy=self.policy,
                archive_integrity=integrity,
            )
            self.assertEqual(packet["schema_version"], PACKET_SCHEMA)
            self.assertEqual(packet["source_count"], 22)
            self.assertEqual(len(comparisons), 22)
            self.assertEqual(events["schema_version"], EVENT_SCHEMA)

    def test_all_comparisons_have_diff_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            integrity = build_archive_integrity(
                report_root=root,
                fetch_manifest=synthetic_fetch_report(root),
            )
            _, comparisons, _ = build_comparison_packet(
                materialization=self.materialization,
                event_pack=self.event_pack,
                policy=self.policy,
                archive_integrity=integrity,
            )
            self.assertTrue(all(
                item["schema_version"] == DIFF_SCHEMA
                for item in comparisons.values()
            ))

    def test_packet_never_claims_human_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            integrity = build_archive_integrity(
                report_root=root,
                fetch_manifest=synthetic_fetch_report(root),
            )
            packet, _, _ = build_comparison_packet(
                materialization=self.materialization,
                event_pack=self.event_pack,
                policy=self.policy,
                archive_integrity=integrity,
            )
            self.assertFalse(packet["human_comparison_complete"])
            self.assertFalse(packet["source_verification_complete"])
            self.assertFalse(packet["human_approval"])
            self.assertFalse(packet["opens_evidence_gate"])

    def test_event_readiness_covers_14_events_and_28_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            integrity = build_archive_integrity(
                report_root=root,
                fetch_manifest=synthetic_fetch_report(root),
            )
            _, _, events = build_comparison_packet(
                materialization=self.materialization,
                event_pack=self.event_pack,
                policy=self.policy,
                archive_integrity=integrity,
            )
            self.assertEqual(events["event_count"], 14)
            self.assertEqual(events["event_source_link_count"], 28)

    def test_review_template_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            integrity = build_archive_integrity(
                report_root=root,
                fetch_manifest=synthetic_fetch_report(root),
            )
            packet, comparisons, _ = build_comparison_packet(
                materialization=self.materialization,
                event_pack=self.event_pack,
                policy=self.policy,
                archive_integrity=integrity,
            )
            review = build_review_template(
                packet=packet,
                comparisons=comparisons,
            )
            self.assertEqual(review["schema_version"], REVIEW_SCHEMA)
            self.assertTrue(all(
                not item["approved_exact_excerpt"]
                and not item["source_verified"]
                and not item["human_decision"]
                for item in review["decisions"]
            ))

    def test_review_contains_suggested_window_hash_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            integrity = build_archive_integrity(
                report_root=root,
                fetch_manifest=synthetic_fetch_report(root),
            )
            packet, comparisons, _ = build_comparison_packet(
                materialization=self.materialization,
                event_pack=self.event_pack,
                policy=self.policy,
                archive_integrity=integrity,
            )
            review = build_review_template(
                packet=packet,
                comparisons=comparisons,
            )
            self.assertTrue(all(
                item["suggested_window_sha256"]
                for item in review["decisions"]
            ))

    def test_packet_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            integrity = build_archive_integrity(
                report_root=root,
                fetch_manifest=synthetic_fetch_report(root),
            )
            one = build_comparison_packet(
                materialization=self.materialization,
                event_pack=self.event_pack,
                policy=self.policy,
                archive_integrity=integrity,
            )
            two = build_comparison_packet(
                materialization=self.materialization,
                event_pack=self.event_pack,
                policy=self.policy,
                archive_integrity=integrity,
            )
            self.assertEqual(
                canonical_sha256(one[0]), canonical_sha256(two[0])
            )
            self.assertEqual(
                canonical_sha256(one[2]), canonical_sha256(two[2])
            )

    def test_validation_rejects_verified_packet_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            integrity = build_archive_integrity(
                report_root=root,
                fetch_manifest=synthetic_fetch_report(root),
            )
            packet, _, _ = build_comparison_packet(
                materialization=self.materialization,
                event_pack=self.event_pack,
                policy=self.policy,
                archive_integrity=integrity,
            )
            changed = copy.deepcopy(packet)
            changed["sources"][0]["source_verified"] = True
            with self.assertRaises(SourceHumanComparisonError):
                validate_comparison_packet(changed)

    def test_validation_rejects_open_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            integrity = build_archive_integrity(
                report_root=root,
                fetch_manifest=synthetic_fetch_report(root),
            )
            packet, _, _ = build_comparison_packet(
                materialization=self.materialization,
                event_pack=self.event_pack,
                policy=self.policy,
                archive_integrity=integrity,
            )
            changed = copy.deepcopy(packet)
            changed["evidence_gate_status"] = "OPEN"
            with self.assertRaises(SourceHumanComparisonError):
                validate_comparison_packet(changed)

    def test_validation_rejects_review_preapproval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            integrity = build_archive_integrity(
                report_root=root,
                fetch_manifest=synthetic_fetch_report(root),
            )
            packet, comparisons, _ = build_comparison_packet(
                materialization=self.materialization,
                event_pack=self.event_pack,
                policy=self.policy,
                archive_integrity=integrity,
            )
            review = build_review_template(
                packet=packet,
                comparisons=comparisons,
            )
            changed = copy.deepcopy(review)
            changed["decisions"][0]["human_decision"] = True
            with self.assertRaises(SourceHumanComparisonError):
                validate_review_template(changed)

    def test_global_guards(self):
        for data in (self.policy,):
            self.assertEqual(data["evidence_gate_status"], GATE)
            self.assertEqual(
                data["automatic_evidence_approval"], AUTO_APPROVAL
            )
            self.assertEqual(
                data["live_provider_execution"], LIVE_EXECUTION
            )

    def test_write_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            integrity = build_archive_integrity(
                report_root=root,
                fetch_manifest=synthetic_fetch_report(root),
            )
            packet, comparisons, events = build_comparison_packet(
                materialization=self.materialization,
                event_pack=self.event_pack,
                policy=self.policy,
                archive_integrity=integrity,
            )
            review = build_review_template(
                packet=packet,
                comparisons=comparisons,
            )
            outputs = write_local_outputs(
                output_root=root / "report",
                packet=packet,
                comparisons=comparisons,
                event_readiness=events,
                archive_integrity=integrity,
                policy=self.policy,
                review=review,
            )
            self.assertTrue(outputs["zip"].is_file())
            self.assertEqual(
                len(list((root / "report/comparisons").glob("*.json"))),
                22,
            )
            self.assertEqual(
                len(list((root / "report/source-dossiers").glob("*.md"))),
                22,
            )
            self.assertEqual(
                len(list((root / "report/review-batches").glob("*.json"))),
                3,
            )

    def test_json_outputs_use_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            from src.application.storyboard_runtime.source_human_comparison_packet import write_json
            write_json(path, self.policy)
            raw = path.read_bytes()
            self.assertNotIn(b"\r\n", raw)
            self.assertTrue(raw.endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
