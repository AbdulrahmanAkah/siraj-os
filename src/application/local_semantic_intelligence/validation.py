"""Deterministic validation for local semantic-provider outputs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from src.application.operations_common import deterministic_id

from .models import SEMANTIC_SCHEMA_VERSION


def canonicalize_literal_spans(
    payload: dict[str, Any],
    original_text: str,
) -> tuple[dict[str, Any], list[str]]:
    """Derive invalid offsets only from a unique literal evidence string.

    The model remains responsible for selecting the evidence.  This routine
    never guesses a span: an ambiguous or absent literal is left unchanged for
    the validator to reject.  It makes Unicode offsets deterministic across
    Windows code pages because all operations occur on decoded Python text.
    """

    normalized = deepcopy(payload)
    repairs: list[str] = []

    def locate(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                locate(item)
            return
        if not isinstance(value, dict):
            return
        if {"start", "end", "text"}.issubset(value):
            evidence = value.get("text")
            if isinstance(evidence, str) and evidence:
                start = value.get("start")
                end = value.get("end")
                current_matches = (
                    isinstance(start, int)
                    and isinstance(end, int)
                    and 0 <= start < end <= len(original_text)
                    and original_text[start:end] == evidence
                )
                if not current_matches:
                    matches: list[int] = []
                    position = original_text.find(evidence)
                    while position >= 0:
                        matches.append(position)
                        position = original_text.find(evidence, position + 1)
                    if len(matches) == 1:
                        value["start"] = matches[0]
                        value["end"] = matches[0] + len(evidence)
                        repairs.append("LITERAL_EVIDENCE_OFFSET_DERIVED")
        for child in value.values():
            locate(child)

    locate(normalized)
    return normalized, sorted(set(repairs))


def _span(value: Any, text: str) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(value, dict):
        return None, "EVIDENCE_SPAN_MISSING"
    try:
        start = int(value["start"])
        end = int(value["end"])
        evidence_text = str(value["text"])
    except (KeyError, TypeError, ValueError):
        return None, "EVIDENCE_SPAN_INVALID"
    if start < 0 or end <= start or end > len(text):
        return None, "EVIDENCE_SPAN_OUT_OF_RANGE"
    if text[start:end] != evidence_text:
        return None, "EVIDENCE_TEXT_MISMATCH"
    return {"start": start, "end": end, "text": evidence_text}, None


def _items(outputs: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for stage_key in ("mentions", "events_relations", "claims_attribution"):
        payload = outputs.get(stage_key, {})
        if not isinstance(payload, dict):
            continue
        for collection in (
            "entities",
            "events",
            "relations",
            "institutions",
            "claims",
            "isnads",
            "temporals",
        ):
            for item in payload.get(collection, []):
                if isinstance(item, dict):
                    yield collection, item


def _item_id(collection: str, item: dict[str, Any]) -> str:
    keys = {
        "entities": "mention_id",
        "events": "event_id",
        "relations": "relation_id",
        "institutions": "record_id",
        "claims": "claim_id",
        "isnads": "isnad_id",
        "temporals": "temporal_id",
    }
    return str(item.get(keys[collection], ""))


def validate_semantic_outputs(
    original_text: str,
    source_id: str,
    locator: str,
    outputs: dict[str, Any],
) -> dict[str, Any]:
    """Validate literal evidence and cross-references without model judgment."""

    issues: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    mention_ids = {
        str(item.get("mention_id", ""))
        for item in outputs.get("mentions", {}).get("entities", [])
        if isinstance(item, dict)
    }
    evidence_ranges: list[tuple[int, int, str, list[str]]] = []

    def add_issue(
        code: str,
        subject_id: str,
        severity: str = "ERROR",
        detail: str = "",
    ) -> None:
        issues.append(
            {
                "issue_id": deterministic_id(
                    "semantic_validation_issue",
                    [code, subject_id, detail],
                ),
                "code": code,
                "severity": severity,
                "subject_id": subject_id,
                "detail": detail,
            }
        )

    for key, payload in outputs.items():
        if key == "structure":
            continue
        if isinstance(payload, dict) and payload.get("schema_version") not in {
            None,
            SEMANTIC_SCHEMA_VERSION,
        }:
            add_issue("SCHEMA_VERSION_MISMATCH", key)

    for collection, item in _items(outputs):
        subject_id = _item_id(collection, item)
        if not subject_id:
            add_issue("ITEM_ID_MISSING", collection)
            subject_id = f"{collection}:missing"
        elif subject_id in seen_ids:
            add_issue("DUPLICATE_ITEM_ID", subject_id)
        else:
            seen_ids.add(subject_id)

        item_source = str(item.get("source_id", source_id))
        item_locator = str(item.get("locator", locator))
        if item_source != source_id or item_locator != locator:
            add_issue("PROVENANCE_MISMATCH", subject_id)

        evidence_value = (
            item.get("evidence")
            or item.get("trigger")
            or item.get("exact_chain_range")
        )
        evidence, span_error = _span(evidence_value, original_text)
        if span_error:
            add_issue(span_error, subject_id)
        elif evidence is not None:
            rationale = [
                str(value)
                for value in item.get("rationale_codes", [])
            ]
            evidence_ranges.append(
                (evidence["start"], evidence["end"], subject_id, rationale)
            )

        if collection == "entities":
            if (
                item.get("exact_surface") != (evidence or {}).get("text")
                or item.get("start") != (evidence or {}).get("start")
                or item.get("end") != (evidence or {}).get("end")
            ):
                add_issue("ENTITY_SURFACE_SPAN_MISMATCH", subject_id)
        elif collection == "events":
            for participant in item.get("participants", []):
                mention_reference = str(
                    participant.get("mention_reference")
                    or participant.get("mention_id", "")
                )
                exact_surface = str(participant.get("exact_surface", ""))
                role = str(participant.get("role", ""))
                unresolved = "UNRESOLVED" in role
                if mention_reference and mention_reference not in mention_ids:
                    add_issue("EVENT_UNKNOWN_PARTICIPANT", subject_id)
                if not mention_reference and not exact_surface:
                    add_issue("EVENT_PARTICIPANT_REFERENCE_MISSING", subject_id)
                if exact_surface and exact_surface not in original_text:
                    add_issue("EVENT_PARTICIPANT_NOT_LITERAL", subject_id)
                if unresolved and not exact_surface:
                    add_issue("UNRESOLVED_ACTOR_NOT_TEXTUAL", subject_id)
            for place in item.get("places", []):
                if isinstance(place, str):
                    add_issue("LEGACY_EVENT_PLACE_REQUIRES_REVIEW", subject_id, "WARNING")
                    continue
                mention_reference = str(place.get("mention_reference", ""))
                exact_surface = str(place.get("exact_surface", ""))
                if mention_reference and mention_reference not in mention_ids:
                    add_issue("EVENT_UNKNOWN_PLACE_REFERENCE", subject_id)
                if not mention_reference and not exact_surface:
                    add_issue("EVENT_PLACE_REFERENCE_MISSING", subject_id)
                if exact_surface and exact_surface not in original_text:
                    add_issue("EVENT_PLACE_NOT_LITERAL", subject_id)
                if not str(place.get("role", "")):
                    add_issue("EVENT_PLACE_ROLE_MISSING", subject_id)
        elif collection == "relations":
            if str(item.get("subject_mention", "")) not in mention_ids:
                add_issue("RELATION_UNKNOWN_SUBJECT", subject_id)
            object_reference = str(item.get("object_reference", ""))
            if object_reference and object_reference not in mention_ids:
                add_issue(
                    "RELATION_UNRESOLVED_OBJECT",
                    subject_id,
                    "WARNING",
                )
            if item.get("explicit_or_inferred") == "INFERRED":
                add_issue(
                    "INFERRED_RELATION_REQUIRES_REVIEW",
                    subject_id,
                    "WARNING",
                )
        elif collection == "isnads":
            positions = [
                int(narrator.get("position", -1))
                for narrator in item.get("ordered_narrators", [])
            ]
            if positions != list(range(len(positions))):
                add_issue("ISNAD_ORDER_INVALID", subject_id)
            if any(
                str(narrator.get("mention_id", "")) not in mention_ids
                for narrator in item.get("ordered_narrators", [])
            ):
                add_issue("ISNAD_UNKNOWN_NARRATOR", subject_id)
        elif collection == "temporals":
            if (
                item.get("relative_reference")
                and item.get("precision") not in {
                    "RELATIVE",
                    "APPROXIMATE",
                    "UNRESOLVED",
                }
            ):
                add_issue("RELATIVE_DATE_OVERRESOLVED", subject_id)

    evidence_ranges.sort()
    entity_ranges = [
        (item.get("start"), item.get("end"), str(item.get("mention_id", "")))
        for item in outputs.get("mentions", {}).get("entities", [])
        if isinstance(item, dict)
    ]
    seen_entity_ranges: set[tuple[int, int]] = set()
    for start, end, subject_id in entity_ranges:
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if (start, end) in seen_entity_ranges:
            add_issue("DUPLICATE_ENTITY_SPAN", subject_id)
        seen_entity_ranges.add((start, end))
    for index, left in enumerate(evidence_ranges):
        for right in evidence_ranges[index + 1 :]:
            if right[0] >= left[1]:
                break
            nested = (
                left[0] <= right[0] and right[1] <= left[1]
            ) or (
                right[0] <= left[0] and left[1] <= right[1]
            )
            if nested and not (left[3] or right[3]):
                add_issue(
                    "NESTED_EVIDENCE_WITHOUT_RATIONALE",
                    f"{left[2]}|{right[2]}",
                    "WARNING",
                )

    structure = outputs.get("structure", {}).get("structure", {})
    heading_ranges = structure.get("heading_ranges", [])
    for heading in heading_ranges:
        parsed_heading, error = _span(heading, original_text)
        if error or parsed_heading is None:
            add_issue("STRUCTURAL_HEADING_RANGE_INVALID", "structure")
            continue
        for start, end, subject_id, rationale in evidence_ranges:
            if (
                start >= parsed_heading["start"]
                and end <= parsed_heading["end"]
                and "HEADING_AS_CONTEXT" not in rationale
            ):
                add_issue(
                    "HEADING_USED_AS_INDEPENDENT_EVIDENCE",
                    subject_id,
                )

    ordered = sorted(
        issues,
        key=lambda item: (
            item["severity"],
            item["code"],
            item["subject_id"],
        ),
    )
    error_count = sum(
        item["severity"] in {"ERROR", "CRITICAL"}
        for item in ordered
    )
    return {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "status": "VALID" if error_count == 0 else "INVALID",
        "issue_count": len(ordered),
        "error_count": error_count,
        "warning_count": len(ordered) - error_count,
        "issues": ordered,
        "validated_item_count": len(seen_ids),
        "source_id": source_id,
        "locator": locator,
    }


__all__ = ["canonicalize_literal_spans", "validate_semantic_outputs"]
