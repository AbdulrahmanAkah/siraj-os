# Local Professional Graphics Engine V1

## Locked architecture

SIRAJ local graphics use a hybrid professional pipeline:

- PySide6 controls validated specifications, files, receipts, and execution.
- Qt Quick / QML renders deterministic motion and layered compositions.
- SVG and QML Canvas handle maps, paths, symbols, and vector geometry.
- FFmpeg encodes the numbered PNG frame sequence to H.264 MP4.
- Runware may supply an optional cinematic background only; factual text,
  dates, names, routes, and relationships remain locally rendered.

## Templates

The engine ships six deterministic templates:

1. Animated timeline.
2. Map route.
3. Relation tree.
4. Source card.
5. Comparison.
6. Location and time card.

Every template exposes `frameProgress` from 0 to 1. The Python controller sets
that value explicitly for every frame, so animation is reproducible and is not
dependent on wall-clock timing.

## Output

- 1920×1080.
- 30 frames per second.
- H.264, YUV420P.
- No music.
- API cost: USD 0.
- Optional Runware backgrounds are separate paid assets and must appear in the
  episode cost ledger.

## Runtime command

Environment preflight:

```powershell
python scripts\desktop\render_local_graphic_v1.py `
  --repo-root C:\SIRAJ\Repositories\siraj-os `
  --preflight-only
```

Render one validated specification:

```powershell
python scripts\desktop\render_local_graphic_v1.py `
  --repo-root C:\SIRAJ\Repositories\siraj-os `
  --spec path\to\graphics-spec.json `
  --output path\to\graphic.mp4
```

## Boundary

This release builds and validates the local engine. The next release connects
the six GRAPHICS storyboard shots to their full structured specifications,
production queue, dependency graph, and desktop progress display.
