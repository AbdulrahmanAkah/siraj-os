# SIRAJ Desktop Dashboard v1.2

## Purpose

This release applies the human live-review corrections to the PySide6 desktop dashboard without opening paid video execution.

## Bound changes

- The compact project hero is restored and placed outside the scroll area.
- The video preview panel has a hard minimum height and a responsive 16:9 canvas.
- Output rows show the filename only, with the complete repository-relative path in a tooltip and a dedicated open action.
- Activity rows use wrapped labels and fixed readable row height.
- Horizontal scrolling remains blocked at the workspace, tables, lists, and theme levels.
- Ready and work queues remain separate.

## Execution boundary

Runware API execution, automatic retries, and bulk production remain blocked. The next stage is human visual review of v1.2, followed by a separately bound Runware execution gate.

## Required visual smoke

The release publisher opens the window offscreen at 1366×768 and verifies:

- horizontal scrollbar maximum equals zero;
- compact hero is visible;
- preview panel height is at least 285 pixels;
- preview canvas height is at least 169 pixels;
- output labels contain filenames, not paths;
- activity labels have word wrapping enabled.
