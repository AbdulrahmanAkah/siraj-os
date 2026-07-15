from src.application.operations_common import *
from .models import OperationalPolicy
class OperationalArchitect:
 def build_operational_policy(self):return OperationalPolicy(deterministic_id("operational_policy",["ASSEMBLE"]),CANONICAL_TIMESTAMP,0,canonical_version_metadata("operations"),canonical_trace())
