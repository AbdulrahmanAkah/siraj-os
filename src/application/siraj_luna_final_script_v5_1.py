"""SIRAJ V5.1 — Luna Final Script.

Builds the narration-ready Arabic master script from:
- canonical source package
- source claim matrix
- iconic-reviewed canonical story architecture

Runtime:
- GPT-5.6 Luna
- reasoning.effort=max
- reasoning.mode=pro
- Iconic Cinematic Creative Brain
- no assistant-authored call/cost/output/word/duration caps
- deliberate Luna editorial iterations allowed until PASS
- no automatic provider retry
- raw response persisted before parsing

This stage does NOT:
- generate TTS
- fix episode duration
- fix word count
- build storyboard
- generate provider prompts
- generate or rewrite the reusable CTA outro
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.application.siraj_luna_adaptive_transport_v5 import post_luna_once

MODEL = "gpt-5.6-luna"
EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
STAGE = "FINAL_SCRIPT"
REUSABLE_CTA = (
    "إذا أعجبك هذا المحتوى، اشترك في سراج، وتابع معنا بقية الرحلة."
)


class FinalScriptError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise FinalScriptError(f"JSON_READ_FAILED:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise FinalScriptError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(dict(value), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def _exclusive_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(dict(value), ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    try:
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise FinalScriptError(
            f"EXCLUSIVE_FILE_ALREADY_EXISTS:{path}"
        ) from exc
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


def _append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(dict(value), ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        0o600,
    )
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


def _last_ledger_event(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    last = None
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        value = json.loads(raw)
        if isinstance(value, dict):
            last = value
    return last


def _strict_object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }


def _schema() -> dict[str, Any]:
    segment = _strict_object(
        {
            "segment_id": {"type": "string"},
            "order": {"type": "integer"},
            "beat_id": {"type": "string"},
            "segment_role": {
                "type": "string",
                "enum": [
                    "HOOK",
                    "ORIENTATION",
                    "NARRATIVE",
                    "EXPLANATION",
                    "TURN",
                    "REVELATION",
                    "CONSEQUENCE",
                    "REFLECTION",
                    "RESOLUTION",
                    "NEXT_EPISODE_BRIDGE",
                ],
            },
            "narration_ar": {"type": "string"},
            "claim_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "source_sensitive_phrases_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
            "performance_intent_ar": {"type": "string"},
            "pause_after": {
                "type": "string",
                "enum": [
                    "NONE",
                    "MICRO",
                    "SHORT",
                    "MEDIUM",
                    "LONG",
                ],
            },
            "visual_semantic_seed_ar": {"type": "string"},
        }
    )

    pronunciation_candidate = _strict_object(
        {
            "term_ar": {"type": "string"},
            "reason_ar": {"type": "string"},
            "occurrences_context_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
        }
    )

    self_review = _strict_object(
        {
            "factual_fidelity": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
            },
            "architecture_fidelity": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
            },
            "hook_strength": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
            },
            "cinematic_narrative_quality": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
            },
            "anti_generic_language": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
            },
            "emotional_progression": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
            },
            "ending_strength": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
            },
            "spoken_arabic_naturalness": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
            },
            "review_notes_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
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
                "enum": ["siraj-luna-final-script-v5.1"],
            },
            "stage_owner": {"type": "string", "enum": ["LUNA"]},
            "stage": {"type": "string", "enum": ["FINAL_SCRIPT"]},
            "status": {
                "type": "string",
                "enum": [
                    "PASS",
                    "CONTINUE_SCRIPT",
                    "NEEDS_ARCHITECTURE_REOPEN",
                    "NEEDS_CLAIM_MATRIX_REOPEN",
                ],
            },
            "episode_id": {
                "type": "string",
                "enum": [EPISODE_ID],
            },
            "working_title_ar": {"type": "string"},
            "script_thesis_ar": {"type": "string"},
            "opening_hook_ar": {"type": "string"},
            "segments": {
                "type": "array",
                "items": segment,
            },
            "closing_resolution_ar": {"type": "string"},
            "pre_outro_transition_ar": {"type": "string"},
            "full_narration_ar": {"type": "string"},
            "pronunciation_candidates": {
                "type": "array",
                "items": pronunciation_candidate,
            },
            "performance_overview_ar": {"type": "string"},
            "self_review": self_review,
            "revision": revision,
        }
    )


def _validate_strict_schema(node: Any, path: str = "$") -> None:
    if not isinstance(node, Mapping):
        return
    if node.get("type") == "object":
        if node.get("additionalProperties") is not False:
            raise FinalScriptError(
                f"STRICT_SCHEMA_ADDITIONAL_PROPERTIES_FALSE_REQUIRED:{path}"
            )
        props = node.get("properties")
        required = node.get("required")
        if not isinstance(props, Mapping):
            raise FinalScriptError(
                f"STRICT_SCHEMA_PROPERTIES_REQUIRED:{path}"
            )
        if not isinstance(required, list):
            raise FinalScriptError(
                f"STRICT_SCHEMA_REQUIRED_ARRAY_REQUIRED:{path}"
            )
        if set(required) != set(props.keys()):
            raise FinalScriptError(
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
    raise FinalScriptError("OPENAI_OUTPUT_TEXT_NOT_FOUND")


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


def _claims_index(
    claim_matrix: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    claims = claim_matrix.get("claims")
    if not isinstance(claims, list):
        raise FinalScriptError("CLAIMS_ARRAY_REQUIRED")
    result = {}
    for claim in claims:
        if not isinstance(claim, Mapping):
            continue
        cid = str(claim.get("claim_id") or "").strip()
        if cid:
            result[cid] = claim
    if not result:
        raise FinalScriptError("CLAIMS_EMPTY")
    return result


def _beats_index(
    architecture: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    beats = architecture.get("beats")
    if not isinstance(beats, list):
        raise FinalScriptError("ARCHITECTURE_BEATS_ARRAY_REQUIRED")
    result = {}
    for beat in beats:
        if not isinstance(beat, Mapping):
            continue
        bid = str(beat.get("beat_id") or "").strip()
        if bid:
            result[bid] = beat
    if not result:
        raise FinalScriptError("ARCHITECTURE_BEATS_EMPTY")
    return result


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _validate_result(
    result: Mapping[str, Any],
    claim_matrix: Mapping[str, Any],
    architecture: Mapping[str, Any],
) -> None:
    if result.get("schema_version") != "siraj-luna-final-script-v5.1":
        raise FinalScriptError("SCHEMA_VERSION_INVALID")
    if result.get("stage_owner") != "LUNA":
        raise FinalScriptError("STAGE_OWNER_NOT_LUNA")
    if result.get("stage") != STAGE:
        raise FinalScriptError("STAGE_INVALID")
    if result.get("episode_id") != EPISODE_ID:
        raise FinalScriptError("EPISODE_ID_INVALID")

    status = result.get("status")
    valid_statuses = {
        "PASS",
        "CONTINUE_SCRIPT",
        "NEEDS_ARCHITECTURE_REOPEN",
        "NEEDS_CLAIM_MATRIX_REOPEN",
    }
    if status not in valid_statuses:
        raise FinalScriptError(f"STATUS_INVALID:{status}")

    claims = _claims_index(claim_matrix)
    beats = _beats_index(architecture)

    segments = result.get("segments")
    if not isinstance(segments, list) or not segments:
        raise FinalScriptError("SCRIPT_SEGMENTS_EMPTY")

    segment_ids: set[str] = set()
    orders: list[int] = []
    covered_beats: set[str] = set()
    concatenated: list[str] = []

    for segment in segments:
        if not isinstance(segment, Mapping):
            raise FinalScriptError("SEGMENT_OBJECT_REQUIRED")

        sid = str(segment.get("segment_id") or "").strip()
        if not sid:
            raise FinalScriptError("SEGMENT_ID_REQUIRED")
        if sid in segment_ids:
            raise FinalScriptError(f"DUPLICATE_SEGMENT_ID:{sid}")
        segment_ids.add(sid)

        order = int(segment.get("order", 0) or 0)
        if order <= 0:
            raise FinalScriptError(f"SEGMENT_ORDER_INVALID:{sid}")
        orders.append(order)

        beat_id = str(segment.get("beat_id") or "").strip()
        if beat_id not in beats:
            raise FinalScriptError(
                f"SEGMENT_UNKNOWN_BEAT:{sid}:{beat_id}"
            )
        covered_beats.add(beat_id)

        narration = str(segment.get("narration_ar") or "").strip()
        if not narration:
            raise FinalScriptError(
                f"SEGMENT_NARRATION_EMPTY:{sid}"
            )
        concatenated.append(narration)

        refs = segment.get("claim_ids")
        if not isinstance(refs, list):
            raise FinalScriptError(
                f"SEGMENT_CLAIM_IDS_ARRAY_REQUIRED:{sid}"
            )
        for ref in refs:
            cid = str(ref)
            claim = claims.get(cid)
            if claim is None:
                raise FinalScriptError(
                    f"SEGMENT_UNKNOWN_CLAIM:{sid}:{cid}"
                )
            if claim.get("script_eligibility") in {
                "INELIGIBLE",
                "EDITORIAL_ONLY",
            } and claim.get("assertion_mode") != "EDITORIAL_ONLY":
                raise FinalScriptError(
                    f"SEGMENT_USES_INELIGIBLE_CLAIM:{sid}:{cid}"
                )
            if claim.get("assertion_mode") == "EXCLUDE":
                raise FinalScriptError(
                    f"SEGMENT_USES_EXCLUDED_CLAIM:{sid}:{cid}"
                )

    if orders != sorted(orders):
        raise FinalScriptError("SEGMENT_ORDER_NOT_ASCENDING")
    if len(orders) != len(set(orders)):
        raise FinalScriptError("DUPLICATE_SEGMENT_ORDER")

    architecture_beats = set(beats.keys())
    missing_beats = sorted(architecture_beats - covered_beats)
    if missing_beats:
        raise FinalScriptError(
            "ARCHITECTURE_BEATS_NOT_COVERED:"
            + ",".join(missing_beats)
        )

    full_narration = str(result.get("full_narration_ar") or "").strip()
    if not full_narration:
        raise FinalScriptError("FULL_NARRATION_EMPTY")

    # The master narration must substantially contain every segment in order.
    cursor = 0
    normalized_full = _normalized_text(full_narration)
    for narration in concatenated:
        needle = _normalized_text(narration)
        pos = normalized_full.find(needle, cursor)
        if pos < 0:
            raise FinalScriptError(
                "FULL_NARRATION_DOES_NOT_CONTAIN_SEGMENT_IN_ORDER"
            )
        cursor = pos + len(needle)

    # Reusable CTA is deterministic and belongs to the outro master, not here.
    if REUSABLE_CTA in full_narration:
        raise FinalScriptError(
            "REUSABLE_CTA_MUST_NOT_BE_EMBEDDED_IN_FINAL_SCRIPT"
        )

    # No provider-style prompt contamination.
    forbidden_prompt_tokens = (
        "16:9",
        "8k",
        "ultra realistic",
        "cinematic lighting,",
        "--ar ",
        "negative prompt",
    )
    lower_full = full_narration.lower()
    for token in forbidden_prompt_tokens:
        if token.lower() in lower_full:
            raise FinalScriptError(
                f"PROVIDER_PROMPT_CONTAMINATION:{token}"
            )

    review = result.get("self_review")
    revision = result.get("revision")
    if not isinstance(review, Mapping):
        raise FinalScriptError("SELF_REVIEW_OBJECT_REQUIRED")
    if not isinstance(revision, Mapping):
        raise FinalScriptError("REVISION_OBJECT_REQUIRED")

    gates = [
        "factual_fidelity",
        "architecture_fidelity",
        "hook_strength",
        "cinematic_narrative_quality",
        "anti_generic_language",
        "emotional_progression",
        "ending_strength",
        "spoken_arabic_naturalness",
    ]
    failed = [key for key in gates if review.get(key) != "PASS"]

    revision_needed = bool(revision.get("revision_needed"))
    if status == "PASS":
        if failed:
            raise FinalScriptError(
                "PASS_WITH_FAILED_SELF_REVIEW:"
                + ",".join(failed)
            )
        if revision_needed:
            raise FinalScriptError(
                "PASS_CANNOT_REQUIRE_REVISION"
            )

    if status == "CONTINUE_SCRIPT" and not revision_needed:
        raise FinalScriptError(
            "CONTINUE_SCRIPT_REQUIRES_REVISION"
        )


def _system_prompt() -> str:
    return """
