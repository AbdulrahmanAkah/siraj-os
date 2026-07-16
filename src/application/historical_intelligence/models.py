from dataclasses import dataclass,field
from src.application.operations_common import CANONICAL_TIMESTAMP
@dataclass
class IntelligenceTrace:
 trace_id:str; source_ids:list[str]=field(default_factory=list); evidence_ids:list[str]=field(default_factory=list); claim_ids:list[str]=field(default_factory=list); event_ids:list[str]=field(default_factory=list); entity_ids:list[str]=field(default_factory=list); reasoning_ids:list[str]=field(default_factory=list); rule_ids:list[str]=field(default_factory=list); timestamp:str=CANONICAL_TIMESTAMP; version_metadata:dict=field(default_factory=dict)
@dataclass
class EvidenceCoverage: coverage_id:str; covered_ids:list[str]=field(default_factory=list); status:str="SUFFICIENT"
@dataclass
class AnalyticalLimitation: limitation_id:str; code:str; reference_id:str
@dataclass
class ComparisonSubjectRef: subject_id:str; subject_type:str
@dataclass
class TemporalScope: scope_id:str; start:str|None=None; end:str|None=None
@dataclass
class AnalyticalFinding: finding_id:str; finding_type:str; subject_ids:list[str]=field(default_factory=list); value:str=""; coverage:EvidenceCoverage=None; trace:IntelligenceTrace=None; limitations:list[AnalyticalLimitation]=field(default_factory=list); position:int=0
@dataclass
class AnalysisResult: result_id:str; layer:str; findings:list[AnalyticalFinding]=field(default_factory=list); trace:IntelligenceTrace=None; validation_state:str="VALID"
@dataclass
class HistoricalIntelligencePackage: package_id:str; results:list[AnalysisResult]=field(default_factory=list); trace:IntelligenceTrace=None; limitations:list[AnalyticalLimitation]=field(default_factory=list); validation_state:str="VALID"
@dataclass
class ValidationIssue: issue_id:str; code:str; reference_id:str; severity:str
@dataclass
class IntelligenceValidationReport: report_id:str; issues:list[ValidationIssue]=field(default_factory=list); status:str="VALID"
@dataclass
class ValidatedHistoricalIntelligence: intelligence_id:str; package:HistoricalIntelligencePackage=None; report:IntelligenceValidationReport=None; status:str="VALID"
