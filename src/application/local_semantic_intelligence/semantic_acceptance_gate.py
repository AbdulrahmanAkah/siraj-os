"""Conservative acceptance gate for evidence-bound Gemini route outputs.

This module does not call a provider. It revalidates persisted structured output,
repairs only uniquely alignable Arabic diacritic differences, checks isnad/matn
boundaries, and reports likely extraction incompleteness for human review.
"""

from __future__ import annotations

from copy import deepcopy
import re
import unicodedata
from typing import Any

from .evidence_resolution import resolve_evidence_span


ACCEPTANCE_GATE_SCHEMA_VERSION = "siraj-semantic-acceptance-gate-v2"
MATN_BOUNDARY_CONTRACT = "RELATIVE_TO_EVIDENCE_TEXT_UNICODE_CODEPOINT_OFFSET"

_ROUTE_COLLECTIONS = {
    # Resolve wider relational evidence before entity-only quotes. This permits
    # a repeated entity surface to be disambiguated only when one occurrence
    # lies inside an already accepted parent evidence span.
    "PERSON_AND_STATUS": (
        ("statuses", "status"),
        ("relations", "relation"),
        ("entities", "entity"),
    ),
    "APPOINTMENT_AND_OFFICE": (
        ("appointments", "appointment"),
        ("entities", "entity"),
    ),
    "ISNAD": (
        ("isnads", "isnad"),
        ("entities", "entity"),
    ),
    "SIRA_POETRY": (
        ("events", "event"),
        ("entities", "entity"),
    ),
}

_ISNAD_CUE_PATTERNS = (
    (
        "TRANSMISSION_VERB",
        re.compile(
            r"\b(?:حدثنا|حدثني|أخبرنا|أخبرني|اخبرنا|اخبرني|سمعت)\b"
        ),
    ),
    (
        "ABRIDGED_REPORT",
        re.compile(r"\b(?:وفي\s+رواية|في\s+رواية)\s+عن\b"),
    ),
    (
        "ATTRIBUTED_REPORT",
        re.compile(r"\b(?:حكى|روى)\b[^.\n]{0,120}\bعن\b"),
    ),
)

_PUNCTUATION = frozenset("،؛:,.!?؟()[]{}«»\"'ـ-–—")


def _canonicalize_with_mapping(
    text: str,
) -> tuple[str, list[int], list[int]]:
    """Strip only combining marks/tatweel while preserving source offsets."""

    normalized: list[str] = []
    starts: list[int] = []
    ends: list[int] = []

    for index, character in enumerate(text):
        if (
            character == "\u0640"
            or unicodedata.category(character) in {"Mn", "Me"}
        ):
            if ends:
                ends[-1] = index + 1
            continue

        emitted = " " if character.isspace() else character

        if emitted == " " and normalized and normalized[-1] == " ":
            ends[-1] = index + 1
            continue

        normalized.append(emitted)
        starts.append(index)
        ends.append(index + 1)

    return "".join(normalized), starts, ends


def canonicalize_arabic_evidence(text: str) -> str:
    """Return a comparison-only Arabic form; never persist it as evidence."""

    normalized, _, _ = _canonicalize_with_mapping(str(text).strip())
    return normalized.strip()


def _all_occurrences(source: str, target: str) -> list[int]:
    positions: list[int] = []
    position = source.find(target)

    while position >= 0:
        positions.append(position)
        position = source.find(target, position + 1)

    return positions


