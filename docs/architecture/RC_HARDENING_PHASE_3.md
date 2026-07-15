# RC Hardening Phase 3: Compatibility and Readiness Verification

## Compatibility freeze and tested matrix

The selected release identity is `0.1.0-rc.1` (`0.1.0rc1` in normalized
package metadata). Public API v1, CLI v2, configuration, plugin, persistence,
and AI gateway contracts are frozen for this phase.

| Dimension | Verified | Notes |
| --- | --- | --- |
| Operating system | Windows native | Windows 11 development host |
| Python | 3.13.14 | minimum, preferred, and latest tested host interpreter |
| Installation | wheel and source distribution | clean virtual environments outside repository |
| Filesystem | local NTFS-like filesystem | UTF-8, Unicode and contained path tests |
| SQLite | local create/reopen/read-only/transaction/migration | no network filesystem claim |
| AI provider | recorded transport offline | live adapter is opt-in only |

The package metadata declares `>=3.13`; Python 3.11 and 3.12 are not supported. Windows is the only supported operating system for this release.
Linux is deferred and macOS is not currently supported. This
verification. No PostgreSQL, cloud, distributed runtime, or real rendering is
included.

## Final Windows-only matrix-closure policy

The package-level support claim is `requires-python = >=3.13`, with Python
`3.13.14` tested on Windows. Python 3.11 and 3.12, Linux, and macOS are
outside the supported matrix for this RC.

The genuine historical source is Git tag `v0.1.0-rc.1`, commit `5d094b9`.
Its real wheel installs but its declared `siraj` entry point fails because the
artifact lacks `src.application`. It cannot create the requested historical
SQLite state. Therefore a genuine packaged pre-hardening migration lifecycle
is blocked rather than represented by the schema-only fixture.

## Upgrade and recovery scope

The explicit upgrade fixture is SQLite schema `rc-hardening-v1` to
`rc-hardening-v2`. The drill persists deterministic repository data, dry-runs
then applies migration, reopens with the new schema identity, validates payload
hashes, restores data, and repeats deterministic export. Unsupported paths and
read-only writes are denied. This does not claim general crash recovery.

## Threat model and residual risks

Trust boundaries include CLI/config input, credential references, plugin
metadata, SQLite payloads, export paths, render manifests, untrusted evidence,
provider responses, audit records, and release artifacts. Controls include
contained paths, atomic local writes, parameterized SQLite, payload hashes,
credential redaction, restricted-data egress denial, evidence citation
allowlists, and recorded offline provider tests.

Residual risks: live OpenAI-compatible behavior and
adversarial prompt injection are bounded but not exhaustively tested. Linux is deferred and macOS is unsupported for this RC. This is
not a full penetration-test claim.
