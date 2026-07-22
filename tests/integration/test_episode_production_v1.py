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
from src.application.evidence_to_script_episode_v1.runtime import EVIDENCE_PACKAGE_SCHEMA, SPEAKING_RATE_POLICY


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


def _e2e_definition_and_config(tmp_path: Path) -> tuple[dict, dict, dict]:
    source = tmp_path / "source.json"; source.write_text("{}", encoding="utf-8")
    claim = {"claim_id": "claim-1", "normalized_claim": "حدث موثق في بغداد.", "claim_type": "EVENT", "status": "APPROVED", "confidence": 1.0, "source_refs": ["source-1"], "evidence_refs": ["evidence-1"], "chronology_refs": [], "entity_refs": [], "dispute_status": "NONE", "approved_for_narrative": True, "restrictions": [], "notes": ""}
    evidence = {"schema_version": EVIDENCE_PACKAGE_SCHEMA, "episode_id": "episode-e2e", "source_package_id": "source-package", "evidence_package_id": "evidence-package", "evidence_status": "APPROVED", "approved_at": "2026-07-23T00:00:00Z", "approved_by": "fixture", "source_artifacts": [{"artifact_id": "source-1", "path": str(source), "fingerprint": sha256(source.read_bytes()).hexdigest()}], "claims": [claim], "events": [], "entities": [], "chronology": [{"claim_id": "claim-1"}], "locations": [], "quotations": [], "disputed_points": [], "uncertainty_notes": [], "exclusions": [], "religious_sensitivity": {}, "historical_scope": {}, "geographical_scope": {}, "provenance": {"evidence": [{"evidence_id": "evidence-1"}]}}
    evidence["input_fingerprint"] = sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    evidence_path = tmp_path / "evidence.json"; evidence_path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
    policy = {"default_allowed": False, "explicit_live_confirmation_required": True, "provider_configured": True, "credential_present": True, "disclosure_permitted": True, "request_limit_available": True, "quota_policy_valid": True, "stage_permissions": {"narrative_script": True, "production_tts": True, "visual_provider": True, "video_provider": True}}
    definition = default_episode_definition(episode_id="episode-e2e", source_package={"path": str(source), "approval_status": "APPROVED"}, evidence_package={"path": str(evidence_path), "input_fingerprint": evidence["input_fingerprint"]})
    config = {"schema_version": PIPELINE_CONFIG_SCHEMA, "episode_id": "episode-e2e", "narrative_writer": {"enabled": True, "model_id": "fixture"}, "tts": {"enabled": False}, "subtitles": {"enabled": False}, "storyboard": {"enabled": False}, "visuals": {"enabled": False}, "video": {"enabled": False}, "render": {"enabled": False}, "external_provider_policy": policy, "approval_policy": {}, "runtime_paths": {}, "request_limits": {}, "disclosure_permissions": {}}
    return definition, config, claim


class FakeNarrativeWriter:
    writer_id = "fake-e2e-narrative"
    writer_version = "1"
    calls = 0
    def generate(self, *, evidence_package, brief, outline):  # type: ignore[no-untyped-def]
        self.calls += 1
        fact = evidence_package["claims"][0]
        filler = " ".join(["انتقال"] * (18 * SPEAKING_RATE_POLICY["words_per_minute"]))
        fact_block = {"block_id": "fact-1", "block_type": "CONTEXT", "assertion_class": "FACTUAL", "text": fact["normalized_claim"], "claim_ids": [fact["claim_id"]], "source_refs": fact["source_refs"], "evidence_refs": fact["evidence_refs"], "citation_required": True, "citation_status": "BOUND", "confidence": 1.0, "disputed": False, "uncertainty_language": None, "direct_quote": False, "quote_id": None}
        editorial_block = {"block_id": "editorial-1", "block_type": "TRANSITION", "assertion_class": "EDITORIAL_TRANSITION", "text": filler, "claim_ids": [], "source_refs": [], "evidence_refs": [], "citation_required": False, "citation_status": "NOT_REQUIRED", "confidence": 1.0, "disputed": False, "uncertainty_language": None, "direct_quote": False, "quote_id": None}
        sections = []
        for section in outline["sections"]:
            blocks = [fact_block] if section["required_claim_ids"] else []
            if section["order"] == len(outline["sections"]):
                blocks.append(editorial_block)
            sections.append({"section_id": section["section_id"], "order": section["order"], "heading": section["title"], "narration_blocks": blocks})
        return {"sections": sections, "quotation_index": {}}


