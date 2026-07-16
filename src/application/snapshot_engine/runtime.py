from src.application.operations_common import *
from src.application.persistence_architecture.models import PersistenceManifest
from .models import Snapshot,SnapshotResult
class SnapshotRuntime:
 def create_snapshot(self,policy,manifest):
  if not isinstance(manifest,PersistenceManifest):raise ValueError("Invalid snapshot inputs")
  snapshot=Snapshot(deterministic_id("snapshot",[manifest.manifest_id,manifest.integrity_hash]),manifest.manifest_id,manifest.integrity_hash,CANONICAL_TIMESTAMP,0,canonical_version_metadata(manifest.manifest_id),manifest.trace_metadata)
  return SnapshotResult(deterministic_id("snapshot_result",[snapshot.snapshot_id]),[snapshot],1,CANONICAL_TIMESTAMP,0,canonical_version_metadata(snapshot.snapshot_id),manifest.trace_metadata)
