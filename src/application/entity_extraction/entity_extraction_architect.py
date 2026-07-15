from hashlib import sha256
import json

from src.application.claim_extraction.claim_extraction_runtime import (
    ClaimExtractionRuntime,
)
from src.application.claim_extraction.models import ClaimExtractionResult

from .models import EntityExtractionPlan


class EntityExtractionArchitect:
    """Defines deterministic entity extraction policies without extraction."""

    EXTRACTION_STRATEGIES = (
        "STRUCTURED_METADATA_ENTITY",
        "CLAIM_PATTERN_ENTITY",
        "TITLE_ENTITY",
    )
    ENTITY_TYPES = (
        "PERSON",
        "ORGANIZATION",
        "LOCATION",
        "DATE",
        "WORK",
    )
    VALIDATION_RULES = (
        "NON_EMPTY_ENTITIES",
        "UNIQUE_ENTITIES",
        "VALID_ENTITY_TYPE",
        "EVIDENCE_REQUIRED",
        "SOURCE_CLAIM_REQUIRED",
        "COUNT_CONSISTENCY",
    )

    def __init__(self, claim_extraction_runtime):
        if not isinstance(claim_extraction_runtime, ClaimExtractionRuntime):
            raise TypeError(
                "EntityExtractionArchitect requires a ClaimExtractionRuntime"
            )
        self.claim_extraction_runtime = claim_extraction_runtime

    def build_entity_extraction_plan(
        self,
        claim_extraction_result=None,
        extraction_strategies=None,
        entity_limit=100,
    ):
        result_id = (
            claim_extraction_result.result_id
            if isinstance(claim_extraction_result, ClaimExtractionResult)
            else "default_claim_extraction"
        )
        strategies = list(
            self.EXTRACTION_STRATEGIES
            if extraction_strategies is None
            else extraction_strategies
        )
        material = {
            "claim_extraction_result_id": result_id,
            "strategies": strategies,
            "entity_limit": entity_limit,
            "validation_rules": list(self.VALIDATION_RULES),
        }
        plan_id = (
            f"entity_extraction_plan_"
            f"{sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )
        plan = EntityExtractionPlan(
            plan_id=plan_id,
            claim_extraction_result_id=result_id,
            extraction_strategies=strategies,
            entity_limit=entity_limit,
            validation_rules=list(self.VALIDATION_RULES),
        )
        if not self.validate_plan(plan):
            raise ValueError("Invalid entity extraction plan")
        return plan

    def validate_plan(self, plan):
        if not isinstance(plan, EntityExtractionPlan):
            return False
        if not isinstance(plan.plan_id, str) or not plan.plan_id:
            return False
        if not isinstance(plan.claim_extraction_result_id, str) or not plan.claim_extraction_result_id:
            return False
        if not isinstance(plan.extraction_strategies, list) or not plan.extraction_strategies:
            return False
        if len(plan.extraction_strategies) != len(set(plan.extraction_strategies)):
            return False
        if any(strategy not in self.EXTRACTION_STRATEGIES for strategy in plan.extraction_strategies):
            return False
        if not isinstance(plan.entity_limit, int) or isinstance(plan.entity_limit, bool):
            return False
        if plan.entity_limit <= 0:
            return False
        return plan.validation_rules == list(self.VALIDATION_RULES)


__all__ = ["EntityExtractionArchitect"]
