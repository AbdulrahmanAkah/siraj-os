"""Explicit, offline-safe composition root for Episode Production Pipeline v1."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Callable

from src.application.evidence_to_script_episode_v1.gemini_writer import (
    GeminiEvidenceBoundScriptWriter,
    GeminiNarrativeWriterConfig,
    GoogleGenAINarrativeTransport,
)
from src.application.evidence_to_script_episode_v1.runtime import EvidenceToScriptEpisodeAdapter
from src.application.episode_orchestration_v1.runtime import (
    EpisodeContext, EpisodeOrchestrator, StageExecutionResult, StageSpec,
)
from .adapters import (
    ProductionTTSEpisodeAdapter, RenderEpisodeAdapter, StoryboardEpisodeAdapter,
    SubtitleEpisodeAdapter, VideoProviderEpisodeAdapter, VisualProviderEpisodeAdapter,
)
from .pipeline import build_episode_production_registry, composed_runners
from .video_provider_v1 import VideoProviderV1

PIPELINE_CONFIG_SCHEMA = "siraj-episode-production-pipeline-config-v1"


def _fingerprint(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def load_pipeline_config(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("PIPELINE_CONFIGURATION_NOT_OBJECT")
    errors = validate_pipeline_config(value)
    if errors:
        raise ValueError(";".join(errors))
    return value


def validate_pipeline_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if config.get("schema_version") != PIPELINE_CONFIG_SCHEMA:
        errors.append("PIPELINE_CONFIGURATION_SCHEMA_INVALID")
    for name in ("narrative_writer", "tts", "subtitles", "storyboard", "visuals", "video", "render", "external_provider_policy"):
        if not isinstance(config.get(name, {}), dict):
            errors.append(f"PIPELINE_CONFIGURATION_SECTION_INVALID:{name}")
    if not isinstance(config.get("episode_id"), str) or not config["episode_id"].strip():
        errors.append("PIPELINE_CONFIGURATION_EPISODE_ID_REQUIRED")
    narrative = config.get("narrative_writer", {})
    if narrative.get("enabled") is True and not isinstance(narrative.get("model_id"), str):
        errors.append("NARRATIVE_WRITER_MODEL_REQUIRED")
    for name in ("subtitles", "storyboard", "render"):
        if config.get(name, {}).get("enabled") not in {True, False, None}:
            errors.append(f"PIPELINE_CONFIGURATION_ENABLED_INVALID:{name}")
    policy = config.get("external_provider_policy", {})
    if policy and not isinstance(policy.get("stage_permissions", {}), dict):
        errors.append("PIPELINE_STAGE_PERMISSIONS_INVALID")
    return errors


class EnvironmentGeminiNarrativeTransport:
    """Defers environment access and SDK construction until an approved live call."""
    def generate_json(self, *, model_id: str, prompt: str, maximum_output_tokens: int, temperature: float) -> dict[str, Any]:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY_MISSING")
        return GoogleGenAINarrativeTransport(key).generate_json(
            model_id=model_id, prompt=prompt,
            maximum_output_tokens=maximum_output_tokens, temperature=temperature,
        )


@dataclass
class EpisodeProductionComposition:
    """Wires thin adapters; it contains no stage implementation or provider call."""
    project_root: Path
    definition: dict[str, Any]
    config: dict[str, Any]
    output_root: Path | None = None
    tts_synthesizer: Callable[[dict[str, Any], Path], Any] | None = None
    tts_request_factory: Callable[[dict[str, Any], EpisodeContext], dict[str, Any]] | None = None
    visual_executor: Callable[..., dict[str, Any]] | None = None
    video_provider: VideoProviderV1 | None = None
    video_allocation_factory: Callable[[EpisodeContext], dict[str, Any]] | None = None
    renderer: Callable[[Path, Path], Any] | None = None
    render_manifest_factory: Callable[[EpisodeContext], Path] | None = None
    narrative_writer: Any | None = None
    subtitle_generator: Callable[[Any], Any] | None = None
    storyboard_generator: Callable[[Any], Any] | None = None

    def _evidence_runner(self) -> Callable[[EpisodeContext, StageSpec, str], StageExecutionResult]:
        evidence_path = Path(str(self.definition.get("evidence_package", {}).get("path", "")))
        adapter = EvidenceToScriptEpisodeAdapter(self.project_root, evidence_path)
        def run(context: EpisodeContext, stage: StageSpec, run_id: str) -> StageExecutionResult:
            package, errors = adapter.validate_input(context.definition)
            if errors or package is None:
                return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=tuple({"code": item} for item in errors), blocker={"code": "EVIDENCE_PACKAGE_INVALID"})
            path = evidence_path.resolve()
            try:
                relative = path.relative_to(context.project_root.resolve()).as_posix()
            except ValueError:
                return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "EVIDENCE_PATH_OUTSIDE_PROJECT"},))
            artifact = {"artifact_id": f"approved-evidence:{package['evidence_package_id']}", "artifact_type": "approved-evidence-package", "stage_id": stage.stage_id, "path": relative, "schema_version": package["schema_version"], "fingerprint": package["input_fingerprint"], "created_at": "", "status": "COMPLETED", "approval_status": "APPROVED", "source_artifact_ids": [], "supersedes": None, "runtime_only": True, "git_trackable": False}
            return StageExecutionResult(stage.stage_id, run_id, "COMPLETED", outputs=(artifact,), input_fingerprint=package["input_fingerprint"], output_fingerprint=package["input_fingerprint"], next_action="Generate the evidence-bound narrative script.")
        return run

    def _writer(self) -> Any | None:
        if self.narrative_writer is not None:
            return self.narrative_writer
        item = self.config.get("narrative_writer", {})
        if item.get("enabled") is not True:
            return None
        return GeminiEvidenceBoundScriptWriter(GeminiNarrativeWriterConfig(
            provider_id=str(item.get("provider_id", "gemini")), model_id=str(item["model_id"]),
            maximum_input_tokens=int(item.get("maximum_input_tokens", 24000)),
            maximum_output_tokens=int(item.get("maximum_output_tokens", 30000)),
            temperature=float(item.get("temperature", 0.2)),
            prompt_version=str(item.get("prompt_version", "evidence-to-script-gemini-v1")),
        ), EnvironmentGeminiNarrativeTransport())

    def build(self) -> EpisodeOrchestrator:
        if self.config["episode_id"] != self.definition.get("episode_id"):
            raise ValueError("PIPELINE_CONFIGURATION_EPISODE_ID_MISMATCH")
        definition = json.loads(json.dumps(self.definition))
        definition["external_provider_policy"] = self.config.get("external_provider_policy", definition.get("external_provider_policy", {}))
        writer = self._writer()
        evidence_path = Path(str(definition.get("evidence_package", {}).get("path", "")))
        narrative = EvidenceToScriptEpisodeAdapter(self.project_root, evidence_path, writer=writer) if writer is not None else None
        runners: dict[str, Any] = {"evidence_knowledge": self._evidence_runner()}
        runners.update(composed_runners(
            narrative=narrative,
            tts=ProductionTTSEpisodeAdapter(self.tts_synthesizer, self.tts_request_factory) if self.tts_synthesizer and self.tts_request_factory else None,
            subtitles=SubtitleEpisodeAdapter(self.subtitle_generator) if self.subtitle_generator is not None else (SubtitleEpisodeAdapter() if self.config.get("subtitles", {}).get("enabled") is True else None),
            storyboard=StoryboardEpisodeAdapter(self.storyboard_generator) if self.storyboard_generator is not None else (StoryboardEpisodeAdapter() if self.config.get("storyboard", {}).get("enabled") is True else None),
            visual=VisualProviderEpisodeAdapter(self.visual_executor) if self.visual_executor is not None else None,
            video=VideoProviderEpisodeAdapter(self.video_provider, self.video_allocation_factory) if self.video_provider and self.video_allocation_factory else None,
            render=RenderEpisodeAdapter(self.renderer, self.render_manifest_factory) if self.renderer and self.render_manifest_factory else None,
        ))
        registry = list(build_episode_production_registry(runners=runners))
        for index, stage in enumerate(registry):
            if stage.stage_id == "evidence_knowledge":
                registry[index] = StageSpec(**{**stage.__dict__, "runner": "episode_production_v1:evidence_knowledge", "current_implementation_status": "AVAILABLE_LOCAL_ADAPTER"})
            elif stage.stage_id == "visual_provider" and stage.stage_id in runners:
                registry[index] = StageSpec(**{**stage.__dict__, "current_implementation_status": "IMPLEMENTATION_COMPLETED_LIVE_VALIDATION_DEFERRED"})
            elif stage.stage_id == "video_provider" and stage.stage_id in runners:
                registry[index] = StageSpec(**{**stage.__dict__, "current_implementation_status": "VIDEO_PROVIDER_V1_IMPLEMENTED_LIVE_VALIDATION_DEFERRED"})
        return EpisodeOrchestrator(self.project_root, definition, output_root=self.output_root, registry=tuple(registry), runners=runners)
