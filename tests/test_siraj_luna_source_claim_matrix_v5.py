from pathlib import Path

from src.application.siraj_luna_source_claim_matrix_v5 import (
    _schema,
    _validate_strict_schema,
)


def test_source_claim_matrix_schema_is_openai_strict():
    schema = _schema()
    _validate_strict_schema(schema)
    assert schema["additionalProperties"] is False


def test_source_claim_matrix_has_no_assistant_output_or_count_cap():
    text = Path(
        "src/application/siraj_luna_source_claim_matrix_v5.py"
    ).read_text(encoding="utf-8-sig")
    assert '"max_output_tokens"' not in text
    assert "MAX_LUNA_CALLS" not in text
    assert "TOTAL_CAP_USD" not in text
    assert "TEXT_CAP_USD" not in text
    assert "time.sleep(" not in text
