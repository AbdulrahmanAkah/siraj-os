"""Stable renderers for controlled-alignment reports.

Reports are projections of immutable evidence.  They never mutate a provider
attempt, candidate, ledger, or authoritative alignment artifact.
"""

from __future__ import annotations

from typing import Any, Mapping


def render_controlled_alignment_markdown(report: Mapping[str, Any]) -> str:
    """Render a future report without leaving unresolved template markers."""

    baseline_hash = str(report.get("creative_baseline_hash") or "")
    candidate_hash = str(report.get("candidate_sha256") or "")
    classification = str(report.get("classification") or "UNKNOWN")
    return "\n".join(
        (
            "# Controlled Alignment Validation",
            "",
            f"Result: `{classification}`.",
            "",
            f"Creative baseline hash: `{baseline_hash}`",
            f"Candidate hash: `{candidate_hash}`",
            "",
        )
    )
