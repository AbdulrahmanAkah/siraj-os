"""Offline Phase 3 upgrade, failure-injection, and deterministic soak checks."""

from pathlib import Path
import json

import pytest

from src.application.ai_integration import AIProviderError
from src.application.ai_provider_openai_compatible import (
    CredentialReference, ExternalAIExecutionPolicy, OpenAICompatibleProvider,
    OpenAICompatibleProviderConfig,
)
from src.application.rc_hardening import (
    ExportOverwritePolicy, ExportPathPolicy, FileExportAdapter,
    RendererDryRunAdapter, SQLiteConnectionConfig, SQLitePersistenceAdapter,
    SQLiteSchemaIdentity,
)


class Resolver:
    def resolve(self, _reference):
        return "verification-only-token"


def test_upgrade_migration_restore_and_replay(tmp_path):
    database = tmp_path / "upgrade.sqlite"
    with SQLitePersistenceAdapter(SQLiteConnectionConfig(str(database))) as old:
        old.initialize()
        record = old.persist_repository("repository-1", {"claims": ["claim-1"], "snapshot": "baseline"})
        assert record.committed
        assert old.migrate_schema("rc-hardening-v2", dry_run=True).dry_run
        assert old.migrate_schema("rc-hardening-v2", dry_run=False).applied
    with SQLitePersistenceAdapter(SQLiteConnectionConfig(str(database)), SQLiteSchemaIdentity(schema_version="rc-hardening-v2")) as current:
        current.initialize()
        assert current.restore(record.record_ids[0]).status == "VALID"
        assert not current.migrate_schema("rc-hardening-v2", dry_run=True).applied
        with pytest.raises(ValueError, match="UNSUPPORTED_MIGRATION_PATH"):
            current.migrate_schema("unsupported-v99", dry_run=True)


def test_failure_injection_produces_controlled_states(tmp_path):
    database = tmp_path / "state.sqlite"
    with SQLitePersistenceAdapter(SQLiteConnectionConfig(str(database))) as adapter:
        adapter.initialize()
        saved = adapter.save("SNAPSHOT", "snapshot", {"value": "safe"})
        adapter._db().execute("UPDATE persisted_records SET payload = ? WHERE record_id = ?", ("{", saved.record_ids[0]))
        adapter._db().commit()
        assert adapter.restore(saved.record_ids[0]).issues[0].code == "MALFORMED_PAYLOAD"
    with SQLitePersistenceAdapter(SQLiteConnectionConfig(str(database), read_only=True)) as adapter:
        adapter.initialize()
        assert adapter.save("REPOSITORY", "blocked", {}).error_code == "READ_ONLY_DATABASE"
    exporter = FileExportAdapter(ExportPathPolicy(str(tmp_path / "exports"), maximum_file_size=20), ExportOverwritePolicy("DENY"))
    assert exporter.export_markdown("large.md", "x" * 21).code == "EXPORT_TOO_LARGE"
    assert exporter.export_json("../escape.json", {}).code == "PATH_TRAVERSAL_REJECTED"
    renderer = RendererDryRunAdapter(str(tmp_path))
    assert renderer.dry_run({"missing_assets": ["missing"]}).status == "BLOCKED"
    assert renderer.dry_run({"tracks": {"visual": [{"start_ms": 5, "end_ms": 0}]}}).status == "INVALID"


def test_provider_failures_are_normalized_without_network():
    def timeout(*_args):
        raise TimeoutError()
    provider = OpenAICompatibleProvider(OpenAICompatibleProviderConfig(), CredentialReference("TEST"), Resolver(), ExternalAIExecutionPolicy(allow_external=True, approved=True), timeout)
    with pytest.raises(AIProviderError, match="TIMEOUT"):
        provider.generate({"text": "public fixture"})
    denied = OpenAICompatibleProvider(OpenAICompatibleProviderConfig(), CredentialReference("TEST"), Resolver(), ExternalAIExecutionPolicy(allow_external=True, data_classification="RESTRICTED", approved=True), timeout)
    with pytest.raises(AIProviderError, match="RESTRICTED_EXTERNAL_TRANSMISSION_DENIED"):
        denied.generate({"text": "restricted fixture"})


def test_deterministic_operational_soak_small_dataset(tmp_path):
    database = tmp_path / "soak.sqlite"
    output = tmp_path / "exports"
    hashes, record_ids = [], []
    with SQLitePersistenceAdapter(SQLiteConnectionConfig(str(database))) as adapter:
        adapter.initialize()
        exporter = FileExportAdapter(ExportPathPolicy(str(output)), ExportOverwritePolicy("REPLACE"))
        for position in range(100):
            stored = adapter.persist_repository("golden-small", {"dataset": "golden-small-v1", "position": 0, "claims": ["claim-1"]})
            restored = adapter.restore(stored.record_ids[0])
            exported = exporter.export_json("golden-small.json", restored.restored)
            assert restored.status == "VALID" and exported.completed
            hashes.append(exported.sha256); record_ids.extend(stored.record_ids)
        assert len(set(hashes)) == 1 and len(set(record_ids)) == 1
        assert not list(output.glob(".siraj-*.tmp"))
    assert database.exists()


def test_golden_descriptors_replay_in_stable_order():
    root = Path(__file__).parents[1] / "fixtures" / "golden"
    descriptors = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(root.glob("*.json"))]
    assert [item["dataset_id"] for item in descriptors] == sorted(item["dataset_id"] for item in descriptors)
    assert all("dataset_id" in item for item in descriptors)