def align_unique_source_quote(
    source_text: str,
    provider_quote: str,
    proposed_start: int | None = None,
    proposed_end: int | None = None,
) -> dict[str, Any]:
    """Resolve exact evidence, or a unique diacritic-only source equivalent."""

    quote = str(provider_quote).strip()

    literal = resolve_evidence_span(
        source_text,
        quote,
        proposed_start,
        proposed_end,
    )

    if literal.status != "REJECTED":
        return {
            "status": literal.status,
            "reason_code": literal.reason_code,
            "provider_quote": quote,
            "source_quote": literal.source_slice or literal.text,
            "start": literal.start,
            "end": literal.end,
            "occurrences": list(literal.occurrences),
            "repair_applied": False,
        }

    if literal.reason_code != "EVIDENCE_TEXT_NOT_VERBATIM":
        return {
            "status": "REJECTED",
            "reason_code": literal.reason_code,
            "provider_quote": quote,
            "source_quote": "",
            "start": None,
            "end": None,
            "occurrences": list(literal.occurrences),
            "repair_applied": False,
        }

    normalized_source, starts, ends = _canonicalize_with_mapping(source_text)
    normalized_quote = canonicalize_arabic_evidence(quote)

    if not normalized_quote:
        return {
            "status": "REJECTED",
            "reason_code": "NORMALIZED_EVIDENCE_EMPTY",
            "provider_quote": quote,
            "source_quote": "",
            "start": None,
            "end": None,
            "occurrences": [],
            "repair_applied": False,
        }

    normalized_positions = _all_occurrences(
        normalized_source,
        normalized_quote,
    )

    if len(normalized_positions) != 1:
        return {
            "status": "REJECTED",
            "reason_code": (
                "NORMALIZED_EVIDENCE_NOT_FOUND"
                if not normalized_positions
                else "NORMALIZED_EVIDENCE_AMBIGUOUS"
            ),
            "provider_quote": quote,
            "source_quote": "",
            "start": None,
            "end": None,
            "occurrences": normalized_positions,
            "repair_applied": False,
        }

    normalized_start = normalized_positions[0]
    normalized_end = normalized_start + len(normalized_quote)
    source_start = starts[normalized_start]
    source_end = ends[normalized_end - 1]
    source_quote = source_text[source_start:source_end]

    if canonicalize_arabic_evidence(source_quote) != normalized_quote:
        return {
            "status": "REJECTED",
            "reason_code": "SOURCE_SLICE_ALIGNMENT_MISMATCH",
            "provider_quote": quote,
            "source_quote": source_quote,
            "start": source_start,
            "end": source_end,
            "occurrences": [source_start],
            "repair_applied": False,
        }

    return {
        "status": "ALIGNED_TO_UNIQUE_SOURCE_SLICE",
        "reason_code": "DIACRITIC_INSENSITIVE_UNIQUE_MATCH",
        "provider_quote": quote,
        "source_quote": source_quote,
        "start": source_start,
        "end": source_end,
        "occurrences": [source_start],
        "repair_applied": True,
    }


def _repair_entity_surface(
    source_text: str,
    item: dict[str, Any],
    evidence_start: int,
    evidence_end: int,
) -> dict[str, Any]:
    surface = str(item.get("surface", "")).strip()
    evidence_slice = source_text[evidence_start:evidence_end]
    local = align_unique_source_quote(evidence_slice, surface)

    if local["status"] == "REJECTED":
        return {
            "status": "REJECTED",
            "reason_code": "ENTITY_SURFACE_NOT_LITERAL_IN_EVIDENCE",
            "resolution": local,
        }

    local_start = local["start"]
    local_end = local["end"]

    if not isinstance(local_start, int) or not isinstance(local_end, int):
        return {
            "status": "REJECTED",
            "reason_code": "ENTITY_SURFACE_OFFSETS_MISSING",
            "resolution": local,
        }

    start = evidence_start + local_start
    end = evidence_start + local_end
    source_surface = source_text[start:end]
    changed = source_surface != surface
    item["surface"] = source_surface

    if "exact_surface" in item:
        item["exact_surface"] = source_surface

    return {
        "status": "PASS",
        "reason_code": local["reason_code"],
        "source_surface": source_surface,
        "start": start,
        "end": end,
        "repair_applied": changed,
    }


def _disambiguate_entity_evidence_in_context(
    source_text: str,
    provider_quote: str,
    resolution: dict[str, Any],
    context_ranges: list[tuple[int, int]],
) -> dict[str, Any]:
    if (
        resolution.get("status") != "REJECTED"
        or resolution.get("reason_code") != "EVIDENCE_AMBIGUOUS"
    ):
        return resolution

    quote = str(provider_quote).strip()
    candidates = [
        int(start)
        for start in resolution.get("occurrences", [])
        if isinstance(start, int)
        and any(
            parent_start <= start
            and start + len(quote) <= parent_end
            for parent_start, parent_end in context_ranges
        )
    ]

    if len(candidates) != 1:
        return resolution

    start = candidates[0]
    return {
        "status": "CONTEXT_DISAMBIGUATED_LITERAL",
        "reason_code": "UNIQUE_OCCURRENCE_INSIDE_ACCEPTED_PARENT_EVIDENCE",
        "provider_quote": quote,
        "source_quote": source_text[start:start + len(quote)],
        "start": start,
        "end": start + len(quote),
        "occurrences": list(resolution.get("occurrences", [])),
        "repair_applied": False,
    }


