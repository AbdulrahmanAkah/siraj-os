# Runware Seedream Negative Prompt Recovery V1

This release fixes the first real end-to-end media execution failure for episode 001.

## Root cause

Runware rejected `negativePrompt` for the `bytedance:seedream@5.0-pro` architecture with `unsupportedArchitectureNegativePrompt`.

## Fix

- Omit `negativePrompt` when constructing or submitting Seedream 5 Pro tasks.
- Preserve negative prompts for models whose architecture supports them.
- Classify the exact HTTP 400 response as a terminal, non-ambiguous provider rejection.
- Never poll a rejected task UUID as though it were still running.
- Archive the failed lock and reset the queue item only for a new explicit paid authorization.
- Sanitize all existing Seedream task drafts in the episode 001 queue without provider requests.

## Financial safety

The recovery sends zero provider requests and performs no automatic resubmission. A new click and explicit consolidated authorization are required before production continues.
