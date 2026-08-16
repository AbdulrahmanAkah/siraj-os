"""OpenAI/Luna request/response contract for Visual Context Research.

This module does NOT send network requests. It only:
- defines the strict dossier schema;
- builds a Responses API request body with web_search enabled;
- parses a completed response;
- extracts provider-grounded URLs from web-search actions and URL citations.

Transport is intentionally left to the Desktop-only authorized paid boundary.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from src.application.openai_luna_orchestrator_v1 import (
    LUNA_MODEL,
    estimate_text_cost_usd,
)
from src.application.visual_context_research_executor_v1 import (
    VisualContextResearchExecutorError,
    VisualResearchProviderResult,
)

CONTRACT_VERSION = "siraj-openai-luna-visual-context-research-contract-v1"



_OPENAI_STRICT_UNSUPPORTED_SCHEMA_KEYWORDS = frozenset(
    {
        "uniqueItems",
        "allOf",
        "not",
        "dependentRequired",
        "dependentSchemas",
        "if",
        "then",
        "else",
    }
)


def _assert_openai_strict_schema_compatibility(
    schema: Mapping[str, Any],
) -> None:
    """Reject provider-incompatible strict schemas before any paid call."""

    def walk(node: Any, path: tuple[str, ...]) -> None:
        if isinstance(node, Mapping):
            for key in _OPENAI_STRICT_UNSUPPORTED_SCHEMA_KEYWORDS:
                if key in node:
                    raise VisualContextResearchExecutorError(
                        "VISUAL_CONTEXT_OPENAI_STRICT_SCHEMA_UNSUPPORTED:"
                        + ".".join((*path, key))
                    )

            if node.get("type") == "object":
                if node.get("additionalProperties") is not False:
                    raise VisualContextResearchExecutorError(
                        "VISUAL_CONTEXT_OPENAI_STRICT_OBJECT_MUST_CLOSE:"
                        + (".".join(path) or "$")
                    )
                properties = node.get("properties")
                required = node.get("required")
                if isinstance(properties, Mapping):
                    property_names = {str(key) for key in properties}
                    required_names = (
                        {str(value) for value in required}
                        if isinstance(required, list)
                        else set()
                    )
                    missing = sorted(property_names - required_names)
                    if missing:
                        raise VisualContextResearchExecutorError(
                            "VISUAL_CONTEXT_OPENAI_STRICT_FIELDS_MUST_BE_REQUIRED:"
                            + (".".join(path) or "$")
                            + ":"
                            + ",".join(missing)
                        )

            for key, value in node.items():
                walk(value, (*path, str(key)))
            return

        if isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, (*path, str(index)))

    walk(schema, ())


def _normalise_provider_wire_dossier(
    payload: dict[str, Any],
) -> dict[str, Any]:
    exhaustion = payload.get("research_exhaustion")
    if not isinstance(exhaustion, dict):
        return payload

    unavailable = exhaustion.get("unavailable_source_classes")
    if not isinstance(unavailable, list):
        return payload

    normalised: dict[str, str] = {}
    for row in unavailable:
        if not isinstance(row, Mapping):
            raise VisualContextResearchExecutorError(
                "VISUAL_CONTEXT_OPENAI_UNAVAILABLE_SOURCE_ROW_INVALID"
            )
        authority_class = str(row.get("authority_class") or "").strip()
        reason = str(row.get("reason") or "").strip()
        if not authority_class or not reason:
            raise VisualContextResearchExecutorError(
                "VISUAL_CONTEXT_OPENAI_UNAVAILABLE_SOURCE_ROW_INCOMPLETE"
            )
        if authority_class in normalised:
            raise VisualContextResearchExecutorError(
                "VISUAL_CONTEXT_OPENAI_UNAVAILABLE_SOURCE_DUPLICATE:"
                + authority_class
            )
        normalised[authority_class] = reason

    exhaustion["unavailable_source_classes"] = normalised
    return payload


def _source_schema(source_classes: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "source_id",
            "title",
            "url",
            "authority_class",
            "publisher_or_author",
            "date_or_edition",
            "verified",
            "verification_method",
            "relevance_dimensions",
        ],
        "properties": {
            "source_id": {
                "type": "string",
                "pattern": "^VCSRC-[0-9]{3}$",
            },
            "title": {"type": "string", "minLength": 1},
            "url": {
                "type": "string",
                "pattern": "^(https?://|shamela://local/)",
            },
            "authority_class": {
                "type": "string",
                "enum": list(source_classes),
            },
            "publisher_or_author": {"type": "string"},
            "date_or_edition": {"type": "string"},
            "verified": {"type": "boolean", "enum": [True]},
            "verification_method": {
                "type": "string",
                "enum": [
                    "WEB_SEARCH_TOOL",
                    "EPISODE_EVIDENCE_PACKAGE",
                    "SHAMELA_LOCAL",
                    "SOURCE_PACKAGE",
                ],
            },
            "relevance_dimensions": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 10,
            },
        },
    }


def _fact_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "fact_id",
            "text",
            "certainty",
            "source_ids",
            "assertive_visualization",
            "visual_implication",
            "conflict_notes",
        ],
        "properties": {
            "fact_id": {"type": "string", "minLength": 3},
            "text": {"type": "string", "minLength": 3},
            "certainty": {
                "type": "string",
                "enum": [
                    "DIRECTLY_SUPPORTED",
                    "STRONGLY_SUPPORTED",
                    "PERMISSIBLE_INFERENCE",
                    "UNCERTAIN",
                    "DISPUTED",
                ],
            },
            "source_ids": {
                "type": "array",
                "items": {
                    "type": "string",
                    "pattern": "^VCSRC-[0-9]{3}$",
                },
                "maxItems": 12,
            },
            "assertive_visualization": {"type": "boolean"},
            "visual_implication": {"type": "string"},
            "conflict_notes": {"type": "string"},
        },
    }


def _dimension_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "summary", "facts"],
        "properties": {
            "status": {
                "type": "string",
                "enum": [
                    "RESOLVED",
                    "UNCERTAIN_NEUTRAL_ONLY",
                    "NOT_APPLICABLE",
                ],
            },
            "summary": {"type": "string"},
            "facts": {
                "type": "array",
                "items": _fact_schema(),
                "maxItems": 24,
            },
        },
    }


def visual_context_dossier_schema(
    source_classes: Sequence[str],
    required_dimensions: Sequence[str],
) -> dict[str, Any]:
    dimensions = {
        name: _dimension_schema()
        for name in required_dimensions
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "episode_id",
            "context_id",
            "status",
            "constitution_precedence",
            "research_scope",
            "sources",
            "research_exhaustion",
            "unresolved_conflicts",
            "dimensions",
            "face_and_body_policy",
            "framing_preferences",
        ],
        "properties": {
            "schema_version": {
                "type": "string",
                "enum": ["siraj-visual-context-dossier-v1"],
            },
            "episode_id": {"type": "string", "minLength": 3},
            "context_id": {"type": "string", "minLength": 2},
            "status": {"type": "string", "enum": ["COMPLETE"]},
            "constitution_precedence": {
                "type": "boolean",
                "enum": [True],
            },
            "research_scope": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "domain_profile",
                    "summary",
                    "research_language",
                ],
                "properties": {
                    "domain_profile": {"type": "string"},
                    "summary": {"type": "string"},
                    "research_language": {"type": "string"},
                },
            },
            "sources": {
                "type": "array",
                "items": _source_schema(source_classes),
                "minItems": 1,
                "maxItems": 120,
            },
            "research_exhaustion": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "search_complete",
                    "source_classes_checked",
                    "unavailable_source_classes",
                    "web_search_performed",
                    "cross_source_reconciliation_complete",
                ],
                "properties": {
                    "search_complete": {
                        "type": "boolean",
                        "enum": [True],
                    },
                    "source_classes_checked": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": list(source_classes),
                        },
                    },
                    "unavailable_source_classes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "authority_class",
                                "reason",
                            ],
                            "properties": {
                                "authority_class": {
                                    "type": "string",
                                    "enum": list(source_classes),
                                },
                                "reason": {"type": "string"},
                            },
                        },
                        "maxItems": len(source_classes),
                    },
                    "web_search_performed": {"type": "boolean"},
                    "cross_source_reconciliation_complete": {
                        "type": "boolean",
                        "enum": [True],
                    },
                },
            },
            "unresolved_conflicts": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 40,
            },
            "dimensions": {
                "type": "object",
                "additionalProperties": False,
                "required": list(required_dimensions),
                "properties": dimensions,
            },
            "face_and_body_policy": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "face_visibility",
                    "head_required",
                    "motion_safe_face_exclusion",
                ],
                "properties": {
                    "face_visibility": {
                        "type": "string",
                        "enum": ["FORBIDDEN_WITHOUT_EXCEPTION"],
                    },
                    "head_required": {
                        "type": "boolean",
                        "enum": [False],
                    },
                    "motion_safe_face_exclusion": {
                        "type": "boolean",
                        "enum": [True],
                    },
                },
            },
            "framing_preferences": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "HANDS_ONLY",
                        "BODY_DETAIL",
                        "TORSO_HEAD_EXCLUDED",
                        "FULL_BODY_HEAD_EXCLUDED",
                        "REAR_BODY_HEAD_OPTIONAL_MOTION_SAFE",
                        "ENVIRONMENT_DOMINANT_BODY_FRAGMENT",
                    ],
                },
                "maxItems": 6,
            },
        },
    }


def build_openai_visual_research_request(
    provider_request: Mapping[str, Any],
) -> dict[str, Any]:
    source_classes = list(
        provider_request["source_sweep"]["required_source_classes"]
    )
    dimensions = list(
        provider_request["dossier_requirements"]["required_dimensions"]
    )

    system_prompt = """أنت باحث السياق البصري في سراج.
