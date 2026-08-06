from __future__ import annotations

from src.application.arabic_actual_stop_waqf_v2 import (
    process_block,
    strip_marks,
    waqf_word,
)


def test_pronoun_ha_stops_without_final_damma() -> None:
    assert waqf_word("مَنَعَهُ") == "مَنَعَهْ"


def test_fathatan_before_final_alif_becomes_long_pause_vowel() -> None:
    assert waqf_word("قَائِمًا") == "قَائِمَا"


def test_ta_marbuta_stops_with_sukun_without_base_change() -> None:
    before = "وَاحِدَةٍ"
    after = waqf_word(before)
    assert after == "وَاحِدَةْ"
    assert strip_marks(after) == strip_marks(before)


def test_incidental_comma_keeps_connected_reading() -> None:
    block = {
        "block_id": "VB-TEST-01",
        "tts_text_ar": "كَانَ يَرَى، وَيَفْهَمُ، ثُمَّ اخْتَارَ.",
        "pause_after_ms": 450,
    }
    processed, audit = process_block(block)
    assert "يَرَى،" in processed["tts_text_ar"]
    assert "يَفْهَمُ،" in processed["tts_text_ar"]
    assert audit["connected_comma_count"] == 2


def test_strong_clause_comma_uses_actual_stop() -> None:
    block = {
        "block_id": "VB-TEST-02",
        "tts_text_ar": (
            "لَمْ يَكُنِ الْعَجْزُ هُوَ مَا مَنَعَهُ، "
            "وَلَا غُمُوضُ الْأَمْرِ."
        ),
        "pause_after_ms": 450,
    }
    processed, audit = process_block(block)
    assert "مَنَعَهْ،" in processed["tts_text_ar"]
    assert any(
        event["stop_type"] == "STRONG_CLAUSE_COMMA"
        for event in audit["events"]
    )


def test_only_tts_base_letters_are_preserved() -> None:
    block = {
        "block_id": "VB-TEST-03",
        "tts_text_ar": "اِمْتِثَالٌ كَامِلٌ...",
        "pause_after_ms": 450,
    }
    processed, audit = process_block(block)
    assert strip_marks(processed["tts_text_ar"]) == strip_marks(
        block["tts_text_ar"]
    )
    assert audit["base_text_preserved"] is True
