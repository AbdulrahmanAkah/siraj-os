from src.application.operations_common import *
from .models import ReproducibilityPolicy
class ReproducibilityArchitect:
 def build_reproducibility_policy(self):return ReproducibilityPolicy(deterministic_id("reproducibility_policy",["EXACT_HASH"]),CANONICAL_TIMESTAMP,0,canonical_version_metadata("reproducibility"),canonical_trace())
