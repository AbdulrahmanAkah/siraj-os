from hashlib import sha256
import json

from .models import HistoricalReasoningPlan


class HistoricalReasoningArchitect:
    VALIDATION_RULES = (
        "EVIDENCE_REQUIRED",
        "GRAPH_NODE_REQUIRED",
        "SOURCE_REFERENCE_REQUIRED",
        "STABLE_ORDERING",
        "COUNT_CONSISTENCY",
    )

    def build_reasoning_plan(self):
        rules = list(self.VALIDATION_RULES)
        plan_id = "historical_reasoning_plan_" + sha256(
            json.dumps(rules, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        return HistoricalReasoningPlan(plan_id=plan_id, validation_rules=rules)

    def validate_plan(self, plan):
        return (
            isinstance(plan, HistoricalReasoningPlan)
            and bool(plan.plan_id)
            and plan.validation_rules == list(self.VALIDATION_RULES)
        )


__all__ = ["HistoricalReasoningArchitect"]
