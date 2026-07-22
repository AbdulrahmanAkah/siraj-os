"""Evidence-preserving coordination for one documentary episode.

This module deliberately owns only orchestration, policy, state, resume and
audit.  It never generates research, media, or provider requests itself.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from typing import Any, Callable
from uuid import uuid4


EPISODE_DEFINITION_SCHEMA = "siraj-episode-definition-v1"
ORCHESTRATION_MANIFEST_SCHEMA = "siraj-episode-orchestration-manifest-v1"
STAGE_REGISTRY_SCHEMA = "siraj-episode-stage-registry-v1"
DEPENDENCY_GRAPH_SCHEMA = "siraj-episode-dependency-graph-v1"
ARTIFACT_INDEX_SCHEMA = "siraj-episode-artifact-index-v1"
EXECUTION_PLAN_SCHEMA = "siraj-episode-execution-plan-v1"
STATUS_REPORT_SCHEMA = "siraj-episode-status-report-v1"
ORCHESTRATOR_VERSION = "1.0"

COMPLETED_STATUSES = frozenset({"COMPLETED", "COMPLETED_WITH_WARNINGS", "SKIPPED_BY_POLICY"})
TERMINAL_BLOCKING_STATUSES = frozenset({"PERMANENT_FAILURE", "NOT_IMPLEMENTED"})
TRANSIENT_EXTERNAL_ERRORS = frozenset({"QUOTA_EXHAUSTED", "RATE_LIMITED", "PROVIDER_UNAVAILABLE", "TRANSIENT_PROVIDER_ERROR", "DAILY_LIMIT_REACHED"})
VALID_MODES = frozenset({"plan", "run-next", "run-through", "run-stage", "resume", "status", "invalidate-stage"})
KNOWN_REQUESTED_OUTPUTS = frozenset({"render_manifest", "subtitles", "video", "publication_package", "audio", "storyboard"})
ALLOWED_VIDEO_MODELS = frozenset({"VEO_3_1_LITE_1080P", "VEO_3_1_FAST_1080P"})
AVAILABLE_IMPLEMENTATION_PREFIX = "AVAILABLE_"
ARTIFACT_REQUIRED_FIELDS = frozenset({
    "artifact_id", "artifact_type", "stage_id", "path", "schema_version",
    "fingerprint", "created_at", "status", "approval_status",
    "source_artifact_ids", "supersedes", "runtime_only", "git_trackable",
})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _fingerprint(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("EPISODE_CONTRACT_NOT_OBJECT")
    return value


def _relative_or_absolute(project_root: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else project_root / candidate


def _path_within_project(project_root: Path, value: str) -> Path:
    """Resolve an artifact path without allowing it to escape the episode project."""
    candidate = _relative_or_absolute(project_root, value).resolve(strict=False)
    try:
        candidate.relative_to(project_root)
    except ValueError as error:
        raise ValueError("ARTIFACT_PATH_OUTSIDE_PROJECT") from error
    return candidate


def _normalise_project_path(project_root: Path, value: str) -> str:
    return _path_within_project(project_root, value).relative_to(project_root).as_posix()


@dataclass(frozen=True)
class StageSpec:
    stage_id: str
    stage_name: str
    stage_version: str
    stage_order: int
    runner: str | None
    input_contracts: tuple[str, ...] = ()
    output_contracts: tuple[str, ...] = ()
    required_files: tuple[str, ...] = ()
    produced_files: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    optional_dependencies: tuple[str, ...] = ()
    human_approval_required: bool = False
    external_provider_required: bool = False
    retry_policy: str = "NO_AUTOMATIC_RETRY"
    resumable: bool = True
    cacheable: bool = True
    current_implementation_status: str = "AVAILABLE_ADAPTER"


@dataclass(frozen=True)
class StageExecutionResult:
    stage_id: str
    run_id: str
    status: str
    outputs: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[dict[str, Any], ...] = ()
    blocker: dict[str, Any] | None = None
    retryable: bool = False
    external_calls: int = 0
    input_fingerprint: str | None = None
    output_fingerprint: str | None = None
    next_action: str | None = None


StageRunner = Callable[["EpisodeContext", StageSpec, str], StageExecutionResult]


@dataclass
class EpisodeContext:
    project_root: Path
    definition: dict[str, Any]
    manifest: dict[str, Any]
    output_root: Path
    allow_external: bool = False
    confirm_live: bool = False
    dry_run: bool = False


def default_episode_definition(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema_version": EPISODE_DEFINITION_SCHEMA,
        "episode_id": "episode-example",
        "series_id": "series-example",
        "title": "Untitled episode",
        "working_title": "Untitled episode",
        "language": "ar",
        "target_duration_minutes": 22,
        "minimum_duration_minutes": 18,
        "maximum_duration_minutes": 25,
        "subject": "",
        "central_question": "",
        "intended_audience": "general",
        "historical_scope": {},
        "geographical_scope": {},
        "religious_sensitivity": "HUMAN_REVIEW_REQUIRED",
        "source_package": {"path": "", "approval_status": "NOT_REQUESTED"},
        "requested_outputs": ["render_manifest", "subtitles", "video"],
        "production_profile": "DOCUMENTARY_STANDARD_V1",
        "human_approval_policy": {"required_gates": ["source_adjudication", "script_approval", "religious_safety_approval", "storyboard_approval", "master_visual_approval", "final_render_approval", "publication_approval"]},
        "external_provider_policy": {"default_allowed": False, "explicit_live_confirmation_required": True, "provider_configured": False, "credential_present": False, "disclosure_permitted": False, "request_limit_available": False, "quota_policy_valid": False, "stage_permissions": {}},
        "generated_video_policy": {"maximum_final_generated_video_seconds": 300, "allowed_models": ["VEO_3_1_LITE_1080P", "VEO_3_1_FAST_1080P"], "allocation_owner": "STORYBOARD_WRITER", "enforcement_owner": "VIDEO_POLICY_GUARD", "final_approval_required": True},
        "created_at": "", "updated_at": "",
    }
    value.update(overrides)
    return value


def validate_episode_definition(value: dict[str, Any]) -> list[str]:
    required = {"schema_version", "episode_id", "series_id", "title", "working_title", "language", "target_duration_minutes", "minimum_duration_minutes", "maximum_duration_minutes", "subject", "central_question", "intended_audience", "historical_scope", "geographical_scope", "religious_sensitivity", "source_package", "requested_outputs", "production_profile", "human_approval_policy", "external_provider_policy", "generated_video_policy", "created_at", "updated_at"}
    errors: list[str] = []
    if value.get("schema_version") != EPISODE_DEFINITION_SCHEMA:
        errors.append("EPISODE_DEFINITION_SCHEMA_INVALID")
    errors.extend(f"EPISODE_DEFINITION_FIELD_MISSING:{name}" for name in sorted(required - set(value)))
    for key in ("episode_id", "series_id", "title", "working_title", "language"):
        if not isinstance(value.get(key), str) or not str(value.get(key)).strip():
            errors.append(f"EPISODE_DEFINITION_FIELD_INVALID:{key}")
    minimum, target, maximum = (value.get("minimum_duration_minutes"), value.get("target_duration_minutes"), value.get("maximum_duration_minutes"))
    if not all(isinstance(item, (int, float)) and item > 0 for item in (minimum, target, maximum)) or not (minimum <= target <= maximum):
        errors.append("EPISODE_DURATION_POLICY_INVALID")
    video_policy = value.get("generated_video_policy")
    if not isinstance(video_policy, dict):
        errors.append("GENERATED_VIDEO_POLICY_INVALID")
    else:
        maximum_video_seconds = video_policy.get("maximum_final_generated_video_seconds")
        if not isinstance(maximum_video_seconds, (int, float)) or isinstance(maximum_video_seconds, bool) or maximum_video_seconds < 0 or maximum_video_seconds > 300:
            errors.append("POLICY_VALIDATION_ERROR:MAXIMUM_FINAL_GENERATED_VIDEO_SECONDS")
        allowed_models = video_policy.get("allowed_models")
        if not isinstance(allowed_models, list) or not allowed_models or any(model not in ALLOWED_VIDEO_MODELS for model in allowed_models):
            errors.append("POLICY_VALIDATION_ERROR:VIDEO_MODEL_NOT_ALLOWED")
        if video_policy.get("allocation_owner") != "STORYBOARD_WRITER":
            errors.append("POLICY_VALIDATION_ERROR:VIDEO_ALLOCATION_OWNER")
        if video_policy.get("enforcement_owner") != "VIDEO_POLICY_GUARD":
            errors.append("POLICY_VALIDATION_ERROR:VIDEO_ENFORCEMENT_OWNER")
        if video_policy.get("final_approval_required") is not True:
            errors.append("POLICY_VALIDATION_ERROR:VIDEO_FINAL_APPROVAL_REQUIRED")
    outputs = value.get("requested_outputs")
    if not isinstance(outputs, list) or not all(isinstance(item, str) and item for item in outputs):
        errors.append("REQUESTED_OUTPUTS_INVALID")
    elif unknown := sorted(set(outputs) - KNOWN_REQUESTED_OUTPUTS):
        errors.append(f"REQUESTED_OUTPUT_UNKNOWN:{','.join(unknown)}")
    return errors


def validate_generated_video_allocation(seconds: int | float, policy: dict[str, Any], *, model: str | None = None) -> list[str]:
    """Validate a storyboard-owned allocation; orchestration never truncates it."""
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds < 0:
        return ["POLICY_VALIDATION_ERROR:VIDEO_SECONDS_INVALID"]
    maximum = policy.get("maximum_final_generated_video_seconds")
    if not isinstance(maximum, (int, float)) or isinstance(maximum, bool) or maximum < 0 or maximum > 300:
        return ["POLICY_VALIDATION_ERROR:MAXIMUM_FINAL_GENERATED_VIDEO_SECONDS"]
    if model is not None and model not in policy.get("allowed_models", []):
        return ["POLICY_VALIDATION_ERROR:VIDEO_MODEL_NOT_ALLOWED"]
    return ["POLICY_VALIDATION_ERROR:GENERATED_VIDEO_SECONDS_EXCEEDED"] if seconds > maximum else []


def load_episode_definition(path: Path) -> dict[str, Any]:
    definition = _read_json(path)
    errors = validate_episode_definition(definition)
    if errors:
        raise ValueError(";".join(errors))
    return definition


def build_default_stage_registry() -> tuple[StageSpec, ...]:
    return (
        StageSpec("source_package", "Source package", "1", 10, "source_package_contract", ("episode-definition-v1",), ("source-package",), human_approval_required=True, current_implementation_status="CONTRACT_ONLY"),
        StageSpec("evidence_knowledge", "Evidence and knowledge", "1", 20, None, ("source-package",), ("evidence-ledger", "assessment"), dependencies=("source_package",), current_implementation_status="DISCONNECTED"),
        StageSpec("narrative_script", "Narrative script", "1", 30, None, ("evidence-ledger", "assessment"), ("approved-script",), dependencies=("evidence_knowledge",), current_implementation_status="DISCONNECTED"),
        StageSpec("script_approval", "Script approval", "1", 40, "human_approval_gate", ("approved-script",), dependencies=("narrative_script",), human_approval_required=True, current_implementation_status="ORCHESTRATOR_GATE"),
        StageSpec("production_tts", "Production TTS", "1", 50, "external_tts_adapter", ("approved-script",), ("mastered-wav",), dependencies=("script_approval",), external_provider_required=True, retry_policy="POLICY_GUARDED", current_implementation_status="DISCONNECTED"),
        StageSpec("subtitles", "Subtitle generation", "1", 60, "subtitles_v1", ("mastered-wav", "approved-script"), ("srt", "vtt", "ass"), dependencies=("production_tts",), current_implementation_status="DISCONNECTED"),
        StageSpec("storyboard", "Storyboard generation", "1", 70, "storyboard_generator_v1", ("subtitles",), ("storyboard", "episode-render-manifest"), dependencies=("subtitles",), current_implementation_status="DISCONNECTED"),
        StageSpec("storyboard_approval", "Storyboard approval", "1", 80, "human_approval_gate", ("storyboard",), dependencies=("storyboard",), human_approval_required=True, current_implementation_status="ORCHESTRATOR_GATE"),
        StageSpec("visual_provider", "Visual provider", "1", 90, "visual_provider_v1", ("storyboard",), ("visual-assets",), dependencies=("storyboard_approval",), external_provider_required=True, retry_policy="POLICY_GUARDED", current_implementation_status="IMPLEMENTATION_COMPLETED_LIVE_VALIDATION_DEFERRED"),
        StageSpec("master_visual_approval", "Master visual approval", "1", 100, "human_approval_gate", ("visual-assets",), dependencies=("visual_provider",), human_approval_required=True, current_implementation_status="ORCHESTRATOR_GATE"),
        StageSpec("render", "Render", "1", 110, "render_adapter_v2", ("episode-render-manifest", "visual-assets", "mastered-wav", "subtitles"), ("rendered-video", "render-verification"), dependencies=("master_visual_approval", "production_tts", "subtitles"), current_implementation_status="DISCONNECTED"),
        StageSpec("final_render_approval", "Final render approval", "1", 120, "human_approval_gate", ("rendered-video", "render-verification"), dependencies=("render",), human_approval_required=True, current_implementation_status="ORCHESTRATOR_GATE"),
        StageSpec("publication", "Publication approval", "1", 130, "human_approval_gate", ("rendered-video",), dependencies=("final_render_approval",), human_approval_required=True, current_implementation_status="CONTRACT_ONLY"),
    )


def build_dependency_graph(registry: tuple[StageSpec, ...]) -> dict[str, Any]:
    ids = {stage.stage_id for stage in registry}
    if len(ids) != len(registry):
        raise ValueError("STAGE_REGISTRY_DUPLICATE_ID")
    missing = sorted({dependency for stage in registry for dependency in stage.dependencies + stage.optional_dependencies if dependency not in ids})
    if missing:
        raise ValueError(f"STAGE_DEPENDENCY_UNKNOWN:{','.join(missing)}")
    graph = {stage.stage_id: list(stage.dependencies) for stage in registry}
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(stage_id: str) -> None:
        if stage_id in visiting:
            raise ValueError("STAGE_DEPENDENCY_CYCLE")
        if stage_id in visited:
            return
        visiting.add(stage_id)
        for dependency in graph[stage_id]:
            visit(dependency)
        visiting.remove(stage_id)
        visited.add(stage_id)
    for stage_id in sorted(graph):
        visit(stage_id)
    dependents = {stage.stage_id: [] for stage in registry}
    for stage in registry:
        for dependency in stage.dependencies:
            dependents[dependency].append(stage.stage_id)
    return {"schema_version": DEPENDENCY_GRAPH_SCHEMA, "nodes": [stage.stage_id for stage in registry], "dependencies": graph, "dependents": {key: sorted(value) for key, value in dependents.items()}, "parallel_candidates": [], "concurrency_enabled": False}


def classify_orchestration_error(code: str) -> dict[str, Any]:
    retryable = code in {"QUOTA_EXHAUSTED", "RATE_LIMITED", "PROVIDER_UNAVAILABLE", "TRANSIENT_PROVIDER_ERROR"}
    mapping = {
        "VALIDATION_ERROR": (False, True, True, "Correct the definition or contract."),
        "MISSING_INPUT": (False, True, True, "Provide the missing input artifact."),
        "DEPENDENCY_BLOCKED": (False, True, True, "Resolve the dependency first."),
        "HUMAN_APPROVAL_REQUIRED": (False, False, True, "Record an explicit human decision."),
        "EXTERNAL_CONFIRMATION_REQUIRED": (False, False, True, "Use explicit provider confirmation."),
        "NOT_IMPLEMENTED": (False, False, True, "Integrate an approved runner before retrying."),
        "CONTRACT_MISMATCH": (False, True, True, "Repair the contract or adapter."),
        "OUTPUT_INVALID": (False, True, True, "Regenerate or repair the output."),
        "INTERNAL_ERROR": (False, True, True, "Inspect the local execution record."),
    }
    values = mapping.get(code, (retryable, retryable, True, "Retry only when the provider condition is resolved."))
    return {"code": code, "retryable": values[0], "blocks_episode": values[1], "blocks_dependents": values[2], "suggested_action": values[3], "safe_message": code}


def external_provider_preflight(policy: dict[str, Any], *, stage_id: str | None = None) -> list[str]:
    """Return policy deficiencies without reading or exposing credentials."""
    required = ("provider_configured", "credential_present", "disclosure_permitted", "request_limit_available", "quota_policy_valid")
    missing = [name.upper() + "_REQUIRED" for name in required if policy.get(name) is not True]
    if stage_id is not None:
        permissions = policy.get("stage_permissions")
        if not isinstance(permissions, dict) or permissions.get(stage_id) is not True:
            missing.append(f"STAGE_PERMISSION_REQUIRED:{stage_id}")
    return missing


class EpisodeOrchestrator:
    def __init__(self, project_root: Path, definition: dict[str, Any], *, output_root: Path | None = None, registry: tuple[StageSpec, ...] | None = None, runners: dict[str, StageRunner] | None = None) -> None:
        errors = validate_episode_definition(definition)
        if errors:
            raise ValueError(";".join(errors))
        self.project_root = project_root.resolve()
        self.definition = definition
        self.output_root = (output_root or self.project_root / "working" / "episode-orchestrator-v1").resolve()
        self.registry = tuple(sorted(registry or build_default_stage_registry(), key=lambda item: (item.stage_order, item.stage_id)))
        self.graph = build_dependency_graph(self.registry)
        self.runners = dict(runners or {})
        self._validate_registry_adapters()
        self.manifest_path = self.output_root / "episode-orchestration-manifest-v1.json"

    def _validate_registry_adapters(self) -> None:
        for stage in self.registry:
            if not stage.current_implementation_status.startswith(AVAILABLE_IMPLEMENTATION_PREFIX):
                continue
            has_callable_runner = stage.stage_id in self.runners or stage.runner == "source_package_contract"
            if not stage.runner or not has_callable_runner:
                raise ValueError(f"AVAILABLE_STAGE_RUNNER_REQUIRED:{stage.stage_id}")

    def _stage_input_fingerprint(self, stage: StageSpec, states: dict[str, Any]) -> str:
        dependencies = {dependency: states.get(dependency, {}).get("output_fingerprint") for dependency in stage.dependencies}
        definition_inputs: dict[str, Any] = {
            "episode_id": self.definition.get("episode_id"),
            "series_id": self.definition.get("series_id"),
            "language": self.definition.get("language"),
            "production_profile": self.definition.get("production_profile"),
        }
        if stage.stage_id in {"source_package", "evidence_knowledge"}:
            definition_inputs["source_package"] = self.definition.get("source_package")
        if stage.stage_id == "narrative_script":
            definition_inputs["narrative"] = {
                key: self.definition.get(key)
                for key in ("title", "working_title", "subject", "central_question", "intended_audience", "historical_scope", "geographical_scope", "religious_sensitivity")
            }
        if stage.external_provider_required:
            definition_inputs["external_provider_policy"] = self.definition.get("external_provider_policy")
        if stage.stage_id in {"storyboard", "visual_provider"}:
            definition_inputs["generated_video_policy"] = self.definition.get("generated_video_policy")
        return _fingerprint({"definition_inputs": definition_inputs, "stage": asdict(stage), "dependencies": dependencies})

    def _new_stage_state(self, stage: StageSpec, states: dict[str, Any]) -> dict[str, Any]:
        return {"stage_id": stage.stage_id, "status": "NOT_STARTED", "dependency_status": [], "attempts": 0, "latest_run_id": None, "input_fingerprint": self._stage_input_fingerprint(stage, states), "output_fingerprint": None, "started_at": None, "completed_at": None, "outputs": [], "warnings": [], "errors": [], "blocker": None, "next_action": None, "human_approval": "NOT_REQUESTED", "external_request_count": 0, "cache_status": "MISS"}

    def _load_or_create_manifest(self) -> dict[str, Any]:
        if self.manifest_path.is_file():
            manifest = _read_json(self.manifest_path)
            if manifest.get("schema_version") == ORCHESTRATION_MANIFEST_SCHEMA and manifest.get("episode_id") == self.definition["episode_id"]:
                return manifest
        states: dict[str, Any] = {}
        for stage in self.registry:
            states[stage.stage_id] = self._new_stage_state(stage, states)
        now = _utc_now()
        return {"schema_version": ORCHESTRATION_MANIFEST_SCHEMA, "episode_id": self.definition["episode_id"], "orchestrator_version": ORCHESTRATOR_VERSION, "run_id": None, "status": "CREATED", "started_at": None, "updated_at": now, "completed_at": None, "current_stage": None, "next_action": "Build an execution plan.", "stage_registry": [asdict(stage) for stage in self.registry], "stage_states": states, "dependency_graph": self.graph, "approvals": [], "blockers": [], "deferred_items": [], "warnings": [], "errors": [], "input_fingerprint": _fingerprint(self.definition), "configuration_fingerprint": _fingerprint([asdict(stage) for stage in self.registry]), "artifact_index": [], "execution_history": [], "resume_metadata": {"resumable": True, "last_resumable_stage": None}, "final_readiness": "NOT_READY"}

    def _approval_for(self, manifest: dict[str, Any], stage_id: str) -> dict[str, Any] | None:
        entries = [item for item in manifest.get("approvals", []) if item.get("stage_id") == stage_id]
        return entries[-1] if entries else None

    def _visual_provider_blocker(self) -> dict[str, Any] | None:
        report = self.project_root / "working" / "visual-provider-v1" / "production-visual-quota-report-v1.json"
        if report.is_file():
            try:
                value = _read_json(report)
                code = str(value.get("provider_error_code") or value.get("quota_status") or "")
                if code in TRANSIENT_EXTERNAL_ERRORS:
                    return {"code": code, "retryable": True, "prior_work_preserved": True, "next_action": "Retry after quota availability or paid-tier activation."}
            except (OSError, ValueError):
                pass
        return {"code": "IMPLEMENTATION_COMPLETED_LIVE_VALIDATION_DEFERRED", "retryable": True, "prior_work_preserved": True, "next_action": "Run a separately confirmed VisualProvider request when external policy allows."}

    def _refresh_states(self, manifest: dict[str, Any], *, allow_external: bool, confirm_live: bool) -> None:
        states = manifest["stage_states"]
        for stage in self.registry:
            state = states.setdefault(stage.stage_id, self._new_stage_state(stage, states))
            expected = self._stage_input_fingerprint(stage, states)
            if state.get("status") in COMPLETED_STATUSES and state.get("input_fingerprint") != expected:
                self._mark_stale(manifest, stage.stage_id, "INPUT_FINGERPRINT_CHANGED")
            state = states[stage.stage_id]
            if state.get("status") == "PERMANENT_FAILURE":
                continue
            if state.get("status") in COMPLETED_STATUSES and state.get("input_fingerprint") == expected:
                state["cache_status"] = "HIT"
                continue
            dependency_status = [{"stage_id": dependency, "status": states[dependency].get("status")} for dependency in stage.dependencies]
            state["dependency_status"] = dependency_status
            unmet = [item for item in dependency_status if item["status"] not in COMPLETED_STATUSES]
            if stage.stage_id == "visual_provider":
                blocker = self._visual_provider_blocker()
                if blocker and blocker["code"] in TRANSIENT_EXTERNAL_ERRORS:
                    state.update({"status": "BLOCKED_BY_EXTERNAL_PROVIDER", "blocker": blocker, "next_action": blocker["next_action"], "cache_status": "TRANSIENT_FAILURE_RETRYABLE"})
                    continue
            if unmet:
                state.update({"status": "BLOCKED_BY_DEPENDENCY", "blocker": {"code": "DEPENDENCY_BLOCKED", "dependencies": unmet}, "next_action": "Complete required dependencies first."})
                continue
            if stage.human_approval_required and stage.stage_id != "source_package":
                approval = self._approval_for(manifest, stage.stage_id)
                if approval and approval.get("status") in {"APPROVED", "APPROVED_WITH_NOTES"}:
                    indexed = {item.get("artifact_id"): item for item in manifest.get("artifact_index", [])}
                    approval_artifacts_match = all(
                        indexed.get(artifact_id, {}).get("fingerprint") == fingerprint
                        for artifact_id, fingerprint in approval.get("artifact_fingerprints", {}).items()
                    )
                    if approval.get("input_fingerprint") != expected or not approval_artifacts_match:
                        approval["status"] = "STALE"
                if approval and approval.get("status") in {"APPROVED", "APPROVED_WITH_NOTES"}:
                    state.update({
                        "status": "COMPLETED",
                        "human_approval": approval["status"],
                        "completed_at": approval.get("resolved_at") or _utc_now(),
                        "input_fingerprint": expected,
                        "output_fingerprint": _fingerprint({"approval_id": approval.get("approval_id"), "decision": approval.get("decision"), "artifact_ids": approval.get("artifact_ids", [])}),
                        "cache_status": "HIT",
                    })
                    continue
                if approval and approval.get("status") == "REJECTED":
                    state.update({"status": "BLOCKED_BY_HUMAN_APPROVAL", "human_approval": "REJECTED", "blocker": {"code": "HUMAN_REJECTION"}, "next_action": "Revise the artifact; human rejection never triggers provider fallback."})
                    continue
                state.update({"status": "BLOCKED_BY_HUMAN_APPROVAL", "human_approval": "PENDING", "blocker": {"code": "HUMAN_APPROVAL_REQUIRED"}, "next_action": "Record an explicit approval decision."})
                continue
            if stage.external_provider_required:
                if not (allow_external and confirm_live):
                    state.update({"status": "BLOCKED_BY_EXTERNAL_PROVIDER", "blocker": {"code": "EXTERNAL_CONFIRMATION_REQUIRED", "retryable": True}, "next_action": "Use --allow-external and --confirm-live only for an approved provider operation."})
                    continue
                policy_errors = external_provider_preflight(self.definition.get("external_provider_policy", {}), stage_id=stage.stage_id)
                if policy_errors:
                    state.update({"status": "BLOCKED_BY_EXTERNAL_PROVIDER", "blocker": {"code": "EXTERNAL_PROVIDER_POLICY_INCOMPLETE", "requirements": policy_errors, "retryable": True}, "next_action": "Complete provider configuration, credential, disclosure, request-limit and quota-policy checks."})
                    continue
            if stage.current_implementation_status in {"DISCONNECTED", "CONTRACT_ONLY"} and stage.runner != "source_package_contract":
                state.update({"status": "NOT_IMPLEMENTED", "blocker": {"code": "NOT_IMPLEMENTED"}, "next_action": "Integrate a canonical episode-level adapter before execution."})
                continue
            if stage.stage_id == "source_package":
                source = self.definition.get("source_package", {})
                source_path = source.get("path") if isinstance(source, dict) else None
                try:
                    source_exists = isinstance(source_path, str) and bool(source_path) and _path_within_project(self.project_root, source_path).is_file()
                except ValueError:
                    source_exists = False
                if not source_exists:
                    state.update({"status": "BLOCKED_BY_DEPENDENCY", "blocker": {"code": "MISSING_INPUT", "input": "source_package.path"}, "next_action": "Provide an approved source package file."})
                    continue
                if source.get("approval_status") not in {"APPROVED", "APPROVED_WITH_NOTES"}:
                    state.update({"status": "BLOCKED_BY_HUMAN_APPROVAL", "human_approval": "PENDING", "blocker": {"code": "HUMAN_APPROVAL_REQUIRED", "approval": "source_adjudication"}, "next_action": "Approve the source package before episode execution."})
                    continue
            state.update({"status": "READY", "blocker": None, "next_action": "Run this stage.", "input_fingerprint": expected, "cache_status": "MISS"})
        self._derive_episode_status(manifest)

    def _derive_episode_status(self, manifest: dict[str, Any]) -> None:
        states = manifest["stage_states"]
        ordered = [(stage, states[stage.stage_id]) for stage in self.registry]
        values = [state.get("status") for _, state in ordered]
        if all(value in COMPLETED_STATUSES for value in values):
            status, readiness = "COMPLETED", "READY_FOR_PUBLICATION"
        elif any(value == "PERMANENT_FAILURE" for value in values):
            status, readiness = "FAILED", "NOT_READY"
        elif states.get("publication", {}).get("status") == "BLOCKED_BY_HUMAN_APPROVAL" and states.get("final_render_approval", {}).get("status") in COMPLETED_STATUSES:
            status, readiness = "READY_FOR_PUBLICATION", "READY_FOR_PUBLICATION"
        elif states.get("render", {}).get("status") == "READY" and all(states[dependency].get("status") in COMPLETED_STATUSES for dependency in self.graph["dependencies"].get("render", [])):
            status, readiness = "READY_FOR_RENDER", "READY_FOR_RENDER"
        elif any(value == "RUNNING" for value in values):
            status, readiness = "IN_PROGRESS", "NOT_READY"
        else:
            first_unresolved = next((state for _, state in ordered if state.get("status") not in COMPLETED_STATUSES), None)
            first_status = first_unresolved.get("status") if first_unresolved else "CREATED"
            completed_any = any(value in COMPLETED_STATUSES for value in values)
            ready_any = any(value == "READY" for value in values)
            if first_status == "BLOCKED_BY_HUMAN_APPROVAL":
                status, readiness = "WAITING_FOR_HUMAN_APPROVAL", "NOT_READY"
            elif first_status == "BLOCKED_BY_EXTERNAL_PROVIDER":
                status, readiness = "WAITING_FOR_EXTERNAL_PROVIDER", "PARTIALLY_READY" if completed_any else "NOT_READY"
            elif first_status in {"NOT_IMPLEMENTED", "DEFERRED", "STALE"}:
                status, readiness = ("PARTIALLY_COMPLETED", "NOT_READY") if completed_any else ("PLANNING", "NOT_READY")
            elif completed_any and ready_any:
                status, readiness = "IN_PROGRESS", "NOT_READY"
            elif completed_any:
                status, readiness = "PARTIALLY_COMPLETED", "NOT_READY"
            elif ready_any:
                status, readiness = "PLANNING", "NOT_READY"
            else:
                status, readiness = "CREATED", "NOT_READY"
        manifest["status"], manifest["final_readiness"] = status, readiness
        manifest["current_stage"] = next((stage.stage_id for stage in self.registry if states[stage.stage_id].get("status") == "READY"), None)
        manifest["next_action"] = states[manifest["current_stage"]]["next_action"] if manifest["current_stage"] else "Resolve the recorded blocker or approval gate."

    def _mark_stale(self, manifest: dict[str, Any], stage_id: str, reason: str) -> None:
        descendants: list[str] = [stage_id]
        cursor = 0
        while cursor < len(descendants):
            current = descendants[cursor]
            descendants.extend(item for item in manifest["dependency_graph"]["dependents"].get(current, []) if item not in descendants)
            cursor += 1
        for item in descendants:
            state = manifest["stage_states"][item]
            if state.get("status") in COMPLETED_STATUSES or item == stage_id:
                state.update({"status": "STALE", "warnings": sorted(set(state.get("warnings", []) + [f"STALE:{reason}"])), "next_action": "Re-run or re-validate after upstream change.", "cache_status": "STALE"})
        for approval in manifest.get("approvals", []):
            if approval.get("stage_id") in descendants and approval.get("status") in {"APPROVED", "APPROVED_WITH_NOTES"}:
                approval["status"] = "STALE"

    def _contract_runner(self, context: EpisodeContext, stage: StageSpec, run_id: str) -> StageExecutionResult:
        source = context.definition["source_package"]
        try:
            path = _path_within_project(context.project_root, str(source["path"]))
        except ValueError:
            return StageExecutionResult(stage.stage_id, run_id, "BLOCKED_BY_DEPENDENCY", blocker={"code": "MISSING_INPUT", "input": "source_package.path"}, next_action="Provide an approved source package file inside project root.")
        if not path.is_file():
            return StageExecutionResult(stage.stage_id, run_id, "BLOCKED_BY_DEPENDENCY", blocker={"code": "MISSING_INPUT", "input": "source_package.path"}, next_action="Provide an approved source package file.")
        output = {"artifact_id": f"source-package:{context.definition['episode_id']}", "artifact_type": "source_package", "stage_id": stage.stage_id, "path": _normalise_project_path(context.project_root, str(path)), "schema_version": "EXTERNAL_OR_EXISTING", "fingerprint": sha256(path.read_bytes()).hexdigest(), "created_at": _utc_now(), "status": "COMPLETED", "approval_status": source.get("approval_status", "NOT_REQUESTED"), "source_artifact_ids": [], "supersedes": None, "runtime_only": False, "git_trackable": False}
        return StageExecutionResult(stage.stage_id, run_id, "COMPLETED", outputs=(output,), output_fingerprint=output["fingerprint"], next_action="Run the next ready stage.")

    def _run_stage(self, manifest: dict[str, Any], stage: StageSpec, run_id: str, *, allow_external: bool, confirm_live: bool) -> StageExecutionResult:
        state = manifest["stage_states"][stage.stage_id]
        if state.get("status") != "READY":
            return StageExecutionResult(stage.stage_id, run_id, state.get("status", "NOT_STARTED"), blocker=state.get("blocker"), retryable=state.get("status") in {"RETRYABLE_FAILURE", "BLOCKED_BY_EXTERNAL_PROVIDER"}, next_action=state.get("next_action"))
        context = EpisodeContext(self.project_root, self.definition, manifest, self.output_root, allow_external, confirm_live)
        prior_outputs = list(state.get("outputs", []))
        prior_output_fingerprint = state.get("output_fingerprint")
        state.update({"status": "RUNNING", "started_at": _utc_now(), "attempts": int(state.get("attempts", 0)) + 1, "latest_run_id": run_id})
        runner = self.runners.get(stage.stage_id)
        if runner is None and stage.runner == "source_package_contract":
            runner = self._contract_runner
        if runner is None:
            result = StageExecutionResult(stage.stage_id, run_id, "NOT_IMPLEMENTED", blocker={"code": "NOT_IMPLEMENTED"}, next_action="Integrate a canonical stage adapter.")
        else:
            result = runner(context, stage, run_id)
        resolved_outputs = list(result.outputs) if result.outputs else prior_outputs
        resolved_output_fingerprint = result.output_fingerprint or (_fingerprint(result.outputs) if result.outputs else prior_output_fingerprint)
        state.update({"status": result.status, "completed_at": _utc_now() if result.status in COMPLETED_STATUSES else None, "outputs": resolved_outputs, "warnings": list(result.warnings), "errors": list(result.errors), "blocker": result.blocker, "next_action": result.next_action, "external_request_count": int(state.get("external_request_count", 0)) + result.external_calls, "input_fingerprint": result.input_fingerprint or state["input_fingerprint"], "output_fingerprint": resolved_output_fingerprint, "cache_status": "MISS"})
        self._index_artifacts(manifest, result.outputs)
        if result.status in COMPLETED_STATUSES:
            self._mark_stale_dependents_if_output_changed(manifest, stage.stage_id, state.get("output_fingerprint"))
        return result

    def _mark_stale_dependents_if_output_changed(self, manifest: dict[str, Any], stage_id: str, output_fingerprint: str | None) -> None:
        state = manifest["stage_states"][stage_id]
        previous = state.get("previous_output_fingerprint")
        state["previous_output_fingerprint"] = output_fingerprint
        if previous and output_fingerprint and previous != output_fingerprint:
            for dependent in manifest["dependency_graph"]["dependents"].get(stage_id, []):
                self._mark_stale(manifest, dependent, "UPSTREAM_OUTPUT_FINGERPRINT_CHANGED")

    def _index_artifacts(self, manifest: dict[str, Any], artifacts: tuple[dict[str, Any], ...]) -> None:
        index = {str(item.get("artifact_id")): item for item in manifest.get("artifact_index", [])}
        for artifact in artifacts:
            missing = ARTIFACT_REQUIRED_FIELDS - set(artifact)
            if missing:
                raise ValueError(f"ARTIFACT_FIELD_MISSING:{','.join(sorted(missing))}")
            artifact_id = str(artifact.get("artifact_id", ""))
            if not artifact_id:
                raise ValueError("ARTIFACT_ID_REQUIRED")
            if artifact.get("stage_id") not in manifest["stage_states"]:
                raise ValueError("ARTIFACT_STAGE_UNKNOWN")
            if not isinstance(artifact.get("path"), str) or not artifact["path"]:
                raise ValueError("ARTIFACT_PATH_INVALID")
            normalised = dict(artifact)
            normalised["path"] = _normalise_project_path(self.project_root, artifact["path"])
            if not isinstance(normalised.get("runtime_only"), bool) or not isinstance(normalised.get("git_trackable"), bool):
                raise ValueError("ARTIFACT_TRACKING_FLAGS_INVALID")
            if normalised["runtime_only"] and normalised["git_trackable"]:
                raise ValueError("RUNTIME_ARTIFACT_CANNOT_BE_GIT_TRACKABLE")
            if not isinstance(normalised.get("source_artifact_ids"), list):
                raise ValueError("ARTIFACT_LINEAGE_INVALID")
            if normalised.get("supersedes") is not None and not isinstance(normalised.get("supersedes"), str):
                raise ValueError("ARTIFACT_SUPERSEDES_INVALID")
            existing = index.get(artifact_id)
            if existing and existing.get("fingerprint") != normalised.get("fingerprint"):
                raise ValueError(f"ARTIFACT_ID_DUPLICATE:{artifact_id}")
            index[artifact_id] = normalised
        manifest["artifact_index"] = [index[key] for key in sorted(index)]

    def _persist(self, manifest: dict[str, Any]) -> None:
        manifest["updated_at"] = _utc_now()
        self.output_root.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self.manifest_path, manifest)
        _atomic_write_json(self.output_root / "episode-stage-registry-v1.json", {"schema_version": STAGE_REGISTRY_SCHEMA, "stages": [asdict(stage) for stage in self.registry]})
        _atomic_write_json(self.output_root / "episode-dependency-graph-v1.json", manifest["dependency_graph"])
        _atomic_write_json(self.output_root / "episode-artifact-index-v1.json", {"schema_version": ARTIFACT_INDEX_SCHEMA, "episode_id": self.definition["episode_id"], "artifacts": manifest["artifact_index"]})
        _atomic_write_json(self.output_root / "episode-status-report-v1.json", {"schema_version": STATUS_REPORT_SCHEMA, "episode_id": self.definition["episode_id"], "status": manifest["status"], "current_stage": manifest["current_stage"], "next_action": manifest["next_action"], "blockers": [state.get("blocker") for state in manifest["stage_states"].values() if state.get("blocker")], "deferred_items": manifest.get("deferred_items", [])})

    def build_plan(self, *, mode: str = "plan", stages: tuple[str, ...] = (), allow_external: bool = False, confirm_live: bool = False) -> dict[str, Any]:
        if mode not in VALID_MODES:
            raise ValueError("ORCHESTRATOR_MODE_INVALID")
        manifest = self._load_or_create_manifest()
        self._refresh_states(manifest, allow_external=allow_external, confirm_live=confirm_live)
        wanted = set(stages) if stages else {stage.stage_id for stage in self.registry}
        if unknown := wanted - {stage.stage_id for stage in self.registry}:
            raise ValueError(f"ORCHESTRATOR_STAGE_UNKNOWN:{','.join(sorted(unknown))}")
        state_values = manifest["stage_states"]
        plan = {"schema_version": EXECUTION_PLAN_SCHEMA, "episode_id": self.definition["episode_id"], "requested_mode": mode, "stages_requested": [stage.stage_id for stage in self.registry if stage.stage_id in wanted], "stages_ready": [stage.stage_id for stage in self.registry if stage.stage_id in wanted and state_values[stage.stage_id]["status"] == "READY"], "stages_cached": [stage.stage_id for stage in self.registry if stage.stage_id in wanted and state_values[stage.stage_id].get("cache_status") == "HIT"], "stages_blocked": [{"stage_id": stage.stage_id, "blocker": state_values[stage.stage_id].get("blocker")} for stage in self.registry if stage.stage_id in wanted and state_values[stage.stage_id]["status"].startswith("BLOCKED")], "stages_deferred": [stage.stage_id for stage in self.registry if stage.stage_id in wanted and state_values[stage.stage_id]["status"] == "DEFERRED"], "stages_not_implemented": [stage.stage_id for stage in self.registry if stage.stage_id in wanted and state_values[stage.stage_id]["status"] == "NOT_IMPLEMENTED"], "external_calls_required": [stage.stage_id for stage in self.registry if stage.stage_id in wanted and stage.external_provider_required and state_values[stage.stage_id]["status"] == "READY"], "human_approvals_required": [stage.stage_id for stage in self.registry if stage.stage_id in wanted and state_values[stage.stage_id]["status"] == "BLOCKED_BY_HUMAN_APPROVAL"], "expected_outputs": {stage.stage_id: list(stage.produced_files) for stage in self.registry if stage.stage_id in wanted}, "execution_order": [stage.stage_id for stage in self.registry if stage.stage_id in wanted], "reasons": {stage.stage_id: state_values[stage.stage_id].get("next_action") for stage in self.registry if stage.stage_id in wanted}}
        manifest["run_id"] = str(uuid4())
        manifest["execution_history"].append({"run_id": manifest["run_id"], "mode": mode, "created_at": _utc_now(), "dry_run": mode == "plan", "stages": plan["stages_requested"]})
        self._persist(manifest)
        _atomic_write_json(self.output_root / "episode-execution-plan-v1.json", plan)
        return {"plan": plan, "manifest": manifest}

    def execute(self, *, mode: str, stage_id: str | None = None, allow_external: bool = False, confirm_live: bool = False, dry_run: bool = False) -> dict[str, Any]:
        if dry_run or mode == "plan":
            return self.build_plan(mode="plan", stages=(stage_id,) if stage_id else (), allow_external=allow_external, confirm_live=confirm_live)
        if mode not in VALID_MODES - {"plan"}:
            raise ValueError("ORCHESTRATOR_MODE_INVALID")
        manifest = self._load_or_create_manifest()
        if mode == "run-stage" and (not stage_id or stage_id not in manifest["stage_states"]):
            raise ValueError("ORCHESTRATOR_STAGE_UNKNOWN")
        self._refresh_states(manifest, allow_external=allow_external, confirm_live=confirm_live)
        if mode == "status":
            self._persist(manifest)
            return {"manifest": manifest, "status": manifest["status"]}
        if mode == "invalidate-stage":
            if not stage_id or stage_id not in manifest["stage_states"]:
                raise ValueError("ORCHESTRATOR_STAGE_REQUIRED")
            self._mark_stale(manifest, stage_id, "MANUAL_INVALIDATION")
            self._refresh_states(manifest, allow_external=allow_external, confirm_live=confirm_live)
            self._persist(manifest)
            return {"manifest": manifest, "status": manifest["status"], "invalidated_stage": stage_id}
        candidates = [stage for stage in self.registry if manifest["stage_states"][stage.stage_id]["status"] == "READY"]
        if mode == "run-stage":
            if not stage_id:
                raise ValueError("ORCHESTRATOR_STAGE_REQUIRED")
            candidates = [stage for stage in candidates if stage.stage_id == stage_id]
        if mode in {"run-next", "resume"}:
            candidates = candidates[:1]
        run_id = str(uuid4())
        results: list[StageExecutionResult] = []
        if mode == "run-through":
            while True:
                next_stage = next((stage for stage in self.registry if manifest["stage_states"][stage.stage_id]["status"] == "READY"), None)
                if next_stage is None:
                    break
                result = self._run_stage(manifest, next_stage, run_id, allow_external=allow_external, confirm_live=confirm_live)
                results.append(result)
                self._refresh_states(manifest, allow_external=allow_external, confirm_live=confirm_live)
                if result.status not in COMPLETED_STATUSES:
                    break
                if manifest["status"] in {"WAITING_FOR_HUMAN_APPROVAL", "WAITING_FOR_EXTERNAL_PROVIDER", "FAILED"}:
                    break
        else:
            for stage in candidates:
                results.append(self._run_stage(manifest, stage, run_id, allow_external=allow_external, confirm_live=confirm_live))
                self._refresh_states(manifest, allow_external=allow_external, confirm_live=confirm_live)
        manifest["run_id"] = run_id
        manifest["execution_history"].append({"run_id": run_id, "mode": mode, "created_at": _utc_now(), "dry_run": False, "results": [asdict(item) for item in results]})
        self._persist(manifest)
        return {"manifest": manifest, "results": [asdict(item) for item in results], "status": manifest["status"]}

    def record_approval(self, *, stage_id: str, decision: str, reviewer: str | None = None, notes: str | None = None, artifact_ids: tuple[str, ...] = ()) -> dict[str, Any]:
        stages = {stage.stage_id: stage for stage in self.registry}
        if stage_id not in stages:
            raise ValueError("ORCHESTRATOR_STAGE_UNKNOWN")
        if not stages[stage_id].human_approval_required:
            raise ValueError("APPROVAL_STAGE_NOT_HUMAN_GATE")
        if decision not in {"APPROVED", "APPROVED_WITH_NOTES", "REJECTED"}:
            raise ValueError("APPROVAL_DECISION_INVALID")
        if not isinstance(reviewer, str) or not reviewer.strip():
            raise ValueError("APPROVAL_REVIEWER_REQUIRED")
        if decision == "APPROVED_WITH_NOTES" and (not isinstance(notes, str) or not notes.strip()):
            raise ValueError("APPROVAL_NOTES_REQUIRED")
        manifest = self._load_or_create_manifest()
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("APPROVAL_ARTIFACT_IDS_DUPLICATE")
        indexed = {item.get("artifact_id"): item for item in manifest.get("artifact_index", [])}
        unknown_artifacts = [artifact_id for artifact_id in artifact_ids if artifact_id not in indexed]
        if unknown_artifacts:
            raise ValueError(f"APPROVAL_ARTIFACT_UNKNOWN:{','.join(unknown_artifacts)}")
        approval_input_fingerprint = self._stage_input_fingerprint(stages[stage_id], manifest["stage_states"])
        resolved_at = _utc_now()
        manifest["approvals"].append({"approval_id": str(uuid4()), "stage_id": stage_id, "artifact_ids": list(artifact_ids), "artifact_fingerprints": {artifact_id: indexed[artifact_id]["fingerprint"] for artifact_id in artifact_ids}, "input_fingerprint": approval_input_fingerprint, "status": decision, "reviewer": reviewer.strip(), "notes": notes, "created_at": resolved_at, "resolved_at": resolved_at, "decision": decision})
        self._refresh_states(manifest, allow_external=False, confirm_live=False)
        self._persist(manifest)
        return manifest
