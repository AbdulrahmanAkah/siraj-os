"""SIRAJ V5 — Luna Source Claim Matrix stage.

Uses the V5 unbounded/adaptive runtime:
- no assistant-authored call-count cap
- no assistant-authored cost cap
- no assistant-authored max_output_tokens
- no fixed pacing delay
- high reasoning
- no automatic paid retry
- raw provider response persisted before parsing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.application.siraj_luna_adaptive_transport_v5 import (
    post_luna_once,
)

MODEL = "gpt-5.6-luna"
EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
STAGE = "SOURCE_CLAIM_MATRIX"


class SourceClaimMatrixError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise SourceClaimMatrixError(f"JSON_READ_FAILED:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise SourceClaimMatrixError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def _exclusive_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise SourceClaimMatrixError(
            f"EXCLUSIVE_FILE_ALREADY_EXISTS:{path}"
        ) from exc
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


def _append_jsonl(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)


def _sha_json(value: Mapping[str, Any]) -> str:
    raw = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _strict_object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }


def _schema() -> dict[str, Any]:
    source = _strict_object(
        {
            "source_id": {"type": "string"},
            "source_type": {
                "type": "string",
                "enum": [
                    "QURAN",
                    "HADITH",
                    "SHAMELA",
                    "WEB",
                    "ACADEMIC",
                    "REFERENCE",
                ],
            },
            "title": {"type": "string"},
            "author_or_publisher": {"type": "string"},
            "locator_or_url": {"type": "string"},
            "evidence_summary_ar": {"type": "string"},
            "verification_status": {
                "type": "string",
                "enum": [
                    "VERIFIED_FOR_THIS_EPISODE",
                    "MATERIALIZED_LOCAL",
                    "REFERENCE_ONLY",
                    "NEEDS_RESEARCH_REOPEN",
                ],
            },
            "canonical_use_ar": {"type": "string"},
            "limitations_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
        }
    )

    claim = _strict_object(
        {
            "claim_id": {"type": "string"},
            "claim_ar": {"type": "string"},
            "claim_class": {
                "type": "string",
                "enum": [
                    "CORE_NARRATIVE",
                    "CONTEXT",
                    "INTERPRETIVE",
                    "DISPUTED_DETAIL",
                    "EDITORIAL_BRIDGE",
                ],
            },
            "evidence_posture": {
                "type": "string",
                "enum": [
                    "QURAN_EXPLICIT",
                    "AUTHENTIC_SUNNAH",
                    "ACCEPTED_ATHAR",
                    "QUALIFIED_REPORT",
                    "SCHOLARLY_INTERPRETATION",
                    "EDITORIAL_BRIDGE",
                    "INSUFFICIENT",
                ],
            },
            "assertion_mode": {
                "type": "string",
                "enum": [
                    "STATE_AS_FACT",
                    "ATTRIBUTE_AND_QUALIFY",
                    "PRESENT_AS_DISPUTED",
                    "EDITORIAL_ONLY",
                    "EXCLUDE",
                ],
            },
            "confidence": {
                "type": "string",
                "enum": ["HIGH", "MEDIUM", "LOW"],
            },
            "source_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "qualification_ar": {"type": "string"},
            "contradictions_or_variants_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
            "israiliyyat_risk": {
                "type": "string",
                "enum": ["NONE", "POSSIBLE", "HIGH"],
            },
            "script_eligibility": {
                "type": "string",
                "enum": [
                    "ELIGIBLE",
                    "ELIGIBLE_WITH_QUALIFICATION",
                    "EDITORIAL_ONLY",
                    "INELIGIBLE",
                ],
            },
            "narrative_role_ar": {"type": "string"},
            "event_id": {"type": "string"},
        }
    )

    event = _strict_object(
        {
            "event_id": {"type": "string"},
            "chronology_order": {"type": "integer"},
            "title_ar": {"type": "string"},
            "claim_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "narrative_purpose_ar": {"type": "string"},
        }
    )

    exclusion = _strict_object(
        {
            "item_ar": {"type": "string"},
            "reason_ar": {"type": "string"},
            "source_or_origin_ar": {"type": "string"},
        }
    )

    gap = _strict_object(
        {
            "gap_id": {"type": "string"},
            "gap_ar": {"type": "string"},
            "severity": {
                "type": "string",
                "enum": ["BLOCKING", "NON_BLOCKING"],
            },
            "recommended_action_ar": {"type": "string"},
        }
    )

    return _strict_object(
        {
            "schema_version": {
                "type": "string",
                "enum": ["siraj-luna-source-claim-matrix-v5"],
            },
            "stage_owner": {"type": "string", "enum": ["LUNA"]},
            "stage": {
                "type": "string",
                "enum": ["SOURCE_CLAIM_MATRIX"],
            },
            "status": {
                "type": "string",
                "enum": [
                    "PASS",
                    "NEEDS_RESEARCH_REOPEN",
                ],
            },
            "episode_id": {
                "type": "string",
                "enum": [EPISODE_ID],
            },
            "working_title_ar": {"type": "string"},
            "scope_ar": {"type": "string"},
            "canonical_source_package": {
                "type": "array",
                "items": source,
            },
            "claim_matrix": {
                "type": "array",
                "items": claim,
            },
            "event_structure": {
                "type": "array",
                "items": event,
            },
            "excluded_material": {
                "type": "array",
                "items": exclusion,
            },
            "research_gaps": {
                "type": "array",
                "items": gap,
            },
            "editorial_rules_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
            "handoff_summary_ar": {"type": "string"},
        }
    )


def _validate_strict_schema(node: Any, path: str = "$") -> None:
    if not isinstance(node, Mapping):
        return

    if node.get("type") == "object":
        if node.get("additionalProperties") is not False:
            raise SourceClaimMatrixError(
                f"STRICT_SCHEMA_ADDITIONAL_PROPERTIES_FALSE_REQUIRED:{path}"
            )
        props = node.get("properties")
        required = node.get("required")
        if not isinstance(props, Mapping):
            raise SourceClaimMatrixError(
                f"STRICT_SCHEMA_PROPERTIES_REQUIRED:{path}"
            )
        if not isinstance(required, list):
            raise SourceClaimMatrixError(
                f"STRICT_SCHEMA_REQUIRED_ARRAY_REQUIRED:{path}"
            )
        if set(required) != set(props.keys()):
            raise SourceClaimMatrixError(
                f"STRICT_SCHEMA_ALL_PROPERTIES_REQUIRED:{path}"
            )
        for name, child in props.items():
            _validate_strict_schema(
                child,
                f"{path}.properties.{name}",
            )

    items = node.get("items")
    if isinstance(items, Mapping):
        _validate_strict_schema(items, f"{path}.items")


def _extract_output_text(response: Mapping[str, Any]) -> str:
    output = response.get("output")
    parts: list[str] = []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, Mapping):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, Mapping):
                    continue
                if block.get("type") == "output_text":
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
    if parts:
        return "".join(parts)

    direct = response.get("output_text")
    if isinstance(direct, str):
        return direct

    raise SourceClaimMatrixError("OPENAI_OUTPUT_TEXT_NOT_FOUND")


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


def _base_text_cost_usd(input_tokens: int, output_tokens: int) -> float:
    # Locked SIRAJ user-confirmed base Luna rates.
    return round(
        input_tokens / 1_000_000 * 0.20
        + output_tokens / 1_000_000 * 1.20,
        8,
    )


def _validate_result(value: Mapping[str, Any]) -> None:
    if value.get("schema_version") != "siraj-luna-source-claim-matrix-v5":
        raise SourceClaimMatrixError("SCHEMA_VERSION_INVALID")
    if value.get("stage_owner") != "LUNA":
        raise SourceClaimMatrixError("STAGE_OWNER_NOT_LUNA")
    if value.get("stage") != STAGE:
        raise SourceClaimMatrixError("STAGE_INVALID")
    if value.get("episode_id") != EPISODE_ID:
        raise SourceClaimMatrixError("EPISODE_ID_INVALID")

    status = value.get("status")
    if status not in {"PASS", "NEEDS_RESEARCH_REOPEN"}:
        raise SourceClaimMatrixError(f"STATUS_INVALID:{status}")

    sources = value.get("canonical_source_package")
    claims = value.get("claim_matrix")
    events = value.get("event_structure")
    gaps = value.get("research_gaps")

    if not isinstance(sources, list) or not sources:
        raise SourceClaimMatrixError("CANONICAL_SOURCE_PACKAGE_EMPTY")
    if not isinstance(claims, list) or not claims:
        raise SourceClaimMatrixError("CLAIM_MATRIX_EMPTY")
    if not isinstance(events, list) or not events:
        raise SourceClaimMatrixError("EVENT_STRUCTURE_EMPTY")
    if not isinstance(gaps, list):
        raise SourceClaimMatrixError("RESEARCH_GAPS_ARRAY_REQUIRED")

    source_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, Mapping):
            raise SourceClaimMatrixError("SOURCE_OBJECT_REQUIRED")
        sid = str(source.get("source_id") or "").strip()
        if not sid:
            raise SourceClaimMatrixError("SOURCE_ID_REQUIRED")
        if sid in source_ids:
            raise SourceClaimMatrixError(f"DUPLICATE_SOURCE_ID:{sid}")
        source_ids.add(sid)

    claim_ids: set[str] = set()
    for claim in claims:
        if not isinstance(claim, Mapping):
            raise SourceClaimMatrixError("CLAIM_OBJECT_REQUIRED")
        cid = str(claim.get("claim_id") or "").strip()
        if not cid:
            raise SourceClaimMatrixError("CLAIM_ID_REQUIRED")
        if cid in claim_ids:
            raise SourceClaimMatrixError(f"DUPLICATE_CLAIM_ID:{cid}")
        claim_ids.add(cid)

        mode = claim.get("assertion_mode")
        posture = claim.get("evidence_posture")
        eligibility = claim.get("script_eligibility")
        refs = claim.get("source_ids")
        if not isinstance(refs, list):
            raise SourceClaimMatrixError(
                f"CLAIM_SOURCE_IDS_ARRAY_REQUIRED:{cid}"
            )
        unknown = [
            str(ref)
            for ref in refs
            if str(ref) not in source_ids
        ]
        if unknown:
            raise SourceClaimMatrixError(
                f"CLAIM_UNKNOWN_SOURCE_IDS:{cid}:{unknown}"
            )

        if posture == "INSUFFICIENT" and mode != "EXCLUDE":
            raise SourceClaimMatrixError(
                f"INSUFFICIENT_CLAIM_MUST_BE_EXCLUDED:{cid}"
            )
        if mode == "EXCLUDE" and eligibility != "INELIGIBLE":
            raise SourceClaimMatrixError(
                f"EXCLUDED_CLAIM_MUST_BE_INELIGIBLE:{cid}"
            )
        if mode == "STATE_AS_FACT" and not refs:
            raise SourceClaimMatrixError(
                f"FACT_CLAIM_REQUIRES_SOURCE:{cid}"
            )

    event_ids: set[str] = set()
    for event in events:
        if not isinstance(event, Mapping):
            raise SourceClaimMatrixError("EVENT_OBJECT_REQUIRED")
        eid = str(event.get("event_id") or "").strip()
        if not eid:
            raise SourceClaimMatrixError("EVENT_ID_REQUIRED")
        if eid in event_ids:
            raise SourceClaimMatrixError(f"DUPLICATE_EVENT_ID:{eid}")
        event_ids.add(eid)
        refs = event.get("claim_ids")
        if not isinstance(refs, list):
            raise SourceClaimMatrixError(
                f"EVENT_CLAIM_IDS_ARRAY_REQUIRED:{eid}"
            )
        unknown = [
            str(ref)
            for ref in refs
            if str(ref) not in claim_ids
        ]
        if unknown:
            raise SourceClaimMatrixError(
                f"EVENT_UNKNOWN_CLAIM_IDS:{eid}:{unknown}"
            )

    if status == "PASS":
        blocking = [
            gap
            for gap in gaps
            if isinstance(gap, Mapping)
            and gap.get("severity") == "BLOCKING"
        ]
        if blocking:
            raise SourceClaimMatrixError(
                "PASS_STATUS_CANNOT_HAVE_BLOCKING_RESEARCH_GAPS"
            )


def _system_prompt() -> str:
    return """
