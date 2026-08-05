from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.application.openai_luna_orchestrator_v1 import (
    LUNA_MODEL,
    estimate_text_cost_usd,
)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
REQUEST_TIMEOUT_SECONDS = 600


class EditorialLunaError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EditorialLunaResult:
    response_id: str
    payload: dict[str, Any]
    raw_output_text: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    estimated_text_cost_usd: float
    web_search_calls: int


def _source_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "source_id",
            "title",
            "url",
            "source_type",
            "publisher_or_author",
            "date_or_edition",
            "reliability_ar",
        ],
        "properties": {
            "source_id": {
                "type": "string",
                "pattern": "^SRC-[0-9]{3}$",
            },
            "title": {"type": "string", "minLength": 1},
            "url": {
                "type": "string",
                "pattern": "^https?://",
            },
            "source_type": {
                "type": "string",
                "enum": [
                    "QURAN",
                    "HADITH_COLLECTION",
                    "CLASSICAL_SOURCE",
                    "ACADEMIC_SOURCE",
                    "REFERENCE_WORK",
                    "ARCHIVE_OR_MUSEUM",
                    "OTHER",
                ],
            },
            "publisher_or_author": {"type": "string"},
            "date_or_edition": {"type": "string"},
            "reliability_ar": {"type": "string", "minLength": 3},
        },
    }


def evidence_schema() -> dict[str, Any]:
    claim = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "claim_id",
            "claim_ar",
            "evidence_posture",
            "confidence",
            "source_ids",
            "use_policy",
            "qualification_ar",
            "contradictions_ar",
        ],
        "properties": {
            "claim_id": {
                "type": "string",
                "pattern": "^CL-[0-9]{3}$",
            },
            "claim_ar": {"type": "string", "minLength": 5},
            "evidence_posture": {
                "type": "string",
                "enum": [
                    "QURAN_EXPLICIT",
                    "AUTHENTIC_SUNNAH",
                    "ACCEPTED_ATHAR",
                    "QUALIFIED_REPORT",
                    "EDITORIAL_BRIDGE",
                ],
            },
            "confidence": {
                "type": "string",
                "enum": ["HIGH", "MEDIUM", "LOW"],
            },
            "source_ids": {
                "type": "array",
                "items": {
                    "type": "string",
                    "pattern": "^SRC-[0-9]{3}$",
                },
                "minItems": 1,
                "maxItems": 8,
            },
            "use_policy": {
                "type": "string",
                "enum": ["ALLOWED", "QUALIFIED_ONLY", "EXCLUDED"],
            },
            "qualification_ar": {"type": "string"},
            "contradictions_ar": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 8,
            },
        },
    }
    event = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "event_id",
            "chronology_summary_ar",
            "claims",
            "unresolved_questions_ar",
            "production_safety_ar",
        ],
        "properties": {
            "event_id": {
                "type": "string",
                "pattern": "^EV-[0-9]{3}$",
            },
            "chronology_summary_ar": {
                "type": "string",
                "minLength": 10,
            },
            "claims": {
                "type": "array",
                "items": claim,
                "minItems": 1,
                "maxItems": 16,
            },
            "unresolved_questions_ar": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 10,
            },
            "production_safety_ar": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 10,
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "episode_id",
            "research_summary_ar",
            "source_register",
            "events",
            "global_uncertainties_ar",
            "excluded_claims_ar",
            "research_quality_score",
        ],
        "properties": {
            "episode_id": {"type": "string", "minLength": 3},
            "research_summary_ar": {
                "type": "string",
                "minLength": 30,
            },
            "source_register": {
                "type": "array",
                "items": _source_schema(),
                "minItems": 3,
                "maxItems": 80,
            },
            "events": {
                "type": "array",
                "items": event,
                "minItems": 3,
                "maxItems": 15,
            },
            "global_uncertainties_ar": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 20,
            },
            "excluded_claims_ar": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 30,
            },
            "research_quality_score": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
            },
        },
    }


