from hashlib import sha256
import json

from src.application.claim_extraction.claim_extraction_runtime import (
    ClaimExtractionRuntime,
)
from src.application.claim_extraction.models import ClaimExtractionResult
from src.application.entity_extraction.entity_extraction_runtime import (
    EntityExtractionRuntime,
)
from src.application.entity_extraction.models import EntityExtractionResult

from .models import EventExtractionPlan


class EventExtractionArchitect:
    """Defines deterministic event extraction policies without extraction."""

    EXTRACTION_STRATEGIES = (
        "METADATA_EVENT",
        "CLAIM_PATTERN_EVENT",
        "ENTITY_DERIVED_EVENT",
    )
    EVENT_TYPES = (
        "CREATION_EVENT",
        "PUBLICATION_EVENT",
        "ORGANIZATION_EVENT",
        "LOCATION_EVENT",
        "DATE_EVENT",
    )
    VALIDATION_RULES = (
        "NON_EMPTY_EVENTS",
        "VALID_EVENT_TYPE",
        "EVIDENCE_REQUIRED",
        "SOURCE_REFERENCE_REQUIRED",
        "COUNT_CONSISTENCY",
    )

    def __init__(self, claim_extraction_runtime, entity_extraction_runtime):
        if not isinstance(claim_extraction_runtime, ClaimExtractionRuntime):
            raise TypeError(
                "EventExtractionArchitect requires a ClaimExtractionRuntime"
            )
        if not isinstance(entity_extraction_runtime, EntityExtractionRuntime):
            raise TypeError(
                "EventExtractionArchitect requires an EntityExtractionRuntime"
            )
        self.claim_extraction_runtime = claim_extraction_runtime
        self.entity_extraction_runtime = entity_extraction_runtime

    def build_event_extraction_plan(
        self,
        claim_extraction_result=None,
        entity_extraction_result=None,
        extraction_strategies=None,
        event_limit=100,
    ):
        claim_result_id = (
            claim_extraction_result.result_id
            if isinstance(claim_extraction_result, ClaimExtractionResult)
            else "default_claim_extraction"
        )
        entity_result_id = (
            entity_extraction_result.result_id
            if isinstance(entity_extraction_result, EntityExtractionResult)
            else "default_entity_extraction"
        )
        strategies = list(
            self.EXTRACTION_STRATEGIES
            if extraction_strategies is None
            else extraction_strategies
        )
        material = {
            "claim_extraction_result_id": claim_result_id,
            "entity_extraction_result_id": entity_result_id,
            "strategies": strategies,
            "event_limit": event_limit,
            "validation_rules": list(self.VALIDATION_RULES),
        }
        plan_id = (
            f"event_extraction_plan_"
            f"{sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )
        plan = EventExtractionPlan(
            plan_id=plan_id,
            claim_extraction_result_id=claim_result_id,
            entity_extraction_result_id=entity_result_id,
            extraction_strategies=strategies,
            event_limit=event_limit,
            validation_rules=list(self.VALIDATION_RULES),
        )
        if not self.validate_plan(plan):
            raise ValueError("Invalid event extraction plan")
        return plan

    def validate_plan(self, plan):
        if not isinstance(plan, EventExtractionPlan):
            return False
        if not plan.plan_id or not plan.claim_extraction_result_id or not plan.entity_extraction_result_id:
            return False
        if not isinstance(plan.extraction_strategies, list) or not plan.extraction_strategies:
            return False
        if len(plan.extraction_strategies) != len(set(plan.extraction_strategies)):
            return False
        if any(strategy not in self.EXTRACTION_STRATEGIES for strategy in plan.extraction_strategies):
            return False
        if not isinstance(plan.event_limit, int) or isinstance(plan.event_limit, bool):
            return False
        if plan.event_limit <= 0:
            return False
        return plan.validation_rules == list(self.VALIDATION_RULES)


__all__ = ["EventExtractionArchitect"]
