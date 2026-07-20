"""Deterministic literal-evidence resolution for provider-facing text quotes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class EvidenceResolution:
    status: str
    text: str
    start: int | None
    end: int | None
    occurrences: tuple[int, ...]
    source_slice: str
    reason_code: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "occurrences": list(self.occurrences),
            "source_slice": self.source_slice,
            "reason_code": self.reason_code,
        }


def _occurrences(source_text: str, evidence_text: str) -> tuple[int, ...]:
    found: list[int] = []
    offset = source_text.find(evidence_text)
    while offset >= 0:
        found.append(offset)
        offset = source_text.find(evidence_text, offset + 1)
    return tuple(found)


def _anchor_candidates(
    source_text: str,
    starts: Iterable[int],
    evidence_text: str,
    anchors: Iterable[str],
) -> tuple[int, ...]:
    required = tuple(anchor for anchor in anchors if isinstance(anchor, str) and anchor)
    if not required:
        return ()
    matches: list[int] = []
    for start in starts:
        # Route anchors can be outside the evidence quote, but only a bounded
        # local context is considered. This is a deterministic disambiguator,
        # never fuzzy evidence acceptance.
        window = source_text[max(0, start - 160): min(len(source_text), start + len(evidence_text) + 160)]
        if all(anchor in window for anchor in required):
            matches.append(start)
    return tuple(matches)


def resolve_evidence_span(
    source_text: str,
    evidence_text: str,
    proposed_start: int | None = None,
    proposed_end: int | None = None,
    anchors: Iterable[str] | None = None,
) -> EvidenceResolution:
    """Resolve a literal quote without trusting provider offsets.

    A provider quote must remain byte-for-byte equal to a source slice. Invalid
    provider offsets are repaired only for a unique literal occurrence, or for
    one deterministically disambiguated by an offset clue or route anchors.
    """

    if not isinstance(evidence_text, str) or not evidence_text:
        return EvidenceResolution("REJECTED", "", None, None, (), "", "EVIDENCE_TEXT_EMPTY")
    if (
        isinstance(proposed_start, int)
        and isinstance(proposed_end, int)
        and 0 <= proposed_start < proposed_end <= len(source_text)
        and source_text[proposed_start:proposed_end] == evidence_text
    ):
        return EvidenceResolution(
            "MODEL_OFFSETS_VALID", evidence_text, proposed_start, proposed_end,
            (proposed_start,), evidence_text,
        )

    occurrences = _occurrences(source_text, evidence_text)
    if not occurrences:
        return EvidenceResolution("REJECTED", evidence_text, None, None, (), "", "EVIDENCE_TEXT_NOT_VERBATIM")
    if len(occurrences) == 1:
        start = occurrences[0]
        return EvidenceResolution(
            "OFFSET_REPAIRED_DETERMINISTICALLY", evidence_text, start,
            start + len(evidence_text), occurrences, source_text[start:start + len(evidence_text)],
        )

    if isinstance(proposed_start, int):
        distances = {start: abs(start - proposed_start) for start in occurrences}
        nearest_distance = min(distances.values())
        nearest = tuple(start for start in occurrences if distances[start] == nearest_distance)
        if len(nearest) == 1:
            start = nearest[0]
            return EvidenceResolution(
                "OFFSET_REPAIRED_DETERMINISTICALLY", evidence_text, start,
                start + len(evidence_text), occurrences, source_text[start:start + len(evidence_text)],
                "PROPOSED_OFFSET_DISAMBIGUATED",
            )

    anchored = _anchor_candidates(source_text, occurrences, evidence_text, anchors or ())
    if len(anchored) == 1:
        start = anchored[0]
        return EvidenceResolution(
            "OFFSET_REPAIRED_DETERMINISTICALLY", evidence_text, start,
            start + len(evidence_text), occurrences, source_text[start:start + len(evidence_text)],
            "ROUTE_ANCHORS_DISAMBIGUATED",
        )
    return EvidenceResolution("REJECTED", evidence_text, None, None, occurrences, "", "EVIDENCE_AMBIGUOUS")


__all__ = ["EvidenceResolution", "resolve_evidence_span"]
