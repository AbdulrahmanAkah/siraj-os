from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.application.shamela_primary_research_v1 import (
    build_shamela_primary_context,
)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
LUNA_MODEL = "gpt-5.6-luna"
REQUEST_TIMEOUT_SECONDS = 300
MAX_TRANSIENT_RETRIES = 2

# Human-authorized pricing snapshot from the 2026-07-30 public announcement.
# This is recorded for estimation only; provider usage/final billing remains source
# of truth and the value is intentionally isolated from execution logic.
LUNA_INPUT_USD_PER_MILLION = 0.20
LUNA_OUTPUT_USD_PER_MILLION = 1.20


class LunaProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LunaResult:
    response_id: str
    payload: dict[str, Any]
    raw_output_text: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    estimated_text_cost_usd: float


def _scope_schema() -> dict[str, Any]:
    source_ref = {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "url", "source_type", "supports"],
        "properties": {
            "title": {"type": "string", "minLength": 1},
            "url": {
                "type": "string",
                "pattern": "^(https?://|shamela://local/)",
            },
            "source_type": {
                "type": "string",
                "enum": [
                    "QURAN",
                    "HADITH_COLLECTION",
                    "CLASSICAL_SOURCE",
                    "ACADEMIC_SOURCE",
                    "REFERENCE_WORK",
                    "SHAMELA_LOCAL_BOOK",
                    "OTHER",
                ],
            },
            "supports": {"type": "string", "minLength": 1},
        },
    }
    event = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "event_id",
            "title_ar",
            "description_ar",
            "chronology_order",
            "evidence_posture",
            "confidence",
            "include_recommendation",
            "source_refs",
            "uncertainty_ar",
        ],
        "properties": {
            "event_id": {"type": "string", "pattern": "^EV-[0-9]{3}$"},
            "title_ar": {"type": "string", "minLength": 2},
            "description_ar": {"type": "string", "minLength": 5},
            "chronology_order": {"type": "integer", "minimum": 1},
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
            "include_recommendation": {"type": "boolean"},
            "source_refs": {
                "type": "array",
                "items": source_ref,
                "minItems": 1,
                "maxItems": 8,
            },
            "uncertainty_ar": {"type": "string"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "proposal_version",
            "slug_en",
            "topic_title_ar",
            "working_title_ar",
            "central_question_ar",
            "episode_summary_ar",
            "rationale_ar",
            "estimated_duration_minutes",
            "event_count",
            "events",
            "excluded_candidates",
            "research_questions",
            "production_risk_notes",
        ],
        "properties": {
            "proposal_version": {"type": "integer", "minimum": 1},
            "slug_en": {
                "type": "string",
                "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$",
                "minLength": 3,
                "maxLength": 80,
            },
            "topic_title_ar": {"type": "string", "minLength": 3},
            "working_title_ar": {"type": "string", "minLength": 3},
            "central_question_ar": {"type": "string", "minLength": 5},
            "episode_summary_ar": {"type": "string", "minLength": 20},
            "rationale_ar": {"type": "string", "minLength": 10},
            "estimated_duration_minutes": {
                "type": "integer",
                "minimum": 18,
                "maximum": 25,
            },
            "event_count": {"type": "integer", "minimum": 3, "maximum": 15},
            "events": {
                "type": "array",
                "items": event,
                "minItems": 3,
                "maxItems": 15,
            },
            "excluded_candidates": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 12,
            },
            "research_questions": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 12,
            },
            "production_risk_notes": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 12,
            },
        },
    }


