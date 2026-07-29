from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from scripts.fast_track.build_adam_prestige_cinematic_directors_cut_v2 import (
    has_storyboard_master_v2_1,
    merge_v2_episode_definition,
    v2_episode_definition_compatible,
)

ROOT = Path(__file__).resolve().parents[1]
DEFINITION = ROOT / "projects/episode-001-adam/contracts/episode-definition-v1.json"


class DirectorsCutV2MasterV21CompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.current = json.loads(DEFINITION.read_text(encoding="utf-8-sig"))
        cls.expected_v2 = copy.deepcopy(cls.current)
        predecessor = cls.current["superseded_directors_cut_v2"]
        cls.expected_v2["cinematic_script"] = predecessor["cinematic_script"]
        cls.expected_v2["detailed_storyboard"] = predecessor["detailed_storyboard"]
        cls.expected_v2["director_cut_revision"] = {"version": 2}

    def test_v2_cli_recognises_master_v2_1(self):
        self.assertTrue(has_storyboard_master_v2_1(self.current))

    def test_v2_validator_accepts_master_v2_1(self):
        self.assertTrue(v2_episode_definition_compatible(self.current, self.expected_v2))

    def test_v2_materializer_preserves_master_v2_1(self):
        self.assertEqual(merge_v2_episode_definition(self.current, self.expected_v2), self.current)


if __name__ == "__main__":
    unittest.main()
