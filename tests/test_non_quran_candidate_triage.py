from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.non_quran_candidate_triage import (
    AUTO_APPROVAL,
    BUCKET_EDITORIAL,
    BUCKET_INTERNAL,
    BUCKET_LOCATOR,
    BUCKET_MANUAL,
    BUCKET_MENTION,
    BUCKET_NOTE,
    FACTUAL_EVENTS,
    GATE,
    LIVE_EXECUTION,
    TARGET_EVENTS,
    CandidateTriageError,
    build_policy,
    build_review_template,
    build_triage,
    build_verification_plan,
    canonical_sha256,
    classify_candidate,
    extract_locator_signals,
    load_backlog,
    load_harvest,
    text_sha256,
    validate_policy,
    validate_review_template,
    validate_triage,
    validate_verification_plan,
    write_local_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
BACKLOG = (
    ROOT
    / "projects/episode-001-adam/evidence/non-quran-research-backlog-v1.json"
)


def candidate(
    *, candidate_id: str, excerpt: str, role: str = "RESEARCH_ARTIFACT",
    hints=None, path: str = "research/sample.md", score: int = 40,
):
    return {
        "candidate_id": candidate_id,
        "event_id": "EV-ADAM-001",
        "path": path,
        "line_start": 1,
        "line_end": 3,
        "matched_tokens": ["EV-ADAM-001"],
        "artifact_role": role,
        "source_hints": hints or ["INTERNAL_REFERENCE"],
        "automatic_source_classification": False,
        "file_sha256": "a" * 64,
        "excerpt_sha256": text_sha256(excerpt),
        "normalised_excerpt_sha256": text_sha256(" ".join(excerpt.split())),
        "excerpt": excerpt,
        "research_priority_score": score,
    }


def synthetic_harvest(path: Path) -> None:
    events = []
    for event_id in TARGET_EVENTS:
        editorial = event_id == "EV-ADAM-099"
        samples = [
            candidate(
                candidate_id=f"{event_id}-locator",
                excerpt="صحيح البخاري 3191 نص مرشح",
                hints=["HADITH_CANDIDATE"],
                path="evidence/source-notes.md",
                score=75,
            ),
            candidate(
                candidate_id=f"{event_id}-mention",
                excerpt="ذكر الطبري رواية في هذا الباب",
                hints=["TAFSIR_OR_ATHAR_CANDIDATE"],
                path="research/notes.md",
                score=55,
            ),
            candidate(
                candidate_id=f"{event_id}-internal",
                excerpt='{"schema_version":"x","event_id":"EV-ADAM-001","human_decision":false}',
                role="CONTRACT_ARTIFACT",
                path="contracts/review-packet.json",
                score=20,
            ),
        ]
        for item in samples:
            item["event_id"] = event_id
        events.append({
            "event_id": event_id,
            "title": event_id,
            "section": "section",
            "event_kind": (
                "EDITORIAL_TRANSITION" if editorial else "FACTUAL_RESEARCH"
            ),
            "candidate_count": len(samples),
            "source_hint_counts": {},
            "candidates": samples,
            "research_status": "LOCAL_CANDIDATES_READY_FOR_VERIFICATION",
        })
    harvest = {
        "schema_version": "siraj-non-quran-research-harvest-v1",
        "status": "LOCAL_CANDIDATE_HARVEST_READY_HUMAN_RESEARCH_PENDING",
        "episode_id": "episode-001-adam",
        "harvest_id": "synthetic-harvest",
        "candidate_count": sum(len(event["candidates"]) for event in events),
        "event_count": len(events),
        "events": events,
    }
    path.write_text(
        json.dumps(harvest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class NonQuranCandidateTriageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backlog = load_backlog(BACKLOG)
        cls.policy = build_policy()
        cls.review = build_review_template(cls.backlog, cls.policy)
        cls.plan = build_verification_plan(cls.backlog, cls.policy)

    def test_target_event_counts(self):
        self.assertEqual(len(FACTUAL_EVENTS), 14)
        self.assertEqual(len(TARGET_EVENTS), 15)

    def test_locator_signal_from_source_name_and_number(self):
        signals = extract_locator_signals("صحيح البخاري 3191")
        self.assertTrue(signals["has_explicit_locator_signal"])
        self.assertIn("صحيح البخاري", signals["source_names"])
        self.assertIn("3191", signals["numbers"])

    def test_locator_signal_from_source_record_id(self):
        signals = extract_locator_signals(
            "SRCREC-ADAM-SNEEZE-TIRMIDHI-3368"
        )
        self.assertTrue(signals["has_explicit_locator_signal"])

    def test_locator_signal_from_url(self):
        signals = extract_locator_signals("https://example.org/source/1")
        self.assertTrue(signals["has_explicit_locator_signal"])

    def test_classifies_locator_candidate(self):
        item = classify_candidate(
            candidate=candidate(
                candidate_id="c1",
                excerpt="صحيح مسلم 2653",
                hints=["HADITH_CANDIDATE"],
            ),
            event_kind="FACTUAL_RESEARCH",
        )
        self.assertEqual(item["triage_bucket"], BUCKET_LOCATOR)
        self.assertTrue(item["selected_for_source_verification_pool"])

    def test_classifies_source_mention(self):
        item = classify_candidate(
            candidate=candidate(
                candidate_id="c2",
                excerpt="ذكر الطبري هذا الخبر",
                hints=["TAFSIR_OR_ATHAR_CANDIDATE"],
            ),
            event_kind="FACTUAL_RESEARCH",
        )
        self.assertEqual(item["triage_bucket"], BUCKET_MENTION)

    def test_classifies_research_note(self):
        item = classify_candidate(
            candidate=candidate(
                candidate_id="c3",
                excerpt="ملاحظة بحثية بلا مصدر محدد",
                role="RESEARCH_ARTIFACT",
            ),
            event_kind="FACTUAL_RESEARCH",
        )
        self.assertEqual(item["triage_bucket"], BUCKET_NOTE)

    def test_classifies_internal_echo(self):
        item = classify_candidate(
            candidate=candidate(
                candidate_id="c4",
                excerpt=(
                    '{"schema_version":"x","human_decision":false,'
                    '"evidence_gate_status":"WITHHELD"}'
                ),
                role="CONTRACT_ARTIFACT",
                path="contracts/review-packet.json",
            ),
            event_kind="FACTUAL_RESEARCH",
        )
        self.assertEqual(item["triage_bucket"], BUCKET_INTERNAL)
        self.assertFalse(item["selected_for_source_verification_pool"])

    def test_editorial_event_never_selects_source(self):
        item = classify_candidate(
            candidate=candidate(
                candidate_id="c5",
                excerpt="صحيح البخاري 3191",
                hints=["HADITH_CANDIDATE"],
            ),
            event_kind="EDITORIAL_TRANSITION",
        )
        self.assertEqual(item["triage_bucket"], BUCKET_EDITORIAL)
        self.assertFalse(item["selected_for_source_verification_pool"])

    def test_candidate_checksum_guard(self):
        item = candidate(candidate_id="bad", excerpt="text")
        item["excerpt_sha256"] = "0" * 64
        with self.assertRaises(CandidateTriageError):
            classify_candidate(item, event_kind="FACTUAL_RESEARCH")

    def test_policy_schema_and_guards(self):
        self.assertEqual(self.policy["selection_limit_per_factual_event"], 8)
        self.assertFalse(self.policy["human_approval"])
        self.assertEqual(self.policy["evidence_gate_status"], GATE)

    def test_review_template_is_blank(self):
        self.assertEqual(len(self.review["decisions"]), 15)
        self.assertTrue(all(
            not decision["selected_candidate_ids"]
            and not decision["approved"]
            and not decision["human_decision"]
            for decision in self.review["decisions"]
        ))

    def test_review_editorial_disposition_only(self):
        editorial = next(
            item for item in self.review["decisions"]
            if item["event_id"] == "EV-ADAM-099"
        )
        factual = [
            item for item in self.review["decisions"]
            if item["event_id"] != "EV-ADAM-099"
        ]
        self.assertEqual(editorial["proposed_disposition"], "editorial_only")
        self.assertTrue(all(not item["proposed_disposition"] for item in factual))

    def test_verification_plan_covers_14_factual_events(self):
        covered = tuple(
            event_id
            for batch in self.plan["batches"]
            for event_id in batch["event_ids"]
        )
        self.assertEqual(covered, FACTUAL_EVENTS)

    def test_verification_plan_excludes_editorial_from_research(self):
        self.assertFalse(self.plan["editorial_event"]["research_required"])

    def test_build_triage_selects_top_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            harvest = Path(tmp) / "harvest.json"
            synthetic_harvest(harvest)
            triage, policy, review, plan, clusters, locators = build_triage(
                harvest_path=harvest,
                backlog_path=BACKLOG,
            )
            self.assertEqual(triage["event_count"], 15)
            self.assertGreater(triage["selected_candidate_count"], 0)
            self.assertEqual(
                next(
                    event for event in triage["events"]
                    if event["event_id"] == "EV-ADAM-099"
                )["selected_candidate_count"],
                0,
            )
            self.assertGreater(clusters["cluster_count"], 0)
            self.assertGreater(locators["locator_count"], 0)

    def test_triage_never_selects_more_than_eight(self):
        with tempfile.TemporaryDirectory() as tmp:
            harvest = Path(tmp) / "harvest.json"
            synthetic_harvest(harvest)
            data = json.loads(harvest.read_text(encoding="utf-8"))
            event = data["events"][0]
            base = event["candidates"][0]
            for index in range(20):
                clone = copy.deepcopy(base)
                clone["candidate_id"] = f"extra-{index}"
                clone["excerpt"] = f"صحيح مسلم {2000 + index}"
                clone["excerpt_sha256"] = text_sha256(clone["excerpt"])
                clone["normalised_excerpt_sha256"] = clone["excerpt_sha256"]
                event["candidates"].append(clone)
            data["candidate_count"] = sum(
                len(item["candidates"]) for item in data["events"]
            )
            harvest.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
            triage, *_ = build_triage(
                harvest_path=harvest,
                backlog_path=BACKLOG,
            )
            first = triage["events"][0]
            self.assertEqual(first["selected_candidate_count"], 8)

    def test_triage_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            harvest = Path(tmp) / "harvest.json"
            synthetic_harvest(harvest)
            one = build_triage(
                harvest_path=harvest, backlog_path=BACKLOG
            )
            two = build_triage(
                harvest_path=harvest, backlog_path=BACKLOG
            )
            self.assertEqual(
                canonical_sha256(one[0]), canonical_sha256(two[0])
            )

    def test_no_automatic_authentication_or_grading(self):
        with tempfile.TemporaryDirectory() as tmp:
            harvest = Path(tmp) / "harvest.json"
            synthetic_harvest(harvest)
            triage, *_ = build_triage(
                harvest_path=harvest, backlog_path=BACKLOG
            )
            for event in triage["events"]:
                for item in event["all_candidates"]:
                    self.assertFalse(item["automatic_source_authentication"])
                    self.assertFalse(item["automatic_hadith_grading"])
                    self.assertFalse(item["automatic_origin_classification"])

    def test_global_guards(self):
        for data in (self.policy, self.review, self.plan):
            self.assertEqual(data["evidence_gate_status"], GATE)
            self.assertEqual(data["automatic_evidence_approval"], AUTO_APPROVAL)
            self.assertEqual(data["live_provider_execution"], LIVE_EXECUTION)

    def test_validation_rejects_preapproved_review(self):
        changed = copy.deepcopy(self.review)
        changed["decisions"][0]["approved"] = True
        with self.assertRaises(CandidateTriageError):
            validate_review_template(changed)

    def test_validation_rejects_plan_event_loss(self):
        changed = copy.deepcopy(self.plan)
        changed["batches"][0]["event_ids"].pop()
        with self.assertRaises(CandidateTriageError):
            validate_verification_plan(changed)

    def test_write_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            harvest = root / "harvest.json"
            synthetic_harvest(harvest)
            triage, policy, review, plan, clusters, locators = build_triage(
                harvest_path=harvest, backlog_path=BACKLOG
            )
            outputs = write_local_outputs(
                output_root=root / "report",
                triage=triage,
                policy=policy,
                review=review,
                plan=plan,
                clusters=clusters,
                locator_index=locators,
            )
            self.assertTrue(outputs["archive"].is_file())
            self.assertTrue(outputs["ranking_csv"].is_file())
            self.assertEqual(
                len(list((root / "report/event-dossiers").glob("*.md"))),
                15,
            )
            self.assertEqual(
                len(list((root / "report/verification-batches").glob("*.json"))),
                3,
            )

    def test_json_outputs_use_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            from src.application.storyboard_runtime.non_quran_candidate_triage import write_json
            write_json(path, self.policy)
            raw = path.read_bytes()
            self.assertNotIn(b"\r\n", raw)
            self.assertTrue(raw.endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
