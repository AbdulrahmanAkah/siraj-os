# Canonical architecture after

Profile: `CANONICAL_NEXT_EPISODE_MANUAL_VISUAL_V1`

Visual mode: `MANUAL_USER_PRODUCTION`

Durable stage order:

`EPISODE_CREATE -> RESEARCH -> SOURCE_LOCK -> TITLE_LOCK -> STORY_ARCHITECTURE -> SCRIPT -> SCRIPT_QA -> NARRATION -> WORD_LEVEL_TIMING -> STORYBOARD -> VISUAL_REQUIREMENT_CONTRACTS -> COVERAGE_DIVERSITY_REUSE_VALIDATION -> HUMAN_PRE_VISUAL_APPROVAL -> MANUAL_VISUAL_HANDOFF_READY -> MANUAL_VISUAL_INGEST -> ASSET_VALIDATION -> SHA_BOUND_VISUAL_LOCK -> AUTOMATED_ASSEMBLY -> MONTAGE -> AUDIO_SYNC -> TECHNICAL_QA -> CONSTITUTION_QA -> EDITORIAL_QA -> HUMAN_FINAL_REVIEW -> MASTER -> SHORTS_DERIVATIVE -> ARCHIVE`

Canonical properties:

- One profile-aware state authority with durable revisions and compare-and-swap writes.
- Explicit artifact slots, lock stages, transition requirements, human approvals, and downstream invalidation.
- Provider-agnostic JSON/HTML/Markdown manual production pack plus naming and ingest contracts.
- Actual image/video probing, immutable accepted assets, SHA ledger, duplicate/replacement policy, and completeness lock.
- Local FFmpeg assembly only; visual asset audio is stripped and final accepted narration is authoritative.
- Separate technical, constitutional, and editorial QA receipts.
- Explicit final human approval before master.
- Versioned preservation of a superseded master after a visual replacement.
- Shorts compatibility and archive receipts without publication.
- Canonical new-episode paid visual generation and provider fallback are disabled and fail closed.
