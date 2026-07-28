from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.non_quran_research_harvest import (
    AUTO_APPROVAL,
    EDITORIAL_EVENTS,
    FACTUAL_EVENTS,
    GATE,
    HARVEST_SCHEMA,
    LIVE_EXECUTION,
    PROMPT_SCHEMA,
    STATUS,
    TARGET_EVENTS,
    NonQuranHarvestError,
    build_backlog,
    build_editorial_review_template,
    build_harvest,
    build_prompt_pack,
    canonical_sha256,
    load_target_events,
    scan_local_candidates,
    text_sha256,
    validate_backlog,
    validate_editorial_review_template,
    validate_harvest,
    validate_prompt_pack,
    write_local_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = (
    ROOT
    / "projects/episode-001-adam/evidence/full-episode-adjudication-inventory-v1.json"
)


class NonQuranResearchHarvestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = load_target_events(INVENTORY)
        cls.backlog = build_backlog(cls.events)
        cls.prompts = build_prompt_pack(cls.events)
        cls.editorial = build_editorial_review_template(cls.events)

    def test_exact_target_counts(self):
        self.assertEqual(len(FACTUAL_EVENTS), 14)
        self.assertEqual(EDITORIAL_EVENTS, ("EV-ADAM-099",))
        self.assertEqual(len(TARGET_EVENTS), 15)

    def test_inventory_target_set(self):
        self.assertEqual(
            tuple(event["event_id"] for event in self.events),
            TARGET_EVENTS,
        )

    def test_no_quran_explicit_events(self):
        self.assertTrue(all(
            event["verification_status"] != "quran_explicit"
            for event in self.events
        ))

    def test_no_human_approved_gap_events(self):
        self.assertTrue(all(
            not event["human_gap_decision_recorded"]
            for event in self.events
        ))

    def test_backlog_schema_and_counts(self):
        self.assertEqual(self.backlog["factual_event_count"], 14)
        self.assertEqual(self.backlog["editorial_event_count"], 1)
        self.assertEqual(self.backlog["event_count"], 15)

    def test_editorial_099_is_not_source_research(self):
        item = next(
            item for item in self.backlog["items"]
            if item["event_id"] == "EV-ADAM-099"
        )
        self.assertEqual(item["recommended_disposition"], "editorial_only")
        self.assertFalse(item["research_required"])

    def test_prompt_pack_covers_all_events_once(self):
        covered = [
            event_id
            for batch in self.prompts["batches"]
            for event_id in batch["event_ids"]
        ]
        self.assertEqual(tuple(covered), TARGET_EVENTS)
        self.assertEqual(self.prompts["schema_version"], PROMPT_SCHEMA)

    def test_prompts_forbid_automatic_adjudication(self):
        self.assertTrue(all(
            batch["automatic_adjudication"] is False
            for batch in self.prompts["batches"]
        ))

    def test_editorial_template_is_blank(self):
        self.assertFalse(self.editorial["approved"])
        self.assertFalse(self.editorial["human_decision"])
        self.assertFalse(self.editorial["approved_by"])
        self.assertFalse(self.editorial["approved_at"])

    def test_scan_captures_event_and_question_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            evidence = project / "evidence"
            evidence.mkdir()
            (evidence / "sample.md").write_text(
                "before\nEV-ADAM-001 RQ-ADAM-001 حديث البخاري\n"
                "after\nRQ-ADAM-002 تفسير الطبري\n",
                encoding="utf-8",
            )
            subset = self.events[:2]
            candidates, scan = scan_local_candidates(
                project_root=project,
                target_events=subset,
                context_lines=1,
            )
            self.assertEqual(scan["files_scanned"], 1)
            self.assertTrue(candidates["EV-ADAM-001"])
            self.assertTrue(candidates["EV-ADAM-002"])

    def test_scan_deduplicates_same_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "a.md").write_text(
                "EV-ADAM-001\nEV-ADAM-001\n",
                encoding="utf-8",
            )
            candidates, _ = scan_local_candidates(
                project_root=project,
                target_events=self.events[:1],
                context_lines=5,
            )
            self.assertEqual(len(candidates["EV-ADAM-001"]), 1)

    def test_candidate_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "a.md").write_text(
                "EV-ADAM-001 حديث مسلم",
                encoding="utf-8",
            )
            candidates, _ = scan_local_candidates(
                project_root=project,
                target_events=self.events[:1],
            )
            candidate = candidates["EV-ADAM-001"][0]
            self.assertEqual(
                candidate["excerpt_sha256"],
                text_sha256(candidate["excerpt"]),
            )

    def test_source_hints_are_not_classifications(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "a.md").write_text(
                "EV-ADAM-001 تفسير الطبري",
                encoding="utf-8",
            )
            candidates, _ = scan_local_candidates(
                project_root=project,
                target_events=self.events[:1],
            )
            candidate = candidates["EV-ADAM-001"][0]
            self.assertIn("TAFSIR_OR_ATHAR_CANDIDATE", candidate["source_hints"])
            self.assertFalse(candidate["automatic_source_classification"])

    def test_backlog_deterministic(self):
        self.assertEqual(
            canonical_sha256(build_backlog(self.events)),
            canonical_sha256(self.backlog),
        )

    def test_prompt_pack_deterministic(self):
        self.assertEqual(
            canonical_sha256(build_prompt_pack(self.events)),
            canonical_sha256(self.prompts),
        )

    def test_rejects_backlog_event_change(self):
        changed = copy.deepcopy(self.backlog)
        changed["event_ids"][-1] = "EV-ADAM-090"
        with self.assertRaises(NonQuranHarvestError):
            validate_backlog(changed)

    def test_rejects_editorial_preapproval(self):
        changed = copy.deepcopy(self.editorial)
        changed["approved"] = True
        with self.assertRaises(NonQuranHarvestError):
            validate_editorial_review_template(changed)

    def test_build_harvest_without_snippets(self):
        harvest, backlog, prompts, editorial, manifest = build_harvest(
            inventory_path=INVENTORY,
            project_root=ROOT / "projects/episode-001-adam",
            include_snippets=False,
        )
        self.assertEqual(harvest["schema_version"], HARVEST_SCHEMA)
        self.assertEqual(harvest["status"], STATUS)
        self.assertEqual(harvest["event_count"], 15)
        self.assertEqual(harvest["candidate_count"], 0)
        self.assertEqual(manifest["file_count"], 0)

    def test_global_guards(self):
        for data in (self.backlog, self.prompts, self.editorial):
            self.assertEqual(data["evidence_gate_status"], GATE)
            self.assertEqual(data["automatic_evidence_approval"], AUTO_APPROVAL)
            self.assertEqual(data["live_provider_execution"], LIVE_EXECUTION)

    def test_write_outputs(self):
        harvest, backlog, prompts, editorial, manifest = build_harvest(
            inventory_path=INVENTORY,
            project_root=ROOT / "projects/episode-001-adam",
            include_snippets=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_local_outputs(
                output_root=Path(tmp) / "report",
                harvest=harvest,
                backlog=backlog,
                prompt_pack=prompts,
                editorial=editorial,
                manifest=manifest,
            )
            self.assertTrue(outputs["archive"].is_file())
            self.assertTrue(outputs["coverage_csv"].is_file())
            self.assertEqual(
                len(list((Path(tmp) / "report/event-review").glob("*.md"))),
                15,
            )


if __name__ == "__main__":
    unittest.main()
