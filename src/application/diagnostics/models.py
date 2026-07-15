from dataclasses import dataclass,field
from src.application.operations_common import CANONICAL_TIMESTAMP
@dataclass
class DiagnosticsPolicy: policy_id:str; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict[str,str]=field(default_factory=dict); trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class DiagnosticIssue: issue_id:str; issue_type:str; severity:str; reference_id:str; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict[str,str]=field(default_factory=dict); trace_metadata:dict[str,list[str]]=field(default_factory=dict)
@dataclass
class DiagnosticsReport: report_id:str; issues:list[DiagnosticIssue]=field(default_factory=list); issue_count:int=0; timestamp:str=CANONICAL_TIMESTAMP; position:int=0; version_metadata:dict[str,str]=field(default_factory=dict); trace_metadata:dict[str,list[str]]=field(default_factory=dict); validation_state:str="VALID"
