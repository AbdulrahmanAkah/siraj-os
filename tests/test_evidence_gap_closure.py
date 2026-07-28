from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.application.storyboard_runtime.evidence_gap_closure import (
    AUTOMATIC_APPROVAL_STATUS,
    DOCKET_STATUS,
    EDITORIAL_ONLY,
    EVIDENCE_GATE_STATUS,
    EVIDENCE_GAP_DOCKET_SCHEMA_VERSION,
    EVIDENCE_GAP_REVIEW_TEMPLATE_SCHEMA_VERSION,
    LIVE_EXECUTION_STATUS,
    TEMPLATE_STATUS,
    AdamEvidenceGapClosureBuilder,
    EvidenceGapClosureError,
    gap_review_template,
    validate_gap_docket,
    validate_gap_review_template,
    write_gap_docket,
    write_gap_review_template,
)


EVENTS = [
    {
        "event_id": "EV-ADAM-031",
        "order": 310,
        "title": "أول حركة وعطاس وكلام لآدم",
        "section": "بدء حياة آدم",
        "verification_status": "deferred",
        "chronology_type": "pending_verification",
        "importance": "supporting",
        "question_ids": ["RQ-ADAM-013"],
    },
    {
        "event_id": "EV-ADAM-071",
        "order": 710,
        "title": "اسم حواء والتفاصيل المنقولة عن خلقها",
        "section": "خلق الزوج",
        "verification_status": "deferred",
        "chronology_type": "pending_verification",
        "importance": "supporting",
        "question_ids": ["RQ-ADAM-026", "RQ-ADAM-027"],
    },
    {
        "event_id": "EV-ADAM-091",
        "order": 910,
        "title": "الأقوال في نوع الشجرة",
        "section": "الاختبار الأول",
        "verification_status": "deferred",
        "chronology_type": "not_applicable",
        "importance": "supporting",
        "question_ids": ["RQ-ADAM-029", "RQ-ADAM-030"],
    },
    {
        "event_id": "EV-ADAM-099",
        "order": 990,
        "title": "التمهيد لبدء الوسوسة",
        "section": "خاتمة الحلقة",
        "verification_status": "editorial",
        "chronology_type": "editorial_arrangement",
        "importance": "core",
        "question_ids": ["RQ-ADAM-032"],
    },
]

QUESTIONS = [
    {
        "question_id": "RQ-ADAM-013",
        "question": "ما الثابت في نفخ الروح وأول حركة أو كلام أو عطاس لآدم؟",
        "verification_status": "deferred",
    },
    {
        "question_id": "RQ-ADAM-026",
        "question": "ما مصدر اسم حواء وما درجة ثبوته؟",
        "verification_status": "deferred",
    },
    {
        "question_id": "RQ-ADAM-027",
        "question": "هل ثبت الضلع الأيسر أو خلقها أثناء نوم آدم؟",
        "verification_status": "deferred",
    },
    {
        "question_id": "RQ-ADAM-029",
        "question": "هل ثبت نوع الشجرة المنهي عنها؟",
        "verification_status": "pending",
    },
    {
        "question_id": "RQ-ADAM-030",
        "question": "ما الروايات التاريخية والإسرائيلية الواردة في تعيين الشجرة؟",
        "verification_status": "deferred",
    },
    {
        "question_id": "RQ-ADAM-032",
        "question": "ما أفضل نقطة لإنهاء الحلقة قبل بدء الوسوسة؟",
        "verification_status": "pending",
    },
]


def recovery_fixture() -> dict[str, object]:
    return {
        "schema_version": "siraj-recovered-evidence-knowledge-v1",
        "episode_id": "episode-001-adam",
        "recovery_id": "recovered_evidence_knowledge_example",
        "recovery_status": "RECOVERED_REVIEW_PENDING",
        "evidence_gate_status": EVIDENCE_GATE_STATUS,
        "automatic_evidence_approval": AUTOMATIC_APPROVAL_STATUS,
        "live_provider_execution": LIVE_EXECUTION_STATUS,
        "candidate_event_links": {
            "SRC-QURAN-BAQARAH-029-035": ["EV-ADAM-090"],
            "SRC-HISTORY-BIDAYAH-ADAM": [],
        },
        "review_artifacts": [
            {
                "review_stage": "topic-prefilter",
                "artifact": {
                    "relative_path": "projects/episode-001-adam/sources/review.jsonl",
                    "event_ids": [],
                },
            }
        ],
        "normalized_sources": [
            {"source_id": "SRC-HISTORY-BIDAYAH-ADAM"},
            {"source_id": "SRC-TAFSIR-IBN-KATHIR-ADAM"},
        ],
        "uncovered_event_ids": [
            "EV-ADAM-031",
            "EV-ADAM-071",
            "EV-ADAM-091",
            "EV-ADAM-099",
        ],
        "unknown_event_ids": [],
        "unknown_source_ids": [],
    }


