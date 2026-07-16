from dataclasses import dataclass,field
@dataclass
class MemoryProfile: profile_id:str; estimated_bytes:int; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class MemorySnapshot: snapshot_id:str; profile:MemoryProfile=None; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
@dataclass
class MemoryOptimizationResult: result_id:str; snapshot:MemorySnapshot=None; validation_state:str="VALID"; version_metadata:dict=field(default_factory=dict); trace_metadata:dict=field(default_factory=dict); performance_metadata:dict=field(default_factory=dict)
