# Adam Episode Exact Source Registry v1

This directory separates source governance from Gemini extraction.

## Files

- `exact-source-registry-v1.jsonl`: exact Qur'an passages and exact hadith reports for Phase 1.
- `acquisition-plan-v1.json`: local asset families, order, and acceptance checks.
- `source-package-v1.exact-draft.json`: normalized draft source package with one item per exact record plus deferred tafsir/history/Isra'iliyyat work-level records.
- `source-materialization-state-v1.json`: records that no source asset is available yet.
- `gemini-work-package-template-v1.json`: bounded extraction instructions; it is blocked until local assets are checksummed and explicitly enabled.
- `asset-map.template.json`: paths remain empty until local source assets are prepared.

## Governance

Locator verification is not source acquisition, hadith grading, source approval, or evidence approval.
No item may be extracted or quoted until its local project-relative path and SHA-256 checksum are recorded.
The Tirmidhi and Abu Dawud reports remain subject to the user-approved hadith grading authorities.
Parallel locators must not be treated automatically as independent corroboration.
