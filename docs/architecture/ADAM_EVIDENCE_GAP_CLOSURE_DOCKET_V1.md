# Adam Evidence Gap Closure Docket v1

## Purpose

Convert the explicit uncovered-event list from `recovered-evidence-knowledge-v1.json`
into a deterministic human-review docket. This layer does not research, grade,
approve, quote, or bind evidence.

## Current Adam gaps

The recovered metadata identifies four uncovered events:

- `EV-ADAM-031`: first movement, sneeze, and speech attributed to Adam.
- `EV-ADAM-071`: the name Hawwa and transmitted creation details.
- `EV-ADAM-091`: transmitted views about the forbidden tree's type.
- `EV-ADAM-099`: editorial handoff to the temptation sequence.

The first three remain factual review items with no default disposition. The last
is an editorial event; the docket recommends `editorial_only`, but the template
still requires a human decision.

## Allowed factual decisions

- `include_assertive`
- `include_qualified`
- `omit_unverified`

Editorial events allow only `editorial_only`.

## Safety guarantees

- Evidence gate stays withheld.
- Automatic approval remains forbidden.
- Live provider execution stays blocked.
- No raw source text, quotation, or excerpt is copied.
- No candidate source or review artifact is inferred; only explicit metadata
  links are carried forward.
- The review template is non-executable and contains no approval.

## Outputs

- `projects/episode-001-adam/evidence/evidence-gap-closure-docket-v1.json`
- `projects/episode-001-adam/evidence/evidence-gap-review-v1.template.json`

The second file must be completed and approved by a human before it can become an
adjudication input to the approved-evidence binding gate.
