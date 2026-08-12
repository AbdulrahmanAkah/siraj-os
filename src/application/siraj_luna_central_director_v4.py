"""Luna Central Director V4 for SIRAJ.

Series law:
- Luna OWNS all editorial/research/creative decisions from episode-content
  selection through the final provider-facing visual prompts and pre-spend
  production plan.
- During TTS/media generation, montage, automatic QA, and repair, Luna becomes
  SUPERVISOR: deterministic/provider runtimes execute; Luna reviews semantic,
  cinematic, historical, narrative, and continuity quality and issues bounded
  repair instructions.
- Luna never authorizes its own spend and never silently retries a paid call.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.application.openai_luna_orchestrator_v1 import (
    LUNA_MODEL,
    estimate_text_cost_usd,
)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
REQUEST_TIMEOUT_SECONDS = 600
LAW_REL = Path("projects/_series/siraj-luna-central-director-law-v4.json")
LUNA_LOCK_ROOT_REL = Path("orchestration/luna-v4/locks")
LUNA_RECEIPT_ROOT_REL = Path("orchestration/luna-v4/receipts")

PREPRODUCTION_OWNER_STAGES = (
    "EPISODE_CONTENT_SELECTION",
    "SOURCE_RESEARCH_FROM_ZERO",
    "SOURCE_CLAIM_MATRIX",
    "STORY_ARCHITECTURE",
    "FINAL_SCRIPT",
    "PRONUNCIATION_AND_PERFORMANCE_GATE",
    "TTS_DIRECTION",
    "FINAL_TTS_EDITORIAL_REVIEW",
    "AUDIO_TIMESTAMPS_AND_BEATS",
    "AUDIO_BOUND_STORYBOARD",
    "LUNA_SEMANTIC_PROMPT_DIRECTION",
    "NARRATION_VISUAL_ALIGNMENT_GATE",
    "PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
    "MEDIA_QUEUE_AND_COST_PLAN",
    "FINAL_PREPRODUCTION_SIGNOFF",
)

SUPERVISED_EXECUTION_STAGES = (
    "TTS_PROVIDER_EXECUTION",
    "IMAGE_PROVIDER_EXECUTION",
    "VIDEO_PROVIDER_EXECUTION",
    "LOCAL_GRAPHICS_EXECUTION",
    "LOCAL_ASSEMBLY_AND_MONTAGE",
    "AUTOMATIC_TECHNICAL_QA",
    "SEMANTIC_AND_EDITORIAL_QA",
    "BOUNDED_PARTIAL_REPAIR",
    "FINAL_DELIVERABLE_REVIEW",
)

DETERMINISTIC_ONLY_RESPONSIBILITIES = (
    "RAW_SOURCE_FETCH_AND_MATERIALIZATION",
    "SOURCE_LOCATOR_AND_HASH_PERSISTENCE",
    "SCHEMA_VALIDATION",
    "DEPENDENCY_HASH_VALIDATION",
    "PAID_ATTEMPT_LEDGER",
    "PROVIDER_TASK_UUID_PERSISTENCE",
    "PROVIDER_NETWORK_EXECUTION",
    "LOCAL_MEDIA_RENDERING",
    "SIGNAL_LEVEL_QA",
    "COST_RECONCILIATION",
)

HUMAN_RESERVED_AUTHORITIES = (
    "EXPLICIT_PAID_BUDGET_AUTHORIZATION",
    "QUEUE_SPECIFIC_PAID_RETRY_AUTHORIZATION",
    "OPTIONAL_CREATIVE_OVERRIDE",
    "FINAL_HUMAN_WATCH_GATE",
    "YOUTUBE_PUBLICATION",
)

class LunaCentralDirectorError(RuntimeError):
    pass

@dataclass(frozen=True, slots=True)
class LunaStageResult:
    stage: str
    response_id: str
    payload: dict[str, Any]
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    estimated_text_cost_usd: float
    web_search_calls: int

def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise LunaCentralDirectorError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise LunaCentralDirectorError(f"JSON_OBJECT_REQUIRED:{path}")
    return value

def _write_new(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise LunaCentralDirectorError(f"EXCLUSIVE_FILE_EXISTS:{path}") from exc
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)

def load_law(repo_root: Path) -> dict[str, Any]:
    law = _read(repo_root.resolve() / LAW_REL)
    if str(law.get("status") or "") != "ACTIVE":
        raise LunaCentralDirectorError("LUNA_CENTRAL_DIRECTOR_LAW_NOT_ACTIVE")
    return law

def assert_stage_governance(stage: str, actor: str) -> None:
    actor = str(actor).upper()
    if stage in PREPRODUCTION_OWNER_STAGES:
        if actor != "LUNA":
            raise LunaCentralDirectorError(
                f"PREPRODUCTION_STAGE_MUST_BE_OWNED_BY_LUNA:{stage}:{actor}"
            )
        return
    if stage in SUPERVISED_EXECUTION_STAGES:
        if actor not in {"LUNA_SUPERVISOR", "DETERMINISTIC_RUNTIME"}:
            raise LunaCentralDirectorError(
                f"EXECUTION_STAGE_ROLE_INVALID:{stage}:{actor}"
            )
        return
    raise LunaCentralDirectorError(f"UNKNOWN_LUNA_GOVERNANCE_STAGE:{stage}")

def assert_luna_cannot_authorize_spend(actor: str) -> None:
    if str(actor).upper() in {"LUNA", "LUNA_SUPERVISOR"}:
        raise LunaCentralDirectorError("LUNA_SELF_AUTHORIZATION_FORBIDDEN")

def base_system_prompt(stage: str) -> str:
    assert_stage_governance(stage, "LUNA")
    return f"""أنت Luna، المدير المركزي لسلسلة سراج، والمالك التحريري والبحثي
