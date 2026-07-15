# SIRAJ 0.1.0-rc.1 Release Verification

## Decision

`READY`

The selected public release version remains `0.1.0-rc.1`. PyPA normalizes
the equivalent PEP 440 package metadata and artifact filename version to
`0.1.0rc1`; this is not a declaration of `1.0.0`.

## Artifact verification

| Artifact | Size (bytes) | SHA-256 | Inspection |
| --- | ---: | --- | --- |
| `siraj_os-0.1.0rc1-py3-none-any.whl` | 306511 | `a94a116e7134f5576643874eb596b60b322429288e86f4423e69544c987a05b5` | pass |
| `siraj_os-0.1.0rc1.tar.gz` | 161159 | `1d4b82f23ed700cbfb4eb498988c8409706ee60d64b1181ba67829a968a68755` | pass |

Both artifacts declare `Name: siraj-os`, `Version: 0.1.0rc1`, and
`Requires-Python: >=3.11`. The final inventories contain 501 wheel members
and 671 source-distribution members. The inspection found no packaged legacy
test modules, environment files, caches, databases, temporary files, local
user paths, or common secret signatures.

## Installation verification

| Gate | Wheel | Source distribution |
| --- | --- | --- |
| Fresh environment | pass | pass |
| Install | pass | pass |
| Import from `site-packages` | pass | pass |
| Metadata name/version | `siraj-os` / `0.1.0rc1` | `siraj-os` / `0.1.0rc1` |
| `siraj version --json` | pass | pass |
| `siraj health --json` | pass | pass |
| `siraj config-validate --json` | pass | pass |
| `siraj release-verify --json` | pass | pass |

Each installed CLI command reports the selected public version
`0.1.0-rc.1`; package metadata uses its standard PEP 440 normalization.

## Regression and hygiene gates

- PyPA build frontend: `build 1.5.0`; build backend: `setuptools 83.0.0`.
- Wheel build with `python -m build --wheel --sdist --no-isolation`: pass.
- Source-distribution build with `python -m build --wheel --sdist --no-isolation`: pass.
- Focused Bundle I tests: `3 passed`.
- Full pytest suite: `268 passed`.
- Existing CLI smoke test: pass.
- CLI v2 smoke test: pass.
- `git diff --check`: pass (exit code 0; Windows line-ending notice only).

## Explicit non-blockers and limitations

- No real external providers, network services, or network-dependent default
  tests were introduced.
- The build frontend and setuptools were installed only in the dedicated local
  build environment, as required for packaging verification.
- The source-distribution installation used pip's isolated build environment
  for the declared setuptools backend; no runtime dependency was added.

There are no failed or unverified release gates for this release candidate.

## RC Hardening Phase 1

- Local SQLite persistence adapter: focused lifecycle, rollback, corruption,
  read-only, redaction, close/reopen, and snapshot tests passed.
- Deterministic file export adapter: UTF-8 JSON, Markdown, SRT, WebVTT,
  manifest, checksum, overwrite, traversal, and Unicode tests passed.
- Renderer dry-run adapter: stable operation planning and distinct `VALID`,
  `BLOCKED`, and `INVALID` tests passed; no subprocess is used.
- Focused RC hardening tests: `4 passed`; complete suite: `272 passed`.
- CLI thin-operation smoke: `siraj persistence init --json` passed.

RC Hardening Phase 1 does not change the selected version, add a real AI
provider, add cloud infrastructure, or declare `1.0.0`.

## RC Hardening Phase 1 re-verification

`READY` — all mandatory RC gates passed.

| Artifact | Size (bytes) | SHA-256 |
| --- | ---: | --- |
| `siraj_os-0.1.0rc1-py3-none-any.whl` | 315519 | `3869c44a43f7e1b8618fffc09137489ee3b5bfc542dd54af8dafa809fe28e146` |
| `siraj_os-0.1.0rc1.tar.gz` | 168349 | `50143146d602092007688eb0ca9c38c560e5f9e133133d90be7b26de4feaea9f` |

- Focused hardening tests: `4 passed`; full pytest suite: `272 passed`.
- Fresh wheel and sdist builds passed. Both artifacts contain `siraj-os`,
  `0.1.0rc1`, and `Requires-Python: >=3.11` metadata.
- Both artifact inventories and content scans found zero unintended files,
  SQLite databases, temporary outputs, local user paths, caches, or common
  credential/secret signatures.
- Wheel and sdist clean installs passed outside the repository. Installed
  import, version, health, configuration, persistence verification, export,
  renderer dry-run, and release verification CLI checks passed.
- Installed-wheel drills passed: SQLite save/snapshot/close/reopen/restore,
  dry-run and applied supported schema migration, deterministic re-export,
  and `VALID` renderer dry-run planning. Temporary test outputs were cleaned.
- Static checks found no environment reads in local adapters and no domain
  imports of SQLite, export, renderer, or CLI adapter implementations. The
  sole `subprocess` match is explanatory documentation; no executable
  subprocess, network client, cloud service, or real AI provider is invoked.
- `git diff --check`: pass (line-ending notices only).

Known limitations: SQLite is the sole real persistence backend; renderer
planning is dry-run only; no crash-safety claim is made beyond the tested
SQLite transaction and reopen/recovery paths. The selected release remains
`0.1.0-rc.1`; this verification does not declare `1.0.0`.
