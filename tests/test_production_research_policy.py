from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.application.storyboard_runtime.production_research_policy import (
    AUTOMATIC_APPROVAL_STATUS,
    EVIDENCE_GATE_STATUS,
    FILLER_PLAN_SCHEMA,
    GAP_EVENTS,
    MUSIC_POLICY,
    POLICY_BUNDLE_SCHEMA,
    RECITATION_AUDIO_MODE,
    RECITATION_CUE_PLAN_SCHEMA,
    REVIEW_STATUS,
    RIGHTS_STATUS,
    TARGETED_REVIEW_PACK_SCHEMA,
    AdamResearchProductionBuilder,
    ProductionPolicyError,
    build_notebooklm_prompts,
    validate_filler_plan,
    validate_policy_bundle,
    validate_recitation_plan,
    validate_targeted_review_pack,
    write_outputs,
)


FRAME_KEYS = [
    "symbolic-cold-open",
    "central-question",
    "before-adam",
    "creation-announcement",
    "formation-of-adam",
    "beginning-of-life",
    "knowledge-and-honor",
    "command-to-prostrate",
    "angels-prostrate",
    "iblis-refusal-climax",
    "covenant-withheld",
    "spouse-and-garden",
    "tree-prohibition",
    "next-episode-promise",
]


class ProductionResearchPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        self._write_fixture()
        self.builder = AdamResearchProductionBuilder(self.repo)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write_json(self, relative: str, payload: object) -> None:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _copy_policy(self, name: str) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "config"
            / name
        )
        destination = self.repo / "config" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())

    def _write_fixture(self) -> None:
        for name in (
            "temporary_hadith_verification_policy_v1.json",
            "cinematic_filler_policy_v1.json",
            "quran_recitation_audio_policy_v1.json",
        ):
            self._copy_policy(name)

        event_map = []
        for number in range(1, 100):
            event_id = f"EV-ADAM-{number:03d}"
            if event_id in {*GAP_EVENTS, "EV-ADAM-099"}:
                event_map.append(
                    {
                        "event_id": event_id,
                        "title": {
                            "EV-ADAM-031": "أول حركة وعطاس وكلام لآدم",
                            "EV-ADAM-071": "اسم حواء وتفاصيل خلقها",
                            "EV-ADAM-091": "الأقوال في نوع الشجرة",
                            "EV-ADAM-099": "تمهيد للحلقة التالية",
                        }[event_id],
                        "section": "fixture",
                        "verification_status": "deferred",
                    }
                )
        self._write_json(
            "projects/episode-001-adam/editorial/event-map.json",
            event_map,
        )

        review_root = (
            self.repo
            / "projects/episode-001-adam/sources/secondary/review"
        )
        review_root.mkdir(parents=True)
        records = [
            {
                "source_id": "SRC-HADITH-LIFE",
                "page": 12,
                "text": "فلما بلغت الروح أنفه عطس فقال الحمد لله",
            },
            {
                "source_id": "SRC-TAFSIR-EVE",
                "page": 44,
                "text": "ويذكر في بعض الأخبار اسم حواء وأنها خلقت من ضلع",
            },
            {
                "source_id": "SRC-TAFSIR-TREE",
                "page": 77,
                "text": "واختلفوا في الشجرة فقيل الحنطة وقيل الكرم",
            },
            {
                "source_id": "SRC-IGNORED",
                "api_key": "secret-value",
                "page": 88,
                "text": "موضوع لا علاقة له",
            },
        ]
        review_path = review_root / "records.jsonl"
        review_path.write_text(
            "".join(
                json.dumps(item, ensure_ascii=False) + "\n"
                for item in records
            ),
            encoding="utf-8",
        )

        self._write_json(
            "projects/episode-001-adam/evidence/"
            "recovered-evidence-knowledge-v1.json",
            {
                "schema_version": "siraj-recovered-evidence-knowledge-v1",
                "evidence_gate_status": EVIDENCE_GATE_STATUS,
                "automatic_evidence_approval": AUTOMATIC_APPROVAL_STATUS,
                "uncovered_event_ids": [*GAP_EVENTS, "EV-ADAM-099"],
                "review_artifacts": [
                    {
                        "artifact": {
                            "relative_path": review_path.relative_to(
                                self.repo
                            ).as_posix()
                        }
                    }
                ],
            },
        )
        self._write_json(
            "projects/episode-001-adam/evidence/"
            "evidence-gap-closure-docket-v1.json",
            {
                "schema_version": "siraj-evidence-gap-closure-docket-v1",
                "status": "HUMAN_REVIEW_PENDING",
            },
        )

        frames = []
        for position, key in enumerate(FRAME_KEYS):
            frames.append(
                {
                    "frame_id": f"frame-{position}",
                    "position": position,
                    "trace_metadata": {
                        "frame_keys": [key],
                        "event_ids": [],
                    },
                }
            )
        self._write_json(
            "projects/episode-001-adam/cinematic/"
            "editorial-cinematic-blueprint-v1.json",
            {"storyboard": {"frames": frames}},
        )
        self._write_json(
            "projects/episode-001-adam/contracts/"
            "source-package-v1.draft.json",
            {
                "source_items": [
                    {
                        "source_id": "SRC-HADITH-LIFE",
                        "title": "حديث الحياة",
                        "source_type": "HADITH",
                    },
                    {
                        "source_id": "SRC-TAFSIR-EVE",
                        "title": "تفسير الزوج",
                        "source_type": "TAFSIR",
                    },
                    {
                        "source_id": "SRC-TAFSIR-TREE",
                        "title": "تفسير الشجرة",
                        "source_type": "TAFSIR",
                    },
                ]
            },
        )

    def test_builds_all_four_outputs(self) -> None:
        built = self.builder.build_all()
        self.assertEqual(
            built["policy_bundle"]["schema_version"],
            POLICY_BUNDLE_SCHEMA,
        )
        self.assertEqual(
            built["review_pack"]["schema_version"],
            TARGETED_REVIEW_PACK_SCHEMA,
        )
        self.assertEqual(
            built["filler_plan"]["schema_version"],
            FILLER_PLAN_SCHEMA,
        )
        self.assertEqual(
            built["recitation_plan"]["schema_version"],
            RECITATION_CUE_PLAN_SCHEMA,
        )

    def test_review_pack_has_exact_three_factual_gaps(self) -> None:
        pack = self.builder.build_all()["review_pack"]
        self.assertEqual(
            [item["event_id"] for item in pack["events"]],
            list(GAP_EVENTS),
        )
        self.assertTrue(
            all(item["default_disposition"] is None for item in pack["events"])
        )

    def test_prefilter_finds_all_fixture_candidates(self) -> None:
        pack = self.builder.build_all()["review_pack"]
        counts = {
            item["event_id"]: item["candidate_record_count"]
            for item in pack["events"]
        }
        self.assertGreaterEqual(counts["EV-ADAM-031"], 1)
        self.assertGreaterEqual(counts["EV-ADAM-071"], 1)
        self.assertGreaterEqual(counts["EV-ADAM-091"], 1)

    def test_prefilter_is_never_evidence(self) -> None:
        pack = self.builder.build_all()["review_pack"]
        for event in pack["events"]:
            for candidate in event["candidates"]:
                self.assertEqual(
                    candidate["status"],
                    "AUTOMATED_PREFILTER_NOT_EVIDENCE",
                )

    def test_secret_value_is_not_copied(self) -> None:
        serialized = json.dumps(
            self.builder.build_all()["review_pack"],
            ensure_ascii=False,
        )
        self.assertNotIn("secret-value", serialized)

    def test_absolute_paths_do_not_leak(self) -> None:
        serialized = json.dumps(
            self.builder.build_all()["review_pack"],
            ensure_ascii=False,
        )
        self.assertNotIn(str(self.repo), serialized)

    def test_dorar_is_temporary_not_automatic(self) -> None:
        pack = self.builder.build_all()["review_pack"]
        policy = pack["temporary_hadith_verification"]
        self.assertEqual(policy["status"], "TEMPORARILY_ALLOWED")
        self.assertTrue(policy["exact_scholar_attribution_required"])
        self.assertTrue(policy["human_verification_required"])
        self.assertTrue(policy["automatic_grading_forbidden"])

    def test_notebooklm_cannot_approve_or_grade(self) -> None:
        method = self.builder.build_all()["review_pack"]["extraction_method"]
        self.assertFalse(method["notebooklm_may_approve"])
        self.assertFalse(method["notebooklm_may_grade_hadith"])

    def test_music_is_prohibited_in_filler_plan(self) -> None:
        plan = self.builder.build_all()["filler_plan"]
        self.assertEqual(plan["music_policy"], MUSIC_POLICY)

    def test_filler_plan_covers_fourteen_frames(self) -> None:
        plan = self.builder.build_all()["filler_plan"]
        self.assertEqual(len(plan["frames"]), 14)
        self.assertEqual(
            [item["frame_key"] for item in plan["frames"]],
            FRAME_KEYS,
        )

    def test_real_adam_frame_keys_all_have_explicit_filler_plans(self) -> None:
        plan = self.builder.build_all()["filler_plan"]
        by_key = {item["frame_key"]: item for item in plan["frames"]}
        self.assertEqual(set(by_key), set(FRAME_KEYS))
        for key in FRAME_KEYS:
            self.assertTrue(by_key[key]["filler_suggestions"])

    def test_filler_has_no_historical_assertions(self) -> None:
        plan = self.builder.build_all()["filler_plan"]
        for item in plan["frames"]:
            self.assertFalse(item["historical_assertion"])
            self.assertFalse(item["geographical_assertion"])
            self.assertFalse(item["chronological_assertion"])
            self.assertFalse(item["identity_assertion"])
            self.assertTrue(item["symbolic_only"])

    def test_battle_travel_and_social_filler_require_context(self) -> None:
        bundle = self.builder.build_all()["policy_bundle"]
        filler = next(
            item
            for item in bundle["policies"]
            if item["schema_version"] == "siraj-cinematic-filler-policy-v1"
        )
        contextual = filler["contextual_filler"]
        self.assertTrue(
            contextual["battle_preparations"][
                "requires_verified_battle_context"
            ]
        )
        self.assertTrue(
            contextual["travel_preparations"][
                "requires_verified_travel_context"
            ]
        )
        self.assertTrue(
            contextual["social_conditions"][
                "requires_verified_period_context"
            ]
        )

    def test_paradise_and_hell_are_conceptual_only(self) -> None:
        plan = self.builder.build_all()["filler_plan"]
        afterlife = plan["afterlife_visualization"]
        self.assertTrue(afterlife["paradise"]["allowed"])
        self.assertFalse(afterlife["paradise"]["true_form_claim"])
        self.assertTrue(afterlife["hell"]["allowed"])
        self.assertFalse(afterlife["hell"]["true_form_claim"])
        self.assertFalse(
            afterlife["hell"]["duration_or_person_specific_judgment_from_visuals"]
        )

    def test_reciter_and_period_are_fixed(self) -> None:
        plan = self.builder.build_all()["recitation_plan"]
        self.assertEqual(plan["preferred_reciter"], "مشاري راشد العفاسي")
        self.assertEqual(
            plan["preferred_period"],
            {"start_year": 1998, "end_year": 2010},
        )

    def test_quran_recitation_has_exclusive_audio(self) -> None:
        plan = self.builder.build_all()["recitation_plan"]
        self.assertEqual(
            plan["recitation_audio_mode"],
            RECITATION_AUDIO_MODE,
        )
        for cue in plan["cues"]:
            self.assertTrue(cue["narrator_muted"])
            self.assertTrue(cue["ambience_muted"])
            self.assertTrue(cue["sound_effects_muted"])
            self.assertFalse(cue["music_present"])

    def test_recitation_rights_are_not_assumed(self) -> None:
        plan = self.builder.build_all()["recitation_plan"]
        self.assertEqual(plan["rights_policy"]["status"], RIGHTS_STATUS)
        self.assertFalse(plan["rights_policy"]["rights_assumed_clear"])
        self.assertFalse(
            all(cue["publication_allowed"] for cue in plan["cues"])
        )

    def test_recitation_cues_are_candidates_not_final(self) -> None:
        cues = self.builder.build_all()["recitation_plan"]["cues"]
        self.assertTrue(
            all(cue["selection_status"] == "CANDIDATE_NOT_SELECTED" for cue in cues)
        )

    def test_notebooklm_prompt_requires_exact_text_and_locator(self) -> None:
        prompts = self.builder.build_all()["notebooklm_prompts"]
        self.assertIn("النص العربي المطابق حرفيًا", prompts)
        self.assertIn("الجزء والصفحة والباب", prompts)
        self.assertIn("لا تصحح حديثًا", prompts)
        for event_id in GAP_EVENTS:
            self.assertIn(event_id, prompts)

    def test_output_write_is_utf8_lf(self) -> None:
        built = self.builder.build_all()
        output = Path(self.temp.name) / "out"
        paths = write_outputs(output, built)
        for path in paths.values():
            data = path.read_bytes()
            self.assertNotIn(b"\r\n", data)
            data.decode("utf-8")

    def test_manifest_is_deterministic(self) -> None:
        first = self.builder.build_all()
        second = self.builder.build_all()
        self.assertEqual(first, second)

    def test_validation_rejects_music_change(self) -> None:
        plan = self.builder.build_all()["filler_plan"]
        tampered = json.loads(json.dumps(plan))
        tampered["music_policy"] = "ALLOWED"
        with self.assertRaises(ProductionPolicyError):
            validate_filler_plan(tampered)

    def test_validation_rejects_filler_fact_claim(self) -> None:
        plan = self.builder.build_all()["filler_plan"]
        tampered = json.loads(json.dumps(plan))
        tampered["frames"][0]["historical_assertion"] = True
        with self.assertRaises(ProductionPolicyError):
            validate_filler_plan(tampered)

    def test_validation_rejects_recitation_mix(self) -> None:
        plan = self.builder.build_all()["recitation_plan"]
        tampered = json.loads(json.dumps(plan))
        tampered["cues"][0]["ambience_muted"] = False
        with self.assertRaises(ProductionPolicyError):
            validate_recitation_plan(tampered)

    def test_validation_rejects_auto_disposition(self) -> None:
        pack = self.builder.build_all()["review_pack"]
        tampered = json.loads(json.dumps(pack))
        tampered["events"][0]["default_disposition"] = "include_assertive"
        with self.assertRaises(ProductionPolicyError):
            validate_targeted_review_pack(tampered)

    def test_policy_bundle_rejects_dorar_disable(self) -> None:
        bundle = self.builder.build_all()["policy_bundle"]
        tampered = json.loads(json.dumps(bundle))
        for item in tampered["policies"]:
            if (
                item["schema_version"]
                == "siraj-temporary-hadith-verification-policy-v1"
            ):
                item["dorar_status"] = "DISABLED"
        with self.assertRaises(ProductionPolicyError):
            validate_policy_bundle(tampered)

    def test_cli_runs_from_arbitrary_cwd(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        script = (
            repository_root
            / "scripts/fast_track/build_adam_research_production_pack_v1.py"
        )
        output = Path(self.temp.name) / "cli-output"
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                str(script),
                "--repo-root",
                str(self.repo),
                "--policy-root",
                str(self.repo),
                "--output-root",
                str(output),
            ],
            cwd=Path(self.temp.name),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
        )
        self.assertIn(
            "STATUS=PASS_ADAM_RESEARCH_PRODUCTION_PACK_BUILT",
            result.stdout,
        )
        self.assertTrue(
            (
                output
                / "projects/episode-001-adam/evidence/"
                "targeted-review-pack-v1.json"
            ).is_file()
        )


if __name__ == "__main__":
    unittest.main()
