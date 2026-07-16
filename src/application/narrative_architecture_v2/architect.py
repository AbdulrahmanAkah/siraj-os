from src.application.documentary_intelligence import CANONICAL_CREATED_AT, canonical_trace, deterministic_id
from .models import NarrativeArchitecturePolicy

class NarrativeArchitectureArchitectV2:
    ROLES = ("OPENING", "CONTEXT", "ESCALATION", "TURNING_POINT", "RESOLUTION", "LEGACY")
    def build_narrative_policy(self):
        roles = list(self.ROLES)
        return NarrativeArchitecturePolicy(deterministic_id("narrative_policy_v2", roles), roles, CANONICAL_CREATED_AT, 0, canonical_trace())
    def validate_policy(self, policy):
        return isinstance(policy, NarrativeArchitecturePolicy) and policy.roles == list(self.ROLES) and policy.created_at == CANONICAL_CREATED_AT
