# Canonical Evidence-to-Script Episode Adapter v1

## Scope and current state

This adapter establishes the first canonical episode boundary from approved evidence to a reviewable documentary script:

```text
approved evidence package
→ narrative brief
→ episode outline
→ evidence-bound script
→ deterministic verification report
→ pending human script approval
```

It creates neither speech, subtitles, storyboard, visual prompts, media assets nor render manifests. The canonical artifact is `episode-script-v1.json`; Markdown is a review projection only.

The contract, verification and orchestration adapter are implemented. There is no configured production narrative writer in the repository, therefore the default Episode Orchestrator registry keeps `narrative_script` as `DISCONNECTED`. A caller can mark the stage `AVAILABLE_LOCAL_ADAPTER` only by providing `EvidenceToScriptEpisodeAdapter.as_stage_runner()` with an approved callable writer. Test writers are fixtures only and are never production defaults.

## Contracts

`siraj-approved-evidence-package-v1` requires an approved reviewer identity, local source artifacts with fingerprints, provenance evidence IDs and claim-level provenance. A claim is usable only when `approved_for_narrative` is true, its status is not rejected/excluded, and its source/evidence references exist in the package.

The adapter writes the following runtime-only artifacts under `working/<episode-id>/narrative-script-v1/`:

- `episode-narrative-brief-v1.json`
- `episode-outline-v1.json`
- `episode-script-v1.json`
- `episode-script-review-v1.md`
- `episode-script-verification-v1.json`
- `stage-execution-result-v1.json`

The brief selects only approved claim IDs. The outline derives section word counts from `siraj-arabic-documentary-speaking-rate-v1` rather than hidden constants; section durations total the requested episode duration. The current standard profile remains 22 minutes within the 18–25 minute episode policy.

## Evidence binding and verification

Deterministic checks reject missing claim links on factual blocks, unapproved claims, missing/foreign citation references, direct-quote mismatch, chronology order reversal, prohibited/scope text and duration outside the policy. Disputed claims require an explicit uncertainty marker.

These checks do not claim complete semantic understanding. Meaning-level paraphrase quality, subtle entity conflation, historical interpretation, religious sensitivity judgement and narrative quality remain human-review responsibilities. An eventual model writer must propose structured blocks only; it never writes directly to the official evidence package or an approved script.

## Approvals, versions and invalidation

Generated scripts are always `PENDING`. The existing `script_approval` gate requires reviewer and resolution time. Where narrative artifacts are indexed, approval must reference both the script and its verification report. Any script/evidence fingerprint change stales approval and directionally invalidates TTS and later dependents without deleting prior artifacts.

Changed generation inputs increment `script_version`, retain the previous JSON as `episode-script-v1-<version>.json`, record `previous_script_id`/`supersedes`, and never replace an approved script silently. Matching evidence, brief, outline and writer identity/version produce a cache hit.

## Provider policy

`DEFAULT_NARRATIVE_MODEL_POLICY` is a non-secret policy contract, not a configured provider. It requires approved-evidence grounding, structured output, disclosure permission, explicit live confirmation, request limits and declared retry/fallback policy. No Gemini, Pro model or cloud fallback is selected by default.

## CLI

```text
python scripts/fast_track/run_evidence_to_script_episode_v1.py \
  --project-root <project-root> \
  --episode-definition <episode-definition-v1.json> \
  --evidence-package <approved-evidence-package-v1.json> \
  --mode plan --json
```

`validate-input`, `plan`, `verify` and `status` are local-only. `generate` reports `GENERATOR_DISCONNECTED` unless application code supplies an approved writer adapter; the CLI never configures a cloud writer or sends a request.

## Episode Orchestrator integration

The default graph remains explicit:

```text
evidence_knowledge → narrative_script → script_approval → production_tts
```

`production_tts` consumes `approved-episode-script-v1`, not a bare text file. It remains `DISCONNECTED` at the episode boundary until its own canonical adapter is supplied. A VisualProvider quota block remains a separate, retryable external block and does not change script provenance or approval state.
