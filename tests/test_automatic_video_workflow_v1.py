from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from src.application.automatic_video_workflow_v1 import (
    PASS_THRESHOLD,
    decision_for_score,
    file_sha256,
    load_automatic_video_spec,
    load_state,
    save_final_score,
)


class AutomaticVideoWorkflowV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[1]

    def _temporary_repo(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        required = (
            "projects/episode-001-adam/cinematic/shot-packages/"
            "adam-dc2-s02-sh03/veo-shot-pack-001-v1.json",
            "projects/episode-001-adam/contracts/"
            "runware-beat-01-execution-authorization-v1.json",
            "projects/episode-001-adam/contracts/"
            "automatic-video-user-authorization-v1.json",
        )
        for relative in required:
            source = self.repo / relative
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        return temporary, root

    def test_score_contract_is_one_integer(self):
        self.assertEqual(PASS_THRESHOLD, 80)
        self.assertEqual(decision_for_score(0), "FAIL")
        self.assertEqual(decision_for_score(79), "FAIL")
        self.assertEqual(decision_for_score(80), "PASS")
        self.assertEqual(decision_for_score(100), "PASS")

    def test_three_deterministic_attempt_plans(self):
        spec = load_automatic_video_spec(self.repo)
        self.assertEqual(len(spec.plans), 3)
        self.assertEqual(
            [plan.prompt_variant for plan in spec.plans],
            [
                "ORIGINAL_SHOT_PACKAGE",
                "CONTINUITY_AND_PHYSICS_REPAIR",
                "SIMPLIFIED_CONTINUOUS_FALLBACK",
            ],
        )
        self.assertEqual(
            [plan.seed for plan in spec.plans],
            [3256281284, 3256281285, 3256281286],
        )

    def test_empty_state_is_ready_for_one_click_generation(self):
        temporary, root = self._temporary_repo()
        try:
            spec = load_automatic_video_spec(root)
            state = load_state(spec)
            self.assertEqual(state["status"], "READY_TO_GENERATE")
            self.assertEqual(state["current_attempt"], 1)
            self.assertEqual(state["pass_threshold"], 80)
            self.assertEqual(state["maximum_attempts"], 3)
        finally:
            temporary.cleanup()

    def test_fail_score_prepares_next_attempt(self):
        temporary, root = self._temporary_repo()
        try:
            spec = load_automatic_video_spec(root)
            output = spec.output_root / "attempt-01" / "sample.mp4"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"test-video")
            state = load_state(spec)
            state.update(
                {
                    "status": "AWAITING_SCORE",
                    "current_attempt": 1,
                    "attempts": [
                        {
                            "attempt_number": 1,
                            "prompt_variant": "ORIGINAL_SHOT_PACKAGE",
                            "status": "GENERATED_AWAITING_SCORE",
                            "task_uuid": "task",
                            "video_uuid": "video",
                            "output_path_relative": str(output.relative_to(root)),
                            "output_filename": output.name,
                            "output_sha256": file_sha256(output),
                            "returned_seed": 3256281284,
                            "actual_cost_usd": 0.18,
                            "score": None,
                            "decision": None,
                        }
                    ],
                }
            )
            spec.state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            review = save_final_score(root, 58)
            self.assertEqual(review["decision"], "FAIL")
            self.assertEqual(
                review["review_input_contract"],
                "ONE_INTEGER_ONLY_0_TO_100",
            )
            updated = load_state(spec)
            self.assertEqual(updated["status"], "READY_TO_GENERATE")
            self.assertEqual(updated["current_attempt"], 2)
        finally:
            temporary.cleanup()

    def test_pass_score_accepts_current_output(self):
        temporary, root = self._temporary_repo()
        try:
            spec = load_automatic_video_spec(root)
            output = spec.output_root / "attempt-01" / "sample.mp4"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"accepted-video")
            state = load_state(spec)
            relative = str(output.relative_to(root))
            state.update(
                {
                    "status": "AWAITING_SCORE",
                    "current_attempt": 1,
                    "attempts": [
                        {
                            "attempt_number": 1,
                            "prompt_variant": "ORIGINAL_SHOT_PACKAGE",
                            "status": "GENERATED_AWAITING_SCORE",
                            "task_uuid": "task",
                            "video_uuid": "video",
                            "output_path_relative": relative,
                            "output_filename": output.name,
                            "output_sha256": file_sha256(output),
                            "returned_seed": 3256281284,
                            "actual_cost_usd": 0.18,
                            "score": None,
                            "decision": None,
                        }
                    ],
                }
            )
            spec.state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            review = save_final_score(root, 90)
            self.assertEqual(review["decision"], "PASS")
            updated = load_state(spec)
            self.assertEqual(updated["status"], "ACCEPTED")
            self.assertEqual(updated["accepted_output_path_relative"], relative)
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
