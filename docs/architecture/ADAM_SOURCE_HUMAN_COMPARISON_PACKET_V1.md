# Adam Source Human Comparison Packet v1

This stage converts remote source materialization into a bounded human review
workflow.

It verifies all archived HTTP response files against the fetch-manifest size and
SHA-256 values. For every source it normalizes Arabic text, selects the strongest
contiguous comparison window, computes token recall, precision, F1, sequence
similarity, missing tokens, and extra tokens, and routes the source either to
bounded human confirmation or targeted resolution.

It generates twenty-two comparison records, twenty-two source dossiers,
fourteen event-readiness records covering twenty-eight event/source links, a
blank review template, and three review batches:

1. Quran comparison against an authorized Mushaf;
2. hadith records ready for exact-text and locator confirmation;
3. partial matches requiring targeted wording or locator resolution.

A strong machine match only reduces human workload. It never means that the
source is verified, authenticated, graded, origin-classified, narration-approved,
or eligible to open the evidence gate.
