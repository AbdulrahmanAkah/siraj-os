from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from src.application.artifact_dependency_graph_v1 import (
    build_scope_dependency_graph,
)
from src.application.sfx_audio_mix_v1 import inspect_audio_environment
from src.application.structural_montage_final_render_v1 import (
    inspect_montage_environment,
)
from src.application.automatic_qa_partial_repair_v1 import (
    inspect_qa_environment,
)
from src.application.openai_luna_orchestrator_v1 import (
    LunaProviderError,
    LunaResult,
    request_scope_proposal,
)

ORCHESTRATOR_ROOT_REL = Path("projects/_orchestrator")
STATE_NAME = "autonomous-episode-orchestrator-state-v1.json"
PROPOSALS_DIR_NAME = "scope-proposals"
DISCUSSION_NAME = "scope-discussion-v1.json"

ORCHESTRATOR_RELEASE = "SIRAJ_AUTONOMOUS_EPISODE_ORCHESTRATOR_V1"
ProgressCallback = Callable[[str, int | None], None]

FULL_STAGE_ORDER = (
    "TOPIC_AND_EVENT_PROPOSAL",
    "HUMAN_SCOPE_REVIEW",
    "EVIDENCE_RESEARCH",
    "SCRIPT_WRITING",
    "STORYBOARD_AND_MEDIA_PLANNING",
    "BUDGET_PREFLIGHT",
    "RUNWARE_IMAGE_GENERATION",
    "RUNWARE_VIDEO_GENERATION",
    "LOCAL_GRAPHICS_RENDER",
    "ELEVENLABS_TTS",
    "SFX_DESIGN",
    "STRUCTURAL_MONTAGE",
    "AUTOMATIC_QA",
    "HUMAN_FINAL_REVIEW",
    "READY_TO_PUBLISH",
)


class AutonomousOrchestratorError(RuntimeError):
    pass


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AutonomousOrchestratorError(
            f"CANNOT_READ_JSON:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise AutonomousOrchestratorError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _root(repo_root: Path) -> Path:
    return repo_root.resolve() / ORCHESTRATOR_ROOT_REL


def _state_path(repo_root: Path) -> Path:
    return _root(repo_root) / STATE_NAME


def _discussion_path(repo_root: Path) -> Path:
    return _root(repo_root) / DISCUSSION_NAME


def _base_state(repo_root: Path) -> dict[str, Any]:
    return {
        "schema_version": "siraj-autonomous-episode-orchestrator-state-v1",
        "release": ORCHESTRATOR_RELEASE,
        "status": "IDLE_READY_FOR_NEXT_EPISODE",
        "stage": "TOPIC_AND_EVENT_PROPOSAL",
        "full_stage_order": list(FULL_STAGE_ORDER),
        "current_episode_id": None,
        "current_proposal_path_relative": None,
        "current_proposal_version": 0,
        "approved_scope_path_relative": None,
        "dependency_graph_path_relative": None,
        "last_provider_response_id": None,
        "luna_usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "estimated_text_cost_usd": 0.0,
        },
        "active_scope_luna_usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "estimated_text_cost_usd": 0.0,
        },
        "provider_readiness": {
            "openai_luna": "KEY_NOT_CHECKED",
            "runware": "EXISTING_INTEGRATION",
            "elevenlabs": "KEY_NOT_CHECKED",
            "montage": "STRUCTURAL_RUNTIME_PRESENT_UNTESTED",
            "qa": "STRUCTURAL_RUNTIME_PRESENT_UNTESTED",
            "sfx": "STRUCTURAL_RUNTIME_PRESENT_UNTESTED",
        },
        "autonomy_contract": {
            "single_start_command": "PRODUCE_NEXT_EPISODE",
            "human_gates": [
                "HUMAN_SCOPE_REVIEW",
                "HUMAN_FINAL_REVIEW",
            ],
            "automatic_after_scope_approval": True,
            "manual_youtube_upload": True,
            "music": "FORBIDDEN",
            "sound_effects": "ALLOWED_ANY_SCENE_APPROPRIATE_TYPE",
            "episode_cost_hard_cap_usd": 40.0,
            "partial_rebuild_only": True,
            "full_regeneration_for_local_defect": "FORBIDDEN",
        },
        "next_stage": "GENERATE_SCOPE_PROPOSAL_WITH_LUNA",
        "last_error": None,
        "created_at_utc": _now_utc(),
        "updated_at_utc": _now_utc(),
    }