مهمتك ليست كتابة السرد، بل البحث في كل حقيقة بصرية لازمة قبل تصوير الحدث.
ابدأ من المصادر المحلية والأولية المتاحة في local_context، ثم استخدم بحث الويب
لفحص كل فئة مصدر مطلوبة في source_sweep. لا تتوقف عند أول مصدر مقنع.
ابحث في البيئة، الشخصيات من دون الوجه، اللباس، المجتمع والعادات، الثقافة
المادية، العمارة، الحقبة، الجغرافيا والمناخ، النبات والحيوان والمنظر الطبيعي،
ومخاطر الحركة وكشف الوجه.

رتّب الأدلة بحسب authority_class. لا تجعل مصدرًا ثانويًا ينسخ أو يتغلب على
مصدر أعلى سلطة. إذا تعارضت الأدلة، أصلح التعارض أو اترك المعلومة
UNCERTAIN/DISPUTED بتصوير محايد؛ unresolved_conflicts يجب أن يبقى فارغًا
فقط بعد المصالحة الفعلية.

غياب التفصيل من كلام الراوي ليس إذنًا للاختراع. كل حقيقة تصويرية تقريرية
يجب أن تكون DIRECTLY_SUPPORTED أو STRONGLY_SUPPORTED ومربوطة بمصدر.
كل رابط ويب تستخدمه في sources يجب أن يكون مصدرًا فتحته/استخدمته فعليًا
عبر أداة web_search في هذه الاستجابة. لا تختلق URL.

