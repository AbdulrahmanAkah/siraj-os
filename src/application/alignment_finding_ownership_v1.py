"""Explicit ownership boundaries for normalized alignment findings.

The classification is local policy, not model output.  In particular a
downstream/pre-spend gate can be useful read-only context for a director, but
it is never a creative-repair target and a model cannot close it.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Iterable


class FindingOwner(StrEnum):
    SEMANTIC_CREATIVE = "SEMANTIC_CREATIVE"
    LOCAL_DETERMINISTIC = "LOCAL_DETERMINISTIC"
    DOWNSTREAM_GATE = "DOWNSTREAM_GATE"
    PROVIDER = "PROVIDER"
    STRUCTURAL = "STRUCTURAL"


EP002_OWNERSHIP: dict[str, FindingOwner] = {
    "LUNA-SEM-001": FindingOwner.SEMANTIC_CREATIVE,
    "LUNA-SEM-002": FindingOwner.SEMANTIC_CREATIVE,
    "LUNA-SEM-003": FindingOwner.SEMANTIC_CREATIVE,
    "LUNA-SEM-004": FindingOwner.SEMANTIC_CREATIVE,
    "LUNA-REP-001": FindingOwner.SEMANTIC_CREATIVE,
    "LUNA-GATE-001": FindingOwner.DOWNSTREAM_GATE,
}


def classify_alignment_finding(finding_id: str) -> FindingOwner:
    """Return deterministic ownership without trusting provider metadata."""

    normalized = str(finding_id or "").strip()
    if normalized in EP002_OWNERSHIP:
        return EP002_OWNERSHIP[normalized]
    if normalized.startswith("STRUCT-"):
        return FindingOwner.STRUCTURAL
    if normalized.startswith("PROVIDER-"):
        return FindingOwner.PROVIDER
    return FindingOwner.LOCAL_DETERMINISTIC


def permits_semantic_creative_repair(finding_id: str) -> bool:
    return classify_alignment_finding(finding_id) is FindingOwner.SEMANTIC_CREATIVE


def editable_finding_ids(finding_ids: Iterable[str]) -> list[str]:
    return [
        str(finding_id)
        for finding_id in finding_ids
        if permits_semantic_creative_repair(str(finding_id))
    ]