def load_orchestrator_state(repo_root: Path) -> dict[str, Any]:
    path = _state_path(repo_root)
    if not path.is_file():
        state = _base_state(repo_root)
        _atomic_write_json(path, state)
        if not _discussion_path(repo_root).is_file():
            _atomic_write_json(
                _discussion_path(repo_root),
                {
                    "schema_version": "siraj-scope-discussion-v1",
                    "turns": [],
                    "created_at_utc": _now_utc(),
                    "updated_at_utc": _now_utc(),
                },
            )
        return state
    return _read_json(path)


def load_scope_discussion(repo_root: Path) -> dict[str, Any]:
    load_orchestrator_state(repo_root)
    return _read_json(_discussion_path(repo_root))


def current_scope_proposal(repo_root: Path) -> dict[str, Any] | None:
    state = load_orchestrator_state(repo_root)
    relative = state.get("current_proposal_path_relative")
    if not isinstance(relative, str) or not relative:
        return None
    path = repo_root.resolve() / relative
    if not path.is_file():
        raise AutonomousOrchestratorError("CURRENT_PROPOSAL_FILE_MISSING")
    return _read_json(path)


def _append_turn(repo_root: Path, role: str, text: str) -> None:
    path = _discussion_path(repo_root)
    discussion = load_scope_discussion(repo_root)
    turns = discussion.setdefault("turns", [])
    if not isinstance(turns, list):
        raise AutonomousOrchestratorError("DISCUSSION_TURNS_INVALID")
    turns.append(
        {
            "role": role,
            "text": text.strip(),
            "created_at_utc": _now_utc(),
        }
    )
    discussion["updated_at_utc"] = _now_utc()
    _atomic_write_json(path, discussion)


def _proposal_path(repo_root: Path, version: int) -> Path:
    return (
        _root(repo_root)
        / PROPOSALS_DIR_NAME
        / f"episode-scope-proposal-v{version:03d}.json"
    )


def _store_luna_result(
    repo_root: Path,
    state: dict[str, Any],
    result: LunaResult,
) -> dict[str, Any]:
    version = int(state.get("current_proposal_version", 0)) + 1
    proposal = dict(result.payload)
    proposal["schema_version"] = "siraj-episode-scope-proposal-v1"
    proposal["proposal_version"] = version
    proposal["provider"] = "OPENAI"
    proposal["model"] = "gpt-5.6-luna"
    proposal["provider_response_id"] = result.response_id
    proposal["human_approval"] = False
    proposal["created_at_utc"] = _now_utc()
    proposal["proposal_sha256"] = _canonical_sha256(proposal)
    path = _proposal_path(repo_root, version)
    _atomic_write_json(path, proposal)

    usage = state.setdefault("luna_usage", {})
    usage["input_tokens"] = int(usage.get("input_tokens", 0)) + result.input_tokens
    usage["output_tokens"] = int(usage.get("output_tokens", 0)) + result.output_tokens
    usage["cached_input_tokens"] = int(
        usage.get("cached_input_tokens", 0)
    ) + result.cached_input_tokens
    usage["estimated_text_cost_usd"] = round(
        float(usage.get("estimated_text_cost_usd", 0.0))
        + result.estimated_text_cost_usd,
        8,
    )
    active_usage = state.setdefault(
        "active_scope_luna_usage",
        {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "estimated_text_cost_usd": 0.0,
        },
    )
    active_usage["input_tokens"] = int(
        active_usage.get("input_tokens", 0)
    ) + result.input_tokens
    active_usage["output_tokens"] = int(
        active_usage.get("output_tokens", 0)
    ) + result.output_tokens
    active_usage["cached_input_tokens"] = int(
        active_usage.get("cached_input_tokens", 0)
    ) + result.cached_input_tokens
    active_usage["estimated_text_cost_usd"] = round(
        float(active_usage.get("estimated_text_cost_usd", 0.0))
        + result.estimated_text_cost_usd,
        8,
    )

    state.update(
        {
            "status": "AWAITING_HUMAN_SCOPE_REVIEW",
            "stage": "HUMAN_SCOPE_REVIEW",
            "current_proposal_version": version,
            "current_proposal_path_relative": str(
                path.relative_to(repo_root.resolve())
            ).replace("\\", "/"),
            "last_provider_response_id": result.response_id,
            "next_stage": "DISCUSS_REVISE_OR_APPROVE_SCOPE",
            "last_error": None,
            "updated_at_utc": _now_utc(),
        }
    )
    _atomic_write_json(_state_path(repo_root), state)
    return state


