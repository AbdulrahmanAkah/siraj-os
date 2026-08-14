# SIRAJ Shorts Legacy Timing Resolver V1 — Final Report

## Decision

`LEGACY_TIMING_RESOLVER=PASS`

`EP001_LEGACY_TIMING_RECOVERY=PASS`

`EP001_SHORTS_SOURCE_ADMISSION=PASS`

`EP001_SHORTS_ANALYSIS_STARTABLE=TRUE`

The final task decision is:

`LEGACY_TIMING_RESOLVER_READY_AND_EP001_SHORTS_SOURCE_ADMISSION_PASS`

## Root cause

EP001's trusted timing evidence was a top-level absolute TTS/timeline-repair JSON array. The old Shorts path accepted nearby SRT/VTT and structured timing dictionaries, but did not discover or classify this legacy array. It therefore stopped at `SHORT_TRANSCRIPT_REQUIRED` even though the final narration and timeline-repair evidence were present.

The fix is generic. It has no `episode_id == EP001` branch and no Adam/path-specific runtime branch.

## Resolver and authority

- Resolver: `SIRAJ_SHORTS_LEGACY_TIMING_RESOLVER_V1`
- Version: `1.0.4`
- Authority order: canonical bound SRT/VTT/JSON, native NarrationTimingMap, absolute TTS/timeline repair, trusted sentence/segment timing, explicit user-selected source.
- Ambiguous equal-level evidence stops with `TIMING_SOURCE_AMBIGUOUS`.
- Stale hashes stop with `TIMING_SOURCE_STALE`.
- Missing or unprovable evidence stops with `TIMING_EVIDENCE_INSUFFICIENT`.
- ASR, network transcription, guessing, and proportional timing are not used.

## EP001 recovered result

- Video: `projects/episode-001-adam/deliverables/integrated-local-repair-v1/episode-master-local-repair-v2.mp4`
- Video SHA256: `d24c4c3cba1dbc0b5ef8ae1be90cc1f710a274875793e2f477b0af4a2e155846`
- Final narration: `projects/episode-001-adam/deliverables/integrated-local-repair-v1/audio/narration-absolute-timeline-v1.m4a`
- Narration SHA256: `9074f39d6afbd3f20a76e73c91918d2c5d477fbc13a325f73fc7bac5bf1535a4`
- Timing source: `projects/episode-001-adam/deliverables/integrated-local-repair-v1/reports/tts-absolute-timeline-repair-v1.json`
- Timing source SHA256: `3e04aa5f9be1688fb5e697c93056fabc821025074ebb4bba57e0ae15a8f736a2`
- Timing type: `LEGACY_ABSOLUTE_TTS_TIMELINE`
- Script: `projects/episode-001-adam/script/episode-script-production-standard-v2.json`
- Script SHA256: `5f3a78456cbb7bbf334f3c19d51e0731b480cc311633116b512fddd3b19ebe6b`
- Timebase: `FINAL_VIDEO_ABSOLUTE`
- Offset: `0.0` seconds, proven by the timeline filter artifact
- Segments: `43`
- First timestamp: `0.6`
- Last timestamp: `1312.24483`
- Authoritative duration: `1320.0` seconds
- Final canonical transcript SHA256: `e1f59aa4d0b8711280ed0e7b9d103bf1c4aed7f5c14ca31206473b8a27f77e91`
- Audio binding: decoded PCM SHA256 equal on final narration and selected video audio: `cd182b319589c4e6246b9df98888e5172fe8236cd443900df417717671ea0faf`

## Desktop result

Desktop Source Discovery returns `READY` with no normal metadata or transcript candidate, because the legacy resolver supplies the safe source. `ready_without_manual_file=true`; manual transcript selection is not required for EP001. The real EP001 engine smoke produced `source_admission.status=PASS`, `transcript_bound=true`, `metadata_bound=true`, and local analysis started with 229 candidates. No render or export was requested.

## Persistence and invalidation

The canonical transcript is stored in the task-owned cache:

`artifacts/shorts-derivatives/_legacy-timing-cache/episode-001-adam/canonical-timed-transcript-c0cc8d79554dedc8d7c442052838fe0b6219b87bf2a7eb15ae7d0b75880d83b2.json`

The cache key includes episode, video, audio, timing, script, evidence hashes, and resolver version. Video, audio, timing evidence, script, evidence-record, or resolver-version changes invalidate it. Desktop resume compares the same source metadata hashes and fails closed when they change.

## Verification

- Legacy Resolver tests: 24 passed.
- Combined Resolver/Shorts/Desktop/PR01/constitutional matrix: 428 passed.
- Additional Shorts integration: 12 passed.
- Unit suite: 373 passed.
- Regression suite: 26 passed.
- Smoke suite: 1 passed.
- Release storage/unicode: 15 passed.
- Release packaging: 9 passed when the pre-existing ignored `build` directory was reversibly isolated and restored.
- Direct full-suite run: 789 passed, 1 historical skip, 9 release-packaging errors caused by the same `WinError 183` build/`dist-info` collision when run in the full-suite order. No task-relevant test failed.
- `compileall`: PASS.
- `git diff --check`: PASS.
- Changed-file secret-literal scan: no suspicious literals; no configured secret scanner, Ruff, or typechecker exists in this repository.

## Safety and constitutional status

Provider calls, paid calls, production network calls, new TTS, new narration, new visual generation, production render, montage, publication, retry, and resubmission were all zero. No ASR was used. R27 review and EP002 regeneration were not started.

`CONSTITUTION_MODIFIED=FALSE`

`CORE_ENFORCEMENT_MODIFIED=FALSE`

All historical untracked evidence was preserved and no historical artifacts were staged.

## Reports

- `SHORTS_LEGACY_TIMING_GAP_AUDIT_V1.json`
- `EP001_LEGACY_TIMING_RECOVERY_EVIDENCE_V1.json`
- `SIRAJ_SHORTS_LEGACY_TIMING_RESOLVER_CERTIFICATION_V1.json`

Next user action: open SIRAJ → Shorts → select Episode 1 → Analyze.
