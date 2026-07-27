# Provider Manual Test and Precise Pricing v1

## Status

`OFFLINE_INTAKE_READY_LIVE_EXECUTION_BLOCKED`

This layer records manually observed provider costs and capabilities, converts
explicit frame quote specifications into verified media options, and performs
budget optimization with six-decimal USD precision.

It performs no HTTP request and cannot authorize paid execution.

## Why this layer exists

Provider prices can be below one cent. A two-decimal price model can silently
turn a real cost such as `0.003125` into `0.00` or `0.01`, which distorts the
media mix across many shots. The precise planner therefore represents money as
integer micro-USD internally while preserving readable decimal strings in
manifests.

## Manual provider test record

A record stores only sanitized observations:

- provider and exact model identifiers
- treatment and media category
- billing basis
- exact observed charged cost
- billed units
- output count or generated-video seconds
- reviewed quality and reliability scores
- observed latency
- SHA-256 fingerprints of sanitized request and response manifests
- test time and pass/fail status

It must not store API keys, authorization headers, credentials, or raw secret
payloads.

## Verified catalog

Only passing records may enter `VerifiedProviderPriceCatalog`. A successful
image test does not create or imply a video price. Each treatment and model must
be supported by its own verified record or another explicit price source.

## Explicit quote semantics

The system does not guess how provider billing scales. Each `FrameQuoteSpec`
selects a verified observation and explicitly states requested billing units and
video duration. For per-second prices, requested units must equal requested
video seconds.

## Precise planning

`PreciseDynamicCinematicBudgetPlanner`:

- chooses one eligible option per storyboard frame
- preserves the editorial preference and motion constraints
- maximizes quality and reliability under the episode limit
- computes category totals as outputs
- keeps the USD 40 target and USD 45 hard cap
- requires explicit justification to use hard headroom
- enforces the 300-second generated-video ceiling
- never enables provider execution

## Runware manual test sequence

The first Runware image test should record:

1. exact model identifier
2. sanitized request fingerprint
3. sanitized response/output-manifest fingerprint
4. charged cost displayed by the provider
5. billed units and output count
6. latency
7. reviewed quality score
8. reviewed reliability score
9. UTC test time

Do not paste the Runware API key into any manifest, terminal output, source file,
or conversation.
