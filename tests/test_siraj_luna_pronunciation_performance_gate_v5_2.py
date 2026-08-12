from pathlib import Path

from src.application.siraj_luna_pronunciation_performance_gate_v5_2 import (
    HOOK_MIN_PAUSE_SECONDS,
    PRE_OUTRO_MIN_PAUSE_SECONDS,
    REUSABLE_CTA,
    _lexical_skeleton,
    _request,
    _schema,
    _validate_strict_schema,
)


def test_schema_is_strict():
    schema = _schema()
    _validate_strict_schema(schema)
    assert schema["additionalProperties"] is False


def test_request_is_max_pro_without_output_cap():
    request = _request(
        {"status": "PASS"},
        {"status": "PASS"},
        {"status": "PASS"},
        None,
        1,
    )
    assert request["reasoning"]["effort"] == "max"
    assert request["reasoning"]["mode"] == "pro"
    assert "max_output_tokens" not in request


def test_diacritics_and_punctuation_do_not_change_lexical_skeleton():
    assert _lexical_skeleton("آدَمُ، عليه السلام.") == _lexical_skeleton(
        "ادم عليه السلام"
    )


def test_project_pause_floors_are_preserved():
    assert HOOK_MIN_PAUSE_SECONDS == 0.6
    assert PRE_OUTRO_MIN_PAUSE_SECONDS == 0.4


def test_gate_makes_no_tts_provider_call():
    text = Path(
        "src/application/siraj_luna_pronunciation_performance_gate_v5_2.py"
    ).read_text(encoding="utf-8-sig")
    assert "TTS_PROVIDER_CALLS=0" in text
    assert "elevenlabs" not in text.lower()
    assert "runware" not in text.lower()


def test_cta_remains_separate():
    assert REUSABLE_CTA == (
        "إذا أعجبك هذا المحتوى، اشترك في سراج، وتابع معنا بقية الرحلة."
    )


def test_internal_madda_preserves_hamza_for_lexical_equivalence():
    assert _lexical_skeleton("السوءات") == _lexical_skeleton("السَّوْآتِ")


def test_word_initial_madda_accepts_legacy_bare_alif():
    assert _lexical_skeleton("آدَمُ، عليه السلام.") == _lexical_skeleton("ادم عليه السلام")
