from src.application.siraj_luna_runtime_policy_v5 import (
    DEFAULT_REASONING_EFFORT,
    DEFAULT_REASONING_MODE,
    apply_unbounded_request_policy,
)
from src.application.siraj_luna_iconic_cinematic_brain_v5_1 import (
    BRAIN_MARKER,
    apply_iconic_cinematic_brain,
    detect_stage,
)

def test_max_pro_runtime():
    req = {"model":"gpt-5.6-luna","max_output_tokens":123,
           "reasoning":{"effort":"high"},"input":[]}
    out = apply_unbounded_request_policy(req)
    assert DEFAULT_REASONING_EFFORT == "max"
    assert DEFAULT_REASONING_MODE == "pro"
    assert out["reasoning"] == {"effort":"max","mode":"pro"}
    assert "max_output_tokens" not in out

def test_creative_brain_injection():
    req = {"input":[{"role":"user","content":[{"type":"input_text",
           "text":"stage=FINAL_SCRIPT"}]}]}
    assert detect_stage(req) == "FINAL_SCRIPT"
    out = apply_iconic_cinematic_brain(req)
    assert BRAIN_MARKER in str(out["input"][0])

def test_truth_guard_stage():
    req = {"input":[{"role":"user","content":[{"type":"input_text",
           "text":"stage=SOURCE_CLAIM_MATRIX"}]}]}
    assert detect_stage(req) == "SOURCE_CLAIM_MATRIX"
    out = apply_iconic_cinematic_brain(req)
    assert "الدقة" in str(out["input"][0])
