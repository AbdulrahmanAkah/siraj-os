from dataclasses import dataclass,field
from src.application.operations_common import CANONICAL_TIMESTAMP
@dataclass
class AITrace: trace_id:str; source_ids:list[str]=field(default_factory=list); evidence_ids:list[str]=field(default_factory=list); claim_ids:list[str]=field(default_factory=list); event_ids:list[str]=field(default_factory=list); entity_ids:list[str]=field(default_factory=list); citation_ids:list[str]=field(default_factory=list)
@dataclass
class AIValidationIssue: issue_id:str; code:str; reference_id:str; severity:str
@dataclass
class AIModelIdentity: provider:str; model_id:str; version:str="UNSPECIFIED"
@dataclass
class PromptIdentity: prompt_id:str; version:str; prompt_hash:str
@dataclass
class ContextIdentity: context_id:str; context_hash:str
@dataclass
class PromptContract: prompt_id:str; version:str; purpose:str; template:str; required_evidence:bool=True; output_schema:str="TEXT"; citation_policy:str="REQUIRED"
@dataclass
class EvidenceContext: context_id:str; evidence_ids:list[str]=field(default_factory=list); excluded_ids:list[str]=field(default_factory=list); context_hash:str=""
@dataclass
class GroundedGenerationResult: result_id:str; text:str; citations:list[str]=field(default_factory=list); claims:list[str]=field(default_factory=list); trace:AITrace=None; status:str="GENERATED"
@dataclass
class AIOutputValidationReport: report_id:str; status:str; issues:list[AIValidationIssue]=field(default_factory=list)
@dataclass
class AIAuditRecord: audit_id:str; provider_request_id:str; prompt:PromptIdentity; context:ContextIdentity; raw_output_hash:str; validation_hash:str; retry_count:int=0
@dataclass
class ValidatedGroundedAIResult: result_id:str; generation:GroundedGenerationResult; validation:AIOutputValidationReport; audit:AIAuditRecord; status:str
