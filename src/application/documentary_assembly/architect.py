from src.application.documentary_intelligence import CANONICAL_CREATED_AT,canonical_trace,deterministic_id
from .models import DocumentaryAssemblyPolicy
class DocumentaryAssemblyArchitect:
 def build_assembly_policy(self): return DocumentaryAssemblyPolicy(deterministic_id("documentary_assembly_policy",["TRACE_COMPLETE"]),CANONICAL_CREATED_AT,0,canonical_trace())
 def validate_policy(self,p): return isinstance(p,DocumentaryAssemblyPolicy) and p.created_at==CANONICAL_CREATED_AT
