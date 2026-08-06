"""Luna Cinematic Prompt Director V2 for SIRAJ.

Every provider-facing visual prompt must be created by Luna or explicitly
reviewed and rewritten by Luna.  Raw storyboard prompts are drafts only.
No Runware request may be submitted without a valid certification attached
to the queue item.

The module supports:
- deterministic prompt-plan preparation with zero provider requests;
- exact batched Luna review requests;
- one locked OpenAI request per authorized batch, with no automatic retry;
- strict cinematic, continuity, provider and religious-safety validation;
- promotion of the production-standard storyboard to a Luna-certified
  storyboard;
- propagation of certified prompts into the existing media queue;
- a final execution guard immediately before any Runware network request.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
import urllib.error
import urllib.request

from src.application.openai_luna_orchestrator_v1 import (
    LUNA_MODEL,
    LUNA_INPUT_USD_PER_MILLION,
    LUNA_OUTPUT_USD_PER_MILLION,
    estimate_text_cost_usd,
)

RELEASE = "SIRAJ_LUNA_CINEMATIC_PROMPT_DIRECTOR_V2"
SCHEMA_VERSION = "siraj-luna-cinematic-prompt-director-v2"

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
REQUEST_TIMEOUT_SECONDS = 600

EPISODE_ID = "episode-001-adam"
BATCH_SIZE = 10
QUALITY_THRESHOLD = 95
PROMPT_DIRECTOR_TOTAL_RESERVE_USD = 0.35
MAXIMUM_BATCH_RESERVE_USD = 0.05

STANDARD_STORYBOARD_REL = Path(
    "cinematic/storyboard-and-media-plan-production-standard-v2.json"
)
CERTIFIED_STORYBOARD_REL = Path(
    "cinematic/storyboard-and-media-plan-luna-certified-v2.json"
)
PROMPT_PLAN_REL = Path(
    "orchestration/luna-cinematic-prompt-direction-plan-v2.json"
)
PROMPT_REQUEST_DIR_REL = Path(
    "orchestration/luna-prompt-direction-v2/requests"
)
PROMPT_RESPONSE_DIR_REL = Path(
    "orchestration/luna-prompt-direction-v2/responses"
)
PROMPT_LOCK_DIR_REL = Path(
    "orchestration/luna-prompt-direction-v2/locks"
)
PROMPT_RECEIPT_DIR_REL = Path(
    "orchestration/luna-prompt-direction-v2/receipts"
)
PROMPT_READINESS_REL = Path(
    "orchestration/luna-prompt-direction-readiness-v2.json"
)
MEDIA_QUEUE_REL = Path("orchestration/media-production-queue-v1.json")
STANDARD_READINESS_REL = Path(
    "orchestration/series-production-standard-v2-readiness.json"
)
DESKTOP_SNAPSHOT_REL = Path(
    "orchestration/desktop-series-production-standard-v2-snapshot.json"
)
SERIES_STANDARD_REL = Path(
    "projects/_series/siraj-series-production-standard-v2.json"
)
DIRECTOR_BIBLE_REL = Path(
    "projects/_series/siraj-series-director-bible-v2.json"
)

FORBIDDEN_DIRECT_DEPICTION_TERMS = (
    "god visible",
    "visible god",
    "allah visible",
    "face of god",
    "portrait of prophet",
    "prophet face",
    "angel portrait",
    "literal angel",
    "devil portrait",
    "iblis face",
    "جسد الله",
    "وجه الله",
    "صورة النبي",
    "وجه النبي",
    "ملاك مجسد",
    "وجه إبليس",
)

LOW_VALUE_QUALITY_STACK = (
    "masterpiece",
    "best quality",
    "8k",
    "16k",
    "ultra detailed",
    "award winning",
    "trending on artstation",
)

CAMERA_TERMS = (
    "camera",
    "lens",
    "wide shot",
    "close-up",
    "close up",
    "macro",
    "dolly",
    "tracking",
    "crane",
    "orbit",
    "composition",
    "foreground",
    "midground",
    "background",
    "depth",
    "focal",
)

LIGHT_TERMS = (
    "light",
    "lighting",
    "shadow",
    "backlight",
    "rim light",
    "volumetric",
    "contrast",
    "exposure",
    "glow",
    "golden",
    "amber",
    "moonlight",
)

MATERIAL_TERMS = (
    "texture",
    "material",
    "stone",
    "clay",
    "dust",
    "water",
    "fabric",
    "wood",
    "metal",
    "parchment",
    "basalt",
    "sand",
    "soil",
    "smoke",
)

MOTION_TERMS = (
    "moves",
    "moving",
    "drifts",
    "tracks",
    "flows",
    "falls",
    "rises",
    "rotates",
    "pushes",
    "pulls",
    "wind",
    "particles",
    "camera",
    "motion",
    "start",
    "then",
    "ends",
    "throughout",
)

PROMPT_KINDS = {
    "GENERATED_VIDEO": "VIDEO_GENERATION",
    "ANIMATED_STILL_COMPOSITING": "IMAGE_GENERATION",
    "DYNAMIC_STILL_SEQUENCE": "IMAGE_GENERATION",
    "DYNAMIC_STILL": "IMAGE_GENERATION",
    "GENERATED_IMAGE": "IMAGE_GENERATION",
    "AUTHORED_GRAPHICS": "LOCAL_GRAPHICS_ART_DIRECTION",
    "GRAPHICS": "LOCAL_GRAPHICS_ART_DIRECTION",
}


class CinematicPromptDirectorError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PromptDraftIssue:
    code: str
    severity: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CinematicPromptDirectorError(
            f"CANNOT_READ_JSON:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise CinematicPromptDirectorError(
            f"JSON_OBJECT_REQUIRED:{path}"
        )
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return value
    return ()


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _shot_lists(storyboard: dict[str, Any]) -> list[list[dict[str, Any]]]:
    direct = storyboard.get("shots")
    if isinstance(direct, list):
        return [direct]
    result: list[list[dict[str, Any]]] = []
    for sequence in _sequence(storyboard.get("sequences")):
        if not isinstance(sequence, dict):
            continue
        shots = sequence.get("shots")
        if isinstance(shots, list):
            result.append(shots)
    return result


def _all_shots(storyboard: Mapping[str, Any]) -> list[dict[str, Any]]:
    direct = storyboard.get("shots")
    if isinstance(direct, list):
        return [
            dict(item)
            for item in direct
            if isinstance(item, Mapping)
        ]
    result: list[dict[str, Any]] = []
    for sequence in _sequence(storyboard.get("sequences")):
        if not isinstance(sequence, Mapping):
            continue
        for shot in _sequence(sequence.get("shots")):
            if isinstance(shot, Mapping):
                item = dict(shot)
                item.setdefault(
                    "sequence_id",
                    sequence.get("sequence_id"),
                )
                result.append(item)
    return result


def _prompt_kind(shot: Mapping[str, Any]) -> str:
    treatment = str(
        shot.get("final_budget_treatment")
        or shot.get("treatment")
        or shot.get("recommended_treatment_v2")
        or ""
    ).upper()
    if treatment in PROMPT_KINDS:
        return PROMPT_KINDS[treatment]
    if "VIDEO" in treatment:
        return "VIDEO_GENERATION"
    if "GRAPHIC" in treatment:
        return "LOCAL_GRAPHICS_ART_DIRECTION"
    return "IMAGE_GENERATION"


def _provider_model(
    shot: Mapping[str, Any],
    kind: str,
) -> tuple[str, str]:
    if kind == "VIDEO_GENERATION":
        return "RUNWARE", str(
            shot.get("selected_model")
            or shot.get("video_model")
            or "google:veo@3.1-lite"
        )
    if kind == "LOCAL_GRAPHICS_ART_DIRECTION":
        return "LOCAL", "PYSIDE6_QT_QUICK_QML_FFMPEG"
    role = str(
        shot.get("image_model_role")
        or shot.get("runware_image_role")
        or ""
    ).upper()
    human_terms = (
        "portrait",
        "human",
        "crowd",
        "person",
        "face",
        "character consistency",
        "بورتريه",
        "إنسان",
        "حشد",
        "وجه",
    )
    source = " ".join(
        _clean(shot.get(key)).lower()
        for key in (
            "label_ar",
            "visual_brief_ar",
            "runware_positive_prompt_en",
        )
    )
    if role in {
        "HUMAN_CLOSEUP",
        "HUMAN_CROWD_COMPLEX",
        "CHARACTER_CONSISTENCY",
        "REFERENCE_EDIT",
        "HUMAN_INTERACTION_COMPLEX",
    } or any(term in source for term in human_terms):
        return "RUNWARE", "google:4@3"
    return "RUNWARE", "bytedance:seedream@5.0-pro"


def _original_positive_prompt(shot: Mapping[str, Any]) -> str:
    for key in (
        "certified_positive_prompt_en",
        "runware_positive_prompt_en",
        "positive_prompt",
        "positive_prompt_en",
        "prompt_en",
        "visual_prompt_en",
    ):
        value = _clean(shot.get(key))
        if value:
            return value
    return ""


def _original_negative_prompt(shot: Mapping[str, Any]) -> str:
    for key in (
        "certified_negative_prompt_en",
        "runware_negative_prompt_en",
        "negative_prompt",
        "negative_prompt_en",
    ):
        value = _clean(shot.get(key))
        if value:
            return value
    return ""


def _context(shot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "shot_id": _clean(shot.get("shot_id")),
        "sequence_id": _clean(shot.get("sequence_id")),
        "label_ar": _clean(shot.get("label_ar")),
        "dramatic_function_ar": _clean(
            shot.get("dramatic_function_ar")
        ),
        "visual_brief_ar": _clean(
            shot.get("visual_brief_ar")
        ),
        "camera_motion_ar": _clean(
            shot.get("camera_motion_ar")
        ),
        "editorial_duration_seconds": (
            shot.get("editorial_duration_seconds")
            or shot.get("planned_seconds")
            or shot.get("duration_seconds")
        ),
        "scene_domain": _clean(shot.get("scene_domain")),
        "representation_mode": _clean(
            shot.get("representation_mode")
        ),
        "representation_claim": _clean(
            shot.get("representation_claim")
        ),
        "character_location": _clean(
            shot.get("character_location")
        ),
        "camera_plan_v2": deepcopy(
            shot.get("camera_plan_v2") or {}
        ),
        "continuity_lock_v2": deepcopy(
            shot.get("continuity_lock_v2") or {}
        ),
        "visual_quality_contract_v2": deepcopy(
            shot.get("visual_quality_contract_v2") or {}
        ),
        "safety_notes_ar": list(
            _sequence(shot.get("safety_notes_ar"))
        ),
        "reference_images": list(
            _sequence(shot.get("reference_images"))
        ),
    }


def audit_prompt_text(
    positive_prompt: str,
    *,
    kind: str,
    context: Mapping[str, Any] | None = None,
) -> tuple[PromptDraftIssue, ...]:
    prompt = _clean(positive_prompt)
    lowered = prompt.lower()
    issues: list[PromptDraftIssue] = []

    minimum = {
        "VIDEO_GENERATION": 220,
        "IMAGE_GENERATION": 160,
        "LOCAL_GRAPHICS_ART_DIRECTION": 100,
    }.get(kind, 140)
    if len(prompt) < minimum:
        issues.append(
            PromptDraftIssue(
                "PROMPT_TOO_SHORT_FOR_PREMIUM_DIRECTION",
                "REWRITE",
                f"length={len(prompt)}:minimum={minimum}",
            )
        )

    if kind != "LOCAL_GRAPHICS_ART_DIRECTION":
        if not any(term in lowered for term in CAMERA_TERMS):
            issues.append(
                PromptDraftIssue(
                    "CAMERA_OR_COMPOSITION_LANGUAGE_MISSING",
                    "REWRITE",
                    "Provider prompt lacks explicit camera/composition language.",
                )
            )
        if not any(term in lowered for term in LIGHT_TERMS):
            issues.append(
                PromptDraftIssue(
                    "LIGHTING_LANGUAGE_MISSING",
                    "REWRITE",
                    "Provider prompt lacks explicit lighting/exposure language.",
                )
            )
        if not any(term in lowered for term in MATERIAL_TERMS):
            issues.append(
                PromptDraftIssue(
                    "MATERIAL_TEXTURE_LANGUAGE_MISSING",
                    "REWRITE",
                    "Provider prompt lacks material/texture specificity.",
                )
            )

    if kind == "VIDEO_GENERATION":
        motion_hits = sum(
            term in lowered for term in MOTION_TERMS
        )
        if motion_hits < 3:
            issues.append(
                PromptDraftIssue(
                    "TEMPORAL_MOTION_PLAN_MISSING",
                    "REWRITE",
                    f"motion_term_hits={motion_hits}",
                )
            )

    if any(term in lowered for term in FORBIDDEN_DIRECT_DEPICTION_TERMS):
        issues.append(
            PromptDraftIssue(
                "RELIGIOUS_DIRECT_DEPICTION_FORBIDDEN",
                "BLOCKING",
                "Prompt contains prohibited direct-depiction language.",
            )
        )

    stack_hits = sum(
        term in lowered for term in LOW_VALUE_QUALITY_STACK
    )
    semantic_terms = len(
        re.findall(r"[A-Za-z\u0600-\u06FF]{4,}", prompt)
    )
    if stack_hits >= 3 and semantic_terms < 45:
        issues.append(
            PromptDraftIssue(
                "GENERIC_QUALITY_STACK_WITHOUT_DIRECTION",
                "REWRITE",
                f"generic_stack_hits={stack_hits}",
            )
        )

    if context:
        representation = _clean(
            context.get("representation_mode")
        ).upper()
        if representation == "SYMBOLIC_UNSEEN":
            safety_terms = (
                "symbolic",
                "non-literal",
                "non literal",
                "no visible being",
                "no personification",
                "abstract",
            )
            if not any(term in lowered for term in safety_terms):
                issues.append(
                    PromptDraftIssue(
                        "UNSEEN_SYMBOLIC_SAFETY_NOT_EXPLICIT",
                        "REWRITE",
                        "Symbolic unseen scene lacks explicit non-literal constraints.",
                    )
                )

    return tuple(issues)


def audit_storyboard_prompt_drafts(
    storyboard: Mapping[str, Any],
    *,
    strict_future_draft: bool = False,
) -> dict[str, Any]:
    shots = _all_shots(storyboard)
    if not shots:
        raise CinematicPromptDirectorError(
            "STORYBOARD_SHOTS_REQUIRED_FOR_PROMPT_AUDIT"
        )

    reports: list[dict[str, Any]] = []
    blocking: list[str] = []
    for shot in shots:
        kind = _prompt_kind(shot)
        prompt = _original_positive_prompt(shot)
        issues = list(
            audit_prompt_text(
                prompt,
                kind=kind,
                context=_context(shot),
            )
        )
        if not prompt and kind != "LOCAL_GRAPHICS_ART_DIRECTION":
            issues.append(
                PromptDraftIssue(
                    "PROVIDER_PROMPT_MISSING",
                    "BLOCKING",
                    "Image/video shot has no provider prompt draft.",
                )
            )
        for issue in issues:
            if issue.severity == "BLOCKING":
                blocking.append(
                    f"{shot.get('shot_id')}:{issue.code}"
                )
        reports.append(
            {
                "shot_id": _clean(shot.get("shot_id")),
                "prompt_kind": kind,
                "original_prompt_length": len(prompt),
                "issues": [item.as_dict() for item in issues],
                "requires_luna_rewrite": bool(issues),
            }
        )

    if strict_future_draft and blocking:
        raise CinematicPromptDirectorError(
            "STORYBOARD_PROMPT_DRAFT_BLOCKED:"
            + ",".join(blocking)
        )
    return {
        "status": "PASS_NO_BLOCKING" if not blocking else "BLOCKED",
        "shot_count": len(shots),
        "blocking_count": len(blocking),
        "reports": reports,
    }


def _prompt_item(
    shot: Mapping[str, Any],
    *,
    index: int,
) -> dict[str, Any]:
    kind = _prompt_kind(shot)
    provider, model = _provider_model(shot, kind)
    positive = _original_positive_prompt(shot)
    negative = _original_negative_prompt(shot)
    context = _context(shot)
    issues = audit_prompt_text(
        positive,
        kind=kind,
        context=context,
    )
    shot_id = _clean(shot.get("shot_id")) or f"SHOT-{index:03d}"
    return {
        "sequence": index,
        "prompt_id": f"PROMPT-{index:03d}",
        "shot_id": shot_id,
        "prompt_kind": kind,
        "provider": provider,
        "model": model,
        "original_positive_prompt_en": positive,
        "original_negative_prompt_en": negative,
        "original_prompt_sha256": _text_sha256(
            positive + "\n--NEGATIVE--\n" + negative
        ),
        "context": context,
        "deterministic_draft_audit": {
            "issues": [item.as_dict() for item in issues],
            "requires_rewrite": bool(issues) or True,
        },
        "required_decision": (
            "CREATE_FROM_CONTEXT"
            if not positive
            else "REVIEW_AND_REWRITE_IF_NEEDED"
        ),
        "status": "AWAITING_LUNA_SUPERVISION",
        "quality_threshold": QUALITY_THRESHOLD,
    }


def _estimated_cost(
    items: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    raw = json.dumps(
        list(items),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    estimated_input_tokens = max(
        1,
        math.ceil(len(raw) / 3.2),
    )
    estimated_output_tokens = len(items) * 650
    estimated = estimate_text_cost_usd(
        estimated_input_tokens,
        estimated_output_tokens,
        0,
    )
    return {
        "pricing_snapshot": {
            "model": LUNA_MODEL,
            "input_usd_per_million": (
                LUNA_INPUT_USD_PER_MILLION
            ),
            "output_usd_per_million": (
                LUNA_OUTPUT_USD_PER_MILLION
            ),
        },
        "estimated_input_tokens": estimated_input_tokens,
        "estimated_output_tokens": estimated_output_tokens,
        "estimated_cost_usd": round(estimated, 6),
    }


def prepare_episode_prompt_plan(
    repo_root: Path,
    episode_id: str = EPISODE_ID,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    episode_root = repo / "projects" / episode_id
    storyboard_path = episode_root / STANDARD_STORYBOARD_REL
    storyboard = _read_json(storyboard_path)
    shots = _all_shots(storyboard)
    if len(shots) != 70:
        raise CinematicPromptDirectorError(
            f"EXPECTED_70_SHOTS_FOR_PROMPT_DIRECTION:{len(shots)}"
        )

    items = [
        _prompt_item(shot, index=index)
        for index, shot in enumerate(shots, start=1)
    ]
    batches: list[dict[str, Any]] = []
    for batch_index, start in enumerate(
        range(0, len(items), BATCH_SIZE),
        start=1,
    ):
        batch_items = items[start : start + BATCH_SIZE]
        batch_id = f"LUNA-PROMPT-BATCH-{batch_index:02d}"
        cost = _estimated_cost(batch_items)
        batches.append(
            {
                "batch_id": batch_id,
                "sequence": batch_index,
                "prompt_ids": [
                    str(item["prompt_id"])
                    for item in batch_items
                ],
                "shot_ids": [
                    str(item["shot_id"])
                    for item in batch_items
                ],
                "item_count": len(batch_items),
                "status": "AWAITING_CONSOLIDATED_AUTHORIZATION",
                "maximum_provider_requests": 1,
                "maximum_authorized_usd": (
                    MAXIMUM_BATCH_RESERVE_USD
                ),
                "automatic_retry": "FORBIDDEN",
                "hidden_paid_retry": "FORBIDDEN",
                "cost_estimate": cost,
                "request_path_relative": str(
                    PROMPT_REQUEST_DIR_REL
                    / f"{batch_id}.json"
                ).replace("\\", "/"),
                "response_path_relative": str(
                    PROMPT_RESPONSE_DIR_REL
                    / f"{batch_id}.json"
                ).replace("\\", "/"),
            }
        )
        for item in batch_items:
            item["batch_id"] = batch_id

    estimated_cost_total = round(
        sum(
            float(
                batch["cost_estimate"]["estimated_cost_usd"]
            )
            for batch in batches
        ),
        6,
    )
    plan = {
        "schema_version": SCHEMA_VERSION,
        "release": RELEASE,
        "episode_id": episode_id,
        "status": (
            "AWAITING_CONSOLIDATED_LUNA_PROMPT_AND_FULL_EPISODE_"
            "AUTHORIZATION"
        ),
        "source_storyboard_path_relative": str(
            STANDARD_STORYBOARD_REL
        ).replace("\\", "/"),
        "source_storyboard_sha256": _canonical_sha256(storyboard),
        "certified_storyboard_path_relative": str(
            CERTIFIED_STORYBOARD_REL
        ).replace("\\", "/"),
        "prompt_item_count": len(items),
        "batch_size": BATCH_SIZE,
        "batch_count": len(batches),
        "maximum_luna_requests": len(batches),
        "quality_threshold": QUALITY_THRESHOLD,
        "luna_model": LUNA_MODEL,
        "prompt_authorship_policy": (
            "CREATED_BY_LUNA_OR_REVIEWED_AND_REWRITTEN_BY_LUNA"
        ),
        "provider_execution_without_certification": "FORBIDDEN",
        "internal_self_revision_within_same_response": "REQUIRED",
        "automatic_additional_luna_request": "FORBIDDEN",
        "hidden_paid_retry": "FORBIDDEN",
        "estimated_cost_usd": estimated_cost_total,
        "maximum_authorized_usd": (
            PROMPT_DIRECTOR_TOTAL_RESERVE_USD
        ),
        "full_episode_production_authorized": False,
        "items": items,
        "batches": batches,
        "created_at_utc": _now(),
        "next_stage": (
            "CONSOLIDATED_LUNA_PROMPT_AND_FULL_EPISODE_AUTHORIZATION"
        ),
    }
    _write_json(episode_root / PROMPT_PLAN_REL, plan)

    for batch in batches:
        request = build_luna_batch_request(
            plan,
            str(batch["batch_id"]),
        )
        _write_json(
            episode_root
            / PROMPT_REQUEST_DIR_REL
            / f"{batch['batch_id']}.json",
            request,
        )

    readiness = {
        "schema_version": (
            "siraj-luna-prompt-direction-readiness-v2"
        ),
        "release": RELEASE,
        "episode_id": episode_id,
        "status": plan["status"],
        "prompt_item_count": len(items),
        "batch_count": len(batches),
        "maximum_luna_requests": len(batches),
        "estimated_cost_usd": estimated_cost_total,
        "maximum_authorized_usd": (
            PROMPT_DIRECTOR_TOTAL_RESERVE_USD
        ),
        "provider_requests_during_preparation": 0,
        "paid_provider_requests_during_preparation": 0,
        "certified_prompt_count": 0,
        "full_episode_production_authorized": False,
        "next_stage": plan["next_stage"],
    }
    _write_json(episode_root / PROMPT_READINESS_REL, readiness)
    _update_standard_snapshots(
        repo,
        episode_id,
        prompt_status=plan["status"],
        certified_count=0,
        batch_count=len(batches),
    )
    return plan


def prompt_output_schema(
    item_count: int,
) -> dict[str, Any]:
    score_properties = {
        name: {
            "type": "integer",
            "minimum": 0,
            "maximum": 10,
        }
        for name in (
            "narrative_function",
            "subject_and_action_clarity",
            "composition_and_depth",
            "camera_and_lens",
            "lighting_and_color",
            "materials_and_atmosphere",
            "motion_and_temporal_logic",
            "continuity",
            "provider_specificity",
            "religious_safety_and_artifact_prevention",
        )
    }
    blueprint_properties = {
        key: {"type": "string", "minLength": 3}
        for key in (
            "subject",
            "action",
            "environment",
            "composition",
            "camera",
            "lens",
            "lighting",
            "color_palette",
            "materials",
            "atmosphere",
            "temporal_motion",
            "continuity",
            "safety",
        )
    }
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "prompt_id",
            "shot_id",
            "prompt_kind",
            "decision",
            "rewrite_iterations_internal",
            "rewrite_reason_ar",
            "art_direction_ar",
            "final_positive_prompt_en",
            "final_negative_prompt_en",
            "negative_prompt_delivery",
            "cinematic_blueprint",
            "quality_scores",
            "final_score",
            "blocking_flags",
        ],
        "properties": {
            "prompt_id": {"type": "string"},
            "shot_id": {"type": "string"},
            "prompt_kind": {
                "type": "string",
                "enum": [
                    "VIDEO_GENERATION",
                    "IMAGE_GENERATION",
                    "LOCAL_GRAPHICS_ART_DIRECTION",
                ],
            },
            "decision": {
                "type": "string",
                "enum": [
                    "CREATED_BY_LUNA",
                    "REWRITTEN_BY_LUNA",
                    "APPROVED_BY_LUNA_AFTER_REVIEW",
                ],
            },
            "rewrite_iterations_internal": {
                "type": "integer",
                "minimum": 1,
                "maximum": 4,
            },
            "rewrite_reason_ar": {
                "type": "string",
                "minLength": 5,
            },
            "art_direction_ar": {
                "type": "string",
                "minLength": 20,
            },
            "final_positive_prompt_en": {
                "type": "string",
                "minLength": 160,
                "maxLength": 2600,
            },
            "final_negative_prompt_en": {
                "type": "string",
                "maxLength": 1400,
            },
            "negative_prompt_delivery": {
                "type": "string",
                "enum": [
                    "SEPARATE_PROVIDER_FIELD",
                    "EMBEDDED_AS_POSITIVE_CONSTRAINTS",
                    "NOT_APPLICABLE_LOCAL_GRAPHICS",
                ],
            },
            "cinematic_blueprint": {
                "type": "object",
                "additionalProperties": False,
                "required": list(blueprint_properties),
                "properties": blueprint_properties,
            },
            "quality_scores": {
                "type": "object",
                "additionalProperties": False,
                "required": list(score_properties),
                "properties": score_properties,
            },
            "final_score": {
                "type": "integer",
                "minimum": QUALITY_THRESHOLD,
                "maximum": 100,
            },
            "blocking_flags": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 0,
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "batch_id",
            "director_summary_ar",
            "items",
        ],
        "properties": {
            "batch_id": {"type": "string"},
            "director_summary_ar": {
                "type": "string",
                "minLength": 20,
            },
            "items": {
                "type": "array",
                "items": item,
                "minItems": item_count,
                "maxItems": item_count,
            },
        },
    }


def _system_prompt() -> str:
    return """أنت LUNA، مدير البرومبتات والمخرج البصري الأعلى لسلسلة سراج.
