from pathlib import Path

from src.application.rc_hardening import (
    ExportOverwritePolicy,
    ExportPathPolicy,
    FileExportAdapter,
    RendererDryRunAdapter,
    SQLiteConnectionConfig,
    SQLitePersistenceAdapter,
)


def test_sqlite_lifecycle_snapshot_reopen_and_redaction(tmp_path):
    database = tmp_path / "siraj.sqlite"
    with SQLitePersistenceAdapter(SQLiteConnectionConfig(str(database))) as adapter:
        adapter.initialize()
        saved = adapter.persist_snapshot("snapshot-1", {"record": "alpha", "api_key": "must-not-persist"})
        assert saved.committed
        restored = adapter.restore(saved.record_ids[0])
        assert restored.status == "VALID"
        assert restored.restored[saved.record_ids[0]]["api_key"] == "REDACTED"
    with SQLitePersistenceAdapter(SQLiteConnectionConfig(str(database))) as reopened:
        reopened.initialize()
        assert reopened.restore(saved.record_ids[0]).status == "VALID"


def test_sqlite_rollback_corruption_and_read_only(tmp_path):
    database = tmp_path / "siraj.sqlite"
    with SQLitePersistenceAdapter(SQLiteConnectionConfig(str(database), maximum_payload_size=32)) as adapter:
        adapter.initialize()
        failed = adapter.save_many([("REPOSITORY", "ok", {"value": "ok"}), ("REPOSITORY", "large", {"value": "x" * 100})])
        assert not failed.committed and failed.error_code == "TRANSACTION_ROLLED_BACK"
        saved = adapter.save("REPOSITORY", "safe", {"value": "ok"})
        adapter._db().execute("UPDATE persisted_records SET payload = ? WHERE record_id = ?", ("{}", saved.record_ids[0]))
        adapter._db().commit()
        assert adapter.restore(saved.record_ids[0]).issues[0].code == "CORRUPTED_PAYLOAD_HASH"
    with SQLitePersistenceAdapter(SQLiteConnectionConfig(str(database), read_only=True)) as adapter:
        adapter.initialize()
        assert adapter.save("REPOSITORY", "blocked", {}).error_code == "READ_ONLY_DATABASE"


def test_exports_are_deterministic_contained_and_unicode_safe(tmp_path):
    exporter = FileExportAdapter(ExportPathPolicy(str(tmp_path)), ExportOverwritePolicy("DENY"))
    first = exporter.export_json("metadata.json", {"title": "وثائقي", "items": ["b", "a"]})
    assert first.completed and (tmp_path / "metadata.json").read_text(encoding="utf-8").startswith('{"items"')
    assert exporter.export_json("metadata.json", {}).code == "OVERWRITE_DENIED"
    assert exporter.export_json("../outside.json", {}).code == "PATH_TRAVERSAL_REJECTED"
    srt = exporter.export_srt([{"cue_id": "b", "start_ms": 1000, "end_ms": 2000, "text": "مرحبا"}, {"cue_id": "a", "start_ms": 0, "end_ms": 900, "text": "Hello"}])
    vtt = exporter.export_webvtt([{"cue_id": "a", "start_ms": 0, "end_ms": 900, "text": "Hello"}])
    report = exporter.build_manifest([first, srt, vtt], [{"code": "RIGHTS_UNVERIFIED"}])
    assert report.status == "VALID" and any(item.relative_path == "export-manifest.json" for item in report.artifacts)


def test_renderer_dry_run_has_valid_blocked_and_invalid_states(tmp_path):
    asset = tmp_path / "asset.jpg"
    asset.write_bytes(b"asset")
    renderer = RendererDryRunAdapter(str(tmp_path))
    valid = renderer.dry_run({"assets": [{"asset_id": "a", "path": str(asset), "rights_status": "RIGHTS_VERIFIED"}], "tracks": {"visual": [{"start_ms": 0, "end_ms": 1000}]}, "dependencies": []})
    assert valid.status == "VALID" and valid.execution_plan.operations
    blocked = renderer.dry_run({"assets": [{"asset_id": "missing", "path": str(tmp_path / "missing.jpg"), "rights_status": "RIGHTS_UNVERIFIED"}]})
    assert blocked.status == "BLOCKED"
    invalid = renderer.dry_run({"assets": [{"asset_id": "outside", "path": str(Path(tmp_path).parent / "outside.jpg"), "rights_status": "RIGHTS_VERIFIED"}], "tracks": {"visual": [{"start_ms": 10, "end_ms": 0}]}})
    assert invalid.status == "INVALID"
