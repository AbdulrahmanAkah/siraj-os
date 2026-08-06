# SIRAJ Native Production Standard V2 — Stabilization and Migration

This migration is based on a forensic comparison of the live working tree and a
clean worktree at the same commit.

## Root causes closed

1. Series Production Quality V2 had modified legacy V1 editorial compiler
   contracts in place. This broke 112 tests in both the clean branch baseline
   and the live workspace.
2. The V2 storyboard was passed into the V1 media queue and montage pipeline.
   V1 expected 44 stills, 20 videos and 6 graphics. The approved V2 plan requires
   61 still panels, 137 provider video clips and 6 authored graphics across 70
   final shots.
3. Old provider assets and receipts were mixed with the new rebuild budget.
4. A shot-level Luna prompt was being reused as though it were an asset-level
   prompt.
5. Tracked Python bytecode and accumulated one-off audit files made the working
   tree noisy and fragile.

## New boundary

- Legacy V1 compiler, pricing and control contracts are restored and tested.
- Production Standard V2 uses a separate native asset planner and local runtime.
- The 70 Luna master certifications remain authoritative.
- Provider-level prompts are deterministic derivations from each Luna cinematic
  blueprint and carry their master response id and hashes.
- Every provider asset has one lock, one receipt and no hidden retry.
- The current production generation has its own hard-cap ledger. Historical
  legacy spend remains preserved and reported separately.
- The final runtime assembles 137 video clips, 61 still panels and 6 graphics
  into exactly 70 shot clips, then runs local audio, montage and QA.
- Production stops at the mandatory final human watch.

## Budget

The authorization amount is computed from the live queue:

- Runware video: 137 × 0.24 USD maximum
- Runware still panels: 61 × 0.04815 USD maximum
- ElevenLabs: remaining approved block reserve
- Automatic bounded technical repair: 0.15 USD

The total must remain below the 40 USD Production Standard V2 generation cap.
Historical V1 attempts are not erased; they are stored in the legacy-spend
report and excluded only from the new generation cap.

## Guarantees

No provider request is made by the migration. The migration runs:

- full Python compilation;
- the complete repository test suite;
- Qt desktop smoke;
- FFmpeg and FFprobe environment validation;
- live V2 asset-plan and queue validation;
- a cryptographic production gate.

Unknown future provider defects cannot be made impossible. Detected code, state,
schema, prompt, queue, budget and environment failures block before paid work.
