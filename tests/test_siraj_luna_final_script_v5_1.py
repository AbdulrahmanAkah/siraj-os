from pathlib import Path

from src.application.siraj_luna_final_script_v5_1 import (
    REUSABLE_CTA,
    _request,
    _schema,
    _validate_strict_schema,
)


def test_final_script_schema_is_openai_strict():
    schema = _schema()
    _validate_strict_schema(schema)
    assert schema["additionalProperties"] is False


def test_final_script_request_is_max_pro_without_output_cap():
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


def test_final_script_has_no_fixed_duration_word_or_segment_count():
    text = Path(
        "src/application/siraj_luna_final_script_v5_1.py"
    ).read_text(encoding="utf-8-sig")
    assert "TARGET_DURATION_SECONDS" not in text
    assert "TARGET_WORD_COUNT" not in text
    assert "EXPECTED_SEGMENT_COUNT" not in text
    assert "MAX_LUNA_CALLS" not in text
    assert "time.sleep(" not in text


def test_reusable_outro_cta_is_explicitly_excluded():
    assert REUSABLE_CTA == (
        "إذا أعجبك هذا المحتوى، اشترك في سراج، وتابع معنا بقية الرحلة."
    )
    text = Path(
        "src/application/siraj_luna_final_script_v5_1.py"
    ).read_text(encoding="utf-8-sig")
    assert "REUSABLE_CTA_OUTRO=EXCLUDED_FROM_SCRIPT" in text


def test_deliberate_editorial_iteration_supported_without_auto_retry():
    text = Path(
        "src/application/siraj_luna_final_script_v5_1.py"
    ).read_text(encoding="utf-8-sig")
    assert "CONTINUE_SCRIPT" in text
    assert "while True:" in text
    assert "AUTOMATIC_PROVIDER_RETRIES=0" in text
