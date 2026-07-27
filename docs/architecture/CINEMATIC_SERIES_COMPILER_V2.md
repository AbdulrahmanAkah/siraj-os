# Dynamic Cinematic Budget Planner v1

## Status

`OFFLINE_EDITORIAL_BLUEPRINT_READY_PRICED_ALLOCATION_DEFERRED`

This revision removes the fixed category split from the cinematic compiler.
Siraj no longer reserves a predetermined amount for images, video, audio, or
retries.

## Fixed constraints

Only these values are fixed:

- Target episode media cost: **USD 40**
- Absolute hard cap: **USD 45**
- Generated-video hard ceiling: **300 seconds**
- Live provider execution remains blocked

## Editorial compiler

The compiler now produces a blueprint rather than a spending plan. Every frame
contains:

- preferred treatment
- allowed alternative treatments
- motion need
- generation priority
- narrative reason
- maximum acceptable generated-video duration

The compiler allocates **zero** generated-video seconds before priced options
exist. A preference for video is not a purchase decision.

## Dynamic budget planner

The planner receives priced media options after provider testing. It chooses one
eligible option per frame while maximizing weighted quality and reliability
under the selected budget limit.

Category totals are computed from the selected options. They are outputs, not
inputs. Two episodes may therefore spend very different amounts on video,
images, maps, local animation, sound, or repair.

## USD 45 headroom

The planner uses USD 40 by default. The USD 45 hard cap is available only when:

1. hard headroom is explicitly enabled, and
2. a non-empty justification is recorded.

Planning does not authorize payment or provider execution.

## Global production costs

Narration, music, sound design, repair, or other episode-wide costs can be
supplied as priced fixed production items. They reduce the remaining budget
before visual options are optimized. No default amount is assigned to them.

## Runware gate

Runware remains blocked pending the manual provider test. The planner can be
tested with offline fixtures, but real provider prices must carry a price source
identifier before they are used in production planning.
