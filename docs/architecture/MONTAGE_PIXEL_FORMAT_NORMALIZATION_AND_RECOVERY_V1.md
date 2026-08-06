# Montage Pixel Format Normalization and Recovery V1

This release makes every structural-montage shot compatible with the locked delivery profile: H.264, 1920×1080, 30 fps and `yuv420p`.

## Behavior

1. Render with explicit H.264 High profile, level 4.1, limited range and BT.709 metadata.
2. Convert the filter graph to limited-range `yuv420p` before encoding.
3. Probe every local shot immediately after render.
4. If the encoder still emits a different pixel format, perform one local normalization pass and validate again.
5. Archive stale invalid `.rendering.mp4` files and resume from the first incomplete shot.
6. Preserve all completed paid media, local outputs with valid receipts, TTS files and provider receipts.

The recovery performs no provider request and does not reset paid media items.
