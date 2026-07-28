# Adam Delegated Source Review Ingestion v1

This stage ingests the human-approved source-text and locator comparison for
twenty-two source candidates.

The standing user delegation authorizes AI decisions for routine evidence while
reserving complex or high-importance matters for explicit user review. The
ingestion therefore:

- accepts the approved source text and locator for all twenty-two sources;
- routes eleven Quran sources to delegated event-scope review;
- retains authentication and origin-classification guards for eleven hadith
  sources;
- reserves Abu Dawud 4700, Muslim 2841, and Tirmidhi 2155 for explicit user
  review because they touch chronology or theological interpretation;
- routes the remaining eight hadith sources to delegated AI authentication
  research;
- keeps every event-binding decision unapproved;
- keeps the episode adjudication incomplete, the evidence gate withheld, and
  provider execution blocked.


## JSON line-ending portability correction — 2026-07-28

The first ingestion build validated the normalization audit against the raw
bytes of `source-review-human-decision-v1.json`. The temporary publication clone
used LF, while the synchronized Windows checkout could materialize CRLF because
of Git line-ending settings. The parsed JSON remained identical, but the raw
SHA-256 changed and prevented local report regeneration after a successful
publication.

The corrected implementation hashes the deterministic UTF-8 JSON serialization
with sorted keys, two-space indentation, and a final LF. This preserves the
existing audit hash while making validation independent of checkout line
endings. Raw file hashing remains available for byte-integrity use cases but is
not used for semantic JSON-document validation.
