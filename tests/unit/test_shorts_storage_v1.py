from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.application.shorts_derivative_storage_v1 import CanonicalShortsLibrary, ShortsLibraryError


REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("case", range(20))
def test_canonical_storage_matrix_case(case: int, tmp_path: Path) -> None:
    desktop = tmp_path / f"Desktop-{case:02d}"
    settings = tmp_path / f"settings-{case:02d}.json"
    library = CanonicalShortsLibrary(REPO, desktop_location=desktop, settings_path=settings)
    binding = library.resolve()
    assert binding.root == desktop / "SIRAJ Shorts"
    episode_id = f"EP-{case:02d}"
    episode = library.episode_directory(episode_id, f"Title {case}: <safe> / Arabic", source_episode_sha256="a" * 64)
    assert episode.parent == binding.root
    assert {item.name for item in episode.iterdir()} >= {"Shorts", "Captions", "Manifests", "Reviews", "episode-shorts-manifest.json"}
    assert len(library.rebuild_index()) == 1


def test_canonical_storage_reports_missing_moved_root(tmp_path: Path) -> None:
    desktop = tmp_path / "Desktop"
    settings = tmp_path / "settings.json"
    library = CanonicalShortsLibrary(REPO, desktop_location=desktop, settings_path=settings)
    root = library.resolve().root
    root.rename(tmp_path / "Moved SIRAJ Shorts")
    with pytest.raises(ShortsLibraryError, match="SHORTS_LIBRARY_NOT_FOUND"):
        CanonicalShortsLibrary(REPO, desktop_location=desktop, settings_path=settings).resolve()


def test_canonical_storage_versions_changed_hash_without_overwrite(tmp_path: Path) -> None:
    desktop = tmp_path / "Desktop"
    settings = tmp_path / "settings.json"
    library = CanonicalShortsLibrary(REPO, desktop_location=desktop, settings_path=settings)
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    common = {
        "episode_id": "EP-VERSION",
        "episode_display_name": "Versioned",
        "source_episode_sha256": "a" * 64,
        "render_plan_sha256": "b" * 64,
        "profile_sha256": "c" * 64,
        "constitution_bundle_sha256": "d" * 64,
        "human_review_receipt_sha256": "e" * 64,
        "review_receipt": {"decision": "APPROVE"},
        "short_number": 1,
    }
    first_result = library.export_approved_short(render_path=first, approved_render_sha256=hashlib.sha256(b"first").hexdigest(), **common)
    second_result = library.export_approved_short(render_path=second, approved_render_sha256=hashlib.sha256(b"second").hexdigest(), **common)
    assert first_result["render"]["path"].endswith("EP-VERSION-SHORT-01.mp4")
    assert second_result["render"]["path"].endswith("EP-VERSION-SHORT-01-v2.mp4")
    assert Path(first_result["render"]["path"]).read_bytes() == b"first"


def test_canonical_storage_rejects_hash_mismatch_before_export(tmp_path: Path) -> None:
    library = CanonicalShortsLibrary(REPO, desktop_location=tmp_path / "Desktop", settings_path=tmp_path / "settings.json")
    source = tmp_path / "render.mp4"
    source.write_bytes(b"actual")
    with pytest.raises(ShortsLibraryError, match="SHORT_EXPORT_HASH_MISMATCH"):
        library.export_approved_short(episode_id="EP-HASH", episode_display_name="Hash", source_episode_sha256="a" * 64, render_plan_sha256="b" * 64, approved_render_sha256="f" * 64, profile_sha256="c" * 64, constitution_bundle_sha256="d" * 64, human_review_receipt_sha256="e" * 64, render_path=source, review_receipt={"decision": "APPROVE"})
