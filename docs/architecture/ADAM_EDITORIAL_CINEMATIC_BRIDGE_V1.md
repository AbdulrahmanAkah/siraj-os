# Adam Editorial Cinematic Bridge v1

## Purpose

This bridge turns the recovered `episode-001-adam` editorial baseline into a
real `Storyboard` and then compiles it with the cinematic-series compiler. The
result is an offline editorial blueprint, not a render plan and not an approved
evidence package.

## Inputs

The bridge reads these episode files:

- `contracts/episode-definition-v1.json`
- `contracts/integration-validation-v1.json`
- `contracts/source-package-v1.draft.json`
- `editorial/event-map.json`
- `editorial/human-decisions.json`
- `cinematic/storyboard-profile-v1.json`

Every input fingerprint is calculated after UTF-8 decoding and LF line-ending
normalization. Windows CRLF materialization therefore does not create false
hash failures.

## Adam frame structure

The profile contains 14 frames:

1. Symbolic cold open.
2. Central question and epistemic limits.
3. The state before Adam.
4. Announcement of Adam's creation.
5. Adam's formation.
6. Beginning of Adam's life.
7. Knowledge and honor.
8. Command to prostrate.
9. The angels prostrate.
10. Iblis refuses, argues, is expelled, and declares enmity — the climax.
11. Covenant material, explicitly marked chronologically uncertain/deferred.
12. Adam's spouse and residence in the Garden.
13. Prohibition of the tree without asserting its kind.
14. Promise of the next episode: temptation, sin, repentance, and descent.

The factual frame coverage contains all 37 required event ids exactly once and
in the approved event order. The cold open may tease later event ids only in
trace metadata; a tease is never treated as evidence or as factual chronology.

## Evidence posture

The recovered episode definition says source-package approval is
`NOT_REQUESTED`, and final verification is deferred. Consequently:

- every `StoryboardFrame.referenced_evidence_ids` list is empty;
- documentary evidence mode is not enabled;
- the bridge status is
  `WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE`;
- even Quran-explicit event labels in the editorial map are not silently
  converted into evidence-package ids;
- if the source package later becomes `APPROVED`, bridge v1 stops and requires
  an explicit event-to-evidence binding layer.

## Cinematic and budget behavior

- Episode target duration: 1,320 seconds (22 minutes).
- Generated-video preallocation: 0 seconds.
- Dynamic media budget allocation remains deferred until priced options exist.
- Target budget guardrail: USD 40.
- Hard budget cap: USD 45.
- Runware execution remains blocked.
- No provider, network, credential, or paid action is used.

## Output

The deterministic output is written to:

`projects/episode-001-adam/cinematic/editorial-cinematic-blueprint-v1.json`

It contains the source trace for every frame, the storyboard, the compiled
cinematic plan, media-treatment preferences, duration allocation, budget
guardrails, and all execution gates.
