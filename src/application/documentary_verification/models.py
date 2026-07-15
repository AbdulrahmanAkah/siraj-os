from dataclasses import dataclass,field
from src.application.documentary_intelligence import CANONICAL_CREATED_AT
@dataclass
class DocumentaryVerificationPolicy: policy_id:str; checks:list[str]=field(default_factory=list); created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class VerificationCheck: check_id:str; check_type:str; passed:bool; reference_ids:list[str]=field(default_factory=list); created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class VerificationReport: report_id:str; package_id:str; checks:list[VerificationCheck]=field(default_factory=list); check_count:int=0; is_valid:bool=True; created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict); validation_state:str="VALID"