def test_e2e_first_boundary_is_stable_and_requires_script_approval(tmp_path: Path) -> None:
    definition, config, _ = _e2e_definition_and_config(tmp_path)
    writer = FakeNarrativeWriter()
    orchestrator = EpisodeProductionComposition(tmp_path, definition, config, output_root=tmp_path / "working" / "e2e", narrative_writer=writer).build()
    result = orchestrator.execute(mode="run-through", allow_external=True, confirm_live=True)
    states = result["manifest"]["stage_states"]
    assert result["status"] == "WAITING_FOR_HUMAN_APPROVAL", states
    assert states["narrative_script"]["status"] == "COMPLETED" and states["script_approval"]["status"] == "BLOCKED_BY_HUMAN_APPROVAL"
    assert writer.calls == 1 and states["production_tts"]["status"] == "BLOCKED_BY_DEPENDENCY"


def test_e2e_fake_pipeline_advances_only_through_human_boundaries(tmp_path: Path) -> None:
    definition, config, _ = _e2e_definition_and_config(tmp_path)
    config.update({"tts": {"enabled": True}, "subtitles": {"enabled": True}, "storyboard": {"enabled": True}, "visuals": {"enabled": True}, "video": {"enabled": True}, "render": {"enabled": True}})
    calls = {name: 0 for name in ("tts", "subtitles", "storyboard", "visual", "video", "render")}
    def tts(request, root):  # type: ignore[no-untyped-def]
        calls["tts"] += 1; path = root / "working" / "fixture.wav"; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"wav")
        return SimpleNamespace(output_path=path.relative_to(root).as_posix(), report_path="working/tts.json")
    def subtitles(request):  # type: ignore[no-untyped-def]
        calls["subtitles"] += 1; root = request.output_directory; root.mkdir(parents=True, exist_ok=True); paths = [root / name for name in ("a.srt", "a.vtt", "a.ass", "manifest.json", "validation.json")]
        for path in paths: path.write_text("{}", encoding="utf-8")
        return SimpleNamespace(input_fingerprint="subtitle-fp"), SimpleNamespace(srt_path=paths[0], vtt_path=paths[1], ass_path=paths[2], manifest_path=paths[3], validation_path=paths[4]), SimpleNamespace(status="PASS", warnings=())
    def storyboard(request):  # type: ignore[no-untyped-def]
        calls["storyboard"] += 1; root = request.output_directory; root.mkdir(parents=True, exist_ok=True); manifest, plan = root / "board.json", root / "asset-plan.json"; manifest.write_text("{}", encoding="utf-8"); plan.write_text("{}", encoding="utf-8")
        return (), SimpleNamespace(manifest_path=manifest, asset_plan_path=plan), SimpleNamespace(status="PASS", warnings=())
    def visual(**kwargs):  # type: ignore[no-untyped-def]
        calls["visual"] += 1; path = tmp_path / "working" / "master.png"; path.write_bytes(b"png")
        return {"status": "COMPLETED", "outputs": [{"path": path.relative_to(tmp_path).as_posix(), "asset_id": "master", "model": "fake"}], "external_calls": 0}
    clip = tmp_path / "working" / "clip.mp4"; clip.parent.mkdir(parents=True, exist_ok=True); clip.write_bytes(b"mp4")
    class VideoClient:
        def generate(self, request):  # type: ignore[no-untyped-def]
            calls["video"] += 1; return {"path": clip.relative_to(tmp_path).as_posix(), "sha256": sha256(clip.read_bytes()).hexdigest()}
    def render(root, manifest):  # type: ignore[no-untyped-def]
        calls["render"] += 1; output, report = root / "working" / "final.mp4", root / "working" / "render.json"; output.write_bytes(b"video"); report.write_text("{}", encoding="utf-8")
        return SimpleNamespace(output=output.relative_to(root).as_posix(), report=report.relative_to(root).as_posix())
    writer = FakeNarrativeWriter()
    pipeline = EpisodeProductionComposition(tmp_path, definition, config, output_root=tmp_path / "working" / "e2e", narrative_writer=writer, tts_synthesizer=tts, tts_request_factory=lambda script, context: {}, subtitle_generator=subtitles, storyboard_generator=storyboard, visual_executor=visual, video_provider=VideoProviderV1(VideoProviderPolicy(request_limit=1), VideoClient()), video_allocation_factory=lambda context: {"requests": [{"request_id": "clip", "preferred_model": "VEO_3_1_LITE_1080P", "requested_duration_seconds": 4, "video_required": "REQUIRED", "video_justification": "fixture"}]}, renderer=render, render_manifest_factory=lambda context: tmp_path / "unused.json")
    orchestrator = pipeline.build()
    statuses = {stage.stage_id: stage.current_implementation_status for stage in orchestrator.registry}
    assert statuses["narrative_script"] == "AVAILABLE_EXTERNAL_ADAPTER" and statuses["production_tts"] == "AVAILABLE_EXTERNAL_ADAPTER"
    assert statuses["subtitles"] == statuses["storyboard"] == statuses["render"] == "AVAILABLE_LOCAL_ADAPTER"
    assert statuses["visual_provider"] == "IMPLEMENTATION_COMPLETED_LIVE_VALIDATION_DEFERRED" and statuses["video_provider"] == "VIDEO_PROVIDER_V1_IMPLEMENTED_LIVE_VALIDATION_DEFERRED"
    def run_boundary() -> dict:
        result = orchestrator.execute(mode="run-through", allow_external=True, confirm_live=True)
        assert result["status"] in {"WAITING_FOR_HUMAN_APPROVAL", "READY_FOR_PUBLICATION", "COMPLETED"}
        return result
    def approve(gate: str, producer: str) -> None:
        manifest = orchestrator.execute(mode="status")["manifest"]
        artifacts = tuple(item["artifact_id"] for item in manifest["stage_states"][producer]["outputs"])
        orchestrator.record_approval(stage_id=gate, decision="APPROVED", reviewer="fixture", artifact_ids=artifacts)
    first = run_boundary(); assert calls == {name: 0 for name in calls} and writer.calls == 1
    approve("script_approval", "narrative_script")
    second = run_boundary(); assert calls["tts"] == calls["subtitles"] == calls["storyboard"] == 1 and calls["visual"] == calls["video"] == calls["render"] == 0
    approve("storyboard_approval", "storyboard")
    third = run_boundary(); assert calls["visual"] == 1 and calls["video"] == calls["render"] == 0
    approve("master_visual_approval", "visual_provider")
    fourth = run_boundary(); assert calls["video"] == 1 and calls["render"] == 0
    approve("video_approval", "video_provider")
    fifth = run_boundary(); assert calls["render"] == 1 and fifth["status"] == "WAITING_FOR_HUMAN_APPROVAL"
    approve("final_render_approval", "render")
    ready = orchestrator.execute(mode="status"); assert ready["status"] == "READY_FOR_PUBLICATION"
    approve("publication", "publication")
    completed = orchestrator.execute(mode="status"); assert completed["status"] == "COMPLETED"
    manifest = completed["manifest"]; assert writer.calls == 1 and len({entry["run_id"] for entry in manifest["execution_history"]}) == len(manifest["execution_history"])
    artifacts = {item["artifact_type"]: item for item in manifest["artifact_index"]}; assert {"approved-evidence-package", "episode-script", "mastered-wav", "subtitle-manifest", "episode-storyboard", "visual-asset", "generated-video", "rendered-video"} <= set(artifacts)
    assert artifacts["mastered-wav"]["source_artifact_ids"] == [artifacts["episode-script"]["artifact_id"]]
    assert artifacts["rendered-video"]["source_artifact_ids"] and sum(state["external_request_count"] for state in manifest["stage_states"].values()) == 2


