from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from src.application.shorts_derivative_engine_v1 import (
    _stabilize_generated_legacy_timing_metadata_hashes_v1,
)


@dataclass(frozen=True)
class _Episode:
    source_metadata_hashes: dict[str, str]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_generated_legacy_timing_cache_hash_is_snapshotted_after_write(tmp_path: Path) -> None:
    cache = (
        tmp_path
        / "artifacts"
        / "shorts-derivatives"
        / "_legacy-timing-cache"
        / "episode"
        / "canonical-timed-transcript.json"
    )
    cache.parent.mkdir(parents=True)
    cache.write_text('{"version": 2}', encoding="utf-8")

    relative = str(cache.relative_to(tmp_path))
    episode = _Episode(source_metadata_hashes={relative: "0" * 64})

    stabilized = _stabilize_generated_legacy_timing_metadata_hashes_v1(
        tmp_path,
        episode,
    )

    assert stabilized.source_metadata_hashes[relative] == _sha(cache)


def test_unrelated_source_metadata_mismatch_is_never_silently_rebound(tmp_path: Path) -> None:
    source = tmp_path / "source-metadata.json"
    source.write_text('{"changed": true}', encoding="utf-8")
    stale = "1" * 64
    episode = _Episode(source_metadata_hashes={"source-metadata.json": stale})

    stabilized = _stabilize_generated_legacy_timing_metadata_hashes_v1(
        tmp_path,
        episode,
    )

    assert stabilized.source_metadata_hashes["source-metadata.json"] == stale
