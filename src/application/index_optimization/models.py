from dataclasses import dataclass,field
from src.application.operations_common import CANONICAL_TIMESTAMP
@dataclass
class IndexSegment: segment_id:str; keys:list[str]=field(default_factory=list); timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class IndexStatistics: statistics_id:str; key_count:int; segment_count:int; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class OptimizedIndex: index_id:str; entries:dict[str,str]=field(default_factory=dict); segments:list[IndexSegment]=field(default_factory=list); timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class IndexManifest: manifest_id:str; index:OptimizedIndex=None; statistics:IndexStatistics=None; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict); validation_state:str="VALID"