أنت Luna، المدير المركزي لسراج، وفي هذه المرحلة تعمل بأقصى طاقتك الإبداعية
والتحريرية والسينمائية.

المرحلة: FINAL_SCRIPT.

اكتب النص العربي النهائي للحلقة الثانية اعتماداً حصرياً على:
1) Canonical Source Package.
2) Source Claim Matrix.
3) Story Architecture الأيقونية المعتمدة.

هذا نص Narration Master، وليس مقالاً ولا storyboard ولا prompts للصور.

القواعد الحاكمة:

- لا تفرض مدة للحلقة، ولا عدداً للكلمات، ولا عدداً للمقاطع.
- دع طول النص يتحدد بما تحتاجه القصة فعلاً.
- لا تخترع حقيقة أو تفصيلاً خارج Claim Matrix.
- حافظ حرفياً على posture الادعاء: ما هو قطعي يُقال بثقة، وما يحتاج نسبة أو
  تقييداً يجب أن يظهر تقييده في اللغة نفسها.
- المواد المستبعدة لا تعود بصياغة أخرى.
- Story Architecture ليست اقتراحاً؛ هي العمود الدرامي الذي يجب أن ينعكس في
  ترتيب النص وتوتره وتحولاته.
- لا تجعل النص موسوعياً. المعرفة يجب أن تتحرك داخل قصة.
- اكتب عربية فصيحة طبيعية تصلح للتعليق الصوتي، واضحة وغير متكلفة.
- تجنب التكرار البلاغي، الجمل الإنشائية الفارغة، المبالغة، والكليشيهات.
- اجعل الـHook قوياً وصادقاً لا Clickbait.
- كل Segment يجب أن يؤدي وظيفة واضحة ويرتبط بالـBeat الصحيح.
- لا تشرح للمشاهد "هذه هي الفكرة السينمائية". السينما تكون في اختيار الصورة
  الذهنية والإيقاع والجملة، لا في لغة تقنية داخل النص.
