from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.application.storyboard_runtime.source_origin_classification import (
    AUTOMATIC_APPROVAL_STATUS,
    CLASSIFICATION_STATUS,
    EVIDENCE_GATE_STATUS,
    LIVE_EXECUTION_STATUS,
    PROPOSAL_STATUS,
    SourceOriginClassificationError,
    TARGET_EVENT_IDS,
    UNKNOWN_TREE_FORMULA,
    canonical_json_sha256,
    load_and_validate_bundle,
    validate_proposed_gap_adjudication,
    validate_source_origin_classification,
    write_validation_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATION_PATH = (
    REPO_ROOT
    / "projects/episode-001-adam/evidence/source-origin-classification-v1.json"
)
PROPOSAL_PATH = (
    REPO_ROOT
    / "projects/episode-001-adam/evidence/proposed-gap-adjudication-v1.json"
)


class SourceOriginClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.classification = json.loads(
            CLASSIFICATION_PATH.read_text(encoding="utf-8")
        )
        cls.proposal = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))

    def test_complete_bundle_validates(self) -> None:
        bundle = load_and_validate_bundle(REPO_ROOT)
        self.assertEqual(
            bundle["classification"]["status"],
            CLASSIFICATION_STATUS,
        )
        self.assertEqual(bundle["proposal"]["status"], PROPOSAL_STATUS)

    def test_classification_schema_and_status(self) -> None:
        validate_source_origin_classification(self.classification)
        self.assertEqual(
            self.classification["schema_version"],
            "siraj-source-origin-classification-v1",
        )
        self.assertEqual(self.classification["status"], CLASSIFICATION_STATUS)

    def test_proposal_schema_and_status(self) -> None:
        validate_proposed_gap_adjudication(self.proposal)
        self.assertEqual(
            self.proposal["schema_version"],
            "siraj-proposed-gap-adjudication-v1",
        )
        self.assertEqual(self.proposal["status"], PROPOSAL_STATUS)

    def test_gate_remains_withheld_everywhere(self) -> None:
        for payload in (self.classification, self.proposal):
            self.assertEqual(
                payload["evidence_gate_status"],
                EVIDENCE_GATE_STATUS,
            )
            self.assertEqual(
                payload["automatic_evidence_approval"],
                AUTOMATIC_APPROVAL_STATUS,
            )
            self.assertEqual(
                payload["live_provider_execution"],
                LIVE_EXECUTION_STATUS,
            )

    def test_no_evidence_or_human_approval(self) -> None:
        self.assertFalse(self.classification["evidence_approval"])
        self.assertFalse(self.classification["human_evidence_approval"])
        self.assertFalse(self.proposal["human_approval"])
        self.assertFalse(self.proposal["binding"])
        self.assertFalse(self.proposal["opens_evidence_gate"])

    def test_exact_three_events_are_preserved(self) -> None:
        self.assertEqual(
            tuple(item["event_id"] for item in self.classification["events"]),
            TARGET_EVENT_IDS,
        )
        self.assertEqual(
            tuple(item["event_id"] for item in self.proposal["decisions"]),
            TARGET_EVENT_IDS,
        )

    def test_sneeze_is_authentic_sunnah_but_firstness_is_not(self) -> None:
        event = self.classification["events"][0]
        origins = {item["origin_classification"] for item in event["claims"]}
        self.assertIn("AUTHENTIC_SUNNAH", origins)
        self.assertIn("UNSUPPORTED_FIRSTNESS", origins)
        self.assertEqual(
            event["firstness_claim"],
            "PROHIBITED_UNLESS_DIRECTLY_PROVEN",
        )

    def test_firstness_cannot_be_relaxed(self) -> None:
        payload = copy.deepcopy(self.classification)
        payload["events"][0]["firstness_claim"] = "ALLOWED"
        with self.assertRaises(SourceOriginClassificationError):
            validate_source_origin_classification(payload)

    def test_loneliness_is_tafsir_report_not_marfu(self) -> None:
        loneliness = self.classification["events"][1]["loneliness_report"]
        self.assertEqual(
            loneliness["origin_classification"],
            "TAFSIR_REPORT_COMPOSITE_CHAIN_NOT_MARFU",
        )
        self.assertFalse(loneliness["assertive_narration_allowed"])

    def test_loneliness_is_not_falsely_called_definite_israiliyyat(self) -> None:
        loneliness = self.classification["events"][1]["loneliness_report"]
        self.assertFalse(loneliness["definite_israiliyyat_label"])
        self.assertTrue(loneliness["possible_israiliyyat_mixture"])

    def test_loneliness_requires_qualified_tafsir_attribution(self) -> None:
        loneliness = self.classification["events"][1]["loneliness_report"]
        self.assertEqual(
            loneliness["narration_mode"],
            "QUALIFIED_TAFSIR_ATTRIBUTION",
        )
        self.assertTrue(loneliness["source_mention_required_here"])

    def test_supported_synthesis_has_exact_premises(self) -> None:
        synthesis = self.classification["events"][1]["supported_synthesis"]
        self.assertEqual(
            synthesis["premises"],
            ["زوج آدم هي حواء", "المرأة خلقت من ضلع"],
        )
        self.assertEqual(synthesis["conclusion"], "حواء خلقت من ضلع آدم")
        self.assertFalse(synthesis["adds_unproved_detail"])

    def test_supported_synthesis_cannot_add_left_rib(self) -> None:
        payload = copy.deepcopy(self.classification)
        payload["events"][1]["supported_synthesis"]["conclusion"] = (
            "حواء خلقت من ضلع آدم الأيسر"
        )
        with self.assertRaises(SourceOriginClassificationError):
            validate_source_origin_classification(payload)

    def test_left_rib_sleep_and_flesh_are_explicit_israiliyyat(self) -> None:
        details = {
            item["detail_id"]: item
            for item in self.classification["events"][1]["secondary_details"]
        }
        for detail_id in (
            "left_rib",
            "sleep_during_creation",
            "place_filled_with_flesh",
        ):
            self.assertEqual(
                details[detail_id]["origin_classification"],
                "ISRAILIYYAT_EXPLICIT_ORIGIN",
            )
            self.assertEqual(details[detail_id]["default_narration"], "OMIT")

    def test_explicit_israiliyyat_cannot_be_made_assertive(self) -> None:
        payload = copy.deepcopy(self.classification)
        payload["events"][1]["secondary_details"][0][
            "origin_classification"
        ] = "AUTHENTIC_SUNNAH"
        with self.assertRaises(SourceOriginClassificationError):
            validate_source_origin_classification(payload)

    def test_dialogue_and_name_reason_remain_non_marfu_tafsir(self) -> None:
        details = {
            item["detail_id"]: item
            for item in self.classification["events"][1]["secondary_details"]
        }
        for detail_id in (
            "adam_hawa_dialogue",
            "angels_name_question",
            "name_reason_created_from_living",
        ):
            self.assertEqual(
                details[detail_id]["origin_classification"],
                "TAFSIR_REPORT_COMPOSITE_CHAIN_NOT_MARFU",
            )

    def test_name_hawa_source_scope_does_not_prove_name_reason(self) -> None:
        records = {
            item["source_record_id"]: item
            for item in self.classification["source_records"]
        }
        record = records[
            "SRCREC-HAWA-NAME-BUKHARI-3330-MUSLIM-1470"
        ]
        self.assertIn("لا يثبت سبب التسمية", record["claim_scope"])

    def test_rib_source_scope_excludes_left_and_sleep(self) -> None:
        records = {
            item["source_record_id"]: item
            for item in self.classification["source_records"]
        }
        record = records[
            "SRCREC-WOMAN-RIB-BUKHARI-3331-MUSLIM-1468"
        ]
        self.assertIn("دون تعيين اليسار أو النوم", record["claim_scope"])

    def test_ibn_ishaq_record_preserves_explicit_ahl_al_kitab_origin(self) -> None:
        records = {
            item["source_record_id"]: item
            for item in self.classification["source_records"]
        }
        record = records[
            "SRCREC-TABARI-8407-IBN-ISHAQ-AHL-AL-KITAB"
        ]
        self.assertEqual(
            record["origin_classification"],
            "ISRAILIYYAT_EXPLICIT_ORIGIN",
        )
        self.assertIn("أهل الكتاب", record["origin_note"])

    def test_al_suddi_records_are_not_marfu(self) -> None:
        records = self.classification["source_records"]
        relevant = [
            item for item in records
            if "SUDDI" in item["source_record_id"]
            and "TIRMIDHI" not in item["source_record_id"]
        ]
        self.assertTrue(relevant)
        self.assertTrue(
            all(
                item["origin_classification"]
                == "TAFSIR_REPORT_COMPOSITE_CHAIN_NOT_MARFU"
                for item in relevant
            )
        )

    def test_all_source_records_have_trace_and_no_auto_grade(self) -> None:
        for record in self.classification["source_records"]:
            self.assertTrue(record["references"])
            self.assertFalse(record["automatic_grade"])

    def test_tree_formula_is_exact(self) -> None:
        event = self.classification["events"][2]
        self.assertEqual(event["approved_narration_formula"], UNKNOWN_TREE_FORMULA)
        decision = self.proposal["decisions"][2]
        self.assertEqual(decision["proposed_narration"], UNKNOWN_TREE_FORMULA)

    def test_tree_type_and_visual_identification_are_prohibited(self) -> None:
        event = self.classification["events"][2]
        self.assertEqual(event["specific_tree_type_assertion"], "PROHIBITED")
        self.assertEqual(event["visual_type_identification"], "PROHIBITED")

    def test_tree_event_is_qualified_not_silently_omitted(self) -> None:
        decision = self.proposal["decisions"][2]
        self.assertEqual(decision["proposed_disposition"], "include_qualified")

    def test_proposed_dispositions_are_expected(self) -> None:
        self.assertEqual(
            [item["proposed_disposition"] for item in self.proposal["decisions"]],
            ["include_assertive", "include_qualified", "include_qualified"],
        )

    def test_proposal_contains_no_evidence_ids(self) -> None:
        self.assertTrue(
            all(item["evidence_ids"] == [] for item in self.proposal["decisions"])
        )

    def test_proposal_cannot_be_made_binding(self) -> None:
        payload = copy.deepcopy(self.proposal)
        payload["binding"] = True
        with self.assertRaises(SourceOriginClassificationError):
            validate_proposed_gap_adjudication(payload)

    def test_classification_hash_is_bound_to_proposal(self) -> None:
        self.assertEqual(
            self.proposal["classification_sha256"],
            canonical_json_sha256(self.classification),
        )

    def test_stale_classification_hash_is_rejected(self) -> None:
        payload = copy.deepcopy(self.proposal)
        payload["classification_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "projects/episode-001-adam/evidence"
            target.mkdir(parents=True)
            (target / "source-origin-classification-v1.json").write_text(
                json.dumps(self.classification, ensure_ascii=False),
                encoding="utf-8",
            )
            (target / "proposed-gap-adjudication-v1.json").write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaises(SourceOriginClassificationError):
                load_and_validate_bundle(root)

    def test_secret_like_field_is_rejected(self) -> None:
        payload = copy.deepcopy(self.classification)
        payload["api_key"] = "forbidden"
        with self.assertRaises(SourceOriginClassificationError):
            validate_source_origin_classification(payload)

    def test_raw_source_text_field_is_rejected(self) -> None:
        payload = copy.deepcopy(self.classification)
        payload["raw_text"] = "forbidden"
        with self.assertRaises(SourceOriginClassificationError):
            validate_source_origin_classification(payload)

    def test_bundle_is_deterministic(self) -> None:
        first = canonical_json_sha256(self.classification)
        second = canonical_json_sha256(
            json.loads(
                json.dumps(
                    self.classification,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        )
        self.assertEqual(first, second)

    def test_validation_manifest_writes_utf8_lf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "validation.json"
            manifest = write_validation_manifest(REPO_ROOT, output)
            raw = output.read_bytes()
            self.assertNotIn(b"\r\n", raw)
            self.assertEqual(manifest["status"], "PASS")
            self.assertFalse(manifest["human_approval"])

    def test_cli_runs_from_arbitrary_cwd(self) -> None:
        script = (
            REPO_ROOT
            / "scripts/fast_track/validate_adam_source_origins_v1.py"
        )
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "validation.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(script),
                    "--repo-root",
                    str(REPO_ROOT),
                    "--output",
                    str(output),
                ],
                cwd=temporary,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=True,
            )
            self.assertIn("STATUS=PASS_ADAM_SOURCE_ORIGIN_CLASSIFICATION", result.stdout)
            self.assertTrue(output.is_file())

    def test_editorial_direction_records_classified_loneliness(self) -> None:
        direction = json.loads(
            (
                REPO_ROOT
                / "projects/episode-001-adam/evidence/editorial-direction-v1.json"
            ).read_text(encoding="utf-8")
        )
        decision = next(
            item for item in direction["decisions"]
            if item["event_id"] == "EV-ADAM-071"
        )
        self.assertEqual(
            decision["loneliness_report"]["origin_classification"],
            "TAFSIR_REPORT_COMPOSITE_CHAIN_NOT_MARFU",
        )
        self.assertEqual(
            decision["loneliness_report"]["status"],
            "SOURCE_ORIGIN_CLASSIFIED_REVIEW_PENDING",
        )

    def test_editorial_direction_marks_explicit_israiliyyat_details(self) -> None:
        direction = json.loads(
            (
                REPO_ROOT
                / "projects/episode-001-adam/evidence/editorial-direction-v1.json"
            ).read_text(encoding="utf-8")
        )
        decision = next(
            item for item in direction["decisions"]
            if item["event_id"] == "EV-ADAM-071"
        )
        self.assertEqual(
            set(decision["explicit_israiliyyat_details"]),
            {
                "الضلع الأيسر",
                "خلق حواء أثناء نوم آدم",
                "التئام موضع الضلع لحمًا",
            },
        )

    def test_editorial_direction_references_new_bundle(self) -> None:
        direction = json.loads(
            (
                REPO_ROOT
                / "projects/episode-001-adam/evidence/editorial-direction-v1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            direction["proposed_gap_adjudication_file"],
            "evidence/proposed-gap-adjudication-v1.json",
        )
        self.assertTrue(
            all(
                item["source_origin_classification_file"]
                == "evidence/source-origin-classification-v1.json"
                for item in direction["decisions"]
            )
        )

    def test_editorial_direction_still_does_not_approve_evidence(self) -> None:
        direction = json.loads(
            (
                REPO_ROOT
                / "projects/episode-001-adam/evidence/editorial-direction-v1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            direction["evidence_gate_status"],
            EVIDENCE_GATE_STATUS,
        )
        self.assertEqual(
            direction["automatic_evidence_approval"],
            AUTOMATIC_APPROVAL_STATUS,
        )
        self.assertTrue(
            all(item["evidence_approval"] is False for item in direction["decisions"])
        )


if __name__ == "__main__":
    unittest.main()
