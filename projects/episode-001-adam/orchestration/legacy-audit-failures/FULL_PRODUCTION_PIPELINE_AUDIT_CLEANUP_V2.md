# Full Production Pipeline Audit & Cleanup V2

This release corrects the schema error in V1 of the audit package. The canonical
storyboard does not use a generic `treatment` field. Its production routing
field is `final_budget_treatment`.

The audited contract is:

- `ANIMATED_STILL_COMPOSITING`: 44 shots
- `GENERATED_VIDEO`: 20 shots
- `GRAPHICS`: 6 shots
- all non-graphics shots must have `graphics_spec = null` after integration
- the graphics queue builder must materialize exactly 44 image jobs, 20 video
  jobs and 6 local-graphics jobs

Before any provider execution, the installer normalizes the Luna-certified
storyboard from the canonical V2 plan, removes every stale embedded graphics
spec so the deterministic graphics builder regenerates all six specs, runs a
sandbox queue materialization, compiles all Python sources, runs the complete
test suite, opens the desktop console in Qt offscreen mode, and writes a stable
semantic fingerprint.

The runtime gate ignores only deterministic downstream `graphics_spec`
materialization. It remains sensitive to code, prompts, TTS text, treatment
routing, the production standard, and the director-approved storyboard.