أنت Luna، المدير المركزي التحريري والبحثي لسلسلة سراج.

المرحلة الحالية حصراً: SOURCE_CLAIM_MATRIX.

مهمتك ليست كتابة السكربت الآن، ولا تحديد مدة الحلقة، ولا بناء storyboard.
حوّل البحث النهائي المرفق إلى حزمة مصادر معيارية ومصفوفة ادعاءات صارمة
يمكن أن تعتمد عليها المراحل اللاحقة دون خلط بين القطعي، والصحيح، والتفسيري،
والمختلف فيه، والإسرائيليات، والجسور التحريرية.

قواعد حاكمة:
1) لا تخترع مصدرًا أو locator أو URL غير موجود في مادة البحث.
2) لا تجعل مجرد وجود نص حديث دليلاً على صحته؛ التزم بوضع التحقق المسجل.
3) القرآن الصريح أعلى مرتبة فيما يثبته نصه مباشرة.
4) الحديث الصحيح المقبول يُفصل عن الأثر والرواية والتفسير.
5) التفاصيل المختلف فيها تُنسب وتُقيّد، ولا تُروى كحقيقة قطعية.
6) الإسرائيليات أو التفاصيل غير المسندة تُستبعد من الادعاءات الواقعية، أو
   تُصنف بوضوح شديد إن كان لذكرها قيمة تفسيرية.
