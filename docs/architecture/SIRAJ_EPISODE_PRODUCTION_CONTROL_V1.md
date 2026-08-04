# SIRAJ Episode Production Control V1

## Hard rules

- Maximum complete episode cost: **USD 40.00**
- No headroom and no override
- Generated-video target: **120–180 seconds**
- Adam default plan: **160 seconds**
- 70 editorial shots are not 70 generated videos
- Adam mix: 20 generated-video shots, 44 animated-still/compositing shots,
  and 6 authored-graphics shots
- Music, musical score, and songs are forbidden
- Scene-appropriate sound effects are allowed without a type restriction
- Flat slideshow treatment is forbidden
- Human review remains one integer from 0 to 100; 80 is the pass threshold
- Every paid attempt requires an explicit desktop click
- Hidden paid retries are forbidden

## Budget gate

Before every new paid provider submission, Siraj scans durable project receipts,
deduplicates them by task UUID, adds the maximum expected cost of the proposed
request, and blocks the request if the projected total exceeds USD 40.

Recovery of an already submitted task does not create another paid request.

## Desktop UI

The video section now contains:

1. **خطة الحلقة** — the 70-shot hybrid queue, budget spent and remaining,
   the exact media mix, the no-music rule, and the next planned video shot.
2. **إنتاج المقطع** — the existing one-click generation, output actions, and
   one-number human review.

This release does not bulk-generate the remaining episode. The next stage is to
author and bind the next selected queue shot package, then generalize the
existing guarded generator across the 20 planned video slots.
