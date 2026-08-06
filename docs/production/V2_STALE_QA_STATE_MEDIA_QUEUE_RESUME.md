# V2 stale QA state and TTS fixture finalization

The V2 state-resume implementation was correct, but its focused regression
suite exposed an older test fixture whose Arabic narration was not sufficiently
vocalized for the current production TTS gate.

The production guard remains unchanged:

`TTS_TEXT_NOT_FULLY_DIACRITIZED`

Only the synthetic test narration is updated from an unvocalized phrase to a
fully vocalized phrase. The fixture continues to test the same six segments,
70-shot queue, budgets, graphics specifications, and idempotency.

After the fixture repair, the installer reruns the complete focused suite and
only then rebases the live stale V1 QA state to the authorized V2 queue-builder
entry state. No provider request or paid action occurs.
