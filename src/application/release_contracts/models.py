from dataclasses import dataclass,field
from src.application.operations_common import CANONICAL_TIMESTAMP
@dataclass
class ApplicationVersion: version:str="0.1.0-rc.2"; schema_version:str="v1"
@dataclass
class ApplicationIdentity: application_id:str="siraj"; version:ApplicationVersion=field(default_factory=ApplicationVersion)
@dataclass
class ReleaseTrace: trace_id:str; input_ids:list[str]=field(default_factory=list); timestamp:str=CANONICAL_TIMESTAMP
@dataclass
class ReleaseValidationIssue: issue_id:str; code:str; severity:str
@dataclass
class ReleaseLimitation: limitation_id:str; code:str
@dataclass
class ReleaseDependency: dependency_id:str; depends_on_id:str