7) كل ادعاء STATE_AS_FACT يجب أن يرتبط بمصدر حقيقي داخل الحزمة.
8) كل ادعاء غير كافٍ يجب أن يكون EXCLUDE + INELIGIBLE.
9) لا تغيّر نطاق الحلقة بلا سبب بحثي. إذا كان نقص الدليل يمنع بناء مصفوفة
   موثوقة، أعد NEEDS_RESEARCH_REOPEN وحدد الفجوات المانعة بدقة.
10) إذا كانت الأدلة كافية، أعد PASS بلا فجوات BLOCKING.
11) لا تفرض أي عدد ثابت للادعاءات أو المصادر أو الأحداث؛ غطِّ المادة بقدر
   ما تحتاجه فعليًا.
12) لا تختصر المصدر إلى درجة تفقد Luna التالية سبب قبول أو تقييد الادعاء.

الخرج JSON منضبط وفق المخطط فقط.
""".strip()


def _request(research: Mapping[str, Any]) -> dict[str, Any]:
    schema = _schema()
    _validate_strict_schema(schema)
    return {
        "model": MODEL,
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
                            {
                                "task": STAGE,
                                "episode_id": EPISODE_ID,
                                "completed_research": research,
                                "required_handoff": (
                                    "canonical source package + claim matrix "
                                    "+ event structure + exclusions + gaps"
                                ),
                            },
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
                "name": "siraj_luna_source_claim_matrix_v5",
                "strict": True,
                "schema": schema,
            },
        },
    }


def run(repo: Path) -> None:
    repo = repo.resolve()
    episode = repo / "projects" / EPISODE_ID
    if not episode.is_dir():
        raise SourceClaimMatrixError("EPISODE_ROOT_MISSING")

    research_path = episode / "research/luna-research-final-v4.json"
    auth_path = (
        episode
        / "orchestration/luna-source-claim-matrix-authorization-v5.json"
    )
    combined_path = (
        episode
        / "research/luna-source-claim-matrix-v5.json"
    )
    source_package_path = (
        episode
        / "research/canonical-source-package-v5.json"
    )
    claim_matrix_path = (
        episode
        / "research/source-claim-matrix-v5.json"
    )
    state_path = (
        episode
        / "orchestration/source-claim-matrix-v5-state.json"
    )
    runtime_marker = (
        episode
        / "orchestration/luna-runtime-v5-active.json"
    )
    lock_dir = (
        episode
        / "orchestration/luna-v5/source-claim-matrix/locks"
    )
    raw_dir = (
        episode
        / "orchestration/luna-v5/source-claim-matrix/raw-responses"
    )
    ledger = (
        episode
        / "orchestration/luna-v5/source-claim-matrix/attempt-ledger.jsonl"
    )
    receipt_dir = (
        episode
        / "orchestration/luna-v5/source-claim-matrix/receipts"
    )

    if combined_path.is_file():
        existing = _read_json(combined_path)
        _validate_result(existing)
        print("SIRAJ_LUNA_SOURCE_CLAIM_MATRIX_V5_ALREADY_COMPLETE")
        print(f"STATUS={existing.get('status')}")
        print(f"OUTPUT={combined_path}")
        return

    research = _read_json(research_path)
    if research.get("status") != "PASS":
        raise SourceClaimMatrixError(
            f"FINAL_RESEARCH_NOT_PASS:{research.get('status')}"
        )

    auth = _read_json(auth_path)
    if auth.get("status") != "ACTIVE":
        raise SourceClaimMatrixError(
            f"STAGE_AUTHORIZATION_NOT_ACTIVE:{auth.get('status')}"
        )
    if auth.get("stage") != STAGE:
        raise SourceClaimMatrixError("STAGE_AUTHORIZATION_MISMATCH")
    if auth.get("automatic_retry") is not False:
        raise SourceClaimMatrixError("AUTOMATIC_RETRY_MUST_BE_FALSE")

    request_payload = _request(research)
    request_hash = _sha_json(request_payload)
    request_uuid = str(uuid.uuid4())

    # A previously prepared submission without a terminal record requires
    # manual inspection; never silently issue a second paid request.
    if ledger.is_file():
        lines = [
            line.strip()
            for line in ledger.read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if line.strip()
        ]
        if lines:
            last = json.loads(lines[-1])
            if (
                isinstance(last, dict)
                and last.get("event") == "PREPARED"
            ):
                raise SourceClaimMatrixError(
                    "PREVIOUS_PREPARED_ATTEMPT_REQUIRES_MANUAL_REVIEW"
                )

    lock_path = lock_dir / f"{request_uuid}.json"
    _exclusive_write(
        lock_path,
        {
            "schema_version": "siraj-luna-stage-request-lock-v5",
            "stage": STAGE,
            "episode_id": EPISODE_ID,
            "request_uuid": request_uuid,
            "request_sha256": request_hash,
            "authorization_id": auth.get("authorization_id"),
            "assistant_authored_call_limit": None,
            "assistant_authored_cost_cap_usd": None,
            "assistant_authored_max_output_tokens": None,
            "automatic_retry": False,
            "created_at_utc": _now(),
        },
    )
    _append_jsonl(
        ledger,
        {
            "event": "PREPARED",
            "stage": STAGE,
            "request_uuid": request_uuid,
            "request_sha256": request_hash,
            "timestamp_utc": _now(),
        },
    )

    state = {
        "schema_version": "siraj-source-claim-matrix-v5-state",
        "episode_id": EPISODE_ID,
        "stage": STAGE,
        "status": "SUBMITTING",
        "request_uuid": request_uuid,
        "automatic_retry": False,
        "updated_at_utc": _now(),
    }
    _atomic_write(state_path, state)

    try:
        response = post_luna_once(
            repo,
            request_payload,
            client_request_id=request_uuid,
        )
    except Exception as exc:
        _append_jsonl(
            ledger,
            {
                "event": "FAILED_NO_AUTO_RETRY",
                "stage": STAGE,
                "request_uuid": request_uuid,
                "error": str(exc),
                "timestamp_utc": _now(),
            },
        )
        state["status"] = "FAILED_NO_AUTO_RETRY"
        state["error"] = str(exc)
        state["updated_at_utc"] = _now()
        _atomic_write(state_path, state)
        raise

    raw_path = raw_dir / f"{request_uuid}.json"
    _exclusive_write(raw_path, response)

    response_status = str(response.get("status") or "")
    if response_status and response_status != "completed":
        input_tokens, output_tokens, cached = _usage(response)
        _append_jsonl(
            ledger,
            {
                "event": "CONSUMED_UNUSABLE_NO_AUTO_RETRY",
                "stage": STAGE,
                "request_uuid": request_uuid,
                "response_id": response.get("id"),
                "response_status": response_status,
                "input_tokens": input_tokens,
                "cached_input_tokens": cached,
                "output_tokens": output_tokens,
                "timestamp_utc": _now(),
            },
        )
        state["status"] = "UNUSABLE_RESPONSE_NO_AUTO_RETRY"
        state["response_status"] = response_status
        state["incomplete_details"] = response.get(
            "incomplete_details"
        )
        state["raw_response_path"] = str(raw_path)
        state["updated_at_utc"] = _now()
        _atomic_write(state_path, state)
        raise SourceClaimMatrixError(
            f"LUNA_RESPONSE_NOT_COMPLETED:{response_status}"
        )

    text = _extract_output_text(response)
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        input_tokens, output_tokens, cached = _usage(response)
        _append_jsonl(
            ledger,
            {
                "event": "CONSUMED_INVALID_JSON_NO_AUTO_RETRY",
                "stage": STAGE,
                "request_uuid": request_uuid,
                "response_id": response.get("id"),
                "input_tokens": input_tokens,
                "cached_input_tokens": cached,
                "output_tokens": output_tokens,
                "json_error": str(exc),
                "timestamp_utc": _now(),
            },
        )
        state["status"] = "INVALID_JSON_NO_AUTO_RETRY"
        state["json_error"] = str(exc)
        state["raw_response_path"] = str(raw_path)
        state["updated_at_utc"] = _now()
        _atomic_write(state_path, state)
        raise SourceClaimMatrixError(
            "LUNA_SOURCE_CLAIM_MATRIX_JSON_INVALID"
        ) from exc

    if not isinstance(result, dict):
        raise SourceClaimMatrixError("LUNA_RESULT_OBJECT_REQUIRED")
    _validate_result(result)

    input_tokens, output_tokens, cached = _usage(response)
    base_cost = _base_text_cost_usd(
        input_tokens,
        output_tokens,
    )

    combined = dict(result)
    combined["_siraj_runtime"] = {
        "runtime": "V5_UNBOUNDED_ADAPTIVE",
        "request_uuid": request_uuid,
        "request_sha256": request_hash,
        "response_id": response.get("id"),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "output_tokens": output_tokens,
        "base_text_cost_usd": base_cost,
        "base_rates_usd_per_million": {
            "input": 0.20,
            "output": 1.20,
        },
        "long_context_surcharge": (
            "NOT_CALCULATED_OFFICIAL_THRESHOLD_NOT_STORED"
        ),
        "assistant_authored_call_limit": None,
        "assistant_authored_cost_cap_usd": None,
        "assistant_authored_max_output_tokens": None,
        "automatic_retry": False,
        "completed_at_utc": _now(),
    }

    _atomic_write(combined_path, combined)
    _atomic_write(
        source_package_path,
        {
            "schema_version": "siraj-canonical-source-package-v5",
            "episode_id": EPISODE_ID,
            "status": result["status"],
            "working_title_ar": result["working_title_ar"],
            "scope_ar": result["scope_ar"],
            "sources": result["canonical_source_package"],
            "research_gaps": result["research_gaps"],
            "generated_by": "LUNA",
            "source_matrix_path": str(combined_path),
        },
    )
    _atomic_write(
        claim_matrix_path,
        {
            "schema_version": "siraj-source-claim-matrix-v5",
            "episode_id": EPISODE_ID,
            "status": result["status"],
            "claims": result["claim_matrix"],
            "event_structure": result["event_structure"],
            "excluded_material": result["excluded_material"],
            "editorial_rules_ar": result["editorial_rules_ar"],
            "handoff_summary_ar": result["handoff_summary_ar"],
            "generated_by": "LUNA",
            "canonical_source_package_path": str(source_package_path),
        },
    )

    receipt_path = receipt_dir / f"{request_uuid}.json"
    _exclusive_write(
        receipt_path,
        {
            "schema_version": "siraj-luna-stage-receipt-v5",
            "episode_id": EPISODE_ID,
            "stage": STAGE,
            "request_uuid": request_uuid,
            "response_id": response.get("id"),
            "input_tokens": input_tokens,
            "cached_input_tokens": cached,
            "output_tokens": output_tokens,
            "base_text_cost_usd": base_cost,
            "status": result["status"],
            "automatic_retry": False,
            "completed_at_utc": _now(),
        },
    )
    _append_jsonl(
        ledger,
        {
            "event": "COMPLETE",
            "stage": STAGE,
            "request_uuid": request_uuid,
            "response_id": response.get("id"),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "base_text_cost_usd": base_cost,
            "result_status": result["status"],
            "timestamp_utc": _now(),
        },
    )

    state["status"] = result["status"]
    state["response_id"] = response.get("id")
    state["combined_output_path"] = str(combined_path)
    state["canonical_source_package_path"] = str(
        source_package_path
    )
    state["claim_matrix_path"] = str(claim_matrix_path)
    state["updated_at_utc"] = _now()
    _atomic_write(state_path, state)

    auth["status"] = "COMPLETED"
    auth["result_status"] = result["status"]
    auth["completed_request_uuid"] = request_uuid
    auth["completed_at_utc"] = _now()
    _atomic_write(auth_path, auth)

    if runtime_marker.is_file():
        marker = _read_json(runtime_marker)
        marker["source_claim_matrix_v5_status"] = result["status"]
        marker["next_stage"] = (
            "STORY_ARCHITECTURE"
            if result["status"] == "PASS"
            else "SOURCE_RESEARCH_REOPEN"
        )
        marker["updated_at_utc"] = _now()
        _atomic_write(runtime_marker, marker)

    print("SIRAJ_LUNA_SOURCE_CLAIM_MATRIX_V5_COMPLETE")
    print(f"STATUS={result['status']}")
    print(
        "CANONICAL_SOURCES="
        + str(len(result["canonical_source_package"]))
    )
    print(
        "CLAIMS="
        + str(len(result["claim_matrix"]))
    )
    print(
        "EVENTS="
        + str(len(result["event_structure"]))
    )
    print(
        "EXCLUDED_MATERIAL="
        + str(len(result["excluded_material"]))
    )
    print(
        "RESEARCH_GAPS="
        + str(len(result["research_gaps"]))
    )
    print(f"INPUT_TOKENS={input_tokens}")
    print(f"OUTPUT_TOKENS={output_tokens}")
    print(f"BASE_TEXT_COST_USD={base_cost:.8f}")
    print("ASSISTANT_AUTHORED_CALL_LIMIT=NONE")
    print("ASSISTANT_AUTHORED_COST_CAP_USD=NONE")
    print("ASSISTANT_AUTHORED_MAX_OUTPUT_TOKENS=NONE")
    print("AUTOMATIC_RETRIES=0")
    print(f"OUTPUT={combined_path}")
    print(
        "NEXT_STAGE="
        + (
            "STORY_ARCHITECTURE"
            if result["status"] == "PASS"
            else "SOURCE_RESEARCH_REOPEN"
        )
    )


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        fn = getattr(stream, "reconfigure", None)
        if callable(fn):
            fn(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-authorized", action="store_true")
    args = parser.parse_args()

    if not args.run_authorized:
        raise SystemExit(
            "EXPLICIT_FLAG_REQUIRED:--run-authorized"
        )

    run(Path(args.repo))


if __name__ == "__main__":
    main()