def script_schema() -> dict[str, Any]:
    segment = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "segment_id",
            "segment_type",
            "event_id",
            "title_ar",
            "narration_ar",
            "estimated_duration_seconds",
            "claim_ids",
            "source_ids",
            "transition_ar",
            "visual_intent_ar",
            "uncertainty_language_ar",
        ],
        "properties": {
            "segment_id": {
                "type": "string",
                "pattern": "^SEG-[0-9]{3}$",
            },
            "segment_type": {
                "type": "string",
                "enum": ["INTRO", "EVENT", "BRIDGE", "OUTRO"],
            },
            "event_id": {"type": "string", "minLength": 2},
            "title_ar": {"type": "string", "minLength": 2},
            "narration_ar": {"type": "string", "minLength": 50},
            "estimated_duration_seconds": {
                "type": "integer",
                "minimum": 20,
                "maximum": 360,
            },
            "claim_ids": {
                "type": "array",
                "items": {
                    "type": "string",
                    "pattern": "^CL-[0-9]{3}$",
                },
                "maxItems": 24,
            },
            "source_ids": {
                "type": "array",
                "items": {
                    "type": "string",
                    "pattern": "^SRC-[0-9]{3}$",
                },
                "maxItems": 20,
            },
            "transition_ar": {"type": "string"},
            "visual_intent_ar": {
                "type": "string",
                "minLength": 5,
            },
            "uncertainty_language_ar": {"type": "string"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "episode_id",
            "title_ar",
            "opening_hook_ar",
            "central_thesis_ar",
            "target_duration_seconds",
            "segments",
            "closing_ar",
            "editorial_notes_ar",
            "music",
            "sound_effects",
        ],
        "properties": {
            "episode_id": {"type": "string", "minLength": 3},
            "title_ar": {"type": "string", "minLength": 3},
            "opening_hook_ar": {
                "type": "string",
                "minLength": 20,
            },
            "central_thesis_ar": {
                "type": "string",
                "minLength": 20,
            },
            "target_duration_seconds": {
                "type": "integer",
                "minimum": 600,
                "maximum": 1800,
            },
            "segments": {
                "type": "array",
                "items": segment,
                "minItems": 5,
                "maxItems": 30,
            },
            "closing_ar": {"type": "string", "minLength": 30},
            "editorial_notes_ar": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 20,
            },
            "music": {
                "type": "string",
                "enum": ["FORBIDDEN"],
            },
            "sound_effects": {
                "type": "string",
                "enum": ["ALLOWED_ANY_SCENE_APPROPRIATE_TYPE"],
            },
        },
    }


