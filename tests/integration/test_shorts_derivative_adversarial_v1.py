from __future__ import annotations

import json
from pathlib import Path
import socket

import pytest

from src.application.shorts_derivative_engine_v1 import ShortsDerivativeEngine


REPO = Path(__file__).resolve().parents[2]


def _metadata() -> dict:
    return {
        "episode_id": "ADVERSARIAL-001",
        "constitution_version": "1.0.0",
        "duration_seconds": 8,
        "source_certainty": "VERIFIED",
        "wardrobe_contract_id": "WARDROBE-1",
        "period_dossier_id": "PERIOD-1",
        "canonical_reference_sha256": "a" * 64,
        "narration_master_sha256": "b" * 64,
        "claims": [],
        "segments": [{"id": "S1", "start": 0, "end": 4, "text": "A safe source moment."}, {"id": "S2", "start": 4, "end": 8, "text": "A meaningful continuation."}],
        "beats": [{"id": "B1", "start": 0, "end": 4, "text": "A safe source moment.", "shot_ids": ["SH1"], "visual_action": "A covered figure crosses a room"}, {"id": "B2", "start": 4, "end": 8, "text": "A meaningful continuation.", "shot_ids": ["SH2"], "visual_action": "The path continues"}],
        "shots": [{"id": "SH1", "start": 0, "end": 4, "visual_action": "A covered figure crosses a room", "subject_region": {"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.5}, "semantic_focus_region": {"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.5}}, {"id": "SH2", "start": 4, "end": 8, "visual_action": "The path continues", "subject_region": {"x": 0.6, "y": 0.2, "w": 0.2, "h": 0.5}, "semantic_focus_region": {"x": 0.6, "y": 0.2, "w": 0.2, "h": 0.5}}],
    }


@pytest.fixture()
def fixture_episode(tmp_path: Path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"offline-adversarial-fixture")
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(_metadata()), encoding="utf-8")
    engine = ShortsDerivativeEngine(REPO)
    return engine, engine.ingest(mode="VIDEO_PLUS_TRANSCRIPT", video_path=source, metadata_path=metadata)


def test_network_guard_is_real_for_engine_path(monkeypatch, fixture_episode) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("network attempted")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    engine, episode = fixture_episode
    analysis = engine.analyze(episode)
    assert analysis.candidates


@pytest.mark.parametrize(
    "mutation, expected_token",
    [
        (lambda data: data["beats"][0].update({"text": "As mentioned, he returned."}), "CONTEXT"),
        (lambda data: data["beats"][0].update({"text": "A visible face appears."}), "FACE"),
        (lambda data: data.update({"music": True}), "MUSIC"),
        (lambda data: data.update({"new_sfx_requested": True}), "SFX"),
        (lambda data: data["shots"][0].update({"key_action_spans_full_width": True}), "VERTICAL"),
    ],
)
def test_adversarial_inputs_are_not_silently_promoted(tmp_path: Path, mutation, expected_token: str) -> None:
    data = _metadata()
    mutation(data)
    source = tmp_path / f"{expected_token}.mp4"
    source.write_bytes(b"adversarial")
    metadata = tmp_path / f"{expected_token}.json"
    metadata.write_text(json.dumps(data), encoding="utf-8")
    engine = ShortsDerivativeEngine(REPO)
    analysis = engine.analyze(engine.ingest(mode="VIDEO_PLUS_TRANSCRIPT", video_path=source, metadata_path=metadata))
    assert any(candidate.status != "PASS" for candidate in analysis.candidates)


def test_provider_and_publication_boundaries_are_false(fixture_episode) -> None:
    engine, episode = fixture_episode
    analysis = engine.analyze(episode)
    assert analysis.profile["capability_contract"]["provider_calls"] is False
    assert analysis.profile["automatic_publication"] is False
    assert all(candidate.policy_result.get("provider_call_allowed") is False for candidate in analysis.candidates)


def test_deterministic_candidate_ordering(fixture_episode) -> None:
    engine, episode = fixture_episode
    first = engine.analyze(episode)
    second = engine.analyze(episode)
    assert [item.candidate_id for item in first.candidates] == [item.candidate_id for item in second.candidates]
    assert [item.total_score for item in first.candidates] == [item.total_score for item in second.candidates]
    assert first.analysis_sha256 == second.analysis_sha256


def test_source_change_invalidates_analysis(tmp_path: Path) -> None:
    source = tmp_path / "changed.mp4"
    source.write_bytes(b"before")
    metadata = tmp_path / "changed.json"
    metadata.write_text(json.dumps(_metadata()), encoding="utf-8")
    engine = ShortsDerivativeEngine(REPO)
    episode = engine.ingest(mode="VIDEO_PLUS_TRANSCRIPT", video_path=source, metadata_path=metadata)
    source.write_bytes(b"after")
    with pytest.raises(Exception, match="SHORT_SOURCE_HASH_CHANGED"):
        engine.analyze(episode)


def test_no_fillers_when_all_candidates_are_weak(tmp_path: Path) -> None:
    data = _metadata()
    data["beats"] = [{"id": "B1", "start": 0, "end": 4, "text": "And then.", "shot_ids": ["SH1"], "visual_action": "A covered figure pauses"}]
    data["segments"] = [{"id": "S1", "start": 0, "end": 4, "text": "And then."}]
    data["shots"] = [{"id": "SH1", "start": 0, "end": 4, "visual_action": "A covered figure pauses", "subject_region": {"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.5}, "semantic_focus_region": {"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.5}}]
    source = tmp_path / "weak.mp4"
    source.write_bytes(b"weak")
    metadata = tmp_path / "weak.json"
    metadata.write_text(json.dumps(data), encoding="utf-8")
    engine = ShortsDerivativeEngine(REPO)
    analysis = engine.analyze(engine.ingest(mode="VIDEO_PLUS_TRANSCRIPT", video_path=source, metadata_path=metadata))
    assert all(candidate.status != "PASS" for candidate in analysis.candidates)
