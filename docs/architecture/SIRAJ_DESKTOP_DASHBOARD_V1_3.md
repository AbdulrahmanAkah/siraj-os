# SIRAJ Desktop Dashboard v1.3

## Purpose

This release fixes the vertical collapse observed during the human review of
v1.2. The defect affected both the episode queue and the video preview even
though their theoretical widget sizes passed the previous headless test.

## Layout correction

The shared workspace `QScrollArea` has been removed. The dashboard now uses
two independent vertical scroll areas inside the horizontal splitter:

- `mainColumnScroll` for the episode queue, workflow, outputs, logs, and metrics.
- `utilityColumnScroll` for preview, episode details, and activities.

Both columns start at vertical position zero. Horizontal scrolling remains
disabled.

## Non-collapsible first panels

The first panel in each column has an explicit minimum height:

- Episode queue: 240 px.
- Preview panel: 315 px.
- Preview canvas: at least 169 px.

The main and utility content roots also have explicit natural minimum heights
so Qt scrolls the columns instead of compressing their children.

## Visual validation

The v1.3 smoke test validates:

1. Effective widget geometry after intersection with the real scroll viewport.
2. Visibility of the episode queue, active work row, preview title, status,
   panel, and 16:9 canvas.
3. Zero horizontal overflow in both column scroll areas.
4. Pixel diversity and expected dark/gold pixels in captured preview and queue
   images.
5. A complete 1366x768 screenshot.

## Execution boundary

Runware execution remains blocked. This release does not generate video and
does not spend provider credit.

## Offscreen visual validation correction

The queue pixel assertion is independent of font rendering. It validates the
effective viewport crop using dark-surface pixels, the gold border, color
bucket diversity, and luminance span. Missing fonts in the Qt offscreen plugin
therefore cannot create a false failure while geometry, tab state, and work-row
visibility remain strictly checked.
