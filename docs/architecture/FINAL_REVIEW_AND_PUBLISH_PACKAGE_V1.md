# Final Review and Publish Package V1

This is the fourth and final programming package in SIRAJ Production V1.

## Purpose

The stage implements the second and final human gate. It opens only after
`AUTOMATIC_QA_AND_PARTIAL_REPAIR_V1` has produced a passing technical report.
The reviewer must watch the complete episode, assess historical and semantic
accuracy, review audio/visual continuity, confirm the music policy and approve
the publishing metadata.

## Approval integrity

Approval rechecks the SHA-256 of the automatic QA report and the final episode
master against the locked receipts. A stale QA report or modified video cannot
be approved silently.

## Decisions

### Approve

All seven checklist items are mandatory. SIRAJ records the signed review,
creates a manual publishing package and advances the episode to
`READY_TO_PUBLISH`.

### Request changes

The reviewer records one or more categories, optional shot IDs and mandatory
notes. SIRAJ creates a structured repair request and targets the relevant
upstream stage. Visual, audio or content changes require automatic QA to pass
again. Metadata-only changes may return directly to final review.

No paid generation or provider request is triggered by a change request.

## Manual publishing package

The package contains:

- a reference and SHA-256 for the exact final MP4;
- the passing QA report and human-review hashes;
- title, description and tags files;
- a metadata JSON file;
- a small metadata ZIP archive;
- `SHA256SUMS.txt`;
- a manual upload checklist.

The video is not duplicated into another archive. The canonical episode master
remains under `deliverables/episode-master-v1.mp4`.

## Upload boundary

YouTube upload remains manual. SIRAJ performs no OAuth flow, stores no YouTube
credentials and makes zero YouTube API requests. Initial visibility, audience,
language, category and thumbnail remain explicit manual upload decisions.

## Completion

Runtime completion is `READY_TO_PUBLISH`, followed by
`MANUAL_YOUTUBE_UPLOAD`. Programming completion is SIRAJ Production V1 ready for
an end-to-end acceptance run.
