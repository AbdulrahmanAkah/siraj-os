from hashlib import sha256
import json

from .models import CausalReasoningPlan


class CausalReasoningArchitect:
    RELATION_TYPES = ("CAUSES", "CONTRIBUTES_TO", "PRECEDES_CAUSE")

    def build_causal_plan(self, allowed_relation_types=None):
        relation_types = list(
            self.RELATION_TYPES
            if allowed_relation_types is None
            else allowed_relation_types
        )
        material = {"allowed_relation_types": relation_types}
        plan = CausalReasoningPlan(
            plan_id="causal_reasoning_plan_"
            + sha256(
                json.dumps(material, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                )
            ).hexdigest()[:16],
            allowed_relation_types=relation_types,
        )
        if not self.validate_plan(plan):
            raise ValueError("Invalid causal reasoning plan")
        return plan

    def validate_plan(self, plan):
        return (
            isinstance(plan, CausalReasoningPlan)
            and bool(plan.plan_id)
            and bool(plan.allowed_relation_types)
            and len(plan.allowed_relation_types) == len(set(plan.allowed_relation_types))
            and all(item in self.RELATION_TYPES for item in plan.allowed_relation_types)
        )


__all__ = ["CausalReasoningArchitect"]
