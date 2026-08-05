# SIRAJ Episode Cost Breakdown V1

This release adds a per-episode cost box to the SIRAJ desktop production
console.

## Displayed values

- Current episode identifier.
- Recorded total cost.
- Actual provider-reported cost.
- Estimated cost when the provider response exposes usage but not a settled
  invoice amount.
- Remaining amount under the USD 40 hard cap.
- Number of paid operations.
- Detailed category rows:
  - GPT-5.6 Luna / OpenAI
  - Runware images
  - Runware video
  - ElevenLabs narration
  - Sound effects
  - Other

The breakdown is receipt-driven and deduplicates provider operations by task
UUID, response ID, receipt ID, or path. Actual cost takes precedence over an
estimate within the same receipt.

## Luna scope cost

Luna usage for the active scope discussion is accumulated separately. When the
scope is approved, SIRAJ writes an episode-local cost receipt and resets the
active scope counter. This prevents a later episode from inheriting the prior
episode's Luna cost.

## Safety

- The full episode hard cap remains USD 40 with zero headroom.
- Installation, audit, and tests make no OpenAI, Runware, or ElevenLabs calls.
- The feature does not regenerate or modify existing paid media.
- Music remains forbidden.
