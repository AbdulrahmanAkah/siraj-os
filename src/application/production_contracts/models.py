from dataclasses import dataclass,field
from src.application.operations_common import CANONICAL_TIMESTAMP
@dataclass
class Timecode: milliseconds:int; frame_position:int=0
@dataclass
class TimeRange: start_ms:int; end_ms:int
@dataclass
class ProductionPosition: position:int
@dataclass
class ProductionTrace: trace_id:str; source_ids:list[str]=field(default_factory=list); evidence_ids:list[str]=field(default_factory=list); claim_ids:list[str]=field(default_factory=list); event_ids:list[str]=field(default_factory=list); entity_ids:list[str]=field(default_factory=list); attribution_ids:list[str]=field(default_factory=list); timestamp:str=CANONICAL_TIMESTAMP; version_metadata:dict=field(default_factory=dict)
@dataclass
class ProductionLimitation: limitation_id:str; code:str; reference_id:str
@dataclass
class TrackReference: track_id:str; track_type:str
@dataclass
class AssetReference: asset_id:str; rights_status:str="RIGHTS_UNVERIFIED"
@dataclass
class LanguageSpecification: language:str; locale:str=""; explicit:bool=True
@dataclass
class ProductionValidationIssue: issue_id:str; code:str; reference_id:str; severity:str
@dataclass
class ProductionDependency: dependency_id:str; depends_on_id:str; position:int=0
