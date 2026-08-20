"""Canonical next-episode profile and provider isolation for manual visuals."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

PROFILE_SCHEMA = "siraj-canonical-next-episode-profile-v1"
PROFILE_ID = "CANONICAL_NEXT_EPISODE_MANUAL_VISUAL_V1"
VISUAL_MODE = "MANUAL_USER_PRODUCTION"
PROFILE_REL = Path("contracts/episode-profile-v1.json")

VISUAL_PROVIDERS = frozenset(
    {"RUNWARE", "VEO", "GOOGLE_VEO", "SEEDDREAM", "OPENAI_IMAGE", "IMAGE_PROVIDER"}
)
VISUAL_TASK_TYPES = frozenset(
    {
        "imageInference",
        "videoInference",
        "IMAGE_GENERATION",
        "VIDEO_GENERATION",
        "VISUAL_REPAIR",
        "CANONICAL_REFERENCE_GENERATION",
    }
)
NON_VISUAL_OPERATION_TYPES = frozenset(
    {
        "TEXT_RESEARCH",
        "TEXT_GENERATION",
        "TTS",
        "NARRATION",
        "TRANSCRIPTION",
        "ALIGNMENT",
        "AUDIO_GENERATION",
    }
)
VISUAL_REQUEST_MARKERS = frozenset(
    {"IMAGE", "VIDEO", "VISUAL", "FRAME", "RENDER", "STORYBOARD", "REFERENCE_ASSET"}
)


class CanonicalManualVisualProfileError(RuntimeError):
    pass


def profile_payload(episode_id: str) -> dict[str, Any]:
    identity = str(episode_id or "").strip()
    if not identity:
        raise CanonicalManualVisualProfileError("EPISODE_ID_REQUIRED")
    return {
        "schema_version": PROFILE_SCHEMA,
        "profile_id": PROFILE_ID,
        "episode_id": identity,
        "visual_mode": VISUAL_MODE,
        "automatic_visual_generation": False,
        "paid_visual_provider_execution": False,
        "provider_visual_fallback": False,
        "primitive_diagram_fallback": False,
        "manual_visual_ingest_required": True,
        "human_pre_visual_approval_required": True,
        "human_final_review_required": True,
        "publication_authorized": False,
    }


def validate_profile(value: Mapping[str, Any], *, episode_id: str | None = None) -> None:
    expected = profile_payload(episode_id or str(value.get("episode_id") or ""))
    for key in (
        "schema_version",
        "profile_id",
        "episode_id",
        "visual_mode",
        "automatic_visual_generation",
        "paid_visual_provider_execution",
        "provider_visual_fallback",
        "primitive_diagram_fallback",
        "manual_visual_ingest_required",
        "human_pre_visual_approval_required",
        "human_final_review_required",
        "publication_authorized",
    ):
        if value.get(key) != expected[key]:
            raise CanonicalManualVisualProfileError(f"PROFILE_FIELD_INVALID:{key}")


def load_profile(repo_root: Path, episode_id: str) -> dict[str, Any] | None:
    path = Path(repo_root).resolve() / "projects" / episode_id / PROFILE_REL
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CanonicalManualVisualProfileError("EPISODE_PROFILE_UNREADABLE") from exc
    if not isinstance(value, dict):
        raise CanonicalManualVisualProfileError("EPISODE_PROFILE_OBJECT_REQUIRED")
    validate_profile(value, episode_id=episode_id)
    return value


def _task_type(payload: Any) -> str:
    if not isinstance(payload, Mapping):
        return ""
    task = payload.get("task")
    if isinstance(task, Mapping):
        return str(task.get("taskType") or task.get("type") or "").strip()
    return str(payload.get("taskType") or payload.get("operation") or "").strip()


def is_visual_generation_request(provider: str, payload: Any) -> bool:
    provider_name = str(provider or "").strip().upper()
    task_type = _task_type(payload)
    searchable = " ".join(
        (
            provider_name,
            task_type.upper(),
            json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str).upper()
            if isinstance(payload, Mapping)
            else str(payload or "").upper(),
        )
    )
    return (
        provider_name in VISUAL_PROVIDERS
        or task_type in VISUAL_TASK_TYPES
        or any(marker in searchable for marker in VISUAL_REQUEST_MARKERS)
    )


def enforce_manual_visual_provider_isolation(request: Any) -> None:
    """Reject canonical manual-profile visual generation before any attempt write."""

    episode_id = str(getattr(request, "episode_id", "") or "").strip()
    repo_root = Path(getattr(request, "repo_root", ".")).resolve()
    if not episode_id:
        return
    profile = load_profile(repo_root, episode_id)
    if profile is None:
        return
    provider = str(getattr(request, "provider", "") or "")
    payload = getattr(request, "payload", None)
    operation_type = str(getattr(request, "operation_type", "") or "").strip().upper()
    stage = str(getattr(request, "stage", "") or "").strip().upper()
    explicitly_non_visual = operation_type in NON_VISUAL_OPERATION_TYPES
    visual = is_visual_generation_request(provider, payload) or any(
        marker in operation_type for marker in VISUAL_REQUEST_MARKERS
    )
    unknown_provider_execution = (
        stage == "PROVIDER_EXECUTION" and not explicitly_non_visual and not operation_type
    ) or (
        bool(provider.strip()) and not explicitly_non_visual and not visual
    )
    if visual or unknown_provider_execution:
        raise CanonicalManualVisualProfileError(
            "MANUAL_VISUAL_PIPELINE_DOES_NOT_ALLOW_PROVIDER_GENERATION"
        )


def desktop_paid_visual_controls_allowed(repo_root: Path, episode_id: str) -> bool:
    return load_profile(repo_root, episode_id) is None
