from dataclasses import dataclass,field
from src.application.documentary_intelligence import CANONICAL_CREATED_AT
@dataclass
class StoryboardPolicy:
 policy_id:str
 created_at:str=CANONICAL_CREATED_AT
 position:int=0
 trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class StoryboardFrame:
 frame_id:str
 scene_id:str
 frame_purpose:str
 referenced_evidence_ids:list[str]=field(default_factory=list)
 created_at:str=CANONICAL_CREATED_AT
 position:int=0
 trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class Storyboard:
 storyboard_id:str
 scene_plan_id:str
 frames:list[StoryboardFrame]=field(default_factory=list)
 frame_count:int=0
 created_at:str=CANONICAL_CREATED_AT
 position:int=0
 trace_metadata:dict[str,list[str]]=field(default_factory=dict)
 validation_state:str="VALID"
