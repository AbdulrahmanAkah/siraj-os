# Independent adversarial review

Initial decision: NO-GO with two critical and four high defects.

Resolved findings:

1. Tampered receipts: every bound artifact is re-hashed before sensitive operations; assembly receipt fields are checked against audio, timing, visual lock, plan, episode, and candidate bytes.
2. Tampered/incomplete pack: canonical file SHA, internal content SHA, required fields, derived totals, both media classes, bindings, and policy are validated.
3. Replacement after master: the old master is preserved in a SHA-named history path and the new master is copied atomically.
4. Upstream drift: all bound authorities are re-hashed before handoff, ingest, lock, assembly, QA, review, master, Shorts, and archive.
5. Provider isolation: canonical manual profiles block known and unknown visual/provider operations before authorization mutation or transport; explicit non-visual classes remain separately classified.
6. Malformed timing: NaN and positive/negative Infinity are rejected.

Focused adversarial coverage passed. Remaining certification blocker is repository-wide regression cleanliness, not a known critical/high defect in this new canonical path.
