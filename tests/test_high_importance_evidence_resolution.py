from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.high_importance_evidence_resolution import (
    APPROVAL_SCHEMA,
    AUTO_APPROVAL,
    EVENT_DECISIONS,
    FINAL_SCOPE_SCHEMA,
    GATE,
    HIGH_IMPORTANCE_EVENT_IDS,
    HIGH_IMPORTANCE_SOURCE_IDS,
    LIVE_EXECUTION,
    PROGRESS_SCHEMA,
    ROUTINE_EVENT_IDS,
    SOURCE_DECISIONS,
    USER_DECISION_TEXT,
    build_final_external_scope,
    build_human_approval,
    build_progress,
    read_json,
    text_sha256,
    validate_inputs,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "projects/episode-001-adam/evidence"


class HighImportanceEvidenceResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dossier = read_json(
            EVIDENCE / "high-importance-evidence-review-dossier-v1.json"
        )
        cls.event_scope = read_json(
            EVIDENCE / "routine-event-scope-adjudication-v1.json"
        )
        cls.research = read_json(
            EVIDENCE / "delegated-hadith-authentication-research-v1.json"
        )
        cls.prior_gap = read_json(
            EVIDENCE / "gap-human-approval-v1.json"
        )
        cls.origin = read_json(
            EVIDENCE / "source-origin-classification-v1.json"
        )
        validate_inputs(
            dossier=cls.dossier,
            event_scope=cls.event_scope,
            research=cls.research,
            prior_gap_approval=cls.prior_gap,
            origin_classification=cls.origin,
        )
        cls.approval = build_human_approval(
            dossier=cls.dossier,
            prior_gap_approval=cls.prior_gap,
            origin_classification=cls.origin,
        )
        cls.final_scope = build_final_external_scope(
            event_scope=cls.event_scope,
            approval=cls.approval,
        )
        cls.progress = build_progress(
            approval=cls.approval,
            final_scope=cls.final_scope,
        )

    def test_approval_schema(self):
        self.assertEqual(
            self.approval["schema_version"], APPROVAL_SCHEMA
        )

    def test_user_decision_text_is_preserved(self):
        self.assertEqual(
            self.approval["user_decision_text"], USER_DECISION_TEXT
        )

    def test_user_decision_hash(self):
        self.assertEqual(
            self.approval["user_decision_text_sha256"],
            text_sha256(USER_DECISION_TEXT),
        )

    def test_three_source_decisions(self):
        self.assertEqual(
            self.approval["source_decision_count"], 3
        )

    def test_exact_source_set(self):
        selected = {
            item["source_candidate_id"]
            for item in self.approval["source_decisions"]
        }
        self.assertEqual(
            selected, set(HIGH_IMPORTANCE_SOURCE_IDS)
        )

    def test_six_event_decisions(self):
        self.assertEqual(
            self.approval["event_decision_count"], 6
        )

    def test_exact_high_importance_event_set(self):
        selected = {
            item["event_id"]
            for item in self.approval["event_decisions"]
        }
        self.assertEqual(
            selected, set(HIGH_IMPORTANCE_EVENT_IDS)
        )

    def test_pen_firstness_is_assertive(self):
        decision = EVENT_DECISIONS["EV-ADAM-003"]
        self.assertEqual(
            decision["disposition"], "include_assertive"
        )
        self.assertEqual(
            decision["firstness_claim"],
            "ASSERTIVE_BY_EXPLICIT_HADITH_TEXT",
        )
        self.assertIn(
            "أول ما خلق الله القلم",
            decision["approved_narration"],
        )

    def test_abu_dawud_pen_source_accepted(self):
        self.assertEqual(
            SOURCE_DECISIONS["SRC-ABUDAWUD-4700"]["decision"],
            "ACCEPT_ASSERTIVE_WITH_SCOPE",
        )

    def test_tirmidhi_pen_source_accepted(self):
        self.assertEqual(
            SOURCE_DECISIONS["SRC-TIRMIDHI-2155"]["decision"],
            "ACCEPT_CORROBORATIVE_WITH_GRADE_NOTE",
        )

    def test_iblis_temporal_claim_is_qualified(self):
        decision = EVENT_DECISIONS["EV-ADAM-007"]
        self.assertEqual(
            decision["disposition"], "include_qualified"
        )
        self.assertIn(
            "غير جازمة", decision["approved_narration"]
        )

    def test_clay_chronology_is_not_asserted(self):
        narration = EVENT_DECISIONS["EV-ADAM-021"][
            "approved_narration"
        ]
        self.assertIn("من دون", narration)
        self.assertIn("جدول زمني جازم", narration)

    def test_names_primary_claim_is_assertive(self):
        decision = EVENT_DECISIONS["EV-ADAM-042"]
        self.assertIn(
            "علّم الله آدم الأسماء كلها",
            decision["approved_narration"],
        )

    def test_tafsir_views_are_qualified(self):
        decision = EVENT_DECISIONS["EV-ADAM-042"]
        self.assertIn(
            "منسوبةً إلى قائليها",
            decision["approved_narration"],
        )
        self.assertIn(
            "NO_EXCLUSIVE_INTERPRETATION_ASSERTION",
            decision["tafsir_supplement_rules"],
        )

    def test_israiliyyat_label_is_required(self):
        self.assertIn(
            "ISRAILIYYAT_EXPLICIT_LABEL_REQUIRED",
            EVENT_DECISIONS["EV-ADAM-042"][
                "tafsir_supplement_rules"
            ],
        )

    def test_covenant_hadith_remains_qualified(self):
        self.assertEqual(
            EVENT_DECISIONS["EV-ADAM-061"]["disposition"],
            "include_qualified",
        )

    def test_hawwa_name_is_asserted(self):
        narration = EVENT_DECISIONS["EV-ADAM-070"][
            "approved_narration"
        ]
        self.assertIn("زوج آدم هي حواء", narration)

    def test_hawwa_rib_synthesis_is_asserted(self):
        decision = EVENT_DECISIONS["EV-ADAM-070"]
        self.assertEqual(
            decision["supported_synthesis"],
            "حواء خلقت من ضلع آدم",
        )
        self.assertIn(
            "خُلقت من ضلع آدم",
            decision["approved_narration"],
        )

    def test_hawwa_uses_prior_event_071(self):
        self.assertEqual(
            EVENT_DECISIONS["EV-ADAM-070"][
                "prior_human_approval_event_id"
            ],
            "EV-ADAM-071",
        )

    def test_hawwa_secondary_details_are_qualified(self):
        policy = EVENT_DECISIONS["EV-ADAM-070"][
            "secondary_detail_policy"
        ]
        self.assertIn("EXPLICIT_ISRAILIYYAT_LABEL", policy)
        self.assertIn("NO_ASSERTIVE_VISUALIZATION", policy)

    def test_human_approval_complete(self):
        self.assertTrue(self.approval["human_approval"])
        self.assertTrue(
            self.approval[
                "final_user_high_importance_decisions_complete"
            ]
        )

    def test_final_scope_schema(self):
        self.assertEqual(
            self.final_scope["schema_version"], FINAL_SCOPE_SCHEMA
        )

    def test_final_scope_has_fourteen_events(self):
        self.assertEqual(self.final_scope["event_count"], 14)

    def test_final_scope_has_eight_delegated_events(self):
        self.assertEqual(
            self.final_scope["routine_delegated_event_count"], 8
        )

    def test_final_scope_has_six_human_events(self):
        self.assertEqual(
            self.final_scope["explicit_human_event_count"], 6
        )

    def test_all_final_events_are_approved(self):
        self.assertTrue(all(
            item["event_scope_approved"]
            for item in self.final_scope["events"]
        ))

    def test_exact_final_event_set(self):
        selected = {
            item["event_id"] for item in self.final_scope["events"]
        }
        self.assertEqual(
            selected,
            set(ROUTINE_EVENT_IDS) | set(HIGH_IMPORTANCE_EVENT_IDS),
        )

    def test_progress_schema(self):
        self.assertEqual(
            self.progress["schema_version"], PROGRESS_SCHEMA
        )

    def test_external_scope_is_complete(self):
        self.assertTrue(
            self.progress["external_event_scope_complete"]
        )

    def test_broader_episode_integration_remains(self):
        self.assertTrue(
            self.progress[
                "remaining_episode_event_integration_required"
            ]
        )
        self.assertFalse(
            self.progress["full_episode_adjudication_complete"]
        )

    def test_global_guards(self):
        for artifact in (
            self.approval,
            self.final_scope,
            self.progress,
        ):
            self.assertFalse(artifact["opens_evidence_gate"])
            self.assertEqual(
                artifact["evidence_gate_status"], GATE
            )
            self.assertEqual(
                artifact["automatic_evidence_approval"],
                AUTO_APPROVAL,
            )
            self.assertEqual(
                artifact["live_provider_execution"],
                LIVE_EXECUTION,
            )

    def test_deterministic_builders(self):
        second = build_human_approval(
            dossier=self.dossier,
            prior_gap_approval=self.prior_gap,
            origin_classification=self.origin,
        )
        self.assertEqual(self.approval, second)

    def test_outputs_and_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                output_root=Path(tmp) / "report",
                approval=self.approval,
                final_scope=self.final_scope,
                progress=self.progress,
            )
            for path in outputs.values():
                self.assertTrue(path.is_file())

    def test_json_outputs_use_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                output_root=Path(tmp) / "report",
                approval=self.approval,
                final_scope=self.final_scope,
                progress=self.progress,
            )
            for key in ("approval", "final_scope", "progress"):
                raw = outputs[key].read_bytes()
                self.assertTrue(raw.endswith(b"\n"))
                self.assertNotIn(b"\r\n", raw)


if __name__ == "__main__":
    unittest.main()
