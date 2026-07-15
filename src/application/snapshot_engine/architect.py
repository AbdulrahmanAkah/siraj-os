from src.application.operations_common import *
from .models import SnapshotPolicy
class SnapshotArchitect:
 def build_snapshot_policy(self):return SnapshotPolicy(deterministic_id("snapshot_policy",["MANIFEST_HASH"]),CANONICAL_TIMESTAMP,0,canonical_version_metadata("snapshot"),canonical_trace())