def _series_context(repo_root: Path) -> str:
    projects = repo_root.resolve() / "projects"
    episodes: list[str] = []
    if projects.is_dir():
        for definition in sorted(
            projects.glob("episode-*/contracts/episode-definition-v1.json")
        ):
            try:
                payload = json.loads(definition.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            episode_id = str(payload.get("episode_id", definition.parents[1].name))
            title = str(
                payload.get("title_ar")
                or payload.get("title")
                or payload.get("working_title_ar")
                or ""
            )
            episodes.append(f"- {episode_id}: {title}".strip())
    if not episodes:
        episodes = ["- episode-001-adam: آدم — الحلقة الأولى"]
    return "\n".join(episodes[-20:])


def _system_prompt() -> str:
    return """أنت المحرر والباحث الرئيس لنظام سراج، سلسلة تاريخية دينية سينمائية عربية.
مهمتك اقتراح نطاق الحلقة التالية فقط، لا كتابة النص ولا إنشاء صور أو فيديو.
التزم بما يلي:
- الاستمرارية مع الحلقات الموجودة وعدم تكرار موضوع مكتمل.
- اختيار موضوع متماسك مدته بين 18 و25 دقيقة، والهدف المعتاد 22 دقيقة.
- كتب المكتبة الشاملة المختارة هي مصدر المعلومات الأول.
- الويب مصدر ثانوي فقط لسد فجوة محددة لا تغطيها كتب الشاملة المختارة.
- اقتراح 3 إلى 15 حدثًا فقط وبترتيب زمني واضح.
- فصل الصريح في القرآن، الصحيح من السنة، الآثار المقبولة، الروايات المؤهلة، والجسور التحريرية.
- لا تجعل رواية ضعيفة أو مختلفًا فيها حقيقة قطعية.
- كل حدث يجب أن يتضمن مرجعًا واحدًا على الأقل مع رابط حقيقي قابل للفحص.
- المصادر الأولية والمرجعية الموثوقة مقدمة على المقالات العامة.
- لا تجسد الله تعالى أو الملائكة أو إبليس أو الغيب حرفيًا في أي تصور إنتاجي.
- الموسيقى ممنوعة؛ المؤثرات الصوتية المناسبة للمشهد مسموحة.
- الحد الأقصى الكامل للحلقة 40 دولارًا، ومتوسط الفيديو المولد 120–180 ثانية، والباقي صور متحركة وتركيب بصري.
- اكتب بالعربية الواضحة، وارجع النتيجة وفق مخطط JSON فقط.
- هذه مسودة تخضع لنقاش واعتماد بشري، ولا تعتبر أي حدث معتمدًا تلقائيًا."""


def _user_prompt(
    repo_root: Path,
    instruction: str,
    previous_proposal: Mapping[str, Any] | None,
    conversation: list[Mapping[str, str]] | None,
) -> str:
    parts = [
        "الحلقات الموجودة في المشروع:",
        _series_context(repo_root),
        "\nسياق كتب الشاملة المختارة — المصدر الأول:",
        json.dumps(
            build_shamela_primary_context(
                repo_root,
                instruction or _series_context(repo_root),
                require_excerpts=False,
            ),
            ensure_ascii=False,
            indent=2,
        ),
        "\nسياسة المصدر: SHAMELA_PRIMARY_INTERNET_SECONDARY.",
        "\nاقترح موضوع الحلقة التالية والأحداث الداخلة فيها.",
    ]
    if previous_proposal:
        parts.extend(
            [
                "\nالمقترح السابق:",
                json.dumps(previous_proposal, ensure_ascii=False, indent=2),
            ]
        )
    if conversation:
        parts.append("\nسجل النقاش البشري:")
        for turn in conversation[-12:]:
            role = str(turn.get("role", "user"))
            text = str(turn.get("text", ""))
            parts.append(f"[{role}] {text}")
    if instruction.strip():
        parts.extend(["\nتعليمات المستخدم الحالية:", instruction.strip()])
    return "\n".join(parts)


def build_scope_request(
    repo_root: Path,
    instruction: str = "",
    previous_proposal: Mapping[str, Any] | None = None,
    conversation: list[Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "model": LUNA_MODEL,
        "store": False,
        "reasoning": {"effort": "medium"},
        "tools": [{"type": "web_search"}],
        "input": [
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": _system_prompt()}
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": _user_prompt(
                            repo_root,
                            instruction,
                            previous_proposal,
                            conversation,
                        ),
                    }
                ],
            },
        ],
        "text": {
            "verbosity": "medium",
            "format": {
                "type": "json_schema",
                "name": "siraj_episode_scope_proposal_v1",
                "strict": True,
                "schema": _scope_schema(),
            },
        },
    }


