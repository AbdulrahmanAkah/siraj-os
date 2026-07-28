from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.remote_source_materialization import (
    AUTO_APPROVAL,
    FETCH_SCHEMA,
    GATE,
    LIVE_EXECUTION,
    MATERIALIZATION_SCHEMA,
    POLICY_SCHEMA,
    PREFILL_SCHEMA,
    REVIEW_SCHEMA,
    RemoteSourceMaterializationError,
    anchor_metrics,
    build_event_readiness,
    build_materialization,
    build_policy,
    build_review_template,
    canonical_sha256,
    choose_hadith_arabic_block,
    fetch_source_candidate,
    normalize_arabic,
    parse_quran_api_response,
    parse_quran_keys,
    quran_request_urls,
    text_sha256,
    validate_fetch_manifest,
    validate_materialization,
    validate_policy,
    validate_prefill,
    validate_review_template,
    write_local_outputs,
)


def source(
    source_id: str,
    kind: str,
    locator: str,
    anchor: str,
    url: str,
):
    return {
        "source_candidate_id": source_id,
        "candidate_record_id": "record-" + source_id,
        "source_kind": kind,
        "collection": "collection",
        "locator": locator,
        "source_url": url,
        "arabic_anchor_text": anchor,
        "arabic_anchor_sha256": text_sha256(anchor),
    }


def synthetic_catalog():
    hadith = source(
        "SRC-H",
        "HADITH_COLLECTION_RECORD",
        "Sahih Test 1",
        "كان الله ولم يكن شيء غيره",
        "https://example.test/hadith",
    )
    quran = source(
        "SRC-Q",
        "QURAN_VERSE",
        "Quran 2:34",
        "وإذ قلنا للملائكة اسجدوا لآدم",
        "https://quran.com/2/34",
    )
    sources = [hadith, quran]
    while len(sources) < 22:
        index = len(sources)
        sources.append(source(
            f"SRC-{index:02d}",
            "HADITH_COLLECTION_RECORD",
            f"Sahih Test {index}",
            f"نص عربي مرشح رقم {index}",
            f"https://example.test/{index}",
        ))
    return {
        "schema_version": (
            "siraj-external-source-candidate-catalog-v1"
        ),
        "catalog_id": "synthetic-catalog",
        "source_candidate_count": 22,
        "source_candidates": sources,
        "human_approval": False,
    }


def synthetic_pack(catalog):
    ids = [
        item["source_candidate_id"]
        for item in catalog["source_candidates"]
    ]
    events = []
    links = []
    cursor = 0
    for index in range(14):
        count = 2
        event_ids = [
            ids[cursor % len(ids)],
            ids[(cursor + 1) % len(ids)],
        ]
        cursor += 2
        events.append({
            "event_id": f"EV-ADAM-{index + 1:03d}",
            "title": f"event {index}",
            "proposed_disposition": "include_qualified",
            "source_candidate_ids": event_ids,
        })
        links.extend(event_ids)
    return {
        "schema_version": (
            "siraj-external-event-source-candidate-pack-v1"
        ),
        "pack_id": "synthetic-pack",
        "event_count": 14,
        "event_source_link_count": 28,
        "events": events,
    }


HADITH_HTML = """
<html><body>
<div class="english_hadith_full">English text</div>
<div class="arabic_hadith_full arabic">
حَدَّثَنَا فُلَانٌ قَالَ كَانَ اللَّهُ وَلَمْ يَكُنْ شَيْءٌ غَيْرُهُ
</div>
</body></html>
""".encode("utf-8")


