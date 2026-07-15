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

## RC Hardening Phase 2

`READY` — the selected provider is the single `OPENAI_COMPATIBLE` Responses
HTTP adapter. It supports declared text generation, structured output,
citation-aware output, and multilingual capability for `gpt-4.1-mini`.

| Artifact | Size (bytes) | SHA-256 |
| --- | ---: | --- |
| `siraj_os-0.1.0rc1-py3-none-any.whl` | 319585 | `960479a337903555f18e1481c330e241aec15184e5e246de04db8ca065603d31` |
| `siraj_os-0.1.0rc1.tar.gz` | 171269 | `96dd16923ec786f1e5e1a33b6fdf84d34000ef3427820bfd41ca2b5a525ed21a` |

- Focused Phase 2 verification: `3 passed`, with one explicit live-provider
  test deselected; complete offline suite: `275 passed, 1 skipped`.
- Recorded fixtures cover success, structured output, citation-bearing output,
  missing/fabricated citations, malformed response, refusal, timeout/rate
  limit/authentication error representations. They contain no credential or
  restricted data and execute without network access.
- Golden offline dataset descriptors cover small historical, medium
  documentary, and cross-era intelligence scenarios, including contradiction,
  false-pattern rejection, trend, theory, and counterfactual expectations.
- The gateway rejects fabricated references and contradicted critical claims;
  it records unsupported claims and injection signals for validation. Source
  text remains untrusted data and injection prevention is bounded, not claimed
  complete.
- Credential values are resolved only through central configuration, never by
  the provider adapter. `RESTRICTED` transmission is denied; no raw provider
  response is retained by default. No provider fallback or silent retry exists.
- Fresh wheel and sdist clean installs passed from `site-packages`; installed
  AI/dataset/release CLI smoke checks passed. Artifact scans found no secrets,
  absolute development paths, databases, caches, or temporary outputs.
- Static dependency scan confirms no domain layer calls the provider directly.
  Default tests execute no network request, subprocess, cloud service, or real
  provider call. `external_ai` remains explicit opt-in and skips safely.

Known limitations: only the OpenAI-compatible adapter is implemented; a live
test requires separately approved credentials and explicit policy setup; live
usage/request IDs and response text are excluded from deterministic replay.
The version remains `0.1.0-rc.1`; `1.0.0` is not declared.

## RC Hardening Phase 3 final readiness

`READY_WITH_LIMITATIONS` — all tested Windows-native mandatory local gates
pass, but this verification does not claim Linux, macOS, minimum-Python, or a
separately packaged historical pre-Phase-1 upgrade image.

| Artifact | Size (bytes) | SHA-256 |
| --- | ---: | --- |
| `siraj_os-0.1.0rc1-py3-none-any.whl` | 319585 | `f7e0bd1bd69d04f27c66153e0256d5a87c05a9435cf1fd81c14c9b370a7e514f` |
| `siraj_os-0.1.0rc1.tar.gz` | 171568 | `e5a1d45b53431bd34fe398b5ec693315cd73d5dca9e168e6f5945353729772c6` |

- Matrix tested: Windows native, Python `3.13.14`, clean wheel and sdist
  installation, local Unicode/UTF-8 paths and SQLite behavior. Linux, macOS,
  network filesystems, and other Python versions are unsupported/unverified.
- Phase 3 focused tests: `5 passed`; full suite: `280 passed, 1 skipped`.
  The skip is the explicit opt-in live-provider test. Default tests remained
  offline.
- Upgrade/recovery drill passed for explicit schema fixture
  `rc-hardening-v1 → rc-hardening-v2`: persist, snapshot, dry-run/apply
  migration, close/reopen, hash validation, and deterministic restore/export.
- Failure injection passed for corrupt payload, read-only SQLite, path escape,
  oversized export, missing/invalid renderer input, provider timeout, and
  restricted-data egress denial. Failures returned controlled statuses.
- Deterministic soak passed: 100 small golden-workflow iterations had one
  stable record ID, one stable export hash, no temporary-file accumulation,
  and no open adapter after context exit.
- Fresh wheel and sdist clean installs passed from `site-packages`; installed
  version, health, persistence, export, renderer, AI configuration, dataset,
  and release CLI checks passed. Artifact scan found no secrets, databases,
  caches, local paths, or temporary outputs. `git diff --check` passed.

Residual risks: no real live-provider execution, no Linux/macOS or multi-Python
matrix, no historical separately packaged pre-Phase-1 upgrade package, and no
full penetration-test or crash-recovery claim. Recommendation: retain
`0.1.0-rc.1` and create a new RC only after those matrix and historical-upgrade
gates are explicitly completed. `1.0.0` is not declared.
