"""Local, side-effect-controlled infrastructure adapters for RC hardening."""

from .file_export import (
    ExportArtifactResult,
    ExportFailure,
    ExportIntegrityReport,
    ExportOverwritePolicy,
    ExportPathPolicy,
    FileExportAdapter,
)
from .renderer_dry_run import (
    RenderArgument,
    RenderDependencyCheck,
    RenderDryRunReport,
    RenderExecutionPlan,
    RenderOperation,
    RendererDryRunAdapter,
)
from .sqlite_persistence import (
    SQLiteConnectionConfig,
    SQLiteIntegrityIssue,
    SQLiteMigrationRecord,
    SQLitePersistenceAdapter,
    SQLiteRecoveryResult,
    SQLiteSchemaIdentity,
    SQLiteTransactionResult,
)

__all__ = [
    "ExportArtifactResult", "ExportFailure", "ExportIntegrityReport",
    "ExportOverwritePolicy", "ExportPathPolicy", "FileExportAdapter",
    "RenderArgument", "RenderDependencyCheck", "RenderDryRunReport",
    "RenderExecutionPlan", "RenderOperation", "RendererDryRunAdapter",
    "SQLiteConnectionConfig", "SQLiteIntegrityIssue", "SQLiteMigrationRecord",
    "SQLitePersistenceAdapter", "SQLiteRecoveryResult", "SQLiteSchemaIdentity",
    "SQLiteTransactionResult",
]