def repair_route_output(
    source_text: str,
    route: str,
    provider_output: dict[str, Any],
) -> dict[str, Any]:
    """Return a repaired copy plus a complete, rebuilt evidence ledger."""

    if route not in _ROUTE_COLLECTIONS:
        raise ValueError(
            f"SEMANTIC_ACCEPTANCE_ROUTE_UNSUPPORTED:{route}"
        )

    repaired = deepcopy(provider_output)
    repairs: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    evidence_quotes: list[dict[str, Any]] = []
    context_ranges: list[tuple[int, int]] = []

    for collection, kind in _ROUTE_COLLECTIONS[route]:
        values = repaired.get(collection, [])

        if not isinstance(values, list):
            rejections.append(
                {
                    "collection": collection,
                    "reason_code": "COLLECTION_NOT_LIST",
                }
            )
            repaired[collection] = []
            continue

        for item_index, item in enumerate(values):
            if not isinstance(item, dict):
                rejections.append(
                    {
                        "collection": collection,
                        "item_index": item_index,
                        "reason_code": "ITEM_NOT_OBJECT",
                    }
                )
                continue

            evidence = item.get("evidence")

            if not isinstance(evidence, dict):
                rejections.append(
                    {
                        "collection": collection,
                        "item_index": item_index,
                        "reason_code": "EVIDENCE_OBJECT_MISSING",
                    }
                )
                continue

            provider_quote = str(evidence.get("text", ""))
            resolution = align_unique_source_quote(
                source_text,
                provider_quote,
                evidence.get("start"),
                evidence.get("end"),
            )
            if kind == "entity":
                resolution = _disambiguate_entity_evidence_in_context(
                    source_text,
                    provider_quote,
                    resolution,
                    context_ranges,
                )

            record: dict[str, Any] = {
                "collection": collection,
                "item_index": item_index,
                "item_kind": kind,
                **resolution,
            }

            if resolution["status"] == "REJECTED":
                rejections.append(record)
                continue

            evidence["text"] = resolution["source_quote"]
            evidence["start"] = resolution["start"]
            evidence["end"] = resolution["end"]
            item_repaired = bool(resolution["repair_applied"])

            if kind == "entity":
                surface_result = _repair_entity_surface(
                    source_text,
                    item,
                    int(resolution["start"]),
                    int(resolution["end"]),
                )
                record["surface_resolution"] = surface_result

                if surface_result["status"] == "REJECTED":
                    rejections.append(
                        {
                            **record,
                            "reason_code": surface_result["reason_code"],
                        }
                    )
                    continue

                item_repaired = item_repaired or bool(
                    surface_result.get("repair_applied", False)
                )

            if kind != "entity":
                context_ranges.append(
                    (int(evidence["start"]), int(evidence["end"]))
                )

            evidence_quotes.append(
                {
                    "collection": collection,
                    "item_index": item_index,
                    "text": evidence["text"],
                    "start": evidence["start"],
                    "end": evidence["end"],
                }
            )

            if item_repaired:
                repairs.append(record)

    return {
        "schema_version": ACCEPTANCE_GATE_SCHEMA_VERSION,
        "route": route,
        "repaired_output": repaired,
        "repair_count": len(repairs),
        "repairs": repairs,
        "rejection_count": len(rejections),
        "rejections": rejections,
        "evidence_quote_count": len(evidence_quotes),
        "evidence_quotes": evidence_quotes,
    }


