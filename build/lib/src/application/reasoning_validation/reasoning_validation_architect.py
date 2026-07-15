from hashlib import sha256
import json

from .models import ReasoningValidationPlan


class ReasoningValidationArchitect:
    REQUIRED_CHECKS = (
        "EVIDENCE_COMPLETENESS",
        "REFERENCE_INTEGRITY",
        "TIMELINE_CONSISTENCY",
        "GRAPH_CONSISTENCY",
        "CONTRADICTION_CONFLICTS",
    )

    def build_validation_plan(self):
        checks = list(self.REQUIRED_CHECKS)
        plan = ReasoningValidationPlan(
            plan_id=self._id("reasoning_validation_plan", checks),
            required_checks=checks,
        )
        if not self.validate_plan(plan):
            raise ValueError("Invalid reasoning validation plan")
        return plan

    def validate_plan(self, plan):
        return (
            isinstance(plan, ReasoningValidationPlan)
            and bool(plan.plan_id)
            and plan.required_checks == list(self.REQUIRED_CHECKS)
            and len(plan.required_checks) == len(set(plan.required_checks))
        )

    @staticmethod
    def _id(prefix, material):
        return prefix + "_" + sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]


__all__ = ["ReasoningValidationArchitect"]
