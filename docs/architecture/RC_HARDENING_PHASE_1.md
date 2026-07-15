# RC Hardening Phase 1

SIRAJ remains `0.1.0-rc.1`. This phase adds only local infrastructure
adapters around the existing Bundle D, F, and I contracts.

## Boundaries

- `rc_hardening.sqlite_persistence` is the only RC adapter with SQL; it
  stores canonical, redacted JSON payloads transactionally with explicit
  schema identity and SHA-256 integrity checks.
- `rc_hardening.file_export` writes deterministic UTF-8 JSON, Markdown,
  SRT, WebVTT, credits, source appendix, and actual-artifact manifests below
  an explicit root. It rejects traversal and does not overwrite by default.
- `rc_hardening.renderer_dry_run` validates a render manifest and emits a
  neutral operation plan. It never executes FFmpeg, a subprocess, or network
  activity.

Dependency direction is application contracts -> local adapters -> Python
standard library. Domain layers do not import SQLite, filesystem, or render
implementation types.

## Recovery and migration

Snapshots, versions, audit records, repository records, documentary/production
packages, and redacted AI audit payloads can be stored as typed record classes.
Restore verifies payload hashes. Migration begins as an explicit dry-run and
only applies supported `rc-hardening-*` schema paths. This phase does not claim
crash safety beyond SQLite transactions and the tested reopen/recovery flow.

## Operator notes

Use explicit `persistence.sqlite.path`, `export.output_root`, and
`renderer.allowed_asset_root` configuration values. SQLite is the only real
persistence adapter; PostgreSQL is not implemented. The renderer is dry-run
only. No real video rendering, AI provider, network access, or cloud service
is included.
