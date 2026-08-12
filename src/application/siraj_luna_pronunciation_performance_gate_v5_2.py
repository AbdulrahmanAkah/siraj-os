"""SIRAJ V5.2 — Pronunciation & Performance Gate.

Luna reviews the approved Final Script for:
- Arabic pronunciation risk
- selective diacritics / orthographic disambiguation
- pauses and delivery
- performance continuity
- TTS readiness

The gate may NOT rewrite factual/script content. If content needs rewriting,
it must return NEEDS_FINAL_SCRIPT_REOPEN.

No TTS provider call is made here.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.application.siraj_luna_adaptive_transport_v5 import post_luna_once
from src.application.siraj_global_arabic_pronunciation_law_v5_3 import (
    assert_no_bare_arabic_words,
    assert_pronunciation_layer_preserves_lexical_content,
)

MODEL = "gpt-5.6-luna"
EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
STAGE = "PRONUNCIATION_AND_PERFORMANCE_GATE"
NEXT_STAGE = "FINAL_TTS"
HOOK_MIN_PAUSE_SECONDS = 0.6
PRE_OUTRO_MIN_PAUSE_SECONDS = 0.4
REUSABLE_CTA = (
    "إذا أعجبك هذا المحتوى، اشترك في سراج، وتابع معنا بقية الرحلة."
)


class PronunciationGateError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise PronunciationGateError(
            f"JSON_READ_FAILED:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise PronunciationGateError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(dict(value), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def _exclusive_json(path: Path, value: Mapping[str, Any]) -> None:
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
        raise PronunciationGateError(
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
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


def _last_ledger_event(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    last = None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        value = json.loads(line)
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
    pronunciation_decision = _strict_object(
        {
            "candidate_term_ar": {"type": "string"},
            "decision": {
                "type": "string",
                "enum": [
                    "DIACRITIZE_IN_CONTEXT",
                    "KEEP_AS_WRITTEN",
                    "ORTHOGRAPHIC_DISAMBIGUATION",
                    "PERFORMANCE_ONLY",
                ],
            },
            "preferred_spoken_form_ar": {"type": "string"},
            "reason_ar": {"type": "string"},
            "contexts_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
        }
    )

    segment = _strict_object(
        {
            "segment_id": {"type": "string"},
            "order": {"type": "integer"},
            "beat_id": {"type": "string"},
            "source_narration_ar": {"type": "string"},
            "tts_text_ar": {"type": "string"},
            "delivery_mode": {
                "type": "string",
                "enum": [
                    "INTIMATE",
                    "NEUTRAL",
                    "REFLECTIVE",
                    "TENSE",
                    "AWE",
                    "GRAVE",
                    "REGRETFUL",
                    "HOPEFUL",
                    "RESOLUTE",
                ],
            },
            "pace": {
                "type": "string",
                "enum": [
                    "VERY_SLOW",
                    "SLOW",
                    "MEASURED",
                    "NATURAL",
                    "BRISK",
                ],
            },
            "intensity": {
                "type": "string",
                "enum": ["LOW", "MEDIUM", "HIGH"],
            },
            "pause_before_seconds": {"type": "number"},
            "pause_after_seconds": {"type": "number"},
            "emphasis_notes_ar": {
                "type": "array",
                "items": {"type": "string"},
            },
            "performance_direction_ar": {"type": "string"},
        }
    )

    pre_outro = _strict_object(
        {
            "source_text_ar": {"type": "string"},
            "tts_text_ar": {"type": "string"},
            "delivery_mode": {
                "type": "string",
                "enum": [
                    "INTIMATE",
                    "NEUTRAL",
                    "REFLECTIVE",
                    "GRAVE",
                    "HOPEFUL",
                    "RESOLUTE",
                ],
            },
            "pace": {
                "type": "string",
                "enum": ["VERY_SLOW", "SLOW", "MEASURED", "NATURAL"],
            },
            "pause_before_seconds": {"type": "number"},
            "pause_after_seconds": {"type": "number"},
            "performance_direction_ar": {"type": "string"},
        }
    )

    review = _strict_object(
        {
            "pronunciation_accuracy": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
            },
            "lexical_fidelity": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
            },
            "natural_spoken_arabic": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
            },
            "performance_arc": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
            },
            "hook_delivery": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
            },
            "pre_outro_delivery": {
                "type": "string",
                "enum": ["PASS", "FAIL"],
            },
            "tts_readiness": {
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
                "enum": ["siraj-luna-pronunciation-performance-gate-v5.2"],
            },
            "stage_owner": {"type": "string", "enum": ["LUNA"]},
            "stage": {
                "type": "string",
                "enum": [STAGE],
            },
            "status": {
                "type": "string",
                "enum": [
                    "PASS",
                    "CONTINUE_GATE",
                    "NEEDS_FINAL_SCRIPT_REOPEN",
                ],
            },
            "episode_id": {
                "type": "string",
                "enum": [EPISODE_ID],
            },
            "voice_profile_ar": {"type": "string"},
            "performance_arc_ar": {"type": "string"},
            "pronunciation_decisions": {
                "type": "array",
                "items": pronunciation_decision,
            },
            "segments": {
                "type": "array",
                "items": segment,
            },
            "pre_outro_transition": pre_outro,
            "self_review": review,
            "revision": revision,
        }
    )


def _validate_strict_schema(node: Any, path: str = "$") -> None:
    if not isinstance(node, Mapping):
        return
    if node.get("type") == "object":
        if node.get("additionalProperties") is not False:
            raise PronunciationGateError(
                f"STRICT_SCHEMA_ADDITIONAL_PROPERTIES_FALSE_REQUIRED:{path}"
            )
        props = node.get("properties")
        required = node.get("required")
        if not isinstance(props, Mapping):
            raise PronunciationGateError(
                f"STRICT_SCHEMA_PROPERTIES_REQUIRED:{path}"
            )
        if not isinstance(required, list) or set(required) != set(props.keys()):
            raise PronunciationGateError(
                f"STRICT_SCHEMA_ALL_PROPERTIES_REQUIRED:{path}"
            )
        for name, child in props.items():
            _validate_strict_schema(child, f"{path}.properties.{name}")
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
                if isinstance(block, Mapping) and block.get("type") == "output_text":
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
    if parts:
        return "".join(parts)
    direct = response.get("output_text")
    if isinstance(direct, str):
        return direct
    raise PronunciationGateError("OPENAI_OUTPUT_TEXT_NOT_FOUND")


def _usage(response: Mapping[str, Any]) -> tuple[int, int, int]:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return 0, 0, 0
    inp = int(usage.get("input_tokens", 0) or 0)
    out = int(usage.get("output_tokens", 0) or 0)
    details = usage.get("input_tokens_details")
    cached = 0
    if isinstance(details, Mapping):
        cached = int(details.get("cached_tokens", 0) or 0)
    return inp, out, cached


def _base_text_cost_usd(inp: int, out: int) -> float:
    return round(inp / 1_000_000 * 0.20 + out / 1_000_000 * 1.20, 8)


_ARABIC_DIACRITICS = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]"
)
_NON_LEXICAL = re.compile(
    r"[\s\.,،؛;:!؟\?…ـ\"'“”‘’()\[\]{}<>«»\-—–_/\\|]+"
)


_ARABIC_BASE_CHAR_CLASS = (
    "\u0621-\u064A\u0671\u067E\u0686\u06A4\u06AF\u06CC"
)


def _normalize_madda_for_lexical_comparison(text: str) -> str:
    value = re.sub(
        rf"(?<![{_ARABIC_BASE_CHAR_CLASS}])آ",
        "ا",
        str(text or ""),
    )
    return value.replace("آ", "ءا")


def _lexical_skeleton(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text or ""))
    text = _ARABIC_DIACRITICS.sub("", text)
    text = _normalize_madda_for_lexical_comparison(text)
    text = (
        text.replace("أ", "ا")
        .replace("إ", "ا")
                .replace("ٱ", "ا")
        .replace("ى", "ي")
    )
    return _NON_LEXICAL.sub("", text)


def _source_segments(script: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    segments = script.get("segments")
    if not isinstance(segments, list) or not segments:
        raise PronunciationGateError("FINAL_SCRIPT_SEGMENTS_EMPTY")
    result = {}
    for seg in segments:
        if not isinstance(seg, Mapping):
            continue
        sid = str(seg.get("segment_id") or "").strip()
        if sid:
            result[sid] = seg
    if not result:
        raise PronunciationGateError("FINAL_SCRIPT_SEGMENT_IDS_EMPTY")
    return result


def _candidate_terms(script: Mapping[str, Any]) -> set[str]:
    items = script.get("pronunciation_candidates")
    if not isinstance(items, list):
        raise PronunciationGateError(
            "FINAL_SCRIPT_PRONUNCIATION_CANDIDATES_ARRAY_REQUIRED"
        )
    return {
        str(x.get("term_ar") or "").strip()
        for x in items
        if isinstance(x, Mapping) and str(x.get("term_ar") or "").strip()
    }



# SIRAJ_V5_3_CONTEXT_SCOPED_PRONUNCIATION_ALIAS
def _v53_alias_collapse(source_text: str, tts_text: str) -> str:
    candidate = str(tts_text or "")
    if "سورة طه" in str(source_text or "") and "طَا هَا" in candidate:
        candidate = candidate.replace("طَا هَا", "طه")
    return candidate


def _v53_assert_no_tts_markup(text: str, label: str) -> None:
    if re.search(
        r"(?m)^\s{0,3}#{1,6}\s+|```|`|\*\*|__",
        str(text or ""),
    ):
        raise PronunciationGateError(
            "TTS_MARKDOWN_OR_CONTROL_MARKUP_FORBIDDEN:" + label
        )


def _validate_result(
    result: Mapping[str, Any],
    script: Mapping[str, Any],
) -> None:
    if result.get("schema_version") != (
        "siraj-luna-pronunciation-performance-gate-v5.2"
    ):
        raise PronunciationGateError("SCHEMA_VERSION_INVALID")
    if result.get("stage_owner") != "LUNA":
        raise PronunciationGateError("STAGE_OWNER_NOT_LUNA")
    if result.get("stage") != STAGE:
        raise PronunciationGateError("STAGE_INVALID")
    if result.get("episode_id") != EPISODE_ID:
        raise PronunciationGateError("EPISODE_ID_INVALID")

    status = result.get("status")
    if status not in {
        "PASS",
        "CONTINUE_GATE",
        "NEEDS_FINAL_SCRIPT_REOPEN",
    }:
        raise PronunciationGateError(f"STATUS_INVALID:{status}")

    source = _source_segments(script)
    output_segments = result.get("segments")
    if not isinstance(output_segments, list) or not output_segments:
        raise PronunciationGateError("GATE_SEGMENTS_EMPTY")

    seen: set[str] = set()
    orders: list[int] = []
    hook_pause_ok = False

    for seg in output_segments:
        if not isinstance(seg, Mapping):
            raise PronunciationGateError("GATE_SEGMENT_OBJECT_REQUIRED")
        sid = str(seg.get("segment_id") or "").strip()
        if sid not in source:
            raise PronunciationGateError(f"UNKNOWN_SEGMENT_ID:{sid}")
        if sid in seen:
            raise PronunciationGateError(f"DUPLICATE_SEGMENT_ID:{sid}")
        seen.add(sid)

        src = source[sid]
        if str(seg.get("beat_id") or "") != str(src.get("beat_id") or ""):
            raise PronunciationGateError(f"BEAT_ID_CHANGED:{sid}")
        if int(seg.get("order", 0) or 0) != int(src.get("order", 0) or 0):
            raise PronunciationGateError(f"SEGMENT_ORDER_CHANGED:{sid}")
        orders.append(int(seg.get("order", 0) or 0))

        source_text = str(src.get("narration_ar") or "").strip()
        declared_source = str(seg.get("source_narration_ar") or "").strip()
        tts_text = str(seg.get("tts_text_ar") or "").strip()

        if declared_source != source_text:
            raise PronunciationGateError(f"SOURCE_TEXT_MUTATED:{sid}")
        lexical_tts_text = _v53_alias_collapse(source_text, tts_text)
        if _lexical_skeleton(lexical_tts_text) != _lexical_skeleton(source_text):
            raise PronunciationGateError(
                f"TTS_TEXT_LEXICAL_CONTENT_CHANGED:{sid}"
            )
        _v53_assert_no_tts_markup(tts_text, sid)

        assert_pronunciation_layer_preserves_lexical_content(
            source_text, tts_text, sid
        )
        assert_no_bare_arabic_words(tts_text, sid)

        pb = float(seg.get("pause_before_seconds", 0) or 0)
        pa = float(seg.get("pause_after_seconds", 0) or 0)
        if pb < 0 or pa < 0:
            raise PronunciationGateError(f"NEGATIVE_PAUSE:{sid}")

        if src.get("segment_role") == "HOOK":
            if pa >= HOOK_MIN_PAUSE_SECONDS:
                hook_pause_ok = True

    if seen != set(source.keys()):
        missing = sorted(set(source.keys()) - seen)
        raise PronunciationGateError(
            "FINAL_SCRIPT_SEGMENTS_NOT_FULLY_COVERED:" + ",".join(missing)
        )
    if orders != sorted(orders) or len(orders) != len(set(orders)):
        raise PronunciationGateError("SEGMENT_ORDER_INVALID")
    if not hook_pause_ok:
        raise PronunciationGateError(
            f"HOOK_PAUSE_TOO_SHORT_MIN_{HOOK_MIN_PAUSE_SECONDS}"
        )

    source_transition = str(
        script.get("pre_outro_transition_ar") or ""
    ).strip()
    transition = result.get("pre_outro_transition")
    if not isinstance(transition, Mapping):
        raise PronunciationGateError("PRE_OUTRO_OBJECT_REQUIRED")
    if str(transition.get("source_text_ar") or "").strip() != source_transition:
        raise PronunciationGateError("PRE_OUTRO_SOURCE_TEXT_MUTATED")
    if _lexical_skeleton(
        str(transition.get("tts_text_ar") or "")
    ) != _lexical_skeleton(source_transition):
        raise PronunciationGateError("PRE_OUTRO_LEXICAL_CONTENT_CHANGED")

    assert_pronunciation_layer_preserves_lexical_content(
        source_transition,
        str(transition.get("tts_text_ar") or ""),
        "PRE_OUTRO",
    )
    assert_no_bare_arabic_words(
        str(transition.get("tts_text_ar") or ""),
        "PRE_OUTRO",
    )
    if float(transition.get("pause_after_seconds", 0) or 0) < (
        PRE_OUTRO_MIN_PAUSE_SECONDS
    ):
        raise PronunciationGateError(
            f"PRE_OUTRO_PAUSE_TOO_SHORT_MIN_{PRE_OUTRO_MIN_PAUSE_SECONDS}"
        )

    required_candidates = _candidate_terms(script)
    decisions = result.get("pronunciation_decisions")
    if not isinstance(decisions, list):
        raise PronunciationGateError("PRONUNCIATION_DECISIONS_ARRAY_REQUIRED")
    covered = {
        str(item.get("candidate_term_ar") or "").strip()
        for item in decisions
        if isinstance(item, Mapping)
    }
    missing_candidates = sorted(required_candidates - covered)
    if missing_candidates:
        raise PronunciationGateError(
            "PRONUNCIATION_CANDIDATES_NOT_REVIEWED:"
            + "|".join(missing_candidates)
        )

    # CTA must remain a separate reusable master.
    all_tts = " ".join(
        str(seg.get("tts_text_ar") or "") for seg in output_segments
    ) + " " + str(transition.get("tts_text_ar") or "")
    if REUSABLE_CTA in all_tts:
        raise PronunciationGateError("REUSABLE_CTA_EMBEDDED_IN_GATE_OUTPUT")

    review = result.get("self_review")
    revision = result.get("revision")
    if not isinstance(review, Mapping) or not isinstance(revision, Mapping):
        raise PronunciationGateError("REVIEW_OR_REVISION_OBJECT_REQUIRED")

    gates = [
        "pronunciation_accuracy",
        "lexical_fidelity",
        "natural_spoken_arabic",
        "performance_arc",
        "hook_delivery",
        "pre_outro_delivery",
        "tts_readiness",
    ]
    failed = [g for g in gates if review.get(g) != "PASS"]
    revision_needed = bool(revision.get("revision_needed"))

    if status == "PASS":
        if failed:
            raise PronunciationGateError(
                "PASS_WITH_FAILED_GATES:" + ",".join(failed)
            )
        if revision_needed:
            raise PronunciationGateError("PASS_CANNOT_REQUIRE_REVISION")
    if status == "CONTINUE_GATE" and not revision_needed:
        raise PronunciationGateError(
            "CONTINUE_GATE_REQUIRES_REVISION"
        )


def _system_prompt() -> str:
    return f"""
