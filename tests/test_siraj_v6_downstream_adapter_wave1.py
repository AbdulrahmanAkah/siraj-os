from src.application.siraj_prompt_duplicate_gate_v6_1 import validate_prompt_similarity
from src.application.siraj_series_autopilot_adapter_certification_v6_1 import CERTIFIED

def test_duplicate_gate():
    assert validate_prompt_similarity([{"prompt":"ancient desert dawn"},{"prompt":"underwater city night"}])==[]

def test_wave1_certifies_seven_downstream_stages():
    assert len(CERTIFIED)==7
    assert "AUDIO_TIMESTAMPS_AND_BEATS" in CERTIFIED
    assert "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA" in CERTIFIED
    assert "PROVIDER_EXECUTION" not in CERTIFIED
