from dataclasses import dataclass,field
from src.application.operations_common import CANONICAL_TIMESTAMP
@dataclass
class OperationalPolicy: policy_id:str; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict[str,str]=field(default_factory=dict); trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class OperationalState:
 state_id:str; persistence_manifest_id:str; snapshot_id:str; version_result_id:str; audit_trail_id:str; reproduction_manifest_id:str; workflow_execution_id:str; execution_report_id:str; diagnostics_report_id:str; recovery_manifest_id:str; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict[str,str]=field(default_factory=dict); trace_metadata:dict[str,list[str]]=field(default_factory=dict); validation_state:str="VALID"