أنت Luna في مرحلة {STAGE}. هذه بوابة جودة قبل أي TTS.

المصدر المعتمد هو Final Script. لا تعيد كتابة الحلقة ولا تحسن الحقائق هنا.
إذا وجدت مشكلة نصية تتطلب حذفاً أو إضافة أو إعادة صياغة، أعد
NEEDS_FINAL_SCRIPT_REOPEN بدلاً من إصلاحها داخل هذه البوابة.

مهمتك:
- افحص كل كلمة يمكن أن يخطئ TTS العربي في نطقها.
- راجع كل pronunciation candidate في Final Script، ولا تهمل أياً منها.
- التشكيل النطقي الكامل إلزامي في كل tts_text_ar. لا تترك أي كلمة عربية متعددة الحروف عارية من التشكيل في النص الذي سيدخل TTS.
- استخدم الحركات والشدة والسكون بما يخدم النطق الفعلي، مع مراعاة الوقف حتى لا تُجبر القارئ الآلي على نهاية مصطنعة.
- هذه البوابة لا تملك حق إعادة كتابة النص: يسمح بالتشكيل والترقيم والتمييز الإملائي الآمن فقط، مع بقاء المحتوى الملفوظ نفسه.
- حافظ على الكلمات نفسها؛ يسمح فقط بالتشكيل، الترقيم، والتمييز الإملائي
  الذي لا يغير المحتوى اللفظي.
