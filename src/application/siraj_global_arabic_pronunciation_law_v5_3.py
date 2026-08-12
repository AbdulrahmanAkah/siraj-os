"""SIRAJ V5.3 — Global Arabic Pronunciation Law.

This is a series-wide invariant for every Arabic text that will be spoken,
rendered by TTS, reused for voice, or regenerated in the future.

It does not force research/claim/source documents to be vocalized.
It governs narration / spoken-text artifacts and every FINAL_TTS preflight.

Core law:
- full pronunciation-oriented Arabic diacritization is mandatory
- no bare multi-letter Arabic word may enter TTS
- lexical/script content may not be rewritten by the pronunciation layer
- Quran quotations should use canonical sourced vocalization when available
- legacy narration is audited and must pass this law before any future TTS/reuse
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

LAW_VERSION = "siraj-global-arabic-pronunciation-law-v5.3"
FULL_PRONUNCIATION_DIACRITIZATION_REQUIRED = True
SELECTIVE_DIACRITIZATION_ONLY_ALLOWED = False
LEXICAL_REWRITE_ALLOWED = False
BARE_MULTI_LETTER_ARABIC_WORDS_ALLOWED = False

ARABIC_MARKS_RE = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]"
)
ARABIC_WORD_RE = re.compile(
    r"[\u0621-\u064A\u0671\u067E\u0686\u06A4\u06AF\u06CC"
    r"\u064B-\u065F\u0670]+"
)
ARABIC_BASE_RE = re.compile(
    r"[\u0621-\u064A\u0671\u067E\u0686\u06A4\u06AF\u06CC]"
)

_PUNCT_RE = re.compile(
    r"[\s\.,،؛;:!؟\?…ـ\"'“”‘’()\[\]{}<>«»\-—–_/\\|]+"
)

SAFE_ORTHOGRAPHIC_TRANSLATION = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        # Madda represents hamza + alif for lexical comparison.
        "ٱ": "ا",
        "ى": "ي",
        "ی": "ي",
        "ک": "ك",
        "ؤ": "ء",
        "ئ": "ء",
    }
)


@dataclass(frozen=True)
class PronunciationAudit:
    total_arabic_words: int
    bare_multi_letter_words: tuple[str, ...]
    marked_word_ratio: float

    @property
    def passes_no_bare_word_gate(self) -> bool:
        return not self.bare_multi_letter_words


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


def lexical_skeleton(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = ARABIC_MARKS_RE.sub("", value)
    value = _normalize_madda_for_lexical_comparison(value)
    value = value.translate(SAFE_ORTHOGRAPHIC_TRANSLATION)
    return _PUNCT_RE.sub("", value)


def _base_letter_count(token: str) -> int:
    return len(ARABIC_BASE_RE.findall(token))


def _mark_count(token: str) -> int:
    return len(ARABIC_MARKS_RE.findall(token))


def audit_spoken_arabic(text: str) -> PronunciationAudit:
    words = ARABIC_WORD_RE.findall(str(text or ""))
    bare: list[str] = []
    marked = 0
    considered = 0

    for token in words:
        bases = _base_letter_count(token)
        if bases <= 1:
            continue
        considered += 1
        marks = _mark_count(token)
        if marks <= 0:
            bare.append(token)
        else:
            marked += 1

    ratio = 1.0 if considered == 0 else marked / considered
    return PronunciationAudit(
        total_arabic_words=considered,
        bare_multi_letter_words=tuple(bare),
        marked_word_ratio=ratio,
    )



_FORBIDDEN_TTS_MARKUP_RE = re.compile(
    r"(?m)^\s{0,3}#{1,6}\s+|```|`|\*\*|__"
)
_SIRAJ_PRONUNCIATION_CARRIERS = {"ا", "ى", "و", "ي", "ی", "آ"}


def assert_no_forbidden_tts_markup(text: str, label: str) -> None:
    if _FORBIDDEN_TTS_MARKUP_RE.search(str(text or "")):
        raise ValueError(
            "SIRAJ_TTS_MARKDOWN_OR_CONTROL_MARKUP_FORBIDDEN:" + label
        )


def assert_minimum_full_diacritization(text: str, label: str) -> None:
    for token in ARABIC_WORD_RE.findall(str(text or "")):
        value = unicodedata.normalize("NFKC", token)
        bases = ARABIC_BASE_RE.findall(value)
        marks = ARABIC_MARKS_RE.findall(value)
        if len(bases) <= 1:
            continue
        exempt = sum(
            ch in _SIRAJ_PRONUNCIATION_CARRIERS
            for ch in bases
        )
        minimum_marks = max(1, len(bases) - exempt)
        if len(marks) < minimum_marks:
            raise ValueError(
                "SIRAJ_TTS_UNDER_DIACRITIZED:"
                f"{label}:{token}:marks={len(marks)}:"
                f"minimum={minimum_marks}"
            )


def assert_no_bare_arabic_words(text: str, label: str) -> None:
    audit = audit_spoken_arabic(text)
    if audit.bare_multi_letter_words:
        preview = "|".join(audit.bare_multi_letter_words[:20])
        raise ValueError(
            "SIRAJ_TTS_BARE_ARABIC_WORDS_FORBIDDEN:"
            f"{label}:count={len(audit.bare_multi_letter_words)}:"
            f"preview={preview}"
        )


def assert_pronunciation_layer_preserves_lexical_content(
    source_text: str,
    tts_text: str,
    label: str,
) -> None:
    if lexical_skeleton(source_text) != lexical_skeleton(tts_text):
        raise ValueError(
            "SIRAJ_PRONUNCIATION_LAYER_LEXICAL_REWRITE_FORBIDDEN:"
            + label
        )


def is_probable_spoken_artifact_path(path_text: str) -> bool:
    lower = str(path_text).lower().replace("\\", "/")
    tokens = (
        "narration",
        "tts",
        "voice",
        "final-script",
        "final_script",
        "script",
    )
    return any(token in lower for token in tokens)
