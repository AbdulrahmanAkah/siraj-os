from dataclasses import dataclass,field
from src.application.documentary_intelligence import CANONICAL_CREATED_AT
@dataclass
class AttributionPolicy: policy_id:str; created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class AttributionRecord:
 attribution_id:str; artifact_id:str; source_ids:list[str]=field(default_factory=list); evidence_ids:list[str]=field(default_factory=list); claim_ids:list[str]=field(default_factory=list); created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class AttributionResult:
 result_id:str; package_id:str; records:list[AttributionRecord]=field(default_factory=list); record_count:int=0; created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict); validation_state:str="VALID"