def generate_next_episode_scope(
    repo_root: Path,
    openai_api_key: str,
    instruction: str = "",
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    state = load_orchestrator_state(repo_root)
    if state.get("status") not in {
        "IDLE_READY_FOR_NEXT_EPISODE",
        "AWAITING_HUMAN_SCOPE_REVIEW",
        "SCOPE_PROVIDER_ERROR",
    }:
        raise AutonomousOrchestratorError(
            f"SCOPE_GENERATION_NOT_ALLOWED:{state.get('status')}"
        )
    previous = current_scope_proposal(repo_root)
    discussion = load_scope_discussion(repo_root)
    turns = discussion.get("turns")
    if not isinstance(turns, list):
        turns = []
    state.update(
        {
            "status": "GENERATING_SCOPE_WITH_LUNA",
            "stage": "TOPIC_AND_EVENT_PROPOSAL",
            "next_stage": "WAIT_FOR_LUNA_SCOPE_RESULT",
            "last_error": None,
            "updated_at_utc": _now_utc(),
        }
    )
    _atomic_write_json(_state_path(repo_root), state)
    if instruction.strip():
        _append_turn(repo_root, "user", instruction)
    if progress:
        progress("يبحث Luna ويقترح موضوع الحلقة والأحداث…", None)
    try:
        result = request_scope_proposal(
            repo_root,
            openai_api_key,
            instruction=instruction,
            previous_proposal=previous,
            conversation=turns,
        )
    except LunaProviderError as exc:
        state["status"] = "SCOPE_PROVIDER_ERROR"
        state["last_error"] = str(exc)
        state["next_stage"] = "RETRY_SCOPE_AFTER_PROVIDER_FIX"
        state["updated_at_utc"] = _now_utc()
        _atomic_write_json(_state_path(repo_root), state)
        raise AutonomousOrchestratorError(str(exc)) from exc
    _append_turn(
        repo_root,
        "assistant",
        "تم إنشاء نسخة جديدة من مقترح موضوع الحلقة والأحداث.",
    )
    if progress:
        progress("اكتمل المقترح وبانتظار المراجعة البشرية.", 100)
    return _store_luna_result(repo_root, state, result)


def discuss_and_revise_scope(
    repo_root: Path,
    openai_api_key: str,
    message: str,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    if not message.strip():
        raise AutonomousOrchestratorError("DISCUSSION_MESSAGE_REQUIRED")
    state = load_orchestrator_state(repo_root)
    if state.get("status") != "AWAITING_HUMAN_SCOPE_REVIEW":
        raise AutonomousOrchestratorError("SCOPE_NOT_OPEN_FOR_DISCUSSION")
    return generate_next_episode_scope(
        repo_root,
        openai_api_key,
        instruction=message,
        progress=progress,
    )


def _next_episode_number(repo_root: Path) -> int:
    maximum = 0
    pattern = re.compile(r"^episode-(\d{3})-")
    projects = repo_root.resolve() / "projects"
    if projects.is_dir():
        for path in projects.iterdir():
            match = pattern.match(path.name)
            if match:
                maximum = max(maximum, int(match.group(1)))
    return maximum + 1


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    if not slug:
        raise AutonomousOrchestratorError("PROPOSAL_SLUG_INVALID")
    return slug[:80]


def approve_scope(
    repo_root: Path,
    approved_by: str = "CREATOR",
) -> dict[str, Any]:
    state = load_orchestrator_state(repo_root)
    if state.get("status") != "AWAITING_HUMAN_SCOPE_REVIEW":
        raise AutonomousOrchestratorError("SCOPE_APPROVAL_NOT_ALLOWED")
    proposal = current_scope_proposal(repo_root)
    if proposal is None:
        raise AutonomousOrchestratorError("SCOPE_PROPOSAL_REQUIRED")
    events = proposal.get("events")
    if not isinstance(events, list) or not 3 <= len(events) <= 15:
        raise AutonomousOrchestratorError("APPROVED_EVENT_COUNT_INVALID")

    number = _next_episode_number(repo_root)
    slug = _safe_slug(str(proposal.get("slug_en", "")))
    episode_id = f"episode-{number:03d}-{slug}"
    episode_root = repo_root.resolve() / "projects" / episode_id
    if episode_root.exists():
        raise AutonomousOrchestratorError("EPISODE_DIRECTORY_ALREADY_EXISTS")

    contracts = episode_root / "contracts"
    orchestration = episode_root / "orchestration"
    contracts.mkdir(parents=True, exist_ok=False)
    orchestration.mkdir(parents=True, exist_ok=False)

    proposal_sha = str(proposal.get("proposal_sha256") or _canonical_sha256(proposal))
    definition = {
        "schema_version": "siraj-autonomous-episode-definition-v1",
        "episode_id": episode_id,
        "title_ar": proposal.get("topic_title_ar"),
        "working_title_ar": proposal.get("working_title_ar"),
        "central_question_ar": proposal.get("central_question_ar"),
        "estimated_duration_minutes": proposal.get("estimated_duration_minutes"),
        "approved_event_count": len(events),
        "approved_event_ids": [item.get("event_id") for item in events],
        "source_scope_proposal_sha256": proposal_sha,
        "production_policy": {
            "episode_cost_hard_cap_usd": 40.0,
            "generated_video_target_seconds": [120, 180],
            "music": "FORBIDDEN",
            "sound_effects": "ALLOWED_ANY_SCENE_APPROPRIATE_TYPE",
            "images_provider": "RUNWARE",
            "video_provider": "RUNWARE",
            "graphics_provider": "LOCAL_QML_FFMPEG",
            "tts_provider": "ELEVENLABS",
            "editorial_model": "gpt-5.6-luna",
        },
        "human_scope_approval": "APPROVED",
        "created_at_utc": _now_utc(),
    }
    definition["definition_sha256"] = _canonical_sha256(definition)
    _atomic_write_json(contracts / "episode-definition-v1.json", definition)

    approved_proposal = dict(proposal)
    approved_proposal["human_approval"] = True
    approved_proposal["approved_by"] = approved_by
    approved_proposal["approved_at_utc"] = _now_utc()
    approved_proposal["episode_id"] = episode_id
    approved_proposal.pop("proposal_sha256", None)
    approved_proposal["proposal_sha256"] = _canonical_sha256(approved_proposal)
    approved_path = contracts / "approved-scope-v1.json"
    _atomic_write_json(approved_path, approved_proposal)

    graph = build_scope_dependency_graph(episode_id, approved_proposal)
    graph_path = orchestration / "artifact-dependency-graph-v1.json"
    _atomic_write_json(graph_path, graph)

    active_usage = state.get("active_scope_luna_usage")
    if not isinstance(active_usage, Mapping):
        active_usage = {}
    scope_cost = float(active_usage.get("estimated_text_cost_usd", 0.0))
    if (
        scope_cost > 0
        or int(active_usage.get("input_tokens", 0)) > 0
        or int(active_usage.get("output_tokens", 0)) > 0
    ):
        cost_receipt = {
            "schema_version": "siraj-provider-cost-receipt-v1",
            "episode_id": episode_id,
            "provider": "OPENAI",
            "service": "GPT-5.6_LUNA_SCOPE_AND_DISCUSSION",
            "cost_category": "OPENAI_LUNA",
            "cost_basis": "ESTIMATED_FROM_PROVIDER_USAGE",
            "estimated_cost_usd": round(scope_cost, 8),
            "input_tokens": int(active_usage.get("input_tokens", 0)),
            "output_tokens": int(active_usage.get("output_tokens", 0)),
            "cached_input_tokens": int(
                active_usage.get("cached_input_tokens", 0)
            ),
            "provider_response_id": state.get(
                "last_provider_response_id"
            ),
            "created_at_utc": _now_utc(),
        }
        _atomic_write_json(
            orchestration
            / "cost-receipts"
            / "openai-luna-scope-receipt-v1.json",
            cost_receipt,
        )

    stage_ledger = {
        "schema_version": "siraj-autonomous-stage-ledger-v1",
        "episode_id": episode_id,
        "status": "AUTOMATIC_PIPELINE_QUEUED",
        "stages": [
            {
                "order": index,
                "stage": stage,
                "status": (
                    "COMPLETE"
                    if stage in {"TOPIC_AND_EVENT_PROPOSAL", "HUMAN_SCOPE_REVIEW"}
                    else "QUEUED"
                ),
            }
            for index, stage in enumerate(FULL_STAGE_ORDER, start=1)
        ],
        "resume_from": "EVIDENCE_RESEARCH",
        "created_at_utc": _now_utc(),
        "updated_at_utc": _now_utc(),
    }
    _atomic_write_json(orchestration / "stage-ledger-v1.json", stage_ledger)

    state.update(
        {
            "status": "SCOPE_APPROVED_AUTOMATIC_PIPELINE_QUEUED",
            "stage": "EVIDENCE_RESEARCH",
            "current_episode_id": episode_id,
            "approved_scope_path_relative": str(
                approved_path.relative_to(repo_root.resolve())
            ).replace("\\", "/"),
            "dependency_graph_path_relative": str(
                graph_path.relative_to(repo_root.resolve())
            ).replace("\\", "/"),
            "next_stage": "IMPLEMENT_AUTOMATIC_RESEARCH_SCRIPT_STORYBOARD_RUNNER_V1",
            "active_scope_luna_usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_input_tokens": 0,
                "estimated_text_cost_usd": 0.0,
            },
            "last_error": None,
            "updated_at_utc": _now_utc(),
        }
    )
    _atomic_write_json(_state_path(repo_root), state)
    _append_turn(repo_root, "system", f"تم اعتماد النطاق وإنشاء {episode_id}.")
    return state


def provider_readiness(
    repo_root: Path,
    *,
    openai_key_present: bool,
    elevenlabs_key_present: bool,
    runware_key_present: bool,
) -> dict[str, str]:
    state = load_orchestrator_state(repo_root)
    audio_environment = inspect_audio_environment(repo_root)
    montage_environment = inspect_montage_environment(repo_root)
    qa_environment = inspect_qa_environment(repo_root)
    readiness = {
        "openai_luna": "READY" if openai_key_present else "KEY_REQUIRED",
        "runware": "READY" if runware_key_present else "KEY_REQUIRED",
        "elevenlabs": "READY" if elevenlabs_key_present else "KEY_REQUIRED",
        "montage": (
            "LOCAL_FFMPEG_READY"
            if montage_environment.ready
            else "LOCAL_FFMPEG_NOT_READY"
        ),
        "qa": (
            "LOCAL_FFMPEG_READY"
            if qa_environment.ready
            else "LOCAL_FFMPEG_NOT_READY"
        ),
        "sfx": (
            "LOCAL_FFMPEG_READY"
            if audio_environment.ready
            else "LOCAL_FFMPEG_NOT_READY"
        ),
    }
    state["provider_readiness"] = readiness
    state["updated_at_utc"] = _now_utc()
    _atomic_write_json(_state_path(repo_root), state)
    return readiness
