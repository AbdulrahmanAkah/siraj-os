# SIRAJ Desktop Complete Workspace and Resume V1

This package closes the desktop usability gap after SIRAJ Production V1.

## Fixes

- The production console is vertically scrollable at every supported window size.
- A persistent stage-aware **Continue episode** action is visible above the tabs.
- Incomplete episodes always open the production console instead of a raw folder.
- The dashboard recognises the canonical V1 final master under `deliverables/` and the manual publishing package under `publishing/`.
- Every sidebar destination is a functional live page rather than a placeholder message.

## Resume boundary

The resume router can start safe local/editorial stages and open the exact tab for the next operation. It does not bypass:

- human scope approval;
- explicit paid-provider confirmation;
- human final review;
- manual YouTube upload.

## Publishing boundary

SIRAJ prepares the final video, QA evidence, title, description, tags, checksums and manual upload checklist. The video page also reports whether a thumbnail file actually exists. It never claims publishing readiness when a required asset is absent.
