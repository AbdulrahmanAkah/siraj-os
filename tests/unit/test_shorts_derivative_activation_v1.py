from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from src.application.shorts_derivative_engine_v1 import (
    ShortsDerivativeEngine,
    ShortsBlockedError,
    approve_local_render,
    create_human_review_receipt,
)
from src.application.shorts_derivative_execution_v1 import (
    TEST_MODE,
    RenderAuthorizationError,
    issue_authorization,
)
from src.application.shorts_derivative_storage_v1 import CanonicalShortsLibrary, ShortsLibraryError


REPO = Path(__file__).resolve().parents[2]


def _video(path: Path) -> None:
    from src.application.shorts_derivative_engine_v1 import find_ffmpeg

    ffmpeg = find_ffmpeg()
    assert ffmpeg
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x334455:s=1920x1080:r=24:d=4", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=4", "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-c:a", "aac", "-ar", "48000", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _metadata() -> dict:
    return {
        "episode_id": "ACTIVATION-001",
        "episode_display_name": "قصة اختبار آمنة",
        "constitution_version": "1.0.0",
        "duration_seconds": 4,
        "source_certainty": "VERIFIED",
        "wardrobe_contract_id": "WARDROBE-ACTIVATION-001",
        "period_dossier_id": "PERIOD-ACTIVATION-001",
        "canonical_reference_sha256": "a" * 64,
        "narration_master_sha256": "b" * 64,
        "claims": [],
        "segments": [{"id": "S1", "start": 0, "end": 2, "text": "What opened the path?"}, {"id": "S2", "start": 2, "end": 4, "text": "The light revealed the answer."}],
        "beats": [{"id": "B1", "start": 0, "end": 2, "text": "What opened the path?", "narrative_role": "QUESTION", "shot_ids": ["SH1"], "visual_action": "A covered figure opens a wooden door", "visual_strength_indicators": ["action"], "question_signal": 1.0}, {"id": "B2", "start": 2, "end": 4, "text": "The light revealed the answer.", "narrative_role": "REVELATION", "shot_ids": ["SH2"], "visual_action": "Warm light reveals the path", "visual_strength_indicators": ["reveal"], "revelation_signal": 1.0, "payoff_signal": 0.7}],
        "shots": [{"id": "SH1", "start": 0, "end": 2, "visual_action": "A covered figure opens a wooden door", "subject_region": {"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.5}, "semantic_focus_region": {"x": 0.2, "y": 0.2, "w": 0.2, "h": 0.5}}, {"id": "SH2", "start": 2, "end": 4, "visual_action": "Warm light reveals the path", "subject_region": {"x": 0.6, "y": 0.2, "w": 0.2, "h": 0.5}, "semantic_focus_region": {"x": 0.6, "y": 0.2, "w": 0.2, "h": 0.5}}],
    }


def _plan(tmp_path: Path):
    source = tmp_path / "source.mp4"
    _video(source)
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(_metadata(), ensure_ascii=False), encoding="utf-8")
    engine = ShortsDerivativeEngine(REPO)
    episode = engine.ingest(mode="VIDEO_PLUS_TRANSCRIPT", video_path=source, metadata_path=metadata)
    analysis = engine.analyze(episode)
    candidate = next(item for item in analysis.candidates if item.status == "PASS")
    portfolio = engine.portfolio(analysis, candidate_ids=[candidate.candidate_id], human_selection_reviewed=True)
    plan = engine.render_plan(analysis, portfolio, candidate.candidate_id, human_selection_approved=True)
    return engine, episode, approve_local_render(plan, explicit_human_click=True)


def test_real_ready_path_uses_same_guard_without_fixture_marker(tmp_path: Path) -> None:
    engine, episode, plan = _plan(tmp_path)
    output_dir = tmp_path / "renders"
    authorization = issue_authorization(episode_id=episode.episode_id, source_episode_sha256=episode.source_episode_sha256, short_plan_sha256=plan.plan_sha256, profile_sha256=plan.profile_sha256, constitution_bundle_sha256=plan.constitution_bundle_sha256, execution_origin="TEST_HARNESS", execution_mode=TEST_MODE, authorized_output_directory=output_dir, authorized_short_ids=(plan.short_id,), explicit_human_click=True)
    result = engine.render(plan, Path(episode.source_video_path), output_dir / "short.mp4", explicit_human_click=True, authorization=authorization)
    assert result.execution_mode == TEST_MODE
    assert result.provider_calls == result.network_calls == result.paid_calls == 0
    assert not Path(episode.source_video_path).with_name(Path(episode.source_video_path).name + ".fixture.json").exists()


def test_authorization_is_single_use_and_terminal_is_forbidden(tmp_path: Path) -> None:
    engine, episode, plan = _plan(tmp_path)
    with pytest.raises(RenderAuthorizationError, match="(REAL_MODE_REQUIRES_SIRAJ_DESKTOP|EXECUTION_ORIGIN_FORBIDDEN)"):
        issue_authorization(episode_id=episode.episode_id, source_episode_sha256=episode.source_episode_sha256, short_plan_sha256=plan.plan_sha256, profile_sha256=plan.profile_sha256, constitution_bundle_sha256=plan.constitution_bundle_sha256, execution_origin="TERMINAL", execution_mode="REAL_EPISODE_LOCAL_RENDER", authorized_output_directory=tmp_path / "renders", authorized_short_ids=(plan.short_id,), explicit_human_click=True)
    auth_path = tmp_path / "auth.json"
    auth = issue_authorization(episode_id=episode.episode_id, source_episode_sha256=episode.source_episode_sha256, short_plan_sha256=plan.plan_sha256, profile_sha256=plan.profile_sha256, constitution_bundle_sha256=plan.constitution_bundle_sha256, execution_origin="TEST_HARNESS", execution_mode=TEST_MODE, authorized_output_directory=tmp_path / "renders", authorized_short_ids=(plan.short_id,), explicit_human_click=True, authorization_path=auth_path)
    engine.render(plan, Path(episode.source_video_path), tmp_path / "renders" / "one.mp4", explicit_human_click=True, authorization=auth)
    with pytest.raises(ShortsBlockedError, match="CONSUMED"):
        engine.render(plan, Path(episode.source_video_path), tmp_path / "renders" / "two.mp4", explicit_human_click=True, authorization=auth)


def test_qa_never_asserts_placeholder_constitutional_pass(tmp_path: Path) -> None:
    engine, episode, plan = _plan(tmp_path)
    auth = issue_authorization(episode_id=episode.episode_id, source_episode_sha256=episode.source_episode_sha256, short_plan_sha256=plan.plan_sha256, profile_sha256=plan.profile_sha256, constitution_bundle_sha256=plan.constitution_bundle_sha256, execution_origin="TEST_HARNESS", execution_mode=TEST_MODE, authorized_output_directory=tmp_path / "renders", authorized_short_ids=(plan.short_id,), explicit_human_click=True)
    render = engine.render(plan, Path(episode.source_video_path), tmp_path / "renders" / "qa.mp4", explicit_human_click=True, authorization=auth)
    qa = engine.qa(plan, render)
    findings = {item["name"]: item for item in qa.findings}
    assert findings["UNSEEN"]["status"] == "HUMAN_REVIEW_REQUIRED"
    assert findings["FACE"]["status"] == "HUMAN_REVIEW_REQUIRED"
    assert all(item.get("status") != "PASS" or item.get("name") not in {"FACE", "UNSEEN"} for item in qa.findings)


def test_canonical_library_reuses_episode_and_rejects_silent_overwrite(tmp_path: Path) -> None:
    desktop = tmp_path / "Desktop"
    settings = tmp_path / "settings.json"
    library = CanonicalShortsLibrary(REPO, desktop_location=desktop, settings_path=settings)
    first = library.resolve()
    second = CanonicalShortsLibrary(REPO, desktop_location=desktop, settings_path=settings).resolve()
    assert first.root == second.root == desktop / "SIRAJ Shorts"
    episode = library.episode_directory("EP001", "عنوان عربي / آمن")
    assert episode.name.startswith("EP001 - ")
    assert library.episode_directory("EP001", "عنوان مختلف") == episode
    source = tmp_path / "render.mp4"
    source.write_bytes(b"approved-render")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    review = {"decision": "APPROVE"}
    result = library.export_approved_short(episode_id="EP001", episode_display_name="عنوان مختلف", source_episode_sha256="a" * 64, render_plan_sha256="b" * 64, approved_render_sha256=digest, profile_sha256="c" * 64, constitution_bundle_sha256="d" * 64, human_review_receipt_sha256="e" * 64, render_path=source, review_receipt=review, short_number=1)
    assert Path(result["render"]["path"]).is_file()
    repeated = library.export_approved_short(episode_id="EP001", episode_display_name="عنوان مختلف", source_episode_sha256="a" * 64, render_plan_sha256="b" * 64, approved_render_sha256=digest, profile_sha256="c" * 64, constitution_bundle_sha256="d" * 64, human_review_receipt_sha256="e" * 64, render_path=source, review_receipt=review, short_number=1)
    assert repeated["export_status"] == "ALREADY_EXPORTED"
