# SIRAJ Production Excellence Plan

## Mission

Build a provider-independent, provenance-aware documentary production
system capable of producing high-quality Arabic historical episodes from
reviewed Islamic sources.

## Core principles

- SIRAJ owns facts, evidence, orchestration, quality and final rendering.
- External AI systems are replaceable capability providers.
- Every claim retains source linkage.
- Every media asset retains provenance and rights metadata.
- Human review remains mandatory for sensitive evidence, visual policy and final publication.
- Every work package must produce a visible vertical-slice improvement.

## P1 — Episode Render Manifest v2

Deliverables:

- Timed scenes.
- Scene-specific motion and transitions.
- Multiple audio layers.
- Sidecar and burned-in subtitles.
- Claim and source references.
- Visual-policy references.
- Deterministic validation.
- Integration tests.

Definition of Done:

- A manifest with differently timed scenes validates.
- Scene overlaps and missing references are rejected.
- A render-ready plan is created without manual FFmpeg editing.

## P2 — Render Adapter v2

Deliverables:

- Consumption of exact scene timing.
- Scene-level motion and transitions.
- Multi-layer audio mixing.
- Sidecar and burned-in subtitle modes.
- Technical verification report.

Definition of Done:

- A V2 manifest produces a valid MP4.
- Output duration matches the timed-scene plan.
- Audio layers and subtitle modes are verified.

## P3 — Production Voice Layer

Deliverables:

- Provider-neutral VoiceProvider.
- Arabic pronunciation dictionary.
- Sentence-level audio segmentation.
- Loudness normalization.
- Retry and fallback policy.
- Voice audition quality gate.

## P4 — Image and Visual Asset Layer

Deliverables:

- ImageProvider interface.
- Historical visual briefs.
- Candidate generation and ranking.
- Metadata and rights registry.
- Human review states.

## P5 — Selective Video Generation

Deliverables:

- VideoProvider interface.
- Reference-image and continuity contracts.
- Cost and duration controls.
- Automatic fallback to animated still images.

## P6 — Automated Editorial Director

Deliverables:

- Shot-purpose taxonomy.
- Pacing and cut decisions.
- Visual-type selection.
- Candidate ranking.
- Regeneration decisions.

## P7 — Maps and Procedural Graphics

Deliverables:

- Timelines.
- Routes and territorial changes.
- Location maps.
- Genealogy and relationship diagrams.
- Source cards.
- Reusable typography and visual identity.

## P8 — Professional Quality System

Deliverables:

- Historical QA.
- Islamic visual-policy QA.
- Editorial QA.
- Media QA.
- Audio QA.
- Rights QA.
- Publication gate.

## P9 — Episode 001 Production

Deliverables:

- Reviewed source pack.
- Claim ledger.
- Final script.
- Timed scenes.
- Production voice.
- Reviewed visual assets.
- Final MP4.
- Subtitles and source report.