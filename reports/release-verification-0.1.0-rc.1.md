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
