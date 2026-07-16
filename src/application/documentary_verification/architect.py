from src.application.documentary_intelligence import CANONICAL_CREATED_AT,canonical_trace,deterministic_id
from .models import DocumentaryVerificationPolicy
class DocumentaryVerificationArchitect:
 CHECKS=("COVERAGE_COMPLETENESS","EVIDENCE_INTEGRITY","REFERENCE_INTEGRITY","ATTRIBUTION_COMPLETENESS","TIMELINE_CONSISTENCY","REASONING_CONSISTENCY")
 def build_verification_policy(self):return DocumentaryVerificationPolicy(deterministic_id("verification_policy",self.CHECKS),list(self.CHECKS),CANONICAL_CREATED_AT,0,canonical_trace())
 def validate_policy(self,p):return isinstance(p,DocumentaryVerificationPolicy) and p.checks==list(self.CHECKS)
