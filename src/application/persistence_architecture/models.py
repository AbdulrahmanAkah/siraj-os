from dataclasses import dataclass,field
from src.application.operations_common import CANONICAL_TIMESTAMP
@dataclass
class PersistenceMetadata: metadata_id:str; timestamp:str=CANONICAL_TIMESTAMP; version_metadata:dict[str,str]=field(default_factory=dict); trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class PersistenceRecord: record_id:str; artifact_type:str; artifact_id:str; payload_hash:str; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict[str,str]=field(default_factory=dict); trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class PersistenceUnit: unit_id:str; records:list[PersistenceRecord]=field(default_factory=list); timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict[str,str]=field(default_factory=dict); trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class PersistenceManifest: manifest_id:str; units:list[PersistenceUnit]=field(default_factory=list); record_count:int=0; metadata:PersistenceMetadata=None; integrity_hash:str=""; timestamp:str=CANONICAL_TIMESTAMP; version_metadata:dict[str,str]=field(default_factory=dict); trace_metadata:dict[str,list[str]]=field(default_factory=dict); validation_state:str="VALID"
