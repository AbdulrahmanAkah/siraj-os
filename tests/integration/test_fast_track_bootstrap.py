from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def test_fast_track_documents_and_episode_manifest_exist() -> None:
    execution_map = (
        REPO
        / "docs"
        / "execution"
        / "FAST_TRACK_EXECUTION_MAP.md"
    ).read_text(encoding="utf-8")

    vertical_slice = (
        REPO
        / "docs"
        / "execution"
        / "FIRST_DOCUMENTARY_VERTICAL_SLICE.md"
    ).read_text(encoding="utf-8")

    episode = json.loads(
        (
            REPO
            / "projects"
            / "episode-001-adam"
            / "episode.json"
        ).read_text(encoding="utf-8")
    )

    assert "creation of Adam through the Day of Judgment" in execution_map
    assert "Gold-20 is a bounded" in execution_map
    assert "Episode 001" in vertical_slice
    assert episode["episode_id"] == "episode-001-adam"
    assert episode["current_gate"] == "GATE_0_PROGRAM_RESET"


def test_source_and_visual_policies_are_explicit() -> None:
    source_pack = json.loads(
        (
            REPO
            / "projects"
            / "episode-001-adam"
            / "source-pack.json"
        ).read_text(encoding="utf-8")
    )

    visual_policy = json.loads(
        (
            REPO
            / "projects"
            / "episode-001-adam"
            / "visual-policy.json"
        ).read_text(encoding="utf-8")
    )

    categories = {
        item["category"]
        for item in source_pack["source_policy"]
    }

    assert "QURAN" in categories
    assert "AUTHENTICATED_HADITH" in categories
    assert "DEPICTION_OF_PROPHETS" in visual_policy["prohibited"]
    assert visual_policy["review_status"] == "PENDING"


def test_pipeline_readiness_report_was_generated() -> None:
    report_path = (
        REPO
        / "artifacts"
        / "fast-track"
        / "pipeline-readiness.json"
    )

    assert report_path.is_file()

    report = json.loads(
        report_path.read_text(encoding="utf-8")
    )

    assert report["first_episode"] == "episode-001-adam"
    assert "media_execution" in report["stage_status"]
    assert report["critical_path"][-1] == "final_mp4"
