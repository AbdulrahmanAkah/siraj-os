from src.application.documentary_intelligence import CANONICAL_CREATED_AT,canonical_trace,deterministic_id
from .models import ExportArchitecturePolicy
class ExportArchitect:
 def build_export_policy(self):return ExportArchitecturePolicy(deterministic_id("export_policy",["MANIFEST_ONLY"]),CANONICAL_CREATED_AT,0,canonical_trace())
 def validate_policy(self,p):return isinstance(p,ExportArchitecturePolicy) and p.created_at==CANONICAL_CREATED_AT
