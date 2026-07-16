from dataclasses import dataclass,field
from src.application.operations_common import CANONICAL_TIMESTAMP
@dataclass
class ExecutionMetrics: metrics_id:str; completed_jobs:int; total_jobs:int; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict[str,str]=field(default_factory=dict); trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class ExecutionStatus: status_id:str; status:str; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict[str,str]=field(default_factory=dict); trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class ExecutionReport: report_id:str; metrics:ExecutionMetrics=None; status:ExecutionStatus=None; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict[str,str]=field(default_factory=dict); trace_metadata:dict[str,list[str]]=field(default_factory=dict); validation_state:str="VALID"
