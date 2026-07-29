from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.fast_track.build_adam_prestige_cinematic_script_storyboard_v1 import (
    has_directors_cut_v2,
    merge_v1_episode_definition,
    v1_episode_definition_compatible,
)
from src.application.storyboard_runtime.prestige_cinematic_script_storyboard import (
    read_json,
    update_episode_definition,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode-001-adam"
CONTRACTS = EPISODE / "contracts"
EDITORIAL = EPISODE / "editorial"
EVIDENCE = EPISODE / "evidence"
CINEMATIC = EPISODE / "cinematic"
OLD_CLI = (
    ROOT
    / "scripts"
    / "fast_track"
    / "build_adam_prestige_cinematic_script_storyboard_v1.py"
)


class PrestigeScriptV1DirectorsCutCompatibilityTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.current = read_json(
            CONTRACTS / "episode-definition-v1.json"
        )
        cls.script_v1 = read_json(
            EDITORIAL / "prestige-cinematic-script-v1.json"
        )
        cls.storyboard_v1 = read_json(
            CINEMATIC / "detailed-storyboard-v1.json"
        )
        cls.trace_v1 = read_json(
            EVIDENCE / "script-storyboard-evidence-trace-v1.json"
        )
        cls.approval_v1 = read_json(
            EVIDENCE
            / "script-storyboard-human-approval-request-v1.json"
        )
        cls.brief_v1 = read_json(
            CINEMATIC / "prestige-production-brief-v1.json"
        )
        cls.expected_v1 = update_episode_definition(
            episode_definition=cls.current,
            script=cls.script_v1,
            storyboard=cls.storyboard_v1,
            trace=cls.trace_v1,
            approval_request=cls.approval_v1,
            production_brief=cls.brief_v1,
        )

    def test_v1_validator_accepts_current_directors_cut(self):
        self.assertTrue(has_directors_cut_v2(self.current))
        self.assertTrue(
            v1_episode_definition_compatible(
                self.current,
                self.expected_v1,
            )
        )

    def test_v1_materializer_preserves_current_directors_cut(self):
        merged = merge_v1_episode_definition(
            self.current,
            self.expected_v1,
        )
        self.assertEqual(merged, self.current)
        self.assertIn(
            str(merged["director_cut_revision"]["version"]),
            {"2", "2.1"},
        )

    def test_v1_cli_audit_does_not_regress_definition(self):
        before = (
            CONTRACTS / "episode-definition-v1.json"
        ).read_bytes()
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
            "STATUS=PASS_ADAM_PRESTIGE_CINEMATIC_SCRIPT_STORYBOARD",
            result.stdout,
        )
        after = (
            CONTRACTS / "episode-definition-v1.json"
        ).read_bytes()
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