والإبداعي لهذه المرحلة: {stage}.

القانون الملزم:
- أنت لا تقدم اقتراحًا ثانويًا؛ أنت المسؤول عن اتخاذ القرار التحريري والبحثي
  والإخراجي في جميع مراحل ما قبل الإنتاج.
- لا تعتمد أي مادة من أعمال الحلقة الثانية السابقة لـ V4+.
- الحقائق لا تُستخرج من الذاكرة وحدها: وجّه البحث إلى مصادر قابلة للفحص،
  واربط كل ادعاء بمعرفات مصادر ومحددات locator واضحة.
- القرآن والنصوص الأولية الموثوقة مقدمة، ثم السنة الصحيحة، ثم المصادر
  التفسيرية/التاريخية مع التصريح بدرجة اليقين والخلاف.
- لا تحول رواية تفسيرية أو إسرائيلية أو مختلفًا فيها إلى حقيقة قطعية.
- لا تخترع تفاصيل بصرية غير مسندة عندما توهم المشاهد بأنها حقيقة تاريخية.
- لا تحدد مدة الحلقة أو عدد اللقطات مسبقًا؛ مدة التعليق الصوتي النهائي هي
  التي تحدد زمن الحلقة، واللقطات تُشتق بعد ذلك من beat map الصوتي.
- بعد Final TTS يجب أن تكون كل لقطة مرتبطة بنص الراوي الفعلي وسبب بصري
  صريح يشرح لماذا تعبّر الصورة عن ذلك النص.
- أنت المسؤول عن جودة البرومبت النهائية: الموضوع، الفعل، البيئة، المقياس،
  التكوين، العدسة، الحركة، الإضاءة، الخامات، الزمن، الاستمرارية، العلاقة
  باللقطة السابقة واللاحقة، والمحظورات.
- النص العربي الدقيق لا يُطلب من مولد الصور/الفيديو؛ ينفذ محليًا فقط.
- الموسيقى ممنوعة.
- لا تكرر أي طلب مدفوع تلقائيًا، ولا تمنح نفسك إذن الصرف.
- عند مرحلة الإنتاج تصبح مشرفًا: راجع النتائج واصدر PASS أو REPAIR_LOCAL أو
  REGENERATE_RECOMMENDED مع السبب، لكن REGENERATE لا يُنفذ دون تصريح مالي.
