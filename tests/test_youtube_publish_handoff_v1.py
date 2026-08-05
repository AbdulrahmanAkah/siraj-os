from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.application.youtube_publish_handoff_v1 import (
    run_youtube_handoff_smoke_test,
)


class YouTubePublishHandoffV1Tests(unittest.TestCase):
    def test_smoke_builds_upload_ready_package_without_api_calls(self) -> None:
        with TemporaryDirectory() as directory:
            result = run_youtube_handoff_smoke_test(Path(directory))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["chapters_count"], 2)
        self.assertEqual(result["subtitle_cue_count"], 2)
        self.assertEqual(result["thumbnail_status"], "ERA_TEMPLATE_NOT_CONFIGURED")
        self.assertTrue(result["manual_upload_only"])
        self.assertEqual(result["youtube_api_requests"], 0)


if __name__ == "__main__":
    unittest.main()
