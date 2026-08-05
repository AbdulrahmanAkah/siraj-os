# Acceptance Resume Button Recovery V1

This acceptance fix prevents the **Continue episode** action from becoming a silent dead control.

## Corrections

- The continue action remains clickable when the stored status maps to `WAIT`, `REFRESH`, or `INSPECT_BLOCKER`.
- Every click immediately displays a visible diagnostic message.
- Stale runtime states can be reconstructed from canonical episode artifacts.
- The orchestrator state is backed up before any recovery write.
- A recovered state never creates a provider request or authorizes paid work.
- Paid media still requires the exact consolidated confirmation.
- Human scope review and human final review remain mandatory.
- Workspace buttons use explicit zero-argument lambdas to avoid Qt signal signature ambiguity.

## Recovery precedence

The recovery engine selects the latest trustworthy boundary in this order:

1. YouTube upload handoff manifest.
2. Publish manifest or approved final review.
3. Passed QA plus final master.
4. Final master awaiting QA.
5. Audio master awaiting montage.
6. Media queue complete or pending.
7. Editorial artifacts awaiting media queue construction.
8. Approved scope awaiting editorial execution.
9. Scope proposal awaiting human review.
10. New episode proposal.

Recovery only changes orchestration pointers and preserves all episode files and receipts.
