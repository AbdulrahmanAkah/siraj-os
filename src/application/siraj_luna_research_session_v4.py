"""Authorized Luna iterative research session for SIRAJ V4+.

This is a paid runner. It is intentionally fail-closed:
- maximum 6 Luna calls
- $1.00 total session authorization
- $0.50 conservative text-compute sub-cap; remaining $0.50 reserved for
  web/tool charges because tool-call pricing is accounted separately by provider
- base text rates locked by SIRAJ policy: $0.20/M input, $1.20/M output
- conservative 2x long-context multiplier applied to every preflight/usage
  estimate until the exact threshold is encoded
- zero automatic retries
- every request lock is persisted before network
- an interrupted/failed round cannot be silently re-submitted
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.application.siraj_luna_central_director_v4 import (
    LUNA_MODEL,
    _extract_output_text,
    _post_json_once,
    _usage,
    _web_search_calls,
    base_system_prompt,
)
from src.application.siraj_luna_iterative_research_v4 import (
    execute_luna_research_actions,
    validate_luna_research_plan,
)
from src.application.siraj_luna_research_gateway_v4 import (
    ResearchGatewayV4,
)

EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
MAX_LUNA_CALLS = 6
TOTAL_CAP_USD = 1.00
TEXT_CAP_USD = 0.50
TOOL_RESERVE_USD = 0.50
BASE_INPUT_USD_PER_MILLION = 0.20
BASE_OUTPUT_USD_PER_MILLION = 1.20
CONSERVATIVE_MULTIPLIER = 2.0
MAX_OUTPUT_TOKENS = 32000
class ResearchSessionError(RuntimeError):
    pass

def _load_openai_api_key() -> tuple[str, str]:
    """Load OpenAI key from env, else Windows Credential Manager, without printing it."""
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key, "ENVIRONMENT"

    if os.name != "nt":
        raise ResearchSessionError(
            "OPENAI_API_KEY_NOT_AVAILABLE:"
            "environment variable missing and Windows Credential Manager unavailable"
        )

    import ctypes
    from ctypes import wintypes

    CRED_TYPE_GENERIC = 1
    target = "SIRAJ/OPENAI_API_KEY"

    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        ]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    PCREDENTIALW = ctypes.POINTER(CREDENTIALW)
    pcred = PCREDENTIALW()

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    cred_read = advapi32.CredReadW
    cred_read.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(PCREDENTIALW),
    ]
    cred_read.restype = wintypes.BOOL

    cred_free = advapi32.CredFree
    cred_free.argtypes = [ctypes.c_void_p]
    cred_free.restype = None

    if not cred_read(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
        error_code = ctypes.get_last_error()
        raise ResearchSessionError(
            f"WINDOWS_CREDENTIAL_READ_FAILED:{target}:Win32Error={error_code}"
        )

    try:
        cred = pcred.contents
        if not cred.CredentialBlob or cred.CredentialBlobSize <= 0:
            raise ResearchSessionError(f"WINDOWS_CREDENTIAL_EMPTY:{target}")

        raw = ctypes.string_at(
            cred.CredentialBlob,
            int(cred.CredentialBlobSize),
        )

        try:
            key = raw.decode("utf-16-le").rstrip("\x00").strip()
        except UnicodeDecodeError:
            key = raw.decode("utf-8", errors="strict").rstrip("\x00").strip()

        if not key:
            raise ResearchSessionError(
                f"WINDOWS_CREDENTIAL_EMPTY_AFTER_DECODE:{target}"
            )

        return key, "WINDOWS_CREDENTIAL_MANAGER"
    finally:
        cred_free(pcred)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ResearchSessionError(f"JSON_READ_FAILED:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise ResearchSessionError(f"JSON_OBJECT_REQUIRED:{path}")
    return value

def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)

def _exclusive_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ResearchSessionError(
            f"ROUND_LOCK_ALREADY_EXISTS_NO_RESUBMIT:{path}"
        ) from exc
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)

def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)

def _sha(value: Mapping[str, Any]) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def _estimated_tokens_from_text(text: str) -> int:
    # Conservative Arabic-safe planning heuristic; provider usage is source of truth.
    return max(1, math.ceil(len(text) / 2))

def _estimate_text_cost(
    input_tokens: int,
    output_tokens: int,
) -> float:
    return round(
        CONSERVATIVE_MULTIPLIER
        * (
            max(0, input_tokens) / 1_000_000
            * BASE_INPUT_USD_PER_MILLION
            + max(0, output_tokens) / 1_000_000
            * BASE_OUTPUT_USD_PER_MILLION
        ),
        8,
    )

def _action_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["operation", "purpose_ar", "query", "locator", "url",
                     "arabic_anchor_text", "params"],
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "SEARCH_SHAMELA",
                    "EXPAND_SHAMELA_LOCATOR",
                    "SEARCH_HADITH_LOCAL",
                    "SEARCH_QURAN_CACHE",
                    "MATERIALIZE_QURAN_LOCATOR",
                    "MATERIALIZE_HADITH_URL",
                    "SEARCH_SOURCE_PACKAGES",
                    "SEARCH_WEB_GAP",
                ],
            },
            "purpose_ar": {"type": "string", "minLength": 3},
            "query": {"type": "string"},
            "locator": {"type": "string"},
            "url": {"type": "string"},
            "arabic_anchor_text": {"type": "string"},
            "params": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        },
    }

def _round_schema() -> dict[str, Any]:
    source = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "source_id", "source_type", "title", "url_or_locator",
            "author_or_publisher", "supports_ar", "verification_status",
        ],
        "properties": {
            "source_id": {"type": "string", "pattern": "^SRC-[0-9]{3}$"},
            "source_type": {
                "type": "string",
                "enum": [
                    "QURAN", "HADITH", "SHAMELA", "WEB",
                    "ACADEMIC", "REFERENCE",
                ],
            },
            "title": {"type": "string", "minLength": 1},
            "url_or_locator": {"type": "string", "minLength": 1},
            "author_or_publisher": {"type": "string"},
            "supports_ar": {"type": "string", "minLength": 3},
            "verification_status": {
                "type": "string",
                "enum": [
                    "LOCALLY_MATERIALIZED",
                    "WEB_REVIEWED",
                    "REFERENCE_ONLY",
                    "NEEDS_VERIFICATION",
                ],
            },
        },
    }
    claim = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "claim_id", "claim_ar", "evidence_posture", "confidence",
            "source_ids", "use_policy", "qualification_ar",
            "contradictions_ar",
        ],
        "properties": {
            "claim_id": {"type": "string", "pattern": "^CL-[0-9]{3}$"},
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
                "items": {"type": "string", "pattern": "^SRC-[0-9]{3}$"},
                "maxItems": 12,
            },
            "use_policy": {
                "type": "string",
                "enum": ["ALLOWED", "QUALIFIED_ONLY", "EXCLUDED"],
            },
            "qualification_ar": {"type": "string"},
            "contradictions_ar": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 12,
            },
        },
    }
    event = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "event_id", "title_ar", "chronology_order", "claim_ids",
        ],
        "properties": {
            "event_id": {"type": "string", "pattern": "^EV-[0-9]{3}$"},
            "title_ar": {"type": "string", "minLength": 2},
            "chronology_order": {"type": "integer", "minimum": 1},
            "claim_ids": {
                "type": "array",
                "items": {"type": "string", "pattern": "^CL-[0-9]{3}$"},
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "stage_owner",
            "status",
            "working_title_ar",
            "central_question_ar",
            "scope_ar",
            "included_topics_ar",
            "excluded_topics_ar",
            "research_questions",
            "coverage_assessment_ar",
            "actions",
            "source_register",
            "claims",
            "event_structure",
            "unresolved_gaps_ar",
            "excluded_claims_ar",
        ],
        "properties": {
            "stage_owner": {"type": "string", "enum": ["LUNA"]},
            "status": {
                "type": "string",
                "enum": ["CONTINUE_RESEARCH", "RESEARCH_COMPLETE"],
            },
            "working_title_ar": {"type": "string", "minLength": 3},
            "central_question_ar": {"type": "string", "minLength": 5},
            "scope_ar": {"type": "string", "minLength": 20},
            "included_topics_ar": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 20,
            },
            "excluded_topics_ar": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 20,
            },
            "research_questions": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 30,
            },
            "coverage_assessment_ar": {"type": "string", "minLength": 10},
            "actions": {
                "type": "array",
                "items": _action_schema(),
                "maxItems": 24,
            },
            "source_register": {
                "type": "array",
                "items": source,
                "maxItems": 120,
            },
            "claims": {
                "type": "array",
                "items": claim,
                "maxItems": 160,
            },
            "event_structure": {
                "type": "array",
                "items": event,
                "maxItems": 24,
            },
            "unresolved_gaps_ar": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 40,
            },
            "excluded_claims_ar": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 50,
            },
        },
    }

def _assert_openai_strict_schema(node: Any, path: str = "$") -> None:
    """Fail locally before network if a strict Structured Outputs schema is invalid."""
    if not isinstance(node, Mapping):
        return

    node_type = node.get("type")
    if node_type == "object":
        if node.get("additionalProperties") is not False:
            raise ResearchSessionError(
                f"STRICT_SCHEMA_ADDITIONAL_PROPERTIES_FALSE_REQUIRED:{path}"
            )
        properties = node.get("properties")
        if not isinstance(properties, Mapping):
            raise ResearchSessionError(
                f"STRICT_SCHEMA_PROPERTIES_OBJECT_REQUIRED:{path}"
            )
        required = node.get("required")
        if not isinstance(required, list):
            raise ResearchSessionError(
                f"STRICT_SCHEMA_REQUIRED_ARRAY_REQUIRED:{path}"
            )
        if set(required) != set(properties.keys()):
            raise ResearchSessionError(
                f"STRICT_SCHEMA_ALL_PROPERTIES_MUST_BE_REQUIRED:{path}:"
                f"properties={sorted(properties.keys())}:"
                f"required={sorted(str(x) for x in required)}"
            )
        for key, value in properties.items():
            _assert_openai_strict_schema(value, f"{path}.properties.{key}")

    items = node.get("items")
    if isinstance(items, Mapping):
        _assert_openai_strict_schema(items, f"{path}.items")

    for keyword in ("anyOf", "oneOf", "allOf"):
        branches = node.get(keyword)
        if isinstance(branches, list):
            for index, branch in enumerate(branches):
                _assert_openai_strict_schema(
                    branch, f"{path}.{keyword}[{index}]"
                )

    defs = node.get("$defs")
    if isinstance(defs, Mapping):
        for key, value in defs.items():
            _assert_openai_strict_schema(value, f"{path}.$defs.{key}")

def _execute_actions_resilient(
    repo: Path,
    plan: Mapping[str, Any],
    *,
    allow_network_materialization: bool,
) -> dict[str, Any]:
    """Execute valid Luna actions and return malformed actions as feedback."""
    raw_actions = plan.get("actions")
    if not isinstance(raw_actions, list):
        raise ResearchSessionError("RESEARCH_ACTIONS_LIST_REQUIRED")

    valid_actions: list[dict[str, Any]] = []
    rejected_actions: list[dict[str, Any]] = []

    for index, action in enumerate(raw_actions):
        if not isinstance(action, Mapping):
            rejected_actions.append(
                {
                    "action_index": index,
                    "status": "REJECTED_ACTION_REQUIRES_LUNA_REPLAN",
                    "reason": "ACTION_OBJECT_REQUIRED",
                    "action": action,
                }
            )
            continue

        mini_plan = dict(plan)
        mini_plan["actions"] = [dict(action)]
        try:
            validate_luna_research_plan(mini_plan)
        except Exception as exc:
            rejected_actions.append(
                {
                    "action_index": index,
                    "status": "REJECTED_ACTION_REQUIRES_LUNA_REPLAN",
                    "operation": str(action.get("operation") or ""),
                    "reason": str(exc),
                    "action": dict(action),
                }
            )
        else:
            valid_actions.append(dict(action))

    executed: Mapping[str, Any] | None = None
    if valid_actions:
        valid_plan = dict(plan)
        valid_plan["actions"] = valid_actions
        executed = execute_luna_research_actions(
            repo,
            valid_plan,
            allow_network_materialization=allow_network_materialization,
        )

    return {
        "schema_version": "siraj-luna-resilient-retrieval-batch-v4",
        "status": (
            "PASS"
            if not rejected_actions
            else "PASS_WITH_REJECTED_ACTIONS"
        ),
        "valid_action_count": len(valid_actions),
        "rejected_action_count": len(rejected_actions),
        "executed_results": executed,
        "rejected_actions": rejected_actions,
        "instruction_to_luna": (
            "Review rejected_actions and issue corrected actions in the next "
            "research round. Do not treat a rejected materialization action as "
            "evidence. MATERIALIZE_HADITH_URL requires a non-empty real URL; "
            "obtain one first through search/discovery."
            if rejected_actions
            else ""
        ),
    }

def _record_unusable_model_round(
    *,
    episode_root: Path,
    session_path: Path,
    session: dict[str, Any],
    ledger: Path,
    round_no: int,
    request_uuid: str,
    request_hash: str,
    response: Mapping[str, Any],
    raw_response_path: Path,
    reason: str,
) -> None:
    """Persist an unusable paid model response without silently retrying it."""
    in_tokens, out_tokens, cached = _usage(response)
    round_text_cost = _estimate_text_cost(in_tokens, out_tokens)
    web_calls = _web_search_calls(response)

    tombstone = (
        episode_root
        / "orchestration/luna-v4/research-unusable-rounds"
        / f"round-{round_no:02d}-{request_uuid}.json"
    )
    _exclusive_write(
        tombstone,
        {
            "schema_version": "siraj-luna-unusable-round-v4",
            "round_no": round_no,
            "request_uuid": request_uuid,
            "request_sha256": request_hash,
            "response_id": str(response.get("id") or ""),
            "response_status": str(response.get("status") or ""),
            "incomplete_details": response.get("incomplete_details"),
            "input_tokens": in_tokens,
            "cached_input_tokens": cached,
            "output_tokens": out_tokens,
            "conservative_text_cost_usd": round_text_cost,
            "web_search_calls": web_calls,
            "reason": reason,
            "raw_response_path": str(raw_response_path),
            "usable_research_state": False,
            "automatic_retry": False,
            "created_at_utc": _now(),
        },
    )
    _append_jsonl(
        ledger,
        {
            "event": "CONSUMED_UNUSABLE_NO_AUTO_RETRY",
            "round_no": round_no,
            "request_uuid": request_uuid,
            "response_id": str(response.get("id") or ""),
            "reason": reason,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
            "conservative_text_cost_usd": round_text_cost,
            "web_search_calls": web_calls,
            "timestamp_utc": _now(),
        },
    )

    session["status"] = "UNUSABLE_MODEL_OUTPUT_REQUIRES_MANUAL_RESUME"
    session["current_round"] = round_no
    session["consumed_paid_rounds_override"] = round_no
    session["unusable_round_cost_reserve_usd"] = round(
        float(session.get("unusable_round_cost_reserve_usd", 0) or 0)
        + round_text_cost,
        8,
    )
    session["last_unusable_round_reason"] = reason
    session["last_unusable_round_response_id"] = str(response.get("id") or "")
    session["automatic_retry_performed"] = False
    session["updated_at_utc"] = _now()
    _atomic_write(session_path, session)

def _series_context(repo: Path) -> dict[str, Any]:
    episodes = []
    for root in sorted((repo / "projects").glob("episode-*")):
        if not root.is_dir():
            continue
        item = {"episode_id": root.name}
        for rel in (
            "episode-context-v4.json",
            "contracts/episode-definition-v1.json",
            "contracts/topic-scope-v4.json",
        ):
            path = root / rel
            if path.is_file():
                try:
                    item[rel] = _read_json(path)
                except Exception:
                    pass
        episodes.append(item)
    return {"episodes": episodes[-12:]}

def _research_system(round_no: int) -> str:
    base = base_system_prompt("SOURCE_RESEARCH_FROM_ZERO")
    return (
        base
        + "\n\n"
        + f"هذه جولة البحث رقم {round_no} من حد أقصى {MAX_LUNA_CALLS}."
        + "\nأنت مالك تحديد محتوى الحلقة داخل استمرارية السلسلة، وليس مجرد "
          "مستجيب لخطة سابقة. اسم مجلد episode-002 معرف تقني ولا يفرض عنوانًا نهائيًا."
        + "\nفي الجولة الأولى: حدد النطاق الفعلي للحلقة والأسئلة البحثية ثم أصدر "
          "إجراءات بحث دقيقة."
        + "\nفي الجولات اللاحقة: افحص نتائج الأدوات المرفقة، قارِن الأدلة، "
          "وسّع السياق عند الحاجة، وحدث سجل المصادر والادعاءات."
        + "\nاستخدم web_search بنفسك فقط عند وجود فجوة حقيقية أو للتحقق من مصدر "
          "خارجي؛ المصادر المحلية والأولية مقدمة."
        + "\nإذا أصبحت الأدلة كافية، أعد status=RESEARCH_COMPLETE وactions=[]؛ "
          "ولا تنتظر استهلاك جميع الجولات."
        + "\nلا تصدر MATERIALIZE_HADITH_URL إلا إذا كان حقل url يحتوي رابطًا "
          "حقيقيًا غير فارغ. إذا لم تعرف الرابط فابدأ بالبحث/الاكتشاف أولًا. "
          "وكذلك لا تصدر أي materialization أو expansion بدون locator/url المطلوب."
        + "\nلا تعدّ العثور على حديث تصحيحًا له. ولا تجعل رواية مختلفًا فيها "
          "حقيقة قطعية. كل claim مسموح يجب أن يملك source_ids حقيقية."
        + "\nأعمال episode-002 السابقة لـV4+ ممنوعة كأساس بحثي."
    )

def _build_request(
    round_no: int,
    repo: Path,
    previous_state: Mapping[str, Any] | None,
    retrieval_output: Mapping[str, Any] | None,
    gateway_audit: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "task": "SIRAJ_ITERATIVE_SOURCE_RESEARCH_FROM_ZERO",
        "episode_id": EPISODE_ID,
        "round_no": round_no,
        "maximum_rounds": MAX_LUNA_CALLS,
        "series_context": _series_context(repo),
        "gateway_audit": gateway_audit,
        "previous_luna_research_state": previous_state,
        "new_deterministic_retrieval_results": retrieval_output,
        "rules": {
            "old_episode_002_pre_v4_reuse": False,
            "source_traceability_required": True,
            "luna_owns_episode_content_selection": True,
            "web_search_allowed_for_gaps": True,
            "automatic_retry": False,
            "duration_not_fixed_before_final_tts": True,
            "storyboard_not_in_this_stage": True,
        },
    }
    return {
        "model": LUNA_MODEL,
        "store": False,
        "reasoning": {"effort": "high"},
        "tools": [{"type": "web_search"}],
        "input": [
            {
                "role": "system",
                "content": [
                    {"type": "input_text", "text": _research_system(round_no)}
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            payload, ensure_ascii=False, indent=2
                        ),
                    }
                ],
            },
        ],
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "text": {
            "verbosity": "medium",
            "format": {
                "type": "json_schema",
                "name": "siraj_luna_iterative_research_round_v4",
                "strict": True,
                "schema": _round_schema(),
            },
        },
    }

def _validate_research_state(state: Mapping[str, Any]) -> None:
    if state.get("stage_owner") != "LUNA":
        raise ResearchSessionError("ROUND_OWNER_NOT_LUNA")
    status = state.get("status")
    if status not in {"CONTINUE_RESEARCH", "RESEARCH_COMPLETE"}:
        raise ResearchSessionError(f"ROUND_STATUS_INVALID:{status}")
    actions = state.get("actions")
    if not isinstance(actions, list):
        raise ResearchSessionError("ROUND_ACTIONS_REQUIRED")
    if status == "RESEARCH_COMPLETE" and actions:
        raise ResearchSessionError("COMPLETE_RESEARCH_MUST_HAVE_ZERO_ACTIONS")
    source_ids = {
        str(item.get("source_id"))
        for item in state.get("source_register") or []
        if isinstance(item, Mapping)
    }
    claim_ids = set()
    for claim in state.get("claims") or []:
        if not isinstance(claim, Mapping):
            continue
        cid = str(claim.get("claim_id") or "")
        if cid:
            if cid in claim_ids:
                raise ResearchSessionError(f"DUPLICATE_CLAIM_ID:{cid}")
            claim_ids.add(cid)
        for sid in claim.get("source_ids") or []:
            if str(sid) not in source_ids:
                raise ResearchSessionError(
                    f"CLAIM_REFERENCES_UNKNOWN_SOURCE:{cid}:{sid}"
                )
    for event in state.get("event_structure") or []:
        if not isinstance(event, Mapping):
            continue
        for cid in event.get("claim_ids") or []:
            if str(cid) not in claim_ids:
                raise ResearchSessionError(
                    f"EVENT_REFERENCES_UNKNOWN_CLAIM:{cid}"
                )

def _activate_authorization(episode_root: Path) -> dict[str, Any]:
    path = (
        episode_root
        / "orchestration/luna-research-session-authorization-v4.json"
    )
    existing = _read_json(path) if path.is_file() else {}
    if existing.get("status") == "ACTIVE":
        return existing
    auth = {
        "schema_version": "siraj-luna-research-session-authorization-v4",
        "episode_id": EPISODE_ID,
        "status": "ACTIVE",
        "authorization_id": "SIRAJ-EP002-LUNA-RESEARCH-AUTH-20260808-01",
        "authorization_source": "EXPLICIT_USER_APPROVAL_IN_CHAT_2026-08-08",
        "maximum_luna_calls": MAX_LUNA_CALLS,
        "maximum_total_session_cost_usd": TOTAL_CAP_USD,
        "maximum_conservative_text_cost_usd": TEXT_CAP_USD,
        "reserved_for_web_and_tool_charges_usd": TOOL_RESERVE_USD,
        "allow_luna_web_search": True,
        "allow_network_source_materialization": True,
        "automatic_retry": False,
        "base_input_usd_per_million": BASE_INPUT_USD_PER_MILLION,
        "base_output_usd_per_million": BASE_OUTPUT_USD_PER_MILLION,
        "conservative_long_context_multiplier": CONSERVATIVE_MULTIPLIER,
        "created_at_utc": _now(),
    }
    _atomic_write(path, auth)
    return auth

def run(repo: Path) -> None:
    episode_root = repo / "projects" / EPISODE_ID
    if not episode_root.is_dir():
        raise ResearchSessionError("EPISODE_ROOT_MISSING")

    api_key, api_key_source = _load_openai_api_key()
    print("OPENAI_KEY_SOURCE=" + api_key_source)

    auth = _activate_authorization(episode_root)
    if auth.get("status") != "ACTIVE":
        raise ResearchSessionError("RESEARCH_AUTHORIZATION_NOT_ACTIVE")
    if int(auth.get("maximum_luna_calls", 0)) != MAX_LUNA_CALLS:
        raise ResearchSessionError("AUTH_CALL_LIMIT_MISMATCH")
    if float(auth.get("maximum_total_session_cost_usd", 0)) != TOTAL_CAP_USD:
        raise ResearchSessionError("AUTH_TOTAL_CAP_MISMATCH")
    if auth.get("automatic_retry") is not False:
        raise ResearchSessionError("AUTOMATIC_RETRY_FORBIDDEN")

    session_path = (
        episode_root / "orchestration/luna-research-session-v4.json"
    )
    session = _read_json(session_path)
    if session.get("research_complete") is True:
        print("LUNA_RESEARCH_SESSION_ALREADY_COMPLETE")
        return

    lock_dir = episode_root / "orchestration/luna-v4/research-locks"
    receipt_dir = episode_root / "orchestration/luna-v4/research-receipts"
    ledger = (
        episode_root / "orchestration/luna-v4/research-attempt-ledger-v4.jsonl"
    )
    round_dir = episode_root / "research/luna-rounds"
    final_path = episode_root / "research/luna-research-final-v4.json"

    completed_rounds: list[dict[str, Any]] = []
    for completed_no in range(1, MAX_LUNA_CALLS + 1):
        completed_receipt_path = (
            receipt_dir / f"round-{completed_no:02d}.json"
        )
        completed_state_path = (
            round_dir / f"round-{completed_no:02d}-state-v4.json"
        )
        if completed_receipt_path.exists() != completed_state_path.exists():
            raise ResearchSessionError(
                "ROUND_RECEIPT_STATE_MISMATCH:"
                f"{completed_no}:receipt={completed_receipt_path.exists()}:"
                f"state={completed_state_path.exists()}"
            )
        if not completed_receipt_path.exists():
            break
        completed_receipt = _read_json(completed_receipt_path)
        completed_state = _read_json(completed_state_path)
        if completed_receipt.get("status") != "COMPLETE":
            raise ResearchSessionError(
                f"NONCOMPLETE_EXISTING_RECEIPT:{completed_no}"
            )
        completed_rounds.append(
            {
                "round_no": completed_no,
                "receipt": completed_receipt,
                "state": completed_state,
            }
        )

    resume_completed_rounds = max(
        len(completed_rounds),
        int(session.get("consumed_paid_rounds_override", 0) or 0),
    )
    if resume_completed_rounds:
        session["current_round"] = resume_completed_rounds
        session["resume_source"] = "COMPLETED_RECEIPTS_AND_STATES"
        session["updated_at_utc"] = _now()
        _atomic_write(session_path, session)

    gateway = ResearchGatewayV4(repo)
    gateway_audit = gateway.audit()
    if gateway_audit.get("status") != "READY_LOCAL":
        raise ResearchSessionError(
            f"RESEARCH_GATEWAY_NOT_READY:{gateway_audit.get('status')}"
        )

    previous_state = (
        completed_rounds[-1]["state"]
        if completed_rounds
        else None
    )
    cumulative_text_cost = round(
        sum(
            float(item["receipt"].get("conservative_text_cost_usd", 0) or 0)
            for item in completed_rounds
        )
        + float(session.get("unusable_round_cost_reserve_usd", 0) or 0),
        8,
    )
    cumulative_web_calls = sum(
        int(item["receipt"].get("web_search_calls", 0) or 0)
        for item in completed_rounds
    )
    retrieval_output = None

    if completed_rounds and previous_state is not None:
        last_completed_no = int(completed_rounds[-1]["round_no"])
        prior_retrieval_path = (
            round_dir
            / f"round-{last_completed_no:02d}-retrieval-v4.json"
        )
        if prior_retrieval_path.is_file():
            retrieval_output = _read_json(prior_retrieval_path)
        elif previous_state.get("status") == "CONTINUE_RESEARCH":
            recovery_plan = {
                "stage_owner": "LUNA",
                "status": "CONTINUE_RESEARCH",
                "research_questions": previous_state["research_questions"],
                "coverage_assessment_ar":
                    previous_state["coverage_assessment_ar"],
                "actions": previous_state["actions"],
                "unresolved_gaps_ar": previous_state["unresolved_gaps_ar"],
            }
            retrieval_output = _execute_actions_resilient(
                repo,
                recovery_plan,
                allow_network_materialization=True,
            )
            _atomic_write(prior_retrieval_path, retrieval_output)

    session["status"] = "RUNNING"
    session["paid_luna_calls_authorized"] = True
    session["authorization_id"] = auth["authorization_id"]
    session["maximum_luna_calls"] = MAX_LUNA_CALLS
    session["maximum_total_session_cost_usd"] = TOTAL_CAP_USD
    session["maximum_conservative_text_cost_usd"] = TEXT_CAP_USD
    session["reserved_for_web_and_tool_charges_usd"] = TOOL_RESERVE_USD
    session["updated_at_utc"] = _now()
    _atomic_write(session_path, session)

    for round_no in range(
        resume_completed_rounds + 1,
        MAX_LUNA_CALLS + 1,
    ):
        request = _build_request(
            round_no,
            repo,
            previous_state,
            retrieval_output,
            gateway_audit,
        )
        _assert_openai_strict_schema(
            request["text"]["format"]["schema"]
        )
        serialized = json.dumps(request, ensure_ascii=False)
        estimated_input_tokens = _estimated_tokens_from_text(serialized)
        estimated_round_text_cost = _estimate_text_cost(
            estimated_input_tokens,
            MAX_OUTPUT_TOKENS,
        )
        if cumulative_text_cost + estimated_round_text_cost > TEXT_CAP_USD:
            session["status"] = "STOPPED_BY_TEXT_BUDGET_PREFLIGHT"
            session["current_round"] = round_no - 1
            session["conservative_text_cost_usd"] = cumulative_text_cost
            session["updated_at_utc"] = _now()
            _atomic_write(session_path, session)
            raise ResearchSessionError(
                "TEXT_BUDGET_PREFLIGHT_BLOCK:"
                f"cumulative={cumulative_text_cost}:"
                f"next_max={estimated_round_text_cost}:cap={TEXT_CAP_USD}"
            )

        request_uuid = str(uuid.uuid4())
        lock_path = lock_dir / f"round-{round_no:02d}.json"
        if lock_path.exists():
            attempt_index = 2
            while True:
                candidate = lock_dir / (
                    f"round-{round_no:02d}-attempt-{attempt_index:02d}.json"
                )
                if not candidate.exists():
                    lock_path = candidate
                    break
                attempt_index += 1
        request_hash = _sha(request)
        _exclusive_write(
            lock_path,
            {
                "schema_version": "siraj-luna-research-request-lock-v4",
                "round_no": round_no,
                "request_uuid": request_uuid,
                "request_sha256": request_hash,
                "authorization_id": auth["authorization_id"],
                "estimated_input_tokens_conservative": estimated_input_tokens,
                "maximum_output_tokens": MAX_OUTPUT_TOKENS,
                "maximum_round_text_cost_usd_conservative":
                    estimated_round_text_cost,
                "status": "LOCKED_BEFORE_NETWORK",
                "automatic_retry": False,
                "created_at_utc": _now(),
            },
        )
        _append_jsonl(
            ledger,
            {
                "event": "PREPARED",
                "round_no": round_no,
                "request_uuid": request_uuid,
                "request_sha256": request_hash,
                "authorization_id": auth["authorization_id"],
                "timestamp_utc": _now(),
            },
        )

        try:
            response = _post_json_once(api_key, request)
        except Exception as exc:
            _append_jsonl(
                ledger,
                {
                    "event": "FAILED_NO_AUTO_RETRY",
                    "round_no": round_no,
                    "request_uuid": request_uuid,
                    "error": str(exc),
                    "timestamp_utc": _now(),
                },
            )
            session["status"] = "FAILED_REQUIRES_EXPLICIT_REAUTHORIZATION"
            session["current_round"] = round_no
            session["updated_at_utc"] = _now()
            _atomic_write(session_path, session)
            raise

        raw_response_dir = (
            episode_root / "orchestration/luna-v4/raw-responses"
        )
        raw_response_path = (
            raw_response_dir
            / f"round-{round_no:02d}-{request_uuid}.json"
        )
        _exclusive_write(raw_response_path, dict(response))

        response_status = str(response.get("status") or "")
        if response_status and response_status != "completed":
            _record_unusable_model_round(
                episode_root=episode_root,
                session_path=session_path,
                session=session,
                ledger=ledger,
                round_no=round_no,
                request_uuid=request_uuid,
                request_hash=request_hash,
                response=response,
                raw_response_path=raw_response_path,
                reason=(
                    "RESPONSE_NOT_COMPLETED:"
                    + response_status
                    + ":"
                    + json.dumps(
                        response.get("incomplete_details"),
                        ensure_ascii=False,
                    )
                ),
            )
            raise ResearchSessionError(
                f"LUNA_RESPONSE_NOT_COMPLETED_NO_AUTO_RETRY:{round_no}:"
                f"{response_status}"
            )

        text = _extract_output_text(response)
        try:
            state = json.loads(text)
        except json.JSONDecodeError as exc:
            _record_unusable_model_round(
                episode_root=episode_root,
                session_path=session_path,
                session=session,
                ledger=ledger,
                round_no=round_no,
                request_uuid=request_uuid,
                request_hash=request_hash,
                response=response,
                raw_response_path=raw_response_path,
                reason="STRUCTURED_OUTPUT_JSON_INVALID:" + str(exc),
            )
            raise ResearchSessionError(
                f"LUNA_ROUND_JSON_INVALID_NO_AUTO_RETRY:{round_no}"
            ) from exc
        if not isinstance(state, dict):
            _record_unusable_model_round(
                episode_root=episode_root,
                session_path=session_path,
                session=session,
                ledger=ledger,
                round_no=round_no,
                request_uuid=request_uuid,
                request_hash=request_hash,
                response=response,
                raw_response_path=raw_response_path,
                reason="STRUCTURED_OUTPUT_OBJECT_REQUIRED",
            )
            raise ResearchSessionError(
                f"LUNA_ROUND_OBJECT_REQUIRED_NO_AUTO_RETRY:{round_no}"
            )
        _validate_research_state(state)

        in_tokens, out_tokens, cached = _usage(response)
        round_text_cost = _estimate_text_cost(in_tokens, out_tokens)
        cumulative_text_cost = round(
            cumulative_text_cost + round_text_cost, 8
        )
        web_calls = _web_search_calls(response)
        cumulative_web_calls += web_calls

        receipt_path = receipt_dir / f"round-{round_no:02d}.json"
        _exclusive_write(
            receipt_path,
            {
                "schema_version": "siraj-luna-research-round-receipt-v4",
                "round_no": round_no,
                "request_uuid": request_uuid,
                "request_sha256": request_hash,
                "response_id": str(response.get("id") or ""),
                "input_tokens": in_tokens,
                "cached_input_tokens": cached,
                "output_tokens": out_tokens,
                "conservative_text_cost_usd": round_text_cost,
                "web_search_calls": web_calls,
                "automatic_retry": False,
                "status": "COMPLETE",
                "completed_at_utc": _now(),
            },
        )
        _append_jsonl(
            ledger,
            {
                "event": "COMPLETE",
                "round_no": round_no,
                "request_uuid": request_uuid,
                "response_id": str(response.get("id") or ""),
                "input_tokens": in_tokens,
                "output_tokens": out_tokens,
                "conservative_text_cost_usd": round_text_cost,
                "web_search_calls": web_calls,
                "timestamp_utc": _now(),
            },
        )

        round_state_path = (
            episode_root
            / f"research/luna-rounds/round-{round_no:02d}-state-v4.json"
        )
        _atomic_write(round_state_path, state)

        session["current_round"] = round_no
        session["conservative_text_cost_usd"] = cumulative_text_cost
        session["web_search_calls_observed"] = cumulative_web_calls
        session["updated_at_utc"] = _now()

        if cumulative_text_cost > TEXT_CAP_USD:
            session["status"] = "STOPPED_BY_TEXT_BUDGET_AFTER_USAGE"
            _atomic_write(session_path, session)
            raise ResearchSessionError(
                f"TEXT_CAP_EXCEEDED_AFTER_PROVIDER_USAGE:{cumulative_text_cost}"
            )

        if state["status"] == "RESEARCH_COMPLETE":
            final = {
                "schema_version": "siraj-luna-research-final-v4",
                "episode_id": EPISODE_ID,
                "status": "PASS",
                "completed_round": round_no,
                "authorization_id": auth["authorization_id"],
                "working_title_ar": state["working_title_ar"],
                "central_question_ar": state["central_question_ar"],
                "scope_ar": state["scope_ar"],
                "included_topics_ar": state["included_topics_ar"],
                "excluded_topics_ar": state["excluded_topics_ar"],
                "research_questions": state["research_questions"],
                "coverage_assessment_ar": state["coverage_assessment_ar"],
                "source_register": state["source_register"],
                "claims": state["claims"],
                "event_structure": state["event_structure"],
                "unresolved_gaps_ar": state["unresolved_gaps_ar"],
                "excluded_claims_ar": state["excluded_claims_ar"],
                "conservative_text_cost_usd": cumulative_text_cost,
                "web_search_calls_observed": cumulative_web_calls,
                "automatic_retry": False,
                "completed_at_utc": _now(),
            }
            _atomic_write(final_path, final)
            session["status"] = "RESEARCH_COMPLETE"
            session["research_complete"] = True
            session["final_research_path"] = str(final_path)
            _atomic_write(session_path, session)
            print("SIRAJ_LUNA_RESEARCH_SESSION_V4_COMPLETE")
            print(f"ROUNDS_USED={round_no}")
            print(
                "CONSERVATIVE_TEXT_COST_USD="
                f"{cumulative_text_cost:.8f}"
            )
            print(f"WEB_SEARCH_CALLS_OBSERVED={cumulative_web_calls}")
            print(f"FINAL_RESEARCH={final_path}")
            print("AUTOMATIC_RETRIES=0")
            print("NEXT_STAGE=BUILD_CANONICAL_SOURCE_PACKAGE_AND_CLAIM_MATRIX")
            return

        # Execute Luna's requested deterministic retrieval actions.
        plan = {
            "stage_owner": "LUNA",
            "status": "CONTINUE_RESEARCH",
            "research_questions": state["research_questions"],
            "coverage_assessment_ar": state["coverage_assessment_ar"],
            "actions": state["actions"],
            "unresolved_gaps_ar": state["unresolved_gaps_ar"],
        }
        retrieval_output = _execute_actions_resilient(
            repo,
            plan,
            allow_network_materialization=True,
        )
        retrieval_path = (
            episode_root
            / f"research/luna-rounds/round-{round_no:02d}-retrieval-v4.json"
        )
        _atomic_write(retrieval_path, retrieval_output)

        previous_state = state
        session["status"] = "CONTINUE_RESEARCH"
        _atomic_write(session_path, session)

    # Max rounds used without completion. Do not make a seventh call.
    session["status"] = "MAX_AUTHORIZED_ROUNDS_REACHED_REVIEW_REQUIRED"
    session["research_complete"] = False
    session["updated_at_utc"] = _now()
    _atomic_write(session_path, session)
    print("SIRAJ_LUNA_RESEARCH_SESSION_V4_STOPPED")
    print("REASON=MAX_AUTHORIZED_ROUNDS_REACHED")
    print(f"ROUNDS_USED={MAX_LUNA_CALLS}")
    print(f"CONSERVATIVE_TEXT_COST_USD={cumulative_text_cost:.8f}")
    print(f"WEB_SEARCH_CALLS_OBSERVED={cumulative_web_calls}")
    print("AUTOMATIC_RETRIES=0")
    print("NEXT_STAGE=HUMAN_REVIEW_BEFORE_ANY_ADDITIONAL_LUNA_CALL")

def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        fn = getattr(stream, "reconfigure", None)
        if callable(fn):
            fn(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument(
        "--run-authorized",
        action="store_true",
        help="Run the explicitly authorized paid Luna research session.",
    )
    args = ap.parse_args()
    if not args.run_authorized:
        raise SystemExit("EXPLICIT_FLAG_REQUIRED:--run-authorized")
    run(Path(args.repo).resolve())

if __name__ == "__main__":
    main()
