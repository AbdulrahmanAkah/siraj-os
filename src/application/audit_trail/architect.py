from src.application.operations_common import *
from .models import AuditPolicy
class AuditTrailArchitect:
 def build_audit_policy(self):return AuditPolicy(deterministic_id("audit_policy",["WHO_WHAT_WHEN_WHY"]),CANONICAL_TIMESTAMP,0,canonical_version_metadata("audit"),canonical_trace())
