from src.application.production_runtime.models import ProductionReadyDocumentary
from src.application.persistence_architecture import PersistenceArchitect
from src.application.repository_persistence import RepositoryPersistenceArchitect, RepositoryPersistenceRuntime
from src.application.snapshot_engine import SnapshotArchitect, SnapshotRuntime
from src.application.versioning_engine import VersioningArchitect, VersioningRuntime
from src.application.audit_trail import AuditTrailArchitect, AuditTrailRuntime
from src.application.reproducibility import ReproducibilityArchitect, ReproducibilityRuntime
from src.application.workflow_runtime import WorkflowArchitect, WorkflowRuntime
from src.application.job_orchestration import JobOrchestrationRuntime
from src.application.execution_monitoring import ExecutionMonitoringRuntime
from src.application.diagnostics import DiagnosticsArchitect, DiagnosticsRuntime
from src.application.recovery_architecture import RecoveryArchitect, RecoveryRuntime
from src.application.operational_runtime import OperationalArchitect, OperationalRuntime


def test_bundle_d_deterministic_operations_lifecycle():
    production = ProductionReadyDocumentary("production", "publication", "export", "verification")
    artifacts = {"knowledge_repository": {"records": ["record-1"]}, "production_ready_documentary": production}
    manifest = PersistenceArchitect().build_persistence_manifest(artifacts)
    persisted = RepositoryPersistenceRuntime().persist_and_restore(RepositoryPersistenceArchitect().build_persistence_policy(), manifest, artifacts)
    snapshots = SnapshotRuntime().create_snapshot(SnapshotArchitect().build_snapshot_policy(), manifest)
    versions = VersioningRuntime().create_versions(VersioningArchitect().build_version_policy(), snapshots, {"repository": "repository", "documentary": production.production_id})
    audit = AuditTrailRuntime().build_audit_trail(AuditTrailArchitect().build_audit_policy(), [{"actor": "system", "action": "persist", "reason": "lifecycle", "subject_id": manifest.manifest_id}])
    reproduction = ReproducibilityRuntime().validate_reproducibility(ReproducibilityArchitect().build_reproducibility_policy(), artifacts, {"mode": "deterministic"}, versions, production)
    definition = WorkflowArchitect().build_workflow_definition(["persist", "snapshot", "operate"])
    execution = WorkflowRuntime().execute_workflow(definition)
    queue, job_results = JobOrchestrationRuntime().orchestrate_jobs(execution)
    monitoring = ExecutionMonitoringRuntime().build_execution_report(queue, job_results)
    diagnostics = DiagnosticsRuntime().diagnose(DiagnosticsArchitect().build_diagnostics_policy(), manifest, monitoring)
    recovery = RecoveryRuntime().build_recovery_manifest(RecoveryArchitect().build_recovery_policy(), snapshots.snapshots[0], diagnostics)
    state = OperationalRuntime().build_operational_state(OperationalArchitect().build_operational_policy(), persisted, snapshots, versions, audit, reproduction, execution, monitoring, diagnostics, recovery)
    assert persisted.stored_record_ids == persisted.restored_artifact_ids
    assert snapshots.snapshots[0].integrity_hash == manifest.integrity_hash
    assert versions.record_count == 2
    assert audit.event_count == 1
    assert reproduction.reproducible
    assert monitoring.status.status == "COMPLETED"
    assert diagnostics.issue_count == 0
    assert state.validation_state == "VALID"
    assert state == OperationalRuntime().build_operational_state(OperationalArchitect().build_operational_policy(), persisted, snapshots, versions, audit, reproduction, execution, monitoring, diagnostics, recovery)
