from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.prestige_cinematic_directors_cut_v2 import (
    APPROVAL_PHRASE,
    EVIDENCE_GATE_OPEN,
    FORBIDDEN_RESEARCH_META_PHRASES,
    MATERIAL_TREATMENTS,
    MINIMUM_MATERIAL_SHOT_COUNT,
    SUPERSEDED_SCRIPT_FINGERPRINT,
    SUPERSEDED_SCRIPT_ID,
    SUPERSEDED_STORYBOARD_FINGERPRINT,
    SUPERSEDED_STORYBOARD_ID,
    EXPECTED_EVIDENCE_ITEM_COUNT,
    EXPECTED_EVENT_COUNT,
    EXPECTED_FRAME_COUNT,
    EXPECTED_QUALIFIED_EVENTS,
    EXPECTED_SHOT_COUNT,
    EXPECTED_TOTAL_SECONDS,
    FORMAT_IDENTITY,
    LIVE_EXECUTION,
    PAID_EXECUTION,
    PRODUCTION_PROFILE,
    TIMEZONE,
    build_script_and_storyboard,
    read_json,
    read_json_list,
    update_episode_definition,
    validate_inputs,
    validate_superseded_artifacts,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode-001-adam"
CONTRACTS = EPISODE / "contracts"
EDITORIAL = EPISODE / "editorial"
EVIDENCE = EPISODE / "evidence"
CINEMATIC = EPISODE / "cinematic"


class PrestigeCinematicDirectorsCutV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.creative = read_json(
            EDITORIAL / "prestige-cinematic-directors-cut-blueprint-v2.json"
        )
        cls.bound = read_json(
            CINEMATIC / "evidence-bound-cinematic-blueprint-v1.json"
        )
        cls.direction = read_json(
            CONTRACTS / "prestige-historical-cinematic-direction-v1.json"
        )
        cls.event_map = read_json_list(EDITORIAL / "event-map.json")
        cls.evidence = read_json(
            EVIDENCE / "approved-evidence-package-v1.json"
        )
        cls.adjudication = read_json(
            EVIDENCE / "event-evidence-adjudication-v1.json"
        )
        cls.definition = read_json(
            CONTRACTS / "episode-definition-v1.json"
        )
        cls.script_v1 = read_json(
            EDITORIAL / "prestige-cinematic-script-v1.json"
        )
        cls.storyboard_v1 = read_json(
            CINEMATIC / "detailed-storyboard-v1.json"
        )
        validate_superseded_artifacts(
            script_v1=cls.script_v1,
            storyboard_v1=cls.storyboard_v1,
        )
        validate_inputs(
            creative_blueprint=cls.creative,
            bound_blueprint=cls.bound,
            direction=cls.direction,
            event_map=cls.event_map,
            evidence_package=cls.evidence,
            adjudication=cls.adjudication,
            episode_definition=cls.definition,
        )
        (
            cls.script,
            cls.storyboard,
            cls.trace,
            cls.approval_request,
            cls.production_brief,
        ) = build_script_and_storyboard(
            creative_blueprint=cls.creative,
            bound_blueprint=cls.bound,
            direction=cls.direction,
            event_map=cls.event_map,
            evidence_package=cls.evidence,
            adjudication=cls.adjudication,
        )
        cls.updated_definition = update_episode_definition(
            episode_definition=cls.definition,
            script=cls.script,
            storyboard=cls.storyboard,
            trace=cls.trace,
            approval_request=cls.approval_request,
            production_brief=cls.production_brief,
        )

    def test_evidence_gate_is_open(self):
        self.assertEqual(
            self.bound["evidence_gate_status"], EVIDENCE_GATE_OPEN
        )

    def test_canonical_timezone_is_baghdad(self):
        self.assertEqual(self.direction["timezone"], TIMEZONE)

    def test_creative_timezone_is_baghdad(self):
        self.assertEqual(self.creative["timezone"], TIMEZONE)

    def test_prestige_format_is_active(self):
        self.assertEqual(
            self.direction["format_identity"], FORMAT_IDENTITY
        )

    def test_world_class_profile_is_active(self):
        self.assertEqual(
            self.direction["production_profile"], PRODUCTION_PROFILE
        )

    def test_script_has_fourteen_sequences(self):
        self.assertEqual(
            self.script["sequence_count"], EXPECTED_FRAME_COUNT
        )

    def test_sequence_order_matches_bound_storyboard(self):
        self.assertEqual(
            [item["frame_id"] for item in self.script["sequences"]],
            [
                item["frame_id"]
                for item in self.bound["storyboard"]["frames"]
            ],
        )

    def test_script_duration_is_22_minutes(self):
        self.assertEqual(
            self.script["target_duration_seconds"],
            EXPECTED_TOTAL_SECONDS,
        )

    def test_sequence_duration_total_is_22_minutes(self):
        self.assertEqual(
            sum(
                item["duration_seconds"]
                for item in self.script["sequences"]
            ),
            EXPECTED_TOTAL_SECONDS,
        )

    def test_narration_has_substantial_length(self):
        self.assertGreaterEqual(
            self.script["narration_word_count"], 1200
        )

    def test_narration_is_not_overloaded(self):
        self.assertLessEqual(
            self.script["narration_word_count"], 3500
        )

    def test_script_is_not_automatically_approved(self):
        self.assertFalse(self.script["human_script_approval"])

    def test_religious_safety_is_pending(self):
        self.assertFalse(self.script["religious_safety_approval"])

    def test_storyboard_has_seventy_shots(self):
        self.assertEqual(
            self.storyboard["shot_count"], EXPECTED_SHOT_COUNT
        )

    def test_shot_ids_are_unique(self):
        ids = [
            item["shot_id"] for item in self.storyboard["shots"]
        ]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_shot_durations_are_positive(self):
        self.assertTrue(all(
            item["duration_seconds"] > 0
            for item in self.storyboard["shots"]
        ))

    def test_shot_duration_total_is_22_minutes(self):
        self.assertEqual(
            sum(
                item["duration_seconds"]
                for item in self.storyboard["shots"]
            ),
            EXPECTED_TOTAL_SECONDS,
        )

    def test_each_sequence_has_five_shots(self):
        self.assertTrue(all(
            item["shot_count"] == 5
            for item in self.script["sequences"]
        ))

    def test_each_sequence_shots_match_duration(self):
        self.assertTrue(all(
            sum(
                shot["duration_seconds"]
                for shot in item["shots"]
            )
            == item["duration_seconds"]
            for item in self.script["sequences"]
        ))

    def test_every_sequence_has_dramatic_objective(self):
        self.assertTrue(all(
            item["dramatic_objective"].strip()
            for item in self.script["sequences"]
        ))

    def test_every_sequence_has_pressure(self):
        self.assertTrue(all(
            item["pressure"].strip()
            for item in self.script["sequences"]
        ))

    def test_every_sequence_has_turn(self):
        self.assertTrue(all(
            item["turn"].strip()
            for item in self.script["sequences"]
        ))

    def test_every_sequence_has_visual_thesis(self):
        self.assertTrue(all(
            item["visual_thesis"].strip()
            for item in self.script["sequences"]
        ))

    def test_every_sequence_has_image_system(self):
        self.assertTrue(all(
            item["image_system"].strip()
            for item in self.script["sequences"]
        ))

    def test_every_sequence_has_sound_design(self):
        self.assertTrue(all(
            item["sound_design"].strip()
            for item in self.script["sequences"]
        ))

    def test_every_sequence_has_music_direction(self):
        self.assertTrue(all(
            item["music_direction"].strip()
            for item in self.script["sequences"]
        ))

    def test_every_sequence_has_transition(self):
        self.assertTrue(all(
            item["transition"].strip()
            for item in self.script["sequences"]
        ))

    def test_no_invented_dialogue_policy(self):
        self.assertTrue(all(
            item["dialogue_policy"].startswith("NO_INVENTED")
            for item in self.script["sequences"]
        ))

    def test_first_sequence_is_cold_open(self):
        self.assertEqual(
            self.script["sequences"][0]["narrative_function"],
            "cold_open",
        )

    def test_central_question_sequence_is_second(self):
        self.assertEqual(
            self.script["sequences"][1]["narrative_function"],
            "central_question",
        )

    def test_climax_sequence_is_present(self):
        climax = [
            item for item in self.script["sequences"]
            if item["narrative_function"] == "climax"
        ]
        self.assertEqual(len(climax), 1)
        self.assertEqual(climax[0]["sequence_title"], "أنا خير منه")

    def test_last_sequence_is_next_episode_promise(self):
        self.assertEqual(
            self.script["sequences"][-1]["narrative_function"],
            "next_episode_promise",
        )

    def test_all_events_are_traced(self):
        self.assertTrue(self.trace["event_coverage_complete"])
        self.assertEqual(self.trace["event_count"], EXPECTED_EVENT_COUNT)

    def test_no_missing_events(self):
        self.assertEqual(self.trace["missing_event_ids"], [])

    def test_all_evidence_is_traced(self):
        self.assertTrue(self.trace["evidence_coverage_complete"])
        self.assertEqual(
            self.trace["evidence_item_count"],
            EXPECTED_EVIDENCE_ITEM_COUNT,
        )

    def test_no_missing_evidence(self):
        self.assertEqual(self.trace["missing_evidence_ids"], [])

    def test_qualified_event_set_is_exact(self):
        self.assertEqual(
            set(self.trace["qualified_event_ids"]),
            EXPECTED_QUALIFIED_EVENTS,
        )

    def test_qualified_sequences_have_labels(self):
        for sequence in self.script["sequences"]:
            if set(sequence["event_ids"]) & EXPECTED_QUALIFIED_EVENTS:
                self.assertTrue(sequence["qualification_labels"])

    def test_editorial_event_is_in_final_sequence(self):
        self.assertIn(
            "EV-ADAM-099",
            self.script["sequences"][-1]["event_ids"],
        )

    def test_storyboard_forbids_literal_unseen_depiction(self):
        self.assertEqual(
            self.storyboard["master_visual_rules"][
                "literal_unseen_depiction"
            ],
            "FORBIDDEN",
        )

    def test_storyboard_forbids_allah_depiction(self):
        self.assertEqual(
            self.storyboard["master_visual_rules"]["allah_depiction"],
            "FORBIDDEN",
        )

    def test_storyboard_forbids_angel_bodies(self):
        self.assertEqual(
            self.storyboard["master_visual_rules"][
                "angel_body_depiction"
            ],
            "FORBIDDEN",
        )

    def test_storyboard_forbids_prophet_face_or_body(self):
        self.assertEqual(
            self.storyboard["master_visual_rules"][
                "prophet_face_or_body_depiction"
            ],
            "FORBIDDEN",
        )

    def test_storyboard_forbids_iblis_body(self):
        self.assertEqual(
            self.storyboard["master_visual_rules"][
                "iblis_body_depiction"
            ],
            "FORBIDDEN",
        )

    def test_storyboard_forbids_invented_dialogue(self):
        self.assertEqual(
            self.storyboard["master_visual_rules"][
                "invented_historical_dialogue"
            ],
            "FORBIDDEN",
        )

    def test_storyboard_is_not_automatically_approved(self):
        self.assertFalse(
            self.storyboard["human_storyboard_approval"]
        )

    def test_master_visual_approval_is_pending(self):
        self.assertFalse(
            self.storyboard["master_visual_approval"]
        )

    def test_all_artifacts_keep_live_execution_blocked(self):
        for artifact in (
            self.script,
            self.storyboard,
            self.trace,
            self.approval_request,
            self.production_brief,
        ):
            self.assertEqual(
                artifact["live_provider_execution"],
                LIVE_EXECUTION,
            )

    def test_all_artifacts_keep_paid_execution_blocked(self):
        for artifact in (
            self.script,
            self.storyboard,
            self.trace,
            self.approval_request,
            self.production_brief,
        ):
            self.assertEqual(
                artifact["paid_execution"], PAID_EXECUTION
            )

    def test_no_generated_video_is_scheduled(self):
        self.assertEqual(
            self.production_brief["generated_video_planned_seconds"],
            0,
        )

    def test_provider_selection_is_deferred(self):
        self.assertEqual(
            self.production_brief["provider_selection"], "DEFERRED"
        )

    def test_budget_allocation_is_deferred(self):
        self.assertEqual(
            self.production_brief["budget_allocation"], "DEFERRED"
        )

    def test_script_fingerprint_is_64_hex(self):
        fingerprint = self.script["script_fingerprint"]
        self.assertEqual(len(fingerprint), 64)
        int(fingerprint, 16)

    def test_storyboard_fingerprint_is_64_hex(self):
        fingerprint = self.storyboard["storyboard_fingerprint"]
        self.assertEqual(len(fingerprint), 64)
        int(fingerprint, 16)

    def test_approval_request_matches_script_fingerprint(self):
        self.assertEqual(
            self.approval_request["script_fingerprint"],
            self.script["script_fingerprint"],
        )

    def test_approval_request_matches_storyboard_fingerprint(self):
        self.assertEqual(
            self.approval_request["storyboard_fingerprint"],
            self.storyboard["storyboard_fingerprint"],
        )

    def test_approval_phrase_is_exactly_recorded(self):
        self.assertEqual(
            self.approval_request["exact_approval_phrase"],
            APPROVAL_PHRASE,
        )

    def test_approval_request_is_pending(self):
        self.assertFalse(self.approval_request["human_approval"])

    def test_episode_definition_points_to_script(self):
        self.assertEqual(
            self.updated_definition["cinematic_script"]["script_id"],
            self.script["script_id"],
        )

    def test_episode_definition_points_to_storyboard(self):
        self.assertEqual(
            self.updated_definition["detailed_storyboard"][
                "storyboard_id"
            ],
            self.storyboard["storyboard_id"],
        )

    def test_episode_definition_next_stage_is_human_review(self):
        self.assertEqual(
            self.updated_definition["next_stage"],
            "HUMAN_REVIEW_OF_PRESTIGE_CINEMATIC_DIRECTORS_CUT_V2",
        )

    def test_build_is_deterministic(self):
        second = build_script_and_storyboard(
            creative_blueprint=self.creative,
            bound_blueprint=self.bound,
            direction=self.direction,
            event_map=self.event_map,
            evidence_package=self.evidence,
            adjudication=self.adjudication,
        )
        self.assertEqual(
            (
                self.script,
                self.storyboard,
                self.trace,
                self.approval_request,
                self.production_brief,
            ),
            second,
        )

    def test_output_files_and_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                output_root=Path(tmp) / "report",
                script=self.script,
                storyboard=self.storyboard,
                trace=self.trace,
                approval_request=self.approval_request,
                production_brief=self.production_brief,
                episode_definition=self.updated_definition,
            )
            for path in outputs.values():
                self.assertTrue(path.is_file())

    def test_json_outputs_use_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                output_root=Path(tmp) / "report",
                script=self.script,
                storyboard=self.storyboard,
                trace=self.trace,
                approval_request=self.approval_request,
                production_brief=self.production_brief,
                episode_definition=self.updated_definition,
            )
            for key in (
                "script_json",
                "storyboard_json",
                "trace",
                "approval_request",
                "production_brief",
                "episode_definition",
            ):
                raw = outputs[key].read_bytes()
                self.assertTrue(raw.endswith(b"\n"))
                self.assertNotIn(b"\r\n", raw)


    def test_director_cut_version_is_two(self):
        self.assertEqual(self.script["director_cut_version"], 2)
        self.assertEqual(self.storyboard["director_cut_version"], 2)

    def test_adaptation_policy_preserves_meaning(self):
        self.assertEqual(
            self.script["adaptation_policy"],
            "MEANING_PRESERVED_WORDING_CINEMATICALLY_ADAPTED",
        )

    def test_literal_source_context_is_not_default(self):
        self.assertEqual(
            self.script["narrative_policy"]["literal_source_context"],
            "FORBIDDEN_AS_DEFAULT",
        )

    def test_meaning_change_is_forbidden(self):
        self.assertEqual(
            self.script["narrative_policy"]["meaning_change"],
            "FORBIDDEN",
        )

    def test_cinematic_paraphrase_is_required(self):
        self.assertEqual(
            self.script["narrative_policy"]["cinematic_paraphrase"],
            "REQUIRED",
        )

    def test_qualification_preservation_is_required(self):
        self.assertEqual(
            self.script["narrative_policy"][
                "qualification_preservation"
            ],
            "REQUIRED",
        )

    def test_no_research_meta_language_in_narration(self):
        narration = "\n".join(
            sequence["narration"]
            for sequence in self.script["sequences"]
        )
        for phrase in FORBIDDEN_RESEARCH_META_PHRASES:
            self.assertNotIn(phrase, narration)

    def test_opening_has_no_methodology_exposition(self):
        opening = "\n".join(
            sequence["narration"]
            for sequence in self.script["sequences"][:2]
        )
        self.assertNotIn("نحن لا", opening)
        self.assertNotIn("المصادر", opening)
        self.assertNotIn("نبحث", opening)

    def test_narration_word_count_is_directors_cut_target(self):
        self.assertEqual(self.script["narration_word_count"], 1321)

    def test_material_environment_dominates_shot_design(self):
        material_count = sum(
            shot["treatment"] in MATERIAL_TREATMENTS
            for shot in self.storyboard["shots"]
        )
        self.assertGreaterEqual(
            material_count,
            MINIMUM_MATERIAL_SHOT_COUNT,
        )

    def test_old_generic_treatments_are_removed(self):
        treatments = {
            shot["treatment"]
            for shot in self.storyboard["shots"]
        }
        self.assertTrue(
            treatments.isdisjoint(
                {
                    "still_led",
                    "generated_image",
                    "generated_video",
                }
            )
        )

    def test_all_shots_keep_provider_execution_blocked(self):
        self.assertTrue(all(
            shot["provider_execution"] == "BLOCKED"
            for shot in self.storyboard["shots"]
        ))

    def test_script_supersedes_exact_v1_candidate(self):
        self.assertEqual(
            self.script["supersedes"]["script_id"],
            SUPERSEDED_SCRIPT_ID,
        )
        self.assertEqual(
            self.script["supersedes"]["script_fingerprint"],
            SUPERSEDED_SCRIPT_FINGERPRINT,
        )

    def test_storyboard_supersedes_exact_v1_candidate(self):
        self.assertEqual(
            self.storyboard["supersedes"]["storyboard_id"],
            SUPERSEDED_STORYBOARD_ID,
        )
        self.assertEqual(
            self.storyboard["supersedes"][
                "storyboard_fingerprint"
            ],
            SUPERSEDED_STORYBOARD_FINGERPRINT,
        )

    def test_superseded_artifacts_validate(self):
        validate_superseded_artifacts(
            script_v1=self.script_v1,
            storyboard_v1=self.storyboard_v1,
        )

    def test_v2_ids_are_distinct(self):
        self.assertTrue(
            self.script["script_id"].startswith(
                "adam_prestige_cinematic_script_v2_"
            )
        )
        self.assertTrue(
            self.storyboard["storyboard_id"].startswith(
                "adam_detailed_cinematic_storyboard_v2_"
            )
        )

    def test_new_sequence_titles_are_active(self):
        self.assertEqual(
            self.script["sequences"][0]["sequence_title"],
            "السجدة التي لم تكتمل",
        )
        self.assertEqual(
            self.script["sequences"][-1]["sequence_title"],
            "قبل الهمس",
        )

    def test_episode_definition_marks_v1_superseded(self):
        value = self.updated_definition[
            "superseded_script_storyboard_v1"
        ]
        self.assertEqual(
            value["status"],
            "SUPERSEDED_BY_DIRECTORS_CUT_V2",
        )

    def test_episode_definition_records_directors_cut(self):
        revision = self.updated_definition["director_cut_revision"]
        self.assertEqual(revision["version"], 2)
        self.assertEqual(
            revision["adaptation_policy"],
            "MEANING_PRESERVED_WORDING_CINEMATICALLY_ADAPTED",
        )
        self.assertEqual(
            revision["source_context_literalism"],
            "REMOVED",
        )

    def test_episode_definition_update_is_idempotent(self):
        rebuilt = update_episode_definition(
            episode_definition=self.updated_definition,
            script=self.script,
            storyboard=self.storyboard,
            trace=self.trace,
            approval_request=self.approval_request,
            production_brief=self.production_brief,
        )
        self.assertEqual(rebuilt, self.updated_definition)

    def test_second_update_preserves_superseded_v1_record(self):
        rebuilt = update_episode_definition(
            episode_definition=self.updated_definition,
            script=self.script,
            storyboard=self.storyboard,
            trace=self.trace,
            approval_request=self.approval_request,
            production_brief=self.production_brief,
        )
        self.assertEqual(
            rebuilt["superseded_script_storyboard_v1"],
            self.updated_definition[
                "superseded_script_storyboard_v1"
            ],
        )

    def test_second_update_does_not_capture_v2_as_v1(self):
        rebuilt = update_episode_definition(
            episode_definition=self.updated_definition,
            script=self.script,
            storyboard=self.storyboard,
            trace=self.trace,
            approval_request=self.approval_request,
            production_brief=self.production_brief,
        )
        superseded = rebuilt["superseded_script_storyboard_v1"]
        self.assertEqual(
            superseded["cinematic_script"]["path"],
            "editorial/prestige-cinematic-script-v1.json",
        )
        self.assertEqual(
            superseded["detailed_storyboard"]["path"],
            "cinematic/detailed-storyboard-v1.json",
        )

    def test_approval_phrase_targets_second_directors_cut(self):
        self.assertIn(
            "النسخة الإخراجية الثانية",
            APPROVAL_PHRASE,
        )


if __name__ == "__main__":
    unittest.main()
