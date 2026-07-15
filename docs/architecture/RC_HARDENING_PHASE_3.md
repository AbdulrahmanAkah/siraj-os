# RC Hardening Phase 3: Compatibility and Readiness Verification

## Compatibility freeze and tested matrix

The selected release identity is `0.1.0-rc.1` (`0.1.0rc1` in normalized
package metadata). Public API v1, CLI v2, configuration, plugin, persistence,
and AI gateway contracts are frozen for this phase.

| Dimension | Verified | Notes |
| --- | --- | --- |
| Operating system | Windows native | Windows 11 development host |
| Python | 3.13.14 | latest available host interpreter |
| Installation | wheel and source distribution | clean virtual environments outside repository |
| Filesystem | local NTFS-like filesystem | UTF-8, Unicode and contained path tests |
| SQLite | local create/reopen/read-only/transaction/migration | no network filesystem claim |
| AI provider | recorded transport offline | live adapter is opt-in only |

Linux and macOS are unverified and are not claimed as supported by this
verification. No PostgreSQL, cloud, distributed runtime, or real rendering is
included.

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

Residual risks: live OpenAI-compatible behavior, Linux/macOS behavior, and
adversarial prompt injection are bounded but not exhaustively tested. This is
not a full penetration-test claim.