مهمتك ليست تحسين الصياغة شكليًا، بل كتابة أو إعادة كتابة كل برومبت ليصبح
تعليمات إنتاج فاخرة قابلة للتنفيذ بمستوى مسلسل تاريخي سينمائي عالمي.

اعمل داخل الاستجابة نفسها بهذه الدورة لكل عنصر:
1) افهم وظيفته الدرامية ومكانه في التسلسل.
2) اكتب مسودة داخلية.
3) انتقدها من منظور المخرج ومدير التصوير ومهندس المولد.
4) أعد كتابتها حتى تتجاوز 95/100.
5) أخرج النسخة النهائية فقط مع سجل القرار والتقييم.

قواعد إلزامية:
- البرومبت النهائي بالإنجليزية العملية، بلا Markdown وبلا حشو تسويقي.
- لا تعتمد على كلمات masterpiece و8K وbest quality بدل الإخراج الحقيقي.
- عرّف الموضوع والفعل والبيئة والتكوين والعمق والكاميرا والعدسة والإضاءة
  واللون والخامات والجو والاستمرارية والمخاطر.
- للفيديو: صف بداية الحركة ووسطها ونهايتها، حركة الموضوع والكاميرا،
  الفيزياء، السرعة، وما يجب أن يبقى ثابتًا. امنع morphing وflicker
  والتشوه والقفزات الزمنية والحركة العشوائية.
