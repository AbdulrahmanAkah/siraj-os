from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.application.storyboard_runtime.master_visual_development_v1 import (
    build_all as build_visual_development,
    read_json,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode-001-adam"
CINEMATIC = EPISODE / "cinematic"
EVIDENCE = EPISODE / "evidence"
CONTRACTS = EPISODE / "contracts"


class AdamMasterVisualHumanReviewDownstreamCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storyboard = read_json(CINEMATIC / "detailed-storyboard-v2-1.json")
        cls.approval = read_json(
            EVIDENCE / "final-storyboard-master-human-approval-v2-1.json"
        )
        cls.approval_binding = read_json(
            CONTRACTS / "final-storyboard-master-approval-binding-v2-1.json"
        )
        cls.visual_gate = read_json(
            CINEMATIC / "non-paid-visual-development-gate-v1.json"
        )
        cls.definition = read_json(CONTRACTS / "episode-definition-v1.json")
        cls.brief = read_json(CINEMATIC / "prestige-production-brief-v2-1.json")

    def test_previous_visual_runtime_preserves_human_decision_state(self):
        result = build_visual_development(
            storyboard=self.storyboard,
            approval=self.approval,
            approval_binding=self.approval_binding,
            visual_gate=self.visual_gate,
            episode_definition=self.definition,
            production_brief=self.brief,
        )
        self.assertEqual(result[-2], self.definition)
        self.assertEqual(result[-1], self.brief)

    def test_previous_visual_cli_audit_does_not_regress_review(self):
        definition_before = copy.deepcopy(self.definition)
        brief_before = copy.deepcopy(self.brief)
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(
                        ROOT
                        / "scripts/fast_track/build_adam_master_visual_development_v1.py"
                    ),
                    "--repo-root",
                    str(ROOT),
                    "--output-root",
                    str(Path(tmp) / "report"),
                ],
                cwd=str(ROOT),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
            )
        self.assertIn(
            "NEXT_STAGE=HUMAN_DECISION_ON_MASTER_VISUAL_DEVELOPMENT_REVIEW_V1",
            result.stdout,
        )
        self.assertEqual(
            json.loads(
                (CONTRACTS / "episode-definition-v1.json").read_text(
                    encoding="utf-8-sig"
                )
            ),
            definition_before,
        )
        self.assertEqual(
            json.loads(
                (CINEMATIC / "prestige-production-brief-v2-1.json").read_text(
                    encoding="utf-8-sig"
                )
            ),
            brief_before,
        )


    def test_storyboard_approval_cli_preserves_human_decision_state(self):
        definition_path = CONTRACTS / "episode-definition-v1.json"
        before = definition_path.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(
                        ROOT
                        / "scripts/fast_track/bind_adam_final_storyboard_master_approval_v2_1.py"
                    ),
                    "--repo-root",
                    str(ROOT),
                    "--output-root",
                    str(Path(tmp) / "report"),
                ],
                cwd=str(ROOT),
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
            )
        self.assertIn(
            "NEXT_STAGE=HUMAN_DECISION_ON_MASTER_VISUAL_DEVELOPMENT_REVIEW_V1",
            result.stdout,
        )
        self.assertEqual(definition_path.read_bytes(), before)

    def test_legacy_storyboard_state_recognises_human_decision_stage(self):
        from scripts.fast_track.build_adam_final_storyboard_master_v2_1 import (
            final_approval_binding_is_active,
            visual_review_state_is_active,
        )

        self.assertTrue(final_approval_binding_is_active(self.definition))
        self.assertTrue(visual_review_state_is_active(self.definition))


if __name__ == "__main__":
    unittest.main()