def validate_matn_boundary(
    evidence_text: str,
    boundary: Any,
) -> dict[str, Any]:
    """Validate the explicit boundary contract without guessing a new value."""

    quote = str(evidence_text)
    base = {
        "contract": MATN_BOUNDARY_CONTRACT,
        "boundary": boundary,
        "evidence_length": len(quote),
    }

    if boundary is None:
        return {
            **base,
            "status": "UNSPECIFIED",
            "severity": "WARNING",
            "reason_code": "MATN_BOUNDARY_UNSPECIFIED",
        }

    if isinstance(boundary, bool) or not isinstance(boundary, int):
        return {
            **base,
            "status": "INVALID",
            "severity": "ERROR",
            "reason_code": "MATN_BOUNDARY_NOT_INTEGER",
        }

    if not 0 < boundary < len(quote):
        return {
            **base,
            "status": "INVALID",
            "severity": "ERROR",
            "reason_code": "MATN_BOUNDARY_OUT_OF_RANGE",
        }

    if unicodedata.category(quote[boundary]) in {"Mn", "Me"}:
        return {
            **base,
            "status": "INVALID",
            "severity": "ERROR",
            "reason_code": "MATN_BOUNDARY_GRAPHEME_SPLIT",
            "context": quote[max(0, boundary - 8) : boundary + 8],
        }

    previous = quote[boundary - 1]
    current = quote[boundary]

    if not (previous.isspace() or previous in _PUNCTUATION):
        return {
            **base,
            "status": "INVALID",
            "severity": "ERROR",
            "reason_code": "MATN_BOUNDARY_NOT_TOKEN_START",
            "context": quote[max(0, boundary - 8) : boundary + 8],
        }

    if current.isspace() or current in _PUNCTUATION:
        return {
            **base,
            "status": "INVALID",
            "severity": "ERROR",
            "reason_code": "MATN_BOUNDARY_POINTS_TO_SEPARATOR",
            "context": quote[max(0, boundary - 8) : boundary + 8],
        }

    normalized_prefix = canonicalize_arabic_evidence(
        quote[:boundary]
    )

    if not any(
        pattern.search(normalized_prefix)
        for _, pattern in _ISNAD_CUE_PATTERNS
    ):
        return {
            **base,
            "status": "INVALID",
            "severity": "ERROR",
            "reason_code": (
                "MATN_BOUNDARY_PREFIX_HAS_NO_TRANSMISSION_CUE"
            ),
        }

    return {
        **base,
        "status": "VALID",
        "severity": "INFO",
        "reason_code": "",
        "matn_preview": quote[boundary : boundary + 120],
    }


def detect_isnad_candidates(
    source_text: str,
) -> list[dict[str, Any]]:
    """Detect high-precision transmission cues; this is a completeness alarm."""

    normalized, starts, ends = _canonicalize_with_mapping(
        source_text
    )
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for cue_type, pattern in _ISNAD_CUE_PATTERNS:
        for match in pattern.finditer(normalized):
            source_start = starts[match.start()]
            source_end = ends[match.end() - 1]
            key = (cue_type, source_start)

            if key in seen:
                continue

            seen.add(key)
            candidates.append(
                {
                    "cue_type": cue_type,
                    "start": source_start,
                    "end": source_end,
                    "text": source_text[source_start:source_end],
                    "context": source_text[
                        max(0, source_start - 80) :
                        min(len(source_text), source_end + 160)
                    ],
                }
            )

    return sorted(
        candidates,
        key=lambda item: (item["start"], item["cue_type"]),
    )


def assess_isnad_completeness(
    source_text: str,
    repaired_output: dict[str, Any],
) -> dict[str, Any]:
    candidates = detect_isnad_candidates(source_text)
    extracted_ranges: list[tuple[int, int]] = []

    for item in repaired_output.get("isnads", []):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("evidence"), dict)
        ):
            continue

        start = item["evidence"].get("start")
        end = item["evidence"].get("end")

        if isinstance(start, int) and isinstance(end, int):
            extracted_ranges.append((start, end))

    uncovered = [
        candidate
        for candidate in candidates
        if not any(
            start <= candidate["start"] < end
            for start, end in extracted_ranges
        )
    ]

    return {
        "status": "COMPLETE" if not uncovered else "PARTIAL",
        "candidate_count": len(candidates),
        "extracted_isnad_count": len(extracted_ranges),
        "covered_candidate_count": len(candidates) - len(uncovered),
        "uncovered_candidate_count": len(uncovered),
        "uncovered_candidates": uncovered,
        "method": "HIGH_PRECISION_TRANSMISSION_CUE_COVERAGE",
    }


