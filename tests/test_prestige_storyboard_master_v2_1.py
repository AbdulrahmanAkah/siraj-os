from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.application.storyboard_runtime.prestige_storyboard_master_v2_1 import (
    APPROVAL_PHRASE,
    EXACT_COVENANT_VERSE,
    EXPECTED_EVIDENCE_COUNT,
    EXPECTED_EVENT_COUNT,
    EXPECTED_SEQUENCE_COUNT,
    EXPECTED_SHOT_COUNT,
    EXPECTED_TOTAL_SECONDS,
    LIVE_EXECUTION,
    PAID_EXECUTION,
    PREDECESSOR_SCRIPT_FINGERPRINT,
    PREDECESSOR_SCRIPT_ID,
    PREDECESSOR_STORYBOARD_FINGERPRINT,
    PREDECESSOR_STORYBOARD_ID,
    VERSION,
    build_master_candidate,
    read_json,
    render_script_markdown,
    update_episode_definition,
    validate_inputs,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode-001-adam"
EDITORIAL = EPISODE / "editorial"
CINEMATIC = EPISODE / "cinematic"
EVIDENCE = EPISODE / "evidence"
CONTRACTS = EPISODE / "contracts"


class PrestigeStoryboardMasterV21Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script_v2 = read_json(EDITORIAL / "prestige-cinematic-script-v2.json")
        cls.storyboard_v2 = read_json(CINEMATIC / "detailed-storyboard-v2.json")
        cls.trace_v2 = read_json(EVIDENCE / "script-storyboard-evidence-trace-v2.json")
        cls.approval_v2 = read_json(EVIDENCE / "script-storyboard-human-approval-request-v2.json")
        cls.brief_v2 = read_json(CINEMATIC / "prestige-production-brief-v2.json")
        cls.definition = read_json(CONTRACTS / "episode-definition-v1.json")
        validate_inputs(
            script_v2=cls.script_v2,
            storyboard_v2=cls.storyboard_v2,
            trace_v2=cls.trace_v2,
            approval_request_v2=cls.approval_v2,
            production_brief_v2=cls.brief_v2,
            episode_definition=cls.definition,
        )
        (
            cls.script,
            cls.storyboard,
            cls.trace,
            cls.approval,
            cls.brief,
            cls.audit,
        ) = build_master_candidate(
            script_v2=cls.script_v2,
            storyboard_v2=cls.storyboard_v2,
            trace_v2=cls.trace_v2,
            approval_request_v2=cls.approval_v2,
            production_brief_v2=cls.brief_v2,
        )
        cls.updated = update_episode_definition(
            episode_definition=cls.definition,
            script=cls.script,
            storyboard=cls.storyboard,
            trace=cls.trace,
            approval_request=cls.approval,
            production_brief=cls.brief,
            audit=cls.audit,
        )

    def test_predecessor_script_is_exact(self):
        self.assertEqual(self.script_v2["script_id"], PREDECESSOR_SCRIPT_ID)
        self.assertEqual(self.script_v2["script_fingerprint"], PREDECESSOR_SCRIPT_FINGERPRINT)

    def test_predecessor_storyboard_is_exact(self):
        self.assertEqual(self.storyboard_v2["storyboard_id"], PREDECESSOR_STORYBOARD_ID)
        self.assertEqual(self.storyboard_v2["storyboard_fingerprint"], PREDECESSOR_STORYBOARD_FINGERPRINT)

    def test_version_is_2_1(self):
        self.assertEqual(self.script["director_cut_version"], VERSION)
        self.assertEqual(self.storyboard["director_cut_version"], VERSION)

    def test_fourteen_sequences_preserved(self):
        self.assertEqual(self.script["sequence_count"], EXPECTED_SEQUENCE_COUNT)
        self.assertEqual(len(self.script["sequences"]), EXPECTED_SEQUENCE_COUNT)

    def test_seventy_shots_preserved(self):
        self.assertEqual(self.storyboard["shot_count"], EXPECTED_SHOT_COUNT)
        self.assertEqual(len(self.storyboard["shots"]), EXPECTED_SHOT_COUNT)

    def test_duration_is_22_minutes(self):
        self.assertEqual(self.script["target_duration_seconds"], EXPECTED_TOTAL_SECONDS)
        self.assertEqual(sum(s["duration_seconds"] for s in self.storyboard["shots"]), EXPECTED_TOTAL_SECONDS)

    def test_exact_covenant_verse_is_present(self):
        narration = "\n".join(s["narration"] for s in self.script["sequences"])
        self.assertIn(EXACT_COVENANT_VERSE, narration)

    def test_malformed_covenant_text_is_absent(self):
        narration = "\n".join(s["narration"] for s in self.script["sequences"])
        self.assertNotIn("قالوا بلى شهد:", narration)
        self.assertNotIn("بربكمنا", narration)

    def test_descendants_emergence_is_assertive(self):
        seq = next(s for s in self.script["sequences"] if s["sequence_number"] == 11)
        self.assertIn("أخرج الله من ظهر آدم ذريته", seq["narration"])
        self.assertNotIn("رواية", seq["narration"])
        self.assertNotIn("خبر", seq["narration"])

    def test_sequence_11_title_is_final(self):
        seq = next(s for s in self.script["sequences"] if s["sequence_number"] == 11)
        self.assertEqual(seq["sequence_title"], "الميثاق والذرية")

    def test_sequence_11_qualification_is_chronology_only(self):
        seq = next(s for s in self.script["sequences"] if s["sequence_number"] == 11)
        self.assertEqual(
            seq["qualification_scope"]["EV-ADAM-061"],
            "CHRONOLOGICAL_LINK_ONLY; DESCENDANTS_EMERGENCE_AND_COVENANT_ORIGINS_ASSERTIVE",
        )

    def test_sequence_3_meta_language_is_polished(self):
        seq = next(s for s in self.script["sequences"] if s["sequence_number"] == 3)
        self.assertNotIn("لا يأتينا إلا من ظلال", seq["narration"])
        self.assertIn("يبقى هناك، في ظل الرواية", seq["narration"])

    def test_sequence_12_meta_language_is_polished(self):
        seq = next(s for s in self.script["sequences"] if s["sequence_number"] == 12)
        self.assertNotIn("ملأت بها بعض الروايات الفراغ", seq["narration"])
        self.assertIn("خلف ستار الحكاية", seq["narration"])

    def test_sequence_13_focuses_on_command_not_fruit(self):
        seq = next(s for s in self.script["sequences"] if s["sequence_number"] == 13)
        self.assertNotIn("حاولت روايات التفسير", seq["narration"])
        self.assertIn("مركز الامتحان لم يكن الثمرة، بل الأمر", seq["narration"])

    def test_narration_density_is_cinematic(self):
        self.assertGreaterEqual(self.script["narration_word_count"], 1200)
        self.assertLessEqual(self.script["narration_word_count"], 1600)

    def test_every_sequence_has_mastering(self):
        self.assertTrue(all(s.get("directorial_mastering") for s in self.script["sequences"]))

    def test_every_sequence_has_five_beat_escalation(self):
        self.assertTrue(all(len(s["directorial_mastering"]["shot_escalation"]) == 5 for s in self.script["sequences"]))

    def test_every_sequence_has_tension_curve(self):
        self.assertTrue(all(len(s["directorial_mastering"]["tension_curve"]) == 5 for s in self.script["sequences"]))

    def test_every_shot_has_dramatic_beat(self):
        self.assertTrue(all(s.get("dramatic_beat") for s in self.storyboard["shots"]))

    def test_every_shot_has_visual_subtext(self):
        self.assertTrue(all(s.get("visual_subtext") for s in self.storyboard["shots"]))

    def test_every_shot_has_camera_psychology(self):
        self.assertTrue(all(s.get("camera_psychology") for s in self.storyboard["shots"]))

    def test_every_shot_has_sound_perspective(self):
        self.assertTrue(all(s.get("sound_perspective") for s in self.storyboard["shots"]))

    def test_every_shot_has_cut_motivation(self):
        self.assertTrue(all(s.get("cut_motivation") for s in self.storyboard["shots"]))

    def test_every_shot_has_continuity_anchor(self):
        self.assertTrue(all(s.get("continuity_anchor") for s in self.storyboard["shots"]))

    def test_every_shot_has_acceptance_criteria(self):
        self.assertTrue(all(len(s.get("acceptance_criteria", [])) >= 4 for s in self.storyboard["shots"]))

    def test_every_shot_has_rejection_triggers(self):
        self.assertTrue(all(len(s.get("rejection_triggers", [])) >= 5 for s in self.storyboard["shots"]))

    def test_every_shot_is_ready_for_human_review(self):
        self.assertTrue(all(s["master_lock_status"] == "READY_FOR_HUMAN_STORYBOARD_REVIEW" for s in self.storyboard["shots"]))

    def test_all_dramatic_beats_are_unique(self):
        beats = [s["dramatic_beat"] for s in self.storyboard["shots"]]
        self.assertEqual(len(beats), len(set(beats)))

    def test_storyboard_has_master_visual_grammar(self):
        self.assertIn("lens_families", self.storyboard["master_visual_grammar"])
        self.assertIn("camera_law", self.storyboard["master_visual_grammar"])
        self.assertIn("colour_arc", self.storyboard["master_visual_grammar"])

    def test_storyboard_completion_is_complete(self):
        completion = self.storyboard["storyboard_completion"]
        self.assertEqual(completion["status"], "COMPLETE_AWAITING_HUMAN_APPROVAL")
        self.assertEqual(completion["unresolved_directorial_decisions"], 0)

    def test_no_generic_placeholders_remain(self):
        self.assertEqual(self.audit["generic_placeholder_shots"], 0)

    def test_audit_has_full_beat_coverage(self):
        self.assertEqual(self.audit["dramatic_beat_coverage"], EXPECTED_SHOT_COUNT)

    def test_audit_has_full_subtext_coverage(self):
        self.assertEqual(self.audit["visual_subtext_coverage"], EXPECTED_SHOT_COUNT)

    def test_audit_has_full_camera_coverage(self):
        self.assertEqual(self.audit["camera_psychology_coverage"], EXPECTED_SHOT_COUNT)

    def test_audit_has_full_sound_coverage(self):
        self.assertEqual(self.audit["sound_perspective_coverage"], EXPECTED_SHOT_COUNT)

    def test_audit_has_full_acceptance_coverage(self):
        self.assertEqual(self.audit["acceptance_criteria_coverage"], EXPECTED_SHOT_COUNT)

    def test_audit_has_full_rejection_coverage(self):
        self.assertEqual(self.audit["rejection_trigger_coverage"], EXPECTED_SHOT_COUNT)

    def test_event_trace_count_is_preserved(self):
        self.assertEqual(self.trace["event_count"], EXPECTED_EVENT_COUNT)

    def test_evidence_trace_count_is_preserved(self):
        self.assertEqual(self.trace["evidence_item_count"], EXPECTED_EVIDENCE_COUNT)

    def test_trace_records_chronology_only_scope(self):
        self.assertIn("Chronological linkage remains qualified", self.trace["qualification_scope"]["EV-ADAM-061"])

    def test_script_is_not_approved_automatically(self):
        self.assertFalse(self.script["human_script_approval"])
        self.assertFalse(self.script["religious_safety_approval"])

    def test_storyboard_is_not_approved_automatically(self):
        self.assertFalse(self.storyboard["human_storyboard_approval"])
        self.assertFalse(self.storyboard["master_visual_approval"])

    def test_approval_request_is_pending(self):
        self.assertFalse(self.approval["human_approval"])

    def test_approval_phrase_is_exact(self):
        self.assertEqual(self.approval["exact_approval_phrase"], APPROVAL_PHRASE)

    def test_approval_phrase_targets_v2_1(self):
        self.assertIn("إصدار 2.1", self.approval["exact_approval_phrase"])

    def test_approval_does_not_authorise_paid_execution(self):
        self.assertIn("دون السماح بأي تشغيل مدفوع أو مباشر", self.approval["exact_approval_phrase"])

    def test_all_artifacts_keep_live_execution_blocked(self):
        for artifact in (self.script, self.storyboard, self.trace, self.approval, self.brief, self.audit):
            self.assertEqual(artifact["live_provider_execution"], LIVE_EXECUTION)

    def test_all_artifacts_keep_paid_execution_blocked(self):
        for artifact in (self.script, self.storyboard, self.trace, self.approval, self.brief, self.audit):
            self.assertEqual(artifact["paid_execution"], PAID_EXECUTION)

    def test_no_generated_video_is_scheduled(self):
        self.assertEqual(self.brief["generated_video_planned_seconds"], 0)

    def test_provider_selection_is_deferred(self):
        self.assertEqual(self.brief["provider_selection"], "DEFERRED")

    def test_next_non_paid_stage_is_visual_bible_and_animatic(self):
        self.assertEqual(self.brief["next_non_paid_stage"], "MASTER_VISUAL_BIBLE_COLOR_SCRIPT_AND_ANIMATIC")

    def test_episode_definition_points_to_v2_1_script(self):
        self.assertEqual(self.updated["cinematic_script"]["path"], "editorial/prestige-cinematic-script-v2-1.json")

    def test_episode_definition_points_to_v2_1_storyboard(self):
        self.assertEqual(self.updated["detailed_storyboard"]["path"], "cinematic/detailed-storyboard-v2-1.json")

    def test_episode_definition_preserves_v2_predecessor(self):
        predecessor = self.updated["superseded_directors_cut_v2"]
        self.assertEqual(predecessor["script_fingerprint"], PREDECESSOR_SCRIPT_FINGERPRINT)
        self.assertEqual(predecessor["storyboard_fingerprint"], PREDECESSOR_STORYBOARD_FINGERPRINT)

    def test_episode_definition_records_descendants_assertive(self):
        self.assertEqual(self.updated["director_cut_revision"]["descendants_emergence"], "ASSERTIVE")

    def test_episode_definition_records_chronology_qualified_only(self):
        self.assertEqual(self.updated["director_cut_revision"]["chronological_linkage"], "QUALIFIED_ONLY")

    def test_episode_definition_has_exact_verse(self):
        self.assertEqual(self.updated["director_cut_revision"]["covenant_verse_text"], EXACT_COVENANT_VERSE)

    def test_episode_definition_next_stage_is_final_human_review(self):
        self.assertEqual(self.updated["next_stage"], "HUMAN_REVIEW_OF_FINAL_STORYBOARD_MASTER_V2_1")

    def test_episode_definition_update_is_idempotent(self):
        rebuilt = update_episode_definition(
            episode_definition=self.updated,
            script=self.script,
            storyboard=self.storyboard,
            trace=self.trace,
            approval_request=self.approval,
            production_brief=self.brief,
            audit=self.audit,
        )
        self.assertEqual(rebuilt, self.updated)

    def test_build_is_deterministic(self):
        second = build_master_candidate(
            script_v2=self.script_v2,
            storyboard_v2=self.storyboard_v2,
            trace_v2=self.trace_v2,
            approval_request_v2=self.approval_v2,
            production_brief_v2=self.brief_v2,
        )
        self.assertEqual((self.script, self.storyboard, self.trace, self.approval, self.brief, self.audit), second)

    def test_markdown_contains_exact_verse(self):
        markdown = render_script_markdown(self.script)
        self.assertIn(EXACT_COVENANT_VERSE, markdown)

    def test_markdown_has_final_master_title(self):
        markdown = render_script_markdown(self.script)
        self.assertIn("Final Storyboard Master v2.1", markdown)

    def test_shot_11_01_avoids_literal_body(self):
        shot = next(s for s in self.storyboard["shots"] if s["shot_id"] == "ADAM-DC2-S11-SH01")
        self.assertIn("لا يكتمل في هيئة بشرية", shot["composition"])
        self.assertIn("لا جسد لآدم", shot["religious_visual_safety"])

    def test_shot_11_02_has_exact_verse(self):
        shot = next(s for s in self.storyboard["shots"] if s["shot_id"] == "ADAM-DC2-S11-SH02")
        self.assertIn(EXACT_COVENANT_VERSE, shot["screen_action"])

    def test_shot_12_02_removes_research_cards(self):
        shot = next(s for s in self.storyboard["shots"] if s["shot_id"] == "ADAM-DC2-S12-SH02")
        self.assertNotIn("قيل", str(shot))
        self.assertNotIn("رُوي", str(shot))

    def test_shot_13_03_avoids_naming_tree(self):
        shot = next(s for s in self.storyboard["shots"] if s["shot_id"] == "ADAM-DC2-S13-SH03")
        self.assertIn("لا كخيارات مكتوبة", shot["composition"])
        self.assertIn("لا تعيين بصري", shot["religious_visual_safety"])

    def test_output_files_and_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(
                output_root=Path(tmp) / "report",
                script=self.script,
                storyboard=self.storyboard,
                trace=self.trace,
                approval_request=self.approval,
                production_brief=self.brief,
                audit=self.audit,
                episode_definition=self.updated,
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
                approval_request=self.approval,
                production_brief=self.brief,
                audit=self.audit,
                episode_definition=self.updated,
            )
            for key in ("script_json", "storyboard_json", "trace", "approval_request", "production_brief", "audit", "episode_definition"):
                raw = outputs[key].read_bytes()
                self.assertTrue(raw.endswith(b"\n"))
                self.assertNotIn(b"\r\n", raw)


if __name__ == "__main__":
    unittest.main()
