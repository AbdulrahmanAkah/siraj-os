
from pathlib import Path
import json

import pytest

import src.application.shorts_derivative_engine_v1 as s


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )


def test_native_discovery_ignores_valid_array_and_unrelated_malformed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "episode"
    _write(root / "index.json", ["a", "b"])
    _write(root / "generated-overlay.json", "{ not-json")
    _write(
        root / "contracts" / "episode-definition-v1.json",
        {
            "episode_id": "GEN-1",
            "central_question": "سؤال",
        },
    )
    rows = s._native_json_candidates(root)
    assert [
        path.name for path, _value in rows
    ] == ["episode-definition-v1.json"]


def test_native_discovery_keeps_malformed_authority_fail_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "episode"
    _write(
        root / "episode-context-final.json",
        "{ not-json",
    )
    with pytest.raises(s.ShortsBlockedError):
        s._native_json_candidates(root)


def test_untimed_storyboard_never_becomes_runtime_shot_authority(
    tmp_path: Path,
) -> None:
    root = tmp_path / "episode"
    _write(
        root / "contracts" / "episode-definition-v1.json",
        {
            "episode_id": "GEN-2",
            "central_question": "سؤال",
        },
    )
    _write(
        root / "cinematic" / "detailed-storyboard-v2.json",
        {
            "episode_id": "GEN-2",
            "status": "FINAL",
            "shots": [
                {
                    "shot_id": "S1",
                    "duration_seconds": 10,
                    "screen_action": "وصف",
                }
            ],
        },
    )
    merged, _paths = s._load_native_metadata_bundle(root)
    assert "shots" not in merged


def test_explicit_timed_focus_shots_are_runtime_authority(
    tmp_path: Path,
) -> None:
    root = tmp_path / "episode"
    _write(
        root / "contracts" / "episode-definition-v1.json",
        {
            "episode_id": "GEN-3",
            "central_question": "سؤال",
        },
    )
    _write(
        root / "deliverables" / "final-shot-timeline-v1.json",
        {
            "episode_id": "GEN-3",
            "status": "PASS",
            "shots": [
                {
                    "shot_id": "S1",
                    "start_seconds": 0,
                    "end_seconds": 5,
                    "screen_action": "فعل بصري",
                    "focus_region": {
                        "x": 0.25,
                        "y": 0.1,
                        "w": 0.2,
                        "h": 0.6,
                    },
                }
            ],
        },
    )
    merged, _paths = s._load_native_metadata_bundle(root)
    assert merged["shots"][0]["shot_id"] == "S1"
    assert merged["shots"][0]["start"] == 0.0
    assert merged["shots"][0]["end"] == 5.0
    assert merged["shots"][0]["semantic_focus_region"]["x"] == 0.25


def test_transcript_beats_inherit_only_temporal_shot_overlap() -> None:
    segments = (
        s.TranscriptSegment("SEG-1", 1.0, 4.0, "نص"),
    )
    metadata = {
        "shots": [
            {
                "shot_id": "S1",
                "start": 0.0,
                "end": 2.0,
                "visual_action": "الفعل الأول",
                "subject_region": {
                    "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.5
                },
                "semantic_focus_region": {
                    "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.5
                },
                "safe_region": {
                    "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.5
                },
            },
            {
                "shot_id": "S2",
                "start": 2.0,
                "end": 5.0,
                "visual_action": "الفعل الثاني",
                "subject_region": {
                    "x": 0.6, "y": 0.1, "w": 0.2, "h": 0.5
                },
                "semantic_focus_region": {
                    "x": 0.6, "y": 0.1, "w": 0.2, "h": 0.5
                },
                "safe_region": {
                    "x": 0.6, "y": 0.1, "w": 0.2, "h": 0.5
                },
            },
        ]
    }
    beats = s._build_beats(metadata, segments)
    assert beats[0].shot_ids == ("S1", "S2")
    assert "الفعل الأول" in beats[0].visual_action
    assert "الفعل الثاني" in beats[0].visual_action
