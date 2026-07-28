from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.non_quran_source_verification_execution import (
    AUTO_APPROVAL,
    BUCKET_LOCATOR,
    BUCKET_MANUAL,
    BUCKET_MENTION,
    BUCKET_NOTE,
    EXECUTION_SCHEMA,
    FACTUAL_EVENTS,
    GATE,
    LIVE_EXECUTION,
    RECORD_SCHEMA,
    REVIEW_SCHEMA,
    ROUTE_DISCOVERY,
    ROUTE_EDITORIAL,
    ROUTE_LOCATOR,
    ROUTE_MENTION,
    TARGET_EVENTS,
    VerificationExecutionError,
    build_execution,
    build_policy,
    build_record_template,
    canonical_sha256,
    consolidate_selected_candidates,
    determine_route,
    load_backlog,
    load_triage,
    load_verification_plan,
    text_sha256,
    validate_execution,
    validate_policy,
    validate_record_template,
    validate_review_template,
    verification_key,
    write_local_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
BACKLOG = (
    ROOT
    / "projects/episode-001-adam/evidence/non-quran-research-backlog-v1.json"
)
PLAN = (
    ROOT
    / "projects/episode-001-adam/evidence/non-quran-source-verification-plan-v1.json"
)


def selected_candidate(
    *, event_id: str, candidate_id: str, excerpt: str,
    bucket: str = BUCKET_LOCATOR, score: int = 90,
    names=None, numbers=None, record_ids=None, urls=None, pages=None,
):
    return {
        "candidate_id": candidate_id,
        "event_id": event_id,
        "path": "evidence/source.md",
        "line_start": 1,
        "line_end": 3,
        "matched_tokens": [event_id],
        "artifact_role": "EVIDENCE_ARTIFACT",
        "source_hints": ["HADITH_CANDIDATE"],
        "automatic_source_classification": False,
        "file_sha256": "a" * 64,
        "excerpt_sha256": text_sha256(excerpt),
        "normalised_excerpt_sha256": text_sha256(" ".join(excerpt.split())),
        "excerpt": excerpt,
        "research_priority_score": score,
        "triage_bucket": bucket,
        "triage_reasons": [],
        "internal_echo_score": 0,
        "locator_signals": {
            "source_names": names or [],
            "numbers": numbers or [],
            "source_record_ids": record_ids or [],
            "urls": urls or [],
            "page_or_volume_markers": pages or [],
            "has_explicit_locator_signal": bucket == BUCKET_LOCATOR,
        },
        "structural_score": score,
        "selected_for_source_verification_pool": True,
        "automatic_source_authentication": False,
        "automatic_hadith_grading": False,
        "automatic_origin_classification": False,
        "human_review_required": True,
    }


def synthetic_triage(path: Path) -> None:
    events = []
    for index, event_id in enumerate(TARGET_EVENTS):
        editorial = event_id == "EV-ADAM-099"
        candidates = []
        if not editorial:
            candidates = [
                selected_candidate(
                    event_id=event_id,
                    candidate_id=f"{event_id}-a",
                    excerpt=f"صحيح البخاري {3000 + index}",
                    names=["صحيح البخاري"],
                    numbers=[str(3000 + index)],
                ),
                selected_candidate(
                    event_id=event_id,
                    candidate_id=f"{event_id}-b",
                    excerpt=f"صحيح البخاري {3000 + index} نص آخر",
                    names=["صحيح البخاري"],
                    numbers=[str(3000 + index)],
                    score=80,
                ),
                selected_candidate(
                    event_id=event_id,
                    candidate_id=f"{event_id}-note",
                    excerpt=f"ملاحظة بحثية {event_id}",
                    bucket=BUCKET_NOTE,
                    score=50,
                ),
            ]
        events.append({
            "event_id": event_id,
            "title": event_id,
            "section": "section",
            "event_kind": (
                "EDITORIAL_TRANSITION" if editorial else "FACTUAL_RESEARCH"
            ),
            "candidate_count": len(candidates),
            "bucket_counts": {},
            "selected_candidate_count": len(candidates),
            "selected_candidate_ids": [
                item["candidate_id"] for item in candidates
            ],
            "selected_candidates": candidates,
            "all_candidates": candidates,
            "verification_readiness": (
                "EDITORIAL_HUMAN_DECISION_PENDING"
                if editorial else "LOCATOR_VERIFICATION_READY"
            ),
        })
    triage = {
        "schema_version": "siraj-non-quran-candidate-triage-v1",
        "status": "STRUCTURAL_TRIAGE_READY_SOURCE_VERIFICATION_PENDING",
        "episode_id": "episode-001-adam",
        "triage_id": "synthetic-triage",
        "input_candidate_count": sum(
            event["candidate_count"] for event in events
        ),
        "selected_candidate_count": sum(
            event["selected_candidate_count"] for event in events
        ),
        "event_count": len(events),
        "events": events,
        "human_approval": False,
    }
    path.write_text(
        json.dumps(triage, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class NonQuranSourceVerificationExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backlog = load_backlog(BACKLOG)
        cls.plan = load_verification_plan(PLAN)
        cls.policy = build_policy()

    def test_target_counts(self):
        self.assertEqual(len(FACTUAL_EVENTS), 14)
        self.assertEqual(len(TARGET_EVENTS), 15)

    def test_verification_key_source_record(self):
        item = selected_candidate(
            event_id="EV-ADAM-001",
            candidate_id="c1",
            excerpt="record",
            record_ids=["SRCREC-ONE"],
        )
        self.assertEqual(
            verification_key(item), "source-record:SRCREC-ONE"
        )

    def test_verification_key_url(self):
        item = selected_candidate(
            event_id="EV-ADAM-001",
            candidate_id="c2",
            excerpt="url",
            urls=["https://example.org/a"],
        )
        self.assertEqual(
            verification_key(item), "url:https://example.org/a"
        )

    def test_verification_key_source_number(self):
        item = selected_candidate(
            event_id="EV-ADAM-001",
            candidate_id="c3",
            excerpt="source",
            names=["صحيح مسلم"],
            numbers=["2653"],
        )
        self.assertEqual(
            verification_key(item), "source-number:صحيح مسلم:2653"
        )

    def test_verification_key_excerpt_fallback(self):
        item = selected_candidate(
            event_id="EV-ADAM-001",
            candidate_id="c4",
            excerpt="unique excerpt",
            bucket=BUCKET_NOTE,
        )
        item["locator_signals"] = {
            "source_names": [],
            "numbers": [],
            "source_record_ids": [],
            "urls": [],
            "page_or_volume_markers": [],
        }
        self.assertTrue(verification_key(item).startswith("excerpt:"))

    def test_route_locator(self):
        item = selected_candidate(
            event_id="EV-ADAM-001",
            candidate_id="c5",
            excerpt="صحيح البخاري 1",
        )
        self.assertEqual(
            determine_route("EV-ADAM-001", [item]), ROUTE_LOCATOR
        )

    def test_route_mention(self):
        item = selected_candidate(
            event_id="EV-ADAM-001",
            candidate_id="c6",
            excerpt="ذكر الطبري",
            bucket=BUCKET_MENTION,
        )
        self.assertEqual(
            determine_route("EV-ADAM-001", [item]), ROUTE_MENTION
        )

    def test_route_discovery(self):
        item = selected_candidate(
            event_id="EV-ADAM-001",
            candidate_id="c7",
            excerpt="note",
            bucket=BUCKET_MANUAL,
        )
        self.assertEqual(
            determine_route("EV-ADAM-001", [item]), ROUTE_DISCOVERY
        )

    def test_route_editorial(self):
        self.assertEqual(
            determine_route("EV-ADAM-099", []), ROUTE_EDITORIAL
        )

    def test_consolidates_same_locator(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "triage.json"
            synthetic_triage(path)
            triage = load_triage(path)
            representatives, duplicates = consolidate_selected_candidates(
                triage
            )
            self.assertGreater(len(duplicates), 0)
            event_reps = [
                item for item in representatives
                if item["event_id"] == "EV-ADAM-001"
            ]
            self.assertEqual(len(event_reps), 2)

    def test_representative_is_highest_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "triage.json"
            synthetic_triage(path)
            triage = load_triage(path)
            representatives, _ = consolidate_selected_candidates(triage)
            locator = next(
                item for item in representatives
                if item["event_id"] == "EV-ADAM-001"
                and item["triage_bucket"] == BUCKET_LOCATOR
            )
            self.assertEqual(locator["candidate_id"], "EV-ADAM-001-a")

    def test_editorial_has_no_representatives(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "triage.json"
            synthetic_triage(path)
            triage = load_triage(path)
            representatives, _ = consolidate_selected_candidates(triage)
            self.assertFalse(any(
                item["event_id"] == "EV-ADAM-099"
                for item in representatives
            ))

    def test_policy_guards(self):
        self.assertFalse(self.policy["human_approval"])
        self.assertEqual(self.policy["evidence_gate_status"], GATE)
        self.assertEqual(
            self.policy["automatic_evidence_approval"], AUTO_APPROVAL
        )
        self.assertEqual(
            self.policy["live_provider_execution"], LIVE_EXECUTION
        )

    def test_policy_forbids_automatic_hadith_grading(self):
        self.assertIn(
            "automatic hadith grading", self.policy["prohibitions"]
        )

    def test_record_template_blank(self):
        item = selected_candidate(
            event_id="EV-ADAM-001",
            candidate_id="record",
            excerpt="صحيح البخاري 3191",
            names=["صحيح البخاري"],
            numbers=["3191"],
        )
        item.update({
            "verification_key": verification_key(item),
            "representative_candidate_id": "record",
        })
        record = build_record_template(
            event_id="EV-ADAM-001",
            event_title="title",
            candidate=item,
            route=ROUTE_LOCATOR,
            policy=self.policy,
        )
        self.assertEqual(record["schema_version"], RECORD_SCHEMA)
        self.assertFalse(record["source_verified"])
        self.assertFalse(record["authentication_verified"])
        self.assertEqual(record["origin_classification"], "unresolved")
        self.assertFalse(record["source_title"])

    def test_record_template_rejects_prefilled_source(self):
        item = selected_candidate(
            event_id="EV-ADAM-001",
            candidate_id="record2",
            excerpt="صحيح مسلم 2653",
            names=["صحيح مسلم"],
            numbers=["2653"],
        )
        item.update({
            "verification_key": verification_key(item),
            "representative_candidate_id": "record2",
        })
        record = build_record_template(
            event_id="EV-ADAM-001",
            event_title="title",
            candidate=item,
            route=ROUTE_LOCATOR,
            policy=self.policy,
        )
        record["source_title"] = "Sahih Muslim"
        with self.assertRaises(VerificationExecutionError):
            validate_record_template(record)

    def test_build_execution_covers_all_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            triage_path = Path(tmp) / "triage.json"
            synthetic_triage(triage_path)
            execution, policy, review, duplicates, records = build_execution(
                triage_path=triage_path,
                backlog_path=BACKLOG,
                plan_path=PLAN,
            )
            self.assertEqual(execution["schema_version"], EXECUTION_SCHEMA)
            self.assertEqual(execution["event_count"], 15)
            self.assertEqual(
                tuple(item["event_id"] for item in execution["events"]),
                TARGET_EVENTS,
            )
            self.assertGreater(len(records), 0)
            self.assertGreater(len(duplicates), 0)

    def test_execution_has_three_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            triage_path = Path(tmp) / "triage.json"
            synthetic_triage(triage_path)
            execution, *_ = build_execution(
                triage_path=triage_path,
                backlog_path=BACKLOG,
                plan_path=PLAN,
            )
            self.assertEqual(execution["batch_count"], 3)
            covered = tuple(
                event_id
                for batch in execution["batches"]
                for event_id in batch["event_ids"]
            )
            self.assertEqual(covered, FACTUAL_EVENTS)

    def test_execution_editorial_has_no_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            triage_path = Path(tmp) / "triage.json"
            synthetic_triage(triage_path)
            execution, *_ = build_execution(
                triage_path=triage_path,
                backlog_path=BACKLOG,
                plan_path=PLAN,
            )
            editorial = next(
                item for item in execution["events"]
                if item["event_id"] == "EV-ADAM-099"
            )
            self.assertEqual(editorial["route"], ROUTE_EDITORIAL)
            self.assertEqual(editorial["record_template_count"], 0)

    def test_review_template_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            triage_path = Path(tmp) / "triage.json"
            synthetic_triage(triage_path)
            _, _, review, _, _ = build_execution(
                triage_path=triage_path,
                backlog_path=BACKLOG,
                plan_path=PLAN,
            )
            self.assertEqual(review["schema_version"], REVIEW_SCHEMA)
            self.assertTrue(all(
                not item["verified_record_ids"]
                and not item["source_verification_complete"]
                and not item["approved"]
                and not item["human_decision"]
                for item in review["decisions"]
            ))

    def test_review_editorial_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            triage_path = Path(tmp) / "triage.json"
            synthetic_triage(triage_path)
            _, _, review, _, _ = build_execution(
                triage_path=triage_path,
                backlog_path=BACKLOG,
                plan_path=PLAN,
            )
            editorial = next(
                item for item in review["decisions"]
                if item["event_id"] == "EV-ADAM-099"
            )
            self.assertEqual(
                editorial["proposed_disposition"], "editorial_only"
            )

    def test_execution_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            triage_path = Path(tmp) / "triage.json"
            synthetic_triage(triage_path)
            one = build_execution(
                triage_path=triage_path,
                backlog_path=BACKLOG,
                plan_path=PLAN,
            )
            two = build_execution(
                triage_path=triage_path,
                backlog_path=BACKLOG,
                plan_path=PLAN,
            )
            self.assertEqual(
                canonical_sha256(one[0]), canonical_sha256(two[0])
            )
            self.assertEqual(
                canonical_sha256(one[2]), canonical_sha256(two[2])
            )

    def test_execution_never_claims_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            triage_path = Path(tmp) / "triage.json"
            synthetic_triage(triage_path)
            execution, *_ = build_execution(
                triage_path=triage_path,
                backlog_path=BACKLOG,
                plan_path=PLAN,
            )
            self.assertFalse(execution["source_verification_complete"])
            self.assertFalse(execution["human_approval"])
            self.assertFalse(execution["full_episode_adjudication_complete"])
            self.assertFalse(execution["approved_evidence_package_complete"])
            self.assertFalse(execution["opens_evidence_gate"])

    def test_validation_rejects_open_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            triage_path = Path(tmp) / "triage.json"
            synthetic_triage(triage_path)
            execution, *_ = build_execution(
                triage_path=triage_path,
                backlog_path=BACKLOG,
                plan_path=PLAN,
            )
            changed = copy.deepcopy(execution)
            changed["evidence_gate_status"] = "OPEN"
            with self.assertRaises(VerificationExecutionError):
                validate_execution(changed)

    def test_validation_rejects_preapproved_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            triage_path = Path(tmp) / "triage.json"
            synthetic_triage(triage_path)
            _, _, review, _, _ = build_execution(
                triage_path=triage_path,
                backlog_path=BACKLOG,
                plan_path=PLAN,
            )
            changed = copy.deepcopy(review)
            changed["decisions"][0]["approved"] = True
            with self.assertRaises(VerificationExecutionError):
                validate_review_template(changed)

    def test_write_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            triage_path = root / "triage.json"
            synthetic_triage(triage_path)
            execution, policy, review, duplicates, records = build_execution(
                triage_path=triage_path,
                backlog_path=BACKLOG,
                plan_path=PLAN,
            )
            outputs = write_local_outputs(
                output_root=root / "report",
                execution=execution,
                policy=policy,
                review=review,
                duplicates=duplicates,
                record_templates=records,
            )
            self.assertTrue(outputs["archive"].is_file())
            self.assertTrue(outputs["queue_csv"].is_file())
            self.assertEqual(
                len(list((root / "report/event-execution-dossiers").glob("*.md"))),
                15,
            )
            self.assertEqual(
                len(list((root / "report/execution-batches").glob("*.json"))),
                3,
            )
            self.assertEqual(
                len(list((root / "report/verification-records").rglob("*.json"))),
                len(records),
            )

    def test_json_outputs_use_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            from src.application.storyboard_runtime.non_quran_source_verification_execution import write_json
            path = Path(tmp) / "policy.json"
            write_json(path, self.policy)
            raw = path.read_bytes()
            self.assertNotIn(b"\r\n", raw)
            self.assertTrue(raw.endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
