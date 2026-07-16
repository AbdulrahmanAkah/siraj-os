from hashlib import sha256
import json

from .models import HistoricalInterpretationPlan


class HistoricalInterpretationArchitect:
    VALIDATION_RULES = (
        "REASONING_CHAIN_REQUIRED",
        "EVIDENCE_REQUIRED",
        "SOURCE_TRACE_REQUIRED",
        "STABLE_ORDERING",
        "COUNT_CONSISTENCY",
    )

    def build_interpretation_plan(self):
        rules = list(self.VALIDATION_RULES)
        return HistoricalInterpretationPlan(
            plan_id="historical_interpretation_plan_"
            + sha256(
                json.dumps(rules, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:16],
            validation_rules=rules,
        )

    def validate_plan(self, plan):
        return (
            isinstance(plan, HistoricalInterpretationPlan)
            and bool(plan.plan_id)
            and plan.validation_rules == list(self.VALIDATION_RULES)
        )


__all__ = ["HistoricalInterpretationArchitect"]
