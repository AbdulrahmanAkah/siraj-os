from src.application.operations_common import deterministic_id,canonical_trace,canonical_version_metadata,stable_unique
from .models import *
LAYERS=("COMPARATIVE","CROSS_ERA","PATTERN","CIVILIZATION","INSTITUTION","STRATEGIC","TREND","COUNTERFACTUAL","THEORY")
def _trace(event_ids=(),evidence_ids=(),claim_ids=(),rule_ids=(),reasoning_ids=()):
 event_ids,evidence_ids,claim_ids,rule_ids,reasoning_ids=(stable_unique(value) for value in (event_ids,evidence_ids,claim_ids,rule_ids,reasoning_ids));return IntelligenceTrace(deterministic_id("intelligence_trace",[event_ids,evidence_ids,claim_ids,rule_ids,reasoning_ids]),[],evidence_ids,claim_ids,event_ids,[],reasoning_ids,rule_ids,version_metadata=canonical_version_metadata("intelligence"))
class HistoricalIntelligenceArchitect:
 def build_plan(self,layer):return {"plan_id":deterministic_id("intelligence_plan",layer),"layer":layer,"rule_id":"EXPLICIT_EVIDENCE_ONLY"}
class HistoricalIntelligenceRuntime:
 def analyze(self,plan,subjects,evidence_ids=(),event_ids=(),claim_ids=(),reasoning_ids=()):
  ids=sorted(set(subjects));trace=_trace(event_ids,evidence_ids,claim_ids,[plan["rule_id"]],reasoning_ids);coverage=EvidenceCoverage(deterministic_id("evidence_coverage",evidence_ids),stable_unique(evidence_ids),"SUFFICIENT" if evidence_ids else "INSUFFICIENT_EVIDENCE");limits=[] if evidence_ids else [AnalyticalLimitation(deterministic_id("limitation",ids),"INSUFFICIENT_EVIDENCE",ids[0] if ids else "")];finding=AnalyticalFinding(deterministic_id("analytical_finding",[plan["layer"],ids,coverage.status]),plan["layer"],ids,"EXPLICIT_COMPARISON" if evidence_ids else "INSUFFICIENT_EVIDENCE",coverage,trace,limits,0);return AnalysisResult(deterministic_id("analysis_result",[plan["layer"],finding.finding_id]),plan["layer"],[finding],trace,"VALID")
 def synthesize(self,results):
  ordered=sorted(results,key=lambda x:(x.layer,x.result_id));trace=_trace(evidence_ids=(e for r in ordered for e in r.trace.evidence_ids),event_ids=(e for r in ordered for e in r.trace.event_ids),claim_ids=(c for r in ordered for c in r.trace.claim_ids),reasoning_ids=(x for r in ordered for x in r.trace.reasoning_ids));limits=[x for r in ordered for f in r.findings for x in f.limitations];return HistoricalIntelligencePackage(deterministic_id("historical_intelligence_package",[r.result_id for r in ordered]),ordered,trace,limits,"VALID")
 def validate(self,package):
  issues=[]
  for r in package.results:
   for f in r.findings:
    if not f.trace or not f.coverage:issues.append(ValidationIssue(deterministic_id("validation_issue",f.finding_id),"MISSING_TRACE",f.finding_id,"HIGH"))
  status="VALID" if not issues else "INVALID";report=IntelligenceValidationReport(deterministic_id("intelligence_validation",[x.issue_id for x in issues]),issues,status);return ValidatedHistoricalIntelligence(deterministic_id("validated_historical_intelligence",[package.package_id,report.report_id]),package,report,status)
