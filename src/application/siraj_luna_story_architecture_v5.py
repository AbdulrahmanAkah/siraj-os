"""SIRAJ V5 — Luna Story Architecture stage.

Purpose:
- Build the episode narrative architecture from the approved V5 claim matrix.
- Do NOT write the final script yet.
- Do NOT impose a target duration, fixed beat count, shot count, or TTS count.
- Luna may iteratively refine the architecture until PASS.
- Deliberate Luna iterations are not provider retries.
- Provider/network failures are never retried automatically.
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

from src.application.siraj_luna_adaptive_transport_v5 import post_luna_once

MODEL = "gpt-5.6-luna"
EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
STAGE = "STORY_ARCHITECTURE"


class StoryArchitectureError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise StoryArchitectureError(f"JSON_READ_FAILED:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise StoryArchitectureError(f"JSON_OBJECT_REQUIRED:{path}")
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
        raise StoryArchitectureError(
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
        json.dumps(dict(payload), ensure_ascii=False, sort_keys=True) + "\n"
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
    hook = _strict_object(
        {
            "hook_purpose_ar": {"type": "string"},
            "hook_strategy_ar": {"type": "string"},
            "hook_information_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
            "hook_claim_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "hook_must_not_do_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
        }
    )

    beat = _strict_object(
        {
            "beat_id": {"type": "string"},
            "order": {"type": "integer"},
            "beat_type": {
                "type": "string",
                "enum": [
                    "HOOK",
                    "ORIENTATION",
                    "SETUP",
                    "ESCALATION",
                    "TURN",
                    "REVELATION",
                    "CONSEQUENCE",
                    "REFLECTION",
                    "RESOLUTION",
                    "BRIDGE",
                ],
            },
            "title_ar": {"type": "string"},
            "dramatic_function_ar": {"type": "string"},
            "narrative_content_ar": {"type": "string"},
            "event_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "claim_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "assertion_guidance_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
            "uncertainty_handling_ar": {"type": "string"},
            "tension_level": {
                "type": "string",
                "enum": ["LOW", "MEDIUM", "HIGH", "PEAK"],
            },
            "emotional_register_ar": {"type": "string"},
            "transition_in_ar": {"type": "string"},
            "transition_out_ar": {"type": "string"},
            "continuity_dependencies": {
                "type": "array",
                "items": {"type": "string"},
            },
            "forbidden_material_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
        }
    )

    act = _strict_object(
        {
            "act_id": {"type": "string"},
            "order": {"type": "integer"},
            "title_ar": {"type": "string"},
            "purpose_ar": {"type": "string"},
            "entry_state_ar": {"type": "string"},
            "exit_state_ar": {"type": "string"},
            "beat_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "tension_progression_ar": {"type": "string"},
        }
    )

    tension_point = _strict_object(
        {
            "order": {"type": "integer"},
            "label_ar": {"type": "string"},
            "level": {
                "type": "string",
                "enum": ["LOW", "MEDIUM", "HIGH", "PEAK"],
            },
            "reason_ar": {"type": "string"},
            "beat_id": {"type": "string"},
        }
    )

    handoff = _strict_object(
        {
            "script_must_preserve_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
            "script_must_avoid_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
            "pronunciation_attention_terms_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
            "narrative_voice_ar": {"type": "string"},
            "opening_performance_direction_ar": {"type": "string"},
            "closing_performance_direction_ar": {"type": "string"},
            "next_episode_bridge_ar": {"type": "string"},
        }
    )

    revision = _strict_object(
        {
            "revision_needed": {"type": "boolean"},
            "revision_reason_ar": {"type": "string"},
            "revision_targets_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
        }
    )

    return _strict_object(
        {
            "schema_version": {
                "type": "string",
                "enum": ["siraj-luna-story-architecture-v5"],
            },
            "stage_owner": {"type": "string", "enum": ["LUNA"]},
            "stage": {
                "type": "string",
                "enum": ["STORY_ARCHITECTURE"],
            },
            "status": {
                "type": "string",
                "enum": [
                    "PASS",
                    "CONTINUE_ARCHITECTURE",
                    "NEEDS_CLAIM_MATRIX_REOPEN",
                ],
            },
            "episode_id": {
                "type": "string",
                "enum": [EPISODE_ID],
            },
            "working_title_ar": {"type": "string"},
            "central_question_ar": {"type": "string"},
            "episode_promise_ar": {"type": "string"},
            "narrative_thesis_ar": {"type": "string"},
            "opening_hook": hook,
            "acts": {
                "type": "array",
                "items": act,
            },
            "beats": {
                "type": "array",
                "items": beat,
            },
            "tension_curve": {
                "type": "array",
                "items": tension_point,
            },
            "core_revelations_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
            "editorial_bridges_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
            "uncertainty_policy_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
            "excluded_material_guard_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
            "final_script_handoff": handoff,
            "self_review_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
            "revision": revision,
        }
    )


def _validate_strict_schema(node: Any, path: str = "$") -> None:
    if not isinstance(node, Mapping):
        return
    if node.get("type") == "object":
        if node.get("additionalProperties") is not False:
            raise StoryArchitectureError(
                f"STRICT_SCHEMA_ADDITIONAL_PROPERTIES_FALSE_REQUIRED:{path}"
            )
        props = node.get("properties")
        required = node.get("required")
        if not isinstance(props, Mapping):
            raise StoryArchitectureError(
                f"STRICT_SCHEMA_PROPERTIES_REQUIRED:{path}"
            )
        if not isinstance(required, list):
            raise StoryArchitectureError(
                f"STRICT_SCHEMA_REQUIRED_ARRAY_REQUIRED:{path}"
            )
        if set(required) != set(props.keys()):
            raise StoryArchitectureError(
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
    raise StoryArchitectureError("OPENAI_OUTPUT_TEXT_NOT_FOUND")


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
    return round(
        input_tokens / 1_000_000 * 0.20
        + output_tokens / 1_000_000 * 1.20,
        8,
    )


def _claim_ids(claim_matrix: Mapping[str, Any]) -> set[str]:
    claims = claim_matrix.get("claims")
    if not isinstance(claims, list):
        raise StoryArchitectureError("CLAIMS_ARRAY_REQUIRED")
    result = set()
    for claim in claims:
        if isinstance(claim, Mapping):
            cid = str(claim.get("claim_id") or "").strip()
            if cid:
                result.add(cid)
    if not result:
        raise StoryArchitectureError("CLAIM_IDS_EMPTY")
    return result


def _event_ids(claim_matrix: Mapping[str, Any]) -> set[str]:
    events = claim_matrix.get("event_structure")
    if not isinstance(events, list):
        raise StoryArchitectureError("EVENT_STRUCTURE_ARRAY_REQUIRED")
    result = set()
    for event in events:
        if isinstance(event, Mapping):
            eid = str(event.get("event_id") or "").strip()
            if eid:
                result.add(eid)
    if not result:
        raise StoryArchitectureError("EVENT_IDS_EMPTY")
    return result


def _validate_result(
    value: Mapping[str, Any],
    claim_matrix: Mapping[str, Any],
) -> None:
    if value.get("schema_version") != "siraj-luna-story-architecture-v5":
        raise StoryArchitectureError("SCHEMA_VERSION_INVALID")
    if value.get("stage_owner") != "LUNA":
        raise StoryArchitectureError("STAGE_OWNER_NOT_LUNA")
    if value.get("stage") != STAGE:
        raise StoryArchitectureError("STAGE_INVALID")
    if value.get("episode_id") != EPISODE_ID:
        raise StoryArchitectureError("EPISODE_ID_INVALID")

    status = value.get("status")
    if status not in {
        "PASS",
        "CONTINUE_ARCHITECTURE",
        "NEEDS_CLAIM_MATRIX_REOPEN",
    }:
        raise StoryArchitectureError(f"STATUS_INVALID:{status}")

    valid_claims = _claim_ids(claim_matrix)
    valid_events = _event_ids(claim_matrix)

    beats = value.get("beats")
    acts = value.get("acts")
    curve = value.get("tension_curve")
    if not isinstance(beats, list) or not beats:
        raise StoryArchitectureError("BEATS_EMPTY")
    if not isinstance(acts, list) or not acts:
        raise StoryArchitectureError("ACTS_EMPTY")
    if not isinstance(curve, list) or not curve:
        raise StoryArchitectureError("TENSION_CURVE_EMPTY")

    beat_ids: set[str] = set()
    beat_orders: list[int] = []
    for beat in beats:
        if not isinstance(beat, Mapping):
            raise StoryArchitectureError("BEAT_OBJECT_REQUIRED")
        bid = str(beat.get("beat_id") or "").strip()
        if not bid:
            raise StoryArchitectureError("BEAT_ID_REQUIRED")
        if bid in beat_ids:
            raise StoryArchitectureError(f"DUPLICATE_BEAT_ID:{bid}")
        beat_ids.add(bid)
        beat_orders.append(int(beat.get("order", 0) or 0))

        claim_refs = beat.get("claim_ids")
        event_refs = beat.get("event_ids")
        if not isinstance(claim_refs, list):
            raise StoryArchitectureError(
                f"BEAT_CLAIM_IDS_ARRAY_REQUIRED:{bid}"
            )
        if not isinstance(event_refs, list):
            raise StoryArchitectureError(
                f"BEAT_EVENT_IDS_ARRAY_REQUIRED:{bid}"
            )

        unknown_claims = [
            str(ref)
            for ref in claim_refs
            if str(ref) not in valid_claims
        ]
        unknown_events = [
            str(ref)
            for ref in event_refs
            if str(ref) not in valid_events
        ]
        if unknown_claims:
            raise StoryArchitectureError(
                f"BEAT_UNKNOWN_CLAIMS:{bid}:{unknown_claims}"
            )
        if unknown_events:
            raise StoryArchitectureError(
                f"BEAT_UNKNOWN_EVENTS:{bid}:{unknown_events}"
            )

    if beat_orders != sorted(beat_orders):
        raise StoryArchitectureError("BEAT_ORDER_NOT_ASCENDING")

    act_ids: set[str] = set()
    act_orders: list[int] = []
    referenced_beats: set[str] = set()
    for act in acts:
        if not isinstance(act, Mapping):
            raise StoryArchitectureError("ACT_OBJECT_REQUIRED")
        aid = str(act.get("act_id") or "").strip()
        if not aid:
            raise StoryArchitectureError("ACT_ID_REQUIRED")
        if aid in act_ids:
            raise StoryArchitectureError(f"DUPLICATE_ACT_ID:{aid}")
        act_ids.add(aid)
        act_orders.append(int(act.get("order", 0) or 0))
        refs = act.get("beat_ids")
        if not isinstance(refs, list) or not refs:
            raise StoryArchitectureError(
                f"ACT_BEAT_IDS_EMPTY:{aid}"
            )
        unknown = [
            str(ref)
            for ref in refs
            if str(ref) not in beat_ids
        ]
        if unknown:
            raise StoryArchitectureError(
                f"ACT_UNKNOWN_BEATS:{aid}:{unknown}"
            )
        referenced_beats.update(str(ref) for ref in refs)

    if act_orders != sorted(act_orders):
        raise StoryArchitectureError("ACT_ORDER_NOT_ASCENDING")
    if referenced_beats != beat_ids:
        missing = sorted(beat_ids - referenced_beats)
        raise StoryArchitectureError(
            f"NOT_ALL_BEATS_ASSIGNED_TO_ACTS:{missing}"
        )

    for point in curve:
        if not isinstance(point, Mapping):
            raise StoryArchitectureError(
                "TENSION_POINT_OBJECT_REQUIRED"
            )
        bid = str(point.get("beat_id") or "").strip()
        if bid not in beat_ids:
            raise StoryArchitectureError(
                f"TENSION_POINT_UNKNOWN_BEAT:{bid}"
            )

    hook = value.get("opening_hook")
    if not isinstance(hook, Mapping):
        raise StoryArchitectureError("OPENING_HOOK_OBJECT_REQUIRED")
    hook_claims = hook.get("hook_claim_ids")
    if not isinstance(hook_claims, list):
        raise StoryArchitectureError(
            "HOOK_CLAIM_IDS_ARRAY_REQUIRED"
        )
    unknown_hook_claims = [
        str(ref)
        for ref in hook_claims
        if str(ref) not in valid_claims
    ]
    if unknown_hook_claims:
        raise StoryArchitectureError(
            f"HOOK_UNKNOWN_CLAIMS:{unknown_hook_claims}"
        )

    revision = value.get("revision")
    if not isinstance(revision, Mapping):
        raise StoryArchitectureError("REVISION_OBJECT_REQUIRED")
    revision_needed = bool(revision.get("revision_needed"))

    if status == "PASS" and revision_needed:
        raise StoryArchitectureError(
            "PASS_CANNOT_REQUIRE_REVISION"
        )
    if status == "CONTINUE_ARCHITECTURE" and not revision_needed:
        raise StoryArchitectureError(
            "CONTINUE_REQUIRES_REVISION"
        )


def _system_prompt() -> str:
    return """
