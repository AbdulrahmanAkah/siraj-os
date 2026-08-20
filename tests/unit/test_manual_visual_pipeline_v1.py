from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from src.application.canonical_manual_visual_profile_v1 import (
    CanonicalManualVisualProfileError,
    enforce_manual_visual_provider_isolation,
)
from src.application.canonical_next_episode_manual_visual_pipeline_v1 import (
    advance_previsual,
    bootstrap_episode,
    export_manual_visual_handoff,
    workflow_status,
)
from src.application.manual_visual_asset_ingest_v1 import (
    ManualVisualIngestError,
    ingest_manual_visuals,
    lock_manual_visuals,
    sha256_file,
)
from src.application.manual_visual_production_pack_v1 import (
    ManualVisualPackError,
    validate_pack_document,
    validate_shots,
)
from src.application.paid_operation_gateway import (
    PaidOperationGatewayError,
    PaidOperationRequest,
    execute_bytes,
)


def write_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def shots() -> list[dict]:
    base = {
        "script_section": "section-1",
        "visual_priority": "HIGH",
        "what_must_be_visible": "المشهد التاريخي المطلوب",
        "what_must_not_be_visible": "أي وجه بشري ظاهر",
        "character_reference": "none",
        "environment_reference": "env-1",
        "continuity_from": "none",
        "continuity_to": "next",
        "composition": "تكوين متوازن",
        "camera_intent": "ثابت وهادئ",
        "subject_motion_intent": "حركة طبيعية محدودة",
        "style_direction": "واقعية تاريخية",
        "constitution_rules": ["NO_VISIBLE_FACES", "NO_MUSIC"],
        "risk_class": "LOW",
        "risk_reasons": [],
        "negative_constraints": ["NO_TEXT_OVERLAY"],
        "human_acceptance_checklist": ["حقبة صحيحة", "لا وجوه ظاهرة"],
    }
    return [
        {
            **base,
            "shot_id": "SH-001", "audio_start": 0.0, "audio_end": 1.0,
            "exact_audio_text": "بدأت القصة بهدوء", "visual_purpose": "افتتاح",
            "recommended_asset_type": "IMAGE", "what_to_create": "صورة افتتاحية",
        },
        {
            **base,
            "shot_id": "SH-002", "audio_start": 1.0, "audio_end": 2.0,
            "exact_audio_text": "ثم تحرك المشهد", "visual_purpose": "تطور",
            "recommended_asset_type": "VIDEO", "what_to_create": "مقطع حركة",
            "continuity_from": "SH-001", "continuity_to": "none",
        },
    ]


def previsual_artifacts(tmp_path: Path) -> dict[str, Path]:
    artifacts: dict[str, Path] = {}
    plain = {
        "research": {"status": "COMPLETE", "sources": ["source-1"]},
        "source_registry": {"sources": [{"source_id": "source-1"}]},
        "claim_matrix": {"claims": [{"claim_id": "claim-1", "source_ids": ["source-1"]}]},
        "sources_lock": {"status": "LOCKED", "uncertainty": []},
        "story_architecture": {"beats": ["beat-1"]},
        "script": {"schema_version": "script-v1", "version": "1", "episode_summary": "ملخص اختباري", "text": "بدأت القصة بهدوء ثم تحرك المشهد"},
        "narration": {"status": "FINAL_ACCEPTED", "text": "بدأت القصة بهدوء ثم تحرك المشهد"},
        "audio": {"placeholder": "bound-as-bytes"},
        "timing": {"version": "1", "words": [{"text": "بدأت", "start": 0.0, "end": 0.4}]},
        "storyboard": {"shots": shots()},
        "visual_contracts": {"shots": shots()},
    }
    for slot, value in plain.items():
        artifacts[slot] = write_json(tmp_path / "artifacts" / f"{slot}.json", value)
    artifacts["title_lock"] = write_json(tmp_path / "artifacts/title_lock.json", {"decision": "APPROVED", "human_actor": "tester", "autonomous_approval": False, "final_title": "عنوان اختباري"})
    artifacts["script_qa"] = write_json(tmp_path / "artifacts/script_qa.json", {"gates": {"factual_source": "PASS", "constitution": "PASS", "editorial": "PASS", "narrative": "PASS"}})
    artifacts["audio_timing_receipt"] = write_json(tmp_path / "artifacts/audio_timing_receipt.json", {"timing_mode": "MANUAL_VERIFIED", "final_audio_sha256": "a" * 64, "timing_bound_audio_sha256": "a" * 64})
    artifacts["coverage_validation"] = write_json(tmp_path / "artifacts/coverage.json", {"status": "PASS", "coverage": 1.0, "diversity": "PASS", "reuse": "PASS"})
    artifacts["pre_visual_approval"] = write_json(tmp_path / "artifacts/pre_visual_approval.json", {"decision": "APPROVED", "human_actor": "tester", "autonomous_approval": False})
    return artifacts