def storyboard_schema() -> dict[str, Any]:
    sequence = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "sequence_id",
            "title_ar",
            "narrative_function_ar",
            "segment_ids",
        ],
        "properties": {
            "sequence_id": {
                "type": "string",
                "pattern": "^SEQ-[0-9]{2}$",
            },
            "title_ar": {"type": "string", "minLength": 2},
            "narrative_function_ar": {
                "type": "string",
                "minLength": 5,
            },
            "segment_ids": {
                "type": "array",
                "items": {
                    "type": "string",
                    "pattern": "^SEG-[0-9]{3}$",
                },
                "minItems": 1,
                "maxItems": 12,
            },
        },
    }
    shot = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "queue_index",
            "shot_id",
            "sequence_id",
            "event_id",
            "segment_ids",
            "label_ar",
            "dramatic_function_ar",
            "final_budget_treatment",
            "editorial_duration_seconds",
            "planned_generated_video_seconds",
            "visual_brief_ar",
            "camera_motion_ar",
            "runware_positive_prompt_en",
            "runware_negative_prompt_en",
            "sfx_cues_ar",
            "sound_policy",
            "depicts_unseen_beings",
            "contains_music",
            "safety_notes_ar",
        ],
        "properties": {
            "queue_index": {
                "type": "integer",
                "minimum": 1,
                "maximum": 70,
            },
            "shot_id": {
                "type": "string",
                "pattern": "^SH-[0-9]{3}$",
            },
            "sequence_id": {
                "type": "string",
                "pattern": "^SEQ-[0-9]{2}$",
            },
            "event_id": {"type": "string", "minLength": 2},
            "segment_ids": {
                "type": "array",
                "items": {
                    "type": "string",
                    "pattern": "^SEG-[0-9]{3}$",
                },
                "minItems": 1,
                "maxItems": 5,
            },
            "label_ar": {"type": "string", "minLength": 3},
            "dramatic_function_ar": {
                "type": "string",
                "minLength": 5,
            },
            "final_budget_treatment": {
                "type": "string",
                "enum": [
                    "GENERATED_VIDEO",
                    "ANIMATED_STILL_COMPOSITING",
                    "GRAPHICS",
                ],
            },
            "editorial_duration_seconds": {
                "type": "integer",
                "minimum": 4,
                "maximum": 45,
            },
            "planned_generated_video_seconds": {
                "type": "integer",
                "enum": [0, 8],
            },
            "visual_brief_ar": {
                "type": "string",
                "minLength": 10,
            },
            "camera_motion_ar": {
                "type": "string",
                "minLength": 3,
            },
            "runware_positive_prompt_en": {
                "type": "string",
                "minLength": 20,
            },
            "runware_negative_prompt_en": {
                "type": "string",
                "minLength": 10,
            },
            "sfx_cues_ar": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 8,
            },
            "sound_policy": {
                "type": "string",
                "enum": ["SFX_ONLY_NO_MUSIC"],
            },
            "depicts_unseen_beings": {
                "type": "boolean",
                "const": False,
            },
            "contains_music": {
                "type": "boolean",
                "const": False,
            },
            "safety_notes_ar": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 8,
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "episode_id",
            "storyboard_version",
            "total_shots",
            "generated_video_target_seconds",
            "treatment_counts",
            "sequences",
            "shots",
            "music",
            "sound_effects",
            "flat_slideshow",
            "production_notes_ar",
        ],
        "properties": {
            "episode_id": {"type": "string", "minLength": 3},
            "storyboard_version": {
                "type": "integer",
                "minimum": 1,
            },
            "total_shots": {
                "type": "integer",
                "enum": [70],
            },
            "generated_video_target_seconds": {
                "type": "object",
                "additionalProperties": False,
                "required": ["minimum", "maximum", "planned"],
                "properties": {
                    "minimum": {
                        "type": "integer",
                        "enum": [120],
                    },
                    "maximum": {
                        "type": "integer",
                        "enum": [180],
                    },
                    "planned": {
                        "type": "integer",
                        "enum": [160],
                    },
                },
            },
            "treatment_counts": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "GENERATED_VIDEO",
                    "ANIMATED_STILL_COMPOSITING",
                    "GRAPHICS",
                ],
                "properties": {
                    "GENERATED_VIDEO": {
                        "type": "integer",
                        "enum": [20],
                    },
                    "ANIMATED_STILL_COMPOSITING": {
                        "type": "integer",
                        "enum": [44],
                    },
                    "GRAPHICS": {
                        "type": "integer",
                        "enum": [6],
                    },
                },
            },
            "sequences": {
                "type": "array",
                "items": sequence,
                "minItems": 5,
                "maxItems": 18,
            },
            "shots": {
                "type": "array",
                "items": shot,
                "minItems": 70,
                "maxItems": 70,
            },
            "music": {
                "type": "string",
                "enum": ["FORBIDDEN"],
            },
            "sound_effects": {
                "type": "string",
                "enum": ["ALLOWED_ANY_SCENE_APPROPRIATE_TYPE"],
            },
            "flat_slideshow": {
                "type": "string",
                "enum": ["FORBIDDEN"],
            },
            "production_notes_ar": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 30,
            },
        },
    }


