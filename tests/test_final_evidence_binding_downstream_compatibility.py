from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from scripts.fast_track.build_adam_final_evidence_approval_binding_v1 import (
    BINDING_EPISODE_KEYS,
    DOWNSTREAM_EPISODE_KEYS,
    binding_episode_fields_match,
    merge_episode_definition,
)

ROOT = Path(__file__).resolve().parents[1]
DEFINITION_PATH = (
    ROOT
    / "projects"
    / "episode-001-adam"
    / "contracts"
    / "episode-definition-v1.json"
)


class FinalEvidenceBindingDownstreamCompatibilityTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.current = json.loads(
            DEFINITION_PATH.read_text(encoding="utf-8-sig")
        )
        cls.legacy_expected = copy.deepcopy(cls.current)
        for key in DOWNSTREAM_EPISODE_KEYS:
            cls.legacy_expected.pop(key, None)
        cls.legacy_expected["next_stage"] = (
            "EVIDENCE_BOUND_CINEMATIC_SCRIPT_"
            "AND_STORYBOARD_DEVELOPMENT"
        )

    def test_binding_validator_accepts_downstream_definition(self):
        self.assertTrue(
            binding_episode_fields_match(
                self.current,
                self.legacy_expected,
            )
        )
        self.assertNotEqual(
            self.current.get("next_stage"),
            self.legacy_expected.get("next_stage"),
        )

    def test_materialize_merge_preserves_downstream_progress(self):
        merged = merge_episode_definition(
            self.current,
            self.legacy_expected,
        )
        self.assertEqual(
            merged.get("next_stage"),
            self.current.get("next_stage"),
        )
        for key in DOWNSTREAM_EPISODE_KEYS:
            self.assertEqual(merged.get(key), self.current.get(key))
        for key in BINDING_EPISODE_KEYS:
            self.assertEqual(
                merged.get(key),
                self.legacy_expected.get(key),
            )


if __name__ == "__main__":
    unittest.main()
