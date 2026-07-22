from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

from src.application.episode_orchestration_v1.runtime import EpisodeContext, StageSpec, default_episode_definition
from src.application.episode_production_v1.adapters import SubtitleEpisodeAdapter, VisualProviderEpisodeAdapter
from src.application.episode_production_v1.composition import EpisodeProductionComposition, PIPELINE_CONFIG_SCHEMA, validate_pipeline_config
from src.application.episode_production_v1.pipeline import build_episode_production_registry, composed_runners
from src.application.episode_production_v1.video_provider_v1 import VideoProviderPolicy, VideoProviderV1, validate_video_allocation, validate_video_output
from src.application.evidence_to_script_episode_v1.gemini_writer import GeminiEvidenceBoundScriptWriter, GeminiNarrativeWriterConfig


def _context(tmp_path: Path) -> EpisodeContext:
    script_path = tmp_path / "working" / "episode" / "episode-script-v1.json"
    script_path.parent.mkdir(parents=True)
    script_path.write_text(json.dumps({"full_narration_text": "نص سردي موثق.", "sections": [{"section_id": "s1", "narration_blocks": [{"text": "نص سردي موثق.", "role": "PRIMARY_NARRATOR"}]}]}, ensure_ascii=False), encoding="utf-8")
    audio_path = tmp_path / "working" / "audio.wav"; audio_path.write_bytes(b"fixture")
    script = {"artifact_id": "episode-script:1", "artifact_type": "episode-script", "path": script_path.relative_to(tmp_path).as_posix(), "fingerprint": "script-fp"}
    verification = {"artifact_id": "script-verification:1", "artifact_type": "script-verification", "path": "working/verification.json", "fingerprint": "verification-fp"}
    audio = {"artifact_id": "mastered-wav:1", "artifact_type": "mastered-wav", "path": audio_path.relative_to(tmp_path).as_posix(), "fingerprint": "audio-fp"}
    manifest = {"stage_states": {"narrative_script": {"status": "COMPLETED", "outputs": [script, verification]}, "production_tts": {"outputs": [audio]}}, "approvals": [{"stage_id": "script_approval", "status": "APPROVED", "artifact_ids": [script["artifact_id"], verification["artifact_id"]]}]}
    return EpisodeContext(tmp_path, {"episode_id": "episode"}, manifest, tmp_path / "working" / "orchestrator")


def test_subtitle_adapter_uses_canonical_script_transcript(tmp_path: Path) -> None:
    captured = {}
    def fake(request):  # type: ignore[no-untyped-def]
        captured["request"] = request; root = request.output_directory; root.mkdir(parents=True)
        paths = [root / name for name in ("a.srt", "a.vtt", "a.ass", "manifest.json", "validation.json")]
        for path in paths: path.write_text("{}", encoding="utf-8")
        return SimpleNamespace(input_fingerprint="track"), SimpleNamespace(srt_path=paths[0], vtt_path=paths[1], ass_path=paths[2], manifest_path=paths[3], validation_path=paths[4]), SimpleNamespace(status="PASS", warnings=())
    result = SubtitleEpisodeAdapter(fake).run(_context(tmp_path), StageSpec("subtitles", "Subtitles", "1", 1, "fake"), "run")
    assert result.status == "COMPLETED" and captured["request"].transcript == "نص سردي موثق."
    assert captured["request"].transcript_segments[0].text == "نص سردي موثق."
    assert {item["artifact_type"] for item in result.outputs} == {"srt", "vtt", "ass", "subtitle-manifest", "subtitle-validation"}


def test_visual_deferred_requires_storyboard_approval_and_makes_no_call(tmp_path: Path) -> None:
    context = _context(tmp_path)
    blocked = VisualProviderEpisodeAdapter().run(context, StageSpec("visual_provider", "Visual", "1", 1, "visual"), "run")
    assert blocked.status == "BLOCKED_BY_HUMAN_APPROVAL" and blocked.external_calls == 0
    context.manifest["approvals"].append({"stage_id": "storyboard_approval", "status": "APPROVED", "artifact_ids": []})
    deferred = VisualProviderEpisodeAdapter().run(context, StageSpec("visual_provider", "Visual", "1", 1, "visual"), "run")
    assert deferred.status == "BLOCKED_BY_EXTERNAL_PROVIDER" and deferred.retryable and deferred.external_calls == 0


