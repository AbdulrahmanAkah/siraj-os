# Automatic Research, Script, and Storyboard Runner V1

## Scope

This release implements the first autonomous downstream production chain after
the creator approves the topic and event set:

1. Evidence research with GPT-5.6 Luna and hosted web search.
2. Evidence-bound Arabic script writing.
3. A strict 70-shot storyboard and media plan.

No additional human gate is inserted. The two existing gates remain:

- Human scope review.
- Human final review.

## Durable outputs

For every approved episode the runner creates:

- `research/evidence-package-v1.json`
- `script/episode-script-v1.json`
- `cinematic/storyboard-and-media-plan-v1.json`
- `orchestration/editorial-runner-state-v1.json`
- Provider-response envelopes for crash recovery.
- One OpenAI cost receipt per completed stage.

## Recovery and paid-call safety

A provider response is persisted before the derived artifact is committed. When
the application is interrupted after a paid response, resume consumes the saved
response instead of sending the same stage again.

The runner performs no automatic HTTP retry. A transient provider or network
error stops the pipeline and exposes an explicit resume action in the desktop
UI.

## Evidence law

- The research stage alone receives web-search access.
- The script stage receives only the approved scope and evidence package.
- Excluded claims are forbidden in the script.
- Qualified claims must retain qualification language.
- Every script segment records claim and source identifiers.

## Fixed media law

The storyboard contains exactly:

- 70 editorial shots.
- 20 generated-video shots at 8 seconds each.
- 44 animated-still/compositing shots.
- 6 graphics shots.
- 160 generated-video seconds.

Music, musical score, and songs remain forbidden. Scene-appropriate sound
effects remain allowed. A flat slideshow is forbidden.

## Current boundary

This release ends with `BUDGET_PREFLIGHT` queued. Runware image/video queues,
ElevenLabs TTS, SFX execution, montage, and final QA remain the following
production stage.
