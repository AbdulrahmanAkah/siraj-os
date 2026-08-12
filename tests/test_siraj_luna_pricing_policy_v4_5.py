
import json
from pathlib import Path

from src.application import openai_luna_orchestrator_v1 as luna

def test_luna_base_rates_are_series_locked():
    assert luna.LUNA_INPUT_USD_PER_MILLION == 0.20
    assert luna.LUNA_OUTPUT_USD_PER_MILLION == 1.20

def test_luna_automatic_transient_retries_are_disabled():
    assert luna.MAX_TRANSIENT_RETRIES == 0

def test_series_pricing_policy_records_long_context_doubling():
    policy = json.loads(
        Path("projects/_series/siraj-luna-pricing-policy-v4.json")
        .read_text(encoding="utf-8-sig")
    )
    assert policy["base_input_usd_per_million"] == 0.20
    assert policy["base_output_usd_per_million"] == 1.20
    assert policy["long_context_multiplier"] == 2.0
    assert policy["long_context_threshold_tokens"] is None
    assert policy["threshold_policy"] == "DO_NOT_GUESS_REQUIRE_OFFICIAL_THRESHOLD_BEFORE_ENFORCEMENT"
