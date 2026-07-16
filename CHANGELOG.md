# Changelog

## [0.1.0] - 2026-07-16

### Added

- First stable Siraj OS release.
- Deterministic local project initialization and persistence.
- Source registration, ingestion, knowledge extraction, claim assessment, and research planning.
- Release verification, recovery, migration, export, and operational CLI contracts.

### Reliability

- Reproducible wheel build with matching SHA-256 hashes.
- Clean non-editable installation verified outside the repository.
- Atomic local storage and recovery hardening validated.
- Schema compatibility and upgrade behavior validated.
- Unicode and Arabic subprocess behavior validated.

### Verification

- 346 tests passed and 1 test skipped.
- Published wheel acceptance tested through project initialization, ingestion, extraction, assessment, research planning, and verification.

## [0.1.0-rc.3] - 2026-07-16

### Added

- Deterministic project ingestion, knowledge extraction, assessment, and research planning.
- Packaging, clean-install, Unicode, recovery, storage, and schema compatibility gates.
- Release artifact manifest and SHA-256 checksums.

### Fixed

- Arabic JSON corruption through Windows PowerShell pipelines.
- Atomic-write cleanup and persistence failure propagation.
- Unsupported and missing schema handling.
- Installed-wheel execution outside the source repository.

### Verification

- 346 tests passed and 1 test skipped.
- Non-editable clean-wheel installation verified.
- Installed CLI health and version smoke tests verified.
- Reproducible wheel build verified.
