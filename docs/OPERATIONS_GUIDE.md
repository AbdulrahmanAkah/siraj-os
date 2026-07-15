# Operator Guide

1. Validate configuration through `ApplicationConfig`.
2. Start `ApplicationBootstrap` and require `READY`.
3. Check `HealthArchitecture` before accepting work.
4. Use the `/v1` API contract or CLI v2 commands for release-facing operations.
5. Run deterministic diagnostics, migrations in dry-run mode, and release governance before packaging.

No secret value should be placed in configuration output, logs, release manifests, or audit records.

## RC local infrastructure

Configure an explicit SQLite path and export root through `ApplicationConfig`.
Run `siraj persistence init`, `siraj export build`, and `siraj render dry-run`
only through the policy-aware application boundary. Local exports are UTF-8,
deterministic, root-contained, and non-overwriting by default. Renderer output
is a dry-run plan; it does not render media.

## AI provider hardening

The only real adapter is the OpenAI-compatible HTTP adapter. It is disabled by
default. Use `siraj ai providers`, `siraj ai models`, and `siraj ai
validate-config` to inspect the thin application surface without exposing a
credential. External execution requires an explicit credential reference,
allowlisted model, and egress policy; `RESTRICTED` data is denied. Default
tests use recorded fixtures and never contact a provider.
