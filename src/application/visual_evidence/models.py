from dataclasses import dataclass,field
from src.application.documentary_intelligence import CANONICAL_CREATED_AT
@dataclass
class VisualEvidencePolicy:
 policy_id:str; created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class VisualEvidenceLink:
 link_id:str; relation_type:str; source_id:str; visual_id:str; evidence_ids:list[str]=field(default_factory=list); created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class VisualEvidenceMap:
 map_id:str; package_id:str; links:list[VisualEvidenceLink]=field(default_factory=list); link_count:int=0; created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict); validation_state:str="VALID"
