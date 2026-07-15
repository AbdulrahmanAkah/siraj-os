from .architect import PersistenceArchitect
class PersistenceArchitectureRuntime:
 def validate_persistence_manifest(self,manifest):return PersistenceArchitect().validate_manifest(manifest)
