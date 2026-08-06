from __future__ import annotations

from src.application.arabic_actual_stop_waqf_v3 import (
    phonetic_waqf_word,
    process_block,
)


def test_pronoun_ha_stops_without_final_damma() -> None:
    assert phonetic_waqf_word("مَنَعَهُ")[0] == "مَنَعَهْ"


def test_ta_marbuta_is_phonetic_haa_at_actual_stop() -> None:
    value, substitution = phonetic_waqf_word("وَاحِدَةٍ")
    assert value == "وَاحِدَهْ"
    assert substitution == "TA_MARBUTA_TO_HAA_AT_WAQF"


def test_fathatan_before_final_alif_becomes_long_pause() -> None:
    assert phonetic_waqf_word("قَائِمًا")[0] == "قَائِمَا"


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


def test_connector_alone_does_not_create_comma_stop() -> None:
    block = {
        "block_id": "VB-TEST-02",
        "tts_text_ar": "مَا مَنَعَهُ، وَلَا شَيْءٌ آخَرُ.",
        "pause_after_ms": 450,
    }
    processed, audit = process_block(block)
    assert "مَنَعَهُ، وَلَا" in processed["tts_text_ar"]
    assert audit["manual_comma_stop_count"] == 0


def test_user_confirmed_sample_comma_stop_is_narrow() -> None:
    block = {
        "block_id": "VB-001-01",
        "tts_text_ar": (
            "لَمْ يَكُنِ الْعَجْزُ هُوَ مَا مَنَعَهُ، "
            "وَلَا غُمُوضُ الْأَمْرِ."
        ),
        "pause_after_ms": 450,
    }
    processed, audit = process_block(block)
    assert "مَنَعَهْ، وَلَا" in processed["tts_text_ar"]
    assert audit["manual_comma_stop_count"] == 1


def test_hard_sentence_stop_is_applied() -> None:
    block = {
        "block_id": "VB-TEST-03",
        "tts_text_ar": "وَلَا غُمُوضُ الْأَمْرِ.",
        "pause_after_ms": 200,
    }
    processed, _ = process_block(block)
    assert "الْأَمْرْ." in processed["tts_text_ar"]
