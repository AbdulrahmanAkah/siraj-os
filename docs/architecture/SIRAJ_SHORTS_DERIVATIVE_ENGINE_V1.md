# SIRAJ Shorts Derivative Engine V1

## Scope

The Shorts engine creates local, extractive derivatives from a selected
long-form episode. It is a short-form director, not a generic clipper.

The pipeline is:

`episode -> ingest -> intelligence map -> candidate discovery -> explainable scoring -> diverse portfolio -> extractive structure -> vertical reframe -> source-audio edit -> immutable render plan -> local render -> QA -> human review package`

## Constitutional inheritance

The engine loads the single unified constitution through
`unified_constitution_enforcement_v1.py`. It does not introduce a second
policy authority or change the constitution machine rules.

Shorts inherit the current face prohibition, modesty, unseen, period,
source/certainty, visual semantic alignment, music, graphics, approval,
append-only evidence, hash binding, and publication-boundary rules.

Legacy episodes may be analyzed and candidates may be discovered, but current
constitutional review is repeated. Previous publication is never a current
approval.

## V1 capability boundary

- Existing episode bytes, approved narration bytes, existing visuals, and
  existing source audio design are the only media inputs.
- New narration, TTS, visuals, music, burned captions, on-screen subtitles,
  public titles, thumbnails, upload, scheduling writes, and publication are
  forbidden.
- External captions are optional and generated from the exact source narration
  segments used by the derivative.
- Rendering is local and deterministic. The approved plan is authoritative;
  the renderer has no creative authority.
- Real episode rendering is not part of certification. Fixture rendering
  requires an explicit local-render approval click.
- Final visual face conformance remains human-required while OPEN-M03 is
  deferred; an uncalibrated detector cannot grant final PASS.

## State machine

`INGESTED -> ANALYZED -> CANDIDATES_READY -> HUMAN_SELECTION_REQUIRED -> PORTFOLIO_READY -> RENDER_PLAN_READY -> LOCAL_RENDER_APPROVAL_REQUIRED -> RENDERED -> SHORT_QA_PENDING -> SHORT_QA_PASS -> HUMAN_FINAL_REVIEW_REQUIRED -> EXPORT_READY`

Any missing or stale evidence moves to `BLOCKED`, `REJECTED`, or
`SHORT_QA_FAIL`; there is no automatic promotion or retry.

## Desktop integration

The existing Desktop application receives a service integration point through
`shorts_derivative_desktop_integration_v1.py`. No second GUI is created. The
workflow exposes episode selection, analysis, candidate review, portfolio
selection, render-plan generation, explicit local render approval, QA, and
review-package inspection. Public metadata remains human-owned.

## Certification evidence

The certification script writes the SHD-00 audit, profile, ingestion,
intelligence/candidate, scoring/portfolio, vertical, audio, renderer,
constitutional compatibility, final certification, and capability coverage
artifacts under `reports/shorts-derivative-engine-v1`.
