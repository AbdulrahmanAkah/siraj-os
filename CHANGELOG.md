# Changelog

## [0.1.0-rc.2] - 2026-07-16

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
