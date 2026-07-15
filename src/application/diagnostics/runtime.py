from src.application.operations_common import *
from .models import DiagnosticsReport
class DiagnosticsRuntime:
 def diagnose(self,policy,manifest,monitoring):
  issues=[]
  if not manifest.integrity_hash:issues.append("INTEGRITY_ISSUE")
  if monitoring.status.status!="COMPLETED":issues.append("EXECUTION_FAILURE")
  return DiagnosticsReport(deterministic_id("diagnostics_report",[manifest.manifest_id,monitoring.report_id,issues]),[],len(issues),CANONICAL_TIMESTAMP,0,canonical_version_metadata(manifest.manifest_id),{},"VALID")
