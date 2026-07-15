import hashlib, json
from .models import CorrelationPlan

class MultiSourceCorrelationArchitect:
    TYPES = ("CLAIM", "ENTITY", "EVENT")
    def build_correlation_plan(self, allowed_correlation_types=None):
        types = list(self.TYPES if allowed_correlation_types is None else allowed_correlation_types)
        if not types or len(types) != len(set(types)) or any(item not in self.TYPES for item in types): raise ValueError("Invalid correlation types")
        plan_id = "correlation_plan_" + hashlib.sha256(json.dumps(types, separators=(",", ":")).encode()).hexdigest()[:16]
        return CorrelationPlan(plan_id, types)
    def validate_plan(self, plan):
        return isinstance(plan, CorrelationPlan) and bool(plan.plan_id) and bool(plan.allowed_correlation_types) and len(plan.allowed_correlation_types) == len(set(plan.allowed_correlation_types)) and all(item in self.TYPES for item in plan.allowed_correlation_types)
