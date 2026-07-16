from src.application.documentary_intelligence import CANONICAL_CREATED_AT,canonical_trace,deterministic_id
from .models import ProductionPolicy
class ProductionArchitect:
 def build_production_policy(self):return ProductionPolicy(deterministic_id("production_policy",["VERIFIED_PUBLICATION"]),CANONICAL_CREATED_AT,0,canonical_trace())
 def validate_policy(self,p):return isinstance(p,ProductionPolicy) and p.created_at==CANONICAL_CREATED_AT
