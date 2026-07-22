# Episode Orchestrator v1

## Purpose

Episode Orchestrator v1 coordinates an episode; it does not perform research, narration, image generation, speech synthesis, rendering, or provider calls itself. Its responsibilities are policy enforcement, dependency evaluation, state, resume, invalidation and audit.

## Actual connected system

The current repository contains deterministic source/project ingestion, knowledge and assessment runtimes; a read-only Shamela adapter and semantic-review gates; production TTS, subtitles, storyboard generation, VisualProvider, and FFmpeg render adapters. These components do not yet form one canonical evidence-to-script-to-storyboard Episode 01 runner.

The registry intentionally distinguishes:

- `AVAILABLE_*`: only used when the registry has a Python-callable episode adapter and a deterministic integration test for its declared contract. A component existing elsewhere in the repository is not sufficient.
- `IMPLEMENTATION_COMPLETED_LIVE_VALIDATION_DEFERRED`: VisualProvider is implemented and a live request path was validated, but its current provider quota blocks image generation.
- `DISCONNECTED`: the repository contains related runtime capability but no canonical episode contract adapter.
- `CONTRACT_ONLY`: the stage has a defined boundary or human gate, but no executable production runner.
- `NOT_IMPLEMENTED`: no runner is available for the requested contract.

Production TTS, subtitles, storyboard and FFmpeg render are currently `DISCONNECTED` at the episode boundary: their own Python APIs exist, but this v1 does not invent an adapter that maps approved episode artifacts to their requests and outputs. No state above is silently promoted to completed.

## Default stage graph

```text
source_package
  -> evidence_knowledge -> narrative_script -> script_approval
  -> production_tts -> subtitles -> storyboard -> storyboard_approval
  -> visual_provider -> master_visual_approval -> render
  -> final_render_approval -> publication
```

The graph is explicit and contains both dependencies and dependents. v1 performs no concurrent execution; it reports no speculative parallel candidates.

## Runtime outputs

By default, runtime-only files are placed under:

`working/episode-orchestrator-v1/`

- `episode-execution-plan-v1.json`
- `episode-orchestration-manifest-v1.json`
- `episode-stage-registry-v1.json`
- `episode-artifact-index-v1.json`
- `episode-dependency-graph-v1.json`
- `episode-status-report-v1.json`

They are runtime artifacts and must not be committed. The artifact index references outputs; it does not copy their contents.

## Episode definition and video policy

Use `docs/execution/examples/episode-definition-v1.example.json` as a schema-valid template. Standard duration is 22 minutes, bounded to 18–25 minutes. Generated-video allocation is validated, not generated, by the orchestrator:

- maximum final generated video: 300 seconds;
- allowed future models: `VEO_3_1_LITE_1080P`, `VEO_3_1_FAST_1080P`;
- allocation owner: `STORYBOARD_WRITER`;
- enforcement owner: `VIDEO_POLICY_GUARD`.

An allocation above 300 seconds produces `POLICY_VALIDATION_ERROR`; the orchestrator never trims it silently.

The definition validator also requires the two allowed future video models, `STORYBOARD_WRITER` as allocation owner, `VIDEO_POLICY_GUARD` as enforcement owner, and a final human approval flag. VideoProvider itself is not implemented.

## Modes

```text
plan                 build plan and manifests; run no runner
run-next             run one READY stage
run-through          run READY stages sequentially until a gate/blocker
run-stage --stage X  validate dependencies then run X
resume               run the first resumable READY stage
status               inspect without running
invalidate-stage     mark stage and completed downstream outputs STALE
```

`--allow-external` and `--confirm-live` must be supplied together. They only permit an adapter to be considered executable; an adapter remains responsible for its own credential, disclosure, quota and request-limit guards.

Before an external stage can become `READY`, the episode policy must declare provider configuration, credential presence, disclosure permission, request-limit availability and a valid quota policy. The manifest records only missing requirement names, never a credential value.

It additionally requires a stage-specific permission entry. Supplying an API key, `--allow-external`, or `--confirm-live` on its own is never enough. Plan and dry-run invoke no runner and make no provider request.

## Human approvals and external blocks

Human gates use `NOT_REQUESTED`, `PENDING`, `APPROVED`, `APPROVED_WITH_NOTES`, `REJECTED`, and `STALE`. Input changes stale completed downstream stages and their approvals without deleting prior artifacts.

An approved decision always records a reviewer and resolution time; `APPROVED_WITH_NOTES` also requires notes. An approval stores its input and referenced-artifact fingerprints, becomes `STALE` when either changes, and never remains valid for a superseded artifact. A rejected decision blocks dependents and never triggers provider fallback.

## Derived episode state, resume and invalidation

Episode status is derived each time from ordered stage states and the explicit graph; it is not a manually maintained second truth. The first unresolved required stage determines whether the episode waits for human approval or an external provider. `READY_FOR_RENDER` requires every declared render dependency to be completed and approved; `READY_FOR_PUBLICATION` requires a completed final-render approval and only the publication gate remaining. A permanent required-stage failure yields `FAILED`; a disconnected or deferred stage after valid progress yields `PARTIALLY_COMPLETED`.

Every invocation receives a new run ID and appends execution history. A completed stage is reused only when its stage-specific input fingerprint, output fingerprint, outputs and approvals remain valid. Invalidating a stage preserves artifacts and attempts, marks only transitive dependents `STALE`, and stales their approvals. Stale outputs never satisfy a dependency.

## Artifact index

The index references artifacts rather than copying them. Each record carries its ID, type, producing stage, project-relative normalized Windows-safe path, schema and content fingerprints, lineage, supersession and runtime/Git tracking flags. Duplicate IDs, unknown stages, paths outside the project root, and runtime artifacts marked Git-trackable are rejected.

VisualProvider is represented as `BLOCKED_BY_EXTERNAL_PROVIDER` with a retryable `QUOTA_EXHAUSTED` blocker when its current quota report says so. This is not an episode failure. Prior plan and attempt history remain preserved; the next action is a separately confirmed retry after quota availability or tier activation.

## CLI

```text
C:\Users\abdul\AppData\Local\Programs\Python\Python313\python.exe scripts\fast_track\run_episode_orchestrator_v1.py --project-root C:\SIRAJ\Workspace\first-project --episode-definition C:\SIRAJ\Workspace\first-project\working\episode-001\episode-definition-v1.json --mode plan --dry-run --json
```

The CLI never enables an external provider by default and does not print secrets or full prompts.
