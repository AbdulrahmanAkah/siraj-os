from src.application.documentary_intelligence import (
    CANONICAL_CREATED_AT,
    canonical_trace,
    deterministic_id,
)

from .models import DocumentaryPlanningPolicy


class DocumentaryPlanningArchitectV2:
    CHAPTER_ROLES = (
        "OPENING",
        "CONTEXT",
        "DEVELOPMENT",
        "TURNING_POINT",
        "OUTCOME",
    )

    def build_documentary_planning_policy(self):
        roles = list(self.CHAPTER_ROLES)
        policy = DocumentaryPlanningPolicy(
            policy_id=deterministic_id("documentary_planning_policy_v2", roles),
            allowed_chapter_roles=roles,
            created_at=CANONICAL_CREATED_AT,
            position=0,
            trace_metadata=canonical_trace(),
        )
        if not self.validate_policy(policy):
            raise ValueError("Invalid documentary planning policy")
        return policy

    def validate_policy(self, policy):
        return (
            isinstance(policy, DocumentaryPlanningPolicy)
            and policy.allowed_chapter_roles == list(self.CHAPTER_ROLES)
            and policy.created_at == CANONICAL_CREATED_AT
            and policy.position == 0
            and bool(policy.policy_id)
        )


__all__ = ["DocumentaryPlanningArchitectV2"]
