from src.application.operations_common import *
from .models import OperationalState
class OperationalRuntime:
 def build_operational_state(self,policy,persistence,snapshot,versions,audit,reproduction,workflow,monitoring,diagnostics,recovery):
  ids=[persistence.manifest_id,snapshot.snapshots[0].snapshot_id,versions.result_id,audit.trail_id,reproduction.manifest.manifest_id,workflow.execution_id,monitoring.report_id,diagnostics.report_id,recovery.manifest_id]
  return OperationalState(deterministic_id("operational_state",ids),*ids,CANONICAL_TIMESTAMP,0,canonical_version_metadata(ids[0]),{},"VALID")
