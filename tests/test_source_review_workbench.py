from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.source_review_workbench import (
    ALLOWED_DECISIONS,
    AUTO_APPROVAL,
    DECISION_SCHEMA,
    FINAL_APPROVAL_PHRASE,
    GATE,
    JSON_SCHEMA_ID,
    LIVE_EXECUTION,
    MANIFEST_SCHEMA,
    POLICY_SCHEMA,
    TEMPLATE_SCHEMA,
    VALIDATION_SCHEMA,
    SourceReviewWorkbenchError,
    build_decision_template,
    build_json_schema,
    build_manifest,
    build_policy,
    canonical_sha256,
    normalize_arabic,
    render_workbench_html,
    text_sha256,
    validate_human_decision,
    write_local_outputs,
)


def docket():
    sources = []
    for index in range(22):
        excerpt = f"نص المصدر رقم {index}"
        sources.append({
            "source_candidate_id": f"SRC-{index:02d}",
            "locator": f"Locator {index}",
            "source_kind": (
                "QURAN_VERSE" if index < 11
                else "HADITH_COLLECTION_RECORD"
            ),
            "refined_readiness": (
                "READY_FOR_HUMAN_CONFIRMATION"
                if index < 17
                else "REFINED_READY_FOR_HUMAN_CONFIRMATION"
            ),
            "resolution_record_id": f"resolution-{index}",
            "suggested_exact_excerpt": excerpt,
            "suggested_exact_excerpt_sha256": text_sha256(excerpt),
            "human_decision": False,
            "source_verified": False,
        })
    return {
        "schema_version": "siraj-source-review-docket-v1",
        "docket_id": "synthetic-docket",
        "source_count": 22,
        "remaining_resolution_source_ids": [],
        "refined_readiness_counts": {
            "READY_FOR_HUMAN_CONFIRMATION": 17,
            "REFINED_READY_FOR_HUMAN_CONFIRMATION": 5,
        },
        "sources": sources,
        "human_comparison_complete": False,
        "human_approval": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }


def resolution():
    records = []
    for index in range(22):
        excerpt = f"نص المصدر رقم {index}"
        records.append({
            "source_candidate_id": f"SRC-{index:02d}",
            "research_anchor_text": f"مرساة {index}",
            "machine_extracted_text": f"مقدمة {excerpt} خاتمة",
            "enhanced_metrics": {
                "candidate_text": excerpt,
                "candidate_text_sha256": text_sha256(excerpt),
                "missing_anchor_tokens": [],
                "extra_candidate_tokens": ["مقدمة", "خاتمة"],
                "weighted_resolution_score": 0.95,
            },
        })
    return {
        "schema_version": "siraj-partial-source-resolution-v1",
        "resolution_id": "synthetic-resolution",
        "source_count": 22,
        "remaining_resolution_source_count": 0,
        "records": records,
    }


def events():
    ids = [f"SRC-{index:02d}" for index in range(22)]
    rows = []
    cursor = 0
    for index in range(14):
        linked = [ids[cursor % 22], ids[(cursor + 1) % 22]]
        cursor += 2
        rows.append({
            "event_id": f"EV-ADAM-{index + 1:03d}",
            "source_candidate_ids": linked,
        })
    return {
        "schema_version": "siraj-event-source-review-readiness-v1",
        "event_count": 14,
        "event_source_link_count": 28,
        "events": rows,
    }


def materialization():
    return {
        "schema_version": "siraj-remote-source-materialization-v1",
        "source_count": 22,
        "sources": [
            {
                "source_candidate_id": f"SRC-{index:02d}",
                "source_url": f"https://example.test/{index}",
                "retrievals": [{
                    "raw_archive_path": (
                        f"raw/SRC-{index:02d}/response.html"
                    )
                }],
            }
            for index in range(22)
        ],
    }


def completed(template, d, decision="confirm_exact_source_text"):
    data = copy.deepcopy(template)
    data["schema_version"] = DECISION_SCHEMA
    for item, expected in zip(data["decisions"], d["sources"]):
        excerpt = expected["suggested_exact_excerpt"]
        item["decision"] = decision
        item["approved_locator"] = expected["locator"]
        item["approved_exact_excerpt"] = excerpt
        item["approved_exact_excerpt_sha256"] = text_sha256(excerpt)
        item["approved_context_before_after"] = "سياق موثق"
        item["human_compared_to_source"] = True
        item["source_verified"] = True
        item["human_decision"] = True
        item["verified_by"] = "Abdulrahman"
        item["verified_at"] = "2026-07-28T12:00:00+03:00"
        if decision == "confirm_with_correction":
            item["reviewer_notes"] = "تصحيح موثق"
    data["approved_by"] = "Abdulrahman"
    data["approved_at"] = "2026-07-28T13:00:00+03:00"
    data["approval_phrase"] = FINAL_APPROVAL_PHRASE
    data["human_comparison_complete"] = True
    data["source_verification_complete"] = True
    data["human_approval"] = True
    return data


class SourceReviewWorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docket = docket()
        cls.resolution = resolution()
        cls.events = events()
        cls.materialization = materialization()
        cls.policy = build_policy()
        cls.template = build_decision_template(
            docket=cls.docket, policy=cls.policy
        )
        cls.manifest = build_manifest(
            docket=cls.docket,
            resolution=cls.resolution,
            events=cls.events,
            materialization=cls.materialization,
            policy=cls.policy,
        )

    def test_normalize_arabic(self):
        self.assertEqual(
            normalize_arabic("إِنَّ آدَمَ"),
            normalize_arabic("ان ادم"),
        )

    def test_policy_schema(self):
        self.assertEqual(
            self.policy["schema_version"], POLICY_SCHEMA
        )

    def test_policy_decisions(self):
        self.assertEqual(
            tuple(self.policy["allowed_decisions"]),
            ALLOWED_DECISIONS,
        )

    def test_policy_phrase(self):
        self.assertEqual(
            self.policy["final_approval_phrase"],
            FINAL_APPROVAL_PHRASE,
        )

    def test_template_schema(self):
        self.assertEqual(
            self.template["schema_version"], TEMPLATE_SCHEMA
        )

    def test_template_blank(self):
        self.assertEqual(len(self.template["decisions"]), 22)
        self.assertTrue(all(
            not item["decision"]
            and not item["source_verified"]
            and not item["human_decision"]
            for item in self.template["decisions"]
        ))

    def test_manifest_schema(self):
        self.assertEqual(
            self.manifest["schema_version"], MANIFEST_SCHEMA
        )

    def test_manifest_counts(self):
        self.assertEqual(self.manifest["source_count"], 22)
        self.assertEqual(self.manifest["event_count"], 14)
        self.assertEqual(
            self.manifest["event_source_link_count"], 28
        )

    def test_manifest_links(self):
        self.assertTrue(all(
            item["source_url"] and item["raw_archive_paths"]
            for item in self.manifest["sources"]
        ))

    def test_manifest_no_decisions(self):
        self.assertEqual(
            self.manifest["human_decisions_recorded"], 0
        )
        self.assertTrue(all(
            not item["human_decision"]
            and not item["source_verified"]
            for item in self.manifest["sources"]
        ))

    def test_json_schema_id(self):
        self.assertEqual(build_json_schema()["$id"], JSON_SCHEMA_ID)

    def test_json_schema_22(self):
        decisions = build_json_schema()["properties"]["decisions"]
        self.assertEqual(decisions["minItems"], 22)
        self.assertEqual(decisions["maxItems"], 22)

    def test_html_self_contained(self):
        text = render_workbench_html(
            manifest=self.manifest,
            template=self.template,
            policy=self.policy,
        )
        self.assertIn("<!doctype html>", text.lower())
        self.assertNotIn("<script src=", text)
        self.assertNotIn("<link rel=", text)

    def test_html_contains_sources(self):
        text = render_workbench_html(
            manifest=self.manifest,
            template=self.template,
            policy=self.policy,
        )
        for item in self.manifest["sources"]:
            self.assertIn(item["source_candidate_id"], text)

    def test_html_no_selected_decision(self):
        text = render_workbench_html(
            manifest=self.manifest,
            template=self.template,
            policy=self.policy,
        )
        self.assertIn("— اختر بعد المراجعة —", text)
        self.assertNotIn('selected value="confirm', text)

    def test_final_valid_exact(self):
        data = completed(self.template, self.docket)
        report = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        self.assertEqual(
            report["status"],
            "PASS_FINAL_HUMAN_SOURCE_REVIEW",
        )
        self.assertFalse(report["errors"])

    def test_final_valid_defer(self):
        data = completed(
            self.template, self.docket, "defer_authentication"
        )
        report = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        self.assertFalse(report["errors"])

    def test_reject_is_valid_but_incomplete(self):
        data = completed(self.template, self.docket)
        item = data["decisions"][0]
        item["decision"] = "reject_locator"
        item["approved_locator"] = ""
        item["approved_exact_excerpt"] = ""
        item["approved_exact_excerpt_sha256"] = ""
        item["approved_context_before_after"] = ""
        item["source_verified"] = False
        item["reviewer_notes"] = "الموضع غير صحيح"
        data["source_verification_complete"] = False
        report = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        self.assertFalse(report["errors"])
        self.assertFalse(
            report["computed_source_verification_complete"]
        )

    def test_correction_requires_notes(self):
        data = completed(
            self.template, self.docket, "confirm_with_correction"
        )
        data["decisions"][0]["reviewer_notes"] = ""
        report = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        self.assertTrue(any(
            "correction notes" in error
            for error in report["errors"]
        ))

    def test_exact_rejects_changed_text(self):
        data = completed(self.template, self.docket)
        item = data["decisions"][0]
        item["approved_exact_excerpt"] += " زيادة"
        item["approved_exact_excerpt_sha256"] = text_sha256(
            item["approved_exact_excerpt"]
        )
        report = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        self.assertTrue(any(
            "correction decision" in error
            for error in report["errors"]
        ))

    def test_checksum_guard(self):
        data = completed(self.template, self.docket)
        data["decisions"][0][
            "approved_exact_excerpt_sha256"
        ] = "0" * 64
        report = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        self.assertTrue(any(
            "SHA-256 mismatch" in error
            for error in report["errors"]
        ))

    def test_phrase_guard(self):
        data = completed(self.template, self.docket)
        data["approval_phrase"] = "موافق"
        report = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        self.assertIn("approval phrase mismatch", report["errors"])

    def test_approved_by_required(self):
        data = completed(self.template, self.docket)
        data["approved_by"] = ""
        report = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        self.assertIn("approved_by is required", report["errors"])

    def test_exact_22_required(self):
        data = completed(self.template, self.docket)
        data["decisions"].pop()
        report = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        self.assertTrue(any(
            "exactly 22" in error
            for error in report["errors"]
        ))

    def test_authentication_locked(self):
        data = completed(self.template, self.docket)
        data["decisions"][0]["authentication_verified"] = True
        report = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        self.assertTrue(any(
            "authentication_verified" in error
            for error in report["errors"]
        ))

    def test_origin_locked(self):
        data = completed(self.template, self.docket)
        data["decisions"][0][
            "origin_classification_verified"
        ] = True
        report = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        self.assertTrue(any(
            "origin_classification_verified" in error
            for error in report["errors"]
        ))

    def test_binding_locked(self):
        data = completed(self.template, self.docket)
        data["decisions"][0]["approved_for_event_binding"] = True
        report = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        self.assertTrue(any(
            "approved_for_event_binding" in error
            for error in report["errors"]
        ))

    def test_gate_locked(self):
        data = completed(self.template, self.docket)
        data["opens_evidence_gate"] = True
        report = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        self.assertTrue(any(
            "opens_evidence_gate" in error
            for error in report["errors"]
        ))

    def test_validation_schema(self):
        data = completed(self.template, self.docket)
        report = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        self.assertEqual(
            report["schema_version"], VALIDATION_SCHEMA
        )

    def test_validation_deterministic(self):
        data = completed(self.template, self.docket)
        one = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        two = validate_human_decision(
            data,
            docket=self.docket,
            policy=self.policy,
            require_final=True,
        )
        self.assertEqual(
            canonical_sha256(one), canonical_sha256(two)
        )

    def test_write_outputs(self):
        html = render_workbench_html(
            manifest=self.manifest,
            template=self.template,
            policy=self.policy,
        )
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_local_outputs(
                output_root=Path(tmp) / "report",
                manifest=self.manifest,
                template=self.template,
                policy=self.policy,
                json_schema=build_json_schema(),
                html_text=html,
            )
            self.assertTrue(outputs["html"].is_file())
            self.assertTrue(outputs["archive"].is_file())
            self.assertGreater(
                outputs["html"].stat().st_size, 10000
            )

    def test_json_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            from src.application.storyboard_runtime.source_review_workbench import write_json
            write_json(path, self.policy)
            raw = path.read_bytes()
            self.assertNotIn(b"\r\n", raw)
            self.assertTrue(raw.endswith(b"\n"))


    def test_html_helpers_are_initialized_before_load(self):
        text = render_workbench_html(
            manifest=self.manifest,
            template=self.template,
            policy=self.policy,
        )
        helper_position = text.index(
            'const $=x=>document.getElementById(x),clone='
        )
        load_position = text.index('let D=load();')
        self.assertLess(helper_position, load_position)

    def test_html_rejects_incomplete_saved_state(self):
        text = render_workbench_html(
            manifest=self.manifest,
            template=self.template,
            policy=self.policy,
        )
        self.assertIn(
            'Array.isArray(x.decisions)&&x.decisions.length===22',
            text,
        )

    def test_html_has_visible_runtime_failure_handler(self):
        text = render_workbench_html(
            manifest=self.manifest,
            template=self.template,
            policy=self.policy,
        )
        self.assertIn('function showFatal(error)', text)
        self.assertIn(
            'window.addEventListener("error"',
            text,
        )
        self.assertIn(
            'تعذر تشغيل منضدة المراجعة',
            text,
        )

    def test_html_does_not_use_broken_bootstrap_order(self):
        text = render_workbench_html(
            manifest=self.manifest,
            template=self.template,
            policy=self.policy,
        )
        broken = (
            'const key="siraj-source-review-"+M.docket_id;'
            'let D=load(),i=0;'
        )
        self.assertNotIn(broken, text)

if __name__ == "__main__":
    unittest.main()
