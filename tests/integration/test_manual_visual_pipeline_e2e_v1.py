from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import wave
from pathlib import Path

import pytest
from PIL import Image

from src.application.canonical_next_episode_manual_visual_pipeline_v1 import (
    CanonicalManualVisualPipelineError,
    advance_previsual,
    archive_episode,
    assemble_manual_visual_episode,
    bootstrap_episode,
    build_master,
    certify_shorts_compatibility,
    export_manual_visual_handoff,
    import_manual_visuals,
    lock_imported_visuals,
    record_human_final_review,
    run_separated_qa,
    workflow_status,
)


def write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def shot(shot_id: str, start: float, end: float, kind: str) -> dict:
    return {
        "shot_id": shot_id, "audio_start": start, "audio_end": end,
        "exact_audio_text": "نص عربي موثوق", "script_section": "section-1",
        "visual_purpose": "غرض تحريري", "visual_priority": "HIGH",
        "recommended_asset_type": kind, "what_to_create": "أصل مرئي يدوي",
        "what_must_be_visible": "بيئة تاريخية آمنة",
        "what_must_not_be_visible": "أي وجه بشري ظاهر",
        "character_reference": "none", "environment_reference": "env-1",
        "continuity_from": "none" if shot_id.endswith("001") else "SH-001",
        "continuity_to": "SH-002" if shot_id.endswith("001") else "none",
        "composition": "تكوين متوازن", "camera_intent": "ثابت",
        "subject_motion_intent": "حركة هادئة", "style_direction": "واقعية تاريخية",
        "constitution_rules": ["NO_VISIBLE_FACES", "NO_MUSIC", "NO_GRAPHICS"],
        "risk_class": "LOW", "risk_reasons": [],
        "negative_constraints": ["NO_TEXT_OVERLAY"],
        "human_acceptance_checklist": ["لا وجوه", "حقبة صحيحة"],
    }


def artifact_set(tmp_path: Path, audio_path: Path) -> dict[str, Path]:
    shots = [shot("SH-001", 0.0, 1.0, "IMAGE"), shot("SH-002", 1.0, 2.0, "VIDEO")]
    root = tmp_path / "previsual"
    artifacts = {
        "research": write_json(root / "research.json", {"status": "COMPLETE", "sources": ["S1"]}),
        "source_registry": write_json(root / "source_registry.json", {"sources": [{"source_id": "S1"}]}),
        "claim_matrix": write_json(root / "claim_matrix.json", {"claims": [{"claim_id": "C1", "source_ids": ["S1"]}]}),
        "sources_lock": write_json(root / "sources_lock.json", {"status": "LOCKED", "uncertainty": []}),
        "title_lock": write_json(root / "title_lock.json", {"decision": "APPROVED", "human_actor": "fixture-operator", "autonomous_approval": False, "final_title": "حلقة تركيبية"}),
        "story_architecture": write_json(root / "story.json", {"beats": ["B1"]}),
        "script": write_json(root / "script.json", {"version": "1", "episode_summary": "حلقة تركيبية لاختبار المسار", "text": "نص عربي موثوق نص عربي موثوق"}),
        "script_qa": write_json(root / "script_qa.json", {"gates": {"factual_source": "PASS", "constitution": "PASS", "editorial": "PASS", "narrative": "PASS"}}),
        "narration": write_json(root / "narration.json", {"status": "FINAL_ACCEPTED", "text": "نص عربي موثوق نص عربي موثوق"}),
        "audio": audio_path,
        "timing": write_json(root / "timing.json", {"version": "1", "duration": 2.0, "words": [{"text": "نص", "start": 0.0, "end": 0.25}, {"text": "موثوق", "start": 1.5, "end": 2.0}]}),
        "storyboard": write_json(root / "storyboard.json", {"shots": shots}),
        "visual_contracts": write_json(root / "visual_contracts.json", {"shots": shots}),
        "coverage_validation": write_json(root / "coverage.json", {"status": "PASS", "coverage": 1.0, "diversity": "PASS", "reuse": "PASS"}),
        "pre_visual_approval": write_json(root / "pre_visual_approval.json", {"decision": "APPROVED", "human_actor": "fixture-operator", "autonomous_approval": False}),
    }
    audio_sha = __import__("hashlib").sha256(audio_path.read_bytes()).hexdigest()
    artifacts["audio_timing_receipt"] = write_json(root / "audio_timing_receipt.json", {"timing_mode": "MANUAL_VERIFIED", "final_audio_sha256": audio_sha, "timing_bound_audio_sha256": audio_sha})
    return artifacts


