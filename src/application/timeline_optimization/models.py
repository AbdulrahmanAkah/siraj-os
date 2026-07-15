from dataclasses import dataclass,field
@dataclass
class TimelineSegment: segment_id:str; entry_ids:list[str]=field(default_factory=list); position:int=0; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class TimelineRangeIndex: index_id:str; ranges:dict[str,list[str]]=field(default_factory=dict); version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class TimelineOptimizationResult: result_id:str; segments:list[TimelineSegment]=field(default_factory=list); range_index:TimelineRangeIndex=None; validation_state:str="VALID"
