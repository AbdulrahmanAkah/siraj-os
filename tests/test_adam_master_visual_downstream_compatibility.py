from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.fast_track.build_adam_final_storyboard_master_v2_1 import (
    final_approval_binding_is_active,
    merge_master_candidate_definition,
    merge_master_candidate_production_brief,
)
from src.application.storyboard_runtime.final_storyboard_master_approval_binding_v2_1 import (
    build_all as rebuild_storyboard_approval,
    read_json,
)
from src.application.storyboard_runtime.master_visual_development_v1 import (
    DOWNSTREAM_REVIEW_DECISION_STAGE,
    NEXT_STAGE,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode-001-adam"
EDITORIAL = EPISODE / "editorial"
CINEMATIC = EPISODE / "cinematic"
EVIDENCE = EPISODE / "evidence"
CONTRACTS = EPISODE / "contracts"
OLD_CLI = ROOT / "scripts/fast_track/build_adam_final_storyboard_master_v2_1.py"


class AdamMasterVisualDownstreamCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definition = read_json(CONTRACTS / "episode-definition-v1.json")

    def test_legacy_storyboard_master_recognises_visual_review_state(self):
        self.assertTrue(final_approval_binding_is_active(self.definition))

    def test_legacy_storyboard_master_preserves_visual_review_state(self):
        self.assertIs(
            merge_master_candidate_definition(
                self.definition,
                {"candidate": "must-not-replace-downstream-state"},
            ),
            self.definition,
        )

    def test_storyboard_approval_rebuild_preserves_visual_review_state(self):
        rebuilt = rebuild_storyboard_approval(
            script=read_json(EDITORIAL / "prestige-cinematic-script-v2-1.json"),
            storyboard=read_json(CINEMATIC / "detailed-storyboard-v2-1.json"),
            trace=read_json(EVIDENCE / "script-storyboard-evidence-trace-v2-1.json"),
            approval_request=read_json(
                EVIDENCE / "script-storyboard-human-approval-request-v2-1.json"
            ),
            audit=read_json(
                CINEMATIC / "storyboard-master-directorial-audit-v2-1.json"
            ),
            episode_definition=self.definition,
        )
        updated_definition = rebuilt[-1]
        self.assertEqual(
            updated_definition["next_stage"],
            self.definition["next_stage"],
        )
        self.assertEqual(
            updated_definition["master_visual_development"],
            self.definition["master_visual_development"],
        )


    def test_legacy_storyboard_master_preserves_visual_production_brief(self):
        current_brief = read_json(
            CINEMATIC / "prestige-production-brief-v2-1.json"
        )
        self.assertIs(
            merge_master_candidate_production_brief(
                current_brief,
                {"candidate": "must-not-replace-downstream-brief"},
                self.definition,
            ),
            current_brief,
        )

    def test_legacy_storyboard_cli_audit_preserves_visual_review_state(self):
        definition_path = CONTRACTS / "episode-definition-v1.json"
        brief_path = CINEMATIC / "prestige-production-brief-v2-1.json"
        before_definition = definition_path.read_bytes()
        before_brief = brief_path.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(OLD_CLI),
                    "--repo-root",
                    str(ROOT),
                    "--output-root",
                    str(Path(tmp) / "report"),
                ],
                cwd=tmp,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=True,
            )
        self.assertIn(
            "STATUS=PASS_ADAM_FINAL_STORYBOARD_MASTER_V2_1",
            result.stdout,
        )
        self.assertIn(
            f"NEXT_STAGE={self.definition['next_stage']}",
            result.stdout,
        )
        self.assertEqual(definition_path.read_bytes(), before_definition)
        self.assertEqual(brief_path.read_bytes(), before_brief)


if __name__ == "__main__":
    unittest.main()
