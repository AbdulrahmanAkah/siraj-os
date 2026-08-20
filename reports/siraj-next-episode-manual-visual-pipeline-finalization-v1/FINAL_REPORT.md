# SIRAJ next-episode manual visual pipeline

## Outcome

The canonical manual-visual episode path is implemented and its focused clean E2E flow passes from episode creation through archive. Final task certification remains blocked because the pre-existing dirty repository-wide suite produced unrelated failures and then hung near 76%; it did not produce a clean final summary.

## What was broken?

The reusable state authority was episode/provider oriented, and the system lacked a complete manual visual handoff, validated ingest, SHA lock, generic assembly, separated QA, Desktop operation, and downstream invalidation path.

## What changed and is now canonical?

New episodes use `CANONICAL_NEXT_EPISODE_MANUAL_VISUAL_V1` and `MANUAL_USER_PRODUCTION`. They progress through research, source/title/script/audio/timing/storyboard/contracts, human pre-visual approval, manual handoff, validated asset ingest, local assembly, separated QA, human final review, master, Shorts compatibility, and archive. All state and authorities are durable and SHA-bound.

## What remains legacy?

EP001/EP002 provider, retry, and recovery code remains preserved behind legacy-specific routes. It is not the canonical router for a new episode. The shared paid gateway blocks a manual-profile visual request before any attempt write or transport.

## Operator workflow

Open SIRAJ Desktop and use the manual visual pipeline panel. Start with `حلقة جديدة`. After approved pre-visual artifacts exist, export with `تصدير حزمة الإنتاج المرئي`. Produce the named image/video files outside SIRAJ, choose their folder, then use `استيراد المرئيات والتحقق منها`, `قفل المرئيات المقبولة`, `استكمال التجميع والمونتاج`, the separated QA action, final human review, and master build.

CLI equivalent: `python -m src.application.canonical_next_episode_manual_visual_pipeline_v1 --repo <repo> --episode-id <id> create`, followed by the explicit subcommands printed by `status`.

Human gates remain mandatory for title lock, pre-visual approval, asset selection/constitutional acceptance, and final review. No public title, thumbnail, publication, provider visual generation, or paid visual fallback is performed.

## Evidence

- Relevant matrix: 54 passed.
- Clean synthetic E2E: passed, including replacement rebuild and historical-master preservation.
- Provider/paid/production calls: 0.
- Commit/push: 0/0.
- Full repository: not certified; first diagnosed failure was in a pre-existing dirty canonical-reference/visual-context contract, an independent dirty Shorts profile mismatch was reproduced, and the run later hung.

Final decision: `BLOCKED:FULL_REPOSITORY_REGRESSION_NOT_CLEAN_OR_COMPLETE`.
