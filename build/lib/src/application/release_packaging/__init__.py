from dataclasses import dataclass,field
from src.application.operations_common import integrity_hash
@dataclass
class ReleaseArtifact: artifact_id:str; artifact_type:str; checksum:str
@dataclass
class ReleaseManifest: version:str; artifacts:list[ReleaseArtifact]=field(default_factory=list)
class ReleasePackagingRuntime:
 def manifest(self,version,artifacts):return ReleaseManifest(version,[ReleaseArtifact(name,kind,integrity_hash([name,kind,version])) for name,kind in sorted(artifacts)])
