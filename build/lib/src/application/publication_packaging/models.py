from dataclasses import dataclass,field
from src.application.documentary_intelligence import CANONICAL_CREATED_AT
@dataclass
class PublicationPackagingPolicy: policy_id:str; created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class PublicationPackage:
 package_id:str; documentary_package_id:str; metadata:dict[str,str]=field(default_factory=dict); credits:list[str]=field(default_factory=list); sources:list[str]=field(default_factory=list); evidence_appendix:list[str]=field(default_factory=list); verification_summary:str=""; created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict); validation_state:str="VALID"
