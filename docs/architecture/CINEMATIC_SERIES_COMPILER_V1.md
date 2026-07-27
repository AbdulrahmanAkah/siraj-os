# Cinematic Series Compiler v1

## Status

`OFFLINE_COMPILER_READY_RUNWARE_BLOCKED`

This layer turns an existing validated `Storyboard` into a deterministic
cinematic-series baseline. It does not contact Runware, estimate provider
prices, or spend media credit.

## Why this layer exists

The previous cinematic-series runtime validated a manually supplied plan. This
compiler closes the next gap: it creates the baseline plan automatically while
preserving storyboard frame identity, order, and evidentiary references.

The compiler is an editorial planning system, not an audience-emotion
prediction model. It verifies structural conditions that make anticipation
possible; it cannot guarantee that viewers will love an episode.

## Inputs

- A valid Siraj `Storyboard`
- An `EpisodeSeriesContract`
- Optional compilation policy
- Optional budget envelope

A complete cinematic arc requires at least seven storyboard frames.

## Deterministic narrative arc

The compiler assigns:

1. Cold open
2. Central question
3. Orientation when enough frames exist
4. Discovery
5. Escalation
6. Reversal
7. Climax
8. Consequence
9. Next-episode promise

The first frame remains the cold open. The final frame remains the continuation
promise. The closing frame calls back to the opening frame.

## Duration contract

- Minimum episode: **18 minutes**
- Default episode: **22 minutes**
- Maximum episode: **25 minutes**
- Default generated-video target: **150 seconds**
- Generated-video hard ceiling: **300 seconds**

The compiler distributes episode seconds by narrative weight and guarantees
that the total equals the configured target.

## Budget envelope

The default editorial reservation is:

- Images: **USD 8**
- Generated video: **USD 29**
- Audio: **USD 1**
- Retry reserve: **USD 2**
- Target total: **USD 40**
- Hard headroom: **USD 5**
- Absolute total: **USD 45**

These values are allocation ceilings, not provider-price predictions. Actual
Runware prices remain unavailable until the manual provider test records the
tested model, request, result, latency, and charged cost.

## Historical integrity

The compiler selects one evidence posture per frame:

- Documentary evidence when direct evidence references are present
- Evidence-based reconstruction for dramatic historical sequences supported by
  evidence
- Symbolic visualization when evidence references are absent
- Atmospheric transition for the opening and continuation promise

It never upgrades a frame without evidence into documentary evidence.

## Spectacle discipline

The baseline contains one peak: the climax.

Other frames are quiet, controlled, or elevated. This prevents constant visual
intensity from flattening the episode and consuming the media budget.

## Output

`CompiledCinematicEpisode` contains:

- A validated `CinematicStoryboardPlan`
- Deterministic frame directives
- Media treatments
- Generation priorities
- Planned episode duration
- Planned generated-video duration
- Budget envelope
- Anticipation score
- A stable JSON manifest
- Explicit live-execution prohibition

## Provider gate

The following remain fixed:

- `RUNWARE_EXECUTION_STATUS = BLOCKED_PENDING_MANUAL_PROVIDER_TEST`
- `live_execution_allowed = false`
- `provider_price_estimate_status = UNAVAILABLE_PENDING_MANUAL_PROVIDER_TEST`

## Editorial review requirement

The generated plan is a baseline. Before media generation, an editor must still
review:

- Whether the climax is attached to the correct historical event
- Whether the reversal is genuinely supported by the evidence
- Whether symbolic visualizations are ethically and religiously acceptable
- Whether the continuation question is strong enough for the next episode
- Whether any frame should receive an explicit override

## Next gate

After this compiler is installed:

1. Add a manifest adapter for real episode project files.
2. Compile the tracked storyboard for `episode-001-adam`.
3. Review and approve frame-level overrides.
4. Complete the manual Runware image test.
5. Add a guarded provider adapter and a 30–60 second proof sequence.
