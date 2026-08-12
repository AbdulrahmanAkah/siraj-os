from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any, Mapping

BRAIN_VERSION = "siraj-luna-iconic-cinematic-brain-v5.1"
BRAIN_MARKER = "[SIRAJ_LUNA_ICONIC_CINEMATIC_BRAIN_V5_1]"

CREATIVE_STAGES = {
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
    "LOCAL_ASSEMBLY_AND_MONTAGE",
    "SEMANTIC_AND_EDITORIAL_QA",
    "BOUNDED_PARTIAL_REPAIR",
    "FINAL_DELIVERABLE_REVIEW",
}

TRUTH_FIRST_STAGES = {
    "EPISODE_CONTENT_SELECTION",
    "SOURCE_RESEARCH_FROM_ZERO",
    "SOURCE_CLAIM_MATRIX",
}

CREATIVE_DIRECTOR_INSTRUCTION_AR = f"""
{BRAIN_MARKER}
أنت في المراحل الإبداعية من سراج تعمل كعقل إبداعي وسينمائي أيقوني أعلى:
Showrunner + Narrative Architect + Cinematic Director + Visual Storyteller +
Editorial Director + Creative Quality Controller.

المعيار ليس مجرد نص جيد أو صورة جميلة؛ المطلوب عمل له هوية تُتذكر.

قواعدك:
1) ICONIC FIRST: لا تقبل الحل الأول إذا كان مألوفاً أو عاماً.
2) CINEMATIC CAUSALITY: كل Beat يسبب ما بعده درامياً أو معرفياً.
3) VISUAL THINKING: فكّر في scale، spatial relationships، foreground/
midground/background، silhouette، negative space، visual hierarchy، contrast،
depth، lens logic، camera position، motivated movement، atmosphere،
materiality، light direction، continuity anchors، visual rhythm.
4) ONE MEMORABLE VISUAL IDEA PER MAJOR BEAT.
5) SILENT-FRAME TEST: إذا كُتم الصوت، يجب أن يحمل الكادر جوهر المعنى أو التحول.
6) NARRATION↔VISUAL SEMANTIC LOCK: الجمال المنفصل عن الجملة فشل.
7) SCALE AND THE UNSEEN: في الغيبيات تجنب الحديقة الأرضية والكليشيه وادعاء
وصف غير ثابت؛ استخدم التجريد والحجب والمقياس والرهبة دون اختراع عقيدة.
8) HISTORICAL/THEOLOGICAL DIGNITY: Claim Matrix تعلو على الدراما.
9) EMOTIONAL PRECISION: لا تستخدم "ملحمي" حلاً لكل شيء.
10) RHYTHM: ضغط/فسحة، حركة/سكون، كشف/استيعاب.
11) MOTIF & CONTINUITY: ابنِ motifs تتطور إذا خدمت المعنى.
12) ICONIC RESTRAINT: الفخامة ليست ازدحاماً.
13) ANTI-GENERIC-AI GATE: ارفض fantasy wallpaper، glow بلا وظيفة، شخصيات
تقف بلا فعل، montage عشوائي، حركة كاميرا بلا سبب، composition مكرر، أو prompt
مليء بصفات بلا منطق مكاني وسردي.
14) ORIGINALITY WITHOUT IMITATION: جودة سينمائية أصلية، لا نسخ أسلوب فنان محدد.
15) MAX SELF-CRITIQUE: قبل PASS اسأل ما المتوقع؟ ما الذي سيتذكر؟ ما الزائد؟
هل يوجد حل أجرأ لكنه أوضح وأصدق؟ وهل الإبداع غطى على الحقيقة؟

المعيار النهائي: دقة موثقة + وضوح + أثر عاطفي + هوية بصرية + ترابط + قابلية للتذكر.

[SIRAJ_GLOBAL_ARABIC_PRONUNCIATION_LAW_V5_3]
في كل مرحلة ينتج عنها نص عربي سيُنطق أو يُرسل إلى TTS: التشكيل النطقي الكامل قانون سلسلة، وليس خياراً تحريرياً. يمنع إدخال كلمات عربية متعددة الحروف عارية من التشكيل إلى TTS، ويمنع استخدام طبقة النطق لإعادة كتابة النص. الاقتباسات القرآنية المباشرة تستخدم الضبط الموثوق من المصدر متى كان متاحاً.
""".strip()

