from __future__ import annotations

import json
from pathlib import Path
import subprocess

from src.application.shorts_derivative_engine_v1 import (
    ShortsDerivativeEngine,
    approve_local_render,
    create_human_review_receipt,
    export_approved_package,
    find_ffmpeg,
)


REPO = Path(__file__).resolve().parents[2]


def _build_video(path: Path) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg is not None, "FFMPEG_REQUIRED_FOR_LOCAL_RENDER_CERTIFICATION"
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x334455:s=1920x1080:r=24:d=4",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=4",
        "-shortest",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ar",
        "48000",
        "-metadata",
        "creation_time=1970-01-01T00:00:00Z",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    import hashlib

    path.with_name(path.name + ".fixture.json").write_text(
        json.dumps({"synthetic": True, "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}),
        encoding="utf-8",
    )


def _metadata() -> dict:
    return {
        "episode_id": "RENDER-FIXTURE-001",
        "constitution_version": "1.0.0",
        "duration_seconds": 4,
        "source_certainty": "VERIFIED",
        "wardrobe_contract_id": "WARDROBE-RENDER-1",
        "period_dossier_id": "PERIOD-RENDER-1",
        "canonical_reference_sha256": "a" * 64,
        "narration_master_sha256": "b" * 64,
        "claims": [],
        "segments": [
            {"id": "S1", "start": 0, "end": 2, "text": "What opened the path?"},
            {"id": "S2", "start": 2, "end": 4, "text": "The light revealed the answer."},
        ],
        "beats": [
            {"id": "B1", "start": 0, "end": 2, "text": "What opened the path?", "narrative_role": "QUESTION", "shot_ids": ["SH1"], "visual_action": "A covered figure opens a wooden door", "visual_strength_indicators": ["action"], "question_signal": 1.0},
            {"id": "B2", "start": 2, "end": 4, "text": "The light revealed the answer.", "narrative_role": "REVELATION", "shot_ids": ["SH2"], "visual_action": "Warm light reveals the path", "visual_strength_indicators": ["reveal"], "revelation_signal": 1.0, "payoff_signal": 0.7},
        ],
        "shots": [
            {"id": "SH1", "start": 0, "end": 2, "visual_action": "A covered figure opens a wooden door", "subject_region": {"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.5}, "semantic_focus_region": {"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.5}},
            {"id": "SH2", "start": 2, "end": 4, "visual_action": "Warm light reveals the path", "subject_region": {"x": 0.6, "y": 0.2, "w": 0.2, "h": 0.5}, "semantic_focus_region": {"x": 0.6, "y": 0.2, "w": 0.2, "h": 0.5}},
        ],
    }


def test_plan_to_local_render_to_qa_to_hash_bound_export(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    _build_video(source)
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(_metadata()), encoding="utf-8")
    engine = ShortsDerivativeEngine(REPO)
    episode = engine.ingest(mode="VIDEO_PLUS_TRANSCRIPT", video_path=source, metadata_path=metadata)
    source_hash = episode.source_episode_sha256
    analysis = engine.analyze(episode)
    passing = [candidate for candidate in analysis.candidates if candidate.status == "PASS"]
    assert passing
    selected = next((candidate for candidate in passing if len(candidate.source_shot_ids) >= 2), passing[0])
    portfolio = engine.portfolio(analysis, candidate_ids=[selected.candidate_id], human_selection_reviewed=True)
    plan = engine.render_plan(analysis, portfolio, selected.candidate_id, human_selection_approved=True)
    assert len(plan.visual_segments) == len(selected.source_shot_ids)
    plan = approve_local_render(plan, explicit_human_click=True)
    render_dir = tmp_path / "render-output"
    render = engine.render(plan, source, render_dir / "short.mp4", explicit_human_click=True, fixture_only=True)
    assert render.provider_calls == 0
    assert render.network_calls == 0
    assert render.paid_calls == 0
    assert render.source_episode_sha256_before == source_hash
    assert render.source_episode_sha256_after == source_hash
    render_repeat = engine.render(
        plan,
        source,
        tmp_path / "render-output-repeat" / "short.mp4",
        explicit_human_click=True,
        fixture_only=True,
    )
    assert render_repeat.render_sha256 == render.render_sha256
    qa = engine.qa(plan, render)
    assert qa.status == "SHORT_QA_PASS"
    assert qa.human_all_frame_visual_review_required is True
    receipt = create_human_review_receipt(
        plan,
        render,
        qa,
        reviewer="fixture-human-reviewer",
        decision="APPROVE",
        all_frame_visual_review=True,
        constitutional_review=True,
        quality_review=True,
    )
    package = export_approved_package(plan, render, qa, receipt, tmp_path / "approved-package")
    assert package["automatic_publication"] is False
    assert package["public_title_owner"] == "HUMAN"
    assert Path(package["render"]["path"]).is_file()
    assert Path(package["render"]["path"]).read_bytes() == Path(render.output_path).read_bytes()
    assert source_hash == episode.source_episode_sha256


def test_renderer_rejects_without_explicit_local_approval(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    _build_video(source)
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(_metadata()), encoding="utf-8")
    engine = ShortsDerivativeEngine(REPO)
    episode = engine.ingest(mode="VIDEO_PLUS_TRANSCRIPT", video_path=source, metadata_path=metadata)
    analysis = engine.analyze(episode)
    candidate = next(item for item in analysis.candidates if item.status == "PASS")
    portfolio = engine.portfolio(analysis, candidate_ids=[candidate.candidate_id], human_selection_reviewed=True)
    plan = engine.render_plan(analysis, portfolio, candidate.candidate_id, human_selection_approved=True)
    try:
        engine.render(plan, source, tmp_path / "output" / "short.mp4", explicit_human_click=False, fixture_only=True)
    except Exception as exc:
        assert "SHORT_HUMAN_REVIEW_REQUIRED" in str(exc)
    else:
        raise AssertionError("render must require explicit local approval")
