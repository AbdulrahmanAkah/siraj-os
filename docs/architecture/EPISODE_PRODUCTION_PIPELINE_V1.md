# Episode Production Pipeline v1

## Scope and source of truth

This composition layer coordinates existing stage adapters.  It does not write
historical facts, make an approval decision, or treat a provider result as an
approved asset.  The canonical evidence package, episode script, stage manifest
and artifact index remain the source of truth.

## Stage path

`approved evidence -> narrative script -> script approval -> production TTS ->
subtitles -> storyboard -> storyboard approval -> visual/video providers ->
asset approval -> render -> final approval -> publication`

The default orchestration registry remains conservative: a component is
`DISCONNECTED` until a composition root supplies a callable runner.  The helper
`build_episode_production_registry` promotes only supplied Python callables to
`AVAILABLE_LOCAL_ADAPTER` or `AVAILABLE_EXTERNAL_ADAPTER`.

## Provider boundaries

`GeminiEvidenceBoundScriptWriter` uses the official `google-genai` SDK only
through an injected transport.  It requests structured JSON and supplies only
the approved package, brief, outline, and quotation records.  The evidence
adapter performs the authoritative deterministic evidence binding afterwards.
It is blocked unless both the stage-specific external policy and explicit live
confirmation are present.

The TTS adapter receives an injected `ProductionTTSOrchestrator.synthesize`
callable and a request factory.  It requires a current script approval and
records only a valid mastered WAV.  The subtitle and storyboard adapters wrap
the existing local APIs and preserve script/audio fingerprints in their output
lineage.  Rendering likewise requires an injected local renderer and a
validated render-manifest factory.

Visual generation remains deferred behind a storyboard approval and its own
quota policy.  It is represented as a resumable external block; no image API
is called by the episode adapter.

## Video boundary

`VideoProviderV1` is a guarded VEO policy boundary, not a default client.  It
accepts only `VEO_3_1_LITE_1080P` and `VEO_3_1_FAST_1080P`, rejects a final
required allocation above 300 seconds, rejects a total allocation above 600
seconds, and requires separate approval above 450 generated seconds.  It has
no client unless a caller injects one, and no live call occurs without
credential, disclosure, request-limit, allow-external, and confirm-live gates.

## Lineage, approvals, and resume

Every produced artifact contains a fingerprint, source artifact identifiers,
runtime-only state, and non-Git-trackable flag.  Script approval is bound to
both the canonical script and verification report.  Replacing a fingerprint
marks dependent stages and approvals stale without deleting previous outputs.
Completed matching fingerprints remain cache hits.

## Deliberate limitations

No live Gemini narrative, TTS, visual, or video request is executed by this
implementation.  A real composition root must configure each provider and its
stage permission separately.  The current storyboard generator does not yet
author video allocation choices; that allocation remains a guarded VideoProvider
contract rather than an implied request.

## Composition root and configuration

`EpisodeProductionComposition` is the composition root.  It accepts the
episode definition, a versioned pipeline configuration, and optional injected
callables for provider-facing adapters.  It does not implement research,
script writing, synthesis, rendering, or provider policy itself.

The example configuration is at
`docs/execution/examples/episode-production-pipeline-v1.example.json`.  It
contains no credential or prompt.  Credentials are read from environment only
at the point of an explicitly confirmed live provider request.  A disabled or
incompletely configured external adapter remains `DISCONNECTED`, never a
permanent failure.  Local subtitle and storyboard adapters are available only
when enabled and callable.

## CLI

```powershell
python scripts/fast_track/run_episode_production_pipeline_v1.py `
  --project-root "C:\SIRAJ\Workspace\first-project" `
  --episode-definition "<episode-definition.json>" `
  --pipeline-config "docs/execution/examples/episode-production-pipeline-v1.example.json" `
  --mode plan --json
```

Supported modes are `plan`, `status`, `run-next`, `run-through`, `resume`, and
`run-stage`.  `--allow-external` and `--confirm-live` must be supplied together
and still do not bypass the stage permission, configured credential state,
disclosure permission, quota policy, or request-limit checks.  JSON mode writes
only JSON to stdout.

## First live-run checklist

1. Review and approve the evidence package and generated script.
2. Enable exactly one intended stage in configuration and its stage permission.
3. Confirm its provider, quota/request limit, disclosure permission, and
   environment credential without writing a secret to configuration.
4. Use both external confirmation flags for that one operation.
5. Review the produced artifact before approving dependents.

Live narrative, TTS, visual, video, and render validation remain deferred.

## Deterministic end-to-end fixture

`tests/integration/test_episode_production_v1.py` includes an in-discovery,
bounded fake episode.  It passes approved evidence through the production
composition root, the evidence-bound script adapter, all approval gates, fake
TTS/subtitles/storyboard/visual/video/render adapters, and the publication
gate.  It never constructs a provider client or sends a request.

The fixture previously exposed an orchestration defect: the approved-evidence
runner returned the evidence-package fingerprint as its *stage input*
fingerprint.  The orchestrator correctly treated that mismatch as stale, then
made the stage ready again, so `run-through` could repeat it indefinitely.  The
runner now leaves stage-input fingerprint ownership to the orchestrator and
uses the package fingerprint only as its output fingerprint.
