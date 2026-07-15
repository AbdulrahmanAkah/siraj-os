from dataclasses import dataclass,field
from src.application.operations_common import CANONICAL_TIMESTAMP
@dataclass
class SnapshotPolicy: policy_id:str; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict[str,str]=field(default_factory=dict); trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class Snapshot: snapshot_id:str; manifest_id:str; integrity_hash:str; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict[str,str]=field(default_factory=dict); trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class SnapshotResult: result_id:str; snapshots:list[Snapshot]=field(default_factory=list); snapshot_count:int=0; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict[str,str]=field(default_factory=dict); trace_metadata:dict[str,list[str]]=field(default_factory=dict); validation_state:str="VALID"