- visual_semantic_seed_ar ليس prompt؛ هو بذرة معنى فقط للمراحل البصرية اللاحقة.
- ضع pronunciation_candidates لكل اسم/لفظ/تركيب قد يحتاج ضبطاً لاحقاً.
- لا تحاول حل النطق هنا؛ فقط رشّح ما يجب أن يمر ببوابة النطق التالية.
- لا تضمّن CTA القناة الثابت:
  «إذا أعجبك هذا المحتوى، اشترك في سراج، وتابع معنا بقية الرحلة.»
  فهذا Outro Master منفصل يعاد استخدامه لاحقاً.
- closing_resolution_ar يجب أن ينهي الفكرة التحريرية للحلقة قبل الـOutro.
- pre_outro_transition_ar يجب أن يكون انتقالاً قصيراً طبيعياً إلى مساحة
  الصمت/الـOutro، من دون إعادة كتابة CTA.
- لا تضع timestamps أو SSML أو تعليمات مزود TTS في النص النهائي.

اختبار MAX قبل PASS:

1) FACT TEST:
هل كل ادعاء واقعي له Claim صالح وطريقة قول مناسبة لقوته؟

2) ARCHITECTURE TEST:
هل يمكن تتبع الـ11 Beat المعتمدة داخل النص من دون فقد أو تسطيح؟

