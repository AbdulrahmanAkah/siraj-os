# Local Graphics Subprocess Isolation V1

## Problem

The desktop completion command already runs inside a `QThread`, but local
graphics rendering creates `QQuickView` and reuses the process-wide
`QGuiApplication`. Qt GUI and Qt Quick objects must remain owned by the GUI
thread. Creating them from the completion worker can stall the Windows event
loop and show the application as **Not Responding**.

## Resolution

Every local graphics item is rendered by a dedicated Python child process.
The child receives `QT_QPA_PLATFORM=offscreen`, `QT_QUICK_BACKEND=software`
and `QSG_RHI_BACKEND=software` before importing PySide6. It owns an isolated
`QGuiApplication`, renders the QML frames, encodes the MP4 and writes the
existing receipt and queue state. The desktop `QThread` only waits for the
child and emits progress signals; the main event loop stays responsive.

## Safety

- Completed Runware, ElevenLabs and local outputs are preserved.
- No provider request is made by migration or recovery.
- Incomplete local output without a valid receipt is archived before rerender.
- Paid retries and authorization rules are unchanged.
- The standard end-to-end resume router continues from the first incomplete
  queue item.
