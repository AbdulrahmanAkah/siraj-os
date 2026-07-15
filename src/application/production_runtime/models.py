from dataclasses import dataclass,field
from src.application.documentary_intelligence import CANONICAL_CREATED_AT
@dataclass
class ProductionPolicy: policy_id:str; created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class ProductionReadyDocumentary:
 production_id:str; publication_package_id:str; export_bundle_id:str; verification_report_id:str; created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict); validation_state:str="VALID"
