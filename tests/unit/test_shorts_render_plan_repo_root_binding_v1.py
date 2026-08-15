from __future__ import annotations

from pathlib import Path

from src.application.shorts_derivative_engine_v1 import _assert_current_source, _sha256_file


def test_relative_metadata_is_resolved_under_explicit_repo_root(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    elsewhere = tmp_path / "elsewhere"
    repo.mkdir()
    elsewhere.mkdir()

    video = repo / "video.mp4"
    video.write_bytes(b"video")

    relative = Path("artifacts") / "shorts-derivatives" / "_legacy-timing-cache" / "episode" / "canonical.json"
    metadata = repo / relative
    metadata.parent.mkdir(parents=True)
    metadata.write_text('{"stable": true}', encoding="utf-8")

    episode = type(
        "Episode",
        (),
        {
            "source_video_path": str(video),
            "source_episode_sha256": _sha256_file(video),
            "source_metadata_hashes": {str(relative): _sha256_file(metadata)},
        },
    )()

    monkeypatch.chdir(elsewhere)
    _assert_current_source(episode, repo)
