from src.application.operations_common import *
from .models import RecoveryAction,RecoveryPlan,RecoveryManifest
class RecoveryRuntime:
 def build_recovery_manifest(self,policy,snapshot,diagnostics):
  actions=[RecoveryAction(deterministic_id("recovery_action",["RESTORE_SNAPSHOT",snapshot.snapshot_id]),"RESTORE_SNAPSHOT",snapshot.snapshot_id,CANONICAL_TIMESTAMP,0,canonical_version_metadata(snapshot.snapshot_id),{})] if diagnostics.issue_count else []
  plan=RecoveryPlan(deterministic_id("recovery_plan",[x.action_id for x in actions]),actions,CANONICAL_TIMESTAMP,0,canonical_version_metadata(snapshot.snapshot_id),{})
  return RecoveryManifest(deterministic_id("recovery_manifest",[plan.plan_id,snapshot.snapshot_id]),plan.plan_id,snapshot.snapshot_id,CANONICAL_TIMESTAMP,0,canonical_version_metadata(snapshot.snapshot_id),{},"VALID")
