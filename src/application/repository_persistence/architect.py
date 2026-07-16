from src.application.operations_common import CANONICAL_TIMESTAMP,canonical_trace,canonical_version_metadata,deterministic_id
from .models import RepositoryPersistencePolicy
class RepositoryPersistenceArchitect:
 def build_persistence_policy(self):return RepositoryPersistencePolicy(deterministic_id("repository_persistence_policy",["IN_MEMORY"]),CANONICAL_TIMESTAMP,0,canonical_version_metadata("repository_persistence"),canonical_trace())
 def validate_policy(self,p):return isinstance(p,RepositoryPersistencePolicy) and p.timestamp==CANONICAL_TIMESTAMP
