import json
from pathlib import Path

from src.application.siraj_luna_runtime_policy_v5 import (
    ASSISTANT_AUTHORED_FIXED_PACING_SECONDS,
    ASSISTANT_AUTHORED_MAX_LUNA_CALLS,
    ASSISTANT_AUTHORED_MAX_OUTPUT_TOKENS,
    ASSISTANT_AUTHORED_TEXT_COST_CAP_USD,
    ASSISTANT_AUTHORED_TOOL_RESERVE_USD,
    ASSISTANT_AUTHORED_TOTAL_COST_CAP_USD,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_REASONING_MODE,
    apply_unbounded_request_policy,
)


def test_no_assistant_authored_hard_limits():
    assert ASSISTANT_AUTHORED_MAX_LUNA_CALLS is None
    assert ASSISTANT_AUTHORED_TOTAL_COST_CAP_USD is None
    assert ASSISTANT_AUTHORED_TEXT_COST_CAP_USD is None
    assert ASSISTANT_AUTHORED_TOOL_RESERVE_USD is None
    assert ASSISTANT_AUTHORED_MAX_OUTPUT_TOKENS is None
    assert ASSISTANT_AUTHORED_FIXED_PACING_SECONDS is None


def test_request_policy_removes_output_cap_and_uses_max_pro_reasoning():
    request = {
        "model": "gpt-5.6-luna",
        "max_output_tokens": 20000,
        "reasoning": {"effort": "medium"},
    }
    result = apply_unbounded_request_policy(request)
    assert "max_output_tokens" not in result
    assert result["reasoning"]["effort"] == DEFAULT_REASONING_EFFORT == "max"
    assert result["reasoning"]["mode"] == DEFAULT_REASONING_MODE == "pro"


def test_series_policy_is_active_and_unbounded():
    value = json.loads(
        Path(
            "projects/_series/siraj-luna-unbounded-adaptive-runtime-v5.json"
        ).read_text(encoding="utf-8")
    )
    assert value["status"] == "ACTIVE"
    p = value["policy"]
    assert p["luna_call_count_limit"] is None
    assert p["assistant_authored_cost_cap_usd"] is None
    assert p["assistant_authored_max_output_tokens"] is None
    assert p["assistant_authored_fixed_pacing_seconds"] is None
    assert p["automatic_paid_retry"] is False
    assert p["paid_execution_requires_explicit_human_authorization"] is True