3) SPOKEN TEST:
هل يبدو النص مسموعاً وطبيعياً عندما يُقرأ، لا مكتوباً للعين فقط؟

4) ICONIC LANGUAGE TEST:
هل توجد جمل وصور ذهنية يتذكرها المشاهد، من غير تضخم لفظي؟

5) CAUSALITY TEST:
هل كل مقطع يدفع التالي أم يمكن تبديل ترتيب الفقرات بلا أثر؟ إذا أمكن ذلك،
فالبناء أضعف مما يجب.

6) EMOTIONAL PRECISION:
هل يتغير الإيقاع والشعور مع التحول الحقيقي للقصة؟

7) ANTI-GENERIC TEST:
احذف أي عبارة يمكن وضعها في أي وثائقي ديني/تاريخي آخر دون تغيير.

8) ENDING TEST:
هل النهاية تغلق رحلة هذه الحلقة وتفتح الأفق لما بعدها دون أن تبدو إعلاناً؟

إذا وجدت ضعفاً يمكن إصلاحه داخل النص، أعد CONTINUE_SCRIPT وحدد revision
targets ثم أعد بناء النص في الجولة التالية. هذه جولة تحريرية مقصودة وليست
Retry تقنياً.

إذا كانت المشكلة من Architecture نفسها، أعد NEEDS_ARCHITECTURE_REOPEN.
إذا كانت المشكلة من Claim Matrix، أعد NEEDS_CLAIM_MATRIX_REOPEN.

