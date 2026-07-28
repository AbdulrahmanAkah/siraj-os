# Adam Remote Source Materialization v1

This stage performs the first real network materialization of the twenty-two
external Quran and hadith source candidates.

For each candidate it:

1. fetches the referenced source, with bounded retries and response size;
2. archives each successful raw response locally and records its SHA-256;
3. extracts Arabic text mechanically;
4. compares the normalized extraction with the existing research anchor;
5. produces source and event readiness dossiers;
6. prepares twenty-eight event/source prefill suggestions;
7. creates a human comparison template.

For hadith pages the extractor selects the Arabic HTML block with the strongest
anchor overlap. For Quran candidates it requests Uthmani verse text by verse key
from Quran.com-compatible endpoints and records every fallback request.

Network success, text extraction, and anchor match are not human source
verification. Exact excerpts, surrounding context, hadith authentication,
source-origin classification, narration disposition, and approval remain blank.
The evidence gate and live providers remain blocked.