أنت Luna، المدير المركزي التحريري والبحثي لسلسلة سراج.

المرحلة الحالية حصراً: STORY_ARCHITECTURE.

أمامك حزمة المصادر المعيارية ومصفوفة الادعاءات المعتمدة للحلقة الثانية.
ابنِ الهيكل السردي الذي سيقود كتابة السكربت النهائي لاحقاً.

ممنوع في هذه المرحلة:
- كتابة السكربت النهائي.
- تثبيت مدة للحلقة قبل TTS.
- فرض عدد مشاهد أو لقطات.
- فرض عدد beats أو acts من رقم مسبق.
- إضافة حقيقة لم تعتمدها مصفوفة الادعاءات.
- تحويل رواية مقيّدة أو مختلفاً فيها إلى حقيقة جازمة.
- إعادة المواد المستبعدة بصياغة ملتوية.

المطلوب:
1) حدد السؤال المركزي والوعد السردي والأطروحة.
2) صمم Hook حقيقياً يخدم موضوع الحلقة ولا يكون Clickbait منفصلاً عنها.
3) ابنِ Acts وBeats بالعدد الذي تحتاجه القصة فعلياً فقط.
4) اربط كل Beat بالـclaim_ids والـevent_ids الصحيحة.
5) حافظ على تدرج التوتر: الوسوسة → الاقتراب → الزلة → انكشاف العاقبة
   → الخروج/الهبوط وفق الأدلة المعتمدة → التوبة والرجاء، بحسب ما تسمح به
   المصفوفة فعلاً، لا بحسب التصورات الشائعة.