الدستور أعلى سلطة من البحث. الوجه البشري ممنوع بلا استثناء. الرأس غير ملزم.
اختر framing_preferences بحسب المعنى البصري: يمكن أن تكون يدين فقط، جزءًا
من الجسد، جذعًا بلا رأس، جسدًا كاملًا بلا رأس، ظهرًا آمنًا للحركة، أو بيئة
واسعة مع جزء محدود من الجسد. لا تجعل اللقطة الساكنة تحتوي جانب وجه أو خدًا
أو أنفًا أو انعكاسًا قد ينكشف عند التحريك.

أخرج JSON فقط وفق المخطط الصارم."""

    schema = visual_context_dossier_schema(
        source_classes,
        dimensions,
    )
    _assert_openai_strict_schema_compatibility(schema)

    return {
        "model": LUNA_MODEL,
        "store": False,
        "reasoning": {"effort": "high"},
        "tools": [{"type": "web_search"}],
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
                            dict(provider_request),
                            ensure_ascii=False,
                            indent=2,
                        ),
                    }
                ],
            },
        ],
        "text": {
            "verbosity": "high",
            "format": {
                "type": "json_schema",
                "name": "siraj_visual_context_dossier_v1",
                "strict": True,
                "schema": schema,
            },
        },
    }


def _output_text(response: Mapping[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    texts: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, Mapping):
            continue
        for part in item.get("content", []):
            if not isinstance(part, Mapping):
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
    if not texts:
        raise VisualContextResearchExecutorError(
            "VISUAL_CONTEXT_OPENAI_OUTPUT_TEXT_MISSING"
        )
    return "\n".join(texts)


def extract_grounded_urls(
    response: Mapping[str, Any],
) -> tuple[str, ...]:
    urls: set[str] = set()
    for item in response.get("output", []):
        if not isinstance(item, Mapping):
            continue
        if item.get("type") == "web_search_call":
            action = item.get("action")
            if isinstance(action, Mapping):
                direct = action.get("url")
                if isinstance(direct, str) and direct.strip():
                    urls.add(direct.strip())
                for source in action.get("sources", []):
                    if not isinstance(source, Mapping):
                        continue
                    url = source.get("url")
                    if isinstance(url, str) and url.strip():
                        urls.add(url.strip())
        for part in item.get("content", []):
            if not isinstance(part, Mapping):
                continue
            for annotation in part.get("annotations", []):
                if not isinstance(annotation, Mapping):
                    continue
                if annotation.get("type") != "url_citation":
                    continue
                url = annotation.get("url")
                if isinstance(url, str) and url.strip():
                    urls.add(url.strip())
    return tuple(sorted(urls))


def _usage(response: Mapping[str, Any]) -> tuple[int, int, int]:
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


def _web_search_calls(response: Mapping[str, Any]) -> int:
    return sum(
        1
        for item in response.get("output", [])
        if isinstance(item, Mapping)
        and item.get("type") == "web_search_call"
    )


def parse_openai_visual_research_response(
    response: Mapping[str, Any],
) -> VisualResearchProviderResult:
    text = _output_text(response)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VisualContextResearchExecutorError(
            "VISUAL_CONTEXT_OPENAI_DOSSIER_JSON_INVALID"
        ) from exc
    if not isinstance(payload, dict):
        raise VisualContextResearchExecutorError(
            "VISUAL_CONTEXT_OPENAI_DOSSIER_OBJECT_REQUIRED"
        )
    payload = _normalise_provider_wire_dossier(payload)
    input_tokens, output_tokens, cached = _usage(response)
    return VisualResearchProviderResult(
        payload=payload,
        provider="OPENAI",
        model=LUNA_MODEL,
        provider_response_id=str(response.get("id") or ""),
        web_search_calls=_web_search_calls(response),
        cited_urls=extract_grounded_urls(response),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached,
        estimated_cost_usd=estimate_text_cost_usd(
            input_tokens,
            output_tokens,
            cached,
        ),
    )
