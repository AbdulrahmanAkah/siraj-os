# SIRAJ Non-Live Production System v1

The non-live production path is deliberately evidence-first and local by
default:

`source_package -> evidence_knowledge -> evidence_approval -> narrative_script
-> script_approval -> production_tts -> subtitles -> storyboard ->
storyboard_approval -> visual_provider/video_provider -> approvals -> render ->
final_render_approval -> qa_gate -> publication_package -> publication`.

## Research and verification

`research_verification_episode_v1` validates source inventory paths,
checksums, identifiers, passage locators, claim references, quotation/provenance
links, structured chronology, and recorded source relationships.  It detects
recorded derivative/circular relationships; it does not make historical truth
claims.  An injected extractor is required for extraction.  Without one the
status is `IMPLEMENTED_EXTRACTOR_DISCONNECTED`.

The adapter creates a research dossier, deterministic verification report and
a review candidate.  `evidence_approval` requires a reviewer and materializes
the only canonical `approved-evidence-package-v1` consumed by the narrative
adapter.  A changed source or dossier makes the approval and downstream
artifacts stale.

## QA and publication

`EpisodeQAGate` aggregates existing stage status, approvals, stale state and
reported validator errors.  It does not duplicate specialist validation.  Its
decision is `PASS`, `PASS_WITH_WARNINGS`, or `FAIL`; required stale artifacts,
missing approvals, unsupported factual assertions and missing final render are
blockers.

`PublicationPackageBuilder` is local only.  It requires a passing QA report
and approved final render, copies approved export assets to a public package,
and writes a separate internal provenance/checksum package.  It strips local
absolute paths, private notes, prompts and credentials.  Supported metadata
profiles are `GENERIC_VIDEO`, `YOUTUBE`, and `WEBSITE_ARCHIVE`; no upload is
implemented.

## Local operator UI

`local_operator_ui_v1` is a Python-standard-library, server-rendered local
console.  It binds only to `127.0.0.1`, `::1`, or `localhost`; actions call
`EpisodeOrchestrator` services directly, have CSRF protection, validate episode
identifiers, and cannot run arbitrary commands or read files outside the
project root.  External operations remain subject to the orchestrator's
provider confirmation and policy guards.

## CLI entry points

* `run_research_verification_episode_v1.py` validates source input and reports
  the explicitly disconnected extractor state.
* `run_episode_qa_v1.py` runs or plans `qa_gate` through the composition root.
* `build_publication_package_v1.py` runs or plans `publication_package` through
  the composition root; it never uploads.
* `run_operator_ui_v1.py --plan-only` checks local UI configuration without
  binding a port.

Live narrative, TTS, visual, video, and production-render validation remain
deferred.  All tests use injected fakes or local fixtures.
