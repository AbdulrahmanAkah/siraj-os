from dataclasses import dataclass, field
from src.application.documentary_intelligence import CANONICAL_CREATED_AT
@dataclass
class SceneGenerationPolicy:
    policy_id:str
    created_at:str=CANONICAL_CREATED_AT
    position:int=0
    trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class GeneratedScene:
    scene_id:str
    scene_purpose:str
    referenced_event_ids:list[str]=field(default_factory=list)
    referenced_evidence_ids:list[str]=field(default_factory=list)
    narration_section_id:str=""
    created_at:str=CANONICAL_CREATED_AT
    position:int=0
    trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class ScenePlanRuntime:
    plan_id:str
    documentary_script_id:str
    scenes:list[GeneratedScene]=field(default_factory=list)
    scene_count:int=0
    created_at:str=CANONICAL_CREATED_AT
    position:int=0
    trace_metadata:dict[str,list[str]]=field(default_factory=dict)
    validation_state:str="VALID"
