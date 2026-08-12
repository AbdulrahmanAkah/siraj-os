from __future__ import annotations
from copy import deepcopy
from typing import Any, Mapping

POLICY_VERSION = "siraj-luna-unbounded-adaptive-runtime-v5.1-max"
ASSISTANT_AUTHORED_MAX_LUNA_CALLS = None
ASSISTANT_AUTHORED_TOTAL_COST_CAP_USD = None
ASSISTANT_AUTHORED_TEXT_COST_CAP_USD = None
ASSISTANT_AUTHORED_TOOL_RESERVE_USD = None
ASSISTANT_AUTHORED_MAX_OUTPUT_TOKENS = None
ASSISTANT_AUTHORED_FIXED_PACING_SECONDS = None
DEFAULT_REASONING_EFFORT = "max"
DEFAULT_REASONING_MODE = "pro"
AUTOMATIC_PAID_RETRY = False

class LunaRuntimePolicyError(RuntimeError):
    pass

def validate_paid_authorization(auth: Mapping[str, Any]) -> dict[str, Any]:
    if auth.get("status") != "ACTIVE":
        raise LunaRuntimePolicyError("PAID_AUTHORIZATION_NOT_ACTIVE")
    if auth.get("automatic_retry") not in (False, None):
        raise LunaRuntimePolicyError("AUTOMATIC_PAID_RETRY_FORBIDDEN")
    source = str(auth.get("authorization_source") or "")
    if not source:
        raise LunaRuntimePolicyError("AUTHORIZATION_SOURCE_REQUIRED")
    return {
        "status": "ACTIVE",
        "authorization_source": source,
        "user_maximum_total_cost_usd": auth.get("maximum_total_session_cost_usd"),
        "user_maximum_calls": auth.get("maximum_luna_calls"),
        "automatic_retry": False,
    }

def apply_unbounded_request_policy(
    request: Mapping[str, Any],
) -> dict[str, Any]:
    result = deepcopy(dict(request))
    result.pop("max_output_tokens", None)
    reasoning = result.get("reasoning")
    if not isinstance(reasoning, dict):
        reasoning = {}
        result["reasoning"] = reasoning
    reasoning["effort"] = DEFAULT_REASONING_EFFORT
    reasoning["mode"] = DEFAULT_REASONING_MODE
    return result

def is_user_limit(value: Any) -> bool:
    return value is not None
