"""Strict model/version request contracts and cinematic prompt preservation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence
import uuid

from src.application.artifact_provenance_v1 import canonical_sha256
from src.application.siraj_runware_provider_contract_v6_6_r9 import (
    VEO_31_MODELS,
    is_veo_31_model,
    sanitize_runware_task_for_submission,
)


CONTRACT_VERSION = "siraj-provider-model-contracts-v1"
SEEDREAM_MODELS = {"bytedance:seedream@5.0-pro"}
NANO_BANANA_MODELS = {"google:4@3"}
# Runware's Veo 3.1 Lite contract is discrete.  A value merely below the
# eight-second maximum is not automatically a supported request duration.
# Keeping this list in the execution contract prevents a planner from
# treating arbitrary timeline fragments as provider billing units.
VEO_31_SUPPORTED_DURATIONS_SECONDS = frozenset({4, 6, 8})
VEO_31_720P_DIMENSIONS = frozenset({(1280, 720), (720, 1280)})


class ProviderModelContractError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ValidatedProviderPayload:
    provider: str
    model: str
    contract_version: str
    payload: Mapping[str, Any]
    internal_metadata: Mapping[str, Any]

    @property
    def payload_sha256(self) -> str:
        return canonical_sha256(self.payload)


RUNWARE_VIDEO_FIELDS = frozenset(
    {
        "taskType",
        "taskUUID",
        "model",
        "positivePrompt",
        "width",
        "height",
        "duration",
        "numberResults",
        "deliveryMethod",
        "includeCost",
        "providerSettings",
    }
)
RUNWARE_IMAGE_FIELDS = frozenset(
    {
        "taskType",
        "taskUUID",
        "model",
        "positivePrompt",
        "negativePrompt",
        "width",
        "height",
        "numberResults",
        "outputFormat",
        "outputType",
        "includeCost",
        "inputs",
    }
)
RUNWARE_POLL_FIELDS = frozenset({"taskType", "taskUUID"})
RUNWARE_LOOKUP_FIELDS = frozenset({"taskType", "taskUUID"})
OPENAI_RESPONSES_FIELDS = frozenset(
    {"model", "store", "reasoning", "input", "text", "tools"}
)
ELEVENLABS_FIELDS = frozenset(
    {"voice_id", "model_id", "text", "voice_settings", "output_format"}
)


def _reject_unknown(payload: Mapping[str, Any], allowed: frozenset[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ProviderModelContractError(
            "PROVIDER_UNKNOWN_FIELDS_REJECTED:" + ",".join(unknown)
        )


def _positive_prompt(payload: Mapping[str, Any]) -> str:
    prompt = str(payload.get("positivePrompt") or "").strip()
    if not prompt:
        raise ProviderModelContractError("PROVIDER_POSITIVE_PROMPT_REQUIRED")
    return prompt


def is_uuid4(value: Any) -> bool:
    """Return whether *value* is a canonical RFC UUID version 4 string.

    Planning artifacts historically used ``planning-only-*`` identities.  A
    planning identity is acceptable to the offline validator for historical
    reports, but it is never acceptable at the paid Runware boundary.  Keeping
    this predicate public lets the execution and forensic layers make the
    same decision without duplicating UUID parsing rules.
    """

    text = str(value or "").strip()
    if not text:
        return False
    try:
        parsed = uuid.UUID(text)
    except (ValueError, AttributeError, TypeError):
        return False
    return parsed.version == 4 and str(parsed) == text.lower()


def _validate_task_uuid(value: Any, *, require_uuid_v4: bool) -> None:
    if not str(value or "").strip():
        raise ProviderModelContractError("RUNWARE_TASK_UUID_REQUIRED")
    if require_uuid_v4 and not is_uuid4(value):
        raise ProviderModelContractError("RUNWARE_TASK_UUID_UUID4_REQUIRED")


def validate_runware_task(
    task: Mapping[str, Any],
    *,
    require_uuid_v4: bool = False,
) -> ValidatedProviderPayload:
    internal = {}
    if isinstance(task.get("sirajRouting"), Mapping):
        internal["sirajRouting"] = dict(task["sirajRouting"])
    if isinstance(task.get("internalNegativeConstraints"), str):
        internal["internalNegativeConstraints"] = task["internalNegativeConstraints"]
    provider_payload = {
        key: value
        for key, value in task.items()
        if key not in {"sirajRouting", "internalNegativeConstraints"}
    }
    task_type = str(provider_payload.get("taskType") or "")
    model = str(provider_payload.get("model") or "")
    if task_type in {"getResponse", "getTaskDetails"}:
        _reject_unknown(provider_payload, RUNWARE_LOOKUP_FIELDS)
        _validate_task_uuid(
            provider_payload.get("taskUUID"),
            require_uuid_v4=require_uuid_v4,
        )
        return ValidatedProviderPayload(
            "RUNWARE", task_type, CONTRACT_VERSION, provider_payload, internal
        )
    if task_type == "videoInference":
        provider_payload = sanitize_runware_task_for_submission(provider_payload)
        _reject_unknown(provider_payload, RUNWARE_VIDEO_FIELDS)
        if not is_veo_31_model(model):
            raise ProviderModelContractError("RUNWARE_VIDEO_MODEL_UNSUPPORTED:" + model)
        if "negativePrompt" in provider_payload:
            raise ProviderModelContractError("VEO31_NEGATIVE_PROMPT_FIELD_FORBIDDEN")
        _positive_prompt(provider_payload)
        duration = provider_payload.get("duration")
        if (
            not isinstance(duration, int)
            or isinstance(duration, bool)
            or duration not in VEO_31_SUPPORTED_DURATIONS_SECONDS
        ):
            raise ProviderModelContractError("VEO31_DURATION_OUT_OF_CONTRACT")
        if (provider_payload.get("width"), provider_payload.get("height")) not in VEO_31_720P_DIMENSIONS:
            raise ProviderModelContractError("VEO31_DIMENSIONS_INVALID")
        if provider_payload.get("numberResults") != 1:
            raise ProviderModelContractError("VEO31_ONE_RESULT_REQUIRED")
        settings = provider_payload.get("providerSettings")
        if not isinstance(settings, Mapping) or set(settings) != {"google"}:
            raise ProviderModelContractError("VEO31_PROVIDER_SETTINGS_INVALID")
    elif task_type == "imageInference":
        _reject_unknown(provider_payload, RUNWARE_IMAGE_FIELDS)
        if model not in SEEDREAM_MODELS | NANO_BANANA_MODELS:
            raise ProviderModelContractError("RUNWARE_IMAGE_MODEL_UNSUPPORTED:" + model)
        _positive_prompt(provider_payload)
        if model in SEEDREAM_MODELS and "negativePrompt" in provider_payload:
            internal["internalNegativeConstraints"] = str(
                provider_payload.pop("negativePrompt") or ""
            )
        width = provider_payload.get("width")
        height = provider_payload.get("height")
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise ProviderModelContractError("RUNWARE_IMAGE_DIMENSIONS_INVALID")
    else:
        raise ProviderModelContractError("RUNWARE_TASK_TYPE_UNSUPPORTED:" + task_type)
    _validate_task_uuid(
        provider_payload.get("taskUUID"),
        require_uuid_v4=require_uuid_v4,
    )
    return ValidatedProviderPayload(
        provider="RUNWARE",
        model=model,
        contract_version=CONTRACT_VERSION,
        payload=provider_payload,
        internal_metadata=internal,
    )


def validate_openai_responses_payload(
    payload: Mapping[str, Any],
) -> ValidatedProviderPayload:
    _reject_unknown(payload, OPENAI_RESPONSES_FIELDS)
    model = str(payload.get("model") or "").strip()
    if not model:
        raise ProviderModelContractError("OPENAI_MODEL_REQUIRED")
    if payload.get("store") is not False:
        raise ProviderModelContractError("OPENAI_STORE_FALSE_REQUIRED")
    if not isinstance(payload.get("input"), list) or not payload["input"]:
        raise ProviderModelContractError("OPENAI_INPUT_REQUIRED")
    return ValidatedProviderPayload(
        "OPENAI", model, CONTRACT_VERSION, dict(payload), {}
    )


def validate_elevenlabs_payload(
    payload: Mapping[str, Any],
) -> ValidatedProviderPayload:
    _reject_unknown(payload, ELEVENLABS_FIELDS)
    voice_id = str(payload.get("voice_id") or "").strip()
    model = str(payload.get("model_id") or "").strip()
    text = str(payload.get("text") or "").strip()
    if not voice_id or not model or not text:
        raise ProviderModelContractError("ELEVENLABS_REQUIRED_FIELDS_MISSING")
    return ValidatedProviderPayload(
        "ELEVENLABS", model, CONTRACT_VERSION, dict(payload), {}
    )


def validate_runware_response(
    response: Mapping[str, Any],
    *,
    task_uuid: str,
    media_kind: str,
) -> Mapping[str, Any] | None:
    if response.get("errors") or response.get("error"):
        raise ProviderModelContractError("RUNWARE_RESPONSE_ERROR")
    data = response.get("data")
    if not isinstance(data, list):
        raise ProviderModelContractError("RUNWARE_RESPONSE_DATA_ARRAY_REQUIRED")
    matched = next(
        (
            row
            for row in data
            if isinstance(row, Mapping) and str(row.get("taskUUID") or "") == task_uuid
        ),
        None,
    )
    if matched is None:
        return None
    key = "imageURL" if media_kind == "RUNWARE_IMAGE" else "videoURL"
    return matched if matched.get(key) else None


def render_cinematic_prompt(direction: Mapping[str, Any]) -> str:
    """Render rich, non-generic creative direction without padding for length."""

    ordered = (
        ("Visual concept", "visual_concept"),
        ("Narrative function", "narrative_function"),
        ("Treatment", "cinematic_treatment"),
        ("Composition", "composition"),
        ("Camera and lens", "camera_intent"),
        ("Scale", "lens_scale_intent"),
        ("Subject staging", "subject_staging"),
        ("Foreground", "foreground"),
        ("Midground", "midground"),
        ("Background", "background"),
        ("Lighting", "lighting"),
        ("Color and mood", "color_mood"),
        ("Atmosphere", "atmosphere"),
        ("Environment", "environment"),
        ("Motion intent", "motion"),
        ("Symbolism", "symbolism"),
        ("Continuity", "continuity_strategy"),
        ("Distinctness", "distinctness_strategy"),
        ("Transition", "transition_intent"),
        ("Historical material detail", "historical_material_details"),
        ("Provider notes", "provider_notes"),
    )
    clauses: list[str] = []
    seen: set[str] = set()
    for label, key in ordered:
        text = str(direction.get(key) or "").strip()
        normalized = " ".join(text.casefold().split())
        if text and normalized not in seen:
            clauses.append(f"{label}: {text}")
            seen.add(normalized)
    existing = str(direction.get("provider_ready_prompt") or "").strip()
    if existing:
        normalized = " ".join(existing.casefold().split())
        if normalized not in seen:
            clauses.insert(0, existing)
    if len(clauses) < 4:
        raise ProviderModelContractError("CINEMATIC_PROMPT_TOO_GENERIC")
    return ". ".join(clause.rstrip(". ") for clause in clauses) + "."


def intentional_reuse_allowed(
    a: Mapping[str, Any],
    b: Mapping[str, Any],
) -> bool:
    reason_a = str(a.get("reuse_justification") or "").strip()
    reason_b = str(b.get("reuse_justification") or "").strip()
    continuity_a = str(a.get("continuity_strategy") or "").strip()
    continuity_b = str(b.get("continuity_strategy") or "").strip()
    return bool(reason_a and reason_b and continuity_a and continuity_b)


def validate_distinct_sequential_clips(items: Sequence[Mapping[str, Any]]) -> None:
    seen_payloads: set[str] = set()
    for item in items:
        if item.get("media_kind") != "RUNWARE_VIDEO":
            continue
        task = item.get("task_draft")
        if not isinstance(task, Mapping):
            raise ProviderModelContractError("VIDEO_TASK_DRAFT_REQUIRED")
        fingerprint = canonical_sha256(
            {
                "prompt": task.get("positivePrompt"),
                "model": task.get("model"),
                "duration": task.get("duration"),
                "progression": item.get("visual_progression_id"),
            }
        )
        if fingerprint in seen_payloads:
            raise ProviderModelContractError("REPEATED_VIDEO_CLIP_PAYLOAD_FORBIDDEN")
        seen_payloads.add(fingerprint)
