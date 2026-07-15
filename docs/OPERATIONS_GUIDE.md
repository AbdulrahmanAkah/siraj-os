# Operator Guide

1. Validate configuration through `ApplicationConfig`.
2. Start `ApplicationBootstrap` and require `READY`.
3. Check `HealthArchitecture` before accepting work.
4. Use the `/v1` API contract or CLI v2 commands for release-facing operations.
5. Run deterministic diagnostics, migrations in dry-run mode, and release governance before packaging.

No secret value should be placed in configuration output, logs, release manifests, or audit records.