def evaluate_semantic_acceptance(
    source_text: str,
    route: str,
    provider_output: dict[str, Any],
) -> dict[str, Any]:
    """Apply gate v2 and return repaired output plus an auditable decision."""

    repair = repair_route_output(
        source_text,
        route,
        provider_output,
    )
    repaired_output = repair["repaired_output"]
    boundary_checks: list[dict[str, Any]] = []

    if route == "ISNAD":
        for item_index, item in enumerate(
            repaired_output.get("isnads", [])
        ):
            if not isinstance(item, dict):
                continue

            evidence = item.get("evidence", {})
            check = validate_matn_boundary(
                str(evidence.get("text", "")),
                item.get("matn_boundary"),
            )
            boundary_checks.append(
                {"item_index": item_index, **check}
            )

        completeness = assess_isnad_completeness(
            source_text,
            repaired_output,
        )
    else:
        completeness = {
            "status": "NOT_APPLICABLE",
            "candidate_count": 0,
            "uncovered_candidate_count": 0,
            "uncovered_candidates": [],
        }

    boundary_errors = [
        item
        for item in boundary_checks
        if item.get("severity") == "ERROR"
    ]
    boundary_warnings = [
        item
        for item in boundary_checks
        if item.get("severity") == "WARNING"
    ]
    hard_failure = bool(
        repair["rejections"] or boundary_errors
    )
    needs_review = bool(
        repair["repairs"]
        or boundary_warnings
        or completeness.get("status") == "PARTIAL"
    )

    if hard_failure:
        status = "FAIL"
    elif needs_review:
        status = "PARTIAL_PASS"
    else:
        status = "PASS"

    production_acceptance = (
        "BLOCKED"
        if hard_failure
        or completeness.get("status") == "PARTIAL"
        else "HUMAN_REVIEW_REQUIRED"
    )

    return {
        "schema_version": ACCEPTANCE_GATE_SCHEMA_VERSION,
        "status": status,
        "route": route,
        "production_acceptance": production_acceptance,
        "human_review_required": True,
        "repair_count": repair["repair_count"],
        "repairs": repair["repairs"],
        "rejection_count": repair["rejection_count"],
        "rejections": repair["rejections"],
        "evidence_quote_count": repair["evidence_quote_count"],
        "evidence_quotes": repair["evidence_quotes"],
        "matn_boundary_contract": MATN_BOUNDARY_CONTRACT,
        "matn_boundary_checks": boundary_checks,
        "matn_boundary_error_count": len(boundary_errors),
        "isnad_completeness": completeness,
        "repaired_output": repaired_output,
    }


def build_context_window(
    previous_text: str,
    target_text: str,
    next_text: str,
    *,
    previous_tail_characters: int = 600,
    next_head_characters: int = 600,
) -> dict[str, Any]:
    """Build an explicit cross-page prompt envelope without mixing provenance."""

    previous_tail = str(previous_text)[
        -max(0, previous_tail_characters) :
    ]
    next_head = str(next_text)[
        : max(0, next_head_characters)
    ]

    return {
        "schema_version": "siraj-semantic-context-window-v1",
        "previous_context": previous_tail,
        "target_text": str(target_text),
        "next_context": next_head,
        "evidence_policy": (
            "TARGET_TEXT_ONLY_UNLESS_CROSS_PAGE_EXPLICIT"
        ),
        "cross_page_items_require_explicit_marker": True,
    }


__all__ = [
    "ACCEPTANCE_GATE_SCHEMA_VERSION",
    "MATN_BOUNDARY_CONTRACT",
    "align_unique_source_quote",
    "assess_isnad_completeness",
    "build_context_window",
    "canonicalize_arabic_evidence",
    "detect_isnad_candidates",
    "evaluate_semantic_acceptance",
    "repair_route_output",
    "validate_matn_boundary",
]
