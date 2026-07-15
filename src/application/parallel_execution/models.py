from dataclasses import dataclass,field
@dataclass
class ExecutionPartition: partition_id:str; item_ids:list[str]=field(default_factory=list); position:int=0; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class ParallelPlan: plan_id:str; partitions:list[ExecutionPartition]=field(default_factory=list); version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class ExecutionShard: shard_id:str; partition_id:str; output_ids:list[str]=field(default_factory=list); position:int=0; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
