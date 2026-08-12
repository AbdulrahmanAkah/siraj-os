from src.application.siraj_luna_upstream_transport_v6_3 import (
    PAID_UPSTREAM_STAGES,
    canonical_sha256,
)
from src.application.siraj_upstream_autopilot_v6_3 import (
    validate_tts_segment,
)
from src.application.siraj_series_autopilot_adapter_certification_v6_3 import (
    WAVE3_CERTIFIED,
)


def test_all_seven_upstream_stages_present():
    expected = {
        "TOPIC_SELECTION",
        "SOURCE_RESEARCH_FROM_ZERO",
        "SOURCE_CLAIM_MATRIX",
        "STORY_ARCHITECTURE",
        "ICONIC_CINEMATIC_REVIEW",
        "FINAL_SCRIPT",
        "PRONUNCIATION_AND_PERFORMANCE_GATE",
    }
    assert PAID_UPSTREAM_STAGES == expected
    assert set(WAVE3_CERTIFIED) == expected


def test_canonical_hash_is_stable():
    value = {"b": 2, "a": 1}
    assert canonical_sha256(value) == canonical_sha256({"a": 1, "b": 2})


def test_pronunciation_strong_audit_accepts_complete_marks():
    errors = validate_tts_segment(
        "قال آدم",
        "قَالَ آدَمُ",
        [],
    )
    assert errors == []


def test_pronunciation_strong_audit_rejects_partially_marked_word():
    errors = validate_tts_segment(
        "قال آدم",
        "قالَ آدَمُ",
        [],
    )
    assert any("BARE_MULTI_LETTER" in error for error in errors)


def test_pronunciation_strong_audit_accepts_definite_article_and_long_vowels():
    errors = validate_tts_segment(
        "في الإنسان",
        "فِي الْإِنْسَانِ",
        [],
    )
    assert errors == []


def test_pronunciation_strong_audit_rejects_internal_bare_consonant():
    errors = validate_tts_segment(
        "اسم",
        "اسمُ",
        [],
    )
    assert any("BARE_MULTI_LETTER" in error for error in errors)


def test_madda_is_self_vocalized_carrier():
    errors = validate_tts_segment(
        "آدم",
        "آدَمُ",
        [],
    )
    assert errors == []


def test_quran_disjoint_alias_supported():
    errors = validate_tts_segment(
        "طه",
        "طَا هَا",
        [
            {
                "source_form": "طه",
                "spoken_form": "طا ها",
                "reason": "QURAN_DISJOINT_LETTERS",
            }
        ],
    )
    assert errors == []
