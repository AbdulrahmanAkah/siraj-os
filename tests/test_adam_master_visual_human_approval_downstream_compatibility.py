from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.application.storyboard_runtime.master_visual_human_approval_binding_v1 import (
    NEXT_STAGE,
    STYLE_FRAME_AUTHORISATION,
    read_json,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode-001-adam"
CINEMATIC = EPISODE / "cinematic"
CONTRACTS = EPISODE / "contracts"

OLD_REVIEW_CLI = ROOT / "scripts/fast_track/build_adam_master_visual_human_review_v1.py"
OLD_VISUAL_CLI = ROOT / "scripts/fast_track/build_adam_master_visual_development_v1.py"
OLD_APPROVAL_CLI = ROOT / "scripts/fast_track/bind_adam_final_storyboard_master_approval_v2_1.py"
OLD_STORYBOARD_CLI = ROOT / "scripts/fast_track/build_adam_final_storyboard_master_v2_1.py"


class AdamMasterVisualHumanApprovalDownstreamCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.definition_path = CONTRACTS / "episode-definition-v1.json"
        cls.plan_path = CINEMATIC / "master-style-frame-prototype-plan-v1.json"
        cls.brief_path = CINEMATIC / "prestige-production-brief-v2-1.json"
        cls.definition = read_json(cls.definition_path)
        cls.plan = read_json(cls.plan_path)

    def test_approved_stage_is_active(self):
        self.assertEqual(self.definition["next_stage"], NEXT_STAGE)
        self.assertFalse(self.definition["master_visual_approval"])
        self.assertEqual(
            self.plan["image_generation_authorisation"], STYLE_FRAME_AUTHORISATION
        )

    def _run_and_preserve(self, cli: Path):
        before = {
            self.definition_path: self.definition_path.read_bytes(),
            self.plan_path: self.plan_path.read_bytes(),
            self.brief_path: self.brief_path.read_bytes(),
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(cli),
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
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
        for path, payload in before.items():
            self.assertEqual(path.read_bytes(), payload, str(path))

    def test_previous_human_review_cli_does_not_regress_approval(self):
        self._run_and_preserve(OLD_REVIEW_CLI)

    def test_previous_visual_cli_does_not_regress_approval(self):
        self._run_and_preserve(OLD_VISUAL_CLI)

    def test_storyboard_approval_cli_does_not_regress_approval(self):
        self._run_and_preserve(OLD_APPROVAL_CLI)

    def test_storyboard_master_cli_does_not_regress_approval(self):
        self._run_and_preserve(OLD_STORYBOARD_CLI)


if __name__ == "__main__":
    unittest.main()