def fake_fetcher(url: str, **kwargs):
    if "quran.com" in url and (
        "api/v4" in url or "api.quran.com" in url
    ):
        payload = {
            "verses": [{
                "verse_key": "2:34",
                "text_uthmani": (
                    "وَإِذْ قُلْنَا لِلْمَلَائِكَةِ "
                    "اسْجُدُوا لِآدَمَ"
                ),
            }]
        }
        raw = json.dumps(
            payload, ensure_ascii=False
        ).encode("utf-8")
        return {
            "success": True,
            "requested_url": url,
            "final_url": url,
            "http_status": 200,
            "content_type": "application/json",
            "charset": "utf-8",
            "response_bytes": raw,
            "response_bytes_count": len(raw),
            "response_sha256": __import__("hashlib").sha256(
                raw
            ).hexdigest(),
            "attempt_count": 1,
            "errors": [],
        }
    if url.startswith("https://quran.com/"):
        raw = b"<html></html>"
    else:
        raw = HADITH_HTML
    return {
        "success": True,
        "requested_url": url,
        "final_url": url,
        "http_status": 200,
        "content_type": "text/html",
        "charset": "utf-8",
        "response_bytes": raw,
        "response_bytes_count": len(raw),
        "response_sha256": __import__("hashlib").sha256(
            raw
        ).hexdigest(),
        "attempt_count": 1,
        "errors": [],
    }


class RemoteSourceMaterializationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = build_policy()
        cls.catalog = synthetic_catalog()
        cls.pack = synthetic_pack(cls.catalog)

    def test_normalize_arabic_removes_diacritics(self):
        self.assertEqual(
            normalize_arabic("كَانَ اللَّهُ"),
            normalize_arabic("كان الله"),
        )

    def test_normalize_arabic_normalizes_alef(self):
        self.assertEqual(
            normalize_arabic("إلى آدم"),
            normalize_arabic("الى ادم"),
        )

    def test_anchor_exact_substring(self):
        metrics = anchor_metrics(
            "كان الله", "قال كان الله ولم يكن شيء"
        )
        self.assertTrue(
            metrics["normalized_anchor_is_substring"]
        )

    def test_anchor_token_coverage(self):
        metrics = anchor_metrics(
            "كان الله ولم يكن شيء", "كان الله شيء"
        )
        self.assertGreater(metrics["anchor_token_coverage"], 0.5)

    def test_hadith_html_extraction(self):
        result = choose_hadith_arabic_block(
            HADITH_HTML, "كان الله ولم يكن شيء غيره"
        )
        self.assertTrue(result["success"])
        self.assertIn(
            normalize_arabic("اللَّهُ"),
            normalize_arabic(result["machine_extracted_text"]),
        )

    def test_hadith_html_extraction_no_arabic(self):
        result = choose_hadith_arabic_block(
            b"<html><p>English only</p></html>",
            "كان الله",
        )
        self.assertFalse(result["success"])

    def test_parse_single_quran_key(self):
        self.assertEqual(
            parse_quran_keys("Quran 2:34"), ["2:34"]
        )

    def test_parse_quran_range(self):
        self.assertEqual(
            parse_quran_keys("Quran 2:31-33"),
            ["2:31", "2:32", "2:33"],
        )

    def test_rejects_invalid_quran_range(self):
        with self.assertRaises(RemoteSourceMaterializationError):
            parse_quran_keys("Quran 2:35-31")

    def test_quran_request_has_three_fallbacks(self):
        urls = quran_request_urls("2:34")
        self.assertEqual(len(urls), 3)
        self.assertTrue(
            urls[0].startswith("https://api.quran.com/")
        )

    def test_parse_quran_verses_payload(self):
        raw = json.dumps({
            "verses": [{
                "verse_key": "2:34",
                "text_uthmani": "نص الآية",
            }]
        }, ensure_ascii=False).encode("utf-8")
        self.assertEqual(
            parse_quran_api_response(raw, "2:34"),
            "نص الآية",
        )

    def test_parse_quran_single_verse_payload(self):
        raw = json.dumps({
            "verse": {"text_uthmani": "نص آخر"}
        }, ensure_ascii=False).encode("utf-8")
        self.assertEqual(
            parse_quran_api_response(raw, "2:34"),
            "نص آخر",
        )

    def test_parse_quran_embedded_json(self):
        raw = (
            '<script>{"text_uthmani":"نص مضمن"}</script>'
        ).encode("utf-8")
        self.assertEqual(
            parse_quran_api_response(raw, "2:34"),
            "نص مضمن",
        )

    def test_fetch_hadith_candidate(self):
        item = self.catalog["source_candidates"][0]
        result = fetch_source_candidate(
            item, fetcher=fake_fetcher
        )
        self.assertTrue(result["machine_extracted_text"])
        self.assertEqual(
            result["status"],
            "FETCHED_EXTRACTED_ANCHOR_MATCH",
        )

    def test_fetch_quran_candidate(self):
        item = self.catalog["source_candidates"][1]
        result = fetch_source_candidate(
            item, fetcher=fake_fetcher
        )
        self.assertTrue(result["machine_extracted_text"])
        self.assertIn("اسْجُدُوا", result["machine_extracted_text"])

    def test_policy_schema(self):
        self.assertEqual(
            self.policy["schema_version"], POLICY_SCHEMA
        )

    def test_policy_forbids_auto_verification(self):
        self.assertIn(
            "automatic source verification",
            self.policy["prohibitions"],
        )

    def test_review_template_blank(self):
        review = build_review_template(
            self.catalog, self.policy
        )
        self.assertEqual(
            review["schema_version"], REVIEW_SCHEMA
        )
        self.assertTrue(all(
            not item["approved_exact_excerpt"]
            and not item["source_verified"]
            and not item["human_decision"]
            for item in review["decisions"]
        ))

    def test_build_materialization_covers_22_sources(self):
        data, manifest, raw, prefill = build_materialization(
            catalog=self.catalog,
            event_pack=self.pack,
            policy=self.policy,
            fetcher=fake_fetcher,
            max_workers=3,
        )
        self.assertEqual(
            data["schema_version"], MATERIALIZATION_SCHEMA
        )
        self.assertEqual(data["source_count"], 22)
        self.assertGreater(len(raw), 0)
        self.assertEqual(
            manifest["schema_version"], FETCH_SCHEMA
        )
        self.assertEqual(
            prefill["schema_version"], PREFILL_SCHEMA
        )

    def test_build_materialization_28_prefills(self):
        _, _, _, prefill = build_materialization(
            catalog=self.catalog,
            event_pack=self.pack,
            policy=self.policy,
            fetcher=fake_fetcher,
        )
        self.assertEqual(
            prefill["event_source_suggestion_count"], 28
        )

    def test_no_materialized_source_is_verified(self):
        data, *_ = build_materialization(
            catalog=self.catalog,
            event_pack=self.pack,
            policy=self.policy,
            fetcher=fake_fetcher,
        )
        self.assertTrue(all(
            not item["human_compared_to_source"]
            and not item["source_verified"]
            and not item["authentication_verified"]
            and not item["origin_classification_verified"]
            for item in data["sources"]
        ))

    def test_raw_bytes_are_not_in_materialization_json(self):
        data, *_ = build_materialization(
            catalog=self.catalog,
            event_pack=self.pack,
            policy=self.policy,
            fetcher=fake_fetcher,
        )
        serialized = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("raw_bytes", serialized)

    def test_fetch_manifest_archives_successes(self):
        _, manifest, raw, _ = build_materialization(
            catalog=self.catalog,
            event_pack=self.pack,
            policy=self.policy,
            fetcher=fake_fetcher,
        )
        self.assertEqual(
            manifest["archived_response_count"], len(raw)
        )
        self.assertTrue(all(
            item["raw_archive_path"]
            for item in manifest["records"]
            if item["success"]
        ))

    def test_prefill_cannot_copy_to_verified(self):
        _, _, _, prefill = build_materialization(
            catalog=self.catalog,
            event_pack=self.pack,
            policy=self.policy,
            fetcher=fake_fetcher,
        )
        self.assertTrue(all(
            item["copy_into_verified_exact_excerpt"] is False
            and item["human_comparison_required"] is True
            for item in prefill["suggestions"]
        ))

    def test_event_readiness_covers_14_events(self):
        data, *_ = build_materialization(
            catalog=self.catalog,
            event_pack=self.pack,
            policy=self.policy,
            fetcher=fake_fetcher,
        )
        readiness = build_event_readiness(data, self.pack)
        self.assertEqual(readiness["event_count"], 14)
        self.assertTrue(all(
            not item["source_verification_complete"]
            and not item["event_approved"]
            for item in readiness["events"]
        ))

    def test_materialization_deterministic_with_fake_fetcher(self):
        one = build_materialization(
            catalog=self.catalog,
            event_pack=self.pack,
            policy=self.policy,
            fetcher=fake_fetcher,
            max_workers=1,
        )[0]
        two = build_materialization(
            catalog=self.catalog,
            event_pack=self.pack,
            policy=self.policy,
            fetcher=fake_fetcher,
            max_workers=4,
        )[0]
        self.assertEqual(
            canonical_sha256(one), canonical_sha256(two)
        )

    def test_validation_rejects_verified_source(self):
        data, *_ = build_materialization(
            catalog=self.catalog,
            event_pack=self.pack,
            policy=self.policy,
            fetcher=fake_fetcher,
        )
        changed = copy.deepcopy(data)
        changed["sources"][0]["source_verified"] = True
        with self.assertRaises(RemoteSourceMaterializationError):
            validate_materialization(changed)

    def test_validation_rejects_open_gate(self):
        data, *_ = build_materialization(
            catalog=self.catalog,
            event_pack=self.pack,
            policy=self.policy,
            fetcher=fake_fetcher,
        )
        changed = copy.deepcopy(data)
        changed["evidence_gate_status"] = "OPEN"
        with self.assertRaises(RemoteSourceMaterializationError):
            validate_materialization(changed)

    def test_validation_rejects_review_preapproval(self):
        review = build_review_template(
            self.catalog, self.policy
        )
        changed = copy.deepcopy(review)
        changed["decisions"][0]["source_verified"] = True
        with self.assertRaises(RemoteSourceMaterializationError):
            validate_review_template(changed)

    def test_global_guards(self):
        review = build_review_template(
            self.catalog, self.policy
        )
        for data in (self.policy, review):
            self.assertEqual(
                data["evidence_gate_status"], GATE
            )
            self.assertEqual(
                data["automatic_evidence_approval"],
                AUTO_APPROVAL,
            )
            self.assertEqual(
                data["live_provider_execution"],
                LIVE_EXECUTION,
            )

    def test_write_outputs(self):
        data, manifest, raw, prefill = build_materialization(
            catalog=self.catalog,
            event_pack=self.pack,
            policy=self.policy,
            fetcher=fake_fetcher,
        )
        review = build_review_template(
            self.catalog,
            self.policy,
            materialization_id=data["materialization_id"],
            materialization_sha256=canonical_sha256(data),
        )
        readiness = build_event_readiness(data, self.pack)
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_local_outputs(
                output_root=Path(tmp) / "report",
                materialization=data,
                fetch_manifest=manifest,
                raw_files=raw,
                prefill=prefill,
                policy=self.policy,
                review=review,
                event_readiness=readiness,
            )
            self.assertTrue(outputs["archive"].is_file())
            self.assertEqual(
                len(list(
                    (Path(tmp) / "report/extracted").glob("*.json")
                )),
                22,
            )
            self.assertEqual(
                len(list(
                    (Path(tmp) / "report/source-dossiers").glob("*.md")
                )),
                22,
            )

    def test_json_outputs_use_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            from src.application.storyboard_runtime.remote_source_materialization import write_json
            write_json(path, self.policy)
            raw = path.read_bytes()
            self.assertNotIn(b"\r\n", raw)
            self.assertTrue(raw.endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
