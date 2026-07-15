from dataclasses import dataclass,field
from src.application.documentary_intelligence import CANONICAL_CREATED_AT
@dataclass
class ExportArchitecturePolicy: policy_id:str; created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class ExportManifest: manifest_id:str; publication_package_id:str; artifacts:list[str]=field(default_factory=list); created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class ExportJob: job_id:str; manifest_id:str; job_type:str="ARCHITECTURE_ONLY"; created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class ExportBundle: bundle_id:str; manifest:ExportManifest=None; jobs:list[ExportJob]=field(default_factory=list); created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict); validation_state:str="VALID"
