from src.application.operations_common import *
from src.application.snapshot_engine.models import SnapshotResult
from .models import VersionRecord,VersionResult
class VersioningRuntime:
 def create_versions(self,policy,snapshots,subjects):
  if not isinstance(snapshots,SnapshotResult) or not isinstance(subjects,dict):raise ValueError("Invalid versioning inputs")
  snapshot_id=snapshots.snapshots[0].snapshot_id;records=[]
  for pos,(kind,subject_id) in enumerate(sorted(subjects.items())):records.append(VersionRecord(deterministic_id("version_record",[kind,subject_id,snapshot_id]),kind,str(subject_id),snapshot_id,"v1",CANONICAL_TIMESTAMP,pos,canonical_version_metadata(str(subject_id)),{}))
  return VersionResult(deterministic_id("version_result",[x.version_id for x in records]),records,len(records),CANONICAL_TIMESTAMP,0,canonical_version_metadata(snapshot_id),{},"VALID")
