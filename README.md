# SIRAJ OS

SIRAJ is a deterministic historical-intelligence and documentary-production architecture.

Support policy: Windows only, with Python 3.13. The tested interpreter is
Python 3.13.14. Linux is deferred and not currently supported; macOS is not
currently supported. SQLite is local-only and rendering remains dry-run.

## Release candidate

The current release candidate is `0.1.0-rc.1`. Use `python -m src.application.cli_v2 health` for a local health command. Configuration is loaded only through the typed release configuration boundary; sensitive values use references and are redacted from public views.

## Supported platform

- Operating system: Windows only.
- Python: 3.13.
- Tested interpreter: Python 3.13.14.
- Linux: deferred and not currently supported.
- macOS: not currently supported.

## Safety

Default tests are local and deterministic. External provider, network, subprocess, rendering, and credential operations require explicit policy approval and are not enabled by default.