def test_composition_is_offline_safe_and_marks_missing_external_adapters_disconnected(tmp_path: Path) -> None:
    source = tmp_path / "source.json"; source.write_text("{}", encoding="utf-8")
    definition = default_episode_definition(episode_id="episode-config", source_package={"path": str(source), "approval_status": "APPROVED"})
    config = {"schema_version": PIPELINE_CONFIG_SCHEMA, "episode_id": "episode-config", "narrative_writer": {"enabled": False}, "tts": {"enabled": False}, "subtitles": {"enabled": True}, "storyboard": {"enabled": True}, "visuals": {"enabled": False}, "video": {"enabled": False}, "render": {"enabled": False}, "external_provider_policy": {"stage_permissions": {}}, "approval_policy": {}, "runtime_paths": {}, "request_limits": {}, "disclosure_permissions": {}}
    assert validate_pipeline_config(config) == []
    orchestrator = EpisodeProductionComposition(tmp_path, definition, config, output_root=tmp_path / "working" / "pipeline").build()
    statuses = {stage.stage_id: stage.current_implementation_status for stage in orchestrator.registry}
    assert statuses["narrative_script"] == "DISCONNECTED" and statuses["production_tts"] == "DISCONNECTED"
    assert statuses["subtitles"] == "AVAILABLE_LOCAL_ADAPTER" and statuses["storyboard"] == "AVAILABLE_LOCAL_ADAPTER"
    assert orchestrator.execute(mode="plan")["plan"]["external_calls_required"] == []


def test_registry_and_gemini_writer_are_callable_without_network() -> None:
    runners = composed_runners(subtitles=SubtitleEpisodeAdapter(lambda request: None))
    registry = {stage.stage_id: stage for stage in build_episode_production_registry(runners=runners)}
    assert registry["subtitles"].current_implementation_status == "AVAILABLE_LOCAL_ADAPTER"
    captured = {}
    class Transport:
        def generate_json(self, **kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs); return {"sections": [], "quotation_index": {}}
    writer = GeminiEvidenceBoundScriptWriter(GeminiNarrativeWriterConfig(), Transport())
    assert writer.generate(evidence_package={"claims": []}, brief={"title": "نص عربي"}, outline={})["sections"] == []
    assert "نص عربي" in captured["prompt"] and writer.requires_external is True and "gemini-2.5-flash" in writer.writer_version or writer.writer_version.startswith("1:")


def test_video_policy_boundaries_and_output_contract(tmp_path: Path) -> None:
    policy = VideoProviderPolicy()
    def request(seconds: int, model: str = "VEO_3_1_LITE_1080P") -> dict[str, object]:
        return {"request_id": "clip", "preferred_model": model, "requested_duration_seconds": seconds, "video_required": "REQUIRED", "video_justification": "storyboard requirement"}
    assert validate_video_allocation({"requests": [request(300)]}, policy) == []
    assert "POLICY_VALIDATION_ERROR:MAXIMUM_FINAL_GENERATED_VIDEO_SECONDS" in validate_video_allocation({"requests": [request(301)]}, policy)
    assert validate_video_allocation({"requests": [{**request(450), "video_required": "PREFERRED"}]}, policy) == []
    assert "VIDEO_ADDITIONAL_APPROVAL_REQUIRED" in validate_video_allocation({"requests": [{**request(451), "video_required": "PREFERRED"}]}, policy)
    assert "POLICY_VALIDATION_ERROR:ABSOLUTE_GENERATED_SECONDS_CAP" in validate_video_allocation({"requests": [{**request(601), "video_required": "PREFERRED"}], "additional_approval": True}, policy)
    assert "VIDEO_MODEL_NOT_ALLOWED" in validate_video_allocation({"requests": [request(1, "OTHER")]}, policy)
    fast = request(1, "VEO_3_1_FAST_1080P"); fast["video_justification"] = ""
    assert "VIDEO_FAST_JUSTIFICATION_REQUIRED" in validate_video_allocation({"requests": [fast]}, policy)
    clip = tmp_path / "clip.mp4"; clip.write_bytes(b"fixture")
    assert validate_video_output(clip, expected_sha256=sha256(clip.read_bytes()).hexdigest()) == []
    assert VideoProviderV1(policy).execute({"requests": []}, allow_external=False, confirm_live=False, credential_present=False, disclosure_permitted=False)["external_calls"] == 0
