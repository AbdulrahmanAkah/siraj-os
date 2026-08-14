from __future__ import annotations

import json
from pathlib import Path
import subprocess
import uuid

import pytest

from src.application.shorts_derivative_desktop_integration_v1 import ShortsDerivativeDesktopWorkflow
from src.application.shorts_derivative_engine_v1 import find_ffmpeg


REPO = Path(__file__).resolve().parents[2]


def _make_source(path: Path) -> None:
    ffmpeg = find_ffmpeg()
    assert ffmpeg
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=0x334455:s=1920x1080:r=24:d=4", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=4", "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-c:a", "aac", "-ar", "48000", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _write_metadata(path: Path, episode_id: str) -> None:
    path.write_text(
        json.dumps(
            {
                "episode_id": episode_id,
                "episode_display_name": "Desktop acceptance episode",
                "constitution_version": "1.0.0",
                "duration_seconds": 4,
                "source_certainty": "VERIFIED",
                "wardrobe_contract_id": "WARDROBE-DESKTOP-001",
                "period_dossier_id": "PERIOD-DESKTOP-001",
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
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_desktop_workflow_real_local_render_resume_and_canonical_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    del app
    episode_id = "DESKTOP-ACCEPTANCE-" + uuid.uuid4().hex[:12]
    source = tmp_path / "source.mp4"
    metadata = tmp_path / "metadata.json"
    _make_source(source)
    _write_metadata(metadata, episode_id)
    desktop = tmp_path / "Desktop"
    settings = tmp_path / "library-settings.json"

    workflow = ShortsDerivativeDesktopWorkflow(REPO, desktop_location=desktop, settings_path=settings)
    episode = workflow.select_episode(mode="VIDEO_PLUS_TRANSCRIPT", video_path=source, metadata_path=metadata)
    assert episode.source_admission["status"] == "PASS"
    analysis = workflow.analyze_episode()
    candidate = next(item for item in analysis.candidates if item.status == "PASS")
    portfolio = workflow.select_candidates([candidate.candidate_id], reviewed=True)
    assert portfolio.portfolio_status == "PORTFOLIO_READY"
    plans = workflow.generate_render_plans()
    assert len(plans) == 1
    plan = workflow.approve_local_render(candidate.candidate_id)
    render = workflow.render_local(candidate.candidate_id)
    assert plan.local_render_approved is True
    assert render.execution_origin == "SIRAJ_DESKTOP"
    assert render.execution_mode == "REAL_EPISODE_LOCAL_RENDER"
    qa = workflow.inspect_qa(candidate.candidate_id)
    assert qa.status == "SHORT_QA_PASS"
    session = workflow.begin_human_review(candidate.candidate_id)
    session.start_playback()
    session.observe_position(session.duration_seconds)
    session.record_detail_inspection()
    receipt = workflow.complete_human_review(candidate.candidate_id, reviewer="Desktop Acceptance", decision="APPROVE", constitutional_review=True, quality_review=True)
    assert receipt.review_evidence["status"] == "PASS"
    manifest = workflow.export_short(candidate.candidate_id)
    assert manifest["export_status"] == "EXPORTED"
    assert manifest["exported_file_sha256"] == manifest["approved_render_sha256"]
    assert Path(manifest["render"]["path"]).is_file()

    resumed = ShortsDerivativeDesktopWorkflow(REPO, desktop_location=desktop, settings_path=settings)
    resumed.select_episode(mode="VIDEO_PLUS_TRANSCRIPT", video_path=source, metadata_path=metadata)
    assert resumed.resume_status == "RESUMED_HASH_MATCH"
    assert resumed.status().exported_count == 1
    assert resumed.status().provider_calls == resumed.status().network_calls == resumed.status().paid_calls == 0
