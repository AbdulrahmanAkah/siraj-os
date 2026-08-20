# SIRAJ Full Repository Regression Closure V1

## Decision

`SYSTEM_READY_FOR_NEXT_EPISODE=YES`

`FINAL_DECISION=READY_FOR_NEXT_EPISODE`

## What caused the 76% hang?

The Shorts engine required profile version `1.2.0`, while the canonical tracked profile and schema were `1.1.0`. Desktop fail-soft startup consequently omitted the Shorts dock. Offscreen navigation then entered a synchronous `QMessageBox.warning` with no operator to dismiss it.

## Which exact node hung?

`tests/integration/test_shorts_desktop_ux_screenshots_v1.py::test_short_ux_screenshots_are_captured_locally`

The minimal trigger is that node alone under the invalid-profile state. No predecessor is required. No second hang was found.

## What failed and how was it classified?

The prior quiet interrupted run emitted 30 failure markers and 12 setup-error markers but did not persist a complete per-node summary. Direct reproduction and segmented execution identified every root-cause family:

- Shorts profile drift and its Desktop effects: pre-existing real repository defect (B), plus the modal hang (F).
- Old Shorts storage assertion after intentional ready-episode migration: obsolete test expectation (D).
- Missing visual-context source relevance in a fixture: obsolete/incomplete fixture (D).
- Old OpenAI request-shape assertion: obsolete test expectation after intentional bounded contract change (D).
- Generic provenance error before the specific citation gate: pre-existing real defect (B).
- Shared Windows wheel build directory collision (`WinError 183`): test-environment defect (C), producing nine dependent setup errors.

All 1,157 configured nodeids subsequently passed or reached the one documented live-provider skip. No manual-visual-mission-caused failure was found.

## What changed?

- Rebound Shorts engine validation to the canonical profile/schema version.
- Preserved legacy episode compatibility for the explicitly revalidated `1.0.0` and `1.1.0` contracts.
- Restored the specific uncited-web-source rejection taxonomy.
- Completed the canonical-reference fixture's source relevance evidence.
- Updated request-contract assertions to the intentional bounded request.
- Updated the old Shorts storage assertion to the shared ready-episode archive authority.
- Isolated wheel builds in a temporary source directory to eliminate shared `build` contamination.

No test was deleted. No skip or xfail was added. No safety gate, SHA check, provider boundary, or fail-closed invariant was weakened. Constitution files were not modified by this closure.

## Validation

- Previous 54-test manual matrix: covered by a 56-test reconstructed superset and the full suite; PASS.
- Clean manual-visual E2E: PASS, including handoff, ingest, asset lock, assembly, separated QA, human-review receipt, master, Shorts compatibility, archive, replacement invalidation, and historical-master preservation.
- Shorts integration: 101 passed.
- Legacy relevant regression: PASS.
- Canonical-reference regression: PASS.
- Segmented full suite: 1,156 passed, 1 skipped, 0 failed, 0 hangs.
- Full pytest run 1: `1156 passed, 1 skipped, 1 warning in 159.86s`.
- Full pytest run 2: `1156 passed, 1 skipped, 1 warning in 151.18s`.
- The single skip is the existing live-provider verification requiring explicit credentials and opt-in.
- Repeatability matrix: 80 passed.
- Independent adversarial audit: PASS.

## New pipeline status

- `CANONICAL_VISUAL_MODE=MANUAL_USER_PRODUCTION`
- `PREVISUAL_PIPELINE=PASS`
- `MANUAL_VISUAL_HANDOFF=PASS`
- `MANUAL_VISUAL_INGEST=PASS`
- `POST_INGEST_ASSEMBLY=PASS`
- `FINAL_QA_PIPELINE=PASS`
- `MASTER_PIPELINE=PASS`
- `NEW_EPISODE_PAID_VISUAL_GENERATION=DISABLED`
- `NEW_EPISODE_PROVIDER_VISUAL_FALLBACK=DISABLED`
- `PAID_VISUAL_CALLS=0`
- `PRODUCTION_PROVIDER_CALLS=0`

## Residual observation

The invalid-profile Desktop fallback still uses a synchronous message box. It is outside the valid canonical path and is a low-priority hardening opportunity, not a release blocker.

Commit and push were not performed, as required.
