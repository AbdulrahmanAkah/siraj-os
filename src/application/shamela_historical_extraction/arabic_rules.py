"""Conservative deterministic Arabic rules used by the extraction pilot."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterator


ARABIC_LETTER = r"[\u0621-\u063A\u0641-\u064A\u0670-\u06D3\u064B-\u065F]"
ARABIC_WORD = rf"{ARABIC_LETTER}+"
SPACE = r"[ \t]+"

_SPACE_RE = re.compile(r"\s+")
_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670]")
_PUNCTUATION = " \t\r\n،؛:,.!?؟()[]{}«»\"'"
_TITLE_RE = re.compile(
    rf"\b(?P<title>الخليفة|السلطان|الملك|الأمير|الإمام|الشيخ|الحافظ|"
    rf"العالم|القاضي|النبي|الرسول|المؤرخ){SPACE}"
    rf"(?P<name>{ARABIC_WORD}(?:{SPACE}{ARABIC_WORD}){{0,5}})"
)
_KUNYA_RE = re.compile(
    rf"\b(?P<name>(?:أبو|أبي|أبا|أم){SPACE}{ARABIC_WORD}"
    rf"(?:{SPACE}(?:بن|ابن|بنت){SPACE}{ARABIC_WORD}){{0,3}})"
)
_LINEAGE_RE = re.compile(
    rf"\b(?P<name>{ARABIC_WORD}{SPACE}(?:بن|ابن|بنت){SPACE}{ARABIC_WORD}"
    rf"(?:{SPACE}(?:بن|ابن|بنت){SPACE}{ARABIC_WORD}){{0,3}})"
)
_WORK_RE = re.compile(
    rf"\b(?:كتاب|رسالة|مصنف){SPACE}(?P<name>{ARABIC_WORD}"
    rf"(?:{SPACE}{ARABIC_WORD}){{0,6}})"
)
_GROUP_RE = re.compile(
    rf"\b(?P<name>(?:بنو|قبيلة|الدولة|فرقة|طائفة){SPACE}"
    rf"{ARABIC_WORD}(?:{SPACE}{ARABIC_WORD}){{0,3}})"
)
_ISNAD_RE = re.compile(
    rf"\b(?P<connector>حدثنا|حدثني|أخبرنا|أخبرني|أنبأنا|أنبأني|"
    rf"سمعت|روى|عن){SPACE}"
    rf"(?P<name>{ARABIC_WORD}(?:{SPACE}{ARABIC_WORD}){{0,5}})"
)
_ISNAD_START_RE = re.compile(
    r"\b(?:حدثنا|حدثني|أخبرنا|أخبرني|أنبأنا|أنبأني|سمعت|روى)\b"
)
_HIJRI_YEAR_RE = re.compile(
    r"(?P<prefix>نحو|قرابة|حوالي|قيل|اختلف في)?\s*"
    r"(?:سنة|عام)\s+(?P<year>[٠-٩0-9]{1,4})\s*(?P<calendar>هـ|هجرية)?"
)
_GREGORIAN_YEAR_RE = re.compile(
    r"(?P<prefix>نحو|قرابة|حوالي|قيل|اختلف في)?\s*"
    r"(?:سنة|عام)\s+(?P<year>[٠-٩0-9]{3,4})\s*(?P<calendar>م|ميلادية)"
)
_CENTURY_RE = re.compile(
    rf"\b(?P<prefix>أوائل|أواخر|منتصف)?{SPACE}?"
    rf"القرن{SPACE}(?P<century>{ARABIC_WORD}|[٠-٩0-9]{{1,2}})"
    rf"(?:{SPACE}(?P<calendar>الهجري|الميلادي))?"
)
_RANGE_RE = re.compile(
    r"\b(?:من|بين)\s+(?:سنة\s+)?(?P<start>[٠-٩0-9]{1,4})"
    r"\s+(?:إلى|و)\s+(?:سنة\s+)?(?P<end>[٠-٩0-9]{1,4})"
    r"\s*(?P<calendar>هـ|م)?"
)
_RELATIVE_RE = re.compile(
    rf"\b(?P<relation>قبل|بعد){SPACE}"
    rf"(?!(?:أن|ذلك|هذا|هذه|ما)\b)"
    rf"(?P<event>{ARABIC_WORD}"
    rf"(?:{SPACE}{ARABIC_WORD}){{0,5}})"
)

_STOP_NAME_TOKENS = {
    "قال",
    "كان",
    "وكان",
    "ثم",
    "عن",
    "في",
    "من",
    "إلى",
    "على",
    "وقد",
    "هو",
    "وهو",
    "الذي",
    "أن",
    "إن",
    "حدثنا",
    "أخبرنا",
    "أنبأنا",
    "سمعت",
    "ولد",
    "توفي",
    "مات",
    "قتل",
    "حكم",
    "أسس",
}

_TITLE_TYPES = {
    "الخليفة": ("PERSON", "CALIPH", "RULER"),
    "السلطان": ("PERSON", "RULER"),
    "الملك": ("PERSON", "RULER"),
    "الأمير": ("PERSON", "RULER"),
    "الإمام": ("PERSON", "SCHOLAR"),
    "الشيخ": ("PERSON", "SCHOLAR"),
    "الحافظ": ("PERSON", "SCHOLAR"),
    "العالم": ("PERSON", "SCHOLAR"),
    "القاضي": ("PERSON", "SCHOLAR"),
    "المؤرخ": ("PERSON", "SCHOLAR", "AUTHOR"),
    "النبي": ("PERSON", "PROPHET"),
    "الرسول": ("PERSON", "PROPHET"),
}

PLACE_TYPES = {
    "بغداد": ("PLACE", "CITY"),
    "مكة": ("PLACE", "CITY"),
    "مكة المكرمة": ("PLACE", "CITY"),
    "المدينة": ("PLACE", "CITY"),
    "المدينة المنورة": ("PLACE", "CITY"),
    "الكوفة": ("PLACE", "CITY"),
    "البصرة": ("PLACE", "CITY"),
    "دمشق": ("PLACE", "CITY"),
    "القاهرة": ("PLACE", "CITY"),
    "مصر": ("PLACE", "REGION"),
    "العراق": ("PLACE", "REGION"),
    "الشام": ("PLACE", "REGION"),
    "الحجاز": ("PLACE", "REGION"),
    "اليمن": ("PLACE", "REGION"),
    "خراسان": ("PLACE", "REGION"),
    "الموصل": ("PLACE", "CITY"),
    "واسط": ("PLACE", "CITY"),
}

EVENT_RULES = (
    ("BIRTH_EVENT", re.compile(r"\bولد\b|\bمولده\b"), "EVENT_BIRTH_V1"),
    ("DEATH_EVENT", re.compile(r"\bتوفي\b|\bمات\b|\bوفاته\b"), "EVENT_DEATH_V1"),
    ("FOUNDING_EVENT", re.compile(r"\bأسس\b|\bأنشأ\b|\bبنى\b"), "EVENT_FOUNDING_V1"),
    (
        "RULE_EVENT",
        re.compile(
            r"\b(?:تولى(?: الحكم| الخلافة| الملك)?|ولي الخلافة|"
            r"حكم (?:البلاد|الدولة|الإمارة|المملكة|مصر|العراق|"
            r"الشام|الحجاز|اليمن|خراسان|بغداد|دمشق|القاهرة))\b"
        ),
        "EVENT_RULE_V1",
    ),
    ("CONFLICT_EVENT", re.compile(r"\bقاتل\b|\bحارب\b|\bوقعة\b|\bمعركة\b"), "EVENT_CONFLICT_V1"),
    ("TRAVEL_EVENT", re.compile(r"\bرحل\b|\bسافر\b|\bقدم إلى\b"), "EVENT_TRAVEL_V1"),
    ("AUTHORSHIP_EVENT", re.compile(r"\bألف\b|\bصنف\b|\bكتب كتاب\b"), "EVENT_AUTHORSHIP_V1"),
)

RELATION_KEYWORDS = (
    (
        "NARRATED_FROM",
        re.compile(
            r"\b(?:روى|حدثنا|حدثني|أخبرنا|أخبرني|أنبأنا|"
            r"أنبأني|سمعت)\b.*\bعن\b"
        ),
        "REL_NARRATED_FROM_V1",
    ),
    ("TEACHER_OF", re.compile(r"\b(?:شيخ|أستاذ)\b"), "REL_TEACHER_V1"),
    ("STUDENT_OF", re.compile(r"\b(?:تلميذ|تتلمذ على)\b"), "REL_STUDENT_V1"),
    (
        "AUTHORED",
        re.compile(r"\b(?:ألف|صنف|كتب كتاب)\b"),
        "REL_AUTHORED_V1",
    ),
    (
        "RULED",
        re.compile(
            r"\b(?:تولى(?: الحكم| الخلافة| الملك)?|ولي الخلافة|"
            r"حكم (?:البلاد|الدولة|الإمارة|المملكة|مصر|العراق|"
            r"الشام|الحجاز|اليمن|خراسان|بغداد|دمشق|القاهرة))\b"
        ),
        "REL_RULED_V1",
    ),
    ("FOUNDED", re.compile(r"\b(?:أسس|أنشأ|بنى)\b"), "REL_FOUNDED_V1"),
    ("FOUGHT", re.compile(r"\b(?:قاتل|حارب)\b"), "REL_FOUGHT_V1"),
    ("OPPOSED", re.compile(r"\b(?:عارض|خالف|نازع)\b"), "REL_OPPOSED_V1"),
    ("LIVED_IN", re.compile(r"\b(?:سكن|أقام في|عاش في)\b"), "REL_LIVED_IN_V1"),
    ("TRAVELED_TO", re.compile(r"\b(?:رحل إلى|سافر إلى|قدم إلى)\b"), "REL_TRAVELED_V1"),
    ("BORN_IN", re.compile(r"\b(?:ولد في|مولده في)\b"), "REL_BORN_IN_V1"),
    ("DIED_IN", re.compile(r"\b(?:توفي في|مات في)\b"), "REL_DIED_IN_V1"),
    ("PRECEDED", re.compile(r"\b(?:سبق|تقدم على)\b"), "REL_PRECEDED_V1"),
    ("SUCCEEDED", re.compile(r"\b(?:خلف|جاء بعد)\b"), "REL_SUCCEEDED_V1"),
)


def normalize_surface(value: str) -> str:
    value = unicodedata.normalize("NFC", value).replace("\u0640", "")
    return _SPACE_RE.sub(" ", value).strip(_PUNCTUATION)


def resolution_key(value: str) -> str:
    value = _DIACRITICS_RE.sub("", normalize_surface(value))
    return (
        value.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .casefold()
    )


def sentence_spans(text: str) -> Iterator[tuple[int, int, str]]:
    start = 0
    for match in re.finditer(r"[.!؟؛\n]+", text):
        end = match.end()
        sentence = text[start:end]
        trimmed = sentence.strip()
        if trimmed:
            left = len(sentence) - len(sentence.lstrip())
            right = len(sentence.rstrip())
            yield start + left, start + right, trimmed
        start = end
    tail = text[start:]
    if tail.strip():
        left = len(tail) - len(tail.lstrip())
        yield start + left, len(text.rstrip()), tail.strip()


def _trim_name_match(
    text: str,
    start: int,
    end: int,
) -> tuple[int, int, str] | None:
    raw = text[start:end]
    tokens = raw.split()
    while tokens and tokens[0].strip(_PUNCTUATION) in _STOP_NAME_TOKENS:
        tokens.pop(0)
    kept: list[str] = []
    for token in tokens:
        cleaned = token.strip(_PUNCTUATION)
        if cleaned in _STOP_NAME_TOKENS and kept:
            break
        if cleaned:
            kept.append(cleaned)
    if not kept:
        return None
    value = " ".join(kept)
    adjusted_end = start + raw.find(value) + len(value)
    adjusted_start = start + raw.find(value)
    return adjusted_start, adjusted_end, value


def entity_candidates(text: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for match in _TITLE_RE.finditer(text):
        trimmed = _trim_name_match(
            text,
            match.start("name"),
            match.end("name"),
        )
        if trimmed is None:
            continue
        start, end, raw_name = trimmed
        title = match.group("title")
        candidates.append(
            {
                "start": start,
                "end": end,
                "surface": raw_name,
                "types": list(_TITLE_TYPES[title]),
                "confidence": 0.91,
                "context": "BODY",
                "rule_id": "ENTITY_EXPLICIT_TITLE_V1",
            }
        )

    for pattern, confidence, rule_id in (
        (_KUNYA_RE, 0.82, "ENTITY_KUNYA_V1"),
        (_LINEAGE_RE, 0.84, "ENTITY_LINEAGE_V1"),
    ):
        for match in pattern.finditer(text):
            candidates.append(
                {
                    "start": match.start("name"),
                    "end": match.end("name"),
                    "surface": match.group("name"),
                    "types": ["PERSON"],
                    "confidence": confidence,
                    "context": "BODY",
                    "rule_id": rule_id,
                }
            )

    for match in _WORK_RE.finditer(text):
        trimmed = _trim_name_match(
            text,
            match.start("name"),
            match.end("name"),
        )
        if trimmed:
            start, end, surface = trimmed
            candidates.append(
                {
                    "start": start,
                    "end": end,
                    "surface": surface,
                    "types": ["WORK"],
                    "confidence": 0.76,
                    "context": "BODY",
                    "rule_id": "ENTITY_WORK_TITLE_V1",
                }
            )

    for match in _GROUP_RE.finditer(text):
        trimmed = _trim_name_match(
            text,
            match.start("name"),
            match.end("name"),
        )
        if trimmed:
            start, end, surface = trimmed
            group_type = "TRIBE" if surface.startswith(("بنو ", "قبيلة ")) else "SECT"
            if surface.startswith("الدولة "):
                group_type = "STATE"
            candidates.append(
                {
                    "start": start,
                    "end": end,
                    "surface": surface,
                    "types": ["GROUP", group_type],
                    "confidence": 0.84,
                    "context": "BODY",
                    "rule_id": "ENTITY_GROUP_V1",
                }
            )

    for place, types in sorted(
        PLACE_TYPES.items(),
        key=lambda item: (-len(item[0]), item[0]),
    ):
        pattern = re.compile(rf"(?<!{ARABIC_LETTER}){re.escape(place)}(?!{ARABIC_LETTER})")
        for match in pattern.finditer(text):
            candidates.append(
                {
                    "start": match.start(),
                    "end": match.end(),
                    "surface": match.group(),
                    "types": list(types),
                    "confidence": 0.96,
                    "context": "BODY",
                    "rule_id": "ENTITY_PLACE_DICTIONARY_V1",
                }
            )

    isnad_spans = [
        (start, end)
        for start, end, sentence in sentence_spans(text)
        if _ISNAD_START_RE.search(sentence)
    ]
    for match in _ISNAD_RE.finditer(text):
        if not any(
            start <= match.start() < end
            for start, end in isnad_spans
        ):
            continue
        trimmed = _trim_name_match(
            text,
            match.start("name"),
            match.end("name"),
        )
        if trimmed:
            start, end, surface = trimmed
            candidates.append(
                {
                    "start": start,
                    "end": end,
                    "surface": surface,
                    "types": ["PERSON", "NARRATOR"],
                    "confidence": 0.88,
                    "context": "ISNAD",
                    "connector": match.group("connector"),
                    "rule_id": "ENTITY_ISNAD_NARRATOR_V1",
                }
            )

    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in candidates:
        key = (
            item["start"],
            item["end"],
            resolution_key(item["surface"]),
            tuple(sorted(item["types"])),
            item["context"],
        )
        unique[key] = item
    return sorted(
        unique.values(),
        key=lambda item: (
            item["start"],
            item["end"],
            item["rule_id"],
        ),
    )


def temporal_candidates(text: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    def precision(prefix: str | None) -> str:
        if prefix in {"نحو", "قرابة", "حوالي"}:
            return "APPROXIMATE"
        if prefix in {"قيل", "اختلف في"}:
            return "DISPUTED"
        return "YEAR"

    for match in _RANGE_RE.finditer(text):
        calendar = (
            "HIJRI"
            if match.group("calendar") == "هـ"
            else "GREGORIAN"
            if match.group("calendar") == "م"
            else "UNSPECIFIED"
        )
        candidates.append(
            {
                "start": match.start(),
                "end": match.end(),
                "value": f"{match.group('start')}-{match.group('end')}",
                "calendar": calendar,
                "type": "RANGE",
                "precision": "RANGE",
                "rule_id": "TEMPORAL_RANGE_V1",
            }
        )

    for pattern, default_calendar, rule_id in (
        (_GREGORIAN_YEAR_RE, "GREGORIAN", "TEMPORAL_GREGORIAN_YEAR_V1"),
        (_HIJRI_YEAR_RE, "HIJRI", "TEMPORAL_HIJRI_YEAR_V1"),
    ):
        for match in pattern.finditer(text):
            calendar_token = match.group("calendar")
            calendar = default_calendar
            if calendar_token is None and default_calendar == "HIJRI":
                calendar = "UNSPECIFIED"
            candidates.append(
                {
                    "start": match.start(),
                    "end": match.end(),
                    "value": match.group("year"),
                    "calendar": calendar,
                    "type": "YEAR",
                    "precision": precision(match.group("prefix")),
                    "rule_id": rule_id,
                }
            )

    for match in _CENTURY_RE.finditer(text):
        candidates.append(
            {
                "start": match.start(),
                "end": match.end(),
                "value": normalize_surface(match.group()),
                "calendar": (
                    "HIJRI"
                    if match.group("calendar") == "الهجري"
                    else "GREGORIAN"
                    if match.group("calendar") == "الميلادي"
                    else "UNSPECIFIED"
                ),
                "type": "CENTURY",
                "precision": (
                    "APPROXIMATE"
                    if match.group("prefix")
                    else "CENTURY"
                ),
                "rule_id": "TEMPORAL_CENTURY_V1",
            }
        )

    for match in _RELATIVE_RE.finditer(text):
        trimmed = _trim_name_match(
            text,
            match.start("event"),
            match.end("event"),
        )
        if trimmed:
            _, end, _ = trimmed
            candidates.append(
                {
                    "start": match.start(),
                    "end": end,
                    "value": normalize_surface(text[match.start():end]),
                    "calendar": "RELATIVE",
                    "type": "RELATIVE",
                    "precision": "RELATIVE",
                    "rule_id": "TEMPORAL_RELATIVE_V1",
                }
            )

    unique = {
        (item["start"], item["end"], item["rule_id"]): item
        for item in candidates
    }
    return sorted(
        unique.values(),
        key=lambda item: (
            item["start"],
            item["end"],
            item["rule_id"],
        ),
    )


def event_candidates(text: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for start, end, sentence in sentence_spans(text):
        for event_type, pattern, rule_id in EVENT_RULES:
            if pattern.search(sentence):
                results.append(
                    {
                        "start": start,
                        "end": end,
                        "text": text[start:end],
                        "event_type": event_type,
                        "confidence": 0.78,
                        "rule_id": rule_id,
                    }
                )
    return results


def explicit_relation_candidates(
    text: str,
    mentions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    sorted_mentions = sorted(
        mentions,
        key=lambda item: (item["start"], item["end"], item["mention_id"]),
    )

    isnad = [
        item
        for item in sorted_mentions
        if item.get("context") == "ISNAD"
    ]
    for left, right in zip(isnad, isnad[1:]):
        if right["start"] - left["end"] <= 120:
            relations.append(
                {
                    "subject": left,
                    "object": right,
                    "type": "NARRATED_FROM",
                    "start": left["start"],
                    "end": right["end"],
                    "confidence": 0.9,
                    "rule_id": "REL_ISNAD_ORDER_V1",
                }
            )

    for sentence_start, sentence_end, sentence in sentence_spans(text):
        sentence_mentions = [
            item
            for item in sorted_mentions
            if item["start"] >= sentence_start
            and item["end"] <= sentence_end
        ]
        for relation_type, pattern, rule_id in RELATION_KEYWORDS:
            if relation_type == "NARRATED_FROM":
                # Ordered isnad links are produced only from mentions that
                # were admitted by an explicit narration-start context.
                continue
            if not pattern.search(sentence) or len(sentence_mentions) < 2:
                continue
            for left, right in zip(
                sentence_mentions,
                sentence_mentions[1:],
            ):
                between = text[left["end"]:right["start"]]
                if pattern.search(sentence) and len(between) <= 120:
                    relations.append(
                        {
                            "subject": left,
                            "object": right,
                            "type": relation_type,
                            "start": sentence_start,
                            "end": sentence_end,
                            "confidence": 0.72,
                            "rule_id": rule_id,
                        }
                    )
                    break

    unique = {
        (
            item["subject"]["mention_id"],
            item["type"],
            item["object"]["mention_id"],
            item["start"],
            item["end"],
        ): item
        for item in relations
    }
    return sorted(
        unique.values(),
        key=lambda item: (
            item["start"],
            item["type"],
            item["subject"]["mention_id"],
            item["object"]["mention_id"],
        ),
    )


__all__ = [
    "EVENT_RULES",
    "RELATION_KEYWORDS",
    "entity_candidates",
    "event_candidates",
    "explicit_relation_candidates",
    "normalize_surface",
    "resolution_key",
    "sentence_spans",
    "temporal_candidates",
]
