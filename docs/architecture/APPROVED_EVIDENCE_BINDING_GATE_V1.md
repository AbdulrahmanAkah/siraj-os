# Approved Evidence Binding Gate v1

Status: `OFFLINE_RUNTIME_READY_HUMAN_APPROVAL_PENDING`

## Purpose

This layer opens the storyboard evidence gate only after two separate human-approved
records exist:

1. an approved evidence package containing source-backed evidence items; and
2. an approved event adjudication that decides how every episode event is treated.

It does not research, acquire, authenticate, grade, approve, or download evidence.
It does not call Runware or any other provider.

## Schemas

- `siraj-approved-evidence-package-v1`
- `siraj-event-evidence-adjudication-v1`
- `siraj-evidence-bound-cinematic-blueprint-v1`

## Event dispositions

- `include_assertive`: factual inclusion backed only by Quran-explicit, authentic
  Sunnah, or accepted-athar evidence classes.
- `include_qualified`: inclusion with an explicit audience-facing qualification.
- `omit_unverified`: event remains in the audit trail but is not narrated as fact.
- `editorial_only`: permitted only for an event whose event-map status is
  `editorial`.

Every required event must receive exactly one decision in the approved event order.
Quran-explicit events must be included assertively and must carry Quran-explicit
evidence.

## Source and approval controls

The binder requires all of the following:

- source package payload status `APPROVED`;
- episode source-package approval status `APPROVED`;
- acquired or verified source records;
- source checksums matching the evidence records;
- source records explicitly supporting the bound event;
- human approval records for both package and adjudication;
- episode evidence-package fingerprint matching the approved file;
- no orphan or multiply assigned evidence items.

Automated approvers such as `SYSTEM`, `AI`, or `MODEL` are rejected.

## Cinematic invariants

Evidence binding may change evidence mode and media treatment preference, but it may
not change:

- frame count or frame order;
- narrative function;
- spectacle level;
- planned duration;
- callback structure;
- generated-video preallocation, which remains zero.

Runware and live provider execution remain blocked.

## Current Adam state

The included files are non-executable templates only. The current Adam source
package is still a draft, so the gate remains:

`WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE`

No approval is inferred from the presence of Quran references, extraction files, or
source manifests. Human adjudication is mandatory.
