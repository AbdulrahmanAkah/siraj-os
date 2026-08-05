# Desktop Media Execution V1

This release turns the prepared media queue into an explicit desktop execution
surface.

## Safety and billing law

Every paid image, video, or TTS attempt requires one desktop confirmation for
that exact queue item and maximum authorized amount. SIRAJ writes an exclusive
submission lock before making the network request. A second submission is
blocked by the lock.

Runware recovery polls `getResponse` using the same persisted UUID v4 and never
resubmits the original inference task. ElevenLabs does not expose an equivalent
task-polling recovery identifier for this synchronous endpoint, so an uncertain
network result is locked and never retried automatically.

## Supported execution

- Runware still images.
- Runware Veo 3.1 Lite videos with generated audio disabled.
- ElevenLabs TTS with the locked four-performer roster.
- All six local QML/FFmpeg graphics at zero API cost.

Every completed output receives a receipt, SHA-256, file size, provider
identifiers, and actual or protective estimated cost. When every queue item is
complete, the orchestrator advances to `STRUCTURAL_MONTAGE_V1`.
