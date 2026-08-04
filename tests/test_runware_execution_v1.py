from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
import uuid

from src.application.runware_execution_v1 import (
    ProductionGateError,
    _create_submission_lock,
    build_video_inference_payload,
    load_execution_spec,
)


class RunwareExecutionV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[1]
        cls.spec = load_execution_spec(cls.repo)

    def test_authorized_spec(self):
        self.assertEqual(self.spec.beat_id, "ADAM-DC2-S02-SH03-B01")
        self.assertEqual(self.spec.max_cost_usd, 0.40)
        self.assertEqual(self.spec.number_results, 1)

    def test_payload_is_exactly_one_async_video_task(self):
        task_uuid = str(uuid.uuid4())
        payload = build_video_inference_payload(self.spec, task_uuid)
        self.assertEqual(len(payload), 1)
        task = payload[0]
        self.assertEqual(task["taskType"], "videoInference")
        self.assertEqual(task["model"], "google:veo@3.1-lite")
        self.assertEqual((task["width"], task["height"]), (1280, 720))
        self.assertEqual(task["duration"], 8)
        self.assertEqual(task["seed"], 3256281284)
        self.assertEqual(task["numberResults"], 1)
        self.assertEqual(task["deliveryMethod"], "async")
        self.assertTrue(task["includeCost"])
        self.assertNotIn("resolution", task)
        self.assertNotIn("negativePrompt", task)
        self.assertFalse(task["providerSettings"]["google"]["generateAudio"])
        self.assertEqual(
            task["providerSettings"]["google"]["personGeneration"],
            "dont_allow",
        )

    def test_invalid_task_uuid_rejected(self):
        with self.assertRaises(ProductionGateError):
            build_video_inference_payload(self.spec, "not-a-uuid")

    def test_pre_network_lock_is_single_use(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "outputs"
            spec = replace(
                self.spec,
                repo_root=root,
                output_dir=output,
                lock_path=output / "lock.json",
                receipt_path=output / "receipt.json",
                review_path=output / "review.json",
            )
            task_uuid = str(uuid.uuid4())
            payload = build_video_inference_payload(spec, task_uuid)
            _create_submission_lock(spec, task_uuid, payload)
            with self.assertRaises(ProductionGateError):
                _create_submission_lock(spec, str(uuid.uuid4()), payload)
            lock = json.loads(spec.lock_path.read_text(encoding="utf-8"))
            self.assertEqual(lock["maximum_submission_attempts"], 1)
            self.assertEqual(lock["automatic_retry"], "BLOCKED")
            self.assertFalse(lock["api_key_persisted"])


if __name__ == "__main__":
    unittest.main()
