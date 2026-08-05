# SIRAJ Autonomous Episode Orchestrator V1

## Purpose

This release starts the autonomous episode workflow at the first mandatory
human gate. The operator presses **إنتاج الحلقة التالية**. GPT-5.6 Luna uses the
OpenAI Responses API with hosted web search and strict structured output to
propose the next topic and 3–15 ordered events. The proposal is not approved by
the model.

The operator can discuss the proposal with Luna, request revisions, and then
approve the exact topic and event set. Approval creates a new episode workspace,
a stage ledger, and an artifact dependency graph.

## Implemented in V1

- Secure OpenAI key storage in Windows Credential Manager.
- Secure ElevenLabs key storage in Windows Credential Manager.
- Existing Runware key and video workflow remain intact.
- One-click next-episode scope generation with `gpt-5.6-luna`.
- Web-search-backed source references for each proposed event.
- Strict JSON schema for topic, events, evidence posture, confidence, sources,
  exclusions, research questions, and production risks.
- Human discussion and revision loop with Luna.
- Human scope approval as a blocking gate.
- Automatic creation of the next episode directory and approved scope contract.
- Durable stage ledger for the complete autonomous workflow.
- Dependency graph and downstream-only invalidation foundation.
- Preservation of unaffected paid assets during future repairs.

## Full target workflow

1. Topic and event proposal.
2. Human scope review and discussion.
3. Evidence research.
4. Script writing.
5. Storyboard and media planning.
6. USD 40 budget preflight.
7. Runware image generation.
8. Runware video generation.
9. ElevenLabs segmented TTS.
10. Sound-effects design without music.
11. Structural montage.
12. Automatic QA.
13. Human final review.
14. Ready-to-publish file; YouTube upload remains manual.

Only stages 1, 2, the episode workspace, stage ledger, and dependency graph are
executed by this release. The remaining stages are queued for subsequent
orchestrator releases. This boundary is explicit and must not be represented as
a completed end-to-end pipeline.

## Human gates

Exactly two human gates are defined:

- `HUMAN_SCOPE_REVIEW`
- `HUMAN_FINAL_REVIEW`

After scope approval, the target design is automatic continuation until final
review. V1 creates the queued state but does not yet execute the downstream
research-to-montage chain.

## Provider mapping

- Editorial research and planning: OpenAI `gpt-5.6-luna`.
- Images: Runware.
- Video: Runware.
- Narration: ElevenLabs.
- Music: forbidden.
- Sound effects: any scene-appropriate type.
- Montage: local structural runtime.

## Partial rebuild law

Every episode is represented as a dependency graph:

`SCOPE -> EVENT -> EVIDENCE -> SCRIPT -> SHOT PLAN -> TTS/SFX/TIMELINE -> FINAL MASTER`

A local correction invalidates only the selected node and its downstream
dependents. Unrelated images, videos, narration, and other paid assets remain
valid. The final MP4 may be re-exported, but valid assets are not regenerated.

## Cost and execution safety

- Complete episode hard cap remains USD 40.
- No budget override or headroom.
- No Runware, OpenAI, or ElevenLabs request is made during publication, audit,
  smoke testing, or installation.
- Scope generation occurs only after the explicit desktop button click.
- Discussion revisions occur only after the explicit send action.
- Provider keys are never written to repository files.