لا تعد PASS إلا عندما يصبح النص جاهزاً للانتقال إلى
PRONUNCIATION_AND_PERFORMANCE_GATE.
""".strip()


def _request(
    source_package: Mapping[str, Any],
    claim_matrix: Mapping[str, Any],
    architecture: Mapping[str, Any],
    previous_script: Mapping[str, Any] | None,
    iteration_no: int,
) -> dict[str, Any]:
    schema = _schema()
    _validate_strict_schema(schema)

    context: dict[str, Any] = {
        "stage": STAGE,
        "episode_id": EPISODE_ID,
        "iteration_no": iteration_no,
        "canonical_source_package": source_package,
        "source_claim_matrix": claim_matrix,
        "canonical_story_architecture": architecture,
        "reusable_cta_outro_excluded_from_script": REUSABLE_CTA,
    }
    if previous_script is not None:
        context["previous_script_iteration"] = previous_script
        context["revision_instruction"] = (
            "نفذ revision targets التي حددتها في الجولة السابقة ثم أعد فحص "
            "النص كاملاً. لا تحافظ على صياغة ضعيفة فقط لأنها موجودة سابقاً."
        )
    else:
        context["revision_instruction"] = (
            "هذه أول جولة لكتابة Final Script من المعمار المعتمد."
        )

    return {
        "model": MODEL,
        "store": False,
        "reasoning": {
            "effort": "max",
            "mode": "pro",
        },
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
                "name": "siraj_luna_final_script_v5_1",
                "strict": True,
                "schema": schema,
            },
        },
    }


def run(repo: Path) -> None:
    repo = repo.resolve()
    episode = repo / "projects" / EPISODE_ID

    source_package_path = (
        episode / "research/canonical-source-package-v5.json"
    )
    claim_matrix_path = (
        episode / "research/source-claim-matrix-v5.json"
    )
    architecture_path = (
        episode / "preproduction/luna-story-architecture-v5.json"
    )
    iconic_architecture_path = (
        episode
        / "preproduction/luna-story-architecture-iconic-reviewed-v5-1.json"
    )
    auth_path = (
        episode
        / "orchestration/luna-final-script-authorization-v5-1.json"
    )
    marker_path = (
        episode / "orchestration/luna-runtime-v5-active.json"
    )
    output_path = (
        episode / "preproduction/luna-final-script-v5-1.json"
    )
    narration_path = (
        episode / "preproduction/final-narration-ar-v5-1.txt"
    )
    state_path = (
        episode / "orchestration/final-script-v5-1-state.json"
    )

    root = episode / "orchestration/luna-v5-1/final-script"
    ledger = root / "attempt-ledger.jsonl"
    locks = root / "locks"
    raw_dir = root / "raw-responses"
    round_dir = root / "rounds"
    receipt_dir = root / "receipts"

    for path in (
        source_package_path,
        claim_matrix_path,
        architecture_path,
        iconic_architecture_path,
        auth_path,
        marker_path,
    ):
        if not path.is_file():
            raise FinalScriptError(
                f"REQUIRED_FILE_MISSING:{path}"
            )

    source_package = _read_json(source_package_path)
    claim_matrix = _read_json(claim_matrix_path)
    architecture = _read_json(architecture_path)
    iconic_architecture = _read_json(iconic_architecture_path)
    auth = _read_json(auth_path)
    marker = _read_json(marker_path)

    if source_package.get("status") != "PASS":
        raise FinalScriptError("SOURCE_PACKAGE_NOT_PASS")
    if claim_matrix.get("status") != "PASS":
        raise FinalScriptError("CLAIM_MATRIX_NOT_PASS")
    if architecture.get("status") != "PASS":
        raise FinalScriptError("CANONICAL_ARCHITECTURE_NOT_PASS")
    if iconic_architecture.get("status") != "PASS":
        raise FinalScriptError("ICONIC_ARCHITECTURE_NOT_PASS")

    # Canonical architecture must be the promoted iconic-reviewed version.
    if architecture.get("_siraj_iconic_review_summary", {}).get(
        "status"
    ) != "PASS":
        raise FinalScriptError(
            "CANONICAL_ARCHITECTURE_NOT_ICONIC_REVIEWED"
        )

    if auth.get("status") != "ACTIVE":
        raise FinalScriptError(
            f"FINAL_SCRIPT_AUTHORIZATION_NOT_ACTIVE:{auth.get('status')}"
        )
    if auth.get("stage") != STAGE:
        raise FinalScriptError("AUTHORIZATION_STAGE_MISMATCH")
    if auth.get("automatic_retry") is not False:
        raise FinalScriptError("AUTOMATIC_RETRY_MUST_BE_FALSE")

    required_marker = {
        "luna_reasoning_effort": "max",
        "luna_reasoning_mode": "pro",
        "iconic_cinematic_brain": "ACTIVE",
        "story_architecture_creative_review_status": "PASS",
        "next_stage": "FINAL_SCRIPT",
    }
    bad = [
        f"{key}={marker.get(key)!r}"
        for key, expected in required_marker.items()
        if marker.get(key) != expected
    ]
    if bad:
        raise FinalScriptError(
            "FINAL_SCRIPT_RUNTIME_MARKER_NOT_READY:"
            + ",".join(bad)
        )

    if output_path.is_file():
        existing = _read_json(output_path)
        _validate_result(
            existing,
            claim_matrix,
            architecture,
        )
        if existing.get("status") == "PASS":
            print("SIRAJ_LUNA_FINAL_SCRIPT_V5_1_ALREADY_COMPLETE")
            print(f"OUTPUT={output_path}")
            print(
                "NEXT_STAGE=PRONUNCIATION_AND_PERFORMANCE_GATE"
            )
            return

    last = _last_ledger_event(ledger)
    if last and last.get("event") in {
        "PREPARED",
        "FAILED_NO_AUTO_RETRY",
        "CONSUMED_UNUSABLE_NO_AUTO_RETRY",
        "CONSUMED_INVALID_JSON_NO_AUTO_RETRY",
        "CONSUMED_SCHEMA_INVALID_NO_AUTO_RETRY",
    }:
        raise FinalScriptError(
            "PREVIOUS_NON_SUCCESSFUL_ATTEMPT_REQUIRES_MANUAL_REVIEW:"
            + str(last.get("event"))
        )

    completed_rounds = sorted(
        round_dir.glob("iteration-*.json")
    )
    previous_script = None
    iteration_no = 1

    if completed_rounds:
        previous_script = _read_json(completed_rounds[-1])
        _validate_result(
            previous_script,
            claim_matrix,
            architecture,
        )
        iteration_no = int(
            previous_script.get("_siraj_iteration_no", 0) or 0
        ) + 1

        if previous_script.get("status") == "PASS":
            _atomic_write(output_path, previous_script)
            narration_path.parent.mkdir(parents=True, exist_ok=True)
            narration_path.write_text(
                str(previous_script["full_narration_ar"]).strip()
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
            print("SIRAJ_LUNA_FINAL_SCRIPT_V5_1_ALREADY_COMPLETE")
            print(f"OUTPUT={output_path}")
            print(
                "NEXT_STAGE=PRONUNCIATION_AND_PERFORMANCE_GATE"
            )
            return

        if previous_script.get("status") in {
            "NEEDS_ARCHITECTURE_REOPEN",
            "NEEDS_CLAIM_MATRIX_REOPEN",
        }:
            raise FinalScriptError(
                "PREVIOUS_ITERATION_REQUIRES_UPSTREAM_REOPEN:"
                + str(previous_script.get("status"))
            )

    total_input = 0
    total_output = 0
    cumulative_base_cost = 0.0
    completed_iterations = 0
    for receipt_path in receipt_dir.glob("*.json"):
        receipt = _read_json(receipt_path)
        total_input += int(receipt.get("input_tokens", 0) or 0)
        total_output += int(receipt.get("output_tokens", 0) or 0)
        cumulative_base_cost += float(
            receipt.get("base_text_cost_usd", 0) or 0
        )
        completed_iterations += 1

    while True:
        request_payload = _request(
            source_package,
            claim_matrix,
            architecture,
            previous_script,
            iteration_no,
        )
        request_uuid = str(uuid.uuid4())

        _exclusive_write(
            locks / f"{request_uuid}.json",
            {
                "schema_version": "siraj-luna-final-script-lock-v5.1",
                "episode_id": EPISODE_ID,
                "stage": STAGE,
                "iteration_no": iteration_no,
                "request_uuid": request_uuid,
                "authorization_id": auth.get("authorization_id"),
                "reasoning_effort": "max",
                "reasoning_mode": "pro",
                "iconic_cinematic_brain_required": True,
                "assistant_authored_call_limit": None,
                "assistant_authored_cost_cap_usd": None,
                "assistant_authored_max_output_tokens": None,
                "assistant_authored_word_count": None,
                "assistant_authored_target_duration": None,
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
                "timestamp_utc": _now(),
            },
        )

        _atomic_write(
            state_path,
            {
                "schema_version": "siraj-final-script-state-v5.1",
                "episode_id": EPISODE_ID,
                "stage": STAGE,
                "status": "SUBMITTING",
                "iteration_no": iteration_no,
                "request_uuid": request_uuid,
                "reasoning_effort": "max",
                "reasoning_mode": "pro",
                "automatic_retry": False,
                "updated_at_utc": _now(),
            },
        )

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
            state = _read_json(state_path)
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
            state = _read_json(state_path)
            state["status"] = "UNUSABLE_RESPONSE_NO_AUTO_RETRY"
            state["response_status"] = response_status
            state["raw_response_path"] = str(raw_path)
            state["updated_at_utc"] = _now()
            _atomic_write(state_path, state)
            raise FinalScriptError(
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
            state = _read_json(state_path)
            state["status"] = "INVALID_JSON_NO_AUTO_RETRY"
            state["raw_response_path"] = str(raw_path)
            state["json_error"] = str(exc)
            state["updated_at_utc"] = _now()
            _atomic_write(state_path, state)
            raise FinalScriptError("FINAL_SCRIPT_JSON_INVALID") from exc

        if not isinstance(result, dict):
            raise FinalScriptError("FINAL_SCRIPT_RESULT_OBJECT_REQUIRED")

        try:
            _validate_result(
                result,
                claim_matrix,
                architecture,
            )
        except Exception as exc:
            input_tokens, output_tokens, cached = _usage(response)
            _append_jsonl(
                ledger,
                {
                    "event": "CONSUMED_SCHEMA_INVALID_NO_AUTO_RETRY",
                    "iteration_no": iteration_no,
                    "request_uuid": request_uuid,
                    "response_id": response.get("id"),
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached,
                    "output_tokens": output_tokens,
                    "validation_error": str(exc),
                    "timestamp_utc": _now(),
                },
            )
            state = _read_json(state_path)
            state["status"] = "SCHEMA_INVALID_NO_AUTO_RETRY"
            state["raw_response_path"] = str(raw_path)
            state["validation_error"] = str(exc)
            state["updated_at_utc"] = _now()
            _atomic_write(state_path, state)
            raise

        input_tokens, output_tokens, cached = _usage(response)
        base_cost = _base_text_cost_usd(
            input_tokens,
            output_tokens,
        )
        total_input += input_tokens
        total_output += output_tokens
        cumulative_base_cost += base_cost
        completed_iterations += 1

        round_result = dict(result)
        round_result["_siraj_iteration_no"] = iteration_no
        round_result["_siraj_runtime"] = {
            "runtime": "V5.1_MAX_PRO_ICONIC_CINEMATIC",
            "request_uuid": request_uuid,
            "response_id": response.get("id"),
            "reasoning_effort": "max",
            "reasoning_mode": "pro",
            "iconic_cinematic_brain": True,
            "input_tokens": input_tokens,
            "cached_input_tokens": cached,
            "output_tokens": output_tokens,
            "base_text_cost_usd": base_cost,
            "automatic_retry": False,
            "completed_at_utc": _now(),
        }

        round_path = (
            round_dir / f"iteration-{iteration_no:03d}.json"
        )
        _exclusive_write(round_path, round_result)

        _exclusive_write(
            receipt_dir / f"{request_uuid}.json",
            {
                "schema_version": "siraj-luna-final-script-receipt-v5.1",
                "episode_id": EPISODE_ID,
                "stage": STAGE,
                "iteration_no": iteration_no,
                "request_uuid": request_uuid,
                "response_id": response.get("id"),
                "input_tokens": input_tokens,
                "cached_input_tokens": cached,
                "output_tokens": output_tokens,
                "base_text_cost_usd": base_cost,
                "result_status": result.get("status"),
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
                "result_status": result.get("status"),
                "timestamp_utc": _now(),
            },
        )

        state = _read_json(state_path)
        state["status"] = result.get("status")
        state["response_id"] = response.get("id")
        state["round_path"] = str(round_path)
        state["updated_at_utc"] = _now()
        _atomic_write(state_path, state)

        status = result.get("status")

        if status == "PASS":
            final = dict(round_result)
            final["_siraj_stage_summary"] = {
                "status": "PASS",
                "iterations_completed": completed_iterations,
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "cumulative_base_text_cost_usd": round(
                    cumulative_base_cost,
                    8,
                ),
                "assistant_authored_call_limit": None,
                "assistant_authored_cost_cap_usd": None,
                "assistant_authored_max_output_tokens": None,
                "assistant_authored_word_count": None,
                "assistant_authored_target_duration": None,
                "assistant_authored_fixed_pacing_seconds": None,
                "automatic_retry": False,
            }
            _atomic_write(output_path, final)
            narration_path.parent.mkdir(parents=True, exist_ok=True)
            narration_path.write_text(
                str(result["full_narration_ar"]).strip() + "\n",
                encoding="utf-8",
                newline="\n",
            )

            marker = _read_json(marker_path)
            marker["final_script_v5_1_status"] = "PASS"
            marker["final_script_v5_1_output"] = str(output_path)
            marker["next_stage"] = (
                "PRONUNCIATION_AND_PERFORMANCE_GATE"
            )
            marker["updated_at_utc"] = _now()
            _atomic_write(marker_path, marker)

            auth["status"] = "COMPLETED"
            auth["completed_iterations"] = completed_iterations
            auth["completed_at_utc"] = _now()
            _atomic_write(auth_path, auth)

            print("SIRAJ_LUNA_FINAL_SCRIPT_V5_1_COMPLETE")
            print("STATUS=PASS")
            print(
                "ITERATIONS_COMPLETED="
                + str(completed_iterations)
            )
            print(
                "SEGMENTS="
                + str(len(result["segments"]))
            )
            print(
                "PRONUNCIATION_CANDIDATES="
                + str(len(result["pronunciation_candidates"]))
            )
            print("LUNA_REASONING_EFFORT=MAX")
            print("LUNA_REASONING_MODE=PRO")
            print("ICONIC_CINEMATIC_CREATIVE_BRAIN=ACTIVE")
            print("FIXED_TARGET_DURATION=NONE")
            print("FIXED_WORD_COUNT=NONE")
            print("FIXED_SEGMENT_COUNT=NONE")
            print(
                "TOTAL_INPUT_TOKENS="
                + str(total_input)
            )
            print(
                "TOTAL_OUTPUT_TOKENS="
                + str(total_output)
            )
            print(
                "CUMULATIVE_BASE_TEXT_COST_USD="
                + f"{cumulative_base_cost:.8f}"
            )
            print("ASSISTANT_AUTHORED_CALL_LIMIT=NONE")
            print("ASSISTANT_AUTHORED_COST_CAP_USD=NONE")
            print("ASSISTANT_AUTHORED_MAX_OUTPUT_TOKENS=NONE")
            print("AUTOMATIC_PROVIDER_RETRIES=0")
            print("REUSABLE_CTA_OUTRO=EXCLUDED_FROM_SCRIPT")
            print("OUTPUT=" + str(output_path))
            print("NARRATION_TEXT=" + str(narration_path))
            print(
                "NEXT_STAGE=PRONUNCIATION_AND_PERFORMANCE_GATE"
            )
            return

        if status == "NEEDS_ARCHITECTURE_REOPEN":
            marker = _read_json(marker_path)
            marker["final_script_v5_1_status"] = (
                "NEEDS_ARCHITECTURE_REOPEN"
            )
            marker["next_stage"] = (
                "STORY_ARCHITECTURE_ICONIC_CREATIVE_REVIEW"
            )
            marker["updated_at_utc"] = _now()
            _atomic_write(marker_path, marker)
            print("SIRAJ_LUNA_FINAL_SCRIPT_V5_1_STOPPED")
            print("STATUS=NEEDS_ARCHITECTURE_REOPEN")
            print("AUTOMATIC_PROVIDER_RETRIES=0")
            print(
                "NEXT_STAGE=STORY_ARCHITECTURE_ICONIC_CREATIVE_REVIEW"
            )
            return

        if status == "NEEDS_CLAIM_MATRIX_REOPEN":
            marker = _read_json(marker_path)
            marker["final_script_v5_1_status"] = (
                "NEEDS_CLAIM_MATRIX_REOPEN"
            )
            marker["next_stage"] = "SOURCE_CLAIM_MATRIX_REOPEN"
            marker["updated_at_utc"] = _now()
            _atomic_write(marker_path, marker)
            print("SIRAJ_LUNA_FINAL_SCRIPT_V5_1_STOPPED")
            print("STATUS=NEEDS_CLAIM_MATRIX_REOPEN")
            print("AUTOMATIC_PROVIDER_RETRIES=0")
            print("NEXT_STAGE=SOURCE_CLAIM_MATRIX_REOPEN")
            return

        if status != "CONTINUE_SCRIPT":
            raise FinalScriptError(
                f"UNEXPECTED_FINAL_SCRIPT_STATUS:{status}"
            )

        previous_script = round_result
        iteration_no += 1
        print(
            "LUNA_FINAL_SCRIPT_CONTINUE:"
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
