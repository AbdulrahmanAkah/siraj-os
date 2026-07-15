# Temporal Reasoning

## Boundary

Temporal reasoning derives BEFORE, AFTER, OVERLAPS, and CONTAINS solely from
explicit timeline dates. Supported phase-1 precision is YYYY, YYYY-MM, or
YYYY-MM-DD.

Equal dates produce OVERLAPS. A coarser date that is an exact prefix of a
more precise date produces CONTAINS. Otherwise chronological comparison
produces paired BEFORE and AFTER relations when enabled. Undated or malformed
dates produce no relation.

Relations are deduplicated, sorted by canonical tuple, and assigned
contiguous positions. IDs derive from canonical relation material.

Validation enforces canonical types, valid event references, non-self
relations, unique IDs, stable ordering, and count consistency. The layer
does not estimate dates, infer overlap, use NLP, or access external systems.