- لا تضف شرحاً أو SSML أو timestamps إلى tts_text_ar.
- ابنِ performance arc حقيقياً: لا تجعل كل الحلقة بنفس النبرة والشدة.
- اجعل الوقفات تخدم المعنى لا الزينة.
- بعد الـHOOK يجب أن توجد وقفة لا تقل عن {HOOK_MIN_PAUSE_SECONDS} ثانية.
- بعد pre-outro transition يجب أن توجد وقفة لا تقل عن
  {PRE_OUTRO_MIN_PAUSE_SECONDS} ثانية قبل الـOutro.
- الـCTA الثابت خارج هذا النص تماماً ولا يجوز إدراجه:
  «{REUSABLE_CTA}»
- لا تولد صوتاً ولا تستدع TTS ولا تحدد مزود TTS في هذه المرحلة.
- لا تغيّر عدد المقاطع أو beat_id أو ترتيب المقاطع.
- source_narration_ar يجب أن يطابق Final Script حرفياً.
- tts_text_ar يجب أن يبقى مطابقاً لفظياً للمصدر؛ هدفه النطق لا التحرير.

اختبار MAX قبل PASS:
1) هل كل المرشحين للنطق روجعوا؟
2) هل توجد كلمة عربية ما زالت قابلة للالتباس عند القراءة الآلية؟
3) هل التشكيل محدود وهادف لا كثيفاً بلا حاجة؟
4) هل الأداء يتغير مع التوتر والندم والرجاء والتحول؟
5) هل الـHook مسموع بقوة ووضوح دون تمثيل زائد؟
6) هل الانتقال قبل الـOutro يترك مساحة سليمة قبل الـCTA المنفصل؟
7) هل أي tts_text غيّر المعنى أو أضاف كلمة؟ إن نعم فهذا فشل.
8) هل الناتج جاهز فعلياً لـFINAL_TTS؟

