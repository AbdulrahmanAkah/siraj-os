from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.presentation.desktop.models import EpisodeStage
from src.presentation.desktop.repository import (
    build_dashboard_snapshot,
    discover_episode_records,
)


class SirajDesktopDashboardV11Tests(unittest.TestCase):
    def _repo(self, root: Path) -> Path:
        (root / "projects").mkdir(parents=True)
        (root / "pyproject.toml").write_text(
            "[project]\nname='fixture'\n",
            encoding="utf-8",
        )
        return root

    def _episode(
        self,
        repo: Path,
        episode_id: str,
        *,
        statuses: list[str],
        ready: bool = False,
    ) -> Path:
        episode = repo / "projects" / episode_id
        cinematic = episode / "cinematic"
        cinematic.mkdir(parents=True)
        manifest = {
            "shot_count": len(statuses),
            "editorial_duration_seconds": 80,
            "master_visual_approval": ready,
            "final_master_visual_approval": ready,
            "execution_policy": {
                "full_episode_bulk_generation": (
                    "ALLOWED_AFTER_HUMAN_GATE"
                    if ready
                    else "BLOCKED_UNTIL_BATCH_GATE"
                )
            },
            "primary_video_model": {
                "provider": "RUNWARE",
                "model": "google:veo@3.1-lite",
            },
            "shots": [
                {"shot_id": f"S{index + 1}", "status": status}
                for index, status in enumerate(statuses)
            ],
        }
        (cinematic / "veo-production-manifest-v1.json").write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        return episode

    def test_planned_not_generated_is_not_counted_as_video(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            self._episode(
                repo,
                "episode-001-adam",
                statuses=["PLANNED_NOT_GENERATED", "PLANNED_NOT_GENERATED"],
            )
            episode = discover_episode_records(repo)[0]
            self.assertEqual(episode.shot_count, 2)
            self.assertEqual(episode.generated_shot_count, 0)
            snapshot = build_dashboard_snapshot(repo)
            self.assertEqual(snapshot.generated_clip_count, 0)

    def test_generated_status_and_real_mp4_are_counted(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            episode_path = self._episode(
                repo,
                "episode-001-adam",
                statuses=["GENERATED_PENDING_REVIEW", "PLANNED_NOT_GENERATED"],
            )
            generated = episode_path / "generated" / "shot-1"
            generated.mkdir(parents=True)
            (generated / "beat-01.mp4").write_bytes(b"fixture")
            episode = discover_episode_records(repo)[0]
            self.assertEqual(episode.generated_shot_count, 1)

    def test_current_shot_and_beat_are_read_from_latest_package(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            episode_path = self._episode(
                repo,
                "episode-001-adam",
                statuses=["PLANNED_NOT_GENERATED"],
            )
            package = (
                episode_path
                / "cinematic"
                / "shot-packages"
                / "adam-dc2-s02-sh03"
            )
            package.mkdir(parents=True)
            (package / "veo-shot-pack-001-v1.json").write_text(
                json.dumps(
                    {
                        "shot_id": "ADAM-DC2-S02-SH03",
                        "execution_authorization": {
                            "currently_authored_generation_beat": (
                                "ADAM-DC2-S02-SH03-B01"
                            )
                        },
                    }
                ),
                encoding="utf-8",
            )
            episode = discover_episode_records(repo)[0]
            self.assertEqual(episode.current_shot_id, "ADAM-DC2-S02-SH03")
            self.assertEqual(episode.current_beat_id, "ADAM-DC2-S02-SH03-B01")

    def test_ready_and_work_queues_are_disjoint(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = self._repo(Path(temporary))
            self._episode(
                repo,
                "episode-001-adam",
                statuses=["PLANNED_NOT_GENERATED"],
                ready=False,
            )
            self._episode(
                repo,
                "episode-002-noah",
                statuses=["APPROVED"],
                ready=True,
            )
            snapshot = build_dashboard_snapshot(repo)
            self.assertEqual(len(snapshot.ready_queue), 1)
            self.assertEqual(len(snapshot.work_queue), 1)
            ready_ids = {item.episode_id for item in snapshot.ready_queue}
            work_ids = {item.episode_id for item in snapshot.work_queue}
            self.assertFalse(ready_ids & work_ids)
            self.assertEqual(snapshot.ready_queue[0].stage, EpisodeStage.READY_FOR_CONVERSION)

    def test_v11_ui_source_binds_responsive_layout_and_svg_icons(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        main_window = (
            repo_root / "src" / "presentation" / "desktop" / "main_window.py"
        ).read_text(encoding="utf-8")
        widgets = (
            repo_root / "src" / "presentation" / "desktop" / "widgets.py"
        ).read_text(encoding="utf-8")
        icons = (
            repo_root / "src" / "presentation" / "desktop" / "icons.py"
        ).read_text(encoding="utf-8")
        self.assertIn("QSplitter", main_window)
        self.assertIn("ScrollBarAlwaysOff", main_window)
        self.assertIn("self.ready_table", main_window)
        self.assertIn("self.work_table", main_window)
        self.assertIn("heightForWidth", widgets)
        self.assertIn("QSvgRenderer", icons)


if __name__ == "__main__":
    unittest.main()
