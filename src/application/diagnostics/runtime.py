from src.application.operations_common import *
from .models import DiagnosticIssue,DiagnosticsReport
class DiagnosticsRuntime:
 def diagnose(self,policy,manifest,monitoring):
  issue_specs=[]
  if not manifest.integrity_hash:issue_specs.append(("INTEGRITY_ISSUE","HIGH",manifest.manifest_id))
  if monitoring.status.status!="COMPLETED":issue_specs.append(("EXECUTION_FAILURE","HIGH",monitoring.report_id))
  issues=[DiagnosticIssue(deterministic_id("diagnostic_issue",spec),spec[0],spec[1],spec[2],CANONICAL_TIMESTAMP,pos,canonical_version_metadata(spec[2]),{}) for pos,spec in enumerate(issue_specs)]
  return DiagnosticsReport(deterministic_id("diagnostics_report",[manifest.manifest_id,monitoring.report_id,[x.issue_id for x in issues]]),issues,len(issues),CANONICAL_TIMESTAMP,0,canonical_version_metadata(manifest.manifest_id),{},"VALID")
