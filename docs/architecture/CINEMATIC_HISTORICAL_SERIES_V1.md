# Cinematic Historical Series Architecture v1

## Status

`OFFLINE_RUNTIME_READY_RUNWARE_BLOCKED`

This layer converts an existing Siraj storyboard into a connected cinematic
historical-series plan. It does not turn uncertain reconstruction into fact,
and it does not contact Runware or spend provider credit.

## Product objective

Every episode must make three explicit promises:

1. **Knowledge promise** — the viewer leaves with a materially clearer
   understanding of the evidence.
2. **Emotional promise** — the episode creates awe, tension, loss, discovery,
   or consequence without fabricated melodrama.
3. **Continuation promise** — the final frame opens a necessary question for
   the next episode.

## Integration point

The cinematic layer is an overlay on `Storyboard`.

Every existing `StoryboardFrame` receives exactly one
`CinematicFrameDirective`. Frame order and frame identity cannot change at this
stage. This preserves the existing evidence and scene-planning pipeline while
adding cinematic structure.

## Required narrative functions

A valid episode must include:

- `COLD_OPEN`
- `CENTRAL_QUESTION`
- `CLIMAX`
- `NEXT_EPISODE_PROMISE`

The cold open must be first. The next-episode promise must be last. The climax
must occur before the closing promise.

Other supported functions are orientation, discovery, escalation, reversal,
and consequence.

## Viewer anticipation

Siraj does not claim to predict audience behavior. It validates structural
conditions that support continued viewing:

- A central question distinct from the next-episode question
- An exact handoff from one episode's closing question to the next episode
- A reversal or meaningful discovery where the evidence supports it
- A consequence larger than the isolated event
- A callback to an earlier frame where useful
- A quiet or controlled close after the climax

## Cinematic restraint

A normal episode may contain at most two `PEAK` frames. Constant spectacle is
rejected because contrast is required for impact.

## Historical integrity

Each directive declares one evidence posture:

- `DOCUMENTARY_EVIDENCE`
- `EVIDENCE_BASED_RECONSTRUCTION`
- `PLAUSIBLE_RECONSTRUCTION`
- `SYMBOLIC_VISUALIZATION`
- `ATMOSPHERIC_TRANSITION`

A `DOCUMENTARY_EVIDENCE` directive is invalid if the underlying storyboard
frame has no referenced evidence.

## Fixed production budget

- Target media cost: **USD 40**
- Absolute media cap: **USD 45**
- Accepted generated-video ceiling: **300 seconds**
- Five minutes is a ceiling, not a quota

## Runware gate

`RUNWARE_EXECUTION_STATUS` remains:

`BLOCKED_PENDING_MANUAL_PROVIDER_TEST`

This release contains no HTTP client, API key handling, image generation,
video generation, or billing operation.

## Next gate

After the manual Runware image test passes:

1. Record the tested model identifier, request fields, cost, latency, and seed.
2. Add a guarded Runware image adapter.
3. Map cinematic directives to budget-aware model routing.
4. Produce a 30–60 second proof sequence.
5. Review historical integrity, continuity, sound, pacing, and actual cost.
