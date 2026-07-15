from src.application.documentary_intelligence import CANONICAL_CREATED_AT,canonical_trace,deterministic_id
from .models import VisualEvidencePolicy
class VisualEvidenceArchitect:
 TYPES=("EVENT_VISUALIZED_BY","CLAIM_SUPPORTED_BY_VISUAL","ENTITY_APPEARS_IN_VISUAL")
 def build_visual_evidence_policy(self): return VisualEvidencePolicy(deterministic_id("visual_evidence_policy",self.TYPES),CANONICAL_CREATED_AT,0,canonical_trace())
 def validate_policy(self,p): return isinstance(p,VisualEvidencePolicy) and p.created_at==CANONICAL_CREATED_AT