إذا احتجت جولة تحريرية أخرى داخل هذه البوابة، أعد CONTINUE_GATE.
لا تعد PASS إلا عندما تصبح النسخة جاهزة فعلياً لـFINAL_TTS.
""".strip()


def _request(
    final_script: Mapping[str, Any],
    claim_matrix: Mapping[str, Any],
    architecture: Mapping[str, Any],
    previous_gate: Mapping[str, Any] | None,
    iteration_no: int,
) -> dict[str, Any]:
    schema = _schema()
    _validate_strict_schema(schema)

    context: dict[str, Any] = {
        "stage": STAGE,
        "episode_id": EPISODE_ID,
        "iteration_no": iteration_no,
        "final_script": final_script,
        "source_claim_matrix_context_only": claim_matrix,
        "canonical_story_architecture_context_only": architecture,
        "constraints": {
            "hook_min_pause_seconds": HOOK_MIN_PAUSE_SECONDS,
            "pre_outro_min_pause_seconds": PRE_OUTRO_MIN_PAUSE_SECONDS,
            "reusable_cta_outside_gate": REUSABLE_CTA,
            "content_rewrite_allowed": False,
            "tts_provider_call_allowed": False,
        },
    }
    if previous_gate is not None:
        context["previous_gate_iteration"] = previous_gate
        context["instruction"] = (
            "نفذ revision targets السابقة ثم أعد فحص البوابة كاملة."
        )
    else:
        context["instruction"] = (
            "هذه أول مراجعة للنطق والأداء للنص النهائي المعتمد."
        )

    return {
        "model": MODEL,
        "store": False,
        "reasoning": {"effort": "max", "mode": "pro"},
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": _system_prompt()}],
            },
            {
                "role": "user",
                "content": [{
                    "type": "input_text",
                    "text": json.dumps(
                        context,
                        ensure_ascii=False,
                        indent=2,
                    ),
                }],
            },
        ],
        "text": {
            "verbosity": "high",
            "format": {
                "type": "json_schema",
                "name": "siraj_luna_pronunciation_performance_gate_v5_2",
                "strict": True,
                "schema": schema,
            },
        },
    }


def run(repo: Path) -> None:
    repo = repo.resolve()
    episode = repo / "projects" / EPISODE_ID

    final_script_path = episode / "preproduction/luna-final-script-v5-1.json"
    claim_matrix_path = episode / "research/source-claim-matrix-v5.json"
    architecture_path = episode / "preproduction/luna-story-architecture-v5.json"
    auth_path = (
        episode
        / "orchestration/luna-pronunciation-performance-gate-authorization-v5-2.json"
    )
    marker_path = episode / "orchestration/luna-runtime-v5-active.json"

    output_path = (
        episode
        / "preproduction/luna-pronunciation-performance-gate-v5-2.json"
    )
    tts_text_path = (
        episode
        / "preproduction/final-narration-tts-ready-ar-v5-2.txt"
    )
    performance_path = (
        episode
        / "preproduction/final-narration-performance-v5-2.json"
    )
    state_path = (
        episode
        / "orchestration/pronunciation-performance-gate-v5-2-state.json"
    )

    root = episode / "orchestration/luna-v5-2/pronunciation-performance-gate"
    ledger = root / "attempt-ledger.jsonl"
    lock_dir = root / "locks"
    raw_dir = root / "raw-responses"
    round_dir = root / "rounds"
    receipt_dir = root / "receipts"

    for path in (
        final_script_path,
        claim_matrix_path,
        architecture_path,
        auth_path,
        marker_path,
    ):
        if not path.is_file():
            raise PronunciationGateError(f"REQUIRED_FILE_MISSING:{path}")

    script = _read_json(final_script_path)
    claim_matrix = _read_json(claim_matrix_path)
    architecture = _read_json(architecture_path)
    auth = _read_json(auth_path)
    marker = _read_json(marker_path)

    if script.get("status") != "PASS":
        raise PronunciationGateError("FINAL_SCRIPT_NOT_PASS")
    if claim_matrix.get("status") != "PASS":
        raise PronunciationGateError("CLAIM_MATRIX_NOT_PASS")
    if architecture.get("status") != "PASS":
        raise PronunciationGateError("ARCHITECTURE_NOT_PASS")
    if auth.get("status") != "ACTIVE":
        raise PronunciationGateError(
            f"GATE_AUTHORIZATION_NOT_ACTIVE:{auth.get('status')}"
        )
    if auth.get("automatic_retry") is not False:
        raise PronunciationGateError("AUTOMATIC_RETRY_MUST_BE_FALSE")

    expected_marker = {
        "luna_reasoning_effort": "max",
        "luna_reasoning_mode": "pro",
        "iconic_cinematic_brain": "ACTIVE",
        "final_script_v5_1_status": "PASS",
        "next_stage": STAGE,
        "local_resource_guard": "V5.2_ACTIVE",
    }
    bad = [
        f"{k}={marker.get(k)!r}"
        for k, v in expected_marker.items()
        if marker.get(k) != v
    ]
    if bad:
        raise PronunciationGateError(
            "GATE_RUNTIME_MARKER_NOT_READY:" + ",".join(bad)
        )

    if output_path.is_file():
        existing = _read_json(output_path)
        _validate_result(existing, script)
        if existing.get("status") == "PASS":
            print("SIRAJ_LUNA_PRONUNCIATION_PERFORMANCE_GATE_V5_2_ALREADY_COMPLETE")
            print("OUTPUT=" + str(output_path))
            print("NEXT_STAGE=" + NEXT_STAGE)
            return

    last = _last_ledger_event(ledger)
    if last and last.get("event") in {
        "PREPARED",
        "FAILED_NO_AUTO_RETRY",
        "CONSUMED_UNUSABLE_NO_AUTO_RETRY",
        "CONSUMED_INVALID_JSON_NO_AUTO_RETRY",
        "CONSUMED_SCHEMA_INVALID_NO_AUTO_RETRY",
    }:
        raise PronunciationGateError(
            "PREVIOUS_NON_SUCCESSFUL_ATTEMPT_REQUIRES_MANUAL_REVIEW:"
            + str(last.get("event"))
        )

    completed_rounds = sorted(round_dir.glob("iteration-*.json"))
    previous_gate = None
    iteration_no = 1
    if completed_rounds:
        previous_gate = _read_json(completed_rounds[-1])
        _validate_result(previous_gate, script)
        iteration_no = int(
            previous_gate.get("_siraj_iteration_no", 0) or 0
        ) + 1
        if previous_gate.get("status") == "NEEDS_FINAL_SCRIPT_REOPEN":
            raise PronunciationGateError(
                "PREVIOUS_GATE_REQUIRES_FINAL_SCRIPT_REOPEN"
            )

    total_input = 0
    total_output = 0
    total_cost = 0.0
    completed_iterations = 0
    for receipt_path in receipt_dir.glob("*.json"):
        receipt = _read_json(receipt_path)
        total_input += int(receipt.get("input_tokens", 0) or 0)
        total_output += int(receipt.get("output_tokens", 0) or 0)
        total_cost += float(receipt.get("base_text_cost_usd", 0) or 0)
        completed_iterations += 1

    while True:
        payload = _request(
            script,
            claim_matrix,
            architecture,
            previous_gate,
            iteration_no,
        )
        request_uuid = str(uuid.uuid4())

        _exclusive_json(
            lock_dir / f"{request_uuid}.json",
            {
                "schema_version": "siraj-luna-pronunciation-gate-lock-v5.2",
                "episode_id": EPISODE_ID,
                "stage": STAGE,
                "iteration_no": iteration_no,
                "request_uuid": request_uuid,
                "authorization_id": auth.get("authorization_id"),
                "reasoning_effort": "max",
                "reasoning_mode": "pro",
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
                "timestamp_utc": _now(),
            },
        )
        _atomic_json(
            state_path,
            {
                "schema_version": "siraj-pronunciation-gate-state-v5.2",
                "episode_id": EPISODE_ID,
                "stage": STAGE,
                "status": "SUBMITTING",
                "iteration_no": iteration_no,
                "request_uuid": request_uuid,
                "automatic_retry": False,
                "updated_at_utc": _now(),
            },
        )

        try:
            response = post_luna_once(
                repo,
                payload,
                client_request_id=request_uuid,
            )
        except Exception as exc:
            _append_jsonl(
                ledger,
                {
                    "event": "FAILED_NO_AUTO_RETRY",
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
            _atomic_json(state_path, state)
            raise

        raw_path = raw_dir / f"{request_uuid}.json"
        _exclusive_json(raw_path, response)

        response_status = str(response.get("status") or "")
        if response_status and response_status != "completed":
            inp, out, cached = _usage(response)
            _append_jsonl(
                ledger,
                {
                    "event": "CONSUMED_UNUSABLE_NO_AUTO_RETRY",
                    "iteration_no": iteration_no,
                    "request_uuid": request_uuid,
                    "response_id": response.get("id"),
                    "response_status": response_status,
                    "input_tokens": inp,
                    "cached_input_tokens": cached,
                    "output_tokens": out,
                    "timestamp_utc": _now(),
                },
            )
            raise PronunciationGateError(
                f"LUNA_RESPONSE_NOT_COMPLETED:{response_status}"
            )

        text = _extract_output_text(response)
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            inp, out, cached = _usage(response)
            _append_jsonl(
                ledger,
                {
                    "event": "CONSUMED_INVALID_JSON_NO_AUTO_RETRY",
                    "iteration_no": iteration_no,
                    "request_uuid": request_uuid,
                    "response_id": response.get("id"),
                    "input_tokens": inp,
                    "cached_input_tokens": cached,
                    "output_tokens": out,
                    "json_error": str(exc),
                    "timestamp_utc": _now(),
                },
            )
            raise PronunciationGateError("GATE_JSON_INVALID") from exc

        if not isinstance(result, dict):
            raise PronunciationGateError("GATE_RESULT_OBJECT_REQUIRED")

        try:
            _validate_result(result, script)
        except Exception as exc:
            inp, out, cached = _usage(response)
            _append_jsonl(
                ledger,
                {
                    "event": "CONSUMED_SCHEMA_INVALID_NO_AUTO_RETRY",
                    "iteration_no": iteration_no,
                    "request_uuid": request_uuid,
                    "response_id": response.get("id"),
                    "input_tokens": inp,
                    "cached_input_tokens": cached,
                    "output_tokens": out,
                    "validation_error": str(exc),
                    "timestamp_utc": _now(),
                },
            )
            state = _read_json(state_path)
            state["status"] = "SCHEMA_INVALID_NO_AUTO_RETRY"
            state["raw_response_path"] = str(raw_path)
            state["validation_error"] = str(exc)
            state["updated_at_utc"] = _now()
            _atomic_json(state_path, state)
            raise

        inp, out, cached = _usage(response)
        cost = _base_text_cost_usd(inp, out)
        total_input += inp
        total_output += out
        total_cost += cost
        completed_iterations += 1

        round_result = dict(result)
        round_result["_siraj_iteration_no"] = iteration_no
        round_result["_siraj_runtime"] = {
            "runtime": "V5.2_MAX_PRO_ICONIC_CINEMATIC_RESOURCE_GUARDED",
            "request_uuid": request_uuid,
            "response_id": response.get("id"),
            "reasoning_effort": "max",
            "reasoning_mode": "pro",
            "input_tokens": inp,
            "cached_input_tokens": cached,
            "output_tokens": out,
            "base_text_cost_usd": cost,
            "automatic_retry": False,
            "completed_at_utc": _now(),
        }

        round_path = round_dir / f"iteration-{iteration_no:03d}.json"
        _exclusive_json(round_path, round_result)
        _exclusive_json(
            receipt_dir / f"{request_uuid}.json",
            {
                "schema_version": "siraj-luna-pronunciation-gate-receipt-v5.2",
                "episode_id": EPISODE_ID,
                "stage": STAGE,
                "iteration_no": iteration_no,
                "request_uuid": request_uuid,
                "response_id": response.get("id"),
                "input_tokens": inp,
                "cached_input_tokens": cached,
                "output_tokens": out,
                "base_text_cost_usd": cost,
                "result_status": result.get("status"),
                "automatic_retry": False,
                "completed_at_utc": _now(),
            },
        )
        _append_jsonl(
            ledger,
            {
                "event": "COMPLETE",
                "iteration_no": iteration_no,
                "request_uuid": request_uuid,
                "response_id": response.get("id"),
                "input_tokens": inp,
                "output_tokens": out,
                "base_text_cost_usd": cost,
                "result_status": result.get("status"),
                "timestamp_utc": _now(),
            },
        )

        status = result.get("status")
        if status == "PASS":
            final = dict(round_result)
            final["_siraj_stage_summary"] = {
                "status": "PASS",
                "iterations_completed": completed_iterations,
                "total_input_tokens": total_input,
                "total_output_tokens": total_output,
                "cumulative_base_text_cost_usd": round(total_cost, 8),
                "hook_min_pause_seconds": HOOK_MIN_PAUSE_SECONDS,
                "pre_outro_min_pause_seconds": PRE_OUTRO_MIN_PAUSE_SECONDS,
                "assistant_authored_call_limit": None,
                "assistant_authored_cost_cap_usd": None,
                "assistant_authored_max_output_tokens": None,
                "assistant_authored_fixed_pacing_seconds": None,
                "automatic_retry": False,
            }
            _atomic_json(output_path, final)

            ordered = sorted(
                result["segments"],
                key=lambda x: int(x["order"]),
            )
            tts_master = "\n\n".join(
                str(seg["tts_text_ar"]).strip() for seg in ordered
            )
            transition_text = str(
                result["pre_outro_transition"]["tts_text_ar"]
            ).strip()
            if transition_text:
                tts_master += "\n\n" + transition_text
            tts_text_path.parent.mkdir(parents=True, exist_ok=True)
            tts_text_path.write_text(
                tts_master.strip() + "\n",
                encoding="utf-8",
                newline="\n",
            )

            _atomic_json(
                performance_path,
                {
                    "schema_version": "siraj-final-narration-performance-v5.2",
                    "episode_id": EPISODE_ID,
                    "stage": STAGE,
                    "voice_profile_ar": result["voice_profile_ar"],
                    "performance_arc_ar": result["performance_arc_ar"],
                    "segments": result["segments"],
                    "pre_outro_transition": result["pre_outro_transition"],
                    "pronunciation_decisions": result["pronunciation_decisions"],
                    "reusable_cta_outro": "SEPARATE_MASTER_NOT_INCLUDED",
                },
            )

            marker = _read_json(marker_path)
            marker["pronunciation_performance_gate_v5_2_status"] = "PASS"
            marker["pronunciation_performance_gate_v5_2_output"] = str(
                output_path
            )
            marker["tts_ready_narration_v5_2"] = str(tts_text_path)
            marker["next_stage"] = NEXT_STAGE
            marker["updated_at_utc"] = _now()
            _atomic_json(marker_path, marker)

            auth["status"] = "COMPLETED"
            auth["completed_iterations"] = completed_iterations
            auth["completed_at_utc"] = _now()
            _atomic_json(auth_path, auth)

            print("SIRAJ_LUNA_PRONUNCIATION_PERFORMANCE_GATE_V5_2_COMPLETE")
            print("STATUS=PASS")
            print("ITERATIONS_COMPLETED=" + str(completed_iterations))
            print("SEGMENTS=" + str(len(result["segments"])))
            print(
                "PRONUNCIATION_CANDIDATES_REVIEWED="
                + str(len(_candidate_terms(script)))
            )
            print(
                "PRONUNCIATION_DECISIONS="
                + str(len(result["pronunciation_decisions"]))
            )
            print("HOOK_MIN_PAUSE_SECONDS=" + str(HOOK_MIN_PAUSE_SECONDS))
            print(
                "PRE_OUTRO_MIN_PAUSE_SECONDS="
                + str(PRE_OUTRO_MIN_PAUSE_SECONDS)
            )
            print("LUNA_REASONING_EFFORT=MAX")
            print("LUNA_REASONING_MODE=PRO")
            print("ICONIC_CINEMATIC_CREATIVE_BRAIN=ACTIVE")
            print("LOCAL_RESOURCE_GUARD=V5.2_ACTIVE")
            print("TTS_PROVIDER_CALLS=0")
            print("TOTAL_INPUT_TOKENS=" + str(total_input))
            print("TOTAL_OUTPUT_TOKENS=" + str(total_output))
            print(
                "CUMULATIVE_BASE_TEXT_COST_USD="
                + f"{total_cost:.8f}"
            )
            print("ASSISTANT_AUTHORED_CALL_LIMIT=NONE")
            print("ASSISTANT_AUTHORED_COST_CAP_USD=NONE")
            print("ASSISTANT_AUTHORED_MAX_OUTPUT_TOKENS=NONE")
            print("AUTOMATIC_PROVIDER_RETRIES=0")
            print("OUTPUT=" + str(output_path))
            print("TTS_READY_NARRATION=" + str(tts_text_path))
            print("PERFORMANCE_PLAN=" + str(performance_path))
            print("NEXT_STAGE=" + NEXT_STAGE)
            return

        if status == "NEEDS_FINAL_SCRIPT_REOPEN":
            marker = _read_json(marker_path)
            marker["pronunciation_performance_gate_v5_2_status"] = (
                "NEEDS_FINAL_SCRIPT_REOPEN"
            )
            marker["next_stage"] = "FINAL_SCRIPT_REOPEN"
            marker["updated_at_utc"] = _now()
            _atomic_json(marker_path, marker)
            print("SIRAJ_LUNA_PRONUNCIATION_PERFORMANCE_GATE_V5_2_STOPPED")
            print("STATUS=NEEDS_FINAL_SCRIPT_REOPEN")
            print("AUTOMATIC_PROVIDER_RETRIES=0")
            print("NEXT_STAGE=FINAL_SCRIPT_REOPEN")
            return

        if status != "CONTINUE_GATE":
            raise PronunciationGateError(
                f"UNEXPECTED_GATE_STATUS:{status}"
            )

        previous_gate = round_result
        iteration_no += 1
        print("LUNA_PRONUNCIATION_GATE_CONTINUE:NEXT_ITERATION=" + str(iteration_no))


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
        raise SystemExit("EXPLICIT_FLAG_REQUIRED:--run-authorized")
    run(Path(args.repo))


if __name__ == "__main__":
    main()
