# SIRAJ Desktop Production Console V1

## Purpose

This stage turns the desktop dashboard into the sole operator surface for the
first real production task of episode 001.

Authorized scope:

- Episode: `episode-001-adam`
- Shot: `ADAM-DC2-S02-SH03`
- Beat: `ADAM-DC2-S02-SH03-B01`
- Provider: Runware
- Task: exactly one `videoInference`
- Model: `google:veo@3.1-lite`
- Output: one 8-second 1280×720 MP4
- Maximum authorized cost: USD 0.40

## Safety and cost gates

The immutable shot package remains unchanged. A separate human authorization
overlay opens exactly one desktop-initiated submission.

Before the network request, the console creates a durable lock containing the
task UUID and request hash. A second generation submission is then impossible.
Recovery can only poll the same task UUID.

The API key is accepted from the password field or `RUNWARE_API_KEY` and remains
in process memory only. It is never written to a file, receipt, log, or Git.

The publisher, audit, tests, and smoke test perform no Runware network request
and cannot spend credit.

## Operator workflow

1. Open the desktop interface.
2. Choose `الفيديو`, or press `استكمال` on episode Adam.
3. Review the immutable package and prompt.
4. Enter the API key or provide it through the environment.
5. Check the exact paid-execution confirmation.
6. Press `تنفيذ Beat 01 الآن` and confirm the final dialog.
7. Leave the console open while it submits, polls, downloads, hashes, and writes
   the execution receipt.
8. Open the MP4 outside the desktop interface.
9. Enter the five weighted review scores and any blocking failures.
10. Save the human review.

Beat 02 and all bulk generation remain blocked.
