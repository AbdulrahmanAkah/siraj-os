from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.application.storyboard_runtime.narration_intent import (
    ADAM_EDITORIAL_DIRECTION_SCHEMA,
    AUTOMATIC_APPROVAL_STATUS,
    CREATOR_EDITORIAL_INTENT_SCHEMA,
    DIRECTION_STATUS,
    EVIDENCE_GATE_STATUS,
    HISTORICAL_NARRATION_POLICY_SCHEMA,
    LIVE_EXECUTION_STATUS,
    UNKNOWN_TREE_FORMULA,
    NarrationIntentError,
    canonical_json_sha256,
    load_and_validate_bundle,
    validate_adam_editorial_direction,
    validate_creator_editorial_intent,
    validate_historical_narration_policy,
    write_validation_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
NARRATION_PATH = ROOT / "config/historical_narration_policy_v1.json"
CREATOR_PATH = ROOT / "config/creator_editorial_intent_v1.json"
DIRECTION_PATH = (
    ROOT / "projects/episode-001-adam/evidence/editorial-direction-v1.json"
)
EVENT_MAP_PATH = ROOT / "projects/episode-001-adam/editorial/event-map.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


class NarrationIntentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.narration = read_json(NARRATION_PATH)
        self.creator = read_json(CREATOR_PATH)
        self.direction = read_json(DIRECTION_PATH)
        self.event_map = read_json(EVENT_MAP_PATH)

    def test_schema_and_status_contracts(self) -> None:
        self.assertEqual(
            self.narration["schema_version"],
            HISTORICAL_NARRATION_POLICY_SCHEMA,
        )
        self.assertEqual(
            self.creator["schema_version"],
            CREATOR_EDITORIAL_INTENT_SCHEMA,
        )
        self.assertEqual(
            self.direction["schema_version"],
            ADAM_EDITORIAL_DIRECTION_SCHEMA,
        )
        self.assertEqual(self.direction["status"], DIRECTION_STATUS)

    def test_validates_complete_bundle(self) -> None:
        manifest = load_and_validate_bundle(
            narration_policy_path=NARRATION_PATH,
            creator_intent_path=CREATOR_PATH,
            adam_direction_path=DIRECTION_PATH,
            event_map_path=EVENT_MAP_PATH,
        )
        self.assertEqual(manifest["status"], "PASS")
        self.assertTrue(
            manifest["bundle_id"].startswith("narration_intent_bundle_")
        )

    def test_bundle_is_deterministic(self) -> None:
        first = load_and_validate_bundle(
            narration_policy_path=NARRATION_PATH,
            creator_intent_path=CREATOR_PATH,
            adam_direction_path=DIRECTION_PATH,
            event_map_path=EVENT_MAP_PATH,
        )
        second = load_and_validate_bundle(
            narration_policy_path=NARRATION_PATH,
            creator_intent_path=CREATOR_PATH,
            adam_direction_path=DIRECTION_PATH,
            event_map_path=EVENT_MAP_PATH,
        )
        self.assertEqual(first, second)
        self.assertEqual(
            canonical_json_sha256(first),
            canonical_json_sha256(second),
        )

    def test_policy_cannot_open_evidence_gate(self) -> None:
        changed = copy.deepcopy(self.narration)
        changed["evidence_gate_effect"] = "OPEN"
        with self.assertRaises(NarrationIntentError):
            validate_historical_narration_policy(changed)

    def test_direction_keeps_gate_withheld(self) -> None:
        self.assertEqual(
            self.direction["evidence_gate_status"],
            EVIDENCE_GATE_STATUS,
        )
        self.assertEqual(
            self.direction["automatic_evidence_approval"],
            AUTOMATIC_APPROVAL_STATUS,
        )
        self.assertEqual(
            self.direction["live_provider_execution"],
            LIVE_EXECUTION_STATUS,
        )

    def test_automatic_evidence_approval_is_rejected(self) -> None:
        changed = copy.deepcopy(self.direction)
        changed["automatic_evidence_approval"] = "ALLOWED"
        with self.assertRaises(NarrationIntentError):
            validate_adam_editorial_direction(changed)

    def test_unsupported_firstness_is_globally_prohibited(self) -> None:
        firstness = self.narration["unsupported_firstness_policy"]
        self.assertEqual(
            firstness["status"],
            "PROHIBITED_WITHOUT_DIRECT_SOUND_EVIDENCE",
        )
        self.assertIn("first movement", firstness["covered_claims"])
        self.assertIn("first speech", firstness["covered_claims"])

    def test_firstness_policy_cannot_be_relaxed(self) -> None:
        changed = copy.deepcopy(self.narration)
        changed["unsupported_firstness_policy"]["status"] = "OPTIONAL"
        with self.assertRaises(NarrationIntentError):
            validate_historical_narration_policy(changed)

    def test_israiliyyat_requires_explicit_label(self) -> None:
        rules = self.narration["israiliyyat_policy"]
        self.assertTrue(rules["must_be_explicitly_labeled_in_narration"])
        self.assertFalse(rules["assertive_language"])

    def test_israiliyyat_cannot_establish_creed_or_law(self) -> None:
        rules = self.narration["israiliyyat_policy"]
        self.assertFalse(rules["may_establish_creed"])
        self.assertFalse(rules["may_establish_law"])

    def test_israiliyyat_label_cannot_be_disabled(self) -> None:
        changed = copy.deepcopy(self.narration)
        changed["israiliyyat_policy"][
            "must_be_explicitly_labeled_in_narration"
        ] = False
        with self.assertRaises(NarrationIntentError):
            validate_historical_narration_policy(changed)

    def test_supported_synthesis_requires_two_premises(self) -> None:
        synthesis = self.narration["supported_synthesis_policy"]
        self.assertEqual(
            synthesis["minimum_independently_established_premises"],
            2,
        )
        self.assertTrue(synthesis["premise_trace_required"])
        self.assertTrue(synthesis["conclusion_must_not_add_unproved_detail"])

    def test_supported_synthesis_cannot_add_left_rib(self) -> None:
        example = self.narration["supported_synthesis_policy"]["example"]
        self.assertEqual(
            example["permitted_conclusion"],
            "حواء خلقت من ضلع آدم",
        )
        self.assertIn("الضلع الأيسر", example["forbidden_extensions"])
        self.assertIn("خلقها أثناء نوم آدم", example["forbidden_extensions"])

    def test_source_names_are_sparing_by_default(self) -> None:
        source = self.narration["source_mention_policy"]
        self.assertEqual(
            source["default_narration"],
            "DO_NOT_OVERLOAD_WITH_SOURCE_NAMES",
        )
        self.assertTrue(source["source_trace_always_kept_in_evidence_records"])

    def test_sensitive_source_attribution_triggers_are_fixed(self) -> None:
        triggers = set(
            self.narration["source_mention_policy"][
                "mandatory_audience_attribution_triggers"
            ]
        )
        self.assertIn("doctrinal_ambiguity", triggers)
        self.assertIn("serious_moral_or_personal_confusion", triggers)
        self.assertIn("israiliyyat", triggers)
        self.assertIn("weak_report", triggers)
        self.assertIn("material_dispute", triggers)

    def test_unknown_tree_formula_is_exact(self) -> None:
        self.assertEqual(
            self.narration["qualified_language_policy"][
                "uncertain_specific_template"
            ],
            UNKNOWN_TREE_FORMULA,
        )
        self.assertEqual(
            self.direction["decisions"][2]["approved_narration_formula"],
            UNKNOWN_TREE_FORMULA,
        )

    def test_tree_specific_type_assertion_is_prohibited(self) -> None:
        tree = self.direction["decisions"][2]
        self.assertEqual(tree["specific_type_assertion"], "PROHIBITED")
        self.assertEqual(
            tree["direction_disposition"],
            "INCLUDE_QUALIFIED_UNCERTAINTY",
        )

    def test_tree_visual_remains_unidentified(self) -> None:
        visual = self.direction["decisions"][2]["visual_rule"]
        self.assertIn("non-identifiable", visual)
        self.assertIn("wheat", visual)
        self.assertIn("grape", visual)
        self.assertIn("fig", visual)

    def test_adam_031_removes_firstness_from_narration_title(self) -> None:
        decision = self.direction["decisions"][0]
        self.assertEqual(
            decision["event_title_override_for_narration"],
            "عطاس آدم وحمده لله",
        )
        prohibited = " ".join(
            decision["prohibited_without_direct_sound_evidence"]
        )
        self.assertIn("أول حركة", prohibited)
        self.assertIn("أول كلام", prohibited)

    def test_adam_031_does_not_approve_evidence(self) -> None:
        self.assertFalse(self.direction["decisions"][0]["evidence_approval"])

    def test_adam_071_supported_synthesis_is_recorded(self) -> None:
        synthesis = self.direction["decisions"][1][
            "assertive_supported_synthesis_after_source_binding"
        ]
        self.assertEqual(len(synthesis["premises"]), 2)
        self.assertEqual(synthesis["conclusion"], "حواء خلقت من ضلع آدم")

    def test_loneliness_report_remains_qualified_until_classified(self) -> None:
        report = self.direction["decisions"][1]["loneliness_report"]
        self.assertEqual(
            report["status"],
            "SOURCE_ORIGIN_CLASSIFICATION_PENDING",
        )
        self.assertEqual(report["narration_until_classified"], "QUALIFIED_ONLY")
        self.assertEqual(
            report["if_israiliyyat"],
            "EXPLICIT_ISRAILIYYAT_LABEL_REQUIRED",
        )

    def test_left_rib_sleep_and_dialogue_require_origin_or_omission(self) -> None:
        details = set(
            self.direction["decisions"][1][
                "details_requiring_origin_label_or_omission"
            ]
        )
        self.assertIn("الضلع الأيسر", details)
        self.assertIn("خلق حواء أثناء نوم آدم", details)
        self.assertIn("الحوار المنقول بين آدم وحواء", details)

    def test_creator_profile_reuses_feedback_without_reasking(self) -> None:
        future = self.narration["future_episode_application"]
        self.assertTrue(future["reuse_without_reasking_creator"])
        self.assertTrue(future["new_creator_feedback_updates_profile"])
        preferences = self.creator["preferences"]
        self.assertEqual(preferences["repeat_explanations_to_creator"], "AVOID")
        self.assertEqual(
            preferences["early_episode_feedback"],
            "GENERALIZE_TO_FUTURE_EPISODES",
        )

    def test_direction_references_real_adam_events(self) -> None:
        validate_adam_editorial_direction(
            self.direction,
            event_map=self.event_map,
        )

    def test_missing_event_is_rejected(self) -> None:
        changed_map = [
            item for item in self.event_map
            if item["event_id"] != "EV-ADAM-091"
        ]
        with self.assertRaises(NarrationIntentError):
            validate_adam_editorial_direction(
                self.direction,
                event_map=changed_map,
            )

    def test_secret_like_field_is_rejected(self) -> None:
        changed = copy.deepcopy(self.creator)
        changed["api_key"] = "forbidden"
        with self.assertRaises(NarrationIntentError):
            validate_creator_editorial_intent(changed)

    def test_validation_manifest_writes_utf8_lf(self) -> None:
        manifest = load_and_validate_bundle(
            narration_policy_path=NARRATION_PATH,
            creator_intent_path=CREATOR_PATH,
            adam_direction_path=DIRECTION_PATH,
            event_map_path=EVENT_MAP_PATH,
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            write_validation_manifest(path, manifest)
            data = path.read_bytes()
        self.assertNotIn(b"\r\n", data)
        self.assertTrue(data.endswith(b"\n"))
        json.loads(data.decode("utf-8"))

    def test_cli_runs_from_arbitrary_cwd(self) -> None:
        script = (
            ROOT
            / "scripts/fast_track/validate_narration_intent_v1.py"
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(script),
                    "--repo-root",
                    str(ROOT),
                    "--output",
                    str(Path(temporary) / "validation.json"),
                ],
                cwd=temporary,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("STATUS=PASS_NARRATION_INTENT_BUNDLE", result.stdout)
        self.assertIn("CURRENT_EVIDENCE_GATE=WITHHELD", result.stdout)


if __name__ == "__main__":
    unittest.main()
