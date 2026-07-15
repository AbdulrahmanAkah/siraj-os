from src.application.operations_common import *
from .models import VersionPolicy
class VersioningArchitect:
 def build_version_policy(self):return VersionPolicy(deterministic_id("version_policy",["v1"]),CANONICAL_TIMESTAMP,0,canonical_version_metadata("versioning"),canonical_trace())