def make_silent_wav(path: Path, seconds: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48_000)
        handle.writeframes(b"\x00\x00" * 48_000 * seconds)


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="FFmpeg required")
def test_clean_offline_manual_visual_episode_to_archive(tmp_path: Path) -> None:
    episode_id = "episode-041-synthetic-e2e"
    audio = tmp_path / "source" / "final-narration.wav"
    make_silent_wav(audio)
    bootstrap_episode(tmp_path, episode_id)
    advance_previsual(tmp_path, episode_id, artifact_set(tmp_path, audio))
    handoff = export_manual_visual_handoff(tmp_path, episode_id)
    assert workflow_status(tmp_path, episode_id)["stage"] == "MANUAL_VISUAL_HANDOFF_READY"
    assert export_manual_visual_handoff(tmp_path, episode_id)["reused"] is True

    incoming = tmp_path / "incoming"
    incoming.mkdir()
    pack = json.loads(Path(handoff["pack_path"]).read_text(encoding="utf-8"))
    Image.new("RGB", (1280, 720), (30, 40, 50)).save(incoming / pack["shots"][0]["expected_filename"])
    subprocess.run(
        [shutil.which("ffmpeg"), "-y", "-f", "lavfi", "-i", "color=c=blue:s=1280x720:r=30:d=1.0", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(incoming / pack["shots"][1]["expected_filename"])],
        check=True, capture_output=True,
    )
    template_path = Path(handoff["ingest_template_path"])
    template = json.loads(template_path.read_text(encoding="utf-8"))
    for item in template["assets"]:
        item["human_selected"] = True
        item["constitution_acceptance"] = True
    write_json(template_path, template)
    ingest = import_manual_visuals(tmp_path, episode_id, ingest_dir=incoming)
    assert ingest["status"] == "PASS_COMPLETE_VALIDATED"
    assert import_manual_visuals(tmp_path, episode_id, ingest_dir=incoming)["reused"] is True
    assert workflow_status(tmp_path, episode_id)["stage"] == "ASSET_VALIDATION"
    assert lock_imported_visuals(tmp_path, episode_id)["status"] == "SHA_BOUND_VISUAL_LOCK"
    assembled = assemble_manual_visual_episode(tmp_path, episode_id)
    assert assembled["status"] == "AUDIO_SYNC"
    assert Path(assembled["candidate_path"]).is_file()
    assert assemble_manual_visual_episode(tmp_path, episode_id)["reused"] is True

    # A receipt cannot authorize QA when its byte binding or semantic bindings
    # no longer match the canonical upstream authorities.
    episode_root = tmp_path / "projects" / episode_id
    state_path = episode_root / "orchestration/canonical-episode-state-v1.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    receipt_path = Path(state["artifacts"]["assembly_candidate"]["path"])
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes.decode("utf-8"))
    receipt["final_audio_sha256"] = "0" * 64
    write_json(receipt_path, receipt)
    state["artifacts"]["assembly_candidate"]["sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    write_json(state_path, state)
    with pytest.raises(CanonicalManualVisualPipelineError, match="ASSEMBLY_RECEIPT_BINDING_INVALID"):
        run_separated_qa(tmp_path, episode_id)
    receipt_path.write_bytes(receipt_bytes)
    state["artifacts"]["assembly_candidate"]["sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    write_json(state_path, state)

    audio_bytes = audio.read_bytes()
    audio.write_bytes(audio_bytes + b"stale")
    with pytest.raises(CanonicalManualVisualPipelineError, match="CANONICAL_ARTIFACT_STALE:audio"):
        run_separated_qa(tmp_path, episode_id)
    audio.write_bytes(audio_bytes)

    assert run_separated_qa(tmp_path, episode_id)["status"] == "EDITORIAL_QA"
    assert record_human_final_review(tmp_path, episode_id, human_actor="synthetic-test-human", decision="APPROVED")["status"] == "HUMAN_FINAL_REVIEW"
    master = build_master(tmp_path, episode_id)
    assert master["status"] == "MASTER"
    assert Path(master["master_path"]).is_file()
    assert certify_shorts_compatibility(tmp_path, episode_id)["status"] == "SHORTS_DERIVATIVE"
    archived = archive_episode(tmp_path, episode_id)
    assert archived["status"] == "ARCHIVE"
    assert workflow_status(tmp_path, episode_id)["stage"] == "ARCHIVE"
    assert workflow_status(tmp_path, episode_id)["paid_visual_controls_visible"] is False
    original_master_sha = master["master_sha256"]

    # A user replacement after master/archive is accepted as new bytes and
    # invalidates only the manual-visual downstream chain back to validation.
    subprocess.run(
        [shutil.which("ffmpeg"), "-y", "-f", "lavfi", "-i", "color=c=red:s=1280x720:r=30:d=1.0", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(incoming / pack["shots"][1]["expected_filename"])],
        check=True, capture_output=True,
    )
    replacement = import_manual_visuals(tmp_path, episode_id, ingest_dir=incoming)
    assert replacement["replacements"][0]["shot_id"] == "SH-002"
    assert workflow_status(tmp_path, episode_id)["stage"] == "ASSET_VALIDATION"
    state = json.loads((tmp_path / "projects" / episode_id / "orchestration/canonical-episode-state-v1.json").read_text(encoding="utf-8"))
    assert "final_master" not in state["artifacts"]
    assert "manual_visual_pack" in state["artifacts"]

    # Replacements are rebuildable without overwriting historical master bytes.
    assert lock_imported_visuals(tmp_path, episode_id)["status"] == "SHA_BOUND_VISUAL_LOCK"
    rebuilt_candidate = assemble_manual_visual_episode(tmp_path, episode_id)
    assert rebuilt_candidate["candidate_sha256"] != assembled["candidate_sha256"]
    assert run_separated_qa(tmp_path, episode_id)["status"] == "EDITORIAL_QA"
    assert record_human_final_review(tmp_path, episode_id, human_actor="synthetic-test-human", decision="APPROVED")["status"] == "HUMAN_FINAL_REVIEW"
    rebuilt_master = build_master(tmp_path, episode_id)
    assert rebuilt_master["master_sha256"] != original_master_sha
    historical_master = tmp_path / "projects" / episode_id / "deliverables/history" / f"{original_master_sha}-episode-master-v1.mp4"
    assert historical_master.is_file()
    assert hashlib.sha256(historical_master.read_bytes()).hexdigest() == original_master_sha
