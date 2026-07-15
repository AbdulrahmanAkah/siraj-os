"""SQLite implementation behind generic persistence payload contracts.

Only this module imports :mod:`sqlite3`; domain models remain storage agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3
from typing import Any, Iterable

from src.application.operations_common import CANONICAL_TIMESTAMP, canonical_payload, deterministic_id, integrity_hash
from src.application.security import SecurityPolicyEngine

from .security import SecurityBoundaryError, redact_sensitive


@dataclass(frozen=True)
class SQLiteConnectionConfig:
    database_path: str
    read_only: bool = False
    timeout_seconds: float = 5.0
    maximum_payload_size: int = 1_000_000


@dataclass(frozen=True)
class SQLiteSchemaIdentity:
    schema_name: str = "siraj_local_persistence"
    schema_version: str = "rc-hardening-v1"


@dataclass(frozen=True)
class SQLiteMigrationRecord:
    migration_id: str
    source_version: str
    target_version: str
    applied: bool
    dry_run: bool


@dataclass(frozen=True)
class SQLiteTransactionResult:
    transaction_id: str
    committed: bool
    record_ids: list[str]
    error_code: str | None = None


@dataclass(frozen=True)
class SQLiteIntegrityIssue:
    issue_id: str
    code: str
    record_id: str


@dataclass(frozen=True)
class SQLiteRecoveryResult:
    recovery_id: str
    restored: dict[str, Any]
    issues: list[SQLiteIntegrityIssue]
    status: str


class SQLitePersistenceAdapter:
    """Transactional local persistence with deterministic JSON serialization."""

    def __init__(self, config: SQLiteConnectionConfig, schema: SQLiteSchemaIdentity | None = None, policy: SecurityPolicyEngine | None = None):
        self.config = config
        self.schema = schema or SQLiteSchemaIdentity()
        self.policy = policy or SecurityPolicyEngine()
        self.connection: sqlite3.Connection | None = None

    def open(self) -> "SQLitePersistenceAdapter":
        path = Path(self.config.database_path)
        if not path.is_absolute():
            raise SecurityBoundaryError("DATABASE_PATH_MUST_BE_EXPLICIT")
        if self.config.read_only:
            if not path.exists():
                raise FileNotFoundError("READ_ONLY_DATABASE_NOT_FOUND")
            uri = f"file:{path.as_posix()}?mode=ro"
            self.connection = sqlite3.connect(uri, uri=True, timeout=self.config.timeout_seconds)
        else:
            decision = self.policy.decide("WRITE")
            if decision.decision != "ALLOW":
                raise PermissionError("FILESYSTEM_WRITE_DENIED")
            path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(str(path), timeout=self.config.timeout_seconds)
        self.connection.row_factory = sqlite3.Row
        return self

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def __enter__(self) -> "SQLitePersistenceAdapter":
        return self.open()

    def __exit__(self, *_: object) -> None:
        self.close()

    def _db(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("DATABASE_NOT_OPEN")
        return self.connection

    def initialize(self) -> SQLiteSchemaIdentity:
        db = self._db()
        if self.config.read_only:
            row = db.execute("SELECT value FROM schema_metadata WHERE key = ?", ("schema_version",)).fetchone()
            if row is None or row["value"] != self.schema.schema_version:
                raise ValueError("INVALID_SCHEMA_VERSION")
            return self.schema
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS schema_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            row = db.execute("SELECT value FROM schema_metadata WHERE key = ?", ("schema_version",)).fetchone()
            if row is not None and row["value"] != self.schema.schema_version:
                raise ValueError("INVALID_SCHEMA_VERSION")
            db.execute("INSERT OR IGNORE INTO schema_metadata(key, value) VALUES (?, ?)", ("schema_name", self.schema.schema_name))
            db.execute("INSERT OR IGNORE INTO schema_metadata(key, value) VALUES (?, ?)", ("schema_version", self.schema.schema_version))
            db.execute("CREATE TABLE IF NOT EXISTS persisted_records (record_id TEXT PRIMARY KEY, record_type TEXT NOT NULL, artifact_id TEXT NOT NULL, payload TEXT NOT NULL, payload_hash TEXT NOT NULL, created_at TEXT NOT NULL)")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS persisted_records_type_artifact_hash ON persisted_records(record_type, artifact_id, payload_hash)")
            db.execute("CREATE TABLE IF NOT EXISTS migration_records (migration_id TEXT PRIMARY KEY, source_version TEXT NOT NULL, target_version TEXT NOT NULL, applied INTEGER NOT NULL, created_at TEXT NOT NULL)")
        return self.schema

    def _serialise(self, payload: Any) -> tuple[str, str]:
        safe_payload = redact_sensitive(payload)
        text = canonical_payload(safe_payload)
        if len(text.encode("utf-8")) > self.config.maximum_payload_size:
            raise ValueError("PAYLOAD_TOO_LARGE")
        return text, integrity_hash(safe_payload)

    def save(self, record_type: str, artifact_id: str, payload: Any) -> SQLiteTransactionResult:
        return self.save_many([(record_type, artifact_id, payload)])

    def save_many(self, records: Iterable[tuple[str, str, Any]]) -> SQLiteTransactionResult:
        db = self._db()
        if self.config.read_only:
            return SQLiteTransactionResult("transaction_read_only", False, [], "READ_ONLY_DATABASE")
        prepared: list[tuple[str, str, str, str, str]] = []
        try:
            for record_type, artifact_id, payload in records:
                text, payload_hash = self._serialise(payload)
                record_id = deterministic_id("sqlite_record", [record_type, artifact_id, payload_hash])
                prepared.append((record_id, record_type, artifact_id, text, payload_hash))
            with db:
                for record_id, record_type, artifact_id, text, payload_hash in prepared:
                    db.execute("INSERT OR IGNORE INTO persisted_records(record_id, record_type, artifact_id, payload, payload_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)", (record_id, record_type, artifact_id, text, payload_hash, CANONICAL_TIMESTAMP))
            return SQLiteTransactionResult(deterministic_id("sqlite_transaction", [item[0] for item in prepared]), True, [item[0] for item in prepared])
        except (TypeError, ValueError, sqlite3.Error) as error:
            db.rollback()
            return SQLiteTransactionResult(deterministic_id("sqlite_transaction_failure", [str(error)]), False, [], "TRANSACTION_ROLLED_BACK")

    def restore(self, record_id: str) -> SQLiteRecoveryResult:
        row = self._db().execute("SELECT payload, payload_hash FROM persisted_records WHERE record_id = ?", (record_id,)).fetchone()
        if row is None:
            issue = SQLiteIntegrityIssue(deterministic_id("sqlite_issue", [record_id, "MISSING_RECORD"]), "MISSING_RECORD", record_id)
            return SQLiteRecoveryResult(deterministic_id("sqlite_recovery", [record_id, issue.code]), {}, [issue], "INVALID")
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            issue = SQLiteIntegrityIssue(deterministic_id("sqlite_issue", [record_id, "MALFORMED_PAYLOAD"]), "MALFORMED_PAYLOAD", record_id)
            return SQLiteRecoveryResult(deterministic_id("sqlite_recovery", [record_id, issue.code]), {}, [issue], "INVALID")
        if integrity_hash(payload) != row["payload_hash"]:
            issue = SQLiteIntegrityIssue(deterministic_id("sqlite_issue", [record_id, "CORRUPTED_PAYLOAD_HASH"]), "CORRUPTED_PAYLOAD_HASH", record_id)
            return SQLiteRecoveryResult(deterministic_id("sqlite_recovery", [record_id, issue.code]), {}, [issue], "INVALID")
        return SQLiteRecoveryResult(deterministic_id("sqlite_recovery", [record_id, row["payload_hash"]]), {record_id: payload}, [], "VALID")

    def persist_snapshot(self, snapshot_id: str, payload: Any) -> SQLiteTransactionResult:
        return self.save("SNAPSHOT", snapshot_id, payload)

    def persist_version(self, version_id: str, payload: Any) -> SQLiteTransactionResult:
        return self.save("VERSION", version_id, payload)

    def persist_audit(self, audit_id: str, payload: Any) -> SQLiteTransactionResult:
        return self.save("AUDIT", audit_id, payload)

    def persist_repository(self, record_id: str, payload: Any) -> SQLiteTransactionResult:
        return self.save("REPOSITORY", record_id, payload)

    def persist_documentary(self, package_id: str, payload: Any) -> SQLiteTransactionResult:
        return self.save("DOCUMENTARY", package_id, payload)

    def persist_production(self, package_id: str, payload: Any) -> SQLiteTransactionResult:
        return self.save("PRODUCTION", package_id, payload)

    def persist_ai_audit(self, audit_id: str, payload: Any) -> SQLiteTransactionResult:
        return self.save("AI_AUDIT", audit_id, payload)

    def migrate_schema(self, target_version: str, dry_run: bool = True) -> SQLiteMigrationRecord:
        source = self.schema.schema_version
        migration_id = deterministic_id("sqlite_migration", [source, target_version])
        if target_version == source:
            return SQLiteMigrationRecord(migration_id, source, target_version, False, dry_run)
        if not target_version.startswith("rc-hardening-"):
            raise ValueError("UNSUPPORTED_MIGRATION_PATH")
        if dry_run:
            return SQLiteMigrationRecord(migration_id, source, target_version, False, True)
        if self.config.read_only:
            raise PermissionError("READ_ONLY_DATABASE")
        db = self._db()
        with db:
            db.execute("UPDATE schema_metadata SET value = ? WHERE key = ?", (target_version, "schema_version"))
            db.execute("INSERT INTO migration_records(migration_id, source_version, target_version, applied, created_at) VALUES (?, ?, ?, ?, ?)", (migration_id, source, target_version, 1, CANONICAL_TIMESTAMP))
        self.schema = SQLiteSchemaIdentity(self.schema.schema_name, target_version)
        return SQLiteMigrationRecord(migration_id, source, target_version, True, False)
