# Anchorless Windows snapshot permission recovery V2

The previous installer failed before changing the repository because it looked
for one exact textual formatting of `DESKTOP_SNAPSHOT_REL`. The local controller
had accumulated later production patches, so the brittle anchor did not match.

This repair is intentionally anchorless:

- it appends a final runtime override of `_update_desktop_snapshot`;
- Python callers resolve the latest global function at execution time;
- it does not depend on the formatting or position of the existing constant;
- transient Windows access failures are retried and then deferred;
- a pending sidecar preserves the UI update;
- the V2 panel overlays that pending update during refresh;
- authoritative production files remain fail-closed;
- no provider request, paid retry, authorization change, or media mutation is
  performed during installation.
