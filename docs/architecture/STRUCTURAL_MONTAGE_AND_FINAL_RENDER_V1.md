# Structural Montage and Final Render V1

This is the second of the four final SIRAJ Production V1 packages.

## Purpose

The package assembles the complete seventy-shot episode after all media and the
locked audio master are complete. It renders every shot to a uniform local
intermediate, concatenates the intermediates without another visual encode, and
then muxes the narration/SFX master as the only final audio source.

## Visual treatments

### Forty-four animated stills

A still is never held flat. SIRAJ builds a blurred full-frame background and a
clean fitted foreground layer, then applies one of eight deterministic motion
profiles: push, pull, horizontal pan, vertical pan, or diagonal movement.
Subtle grade and vignette are applied after motion.

### Twenty generated videos

Provider audio is stripped. The visual is normalized to 1920×1080 at 30 fps. If
the editorial duration is longer than the generated source, SIRAJ extends only
the last frame; it does not create an additional paid generation.

### Six local graphics

The rendered QML/FFmpeg graphic is normalized while preserving its authored
color design. No additional source audio is accepted.

## Editing language

Shots inside one sequence use direct cuts. Sequence boundaries receive a short
fade to black. This avoids seventy identical dissolves and keeps sequence
changes legible.

## Resume model

Each shot has a render fingerprint, receipt, input SHA-256, and output SHA-256.
An interrupted run reuses valid completed shot clips and renders only missing or
invalidated clips. No provider request occurs during montage or recovery.

## Delivery

The final output is H.264, 1920×1080, 30 fps, yuv420p with AAC 192 kbps,
48 kHz stereo. The file is written to:

`projects/<episode-id>/deliverables/episode-master-v1.mp4`

The completed render advances automatically to
`AUTOMATIC_QA_AND_PARTIAL_REPAIR_V1`.