6) اعزل أي تفصيل يحتاج نسبة أو تقييد، وحدد طريقة قوله لاحقاً.
7) اجعل كل انتقال له وظيفة، ولا تكدّس المعلومات.
8) حافظ على نبرة سراج: تاريخية/فكرية جادة، واضحة، غير وعظية بصورة مباشرة،
   لكنها لا تتجاهل المعنى الإيماني للنصوص.
9) لا تجعل النهاية مجرد توقف؛ اصنع Resolution ثم Bridge طبيعي للحلقة التالية
   فقط إذا كان ذلك مدعوماً ببنية السلسلة.
10) راجع نفسك. إذا كانت البنية غير ناضجة بعد، أعد
    CONTINUE_ARCHITECTURE وحدد revision targets. هذا يسمح بجولة Luna تحريرية
    أخرى مقصودة داخل المرحلة، وليس Retry تقنياً.
11) إذا كشفت مشكلة حقيقية في Claim Matrix تمنع البناء الموثوق، أعد
    NEEDS_CLAIM_MATRIX_REOPEN.
12) عندما تصبح البنية ناضجة فعلاً، أعد PASS.

لا توجد حدود من سراج على عدد جولاتك التحريرية أو حجم البنية. لا تختصر بسبب
أرقام مصطنعة. وفي المقابل لا تستهلك جولة إضافية إن كانت البنية جاهزة بالفعل.

