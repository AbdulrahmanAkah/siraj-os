# Automatic QA and Partial Repair V1

This is the third of the four final SIRAJ Production V1 packages.

## Purpose

The stage inspects the completed episode locally before the final human gate. It
verifies the seventy montage clips, the locked render plan, receipts and
SHA-256 values, the final container, stream layout, duration, audio profile,
black intervals, frozen intervals, silence and measured loudness.

The stage is deliberately evidence-bounded. It does not claim that local FFmpeg
checks can judge historical meaning, dramatic quality or visual truth. Those
remain part of `HUMAN_FINAL_REVIEW`.

## Defect classes

### Local shot repair

A missing, corrupt, stale or profile-invalid local montage clip invalidates only
that shot's output and receipt. SIRAJ calls the structural montage engine again;
all other valid shot receipts are reused.

### Local final remux

A final-container, receipt, stream-layout or locked-audio-hash defect removes
only the final mux outputs. The seventy valid shot clips are reused.

### Upstream media or audio defect

Missing provider media, excessive source black/freeze, loudness, true-peak or
long-silence defects are not silently regenerated. SIRAJ records the exact shot
or audio stage and stops. Any paid retry still requires explicit authorization.

## Policies

- Maximum local repair passes: two.
- Full regeneration for a local defect: forbidden.
- Automatic paid regeneration: forbidden.
- Music: forbidden.
- Provider requests during QA and local repair: zero.
- Local QA API cost: USD 0.00.

## Completion

A clean report advances the episode to `AWAITING_HUMAN_FINAL_REVIEW`. The next
package is `HUMAN_FINAL_REVIEW_AND_PUBLISHING_V1`.
