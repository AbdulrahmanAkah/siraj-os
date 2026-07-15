from dataclasses import dataclass,field
@dataclass
class GraphPartition: partition_id:str; node_ids:list[str]=field(default_factory=list); position:int=0; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class GraphTraversalPlan: plan_id:str; traversal_order:list[str]=field(default_factory=list); position:int=0; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class GraphStatistics: statistics_id:str; node_count:int=0; edge_count:int=0; performance_metadata:dict=field(default_factory=dict)
@dataclass
class GraphOptimizationResult: result_id:str; partitions:list[GraphPartition]=field(default_factory=list); traversal_plan:GraphTraversalPlan=None; statistics:GraphStatistics=None; validation_state:str="VALID"