def test_pipeline_cli_plan_json_is_clean_and_offline(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    from scripts.fast_track.run_episode_production_pipeline_v1 import main
    source = tmp_path / "source.json"; source.write_text("{}", encoding="utf-8")
    definition = default_episode_definition(episode_id="episode-cli", source_package={"path": str(source), "approval_status": "APPROVED"})
    config = {"schema_version": PIPELINE_CONFIG_SCHEMA, "episode_id": "episode-cli", "narrative_writer": {"enabled": False}, "tts": {"enabled": False}, "subtitles": {"enabled": True}, "storyboard": {"enabled": True}, "visuals": {}, "video": {}, "render": {"enabled": False}, "external_provider_policy": {"stage_permissions": {}}, "approval_policy": {}, "runtime_paths": {}, "request_limits": {}, "disclosure_permissions": {}}
    definition_path, config_path = tmp_path / "episode.json", tmp_path / "pipeline.json"
    definition_path.write_text(json.dumps(definition), encoding="utf-8"); config_path.write_text(json.dumps(config), encoding="utf-8")
    assert main(["--project-root", str(tmp_path), "--episode-definition", str(definition_path), "--pipeline-config", str(config_path), "--mode", "plan", "--json", "--output", str(tmp_path / "working" / "cli")]) == 0
    assert isinstance(json.loads(capsys.readouterr().out), dict)
