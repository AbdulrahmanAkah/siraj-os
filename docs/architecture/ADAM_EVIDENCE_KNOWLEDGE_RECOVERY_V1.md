# Adam Evidence Knowledge Recovery v1

## Purpose

This layer recovers the substantial evidence work already present in the local
`episode-001-adam` workspace and connects it to a deterministic contract without
copying source text, approving claims, or opening the evidence gate.

The inspected local state contained nine normalized source directories and at
least 46 review artifacts. Those assets are valuable, but they are not yet a
human-approved evidence package.

## Inputs

The recovery runtime reads:

- `projects/episode-001-adam/contracts/source-package-v1.draft.json`
- `projects/episode-001-adam/editorial/event-map.json`
- normalized source directories under
  `projects/episode-001-adam/sources/secondary/assets/normalized/SRC-*`
- structured JSON/JSONL review artifacts under the existing review-stage
  directories
- `working/adam-truncated-window-repair-v1` when present

## Output

The generated output is:

`projects/episode-001-adam/evidence/recovered-evidence-knowledge-v1.json`

It contains only:

- repository-relative paths
- SHA-256 fingerprints
- sizes and record counts
- schema/status identifiers
- source, event and report identifiers
- candidate event links
- explicit recovery gaps

It does not contain raw source pages, quotations, API credentials or absolute
local paths.

## Security and approval posture

The generated manifest always records:

- `recovery_status = RECOVERED_REVIEW_PENDING`
- `evidence_gate_status = WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE`
- `automatic_evidence_approval = FORBIDDEN`
- `live_provider_execution = BLOCKED`

Recovery is not approval. Candidate source-event links remain non-authoritative
until the human approval and event adjudication contracts are completed.

## Validation

The runtime rejects:

- fewer than nine normalized sources
- fewer than 46 review artifacts
- unknown event identifiers
- symlinked evidence files
- invalid JSON/JSONL
- secret-like fields
- absolute-path leakage
- any manifest that opens the evidence gate

## Next stage

After recovery, the next stage is a human review dossier that turns the recovered
metadata into explicit per-event adjudication decisions. Only after those
decisions and a signed approved evidence package exist may
`ApprovedEvidenceBinder` open the gate.