def prepared_episode(tmp_path: Path, episode_id: str = "episode-017-test") -> tuple[Path, dict]:
    bootstrap_episode(tmp_path, episode_id)
    advance_previsual(tmp_path, episode_id, previsual_artifacts(tmp_path))
    result = export_manual_visual_handoff(tmp_path, episode_id)
    return tmp_path / "projects" / episode_id, result


def test_bootstrap_and_handoff_are_generic_and_durable(tmp_path: Path) -> None:
    episode_root, result = prepared_episode(tmp_path, "episode-017-topic-neutral")
    assert result["status"] == "MANUAL_VISUAL_HANDOFF_READY"
    assert workflow_status(tmp_path, "episode-017-topic-neutral")["stage"] == "MANUAL_VISUAL_HANDOFF_READY"
    assert (episode_root / "contracts/episode-profile-v1.json").is_file()
    output = episode_root / "manual-visuals/handoff-v1"
    assert {path.name for path in output.iterdir()} == {
        "manual-visual-production-pack-v1.json", "manual-visual-production-pack-v1.html",
        "manual-visual-production-pack-v1.md", "manual-visual-ingest-template-v1.json",
        "manual-visual-asset-naming-v1.json",
    }
    pack = json.loads((output / "manual-visual-production-pack-v1.json").read_text(encoding="utf-8"))
    assert pack["total_images"] == 1
    assert pack["total_video_clips"] == 1
    assert pack["video_duration_coverage"] == 1.0
    assert all("EP003" not in shot["expected_filename"] for shot in pack["shots"])


def test_manual_profile_blocks_visual_provider_before_transport(tmp_path: Path) -> None:
    bootstrap_episode(tmp_path, "episode-031-safe")
    request = SimpleNamespace(
        repo_root=tmp_path, episode_id="episode-031-safe", provider="RUNWARE",
        payload={"taskType": "imageInference"},
    )
    with pytest.raises(CanonicalManualVisualProfileError, match="MANUAL_VISUAL_PIPELINE"):
        enforce_manual_visual_provider_isolation(request)


def test_manual_profile_blocks_unknown_provider_operation_fail_closed(tmp_path: Path) -> None:
    bootstrap_episode(tmp_path, "episode-031-unknown-provider")
    request = SimpleNamespace(
        repo_root=tmp_path, episode_id="episode-031-unknown-provider",
        stage="PROVIDER_EXECUTION", operation_type="UNCLASSIFIED_PROVIDER_TASK",
        provider="FUTURE_PROVIDER", payload={"task": {"type": "unclassified"}},
    )
    with pytest.raises(CanonicalManualVisualProfileError, match="MANUAL_VISUAL_PIPELINE"):
        enforce_manual_visual_provider_isolation(request)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_pack_rejects_non_finite_timing(bad: float) -> None:
    altered = shots()
    altered[0]["audio_start"] = bad
    with pytest.raises(ManualVisualPackError, match="TIMING_INVALID"):
        validate_shots("episode-050-nonfinite", altered)


def test_incomplete_pack_cannot_become_authority() -> None:
    with pytest.raises(ManualVisualPackError, match="SHOTS_REQUIRED"):
        validate_pack_document({"schema_version": "siraj-manual-visual-production-pack-v1", "episode_id": "episode-051", "shots": []})


def test_direct_paid_gateway_visual_attempt_is_blocked_before_transport_or_attempt_write(tmp_path: Path) -> None:
    episode_id = "episode-032-safe"
    bootstrap_episode(tmp_path, episode_id)
    called = False

    def transport(boundary):
        nonlocal called
        called = True
        return b"forbidden"

    request = PaidOperationRequest(
        repo_root=tmp_path, episode_id=episode_id, stage="PROVIDER_EXECUTION",
        operation_type="VISUAL_GENERATION", provider="RUNWARE", model="test",
        provider_contract_version="test-v1", payload={"taskType": "imageInference"},
        input_artifact_hashes={}, master_authorization_reference={},
    )
    with pytest.raises(PaidOperationGatewayError, match="MANUAL_VISUAL_PIPELINE"):
        execute_bytes(request, transport)
    assert called is False
    assert not (tmp_path / "projects" / episode_id / "orchestration" / "paid-operation-attempts-v1").exists()