- للصورة: أنشئ تسلسل عمق واضحًا بين foreground وmidground وbackground،
  بؤرة بصرية واحدة، وعدسة وإضاءة وخامات قابلة للرؤية.
- للجرافيك المحلي: قدّم art direction دقيقًا للتكوين والخط والحركة
  واللون والتسلسل البصري، من دون تحويله إلى Prompt لمولد صور.
- احفظ هوية اللقطة، العالم، اتجاه الشاشة، الإضاءة، لوحة اللون، الخامات،
  المقياس والصورة الظلية كما وردت في continuity_lock_v2.
- لا تخترع معلومة تاريخية أو دينية غير موجودة في السياق.
- لا تجسد الله تعالى أو الأنبياء أو الملائكة أو إبليس تجسيدًا مباشرًا.
- العالم الغيبي رمزي وغير جازم، بلا كائن مرئي أو هيئة حرفية.
- لا موسيقى ولا إشارة إلى musical score.
- Seedream لا يستقبل negativePrompt منفصلًا؛ ادمج المنع داخل البرومبت
  الإيجابي بصياغة طبيعية واضبط negative_prompt_delivery وفق ذلك.
- لا تتعارض تعليمات العدسة والكاميرا، ولا تطلب أكثر من مركز بصري رئيسي.
- blocking_flags يجب أن تكون فارغة؛ إن وجدت مشكلة فأعد الكتابة داخليًا.
أخرج JSON فقط وفق المخطط الصارم."""


def build_luna_batch_request(
    plan: Mapping[str, Any],
    batch_id: str,
) -> dict[str, Any]:
    batches = [
        item
        for item in _sequence(plan.get("batches"))
        if isinstance(item, Mapping)
        and str(item.get("batch_id")) == batch_id
    ]
    if len(batches) != 1:
        raise CinematicPromptDirectorError(
            f"PROMPT_BATCH_NOT_FOUND:{batch_id}"
        )
    batch = batches[0]
    prompt_ids = set(
        str(value)
        for value in _sequence(batch.get("prompt_ids"))
    )
    items = [
        item
        for item in _sequence(plan.get("items"))
        if isinstance(item, Mapping)
        and str(item.get("prompt_id")) in prompt_ids
    ]
    items.sort(key=lambda item: int(item.get("sequence", 0)))
    if len(items) != int(batch.get("item_count", 0)):
        raise CinematicPromptDirectorError(
            f"PROMPT_BATCH_ITEM_COUNT_MISMATCH:{batch_id}"
        )

    user_payload = {
        "task": "CREATE_OR_SUPERVISE_PREMIUM_CINEMATIC_PROMPTS",
        "episode_id": plan.get("episode_id"),
        "batch_id": batch_id,
        "quality_threshold": QUALITY_THRESHOLD,
        "series_identity": {
            "channel": "سراج",
            "quality_mode": "GLOBAL_PRESTIGE_CINEMATIC",
            "genre": "HISTORICAL_RELIGIOUS_DOCUMENTARY_DRAMA",
            "music": "FORBIDDEN",
            "visual_style": (
                "PHOTOREAL_RESTRAINED_PRESTIGE_CINEMATIC"
            ),
        },
        "items": items,
    }
    return {
        "model": LUNA_MODEL,
        "store": False,
        "reasoning": {"effort": "high"},
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": _system_prompt(),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            user_payload,
                            ensure_ascii=False,
                            indent=2,
                        ),
                    }
                ],
            },
        ],
        "max_output_tokens": 45000,
        "text": {
            "verbosity": "high",
            "format": {
                "type": "json_schema",
                "name": "siraj_luna_cinematic_prompt_batch_v2",
                "strict": True,
                "schema": prompt_output_schema(len(items)),
            },
        },
        "siraj_authorization": {
            "maximum_provider_requests": 1,
            "maximum_authorized_usd": (
                MAXIMUM_BATCH_RESERVE_USD
            ),
            "automatic_retry": "FORBIDDEN",
            "hidden_paid_retry": "FORBIDDEN",
        },
    }


def _extract_output_text(response: Mapping[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    texts: list[str] = []
    for item in _sequence(response.get("output")):
        if not isinstance(item, Mapping):
            continue
        for part in _sequence(item.get("content")):
            if not isinstance(part, Mapping):
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
    if not texts:
        raise CinematicPromptDirectorError(
            "LUNA_PROMPT_OUTPUT_TEXT_MISSING"
        )
    return "\n".join(texts)


def _usage(
    response: Mapping[str, Any],
) -> tuple[int, int, int]:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return 0, 0, 0
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    details = usage.get("input_tokens_details")
    cached = (
        int(details.get("cached_tokens", 0) or 0)
        if isinstance(details, Mapping)
        else 0
    )
    return input_tokens, output_tokens, cached


def _post_once(
    api_key: str,
    request_payload: Mapping[str, Any],
) -> dict[str, Any]:
    if not api_key.strip():
        raise CinematicPromptDirectorError(
            "OPENAI_API_KEY_REQUIRED"
        )
    provider_payload = {
        key: value
        for key, value in request_payload.items()
        if key != "siraj_authorization"
    }
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(
            provider_payload,
            ensure_ascii=False,
        ).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode(
            "utf-8",
            errors="replace",
        )
        raise CinematicPromptDirectorError(
            f"LUNA_PROMPT_HTTP_ERROR_NO_AUTO_RETRY:{exc.code}:{body}"
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CinematicPromptDirectorError(
            f"LUNA_PROMPT_NETWORK_ERROR_NO_AUTO_RETRY:{exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise CinematicPromptDirectorError(
            "LUNA_PROMPT_INVALID_JSON_RESPONSE"
        ) from exc
    if not isinstance(value, dict):
        raise CinematicPromptDirectorError(
            "LUNA_PROMPT_RESPONSE_OBJECT_REQUIRED"
        )
    return value


def _validate_scores(item: Mapping[str, Any]) -> None:
    scores = item.get("quality_scores")
    if not isinstance(scores, Mapping):
        raise CinematicPromptDirectorError(
            "PROMPT_QUALITY_SCORES_REQUIRED"
        )
    expected = {
        "narrative_function",
        "subject_and_action_clarity",
        "composition_and_depth",
        "camera_and_lens",
        "lighting_and_color",
        "materials_and_atmosphere",
        "motion_and_temporal_logic",
        "continuity",
        "provider_specificity",
        "religious_safety_and_artifact_prevention",
    }
    if set(scores) != expected:
        raise CinematicPromptDirectorError(
            "PROMPT_QUALITY_SCORE_DIMENSIONS_CHANGED"
        )
    if any(
        not isinstance(value, int) or value < 8
        for value in scores.values()
    ):
        raise CinematicPromptDirectorError(
            "PROMPT_QUALITY_DIMENSION_BELOW_EIGHT"
        )
    final_score = int(item.get("final_score", 0))
    if final_score < QUALITY_THRESHOLD:
        raise CinematicPromptDirectorError(
            f"PROMPT_FINAL_SCORE_BELOW_THRESHOLD:{final_score}"
        )


def validate_luna_batch_output(
    plan: Mapping[str, Any],
    batch_id: str,
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if str(payload.get("batch_id")) != batch_id:
        raise CinematicPromptDirectorError(
            "PROMPT_BATCH_ID_MISMATCH"
        )
    batch = next(
        (
            item
            for item in _sequence(plan.get("batches"))
            if isinstance(item, Mapping)
            and str(item.get("batch_id")) == batch_id
        ),
        None,
    )
    if not isinstance(batch, Mapping):
        raise CinematicPromptDirectorError(
            f"PROMPT_BATCH_NOT_FOUND:{batch_id}"
        )
    expected_ids = list(
        str(value)
        for value in _sequence(batch.get("prompt_ids"))
    )
    output_items = [
        dict(item)
        for item in _sequence(payload.get("items"))
        if isinstance(item, Mapping)
    ]
    if [str(item.get("prompt_id")) for item in output_items] != (
        expected_ids
    ):
        raise CinematicPromptDirectorError(
            "PROMPT_OUTPUT_ITEMS_OR_ORDER_MISMATCH"
        )
    plan_items = {
        str(item.get("prompt_id")): item
        for item in _sequence(plan.get("items"))
        if isinstance(item, Mapping)
    }

    for item in output_items:
        prompt_id = str(item.get("prompt_id"))
        source = plan_items[prompt_id]
        if str(item.get("shot_id")) != str(source.get("shot_id")):
            raise CinematicPromptDirectorError(
                f"PROMPT_SHOT_ID_MISMATCH:{prompt_id}"
            )
        if str(item.get("prompt_kind")) != str(
            source.get("prompt_kind")
        ):
            raise CinematicPromptDirectorError(
                f"PROMPT_KIND_MISMATCH:{prompt_id}"
            )
        if list(_sequence(item.get("blocking_flags"))):
            raise CinematicPromptDirectorError(
                f"PROMPT_BLOCKING_FLAGS_NOT_EMPTY:{prompt_id}"
            )
        _validate_scores(item)
        final_positive = _clean(
            item.get("final_positive_prompt_en")
        )
        issues = audit_prompt_text(
            final_positive,
            kind=str(item.get("prompt_kind")),
            context=source.get("context")
            if isinstance(source.get("context"), Mapping)
            else None,
        )
        blocking = [
            issue
            for issue in issues
            if issue.severity == "BLOCKING"
        ]
        if blocking:
            raise CinematicPromptDirectorError(
                f"CERTIFIED_PROMPT_STILL_BLOCKED:{prompt_id}:"
                + ",".join(issue.code for issue in blocking)
            )
        if len(final_positive) < 160:
            raise CinematicPromptDirectorError(
                f"CERTIFIED_PROMPT_TOO_SHORT:{prompt_id}"
            )
        model = str(source.get("model"))
        delivery = str(item.get("negative_prompt_delivery"))
        if model == "bytedance:seedream@5.0-pro":
            if delivery != "EMBEDDED_AS_POSITIVE_CONSTRAINTS":
                raise CinematicPromptDirectorError(
                    f"SEEDREAM_NEGATIVE_MODE_INVALID:{prompt_id}"
                )
        if str(item.get("prompt_kind")) == (
            "LOCAL_GRAPHICS_ART_DIRECTION"
        ):
            if delivery != "NOT_APPLICABLE_LOCAL_GRAPHICS":
                raise CinematicPromptDirectorError(
                    f"GRAPHICS_NEGATIVE_MODE_INVALID:{prompt_id}"
                )
    return output_items


def execute_authorized_batch(
    repo_root: Path,
    *,
    episode_id: str,
    batch_id: str,
    api_key: str,
    confirmed_maximum_usd: float,
) -> dict[str, Any]:
    if abs(
        float(confirmed_maximum_usd)
        - MAXIMUM_BATCH_RESERVE_USD
    ) > 1e-9:
        raise CinematicPromptDirectorError(
            "PROMPT_BATCH_AUTHORIZATION_MAXIMUM_MISMATCH"
        )
    repo = repo_root.resolve()
    episode_root = repo / "projects" / episode_id
    plan_path = episode_root / PROMPT_PLAN_REL
    plan = _read_json(plan_path)
    batch = next(
        (
            item
            for item in _sequence(plan.get("batches"))
            if isinstance(item, Mapping)
            and str(item.get("batch_id")) == batch_id
        ),
        None,
    )
    if not isinstance(batch, dict):
        raise CinematicPromptDirectorError(
            f"PROMPT_BATCH_NOT_FOUND:{batch_id}"
        )
    if str(batch.get("status")) == "COMPLETE":
        response_path = (
            episode_root
            / PROMPT_RESPONSE_DIR_REL
            / f"{batch_id}.json"
        )
        if response_path.is_file():
            return {
                "status": "COMPLETE_EXISTING_RESULT_REUSED",
                "batch_id": batch_id,
                "provider_requests_this_run": 0,
            }
    if str(batch.get("status")) != (
        "AWAITING_CONSOLIDATED_AUTHORIZATION"
    ):
        raise CinematicPromptDirectorError(
            f"PROMPT_BATCH_NOT_AUTHORIZABLE:{batch.get('status')}"
        )

    request_path = (
        episode_root / PROMPT_REQUEST_DIR_REL / f"{batch_id}.json"
    )
    request_payload = _read_json(request_path)
    lock_path = (
        episode_root / PROMPT_LOCK_DIR_REL / f"{batch_id}.json"
    )
    response_path = (
        episode_root
        / PROMPT_RESPONSE_DIR_REL
        / f"{batch_id}.json"
    )
    receipt_path = (
        episode_root
        / PROMPT_RECEIPT_DIR_REL
        / f"{batch_id}-receipt.json"
    )
    if lock_path.exists():
        raise CinematicPromptDirectorError(
            "PROMPT_BATCH_ALREADY_LOCKED_NO_AUTOMATIC_RETRY"
        )

    lock = {
        "schema_version": "siraj-luna-prompt-batch-lock-v2",
        "release": RELEASE,
        "episode_id": episode_id,
        "batch_id": batch_id,
        "status": "LOCKED_BEFORE_NETWORK",
        "maximum_provider_requests": 1,
        "provider_requests_made": 0,
        "maximum_authorized_usd": (
            MAXIMUM_BATCH_RESERVE_USD
        ),
        "request_payload_sha256": _canonical_sha256(
            request_payload
        ),
        "automatic_retry": "FORBIDDEN",
        "hidden_paid_retry": "FORBIDDEN",
        "created_at_utc": _now(),
    }
    _write_json(lock_path, lock)

    lock["status"] = "NETWORK_REQUEST_STARTED"
    lock["provider_requests_made"] = 1
    lock["network_started_at_utc"] = _now()
    _write_json(lock_path, lock)

    try:
        response = _post_once(api_key, request_payload)
    except CinematicPromptDirectorError as exc:
        lock["status"] = (
            "NETWORK_OR_PROVIDER_RESULT_UNKNOWN_NO_AUTOMATIC_RETRY"
        )
        lock["last_error"] = str(exc)
        lock["updated_at_utc"] = _now()
        _write_json(lock_path, lock)
        raise

    text = _extract_output_text(response)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        lock["status"] = (
            "INVALID_LUNA_OUTPUT_NO_AUTOMATIC_RETRY"
        )
        lock["last_error"] = "LUNA_OUTPUT_JSON_INVALID"
        _write_json(lock_path, lock)
        raise CinematicPromptDirectorError(
            "LUNA_OUTPUT_JSON_INVALID"
        ) from exc
    if not isinstance(payload, dict):
        raise CinematicPromptDirectorError(
            "LUNA_OUTPUT_OBJECT_REQUIRED"
        )
    items = validate_luna_batch_output(
        plan,
        batch_id,
        payload,
    )
    input_tokens, output_tokens, cached_tokens = _usage(response)
    estimated_cost = estimate_text_cost_usd(
        input_tokens,
        output_tokens,
        cached_tokens,
    )
    if estimated_cost > (
        MAXIMUM_BATCH_RESERVE_USD + 1e-9
    ):
        raise CinematicPromptDirectorError(
            f"PROMPT_BATCH_ESTIMATED_COST_EXCEEDED:"
            f"{estimated_cost:.6f}"
        )

    response_record = {
        "schema_version": (
            "siraj-luna-prompt-batch-response-v2"
        ),
        "release": RELEASE,
        "episode_id": episode_id,
        "batch_id": batch_id,
        "provider": "OPENAI",
        "model": LUNA_MODEL,
        "response_id": str(response.get("id") or ""),
        "payload": payload,
        "captured_at_utc": _now(),
    }
    _write_json(response_path, response_record)

    receipt = {
        "schema_version": (
            "siraj-luna-prompt-batch-receipt-v2"
        ),
        "release": RELEASE,
        "episode_id": episode_id,
        "batch_id": batch_id,
        "status": "COMPLETE",
        "provider": "OPENAI",
        "model": LUNA_MODEL,
        "response_id": response_record["response_id"],
        "provider_requests": 1,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_tokens,
        "estimated_cost_usd": round(estimated_cost, 8),
        "maximum_authorized_usd": (
            MAXIMUM_BATCH_RESERVE_USD
        ),
        "item_count": len(items),
        "response_payload_sha256": _canonical_sha256(payload),
        "automatic_retry": "FORBIDDEN",
        "hidden_paid_retry": "FORBIDDEN",
        "completed_at_utc": _now(),
    }
    _write_json(receipt_path, receipt)

    lock["status"] = "COMPLETE"
    lock["response_id"] = response_record["response_id"]
    lock["receipt_path_relative"] = str(
        receipt_path.relative_to(repo)
    ).replace("\\", "/")
    lock["completed_at_utc"] = _now()
    _write_json(lock_path, lock)

    batch["status"] = "COMPLETE"
    batch["response_id"] = response_record["response_id"]
    batch["receipt_path_relative"] = str(
        receipt_path.relative_to(repo)
    ).replace("\\", "/")
    batch["estimated_cost_usd"] = round(
        estimated_cost,
        8,
    )
    plan["updated_at_utc"] = _now()
    if all(
        str(item.get("status")) == "COMPLETE"
        for item in _sequence(plan.get("batches"))
        if isinstance(item, Mapping)
    ):
        plan["status"] = "ALL_LUNA_BATCHES_COMPLETE_READY_TO_CERTIFY"
    _write_json(plan_path, plan)
    return {
        "status": "COMPLETE",
        "batch_id": batch_id,
        "response_id": response_record["response_id"],
        "provider_requests_this_run": 1,
        "estimated_cost_usd": round(estimated_cost, 8),
    }


def _certification(
    source_item: Mapping[str, Any],
    output_item: Mapping[str, Any],
    response_id: str,
    batch_id: str,
) -> dict[str, Any]:
    positive = _clean(
        output_item.get("final_positive_prompt_en")
    )
    negative = _clean(
        output_item.get("final_negative_prompt_en")
    )
    return {
        "schema_version": (
            "siraj-luna-prompt-certification-v2"
        ),
        "release": RELEASE,
        "status": "PASS",
        "prompt_id": source_item.get("prompt_id"),
        "shot_id": source_item.get("shot_id"),
        "prompt_kind": source_item.get("prompt_kind"),
        "provider": source_item.get("provider"),
        "model": source_item.get("model"),
        "authorship": output_item.get("decision"),
        "luna_model": LUNA_MODEL,
        "luna_response_id": response_id,
        "luna_batch_id": batch_id,
        "rewrite_iterations_internal": output_item.get(
            "rewrite_iterations_internal"
        ),
        "rewrite_reason_ar": output_item.get(
            "rewrite_reason_ar"
        ),
        "art_direction_ar": output_item.get(
            "art_direction_ar"
        ),
        "cinematic_blueprint": output_item.get(
            "cinematic_blueprint"
        ),
        "quality_scores": output_item.get("quality_scores"),
        "final_score": int(output_item.get("final_score", 0)),
        "quality_threshold": QUALITY_THRESHOLD,
        "blocking_flags": [],
        "certified_positive_prompt_en": positive,
        "certified_negative_prompt_en": negative,
        "negative_prompt_delivery": output_item.get(
            "negative_prompt_delivery"
        ),
        "positive_prompt_sha256": _text_sha256(positive),
        "negative_prompt_sha256": _text_sha256(negative),
        "source_prompt_sha256": source_item.get(
            "original_prompt_sha256"
        ),
        "certified_at_utc": _now(),
    }


def finalize_certified_storyboard(
    repo_root: Path,
    *,
    episode_id: str,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    episode_root = repo / "projects" / episode_id
    plan_path = episode_root / PROMPT_PLAN_REL
    plan = _read_json(plan_path)
    if str(plan.get("status")) not in {
        "ALL_LUNA_BATCHES_COMPLETE_READY_TO_CERTIFY",
        "CERTIFIED_COMPLETE",
    }:
        raise CinematicPromptDirectorError(
            f"PROMPT_BATCHES_NOT_COMPLETE:{plan.get('status')}"
        )
    source_storyboard = _read_json(
        episode_root / STANDARD_STORYBOARD_REL
    )
    source_items = {
        str(item.get("prompt_id")): item
        for item in _sequence(plan.get("items"))
        if isinstance(item, Mapping)
    }
    certifications_by_shot: dict[str, dict[str, Any]] = {}

    for batch in _sequence(plan.get("batches")):
        if not isinstance(batch, Mapping):
            continue
        batch_id = str(batch.get("batch_id"))
        response_path = (
            episode_root
            / PROMPT_RESPONSE_DIR_REL
            / f"{batch_id}.json"
        )
        response = _read_json(response_path)
        payload = response.get("payload")
        if not isinstance(payload, Mapping):
            raise CinematicPromptDirectorError(
                f"PROMPT_RESPONSE_PAYLOAD_MISSING:{batch_id}"
            )
        output_items = validate_luna_batch_output(
            plan,
            batch_id,
            payload,
        )
        response_id = str(response.get("response_id") or "")
        if not response_id:
            raise CinematicPromptDirectorError(
                f"LUNA_RESPONSE_ID_REQUIRED:{batch_id}"
            )
        for output_item in output_items:
            prompt_id = str(output_item.get("prompt_id"))
            source_item = source_items[prompt_id]
            certification = _certification(
                source_item,
                output_item,
                response_id,
                batch_id,
            )
            certifications_by_shot[
                str(source_item.get("shot_id"))
            ] = certification

    if len(certifications_by_shot) != 70:
        raise CinematicPromptDirectorError(
            f"EXPECTED_70_CERTIFICATIONS:"
            f"{len(certifications_by_shot)}"
        )

    certified = deepcopy(source_storyboard)
    count = 0
    for shot_list in _shot_lists(certified):
        for index, raw in enumerate(list(shot_list)):
            if not isinstance(raw, Mapping):
                raise CinematicPromptDirectorError(
                    "CERTIFIED_STORYBOARD_SHOT_INVALID"
                )
            shot = dict(raw)
            shot_id = _clean(shot.get("shot_id"))
            certification = certifications_by_shot.get(shot_id)
            if certification is None:
                raise CinematicPromptDirectorError(
                    f"PROMPT_CERTIFICATION_MISSING:{shot_id}"
                )
            shot["luna_prompt_certification_v2"] = certification
            shot["runware_positive_prompt_en"] = certification[
                "certified_positive_prompt_en"
            ]
            shot["runware_negative_prompt_en"] = certification[
                "certified_negative_prompt_en"
            ]
            shot["prompt_director_status"] = "PASS"
            shot_list[index] = shot
            count += 1

    certified["schema_version"] = (
        "siraj-storyboard-and-media-plan-luna-certified-v2"
    )
    certified["status"] = (
        "LUNA_PROMPTS_CERTIFIED_READY_FOR_PROVIDER_EXECUTION"
    )
    certified["luna_prompt_direction_v2"] = {
        "release": RELEASE,
        "certified_prompt_count": count,
        "quality_threshold": QUALITY_THRESHOLD,
        "provider_execution_without_certification": "FORBIDDEN",
        "source_storyboard_sha256": plan.get(
            "source_storyboard_sha256"
        ),
        "plan_sha256": _canonical_sha256(plan),
        "completed_at_utc": _now(),
    }
    certified_path = episode_root / CERTIFIED_STORYBOARD_REL
    _write_json(certified_path, certified)

    _apply_to_media_queue(
        episode_root,
        certifications_by_shot,
    )

    plan["status"] = "CERTIFIED_COMPLETE"
    plan["certified_prompt_count"] = count
    plan["certified_storyboard_sha256"] = _canonical_sha256(
        certified
    )
    plan["certified_storyboard_path_relative"] = str(
        CERTIFIED_STORYBOARD_REL
    ).replace("\\", "/")
    plan["full_episode_production_authorized"] = False
    plan["next_stage"] = (
        "CONSOLIDATED_FULL_EPISODE_REBUILD_AUTHORIZATION"
    )
    plan["completed_at_utc"] = _now()
    _write_json(plan_path, plan)

    readiness = {
        "schema_version": (
            "siraj-luna-prompt-direction-readiness-v2"
        ),
        "release": RELEASE,
        "episode_id": episode_id,
        "status": "PASS_CERTIFIED_COMPLETE",
        "prompt_item_count": count,
        "certified_prompt_count": count,
        "quality_threshold": QUALITY_THRESHOLD,
        "provider_execution_guard": "ACTIVE",
        "full_episode_production_authorized": False,
        "next_stage": (
            "CONSOLIDATED_FULL_EPISODE_REBUILD_AUTHORIZATION"
        ),
    }
    _write_json(episode_root / PROMPT_READINESS_REL, readiness)
    _update_standard_snapshots(
        repo,
        episode_id,
        prompt_status="PASS_CERTIFIED_COMPLETE",
        certified_count=count,
        batch_count=int(plan.get("batch_count", 0)),
    )
    return {
        "status": "PASS_CERTIFIED_COMPLETE",
        "episode_id": episode_id,
        "certified_prompt_count": count,
        "certified_storyboard_path": str(certified_path),
        "provider_requests": 0,
        "full_episode_production_authorized": False,
    }


def _apply_to_media_queue(
    episode_root: Path,
    certifications_by_shot: Mapping[str, Mapping[str, Any]],
) -> None:
    queue_path = episode_root / MEDIA_QUEUE_REL
    if not queue_path.is_file():
        return
    queue = _read_json(queue_path)
    queues = queue.get("queues")
    if not isinstance(queues, dict):
        return
    for collection in ("runware_images", "runware_videos"):
        values = queues.get(collection)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            shot_id = _clean(item.get("shot_id"))
            certification = certifications_by_shot.get(shot_id)
            if not isinstance(certification, Mapping):
                continue
            item["luna_prompt_certification_v2"] = deepcopy(
                dict(certification)
            )
            task = item.get("task_draft")
            if isinstance(task, dict):
                task["positivePrompt"] = certification[
                    "certified_positive_prompt_en"
                ]
                delivery = str(
                    certification.get(
                        "negative_prompt_delivery"
                    )
                )
                negative = _clean(
                    certification.get(
                        "certified_negative_prompt_en"
                    )
                )
                if (
                    negative
                    and delivery == "SEPARATE_PROVIDER_FIELD"
                ):
                    task["negativePrompt"] = negative
                else:
                    task.pop("negativePrompt", None)
            item["prompt_director_status"] = "PASS"
    queue["luna_prompt_direction_v2"] = {
        "release": RELEASE,
        "status": "PASS",
        "certified_prompt_count": len(
            certifications_by_shot
        ),
        "provider_execution_without_certification": "FORBIDDEN",
        "updated_at_utc": _now(),
    }
    _write_json(queue_path, queue)


def _update_standard_snapshots(
    repo: Path,
    episode_id: str,
    *,
    prompt_status: str,
    certified_count: int,
    batch_count: int,
) -> None:
    episode_root = repo / "projects" / episode_id
    readiness_path = episode_root / STANDARD_READINESS_REL
    if readiness_path.is_file():
        readiness = _read_json(readiness_path)
        readiness["prompt_direction"] = {
            "release": RELEASE,
            "status": prompt_status,
            "certified_prompt_count": certified_count,
            "required_prompt_count": 70,
            "batch_count": batch_count,
            "quality_threshold": QUALITY_THRESHOLD,
            "provider_execution_without_certification": "FORBIDDEN",
        }
        readiness["full_episode_production_authorized"] = False
        readiness["next_stage"] = (
            "CONSOLIDATED_LUNA_PROMPT_AND_FULL_EPISODE_AUTHORIZATION"
            if certified_count < 70
            else "CONSOLIDATED_FULL_EPISODE_REBUILD_AUTHORIZATION"
        )
        _write_json(readiness_path, readiness)

    snapshot_path = episode_root / DESKTOP_SNAPSHOT_REL
    if snapshot_path.is_file():
        snapshot = _read_json(snapshot_path)
        snapshot["prompt_direction"] = {
            "status": prompt_status,
            "certified": certified_count,
            "required": 70,
            "batches": batch_count,
            "quality_threshold": QUALITY_THRESHOLD,
        }
        snapshot["next_action_ar"] = (
            "تفويض لونا لمراجعة وكتابة البرومبتات ثم إنتاج الحلقة"
            if certified_count < 70
            else "إنتاج الحلقة كاملة من جديد"
        )
        snapshot["full_episode_production_authorized"] = False
        snapshot["updated_at_utc"] = _now()
        _write_json(snapshot_path, snapshot)

    series_path = repo / SERIES_STANDARD_REL
    if series_path.is_file():
        standard = _read_json(series_path)
        standard["prompt_direction"] = {
            "release": RELEASE,
            "owner": "GPT-5.6_LUNA",
            "scope": "ALL_PROVIDER_AND_GENERATION_PROMPTS",
            "policy": (
                "CREATED_BY_LUNA_OR_REVIEWED_AND_REWRITTEN_BY_LUNA"
            ),
            "quality_threshold": QUALITY_THRESHOLD,
            "internal_self_revision": "REQUIRED",
            "provider_execution_without_certification": "FORBIDDEN",
            "automatic_additional_paid_request": "FORBIDDEN",
            "negative_prompt_provider_adaptation": True,
            "religious_and_historical_safety": "BLOCKING",
        }
        _write_json(series_path, standard)

    bible_path = repo / DIRECTOR_BIBLE_REL
    if bible_path.is_file():
        bible = _read_json(bible_path)
        bible["prompt_direction"] = {
            "owner": "LUNA",
            "cinematic_blueprint_required": True,
            "camera_lens_light_material_motion_required": True,
            "continuity_lock_required": True,
            "generic_quality_word_stack": "FORBIDDEN",
            "self_critique_and_rewrite": "REQUIRED",
            "quality_threshold": QUALITY_THRESHOLD,
        }
        _write_json(bible_path, bible)


def _validate_certification(
    certification: Mapping[str, Any],
    *,
    expected_kind: str,
) -> dict[str, Any]:
    if str(certification.get("status")) != "PASS":
        raise CinematicPromptDirectorError(
            "LUNA_PROMPT_CERTIFICATION_NOT_PASS"
        )
    if int(certification.get("final_score", 0)) < (
        QUALITY_THRESHOLD
    ):
        raise CinematicPromptDirectorError(
            "LUNA_PROMPT_SCORE_BELOW_THRESHOLD"
        )
    if list(
        _sequence(certification.get("blocking_flags"))
    ):
        raise CinematicPromptDirectorError(
            "LUNA_PROMPT_BLOCKING_FLAGS_NOT_EMPTY"
        )
    response_id = _clean(
        certification.get("luna_response_id")
    )
    if not response_id:
        raise CinematicPromptDirectorError(
            "LUNA_PROMPT_RESPONSE_ID_REQUIRED"
        )
    kind = str(certification.get("prompt_kind"))
    if expected_kind == "RUNWARE_VIDEO":
        required = "VIDEO_GENERATION"
    elif expected_kind == "RUNWARE_IMAGE":
        required = "IMAGE_GENERATION"
    else:
        required = kind
    if kind != required:
        raise CinematicPromptDirectorError(
            f"LUNA_PROMPT_KIND_MISMATCH:{kind}:{required}"
        )
    positive = _clean(
        certification.get("certified_positive_prompt_en")
    )
    negative = _clean(
        certification.get("certified_negative_prompt_en")
    )
    if _text_sha256(positive) != str(
        certification.get("positive_prompt_sha256")
    ):
        raise CinematicPromptDirectorError(
            "LUNA_POSITIVE_PROMPT_HASH_MISMATCH"
        )
    if _text_sha256(negative) != str(
        certification.get("negative_prompt_sha256")
    ):
        raise CinematicPromptDirectorError(
            "LUNA_NEGATIVE_PROMPT_HASH_MISMATCH"
        )
    return dict(certification)


def apply_certified_prompt_to_task(
    queue_item: Mapping[str, Any],
    task: Mapping[str, Any],
    media_kind: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    certification = queue_item.get(
        "luna_prompt_certification_v2"
    )
    if not isinstance(certification, Mapping):
        raise CinematicPromptDirectorError(
            "LUNA_PROMPT_CERTIFICATION_REQUIRED_BEFORE_PROVIDER_EXECUTION"
        )
    validated = _validate_certification(
        certification,
        expected_kind=media_kind,
    )
    result = dict(task)
    result["positivePrompt"] = validated[
        "certified_positive_prompt_en"
    ]
    negative = _clean(
        validated.get("certified_negative_prompt_en")
    )
    delivery = str(
        validated.get("negative_prompt_delivery")
    )
    if (
        negative
        and delivery == "SEPARATE_PROVIDER_FIELD"
    ):
        result["negativePrompt"] = negative
    else:
        result.pop("negativePrompt", None)
    return result, validated
