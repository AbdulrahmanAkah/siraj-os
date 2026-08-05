# End-to-End Production and YouTube Handoff V1

This package completes the operational path from topic selection to a manual YouTube upload handoff.

## Operating sequence

1. Luna proposes the next topic and evidence-bounded events.
2. The creator reviews and approves the scope.
3. SIRAJ resumes evidence research, script writing and storyboard planning.
4. SIRAJ builds one complete media queue.
5. The creator receives one consolidated maximum-cost confirmation for all remaining Runware and ElevenLabs items.
6. SIRAJ executes the authorized media queue sequentially, reuses completed receipts and recovers existing Runware tasks without resubmission.
7. SIRAJ automatically continues through local SFX/audio mix, structural montage and automatic QA.
8. The creator watches and approves the final episode.
9. SIRAJ builds the complete manual YouTube handoff: title, description, tags, chapters, Arabic SRT, altered-content disclosure, checksums, upload sheet and YouTube Studio shortcut.
10. The creator uploads the exact MP4 and presses Publish manually.

## Human boundaries

Only two editorial gates remain:

- `HUMAN_SCOPE_REVIEW`
- `HUMAN_FINAL_REVIEW`

Paid media execution also requires an explicit consolidated authorization matching the exact remaining maximum. This is a financial authorization, not an editorial gate.

## Thumbnail policy

Thumbnails are not generated per episode. SIRAJ supports a stable thumbnail template per historical era. The design files are intentionally deferred. Until an era template is configured, the handoff remains usable with YouTube's generated thumbnail and records `ERA_TEMPLATE_NOT_CONFIGURED` transparently.

## YouTube boundary

SIRAJ opens YouTube Studio and prepares all local upload assets. It does not perform OAuth, store YouTube credentials, call the YouTube API or publish automatically.

## Verified YouTube API boundary

The release prepares every local publishing asset and opens YouTube Studio, but
does not upload through an unverified YouTube Data API project. API draft upload
remains deferred until the creator owns an audited/verified API project. This
avoids producing a video that YouTube locks permanently to private visibility.

The supported V1 boundary is therefore: exact upload-ready package, guided manual
site upload, final creator review, and manual publication.
