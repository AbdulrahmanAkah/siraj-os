from hashlib import sha256
import json

from .models import NarrativeReasoningPlan


class NarrativeReasoningArchitect:
    ROLES = ("BEGINNING", "DEVELOPMENT", "TURNING_POINT", "OUTCOME")

    def build_narrative_reasoning_plan(self):
        roles = list(self.ROLES)
        return NarrativeReasoningPlan(
            plan_id="narrative_reasoning_plan_"
            + sha256(
                json.dumps(roles, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:16],
            narrative_roles=roles,
        )

    def validate_plan(self, plan):
        return (
            isinstance(plan, NarrativeReasoningPlan)
            and bool(plan.plan_id)
            and plan.narrative_roles == list(self.ROLES)
        )


__all__ = ["NarrativeReasoningArchitect"]
