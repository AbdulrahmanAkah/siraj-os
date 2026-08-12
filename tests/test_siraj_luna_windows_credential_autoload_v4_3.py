
from pathlib import Path

def test_runner_contains_windows_credential_autoload():
    text = Path(
        "src/application/siraj_luna_research_session_v4.py"
    ).read_text(encoding="utf-8-sig")
    assert "def _load_openai_api_key()" in text
    assert 'target = "SIRAJ/OPENAI_API_KEY"' in text
    assert 'api_key, api_key_source = _load_openai_api_key()' in text
    assert 'OPENAI_KEY_SOURCE=' in text
