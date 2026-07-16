from hashlib import sha256
import json

from .models import EvidenceResolutionPlan


class EvidenceResolutionArchitect:
    """Defines deterministic evidence-resolution policy without resolution."""

    SOURCE_TYPES = (
        "CLAIM",
        "ENTITY",
        "EVENT",
        "GRAPH_EDGE",
        "TIMELINE_ENTRY",
    )
    VALIDATION_LEVELS = ("STRICT", "STANDARD", "BASIC")

    def build_resolution_plan(
        self,
        allowed_source_types=None,
        validation_level="STANDARD",
    ):
        source_types = list(self.SOURCE_TYPES if allowed_source_types is None else allowed_source_types)
        material = {
            "allowed_source_types": source_types,
            "validation_level": validation_level,
        }
        plan = EvidenceResolutionPlan(
            plan_id="evidence_resolution_plan_"
            + sha256(
                json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:16],
            allowed_source_types=source_types,
            validation_level=validation_level,
        )
        if not self.validate_resolution_plan(plan):
            raise ValueError("Invalid evidence resolution plan")
        return plan

    def validate_resolution_plan(self, plan):
        return (
            isinstance(plan, EvidenceResolutionPlan)
            and bool(plan.plan_id)
            and isinstance(plan.allowed_source_types, list)
            and bool(plan.allowed_source_types)
            and len(plan.allowed_source_types) == len(set(plan.allowed_source_types))
            and all(source_type in self.SOURCE_TYPES for source_type in plan.allowed_source_types)
            and plan.validation_level in self.VALIDATION_LEVELS
        )

    validate_plan = validate_resolution_plan


__all__ = ["EvidenceResolutionArchitect"]
