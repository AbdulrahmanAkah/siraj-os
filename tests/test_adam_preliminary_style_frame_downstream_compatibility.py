from __future__ import annotations

import unittest
from pathlib import Path

from src.application.storyboard_runtime.master_visual_human_approval_binding_v1 import (
    build_all as rebuild_previous_visual_approval,
    read_json,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode-001-adam"
CINEMATIC = EPISODE / "cinematic"
EVIDENCE = EPISODE / "evidence"
CONTRACTS = EPISODE / "contracts"


class AdamPreliminaryStyleFrameDownstreamCompatibilityTests(unittest.TestCase):
    def test_previous_visual_approval_runtime_preserves_new_references(self):
        definition = read_json(CONTRACTS / "episode-definition-v1.json")
        brief = read_json(CINEMATIC / "prestige-production-brief-v2-1.json")
        result = rebuild_previous_visual_approval(
            dossier=read_json(CINEMATIC / "master-visual-human-review-dossier-v1.json"),
            critical_review=read_json(CINEMATIC / "master-visual-critical-review-v1.json"),
            prototype_plan=read_json(CINEMATIC / "master-style-frame-prototype-plan-v1.json"),
            approval_request=read_json(EVIDENCE / "master-visual-human-approval-request-v1.json"),
            review_binding=read_json(CONTRACTS / "master-visual-human-review-binding-v1.json"),
            episode_definition=definition,
            production_brief=brief,
        )
        updated_definition = result[5]
        updated_brief = result[6]
        self.assertEqual(
            updated_definition["preliminary_style_frame_reference_set"],
            definition["preliminary_style_frame_reference_set"],
        )
        self.assertEqual(
            updated_definition["single_shot_motion_prototype_gate"],
            definition["single_shot_motion_prototype_gate"],
        )
        self.assertEqual(
            updated_brief["single_shot_motion_prototype_gate_id"],
            brief["single_shot_motion_prototype_gate_id"],
        )


if __name__ == "__main__":
    unittest.main()
