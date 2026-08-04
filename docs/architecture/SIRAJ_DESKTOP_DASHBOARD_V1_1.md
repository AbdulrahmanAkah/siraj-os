# SIRAJ Desktop Dashboard v1.1

## Purpose

This release refines the first SIRAJ Windows desktop dashboard after direct human review of the running application. It keeps the approved dark navy and gold visual direction while correcting layout, semantics, and production-state presentation.

## Bound corrections

- Prevent horizontal scrolling at the workspace and episode-table levels.
- Use a responsive horizontal splitter between the main production workspace and the preview/details column.
- Preserve the approved composition with navigation on the left and preview/details on the right while keeping Arabic RTL inside content areas.
- Separate episodes into `ready for conversion` and `work in progress` queues.
- Render a clear empty state when no episode is ready for conversion.
- Count only real generated states or real MP4 files as generated clips. `PLANNED_NOT_GENERATED` must never increment the generated counter.
- Present planned, generated, and approved shot counts as distinct metrics.
- Read the current generation beat from the latest shot package.
- Keep the preview at a 16:9 aspect ratio and show shot, beat, and video state.
- Wrap execution logs and elide long file/activity names without horizontal overflow.
- Replace mixed Unicode/emoji navigation symbols with internally rendered SVG icons.
- Bind workflow stage appearance to the active episode rather than a fixed static strip.

## Safety boundary

This release does not call Runware and cannot spend provider credit. Video execution remains blocked until a later binding explicitly connects a human-approved shot package to a single-use API execution gate.

## Runtime

- Python 3.13
- PySide6 6.10 or later, below 7
- Windows desktop
- Repository-derived episode data

## Launch

```powershell
& "C:\SIRAJ\Repositories\historical-fixture-venv-20260716\Scripts\python.exe" `
  "C:\SIRAJ\Repositories\siraj-os\scripts\desktop\launch_siraj_desktop.py" `
  --repo-root "C:\SIRAJ\Repositories\siraj-os"
```

## Next stage

`HUMAN_UI_REVIEW_V1_1_AND_RUNWARE_EXECUTION_BINDING`
