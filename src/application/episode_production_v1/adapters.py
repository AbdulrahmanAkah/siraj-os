"""Thin, evidence-preserving adapters for the existing production APIs.

These adapters deliberately do not create media themselves.  Provider-facing
callables are injected by composition code, which keeps a default episode run
offline and makes every external request pass through the orchestrator guard.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable

from src.application.episode_orchestration_v1.runtime import EpisodeContext, StageExecutionResult, StageSpec
from src.application.local_video_production.subtitles_v1 import SubtitleRequest, TranscriptSegment, generate_subtitles
from src.application.local_video_production.storyboard_generator_v1 import StoryboardRequest, generate_storyboard
from .video_provider_v1 import VideoProviderV1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fp(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()


def _relative(root: Path, path: Path | str) -> Path:
    candidate = Path(path).resolve(strict=False)
    try:
        return candidate.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError("ADAPTER_OUTPUT_OUTSIDE_PROJECT") from error


def _artifact(stage: str, kind: str, path: Path, fingerprint: str, *, approval: str = "NOT_REQUESTED", sources: list[str] | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    value = {
        "artifact_id": f"{kind}:{fingerprint[:16]}", "artifact_type": kind,
        "stage_id": stage, "path": path.as_posix(),
        "schema_version": "siraj-episode-production-artifact-v1", "fingerprint": fingerprint,
        "created_at": _now(), "status": "COMPLETED", "approval_status": approval,
        "source_artifact_ids": sources or [], "supersedes": None,
        "runtime_only": True, "git_trackable": False,
    }
    if metadata:
        value["metadata"] = metadata
    return value


def _latest_approval(context: EpisodeContext, stage_id: str) -> dict[str, Any] | None:
    return next((item for item in reversed(context.manifest.get("approvals", [])) if item.get("stage_id") == stage_id), None)


def _approved_script(context: EpisodeContext) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    state = context.manifest["stage_states"].get("narrative_script", {})
    approval = _latest_approval(context, "script_approval")
    script = next((item for item in state.get("outputs", []) if item.get("artifact_type") == "episode-script"), None)
    verification = next((item for item in state.get("outputs", []) if item.get("artifact_type") == "script-verification"), None)
    bound = set(approval.get("artifact_ids", [])) if approval else set()
    if (state.get("status") not in {"COMPLETED", "COMPLETED_WITH_WARNINGS"} or not script or not verification
            or not approval or approval.get("status") not in {"APPROVED", "APPROVED_WITH_NOTES"}
            or not {script["artifact_id"], verification["artifact_id"]} <= bound):
        return None, None
    return script, approval


def _read_script(context: EpisodeContext, artifact: dict[str, Any]) -> dict[str, Any]:
    path = context.project_root / artifact["path"]
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or not isinstance(value.get("full_narration_text"), str):
        raise ValueError("EPISODE_SCRIPT_ARTIFACT_INVALID")
    return value


def _segments(script: dict[str, Any]) -> tuple[TranscriptSegment, ...]:
    result: list[TranscriptSegment] = []
    for section in script.get("sections", []):
        for block in section.get("narration_blocks", []):
            text = block.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            result.append(TranscriptSegment(
                text=text.strip(), speaker_id=block.get("speaker_id"), speaker_name=block.get("speaker_name"),
                role=str(block.get("role") or "PRIMARY_NARRATOR"), voice_id=block.get("voice_id"),
                scene_id=section.get("section_id"), start_ms=block.get("start_ms"), end_ms=block.get("end_ms"),
            ))
    if not result:
        raise ValueError("EPISODE_SCRIPT_TRANSCRIPT_EMPTY")
    return tuple(result)


class ProductionTTSEpisodeAdapter:
    """Wrap ``ProductionTTSOrchestrator.synthesize`` without selecting a provider."""
    def __init__(self, synthesizer: Callable[[dict[str, Any], Path], Any] | None, request_factory: Callable[[dict[str, Any], EpisodeContext], dict[str, Any]] | None = None) -> None:
        self.synthesizer, self.request_factory = synthesizer, request_factory

    def run(self, context: EpisodeContext, stage: StageSpec, run_id: str) -> StageExecutionResult:
        script, _ = _approved_script(context)
        if not script:
            return StageExecutionResult(stage.stage_id, run_id, "BLOCKED_BY_HUMAN_APPROVAL", blocker={"code": "SCRIPT_APPROVAL_REQUIRED"}, next_action="Approve the current script and verification report first.")
        if not (context.allow_external and context.confirm_live):
            return StageExecutionResult(stage.stage_id, run_id, "BLOCKED_BY_EXTERNAL_PROVIDER", blocker={"code": "EXTERNAL_CONFIRMATION_REQUIRED"}, retryable=True)
        if self.synthesizer is None or self.request_factory is None:
            return StageExecutionResult(stage.stage_id, run_id, "NOT_IMPLEMENTED", blocker={"code": "TTS_ADAPTER_DISCONNECTED"})
        try:
            result = self.synthesizer(self.request_factory(script, context), context.project_root)
            output = context.project_root / str(result.output_path)
            if not output.is_file() or output.stat().st_size == 0:
                raise ValueError("MASTERED_WAV_MISSING_OR_EMPTY")
            fingerprint = sha256(output.read_bytes()).hexdigest()
        except (OSError, ValueError) as error:
            return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "OUTPUT_INVALID", "exception_class": type(error).__name__},))
        except Exception as error:
            return StageExecutionResult(stage.stage_id, run_id, "RETRYABLE_FAILURE", errors=({"code": "TRANSIENT_PROVIDER_ERROR", "exception_class": type(error).__name__},), retryable=True)
        output_artifact = _artifact(stage.stage_id, "mastered-wav", _relative(context.project_root, output), fingerprint, approval="TECHNICALLY_ACCEPTED", sources=[script["artifact_id"]], metadata={"script_fingerprint": script["fingerprint"], "report_path": str(getattr(result, "report_path", ""))})
        return StageExecutionResult(stage.stage_id, run_id, "COMPLETED", outputs=(output_artifact,), output_fingerprint=fingerprint, external_calls=1, next_action="Generate subtitles from the mastered WAV.")


class SubtitleEpisodeAdapter:
    """Build a deterministic subtitle request from the approved canonical script."""
    def __init__(self, generator: Callable[[SubtitleRequest], Any] = generate_subtitles) -> None:
        self.generator = generator

    def run(self, context: EpisodeContext, stage: StageSpec, run_id: str) -> StageExecutionResult:
        script_artifact, _ = _approved_script(context)
        audio = next((item for item in context.manifest["stage_states"].get("production_tts", {}).get("outputs", []) if item.get("artifact_type") == "mastered-wav"), None)
        if not script_artifact or not audio:
            return StageExecutionResult(stage.stage_id, run_id, "BLOCKED_BY_DEPENDENCY", blocker={"code": "APPROVED_SCRIPT_AND_AUDIO_REQUIRED"})
        try:
            script = _read_script(context, script_artifact)
            segments = _segments(script)
            audio_path = context.project_root / audio["path"]
            request = SubtitleRequest(mastered_audio_path=audio_path, transcript=script["full_narration_text"], transcript_segments=segments, output_directory=context.output_root.parent / "subtitles-v1")
            track, exported, validation = self.generator(request)
        except Exception as error:
            return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "CONTRACT_MISMATCH", "exception_class": type(error).__name__},))
        if validation.status == "FAIL":
            return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "OUTPUT_INVALID"},), warnings=tuple(validation.warnings))
        fp = _fp({"script": script_artifact["fingerprint"], "audio": audio["fingerprint"], "track": track.input_fingerprint})
        artifact_paths = (("srt", exported.srt_path), ("vtt", exported.vtt_path), ("ass", exported.ass_path), ("subtitle-manifest", exported.manifest_path), ("subtitle-validation", exported.validation_path))
        outputs = tuple(_artifact(stage.stage_id, kind, _relative(context.project_root, path), fp, sources=[script_artifact["artifact_id"], audio["artifact_id"]]) for kind, path in artifact_paths)
        status = "COMPLETED" if validation.status == "PASS" else "COMPLETED_WITH_WARNINGS"
        return StageExecutionResult(stage.stage_id, run_id, status, outputs=outputs, warnings=tuple(validation.warnings), output_fingerprint=fp, next_action="Generate a deterministic storyboard from validated subtitles.")


class StoryboardEpisodeAdapter:
    """Wrap the local storyboard generator; it has no provider/network behaviour."""
    def __init__(self, generator: Callable[[StoryboardRequest], Any] = generate_storyboard) -> None:
        self.generator = generator

    def run(self, context: EpisodeContext, stage: StageSpec, run_id: str) -> StageExecutionResult:
        script, _ = _approved_script(context)
        states = context.manifest["stage_states"]
        audio = next((item for item in states.get("production_tts", {}).get("outputs", []) if item.get("artifact_type") == "mastered-wav"), None)
        subtitles = next((item for item in states.get("subtitles", {}).get("outputs", []) if item.get("artifact_type") == "subtitle-manifest"), None)
        if not script or not audio or not subtitles:
            return StageExecutionResult(stage.stage_id, run_id, "BLOCKED_BY_DEPENDENCY", blocker={"code": "SCRIPT_AUDIO_SUBTITLES_REQUIRED"})
        try:
            request = StoryboardRequest(mastered_audio_path=context.project_root / audio["path"], subtitle_manifest_path=context.project_root / subtitles["path"], output_directory=context.output_root.parent / "storyboard-v1")
            _, exported, validation = self.generator(request)
        except Exception as error:
            return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "CONTRACT_MISMATCH", "exception_class": type(error).__name__},))
        if validation.status == "FAIL":
            return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "OUTPUT_INVALID"},), warnings=tuple(validation.warnings))
        fp = _fp({"script": script["fingerprint"], "audio": audio["fingerprint"], "subtitles": subtitles["fingerprint"], "storyboard": str(exported.manifest_path)})
        source_ids = [script["artifact_id"], audio["artifact_id"], subtitles["artifact_id"]]
        outputs = (
            _artifact(stage.stage_id, "episode-storyboard", _relative(context.project_root, exported.manifest_path), fp, approval="PENDING", sources=source_ids),
            _artifact(stage.stage_id, "visual-asset-plan", _relative(context.project_root, exported.asset_plan_path), fp, approval="PENDING", sources=source_ids),
        )
        return StageExecutionResult(stage.stage_id, run_id, "COMPLETED" if validation.status == "PASS" else "COMPLETED_WITH_WARNINGS", outputs=outputs, warnings=tuple(validation.warnings), output_fingerprint=fp, next_action="Approve the storyboard before any visual or video provider request.")


class VisualProviderEpisodeAdapter:
    """Keep the quota-deferred VisualProvider resumable without implicit live work."""
    def __init__(self, executor: Callable[..., dict[str, Any]] | None = None) -> None:
        self.executor = executor

    def run(self, context: EpisodeContext, stage: StageSpec, run_id: str) -> StageExecutionResult:
        approval = _latest_approval(context, "storyboard_approval")
        if not approval or approval.get("status") not in {"APPROVED", "APPROVED_WITH_NOTES"}:
            return StageExecutionResult(stage.stage_id, run_id, "BLOCKED_BY_HUMAN_APPROVAL", blocker={"code": "STORYBOARD_APPROVAL_REQUIRED"})
        # The actual executor deliberately remains separately confirmed because it
        # owns Gemini quota policy and image-level human review.
        if self.executor is None:
            return StageExecutionResult(stage.stage_id, run_id, "BLOCKED_BY_EXTERNAL_PROVIDER", blocker={"code": "IMPLEMENTATION_COMPLETED_LIVE_VALIDATION_DEFERRED", "retryable": True, "prior_work_preserved": True}, retryable=True, next_action="Run VisualProvider separately with a valid quota policy and explicit confirmation.")
        if not (context.allow_external and context.confirm_live):
            return StageExecutionResult(stage.stage_id, run_id, "BLOCKED_BY_EXTERNAL_PROVIDER", blocker={"code": "EXTERNAL_CONFIRMATION_REQUIRED"}, retryable=True)
        try:
            value = self.executor(context=context, stage=stage, run_id=run_id)
        except Exception as error:
            return StageExecutionResult(stage.stage_id, run_id, "RETRYABLE_FAILURE", errors=({"code": "TRANSIENT_PROVIDER_ERROR", "exception_class": type(error).__name__},), retryable=True)
        if not isinstance(value, dict) or value.get("status") not in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}:
            return StageExecutionResult(stage.stage_id, run_id, "RETRYABLE_FAILURE", blocker={"code": str(value.get("stopped_reason", "VISUAL_PROVIDER_FAILURE")) if isinstance(value, dict) else "VISUAL_PROVIDER_FAILURE"}, retryable=True)
        artifacts = value.get("outputs", [])
        if not isinstance(artifacts, list) or not artifacts:
            return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "VISUAL_OUTPUT_INVALID"},))
        outputs = []
        for item in artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "VISUAL_OUTPUT_INVALID"},))
            path = context.project_root / item["path"]
            if not path.is_file() or path.stat().st_size == 0:
                return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "VISUAL_OUTPUT_INVALID"},))
            fp = sha256(path.read_bytes()).hexdigest()
            outputs.append(_artifact(stage.stage_id, "visual-asset", _relative(context.project_root, path), fp, approval="HUMAN_REVIEW_REQUIRED", metadata={"asset_id": item.get("asset_id"), "model": item.get("model")}))
        return StageExecutionResult(stage.stage_id, run_id, str(value["status"]), outputs=tuple(outputs), output_fingerprint=_fp(outputs), external_calls=int(value.get("external_calls", 1)), next_action="Record master visual approval before rendering.")


class VideoProviderEpisodeAdapter:
    """Bridge a storyboard-owned allocation to the guarded VideoProvider boundary."""
    def __init__(self, provider: VideoProviderV1 | None, allocation_factory: Callable[[EpisodeContext], dict[str, Any]] | None = None) -> None:
        self.provider, self.allocation_factory = provider, allocation_factory

    def run(self, context: EpisodeContext, stage: StageSpec, run_id: str) -> StageExecutionResult:
        approval = _latest_approval(context, "storyboard_approval")
        if not approval or approval.get("status") not in {"APPROVED", "APPROVED_WITH_NOTES"}:
            return StageExecutionResult(stage.stage_id, run_id, "BLOCKED_BY_HUMAN_APPROVAL", blocker={"code": "STORYBOARD_APPROVAL_REQUIRED"})
        if self.provider is None or self.allocation_factory is None:
            return StageExecutionResult(stage.stage_id, run_id, "NOT_IMPLEMENTED", blocker={"code": "VIDEO_ADAPTER_DISCONNECTED"})
        allocation = self.allocation_factory(context)
        result = self.provider.execute(
            allocation, allow_external=context.allow_external, confirm_live=context.confirm_live,
            credential_present=bool(context.definition.get("external_provider_policy", {}).get("credential_present")),
            disclosure_permitted=bool(context.definition.get("external_provider_policy", {}).get("disclosure_permitted")),
        )
        if result["status"] != "COMPLETED":
            return StageExecutionResult(stage.stage_id, run_id, result["status"], errors=tuple({"code": item} for item in result.get("errors", [])), blocker={"code": result.get("blocker", "VIDEO_PROVIDER_FAILURE")}, retryable=result["status"] in {"BLOCKED_BY_EXTERNAL_PROVIDER", "RETRYABLE_FAILURE"}, external_calls=int(result.get("external_calls", 0)))
        outputs = []
        for item in result.get("outputs", []):
            path = context.project_root / str(item["path"])
            if not path.is_file() or sha256(path.read_bytes()).hexdigest() != item["sha256"]:
                return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "VIDEO_OUTPUT_INVALID"},))
            outputs.append(_artifact(stage.stage_id, "generated-video", _relative(context.project_root, path), str(item["sha256"]), approval="HUMAN_REVIEW_REQUIRED", metadata={"request_id": item["request_id"], "model": item["model"], "duration_seconds": item["duration_seconds"]}))
        return StageExecutionResult(stage.stage_id, run_id, "COMPLETED", outputs=tuple(outputs), output_fingerprint=_fp(result.get("outputs", [])), external_calls=int(result.get("external_calls", 0)), next_action="Record per-asset video approval before rendering.")


class RenderEpisodeAdapter:
    """Invoke an injected local renderer only after an approved render manifest exists."""
    def __init__(self, renderer: Callable[[Path, Path], Any] | None = None, manifest_factory: Callable[[EpisodeContext], Path] | None = None) -> None:
        self.renderer, self.manifest_factory = renderer, manifest_factory

    def run(self, context: EpisodeContext, stage: StageSpec, run_id: str) -> StageExecutionResult:
        if self.renderer is None or self.manifest_factory is None:
            return StageExecutionResult(stage.stage_id, run_id, "NOT_IMPLEMENTED", blocker={"code": "RENDER_ADAPTER_DISCONNECTED"})
        try:
            manifest_path = self.manifest_factory(context)
            result = self.renderer(context.project_root, manifest_path)
            output = context.project_root / str(result.output)
            report = context.project_root / str(result.report)
            if not output.is_file() or not report.is_file():
                raise ValueError("RENDER_OUTPUT_INVALID")
            fp = sha256(output.read_bytes()).hexdigest()
        except Exception as error:
            return StageExecutionResult(stage.stage_id, run_id, "PERMANENT_FAILURE", errors=({"code": "OUTPUT_INVALID", "exception_class": type(error).__name__},))
        outputs = (_artifact(stage.stage_id, "rendered-video", _relative(context.project_root, output), fp), _artifact(stage.stage_id, "render-verification", _relative(context.project_root, report), _fp({"render": fp, "report": report.read_text(encoding="utf-8", errors="replace")[:4000]})))
        return StageExecutionResult(stage.stage_id, run_id, "COMPLETED", outputs=outputs, output_fingerprint=fp, next_action="Record final render approval before publication.")
