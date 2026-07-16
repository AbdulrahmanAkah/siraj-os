from dataclasses import dataclass,field
from src.application.operations_common import CANONICAL_TIMESTAMP
@dataclass
class QueryStrategy: strategy_id:str; lookup_order:list[str]=field(default_factory=list); timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class QueryPlan: plan_id:str; query_key:str; strategy:QueryStrategy=None; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class QueryStatistics: statistics_id:str; examined_keys:int; match_count:int; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class QueryResultProfile: profile_id:str; plan_id:str; matches:list[str]=field(default_factory=list); statistics:QueryStatistics=None; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict); validation_state:str="VALID"
