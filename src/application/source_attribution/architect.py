from src.application.documentary_intelligence import CANONICAL_CREATED_AT,canonical_trace,deterministic_id
from .models import AttributionPolicy
class SourceAttributionArchitect:
 def build_attribution_policy(self):return AttributionPolicy(deterministic_id("attribution_policy",["ALL_VISUALS_ATTRIBUTED"]),CANONICAL_CREATED_AT,0,canonical_trace())
 def validate_policy(self,p):return isinstance(p,AttributionPolicy) and p.created_at==CANONICAL_CREATED_AT
