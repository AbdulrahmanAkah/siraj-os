from __future__ import annotations

from pathlib import Path
import unittest

from scripts.fast_track.build_adam_prestige_cinematic_script_storyboard_v1 import (
    has_directors_cut_v2,
    merge_v1_episode_definition,
    v1_episode_definition_compatible,
)
from src.application.storyboard_runtime.prestige_cinematic_script_storyboard import (
    read_json as read_v1_json,
    update_episode_definition as update_v1_definition,
)
from src.application.storyboard_runtime.prestige_cinematic_directors_cut_v2 import (
    read_json as read_v2_json,
    update_episode_definition as update_v2_definition,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode-001-adam"
CONTRACTS = EPISODE / "contracts"
EDITORIAL = EPISODE / "editorial"
EVIDENCE = EPISODE / "evidence"
CINEMATIC = EPISODE / "cinematic"


class StoryboardMasterLegacyChainCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = read_v2_json(
            CONTRACTS / "episode-definition-v1.json"
        )

        cls.script_v1 = read_v1_json(
            EDITORIAL / "prestige-cinematic-script-v1.json"
        )
        cls.storyboard_v1 = read_v1_json(
            CINEMATIC / "detailed-storyboard-v1.json"
        )
        cls.trace_v1 = read_v1_json(
            EVIDENCE / "script-storyboard-evidence-trace-v1.json"
        )
        cls.approval_v1 = read_v1_json(
            EVIDENCE
            / "script-storyboard-human-approval-request-v1.json"
        )
        cls.brief_v1 = read_v1_json(
            CINEMATIC / "prestige-production-brief-v1.json"
        )
        cls.expected_v1 = update_v1_definition(
            episode_definition=cls.current,
            script=cls.script_v1,
            storyboard=cls.storyboard_v1,
            trace=cls.trace_v1,
            approval_request=cls.approval_v1,
            production_brief=cls.brief_v1,
        )

        cls.script_v2 = read_v2_json(
            EDITORIAL / "prestige-cinematic-script-v2.json"
        )
        cls.storyboard_v2 = read_v2_json(
            CINEMATIC / "detailed-storyboard-v2.json"
        )
        cls.trace_v2 = read_v2_json(
            EVIDENCE / "script-storyboard-evidence-trace-v2.json"
        )
        cls.approval_v2 = read_v2_json(
            EVIDENCE
            / "script-storyboard-human-approval-request-v2.json"
        )
        cls.brief_v2 = read_v2_json(
            CINEMATIC / "prestige-production-brief-v2.json"
        )
        cls.rebuilt_v2 = update_v2_definition(
            episode_definition=cls.current,
            script=cls.script_v2,
            storyboard=cls.storyboard_v2,
            trace=cls.trace_v2,
            approval_request=cls.approval_v2,
            production_brief=cls.brief_v2,
        )

    def test_v1_detector_accepts_storyboard_master_v2_1(self):
        self.assertTrue(has_directors_cut_v2(self.current))
        self.assertEqual(
            str(self.current["director_cut_revision"]["version"]),
            "2.1",
        )

    def test_v1_validator_accepts_storyboard_master_v2_1(self):
        self.assertTrue(
            v1_episode_definition_compatible(
                self.current,
                self.expected_v1,
            )
        )
        self.assertEqual(
            merge_v1_episode_definition(
                self.current,
                self.expected_v1,
            ),
            self.current,
        )

    def test_v2_audit_view_preserves_original_v1_predecessor(self):
        superseded = self.rebuilt_v2[
            "superseded_script_storyboard_v1"
        ]
        self.assertEqual(
            superseded["cinematic_script"]["path"],
            "editorial/prestige-cinematic-script-v1.json",
        )
        self.assertEqual(
            superseded["detailed_storyboard"]["path"],
            "cinematic/detailed-storyboard-v1.json",
        )

    def test_v2_audit_view_does_not_mutate_current_master(self):
        self.assertEqual(
            self.rebuilt_v2["director_cut_revision"]["version"],
            2,
        )
        self.assertEqual(
            str(self.current["director_cut_revision"]["version"]),
            "2.1",
        )
        self.assertEqual(
            self.current["cinematic_script"]["path"],
            "editorial/prestige-cinematic-script-v2-1.json",
        )
        self.assertEqual(
            self.current["detailed_storyboard"]["path"],
            "cinematic/detailed-storyboard-v2-1.json",
        )


if __name__ == "__main__":
    unittest.main()
