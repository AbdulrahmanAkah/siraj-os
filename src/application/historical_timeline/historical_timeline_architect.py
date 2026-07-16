from hashlib import sha256
import json

from src.application.event_extraction.event_extraction_runtime import (
    EventExtractionRuntime,
)
from src.application.relationship_graph.relationship_graph_runtime import (
    RelationshipGraphRuntime,
)

from .models import TimelinePlan


class HistoricalTimelineArchitect:
    """Defines deterministic timeline policy without building a timeline."""

    VALIDATION_LEVELS = ("STRICT", "STANDARD", "BASIC")

    def __init__(self, event_extraction_runtime, relationship_graph_runtime):
        if not isinstance(event_extraction_runtime, EventExtractionRuntime):
            raise TypeError(
                "HistoricalTimelineArchitect requires an EventExtractionRuntime"
            )
        if not isinstance(relationship_graph_runtime, RelationshipGraphRuntime):
            raise TypeError(
                "HistoricalTimelineArchitect requires a RelationshipGraphRuntime"
            )
        self.event_extraction_runtime = event_extraction_runtime
        self.relationship_graph_runtime = relationship_graph_runtime

    def build_timeline_plan(
        self,
        allowed_event_types=None,
        include_undated_events=True,
        validation_level="STANDARD",
    ):
        allowed_types = list(allowed_event_types or [])
        material = {
            "allowed_event_types": allowed_types,
            "include_undated_events": include_undated_events,
            "validation_level": validation_level,
        }
        plan_id = (
            "historical_timeline_plan_"
            f"{sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )
        plan = TimelinePlan(
            plan_id=plan_id,
            allowed_event_types=allowed_types,
            include_undated_events=include_undated_events,
            validation_level=validation_level,
        )
        if not self.validate_timeline_plan(plan):
            raise ValueError("Invalid timeline plan")
        return plan

    def validate_timeline_plan(self, plan):
        if not isinstance(plan, TimelinePlan) or not plan.plan_id:
            return False
        if not isinstance(plan.allowed_event_types, list):
            return False
        if len(plan.allowed_event_types) != len(set(plan.allowed_event_types)):
            return False
        if not isinstance(plan.include_undated_events, bool):
            return False
        return plan.validation_level in self.VALIDATION_LEVELS

    validate_plan = validate_timeline_plan


__all__ = ["HistoricalTimelineArchitect"]
