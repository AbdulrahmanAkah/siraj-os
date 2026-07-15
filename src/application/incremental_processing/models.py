from dataclasses import dataclass,field
@dataclass
class ChangeSet: change_set_id:str; changed_ids:list[str]=field(default_factory=list); version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class IncrementalPlan: plan_id:str; recompute_ids:list[str]=field(default_factory=list); version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class IncrementalResult: result_id:str; recomputed_ids:list[str]=field(default_factory=list); validation_state:str="VALID"; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
