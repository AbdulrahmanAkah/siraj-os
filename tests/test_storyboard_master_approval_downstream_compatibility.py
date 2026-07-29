from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.fast_track.build_adam_final_storyboard_master_v2_1 import (
    final_approval_binding_is_active,
    master_candidate_definition_compatible,
    merge_master_candidate_definition,
)
from src.application.storyboard_runtime.prestige_storyboard_master_v2_1 import (
    build_master_candidate,
    read_json,
    update_episode_definition,
)

ROOT = Path(__file__).resolve().parents[1]
EPISODE = ROOT / "projects/episode-001-adam"
EDITORIAL = EPISODE / "editorial"
CINEMATIC = EPISODE / "cinematic"
EVIDENCE = EPISODE / "evidence"
CONTRACTS = EPISODE / "contracts"
OLD_CLI = (
    ROOT / "scripts" / "fast_track"
    / "build_adam_final_storyboard_master_v2_1.py"
)


class StoryboardMasterApprovalDownstreamCompatibilityTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(cls):
        cls.current = read_json(
            CONTRACTS / "episode-definition-v1.json"
        )
        script_v2 = read_json(
            EDITORIAL / "prestige-cinematic-script-v2.json"
        )
        storyboard_v2 = read_json(
            CINEMATIC / "detailed-storyboard-v2.json"
        )
        trace_v2 = read_json(
            EVIDENCE / "script-storyboard-evidence-trace-v2.json"
        )
        approval_v2 = read_json(
            EVIDENCE / "script-storyboard-human-approval-request-v2.json"
        )
        brief_v2 = read_json(
            CINEMATIC / "prestige-production-brief-v2.json"
        )
        script, storyboard, trace, request, brief, audit = (
            build_master_candidate(
                script_v2=script_v2,
                storyboard_v2=storyboard_v2,
                trace_v2=trace_v2,
                approval_request_v2=approval_v2,
                production_brief_v2=brief_v2,
            )
        )
        cls.expected_candidate = update_episode_definition(
            episode_definition=cls.current,
            script=script,
            storyboard=storyboard,
            trace=trace,
            approval_request=request,
            production_brief=brief,
            audit=audit,
        )

    def test_master_cli_recognises_bound_human_approval(self):
        self.assertTrue(final_approval_binding_is_active(self.current))

    def test_master_validator_accepts_bound_human_approval(self):
        self.assertTrue(
            master_candidate_definition_compatible(
                self.current,
                self.expected_candidate,
            )
        )

    def test_master_materializer_preserves_bound_human_approval(self):
        self.assertEqual(
            merge_master_candidate_definition(
                self.current,
                self.expected_candidate,
            ),
            self.current,
        )

    def test_master_cli_audit_does_not_regress_approval(self):
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
            "STATUS=PASS_ADAM_FINAL_STORYBOARD_MASTER_V2_1",
            result.stdout,
        )
        after = (
            CONTRACTS / "episode-definition-v1.json"
        ).read_bytes()
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