أخرج JSON فقط وفق المخطط المطلوب."""

def _post_json_once(api_key: str, request_payload: Mapping[str, Any]) -> dict[str, Any]:
    if not api_key.strip():
        raise LunaCentralDirectorError("OPENAI_API_KEY_REQUIRED")
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
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
        if exc.code >= 500:
            code = "OPENAI_TRANSIENT_SERVER_ERROR_NO_AUTO_RETRY"
        elif exc.code == 429:
            code = "OPENAI_RATE_LIMIT_OR_QUOTA_NO_AUTO_RETRY"
        elif exc.code == 401:
            code = "OPENAI_API_KEY_INVALID"
        elif exc.code == 402 or "billing" in body.lower():
            code = "WAITING_FOR_OPENAI_BALANCE"
        else:
            code = f"OPENAI_HTTP_{exc.code}"
        raise LunaCentralDirectorError(f"{code}:{body[:1200]}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise LunaCentralDirectorError(
            f"OPENAI_NETWORK_ERROR_NO_AUTO_RETRY:{exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise LunaCentralDirectorError("OPENAI_INVALID_JSON_RESPONSE") from exc
    if not isinstance(value, dict):
        raise LunaCentralDirectorError("OPENAI_RESPONSE_OBJECT_REQUIRED")
    return value

def _extract_output_text(response: Mapping[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    output = response.get("output")
    if not isinstance(output, list):
        raise LunaCentralDirectorError("OPENAI_OUTPUT_MISSING")
    texts: list[str] = []
    for item in output:
        if not isinstance(item, Mapping):
            continue
        for part in item.get("content") or []:
            if isinstance(part, Mapping):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
    if not texts:
        raise LunaCentralDirectorError("OPENAI_OUTPUT_TEXT_MISSING")
    return "\n".join(texts)

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
    output = response.get("output")
    if not isinstance(output, list):
        return 0
    return sum(
        1
        for item in output
        if isinstance(item, Mapping)
        and str(item.get("type") or "") == "web_search_call"
    )

def build_stage_request(
    *,
    stage: str,
    user_payload: Mapping[str, Any],
    schema_name: str,
    schema: Mapping[str, Any],
    use_web_search: bool,
    reasoning_effort: str = "high",
) -> dict[str, Any]:
    assert_stage_governance(stage, "LUNA")
    request: dict[str, Any] = {
        "model": LUNA_MODEL,
        "store": False,
        "reasoning": {"effort": reasoning_effort},
        "input": [
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": base_system_prompt(stage)}
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
    return request

def execute_authorized_luna_stage_once(
    repo_root: Path,
    episode_root: Path,
    *,
    stage: str,
    api_key: str,
    authorization: Mapping[str, Any],
    user_payload: Mapping[str, Any],
    schema_name: str,
    schema: Mapping[str, Any],
    use_web_search: bool,
    reasoning_effort: str = "high",
) -> LunaStageResult:
    load_law(repo_root)
    assert_stage_governance(stage, "LUNA")
    if str(authorization.get("status") or "") != "ACTIVE":
        raise LunaCentralDirectorError("LUNA_STAGE_AUTHORIZATION_NOT_ACTIVE")
    allowed = list(authorization.get("authorized_stages") or [])
    if stage not in allowed:
        raise LunaCentralDirectorError(
            f"LUNA_STAGE_NOT_IN_AUTHORIZATION:{stage}"
        )
    if authorization.get("automatic_retry") is not False:
        raise LunaCentralDirectorError("LUNA_AUTO_RETRY_MUST_BE_FALSE")

    attempt_no = int(authorization.get("attempt_no_by_stage", {}).get(stage, 1))
    if attempt_no != 1:
        if str(authorization.get("authorization_kind") or "") != (
            "STAGE_SPECIFIC_RETRY"
        ):
            raise LunaCentralDirectorError(
                f"LUNA_STAGE_RETRY_REQUIRES_SPECIFIC_AUTHORIZATION:{stage}"
            )

    request_payload = build_stage_request(
        stage=stage,
        user_payload=user_payload,
        schema_name=schema_name,
        schema=schema,
        use_web_search=use_web_search,
        reasoning_effort=reasoning_effort,
    )
    safe_stage = stage.lower().replace("_", "-")
    lock_path = (
        episode_root
        / LUNA_LOCK_ROOT_REL
        / f"{safe_stage}-attempt-{attempt_no:02d}.json"
    )
    _write_new(
        lock_path,
        {
            "schema_version": "siraj-luna-v4-request-lock-v1",
            "stage": stage,
            "attempt_no": attempt_no,
            "authorization_id": authorization.get("authorization_id"),
            "status": "LOCKED_BEFORE_NETWORK",
            "automatic_retry": False,
            "created_at_utc": _now(),
            "request_payload": request_payload,
        },
    )

    response = _post_json_once(api_key, request_payload)
    text = _extract_output_text(response)
    try:
        output_payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LunaCentralDirectorError(
            f"LUNA_STAGE_JSON_INVALID:{stage}"
        ) from exc
    if not isinstance(output_payload, dict):
        raise LunaCentralDirectorError(
            f"LUNA_STAGE_OBJECT_REQUIRED:{stage}"
        )
    input_tokens, output_tokens, cached = _usage(response)
    result = LunaStageResult(
        stage=stage,
        response_id=str(response.get("id") or ""),
        payload=output_payload,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached,
        estimated_text_cost_usd=estimate_text_cost_usd(
            input_tokens, output_tokens, cached
        ),
        web_search_calls=_web_search_calls(response),
    )
    receipt_path = (
        episode_root
        / LUNA_RECEIPT_ROOT_REL
        / f"{safe_stage}-attempt-{attempt_no:02d}.json"
    )
    _write_new(
        receipt_path,
        {
            "schema_version": "siraj-luna-v4-stage-receipt-v1",
            "stage": stage,
            "attempt_no": attempt_no,
            "authorization_id": authorization.get("authorization_id"),
            "response_id": result.response_id,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cached_input_tokens": result.cached_input_tokens,
            "estimated_text_cost_usd": result.estimated_text_cost_usd,
            "web_search_calls": result.web_search_calls,
            "status": "COMPLETE",
            "completed_at_utc": _now(),
        },
    )
    return result
