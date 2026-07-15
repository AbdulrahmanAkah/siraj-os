from dataclasses import dataclass,field
from src.application.documentary_intelligence import CANONICAL_CREATED_AT
@dataclass
class DocumentaryAssemblyPolicy:
 policy_id:str; created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class DocumentaryPackage:
 package_id:str; documentary_plan_id:str; narrative_architecture_id:str; script_id:str; scene_plan_id:str; storyboard_id:str; created_at:str=CANONICAL_CREATED_AT; position:int=0; trace_metadata:dict[str,list[str]]=field(default_factory=dict); validation_state:str="VALID"