TRUTH_GUARD_INSTRUCTION_AR = f"""
{BRAIN_MARKER}
أنت في مرحلة توثيقية. العقل الإبداعي هنا ناقد جودة فقط، وليس مصدراً للحقائق.
الأولوية المطلقة: الدقة وprovenance والفصل بين النص الصريح والتفسير والرواية والجسر
التحريري. لا تضف تفصيلاً سينمائياً إلى claims ولا تحول الاحتمال إلى حقيقة.
""".strip()


def _serialize(request: Mapping[str, Any]) -> str:
    try:
        return json.dumps(dict(request), ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(request)


def _known_stage(value: object) -> str | None:
    text = str(value or "").strip().rstrip(".:")
    known = CREATIVE_STAGES | TRUTH_FIRST_STAGES
    return text if text in known else None


def _extract_explicit_stage_from_json_text(text: str) -> str | None:
    raw = str(text or "").strip()
    if not raw or raw[0] not in "{[":
        return None
    try:
        value = json.loads(raw)
    except Exception:
        return None

    def walk(node: object) -> str | None:
        if isinstance(node, Mapping):
            direct = _known_stage(node.get("stage"))
            if direct:
                return direct
            for child in node.values():
                found = walk(child)
                if found:
                    return found
        elif isinstance(node, list):
            for child in node:
                found = walk(child)
                if found:
                    return found
        return None

    return walk(value)


def _iter_input_texts(request: Mapping[str, Any]):
    input_value = request.get("input")
    if not isinstance(input_value, list):
        return
    for item in input_value:
        if not isinstance(item, Mapping):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, Mapping):
                continue
            text = block.get("text")
            if isinstance(text, str):
                yield text


def detect_stage(request: Mapping[str, Any]) -> str:
    direct = _known_stage(request.get("stage"))
    if direct:
        return direct

    for text in _iter_input_texts(request) or ():
        found = _extract_explicit_stage_from_json_text(text)
        if found:
            return found

    known = sorted(
        CREATIVE_STAGES | TRUTH_FIRST_STAGES,
        key=len,
        reverse=True,
    )
    declarations = (
        r"(?im)^\s*stage\s*[:=]\s*([A-Z0-9_]+)\s*[\.:]?\s*$",
        r"(?im)^\s*المرحلة\s*[:=]\s*([A-Z0-9_]+)\s*[\.:]?\s*$",
        r"(?im)^\s*المرحلة\s*[:=]\s*([A-Z0-9_]+)\s*[\.:]?",
    )
    for text in _iter_input_texts(request) or ():
        for pattern in declarations:
            match = re.search(pattern, text)
            if match:
                candidate = _known_stage(match.group(1))
                if candidate:
                    return candidate

    text = _serialize(request)
    for stage in known:
        if stage in text:
            return stage
    return "UNKNOWN"

def apply_iconic_cinematic_brain(
    request: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(request))
    if BRAIN_MARKER in _serialize(result):
        return result
    input_value = result.get("input")
    if not isinstance(input_value, list):
        return result
    stage = detect_stage(result)
    if stage in CREATIVE_STAGES:
        instruction = CREATIVE_DIRECTOR_INSTRUCTION_AR
    elif stage in TRUTH_FIRST_STAGES:
        instruction = TRUTH_GUARD_INSTRUCTION_AR
    else:
        instruction = (
            BRAIN_MARKER
            + "\nاعمل بأقصى معيار لسراج. لا تخترع حقائق. إن كانت المهمة إبداعية "
            "فاطلب حلاً أصيلاً سينمائياً غير عام، وإن كانت توثيقية فالدقة أولاً."
        )
    result["input"] = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": instruction}],
        },
        *input_value,
    ]
    return result
