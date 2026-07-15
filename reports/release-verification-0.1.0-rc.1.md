# SIRAJ 0.1.0-rc.1 Final Windows Release Verification

## Decision

`READY`

The selected version remains `0.1.0-rc.1`; package metadata normalizes this to
PEP 440 version `0.1.0rc1`. No `1.0.0` declaration or new RC was created.

## Support policy

- Supported OS: Windows only.
- Supported Python: Python 3.13.
- Tested Python: Python 3.13.14.
- Linux: not currently supported; deferred.
- macOS: not currently supported.
- Python 3.11 and 3.12: not supported.
- Docker and WSL were unavailable and no Linux claim is made.

## Final artifacts

| Artifact | Size (bytes) | SHA-256 | Scan | Clean install |
| --- | ---: | --- | --- | --- |
| `siraj_os-0.1.0rc1-py3-none-any.whl` | 319586 | `2502421c57b9a10ee2490364be375d1001aa3ad951357cb0355f4df49d28d3a3` | pass | pass |
| `siraj_os-0.1.0rc1.tar.gz` | 171399 | `2a302e33f1ca9ee200559449a7c54583588ed09a3e48298cd3947b5f26b2c3e3` | pass | pass |

Both artifacts declare `Name: siraj-os`, `Version: 0.1.0rc1`, and
`Requires-Python: >=3.13`. They contain no databases, caches, temporary
files, generated exports, credentials, secrets, development environments, or
absolute development paths.

## Verification gates

- Focused release and hardening tests: 5 passed.
- Full pytest suite: 280 passed, 1 skipped; the skip is the opt-in live AI
  test and default tests remain offline.
- Windows CLI smoke: version, health, configuration, persistence, export,
  renderer dry-run, AI validation, dataset validation, and release verify:
  passed.
- SQLite initialize/write/close/reopen/snapshot/restore: passed.
- Deterministic export and checksum verification: passed.
- Renderer dry-run lifecycle: passed.
- Recorded AI provider lifecycle: passed; no live provider required.
- Historical packaged upgrade: passed using `v0.1.0-rc.1-hardened.1` commit
  `863ef50`, wheel SHA-256
  `ad317a28c1e20e8871a9149af9e55f5fda2b5043cca4d6b509f87e19fecf53ac`, and
  sdist SHA-256
  `4ef1a934b3cbd28941ef207e302e4c5a2e42ff3d028cf1356211bbaac2c51d1e`.
- Upgrade migrated `rc-hardening-v1` to `rc-hardening-v2`, reopened the
  database, restored the original payload hash, and treated repeated migration
  as a no-op.
- Security boundary scan: no domain-to-adapter imports and no provider adapter
  environment reads.
- No network, subprocess renderer, cloud service, or real AI provider executed
  in default verification.
- `git diff --check`: passed; Windows line-ending notices only.

## Preserved limitations

- SQLite is the only persistence backend.
- Renderer is dry-run only; no real video rendering occurs.
- Live AI-provider execution remains opt-in.
- No full penetration-test coverage is claimed.
- No general crash-recovery guarantee is claimed beyond tested local paths.

Linux validation and Windows/Linux determinism comparison are not mandatory
release blockers because Linux is not a claimed platform for this release.
The final recommendation is `READY` for the Windows-only support policy.
