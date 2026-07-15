from hashlib import sha256
import json

from src.application.retrieval.models import RetrievalResult
from src.application.retrieval.retrieval_runtime_engine import (
    RetrievalRuntimeEngine,
)

from .models import ClaimExtractionPlan


class ClaimExtractionArchitect:
    """Defines deterministic claim extraction policies without extracting claims."""

    EXTRACTION_STRATEGIES = (
        "EXPLICIT_STATEMENT",
        "STRUCTURED_METADATA",
        "TITLE_DERIVED",
    )
    VALIDATION_RULES = (
        "NON_EMPTY_CLAIMS",
        "UNIQUE_CLAIMS",
        "EVIDENCE_REQUIRED",
        "COUNT_CONSISTENCY",
    )

    def __init__(self, retrieval_runtime_engine):
        if not isinstance(retrieval_runtime_engine, RetrievalRuntimeEngine):
            raise TypeError(
                "ClaimExtractionArchitect requires a RetrievalRuntimeEngine"
            )
        self.retrieval_runtime_engine = retrieval_runtime_engine

    def build_claim_extraction_plan(
        self,
        retrieval_result=None,
        extraction_strategies=None,
        claim_limit=100,
    ):
        retrieval_id = (
            retrieval_result.retrieval_id
            if isinstance(retrieval_result, RetrievalResult)
            else "default_retrieval"
        )
        strategies = list(
            self.EXTRACTION_STRATEGIES
            if extraction_strategies is None
            else extraction_strategies
        )
        plan_material = {
            "retrieval_id": retrieval_id,
            "strategies": strategies,
            "claim_limit": claim_limit,
            "validation_rules": list(self.VALIDATION_RULES),
        }
        plan_id = (
            f"claim_extraction_plan_"
            f"{sha256(json.dumps(plan_material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )
        plan = ClaimExtractionPlan(
            plan_id=plan_id,
            retrieval_id=retrieval_id,
            extraction_strategies=strategies,
            claim_limit=claim_limit,
            validation_rules=list(self.VALIDATION_RULES),
        )
        if not self.validate_plan(plan):
            raise ValueError("Invalid claim extraction plan")
        return plan

    def validate_plan(self, plan):
        if not isinstance(plan, ClaimExtractionPlan):
            return False
        if not isinstance(plan.plan_id, str) or not plan.plan_id:
            return False
        if not isinstance(plan.retrieval_id, str) or not plan.retrieval_id:
            return False
        if not isinstance(plan.extraction_strategies, list):
            return False
        if not plan.extraction_strategies:
            return False
        if len(plan.extraction_strategies) != len(
            set(plan.extraction_strategies)
        ):
            return False
        if any(
            strategy not in self.EXTRACTION_STRATEGIES
            for strategy in plan.extraction_strategies
        ):
            return False
        if not isinstance(plan.claim_limit, int) or isinstance(plan.claim_limit, bool):
            return False
        if plan.claim_limit <= 0:
            return False
        if plan.validation_rules != list(self.VALIDATION_RULES):
            return False
        return True


__all__ = ["ClaimExtractionArchitect"]
