from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.presentation.desktop.models import EpisodeStage, format_duration
from src.presentation.desktop.repository import (
    build_dashboard_snapshot,
    discover_episode_records,
    find_repo_root,
)


class SirajDesktopDashboardV1Tests(unittest.TestCase):
    def _repo(self, root: Path) -> Path:
        (root / "projects").mkdir(parents=True)
        (root / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
        return root

    def _episode_manifest(
        self,
        repo: Path,
        *,
        master: bool = False,
        final_master: bool = False,
        bulk: str = "BLOCKED_UNTIL_BATCH_GATE",
    ) -> Path:
        episode = repo / "projects" / "episode-001-adam"
        cinematic = episode / "cinematic"
        cinematic.mkdir(parents=True)
        manifest = {
            "shot_count": 2,
            "editorial_duration_seconds": 75,
            "master_visual_approval": master,
            "final_master_visual_approval": final_master,
            "execution_policy": {"full_episode_bulk_generation": bulk},
            "primary_video_model": {
                "provider": "RUNWARE",
                "model": "google:veo@3.1-lite",
            },
            "shots": [
                {"shot_id": "S1", "status": "APPROVED"},
                {"shot_id": "S2", "status": "PLANNED_NOT_GENERATED"},
            ],
        }
        path = cinematic / "veo-production-manifest-v1.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return episode

    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(0), "00:00")
        self.assertEqual(format_duration(1320), "22:00")
        self.assertEqual(format_duration(3661), "01:01:01")

    def test_find_repo_root_from_child(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            child = repo / "projects" / "nested"
            child.mkdir(parents=True)
            self.assertEqual(find_repo_root(child), repo)

    def test_empty_repository_has_no_episodes(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            self.assertEqual(discover_episode_records(repo), ())

    def test_manifest_with_blockers_is_in_production(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            self._episode_manifest(repo)
            episode = discover_episode_records(repo)[0]
            self.assertEqual(episode.stage, EpisodeStage.IN_PRODUCTION)
            self.assertEqual(episode.title_ar, "آدم")
            self.assertEqual(episode.duration_label, "01:15")
            self.assertEqual(episode.shot_count, 2)
            self.assertEqual(episode.approved_shot_count, 1)
            self.assertFalse(episode.conversion_ready)

    def test_approved_manifest_is_ready_for_conversion(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            self._episode_manifest(
                repo,
                master=True,
                final_master=True,
                bulk="ALLOWED_AFTER_HUMAN_GATE",
            )
            episode = discover_episode_records(repo)[0]
            self.assertEqual(episode.stage, EpisodeStage.READY_FOR_CONVERSION)
            self.assertTrue(episode.conversion_ready)

    def test_final_video_without_receipt_requires_review(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            episode_path = self._episode_manifest(repo)
            publish = episode_path / "publish"
            publish.mkdir()
            (publish / "final-video.mp4").write_bytes(b"fixture")
            episode = discover_episode_records(repo)[0]
            self.assertEqual(episode.stage, EpisodeStage.VIDEO_REVIEW)

    def test_approved_final_video_is_publish_ready(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            episode_path = self._episode_manifest(repo)
            publish = episode_path / "publish"
            publish.mkdir()
            (publish / "final-video.mp4").write_bytes(b"fixture")
            (publish / "final-video-receipt.json").write_text(
                json.dumps({"status": "PUBLISH_READY"}),
                encoding="utf-8",
            )
            episode = discover_episode_records(repo)[0]
            self.assertEqual(episode.stage, EpisodeStage.PUBLISH_READY)
            self.assertTrue(episode.publish_ready)

    def test_snapshot_metrics_are_derived(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            self._episode_manifest(repo)
            snapshot = build_dashboard_snapshot(repo)
            self.assertEqual(snapshot.total_shot_count, 2)
            self.assertEqual(snapshot.approved_shot_count, 1)
            self.assertEqual(snapshot.readiness_percent, 0)
            self.assertEqual(snapshot.active_episode_id, "episode-001-adam")


if __name__ == "__main__":
    unittest.main()
