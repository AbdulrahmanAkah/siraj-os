from src.application.documentary_intelligence import CANONICAL_CREATED_AT, canonical_trace, deterministic_id
from .models import DocumentaryScriptPolicy
class DocumentaryScriptArchitect:
    def build_script_policy(self): return DocumentaryScriptPolicy(deterministic_id("documentary_script_policy", ["EVIDENCE_REFERENCED"]), CANONICAL_CREATED_AT, 0, canonical_trace())
    def validate_policy(self, policy): return isinstance(policy, DocumentaryScriptPolicy) and policy.created_at == CANONICAL_CREATED_AT