def source_package_fixture() -> dict[str, object]:
    return {
        "schema_version": "siraj-episode-source-package-v1",
        "package_status": "DRAFT_ACQUISITION_PENDING",
        "source_items": [],
    }


class EvidenceGapClosureTests(unittest.TestCase):
    def build(self):
        return AdamEvidenceGapClosureBuilder().build_from_data(
            recovery=recovery_fixture(),
            event_map=EVENTS,
            research_questions=QUESTIONS,
            source_package=source_package_fixture(),
        )

    def test_builds_exact_four_gap_docket(self):
        docket = self.build()
        self.assertEqual([item.event_id for item in docket.entries], [
            "EV-ADAM-031", "EV-ADAM-071", "EV-ADAM-091", "EV-ADAM-099"
        ])
        self.assertEqual(docket.to_manifest()["counts"]["total_uncovered_events"], 4)

    def test_three_factual_and_one_editorial(self):
        manifest = self.build().to_manifest()
        self.assertEqual(manifest["counts"]["factual_review_events"], 3)
        self.assertEqual(manifest["counts"]["editorial_only_events"], 1)

    def test_editorial_event_is_recommendation_only(self):
        item = self.build().entries[-1]
        self.assertEqual(item.resolution_lane, "editorial_only")
        self.assertEqual(item.allowed_dispositions, (EDITORIAL_ONLY,))
        self.assertEqual(item.recommended_disposition, EDITORIAL_ONLY)
        self.assertEqual(item.recommendation_status, "RECOMMENDATION_ONLY")
        self.assertTrue(item.human_decision_required)

    def test_factual_events_have_no_default_decision(self):
        for item in self.build().entries[:3]:
            self.assertEqual(item.resolution_lane, "targeted_human_review")
            self.assertIsNone(item.recommended_disposition)
            self.assertEqual(item.recommendation_status, "NO_DEFAULT_DECISION")

    def test_research_questions_are_preserved(self):
        item = self.build().entries[1]
        self.assertEqual(item.question_ids, ("RQ-ADAM-026", "RQ-ADAM-027"))
        self.assertEqual(len(item.research_questions), 2)

    def test_no_explicit_source_link_is_invented(self):
        for item in self.build().entries:
            self.assertEqual(item.explicit_candidate_source_ids, ())

    def test_gate_remains_withheld(self):
        manifest = self.build().to_manifest()
        self.assertEqual(manifest["evidence_gate_status"], EVIDENCE_GATE_STATUS)
        self.assertEqual(manifest["automatic_evidence_approval"], AUTOMATIC_APPROVAL_STATUS)
        self.assertEqual(manifest["live_provider_execution"], LIVE_EXECUTION_STATUS)
        self.assertFalse(manifest["raw_source_text_copied"])

    def test_manifest_is_deterministic(self):
        self.assertEqual(self.build().to_json(), self.build().to_json())
        self.assertEqual(self.build().docket_id, self.build().docket_id)

    def test_template_is_non_executable(self):
        docket = self.build()
        template = gap_review_template(docket)
        self.assertEqual(template["schema_version"], EVIDENCE_GAP_REVIEW_TEMPLATE_SCHEMA_VERSION)
        self.assertEqual(template["status"], TEMPLATE_STATUS)
        self.assertFalse(template["human_approval"])
        self.assertTrue(all(item["disposition"] == "" for item in template["decisions"]))
        validate_gap_review_template(template, docket)

    def test_unknown_event_is_rejected(self):
        recovery = recovery_fixture()
        recovery["uncovered_event_ids"] = ["EV-ADAM-DOES-NOT-EXIST"]
        with self.assertRaises(EvidenceGapClosureError):
            AdamEvidenceGapClosureBuilder().build_from_data(
                recovery=recovery,
                event_map=EVENTS,
                research_questions=QUESTIONS,
                source_package=source_package_fixture(),
            )

    def test_unknown_recovered_ids_block_docket(self):
        recovery = recovery_fixture()
        recovery["unknown_source_ids"] = ["SRC-UNKNOWN"]
        with self.assertRaises(EvidenceGapClosureError):
            AdamEvidenceGapClosureBuilder().build_from_data(
                recovery=recovery,
                event_map=EVENTS,
                research_questions=QUESTIONS,
                source_package=source_package_fixture(),
            )

    def test_approved_source_package_is_rejected(self):
        package = source_package_fixture()
        package["package_status"] = "APPROVED"
        with self.assertRaises(EvidenceGapClosureError):
            AdamEvidenceGapClosureBuilder().build_from_data(
                recovery=recovery_fixture(),
                event_map=EVENTS,
                research_questions=QUESTIONS,
                source_package=package,
            )

    def test_stale_gate_state_is_rejected(self):
        recovery = recovery_fixture()
        recovery["evidence_gate_status"] = "OPEN_APPROVED_EVIDENCE_PACKAGE_BOUND"
        with self.assertRaises(EvidenceGapClosureError):
            AdamEvidenceGapClosureBuilder().build_from_data(
                recovery=recovery,
                event_map=EVENTS,
                research_questions=QUESTIONS,
                source_package=source_package_fixture(),
            )

    def test_absolute_review_path_is_rejected(self):
        recovery = recovery_fixture()
        recovery["review_artifacts"][0]["artifact"]["relative_path"] = "C:/secret/review.jsonl"
        with self.assertRaises(EvidenceGapClosureError):
            AdamEvidenceGapClosureBuilder().build_from_data(
                recovery=recovery,
                event_map=EVENTS,
                research_questions=QUESTIONS,
                source_package=source_package_fixture(),
            )

    def test_secret_like_field_is_rejected(self):
        recovery = recovery_fixture()
        recovery["api_key"] = "not-allowed"
        with self.assertRaises(EvidenceGapClosureError):
            AdamEvidenceGapClosureBuilder().build_from_data(
                recovery=recovery,
                event_map=EVENTS,
                research_questions=QUESTIONS,
                source_package=source_package_fixture(),
            )

    def test_raw_text_field_is_rejected(self):
        recovery = recovery_fixture()
        recovery["quoted_text"] = "raw source text"
        with self.assertRaises(EvidenceGapClosureError):
            AdamEvidenceGapClosureBuilder().build_from_data(
                recovery=recovery,
                event_map=EVENTS,
                research_questions=QUESTIONS,
                source_package=source_package_fixture(),
            )

    def test_docket_validation_rejects_auto_decision(self):
        manifest = self.build().to_manifest()
        manifest["entries"][0]["recommended_disposition"] = "omit_unverified"
        with self.assertRaises(EvidenceGapClosureError):
            validate_gap_docket(manifest)

    def test_write_is_utf8_lf(self):
        docket = self.build()
        with tempfile.TemporaryDirectory() as temp:
            docket_path = Path(temp) / "docket.json"
            template_path = Path(temp) / "template.json"
            write_gap_docket(docket_path, docket)
            write_gap_review_template(template_path, docket)
            for path in (docket_path, template_path):
                data = path.read_bytes()
                self.assertNotIn(b"\r\n", data)
                json.loads(data.decode("utf-8"))

    def test_cli_runs_from_arbitrary_cwd(self):
        repo_root = Path(__file__).resolve().parents[1]
        episode = repo_root / "projects" / "episode-001-adam"
        (episode / "evidence").mkdir(parents=True, exist_ok=True)
        (episode / "editorial").mkdir(parents=True, exist_ok=True)
        (episode / "contracts").mkdir(parents=True, exist_ok=True)
        files = {
            episode / "evidence" / "recovered-evidence-knowledge-v1.json": recovery_fixture(),
            episode / "editorial" / "event-map.json": EVENTS,
            episode / "editorial" / "research-questions.json": QUESTIONS,
            episode / "contracts" / "source-package-v1.draft.json": source_package_fixture(),
        }
        for path, payload in files.items():
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        docket_path = episode / "evidence" / "test-docket.json"
        template_path = episode / "evidence" / "test-template.json"
        try:
            with tempfile.TemporaryDirectory() as cwd:
                result = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        str(repo_root / "scripts/fast_track/build_adam_evidence_gap_docket_v1.py"),
                        "--repo-root",
                        str(repo_root),
                        "--docket-output",
                        str(docket_path),
                        "--review-template-output",
                        str(template_path),
                    ],
                    cwd=cwd,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
            self.assertIn("STATUS=PASS_ADAM_EVIDENCE_GAP_DOCKET_BUILT", result.stdout)
            self.assertTrue(docket_path.is_file())
            self.assertTrue(template_path.is_file())
        finally:
            docket_path.unlink(missing_ok=True)
            template_path.unlink(missing_ok=True)

    def test_schema_and_status_are_fixed(self):
        manifest = self.build().to_manifest()
        self.assertEqual(manifest["schema_version"], EVIDENCE_GAP_DOCKET_SCHEMA_VERSION)
        self.assertEqual(manifest["status"], DOCKET_STATUS)


if __name__ == "__main__":
    unittest.main()
