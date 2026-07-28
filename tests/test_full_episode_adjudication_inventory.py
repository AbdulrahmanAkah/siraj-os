from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.full_episode_adjudication_inventory import (
    AUTO_APPROVAL, GATE, LIVE_EXECUTION, SCHEMA, STATUS,
    FullEpisodeInventoryError, build_inventory, canonical_sha256,
    validate_inventory, write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
EVENT_MAP = ROOT / "projects/episode-001-adam/editorial/event-map.json"
PROJECT = ROOT / "projects/episode-001-adam"
CLASSIFICATION = PROJECT / "evidence/source-origin-classification-v1.json"
APPROVAL = PROJECT / "evidence/gap-human-approval-v1.json"


class FullEpisodeInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The legacy full-suite tests may temporarily rewrite event-map.json.
        # Reconstruct an isolated canonical 37-event map from the tracked
        # baseline inventory generated before the suite starts.
        baseline_path = (
            PROJECT
            / "evidence/full-episode-adjudication-inventory-v1.json"
        )
        baseline = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
        event_fields = (
            "event_id",
            "order",
            "section",
            "title",
            "importance",
            "duration_weight",
            "chronology_type",
            "verification_status",
            "question_ids",
        )
        canonical_events = [
            {key: item[key] for key in event_fields}
            for item in baseline["events"]
        ]
        cls._temporary = tempfile.TemporaryDirectory()
        cls.isolated_event_map = (
            Path(cls._temporary.name) / "event-map.json"
        )
        cls.isolated_event_map.write_text(
            json.dumps(
                canonical_events,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        cls.data = build_inventory(
            event_map_path=cls.isolated_event_map,
            project_root=PROJECT,
            source_classification_path=CLASSIFICATION,
            human_approval_path=APPROVAL,
            include_local_scan=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls._temporary.cleanup()

    def test_schema_status_and_count(self):
        self.assertEqual(self.data["schema_version"], SCHEMA)
        self.assertEqual(self.data["status"], STATUS)
        self.assertEqual(self.data["event_count"], 37)

    def test_all_event_ids_are_unique(self):
        ids = [x["event_id"] for x in self.data["events"]]
        self.assertEqual(len(ids), 37)
        self.assertEqual(len(set(ids)), 37)

    def test_exact_human_approved_gaps(self):
        approved = [x["event_id"] for x in self.data["events"]
                    if x["human_gap_decision_recorded"]]
        self.assertEqual(approved, ["EV-ADAM-031", "EV-ADAM-071", "EV-ADAM-091"])

    def test_gap_dispositions_are_preserved(self):
        by_id = {x["event_id"]: x for x in self.data["events"]}
        self.assertEqual(by_id["EV-ADAM-031"]["approved_gap_disposition"], "include_assertive")
        self.assertEqual(by_id["EV-ADAM-071"]["approved_gap_disposition"], "include_qualified")
        self.assertEqual(by_id["EV-ADAM-091"]["approved_gap_disposition"], "include_qualified")

    def test_quran_explicit_events_are_binding_pending(self):
        for item in self.data["events"]:
            if item["verification_status"] == "quran_explicit":
                self.assertEqual(item["readiness"], "QURAN_SOURCE_BINDING_PENDING")

    def test_human_gaps_are_not_fully_bound(self):
        for event_id in ("EV-ADAM-031", "EV-ADAM-071", "EV-ADAM-091"):
            item = next(x for x in self.data["events"] if x["event_id"] == event_id)
            self.assertEqual(item["readiness"], "HUMAN_DECISION_RECORDED_BINDING_PENDING")

    def test_gate_remains_withheld(self):
        self.assertEqual(self.data["evidence_gate_status"], GATE)
        self.assertEqual(self.data["automatic_evidence_approval"], AUTO_APPROVAL)
        self.assertEqual(self.data["live_provider_execution"], LIVE_EXECUTION)

    def test_no_binding_readiness(self):
        self.assertTrue(all(v is False for v in self.data["binding_readiness"].values()))

    def test_recommended_batch_is_bounded(self):
        self.assertGreater(len(self.data["recommended_next_batch"]), 0)
        self.assertLessEqual(len(self.data["recommended_next_batch"]), 12)

    def test_scan_does_not_retain_raw_text(self):
        self.assertFalse(self.data["scan_summary"]["raw_text_retained"])

    def test_inventory_is_deterministic(self):
        second = build_inventory(
            event_map_path=self.isolated_event_map,
            project_root=PROJECT,
            source_classification_path=CLASSIFICATION,
            human_approval_path=APPROVAL,
            include_local_scan=True,
        )
        self.assertEqual(canonical_sha256(self.data), canonical_sha256(second))

    def test_external_four_event_map_cannot_affect_isolated_inventory(self):
        canonical_events = json.loads(
            self.isolated_event_map.read_text(encoding="utf-8")
        )
        with tempfile.TemporaryDirectory() as tmp:
            mutated_event_map = Path(tmp) / "event-map.json"
            mutated_event_map.write_text(
                json.dumps(
                    canonical_events[:4],
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
            with self.assertRaises(FullEpisodeInventoryError):
                build_inventory(
                    event_map_path=mutated_event_map,
                    project_root=PROJECT,
                    source_classification_path=CLASSIFICATION,
                    human_approval_path=APPROVAL,
                    include_local_scan=True,
                )

        rebuilt = build_inventory(
            event_map_path=self.isolated_event_map,
            project_root=PROJECT,
            source_classification_path=CLASSIFICATION,
            human_approval_path=APPROVAL,
            include_local_scan=True,
        )
        self.assertEqual(rebuilt["event_count"], 37)
        self.assertEqual(
            canonical_sha256(rebuilt),
            canonical_sha256(self.data),
        )

    def test_validation_rejects_gate_open(self):
        changed = copy.deepcopy(self.data)
        changed["evidence_gate_status"] = "OPEN"
        with self.assertRaises(FullEpisodeInventoryError):
            validate_inventory(changed)

    def test_validation_rejects_auto_approval(self):
        changed = copy.deepcopy(self.data)
        changed["automatic_evidence_approval"] = "ALLOWED"
        with self.assertRaises(FullEpisodeInventoryError):
            validate_inventory(changed)

    def test_validation_rejects_missing_event(self):
        changed = copy.deepcopy(self.data)
        changed["events"].pop()
        with self.assertRaises(FullEpisodeInventoryError):
            validate_inventory(changed)

    def test_outputs_are_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(Path(tmp), self.data)
            self.assertEqual(set(outputs), {
                "inventory", "coverage_csv", "next_batch", "backlog", "readme"
            })
            for path in outputs.values():
                self.assertTrue(path.is_file())

    def test_json_outputs_are_utf8_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(Path(tmp), self.data)
            raw = outputs["inventory"].read_bytes()
            self.assertNotIn(b"\r\n", raw)
            self.assertTrue(raw.endswith(b"\n"))
            json.loads(raw.decode("utf-8"))

if __name__ == "__main__":
    unittest.main()
