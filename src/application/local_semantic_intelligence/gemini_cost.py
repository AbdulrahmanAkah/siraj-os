"""Versioned, opt-in Gemini usage cost estimation; provider never guesses prices."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


GEMINI_COST_SCHEMA_VERSION = "siraj-gemini-cost-table-v1"


def estimate_gemini_cost(
    *,
    model_reference: str,
    usage: dict[str, Any],
    price_table: dict[str, Any] | None,
) -> dict[str, Any]:
    """Estimate only from an explicit versioned price-table entry."""

    if not price_table or price_table.get("schema_version") != GEMINI_COST_SCHEMA_VERSION:
        return {"cost_status": "UNKNOWN", "reason_code": "PRICE_TABLE_NOT_CONFIGURED"}
    price = price_table.get("models", {}).get(model_reference)
    if not isinstance(price, dict):
        return {"cost_status": "UNKNOWN", "reason_code": "MODEL_PRICE_NOT_CONFIGURED"}
    try:
        input_rate = Decimal(str(price["input_per_million"]))
        output_rate = Decimal(str(price["output_per_million"]))
        cached_rate = Decimal(str(price.get("cached_per_million", 0)))
        input_tokens = Decimal(str(int(usage.get("input_tokens", 0))))
        output_tokens = Decimal(str(int(usage.get("output_tokens", 0))))
        cached_tokens = Decimal(str(int(usage.get("cached_tokens", 0))))
    except (KeyError, ValueError, ArithmeticError):
        return {"cost_status": "UNKNOWN", "reason_code": "INVALID_PRICE_TABLE"}
    estimated = (input_tokens * input_rate + output_tokens * output_rate + cached_tokens * cached_rate) / Decimal("1000000")
    return {
        "cost_status": "ESTIMATED",
        "currency": str(price.get("currency", "USD")),
        "estimated_cost": format(estimated.quantize(Decimal("0.000001")), "f"),
        "price_table_version": GEMINI_COST_SCHEMA_VERSION,
    }


__all__ = ["GEMINI_COST_SCHEMA_VERSION", "estimate_gemini_cost"]