الخرج JSON فقط وفق المخطط.
""".strip()


def _request(
    *,
    claim_package: Mapping[str, Any],
    claim_matrix: Mapping[str, Any],
    previous_architecture: Mapping[str, Any] | None,
    iteration_no: int,
) -> dict[str, Any]:
    schema = _schema()
    _validate_strict_schema(schema)

    context: dict[str, Any] = {
        "task": STAGE,
        "episode_id": EPISODE_ID,
        "iteration_no": iteration_no,
        "canonical_source_package": claim_package,
        "source_claim_matrix": claim_matrix,
    }
    if previous_architecture is not None:
        context["previous_architecture"] = previous_architecture
        context["iteration_instruction"] = (
            "راجع البنية السابقة بالكامل ونفّذ revision targets التي حددتها "
            "بنفسك. لا تحافظ على جزء ضعيف لمجرد أنه ظهر في الجولة السابقة."
        )
    else:
        context["iteration_instruction"] = (
            "هذه أول جولة لبناء Story Architecture من الصفر."
        )

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
                            context,
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
                "name": "siraj_luna_story_architecture_v5",
                "strict": True,
                "schema": schema,
            },
        },
    }


def run(repo: Path) -> None:
    repo = repo.resolve()
    episode = repo / "projects" / EPISODE_ID
    if not episode.is_dir():
        raise StoryArchitectureError("EPISODE_ROOT_MISSING")

    package_path = episode / "research/canonical-source-package-v5.json"
    matrix_path = episode / "research/source-claim-matrix-v5.json"
    auth_path = (
        episode
        / "orchestration/luna-story-architecture-authorization-v5.json"
    )
    output_path = (
        episode
        / "preproduction/luna-story-architecture-v5.json"
    )
    state_path = (
        episode
        / "orchestration/story-architecture-v5-state.json"
    )
    runtime_marker = (
        episode
        / "orchestration/luna-runtime-v5-active.json"
    )
    root = (
        episode
        / "orchestration/luna-v5/story-architecture"
    )
    lock_dir = root / "locks"
    raw_dir = root / "raw-responses"
    round_dir = root / "rounds"
    receipt_dir = root / "receipts"
    ledger = root / "attempt-ledger.jsonl"

    if output_path.is_file():
        existing = _read_json(output_path)
        claim_matrix = _read_json(matrix_path)
        _validate_result(existing, claim_matrix)
        if existing.get("status") == "PASS":
            print("SIRAJ_LUNA_STORY_ARCHITECTURE_V5_ALREADY_COMPLETE")
            print(f"OUTPUT={output_path}")
            return

    claim_package = _read_json(package_path)
    claim_matrix = _read_json(matrix_path)
    if claim_package.get("status") != "PASS":
        raise StoryArchitectureError(
            f"CANONICAL_SOURCE_PACKAGE_NOT_PASS:{claim_package.get('status')}"
        )
    if claim_matrix.get("status") != "PASS":
        raise StoryArchitectureError(
            f"CLAIM_MATRIX_NOT_PASS:{claim_matrix.get('status')}"
        )

    auth = _read_json(auth_path)
    if auth.get("status") != "ACTIVE":
        raise StoryArchitectureError(
            f"STAGE_AUTHORIZATION_NOT_ACTIVE:{auth.get('status')}"
        )
    if auth.get("stage") != STAGE:
        raise StoryArchitectureError("STAGE_AUTHORIZATION_MISMATCH")
    if auth.get("automatic_retry") is not False:
        raise StoryArchitectureError("AUTOMATIC_RETRY_MUST_BE_FALSE")

    previous_architecture: dict[str, Any] | None = None
    iteration_no = 1

    # Recover only fully completed editorial iterations. A PREPARED/failed
    # provider attempt is never silently resubmitted.
    completed_rounds = sorted(round_dir.glob("iteration-*.json"))
    if completed_rounds:
        last_round = _read_json(completed_rounds[-1])
        previous_architecture = last_round
        iteration_no = int(last_round.get("_siraj_iteration_no", 0) or 0) + 1

        if last_round.get("status") == "PASS":
            _atomic_write(output_path, last_round)
            print("SIRAJ_LUNA_STORY_ARCHITECTURE_V5_ALREADY_COMPLETE")
            print(f"OUTPUT={output_path}")
            return
        if last_round.get("status") == "NEEDS_CLAIM_MATRIX_REOPEN":
            raise StoryArchitectureError(
                "PREVIOUS_ITERATION_REQUIRES_CLAIM_MATRIX_REOPEN"
            )

    if ledger.is_file():
        lines = [
            line.strip()
            for line in ledger.read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if line.strip()
        ]
        if lines:
            last_event = json.loads(lines[-1])
            if (
                isinstance(last_event, dict)
                and last_event.get("event") == "PREPARED"
            ):
                raise StoryArchitectureError(
                    "PREVIOUS_PREPARED_ATTEMPT_REQUIRES_MANUAL_REVIEW"
                )
            if (
                isinstance(last_event, dict)
                and last_event.get("event") in {
                    "FAILED_NO_AUTO_RETRY",
                    "CONSUMED_UNUSABLE_NO_AUTO_RETRY",
                    "CONSUMED_INVALID_JSON_NO_AUTO_RETRY",
                }
            ):
                raise StoryArchitectureError(
                    "PREVIOUS_FAILED_ATTEMPT_REQUIRES_MANUAL_REVIEW"
                )

    cumulative_base_text_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    total_iterations_completed = len(completed_rounds)

    for receipt_path in receipt_dir.glob("*.json"):
        receipt = _read_json(receipt_path)
        cumulative_base_text_cost += float(
            receipt.get("base_text_cost_usd", 0) or 0
        )
        total_input_tokens += int(
            receipt.get("input_tokens", 0) or 0
        )
        total_output_tokens += int(
            receipt.get("output_tokens", 0) or 0
        )

    while True:
        request_payload = _request(
            claim_package=claim_package,
            claim_matrix=claim_matrix,
            previous_architecture=previous_architecture,
            iteration_no=iteration_no,
        )
        request_hash = _sha_json(request_payload)
        request_uuid = str(uuid.uuid4())

        lock_path = lock_dir / f"{request_uuid}.json"
        _exclusive_write(
            lock_path,
            {
                "schema_version": "siraj-luna-stage-request-lock-v5",
                "stage": STAGE,
                "episode_id": EPISODE_ID,
                "iteration_no": iteration_no,
                "request_uuid": request_uuid,
                "request_sha256": request_hash,
                "authorization_id": auth.get("authorization_id"),
                "assistant_authored_call_limit": None,
                "assistant_authored_cost_cap_usd": None,
                "assistant_authored_max_output_tokens": None,
                "assistant_authored_fixed_pacing_seconds": None,
                "automatic_retry": False,
                "created_at_utc": _now(),
            },
        )
        _append_jsonl(
            ledger,
            {
                "event": "PREPARED",
                "stage": STAGE,
                "iteration_no": iteration_no,
                "request_uuid": request_uuid,
                "request_sha256": request_hash,
                "timestamp_utc": _now(),
            },
        )

        state = {
            "schema_version": "siraj-story-architecture-v5-state",
            "episode_id": EPISODE_ID,
            "stage": STAGE,
            "status": "SUBMITTING",
            "iteration_no": iteration_no,
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
                    "iteration_no": iteration_no,
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
                    "iteration_no": iteration_no,
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
            state["raw_response_path"] = str(raw_path)
            state["updated_at_utc"] = _now()
            _atomic_write(state_path, state)
            raise StoryArchitectureError(
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
                    "iteration_no": iteration_no,
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
            raise StoryArchitectureError(
                "LUNA_STORY_ARCHITECTURE_JSON_INVALID"
            ) from exc

        if not isinstance(result, dict):
            raise StoryArchitectureError("LUNA_RESULT_OBJECT_REQUIRED")
        _validate_result(result, claim_matrix)

        input_tokens, output_tokens, cached = _usage(response)
        base_cost = _base_text_cost_usd(
            input_tokens,
            output_tokens,
        )
        cumulative_base_text_cost += base_cost
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens
        total_iterations_completed += 1

        round_result = dict(result)
        round_result["_siraj_iteration_no"] = iteration_no
        round_result["_siraj_runtime"] = {
            "runtime": "V5_UNBOUNDED_ADAPTIVE",
            "request_uuid": request_uuid,
            "request_sha256": request_hash,
            "response_id": response.get("id"),
            "input_tokens": input_tokens,
            "cached_input_tokens": cached,
            "output_tokens": output_tokens,
            "base_text_cost_usd": base_cost,
            "assistant_authored_call_limit": None,
            "assistant_authored_cost_cap_usd": None,
            "assistant_authored_max_output_tokens": None,
            "assistant_authored_fixed_pacing_seconds": None,
            "automatic_retry": False,
            "completed_at_utc": _now(),
        }

        round_path = (
            round_dir
            / f"iteration-{iteration_no:03d}.json"
        )
        _exclusive_write(round_path, round_result)

        receipt_path = receipt_dir / f"{request_uuid}.json"
        _exclusive_write(
            receipt_path,
            {
                "schema_version": "siraj-luna-stage-receipt-v5",
                "episode_id": EPISODE_ID,
                "stage": STAGE,
                "iteration_no": iteration_no,
                "request_uuid": request_uuid,
                "response_id": response.get("id"),
                "input_tokens": input_tokens,
                "cached_input_tokens": cached,
                "output_tokens": output_tokens,
                "base_text_cost_usd": base_cost,
                "result_status": result["status"],
                "automatic_retry": False,
                "completed_at_utc": _now(),
            },
        )
        _append_jsonl(
            ledger,
            {
                "event": "COMPLETE",
                "stage": STAGE,
                "iteration_no": iteration_no,
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
        state["round_path"] = str(round_path)
        state["updated_at_utc"] = _now()
        _atomic_write(state_path, state)

        if result["status"] == "PASS":
            final = dict(round_result)
            final["_siraj_stage_summary"] = {
                "iterations_completed": total_iterations_completed,
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "cumulative_base_text_cost_usd": round(
                    cumulative_base_text_cost,
                    8,
                ),
                "assistant_authored_call_limit": None,
                "assistant_authored_cost_cap_usd": None,
                "assistant_authored_max_output_tokens": None,
                "assistant_authored_fixed_pacing_seconds": None,
                "automatic_retry": False,
            }
            _atomic_write(output_path, final)

            auth["status"] = "COMPLETED"
            auth["completed_iterations"] = total_iterations_completed
            auth["completed_at_utc"] = _now()
            _atomic_write(auth_path, auth)

            if runtime_marker.is_file():
                marker = _read_json(runtime_marker)
                marker["story_architecture_v5_status"] = "PASS"
                marker["next_stage"] = "FINAL_SCRIPT"
                marker["updated_at_utc"] = _now()
                _atomic_write(runtime_marker, marker)

            print("SIRAJ_LUNA_STORY_ARCHITECTURE_V5_COMPLETE")
            print("STATUS=PASS")
            print(
                "ITERATIONS_COMPLETED="
                + str(total_iterations_completed)
            )
            print(
                "ACTS="
                + str(len(result["acts"]))
            )
            print(
                "BEATS="
                + str(len(result["beats"]))
            )
            print(
                "TOTAL_INPUT_TOKENS="
                + str(total_input_tokens)
            )
            print(
                "TOTAL_OUTPUT_TOKENS="
                + str(total_output_tokens)
            )
            print(
                "CUMULATIVE_BASE_TEXT_COST_USD="
                + f"{cumulative_base_text_cost:.8f}"
            )
            print("ASSISTANT_AUTHORED_CALL_LIMIT=NONE")
            print("ASSISTANT_AUTHORED_COST_CAP_USD=NONE")
            print("ASSISTANT_AUTHORED_MAX_OUTPUT_TOKENS=NONE")
            print("ASSISTANT_AUTHORED_FIXED_PACING_SECONDS=NONE")
            print("AUTOMATIC_RETRIES=0")
            print(f"OUTPUT={output_path}")
            print("NEXT_STAGE=FINAL_SCRIPT")
            return

        if result["status"] == "NEEDS_CLAIM_MATRIX_REOPEN":
            if runtime_marker.is_file():
                marker = _read_json(runtime_marker)
                marker["story_architecture_v5_status"] = (
                    "NEEDS_CLAIM_MATRIX_REOPEN"
                )
                marker["next_stage"] = "SOURCE_CLAIM_MATRIX_REOPEN"
                marker["updated_at_utc"] = _now()
                _atomic_write(runtime_marker, marker)

            print("SIRAJ_LUNA_STORY_ARCHITECTURE_V5_STOPPED")
            print("STATUS=NEEDS_CLAIM_MATRIX_REOPEN")
            print(
                "ITERATIONS_COMPLETED="
                + str(total_iterations_completed)
            )
            print(f"LAST_ROUND={round_path}")
            print("AUTOMATIC_RETRIES=0")
            print("NEXT_STAGE=SOURCE_CLAIM_MATRIX_REOPEN")
            return

        # CONTINUE_ARCHITECTURE means Luna explicitly judged another editorial
        # pass necessary. This is a planned stage iteration, not a technical retry.
        previous_architecture = round_result
        iteration_no += 1
        print(
            "LUNA_STORY_ARCHITECTURE_CONTINUE:"
            f"NEXT_ITERATION={iteration_no}"
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