def _post_json_once(
    api_key: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if not api_key.strip():
        raise EditorialLunaError("OPENAI_API_KEY_REQUIRED")
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=encoded,
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
        body = exc.read().decode("utf-8", errors="replace")
        lowered = body.lower()
        if exc.code == 401:
            code = "OPENAI_API_KEY_INVALID"
        elif (
            exc.code == 402
            or "insufficient" in lowered
            or "billing" in lowered
        ):
            code = "WAITING_FOR_OPENAI_BALANCE"
        elif exc.code == 429:
            code = "OPENAI_RATE_LIMIT_OR_QUOTA"
        elif exc.code >= 500:
            code = "OPENAI_TRANSIENT_SERVER_ERROR_NO_AUTO_RETRY"
        else:
            code = f"OPENAI_HTTP_{exc.code}"
        raise EditorialLunaError(f"{code}:{body[:1200]}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise EditorialLunaError(
            f"OPENAI_NETWORK_ERROR_NO_AUTO_RETRY:{exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise EditorialLunaError("OPENAI_INVALID_JSON_RESPONSE") from exc
    if not isinstance(value, dict):
        raise EditorialLunaError("OPENAI_RESPONSE_OBJECT_REQUIRED")
    return value


def _extract_output_text(response: Mapping[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    output = response.get("output")
    if not isinstance(output, list):
        raise EditorialLunaError("OPENAI_OUTPUT_MISSING")
    texts: list[str] = []
    for item in output:
        if not isinstance(item, Mapping):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, Mapping):
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
    if not texts:
        raise EditorialLunaError("OPENAI_OUTPUT_TEXT_MISSING")
    return "\n".join(texts)


def _usage(response: Mapping[str, Any]) -> tuple[int, int, int]:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return 0, 0, 0
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    details = usage.get("input_tokens_details")
    cached = 0
    if isinstance(details, Mapping):
        cached = int(details.get("cached_tokens", 0) or 0)
    return input_tokens, output_tokens, cached


def _web_search_calls(response: Mapping[str, Any]) -> int:
    output = response.get("output")
    if not isinstance(output, list):
        return 0
    return sum(
        1
        for item in output
        if isinstance(item, Mapping)
        and str(item.get("type", "")) == "web_search_call"
    )


def _request(
    api_key: str,
    *,
    system_prompt: str,
    user_payload: Mapping[str, Any],
    schema_name: str,
    schema: Mapping[str, Any],
    use_web_search: bool,
    reasoning_effort: str,
) -> EditorialLunaResult:
    request: dict[str, Any] = {
        "model": LUNA_MODEL,
        "store": False,
        "reasoning": {"effort": reasoning_effort},
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": system_prompt,
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
        "max_output_tokens": 100000,
        "text": {
            "verbosity": "high",
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        },
    }
    if use_web_search:
        request["tools"] = [{"type": "web_search"}]
    response = _post_json_once(api_key, request)
    text = _extract_output_text(response)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EditorialLunaError(
            f"{schema_name.upper()}_JSON_INVALID"
        ) from exc
    if not isinstance(payload, dict):
        raise EditorialLunaError(
            f"{schema_name.upper()}_OBJECT_REQUIRED"
        )
    input_tokens, output_tokens, cached = _usage(response)
    return EditorialLunaResult(
        response_id=str(response.get("id", "")),
        payload=payload,
        raw_output_text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached,
        estimated_text_cost_usd=estimate_text_cost_usd(
            input_tokens,
            output_tokens,
            cached,
        ),
        web_search_calls=_web_search_calls(response),
    )


def request_evidence_package(
    repo_root: Path,
    api_key: str,
    episode_id: str,
    approved_scope: Mapping[str, Any],
) -> EditorialLunaResult:
    del repo_root
    system = """أنت باحث سراج المسؤول عن حزمة الأدلة النهائية قبل كتابة النص.
ابحث في الويب بعمق، وابدأ بالمصادر الأولية والمرجعية الموثوقة.
التزم بنطاق الأحداث المعتمد ولا تضف حدثًا جديدًا.
افصل النص القرآني الصريح، الحديث الصحيح، الأثر المقبول، الرواية المؤهلة،
والجسر التحريري. لا ترفع الضعيف أو المختلف فيه إلى حقيقة قطعية.
كل ادعاء مسموح يجب أن يرتبط بمصدر حقيقي قابل للفحص.
اجعل source_id وclaim_id فريدين على مستوى الحلقة كلها، لا داخل الحدث فقط.
استبعد الادعاءات غير المدعومة بوضوح. اكتب بالعربية وأخرج JSON فقط."""
    return _request(
        api_key,
        system_prompt=system,
        user_payload={
            "task": "BUILD_EVIDENCE_PACKAGE",
            "episode_id": episode_id,
            "approved_scope": approved_scope,
            "requirements": {
                "preserve_event_ids": True,
                "minimum_sources": 3,
                "no_new_events": True,
                "religious_claims_require_qualification": True,
            },
        },
        schema_name="siraj_evidence_package_v1",
        schema=evidence_schema(),
        use_web_search=True,
        reasoning_effort="high",
    )


def request_script_package(
    repo_root: Path,
    api_key: str,
    episode_id: str,
    approved_scope: Mapping[str, Any],
    evidence_package: Mapping[str, Any],
) -> EditorialLunaResult:
    del repo_root
    system = """أنت كاتب سراج الرئيس. اكتب نصًا وثائقيًا تاريخيًا دينيًا
سينمائيًا بالعربية اعتمادًا حصريًا على حزمة الأدلة المرفقة.
لا تستخدم أي ادعاء حالته EXCLUDED. ما كان QUALIFIED_ONLY يجب صياغته
بعبارات تحفظية صريحة. اربط كل مقطع بمعرفات الادعاءات والمصادر.
اجعل السرد مشوقًا ومتماسكًا بلا خطاب محاضرة وبلا مبالغة مصطنعة.
لا موسيقى مطلقًا؛ المؤثرات الصوتية المناسبة مسموحة.
لا تصف الله تعالى أو الملائكة أو إبليس أو الغيب بطريقة تجسيدية.
المدة الكاملة بين 10 و30 دقيقة. أخرج JSON فقط."""
    return _request(
        api_key,
        system_prompt=system,
        user_payload={
            "task": "WRITE_EPISODE_SCRIPT",
            "episode_id": episode_id,
            "approved_scope": approved_scope,
            "evidence_package": evidence_package,
            "requirements": {
                "language": "ARABIC",
                "duration_seconds": [600, 1800],
                "claim_traceability": True,
                "music": "FORBIDDEN",
                "human_gates_added": 0,
            },
        },
        schema_name="siraj_episode_script_v1",
        schema=script_schema(),
        use_web_search=False,
        reasoning_effort="high",
    )


def request_storyboard_plan(
    repo_root: Path,
    api_key: str,
    episode_id: str,
    approved_scope: Mapping[str, Any],
    evidence_package: Mapping[str, Any],
    script_package: Mapping[str, Any],
) -> EditorialLunaResult:
    del repo_root
    system = """أنت المخرج البصري ومخطط الإنتاج في سراج.
حوّل النص المعتمد إلى ستوريبورد سينمائي قابل للتنفيذ، لا عرض شرائح مسطح.
أنشئ 70 لقطة بالضبط: 20 فيديو مولد مدة كل منها 8 ثوان، و44 صورة
متحركة/تركيب بصري، و6 جرافيك. مجموع الفيديو المولد 160 ثانية.
كل لقطة يجب أن تغيّر معلومة درامية أو ضغطًا عاطفيًا أو فهمًا مكانيًا
أو ثيمة؛ الجمال وحده غير كافٍ. الحركة والانتقالات يجب أن تكون مبررة.
اكتب Prompts إنجليزية عملية لـRunware مع Negative Prompts.
الموسيقى والأغاني ممنوعة تمامًا، والمؤثرات المناسبة للمشهد مسموحة.
لا تجسد الله تعالى أو الملائكة أو إبليس أو الغيب حرفيًا.
لا تنشئ أشخاصًا أو كائنات عندما يمنع السياق الديني ذلك.
أخرج JSON فقط وفق المخطط."""
    return _request(
        api_key,
        system_prompt=system,
        user_payload={
            "task": "BUILD_STORYBOARD_AND_MEDIA_PLAN",
            "episode_id": episode_id,
            "approved_scope": approved_scope,
            "evidence_package": evidence_package,
            "script_package": script_package,
            "fixed_media_law": {
                "total_shots": 70,
                "generated_video_shots": 20,
                "generated_video_seconds_each": 8,
                "animated_still_compositing_shots": 44,
                "graphics_shots": 6,
                "generated_video_total_seconds": 160,
                "music": "FORBIDDEN",
                "flat_slideshow": "FORBIDDEN",
            },
        },
        schema_name="siraj_storyboard_media_plan_v1",
        schema=storyboard_schema(),
        use_web_search=False,
        reasoning_effort="high",
    )
