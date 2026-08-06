# Full production-pipeline audit and cleanup V1

This certification replaces one-error-at-a-time debugging.

The installer:

- restores the Luna-certified storyboard to the canonical 70-shot treatment
  plan;
- forces `graphics_spec = null` on every non-graphics shot;
- verifies the exact 50 / 14 / 6 treatment split;
- verifies all 70 Luna certifications, seven batches and 43 TTS blocks;
- runs an isolated media-queue materialization using a copy of the live episode;
- runs `compileall`, the complete repository test suite and a Qt desktop smoke
  test;
- records all blockers in one report;
- adds a cryptographic runtime gate before any provider execution.

The gate does not claim that unknown future software defects are impossible.
It guarantees that all detected contract, state, schema, test and live-artifact
failures block before paid provider work.
