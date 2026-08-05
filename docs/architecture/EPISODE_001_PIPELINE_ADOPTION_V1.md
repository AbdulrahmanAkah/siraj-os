# Episode 001 Pipeline Adoption V1

This release connects the already human-approved `episode-001-adam` master to the current SIRAJ end-to-end production pipeline.

## Root cause

The autonomous orchestrator state had no valid `current_episode_id`. The dashboard therefore exposed a new-scope review gate, while the media page failed with `CURRENT_EPISODE_REQUIRED_FOR_MEDIA_EXECUTION`. The first episode itself remained present and approved, but it was produced before the canonical autonomous pipeline schemas existed.

## Adoption behavior

1. Detect the human-approved final script and storyboard paths from `contracts/episode-definition-v1.json`.
2. Verify the approved evidence package and human approval bindings.
3. Preserve every legacy file unchanged.
4. Back up the existing orchestrator state and any canonical compatibility files before replacement.
5. Build canonical compatibility artifacts for scope, evidence, script and the 70-shot storyboard without provider requests or editorial rewriting.
6. Map the approved 70 shots to the production constitution: 20 generated videos, 44 animated stills and 6 local graphics.
7. Build the standard media queue and budget preflight.
8. Set `current_episode_id=episode-001-adam` and continue through the normal consolidated paid authorization gate.

## Human and financial boundaries

The migration does not call OpenAI, Runware, ElevenLabs or YouTube. It does not bypass paid confirmation. It does not remove the final human review. Legacy hashes and paths are recorded in an adoption report.
