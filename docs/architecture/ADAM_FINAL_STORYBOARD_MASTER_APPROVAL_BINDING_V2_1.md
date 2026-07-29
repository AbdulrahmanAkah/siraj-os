# Adam Final Storyboard Master Approval Binding v2.1

This stage records the user's exact approval phrase and binds it to:

- script fingerprint `ff540783...a4fb27`;
- storyboard fingerprint `867b88ad...88bf8`;
- the 70-shot directorial audit;
- the complete 37-event and 57-evidence trace.

The original approval request remains immutable. Separate approval, receipt,
binding, and non-paid visual-development gate artifacts are created.

## Gate effects

Approved:

- final cinematic script v2.1;
- religious safety of the final script;
- final storyboard master v2.1;
- non-paid Visual Bible development;
- non-paid Color Script development;
- non-paid animatic, shot-package planning, and audio previs.

Not approved:

- master visual identity itself;
- any generated-video execution;
- paid, direct, live-provider, or Runware execution.

The episode advances to
`MASTER_VISUAL_BIBLE_COLOR_SCRIPT_AND_NON_PAID_ANIMATIC_DEVELOPMENT`.

The previous storyboard-master CLI remains a valid audit tool. It recognises
the downstream approval binding, compares the immutable v2.1 fingerprints,
and preserves the approved episode definition during materialisation.

## Persisted audit-schema compatibility

The approval binder validates the fields actually persisted in `storyboard-master-directorial-audit-v2-1.json`. The unresolved-decision count is derived from complete 70/70 coverage, unique beats, zero generic placeholders, the passed covenant and chronology checks, and blocked execution states. It does not require a synthetic `unresolved_directorial_decisions` field that is absent from the audit artifact.

## Uniform execution-gate contract

Approval, receipt, binding, and visual-development gate artifacts each carry top-level `live_provider_execution`, `paid_execution`, `direct_execution`, and `runware_execution` fields. All four are `BLOCKED`. The same restrictions may also appear inside approval scope, but nested scope does not replace the top-level machine contract.