def test_missing_assets_fail_closed(tmp_path: Path) -> None:
    episode_root, result = prepared_episode(tmp_path)
    ingest_dir = tmp_path / "incoming"
    ingest_dir.mkdir()
    outcome = ingest_manual_visuals(
        episode_root=episode_root,
        pack_path=Path(result["pack_path"]),
        ingest_template_path=Path(result["ingest_template_path"]),
        ingest_dir=ingest_dir,
        expected_pack_sha256=sha256_file(Path(result["pack_path"])),
    )
    assert outcome["status"] == "MISSING_MANUAL_VISUAL_ASSETS"
    assert outcome["missing"] == ["SH-001", "SH-002"]

    pack_path = Path(result["pack_path"])
    tampered = json.loads(pack_path.read_text(encoding="utf-8"))
    tampered["final_title"] = "tampered"
    write_json(pack_path, tampered)
    with pytest.raises(ManualVisualIngestError, match="CANONICAL_SHA_MISMATCH"):
        ingest_manual_visuals(
            episode_root=episode_root, pack_path=pack_path,
            ingest_template_path=Path(result["ingest_template_path"]), ingest_dir=ingest_dir,
            expected_pack_sha256=result["pack_sha256"],
        )


def test_ingest_lock_and_replacement_are_sha_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    episode_root, result = prepared_episode(tmp_path)
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    pack = json.loads(Path(result["pack_path"]).read_text(encoding="utf-8"))
    Image.new("RGB", (1280, 720), (20, 30, 40)).save(incoming / pack["shots"][0]["expected_filename"])
    (incoming / pack["shots"][1]["expected_filename"]).write_bytes(b"synthetic-video-one")
    template_path = Path(result["ingest_template_path"])
    template = json.loads(template_path.read_text(encoding="utf-8"))
    for item in template["assets"]:
        item["human_selected"] = True
        item["constitution_acceptance"] = True
    write_json(template_path, template)
    monkeypatch.setattr(
        "src.application.manual_visual_asset_ingest_v1._probe_video",
        lambda path: {"duration": 1.0, "width": 1280, "height": 720, "fps": 30.0, "codec": "h264", "container": "mp4"},
    )
    first = ingest_manual_visuals(
        episode_root=episode_root, pack_path=Path(result["pack_path"]),
        ingest_template_path=template_path, ingest_dir=incoming,
        expected_pack_sha256=sha256_file(Path(result["pack_path"])),
    )
    assert first["status"] == "PASS_COMPLETE_VALIDATED"
    locked = lock_manual_visuals(
        pack_path=Path(result["pack_path"]), ledger_path=Path(first["ledger_path"]),
        output_path=episode_root / "manual-visuals/lock.json",
        expected_pack_sha256=sha256_file(Path(result["pack_path"])),
        expected_ledger_sha256=sha256_file(Path(first["ledger_path"])),
    )
    assert locked["status"] == "SHA_BOUND_VISUAL_LOCK"
    (incoming / pack["shots"][1]["expected_filename"]).write_bytes(b"synthetic-video-two")
    second = ingest_manual_visuals(
        episode_root=episode_root, pack_path=Path(result["pack_path"]),
        ingest_template_path=template_path, ingest_dir=incoming,
        expected_pack_sha256=sha256_file(Path(result["pack_path"])),
    )
    assert second["replacements"][0]["shot_id"] == "SH-002"
    ledger = json.loads(Path(second["ledger_path"]).read_text(encoding="utf-8"))
    assert ledger["invalidations"][-1]["affected_shot_ids"] == ["SH-002"]
    assert len([item for item in ledger["assets"] if item["shot_id"] == "SH-002" and item["current"]]) == 1


def test_duplicate_asset_requires_explicit_reuse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    episode_root, result = prepared_episode(tmp_path)
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    pack = json.loads(Path(result["pack_path"]).read_text(encoding="utf-8"))
    image_path = incoming / pack["shots"][0]["expected_filename"]
    Image.new("RGB", (1280, 720), (1, 2, 3)).save(image_path)
    video_path = incoming / pack["shots"][1]["expected_filename"]
    video_path.write_bytes(image_path.read_bytes())
    template_path = Path(result["ingest_template_path"])
    template = json.loads(template_path.read_text(encoding="utf-8"))
    for item in template["assets"]:
        item["human_selected"] = True
        item["constitution_acceptance"] = True
    write_json(template_path, template)
    monkeypatch.setattr(
        "src.application.manual_visual_asset_ingest_v1._probe_video",
        lambda path: {"duration": 1.0, "width": 1280, "height": 720, "fps": 30.0, "codec": "h264", "container": "mp4"},
    )
    result2 = ingest_manual_visuals(
        episode_root=episode_root, pack_path=Path(result["pack_path"]),
        ingest_template_path=template_path, ingest_dir=incoming,
        expected_pack_sha256=sha256_file(Path(result["pack_path"])),
    )
    assert result2["status"] == "MISSING_MANUAL_VISUAL_ASSETS"
    assert result2["failures"] == [{"shot_id": "SH-002", "code": "DUPLICATE_ASSET_REUSE_NOT_APPROVED"}]
