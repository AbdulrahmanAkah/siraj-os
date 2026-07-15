# SIRAJ OS

SIRAJ is a deterministic historical-intelligence and documentary-production architecture.

## Release candidate

The current release candidate is `0.1.0-rc.1`. Use `python -m src.application.cli_v2 health` for a local health command. Configuration is loaded only through the typed release configuration boundary; sensitive values use references and are redacted from public views.

## Safety

Default tests are local and deterministic. External provider, network, subprocess, rendering, and credential operations require explicit policy approval and are not enabled by default.