def _error_code(status: int, body: str) -> str:
    lowered = body.lower()
    if status == 401:
        return "OPENAI_API_KEY_INVALID"
    if status == 402 or "insufficient" in lowered or "billing" in lowered:
        return "WAITING_FOR_OPENAI_BALANCE"
    if status == 429:
        return "OPENAI_RATE_LIMIT_OR_QUOTA"
    if status >= 500:
        return "OPENAI_TRANSIENT_SERVER_ERROR"
    return f"OPENAI_HTTP_{status}"


def _post_json(api_key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
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
    last_error: Exception | None = None
    for attempt in range(MAX_TRANSIENT_RETRIES + 1):
        try:
            with urllib.request.urlopen(
                request,
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as response:
                body = response.read().decode("utf-8")
                value = json.loads(body)
                if not isinstance(value, dict):
                    raise LunaProviderError("OPENAI_RESPONSE_OBJECT_REQUIRED")
                return value
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            code = _error_code(exc.code, body)
            if exc.code >= 500 and attempt < MAX_TRANSIENT_RETRIES:
                last_error = exc
                time.sleep(2**attempt)
                continue
            raise LunaProviderError(f"{code}:{body[:1200]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < MAX_TRANSIENT_RETRIES:
                time.sleep(2**attempt)
                continue
            raise LunaProviderError(f"OPENAI_NETWORK_ERROR:{exc}") from exc
        except json.JSONDecodeError as exc:
            raise LunaProviderError("OPENAI_INVALID_JSON_RESPONSE") from exc
    raise LunaProviderError(f"OPENAI_REQUEST_FAILED:{last_error}")


def _extract_output_text(response: Mapping[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    output = response.get("output")
    if not isinstance(output, list):
        raise LunaProviderError("OPENAI_OUTPUT_MISSING")
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
        raise LunaProviderError("OPENAI_OUTPUT_TEXT_MISSING")
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


def estimate_text_cost_usd(
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
) -> float:
    uncached = max(0, int(input_tokens) - int(cached_input_tokens))
    # Cached price is deliberately estimated at 10% of current input price.
    cached_rate = LUNA_INPUT_USD_PER_MILLION * 0.10
    return round(
        uncached / 1_000_000 * LUNA_INPUT_USD_PER_MILLION
        + max(0, int(cached_input_tokens)) / 1_000_000 * cached_rate
        + max(0, int(output_tokens)) / 1_000_000 * LUNA_OUTPUT_USD_PER_MILLION,
        8,
    )


def request_scope_proposal(
    repo_root: Path,
    api_key: str,
    instruction: str = "",
    previous_proposal: Mapping[str, Any] | None = None,
    conversation: list[Mapping[str, str]] | None = None,
) -> LunaResult:
    if not api_key.strip():
        raise LunaProviderError("OPENAI_API_KEY_REQUIRED")
    request = build_scope_request(
        repo_root,
        instruction=instruction,
        previous_proposal=previous_proposal,
        conversation=conversation,
    )
    response = _post_json(api_key, request)
    text = _extract_output_text(response)
    try:
        proposal = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LunaProviderError("LUNA_SCOPE_JSON_INVALID") from exc
    if not isinstance(proposal, dict):
        raise LunaProviderError("LUNA_SCOPE_OBJECT_REQUIRED")
    events = proposal.get("events")
    if not isinstance(events, list) or len(events) != proposal.get("event_count"):
        raise LunaProviderError("LUNA_EVENT_COUNT_MISMATCH")
    ordered = [int(item.get("chronology_order", 0)) for item in events]
    if ordered != sorted(ordered) or len(set(ordered)) != len(ordered):
        raise LunaProviderError("LUNA_EVENT_ORDER_INVALID")
    input_tokens, output_tokens, cached = _usage(response)
    return LunaResult(
        response_id=str(response.get("id", "")),
        payload=proposal,
        raw_output_text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached,
        estimated_text_cost_usd=estimate_text_cost_usd(
            input_tokens,
            output_tokens,
            cached,
        ),
    )
