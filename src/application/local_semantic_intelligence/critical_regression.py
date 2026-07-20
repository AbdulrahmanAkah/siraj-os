"""Bounded, evidence-first execution for four semantic regression cases."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path
from time import perf_counter_ns
from typing import Any, Callable

from src.application.operations_common import CANONICAL_TIMESTAMP, integrity_hash

from .evidence_resolution import resolve_evidence_span
from .foundation import _read_json
from .models import SemanticProviderError
from .orchestrator import atomic_write_json, atomic_write_text
from .pilot_evaluation import pilot_root
from .provider import SemanticExtractionProvider


CRITICAL_SCHEMA_VERSION = "siraj-semantic-critical-regression-v2"
CRITICAL_SAMPLE = "critical-4"
ROUTES = ("PERSON_AND_STATUS", "APPOINTMENT_AND_OFFICE", "ISNAD", "SIRA_POETRY")
_CASE_BY_SEGMENT = {
    3: ("ENTITY_AND_NAME_BOUNDARIES", "PERSON_AND_STATUS"),
    17: ("APPOINTMENT_OFFICE_AND_JURISDICTION", "APPOINTMENT_AND_OFFICE"),
    8: ("ISNAD_AND_NARRATOR_STATE", "ISNAD"),
    15: ("SIRA_OR_POETRY_WITH_HISTORICAL_CONTENT", "SIRA_POETRY"),
}
_COLLECTIONS = {
    "PERSON_AND_STATUS": (("entities", "entity"), ("statuses", "status"), ("relations", "relation")),
    "APPOINTMENT_AND_OFFICE": (("entities", "entity"), ("appointments", "appointment")),
    "ISNAD": (("entities", "entity"), ("isnads", "isnad")),
    "SIRA_POETRY": (("entities", "entity"), ("events", "event")),
}
_REPAIRABLE = {
    "EVIDENCE_TEXT_NOT_VERBATIM", "EVIDENCE_AMBIGUOUS", "ENTITY_EVIDENCE_TOO_NARROW",
    "RELATION_EVIDENCE_INSUFFICIENT", "CROSS_REFERENCE_MISMATCH",
}


class CriticalRegressionError(ValueError):
    """The bounded Critical-4 lifecycle cannot proceed safely."""


class CriticalEvidenceValidationError(CriticalRegressionError):
    """A route output failed strict item-level evidence validation."""


def critical_root(semantic_root: str | Path) -> Path:
    return pilot_root(semantic_root) / CRITICAL_SAMPLE


def _case(annotation: dict[str, Any], run_items: dict[str, dict[str, Any]]) -> dict[str, Any]:
    failure_type, route = _CASE_BY_SEGMENT[int(annotation["segment_id"])]
    audit_id = str(annotation["audit_segment_id"])
    return {
        "case_id": f"critical-{int(annotation['segment_id']):02d}",
        "audit_segment_id": audit_id,
        "segment_id": int(annotation["segment_id"]),
        "source_id": str(annotation["source_id"]),
        "locator": str(annotation["locator"]),
        "book_title": str(annotation["book_title"]),
        "original_text": str(annotation["original_text"]),
        "failure_type": failure_type,
        "route": route,
        "human_notes": str(annotation.get("prior_diagnostic_reviewer_notes", "")),
        "old_model_reference": run_items.get(audit_id, {}),
        "input_hash": integrity_hash({"audit_segment_id": audit_id, "original_text": annotation["original_text"], "route": route}),
    }


def prepare_critical_4(semantic_root: str | Path) -> dict[str, Any]:
    root = critical_root(semantic_root)
    pilot = pilot_root(semantic_root)
    adjudication = _read_json(pilot / "pilot-12-human-adjudication.json")
    run_manifest = _read_json(pilot / "pilot-12-run-manifest.json")
    reports = {
        name: _read_json(pilot / name)
        for name in (
            "pilot-12-quick-review-summary.json", "pilot-12-validation-report.json",
            "pilot-12-reconciliation-report.json", "pilot-12-learning-report.json",
        )
    }
    run_items = {str(item.get("audit_segment_id", "")): item for item in run_manifest.get("segments", []) if isinstance(item, dict)}
    annotations = [item for item in adjudication.get("annotations", []) if int(item.get("segment_id", -1)) in _CASE_BY_SEGMENT]
    if len(annotations) != len(_CASE_BY_SEGMENT):
        raise CriticalRegressionError("CRITICAL_4_SOURCE_SEGMENTS_MISSING")
    cases = sorted((_case(item, run_items) for item in annotations), key=lambda item: item["case_id"])
    manifest = {
        "schema_version": CRITICAL_SCHEMA_VERSION, "sample": CRITICAL_SAMPLE,
        "status": "PREPARED_PENDING_MANUAL_RUN", "created_at": CANONICAL_TIMESTAMP,
        "concurrency": 1, "no_parallel_requests": True, "automatic_critic": False,
        "maximum_calls_per_case": 2,
        "input_report_hashes": {name: integrity_hash(value) for name, value in sorted(reports.items())},
        "cases": cases,
    }
    atomic_write_json(root / "critical-4-manifest.json", manifest)
    atomic_write_text(root / "critical-4-diagnosis.md", "# Critical-4 diagnosis\n\nEvidence is accepted only after literal deterministic resolution and route validation.\n")
    pending = {
        "schema_version": CRITICAL_SCHEMA_VERSION, "sample": CRITICAL_SAMPLE,
        "status": "PENDING_MANUAL_RUN", "quality_claim": "NONE_UNTIL_MANUAL_RUN_AND_REVIEW",
        "cases": [{"case_id": case["case_id"], "route": case["route"], "baseline": "AVAILABLE_AT_MANUAL_RUN", "old_model_output": case["old_model_reference"], "new_route_output": "PENDING_MANUAL_RUN", "human_notes": case["human_notes"]} for case in cases],
    }
    atomic_write_json(root / "critical-4-comparison.json", pending)
    atomic_write_text(root / "critical-4-comparison.md", "# Critical-4 comparison\n\nStatus: `PENDING_MANUAL_RUN`\n")
    return manifest


def _anchors(kind: str, item: dict[str, Any]) -> list[str]:
    fields = {
        "entity": ("surface",), "status": ("person", "status"), "relation": ("subject", "object"),
        "appointment": ("appointee", "appointing_authority", "office", "jurisdiction"), "isnad": ("narrators",), "event": (),
    }[kind]
    result: list[str] = []
    for field in fields:
        value = item.get(field, "")
        if isinstance(value, str) and value:
            result.append(value)
        elif isinstance(value, list):
            result.extend(str(entry) for entry in value if entry)
    return result


def _resolved_reference(
    value: Any,
    entity_surfaces: dict[str, str],
) -> str:
    """Resolve an entity ID to its literal source surface."""
    candidate = str(value or "")
    return entity_surfaces.get(candidate, candidate)


def _semantic_reason(
    text: str,
    kind: str,
    item: dict[str, Any],
    entity_surfaces: dict[str, str] | None = None,
) -> str:
    entity_surfaces = entity_surfaces or {}
    quote = str(item.get("evidence", {}).get("text", ""))

    if kind == "entity":
        surface = str(item.get("surface", ""))

        if not surface or surface not in text:
            return "CROSS_REFERENCE_MISMATCH"

        # A literal quote may safely be wider than the entity surface.
        if surface not in quote:
            return "ENTITY_EVIDENCE_TOO_NARROW"

        if (
            item.get("name_boundary_complete") is False
            and any(token in surface for token in (" بن ", " ابن ", " أبي "))
        ):
            return "ROUTE_SEMANTIC_VALIDATION_FAILURE"

        if (
            surface in {"قال", "تعالى", "الله", "رب"}
            and not item.get("explicit_proper_name", False)
        ):
            return "ROUTE_SEMANTIC_VALIDATION_FAILURE"

    elif kind == "status":
        person = _resolved_reference(
            item.get("person"),
            entity_surfaces,
        )
        status = str(item.get("status", ""))

        if person and person not in text:
            return "CROSS_REFERENCE_MISMATCH"

        if status and status not in text and status not in quote:
            return "CROSS_REFERENCE_MISMATCH"

        if person and person not in quote:
            return "RELATION_EVIDENCE_INSUFFICIENT"

    elif kind == "relation":
        subject = _resolved_reference(
            item.get("subject"),
            entity_surfaces,
        )
        object_value = _resolved_reference(
            item.get("object"),
            entity_surfaces,
        )

        if subject and subject not in text:
            return "CROSS_REFERENCE_MISMATCH"

        if object_value and object_value not in text:
            return "CROSS_REFERENCE_MISMATCH"

        if subject and subject not in quote:
            return "RELATION_EVIDENCE_INSUFFICIENT"

        if object_value and object_value not in quote:
            return "RELATION_EVIDENCE_INSUFFICIENT"

    elif kind == "appointment":
        appointee = _resolved_reference(
            item.get("appointee"),
            entity_surfaces,
        )
        authority = _resolved_reference(
            item.get("appointing_authority"),
            entity_surfaces,
        )
        office = str(item.get("office", ""))
        jurisdiction = str(item.get("jurisdiction", ""))

        if any(
            value and value not in text
            for value in (
                appointee,
                authority,
                office,
                jurisdiction,
            )
        ):
            return "CROSS_REFERENCE_MISMATCH"

        if (
            jurisdiction
            and jurisdiction == str(item.get("generic_object", ""))
        ):
            return "ROUTE_SEMANTIC_VALIDATION_FAILURE"

    elif kind == "isnad":
        narrators = item.get("narrators", [])

        if not isinstance(narrators, list):
            return "ROUTE_SEMANTIC_VALIDATION_FAILURE"

        resolved_narrators = [
            _resolved_reference(value, entity_surfaces)
            for value in narrators
            if str(value or "")
        ]

        if any(value not in text for value in resolved_narrators):
            return "CROSS_REFERENCE_MISMATCH"

        if any(value not in quote for value in resolved_narrators):
            return "RELATION_EVIDENCE_INSUFFICIENT"

    elif kind == "event":
        if not quote:
            return "ROUTE_SEMANTIC_VALIDATION_FAILURE"

    return ""



_STATUS_COREFERENCE_VERBS = (
    "\u0648\u0635\u0641\u0647",
    "\u0630\u0643\u0631\u0647",
    "\u0639\u062f\u0647",
    "\u0627\u062a\u0647\u0645\u0647",
    "\u0636\u0639\u0641\u0647",
    "\u0648\u062b\u0642\u0647",
    "\u0643\u0630\u0628\u0647",
    "\u0645\u062f\u062d\u0647",
    "\u0630\u0645\u0647",
)

_STATUS_EVIDENCE_ALIASES = {
    "\u0645\u062f\u0644\u0633": (
        "\u0627\u0644\u062a\u062f\u0644\u064a\u0633",
        "\u0628\u0627\u0644\u062a\u062f\u0644\u064a\u0633",
    ),
    "\u0643\u0630\u0627\u0628": (
        "\u0627\u0644\u0643\u0630\u0628",
        "\u0628\u0627\u0644\u0643\u0630\u0628",
    ),
    "\u0636\u0639\u064a\u0641": (
        "\u0627\u0644\u0636\u0639\u0641",
        "\u0628\u0627\u0644\u0636\u0639\u0641",
    ),
}


def _deterministic_status_coreference(
    text: str,
    item: dict[str, Any],
    entity_surfaces: dict[str, str],
    accepted_entities: list[dict[str, Any]],
) -> dict[str, Any] | None:
    evidence = item.get("evidence", {})

    if not isinstance(evidence, dict):
        return None

    quote = str(evidence.get("text", ""))
    start = evidence.get("start")
    end = evidence.get("end")

    if (
        not quote
        or not isinstance(start, int)
        or not isinstance(end, int)
        or text[start:end] != quote
    ):
        return None

    raw_person = str(item.get("person", ""))
    person = _resolved_reference(
        raw_person,
        entity_surfaces,
    )
    status = str(item.get("status", "")).strip()

    if not person or not status:
        return None

    # This contract is only for an antecedent represented by a pronoun.
    if person in quote:
        return None

    matched_verb = next(
        (
            verb
            for verb in _STATUS_COREFERENCE_VERBS
            if verb in quote
        ),
        "",
    )

    if not matched_verb:
        return None

    aliases = _STATUS_EVIDENCE_ALIASES.get(status, ())

    matched_status_evidence = next(
        (
            alias
            for alias in aliases
            if alias in quote
        ),
        "",
    )

    if not matched_status_evidence:
        return None

    person_entities: list[dict[str, Any]] = []

    for entity in accepted_entities:
        if not isinstance(entity, dict):
            continue

        types = entity.get("types", [])

        if (
            not isinstance(types, list)
            or "person" not in {
                str(value).lower()
                for value in types
            }
        ):
            continue

        entity_evidence = entity.get("evidence", {})

        if not isinstance(entity_evidence, dict):
            continue

        entity_start = entity_evidence.get("start")
        entity_end = entity_evidence.get("end")
        surface = str(entity.get("surface", ""))

        if (
            not surface
            or not isinstance(entity_start, int)
            or not isinstance(entity_end, int)
        ):
            continue

        person_entities.append({
            "id": str(entity.get("id", "")),
            "surface": surface,
            "start": entity_start,
            "end": entity_end,
        })

    antecedent_candidates = [
        entity
        for entity in person_entities
        if entity["surface"] == person
        and entity["end"] <= start
    ]

    if not antecedent_candidates:
        return None

    target = max(
        antecedent_candidates,
        key=lambda entity: (
            entity["end"],
            entity["start"],
        ),
    )

    preceding_people = [
        entity
        for entity in person_entities
        if entity["end"] <= start
    ]

    if not preceding_people:
        return None

    nearest_end = max(
        entity["end"]
        for entity in preceding_people
    )

    nearest_people = [
        entity
        for entity in preceding_people
        if entity["end"] == nearest_end
    ]

    # Reject ambiguity: the referenced person must be the single nearest
    # explicit person mention preceding the evidence.
    if (
        len(nearest_people) != 1
        or nearest_people[0]["surface"] != person
    ):
        return None

    explicit_people_in_quote = [
        entity
        for entity in person_entities
        if (
            entity["start"] >= start
            and entity["end"] <= end
            and entity["surface"] in quote
            and entity["surface"] != person
        )
    ]

    unique_quote_people = {
        (
            entity["surface"],
            entity["start"],
            entity["end"],
        )
        for entity in explicit_people_in_quote
    }

    # The clause must contain exactly one explicit critic/speaker.
    if len(unique_quote_people) != 1:
        return None

    critic_surface, critic_start, critic_end = next(
        iter(unique_quote_people)
    )

    return {
        "resolution": (
            "DETERMINISTIC_LOCAL_COREFERENCE_RESOLVED"
        ),
        "antecedent": {
            "id": target["id"],
            "surface": target["surface"],
            "start": target["start"],
            "end": target["end"],
        },
        "explicit_clause_person": {
            "surface": critic_surface,
            "start": critic_start,
            "end": critic_end,
        },
        "matched_pronominal_verb": matched_verb,
        "status": status,
        "matched_status_evidence": (
            matched_status_evidence
        ),
        "evidence_start": start,
        "evidence_end": end,
    }




def _deterministic_predicative_status_coreference(
    text: str,
    item: dict[str, Any],
    entity_surfaces: dict[str, str],
    accepted_entities: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Resolve bounded local forms such as:

        PERSON وقال هو STATUS
        PERSON وقال إنه STATUS
        PERSON ثم قال هو STATUS
        PERSON ثم قال إنه STATUS

    The antecedent must be the unique nearest preceding person.
    """
    import re

    evidence = item.get("evidence", {})

    if not isinstance(evidence, dict):
        return None

    quote = str(evidence.get("text", ""))
    quote_start = evidence.get("start")
    quote_end = evidence.get("end")

    if (
        not quote
        or not isinstance(quote_start, int)
        or not isinstance(quote_end, int)
        or text[quote_start:quote_end] != quote
    ):
        return None

    person = _resolved_reference(
        item.get("person"),
        entity_surfaces,
    ).strip()

    status = str(
        item.get("status", "")
    ).strip()

    if (
        not person
        or not status
        or person in quote
    ):
        return None

    normalized = " ".join(quote.split())

    pattern = re.compile(
        r"^(?:و|ثم\s+)?قال\s+"
        r"(هو|إنه|انه)\s+"
        + re.escape(status)
        + r"(?:$|[\s،؛,.])"
    )

    match = pattern.search(normalized)

    if match is None:
        return None

    candidates = []

    for entity in accepted_entities:
        if not isinstance(entity, dict):
            continue

        if "person" not in {
            str(value)
            for value in entity.get("types", [])
        }:
            continue

        entity_evidence = entity.get("evidence", {})

        if not isinstance(entity_evidence, dict):
            continue

        surface = str(
            entity.get("surface", "")
        ).strip()

        start = entity_evidence.get("start")
        end = entity_evidence.get("end")

        if (
            not surface
            or not isinstance(start, int)
            or not isinstance(end, int)
            or end > quote_start
        ):
            continue

        candidates.append(
            {
                "id": str(entity.get("id", "")),
                "surface": surface,
                "start": start,
                "end": end,
            }
        )

    if not candidates:
        return None

    nearest_end = max(
        candidate["end"]
        for candidate in candidates
    )

    nearest = [
        candidate
        for candidate in candidates
        if candidate["end"] == nearest_end
    ]

    if len(nearest) != 1:
        return None

    antecedent = nearest[0]

    if antecedent["surface"] != person:
        return None

    gap = text[
        antecedent["end"]:quote_start
    ]

    if not re.fullmatch(
        r"[\s،؛,:.\-]*",
        gap,
    ):
        return None

    expanded_start = antecedent["start"]
    expanded_end = quote_end
    expanded_text = text[
        expanded_start:expanded_end
    ]

    item["evidence"] = {
        "start": expanded_start,
        "end": expanded_end,
        "text": expanded_text,
    }

    return {
        "resolution": (
            "DETERMINISTIC_PREDICATIVE_"
            "COREFERENCE_RESOLVED"
        ),
        "antecedent": antecedent,
        "matched_pronoun": match.group(1),
        "status": status,
        "expanded_evidence_text": expanded_text,
        "expanded_evidence_start": expanded_start,
        "expanded_evidence_end": expanded_end,
    }


def _resolve_status_coreference(
    text: str,
    item: dict[str, Any],
    entity_surfaces: dict[str, str],
    accepted_entities: list[dict[str, Any]],
) -> dict[str, Any] | None:
    result = _deterministic_status_coreference(
        text,
        item,
        entity_surfaces,
        accepted_entities,
    )

    if result is not None:
        return result

    return _deterministic_predicative_status_coreference(
        text,
        item,
        entity_surfaces,
        accepted_entities,
    )


def _deterministic_relation_object_coreference(
    text: str,
    item: dict[str, Any],
    entity_surfaces: dict[str, str],
    accepted_entities: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Resolve a relation object expressed by a local attached pronoun.

    The resolution is accepted only when:
    - the subject is explicit inside the evidence quote;
    - the object surface is absent from the quote;
    - the quote contains an approved pronominal verb;
    - the target object is the single nearest preceding person entity;
    - no different explicit person inside the quote can be the object.
    """

    evidence = item.get("evidence", {})

    if not isinstance(evidence, dict):
        return None

    quote = str(evidence.get("text", ""))
    quote_start = evidence.get("start")
    quote_end = evidence.get("end")

    if (
        not quote
        or not isinstance(quote_start, int)
        or not isinstance(quote_end, int)
        or quote_start < 0
        or quote_end < quote_start
        or text[quote_start:quote_end] != quote
    ):
        return None

    subject = _resolved_reference(
        item.get("subject"),
        entity_surfaces,
    )
    object_value = _resolved_reference(
        item.get("object"),
        entity_surfaces,
    )

    if (
        not subject
        or not object_value
        or subject not in quote
        or object_value in quote
    ):
        return None

    matched_verb = next(
        (
            verb
            for verb in _STATUS_COREFERENCE_VERBS
            if verb in quote
        ),
        None,
    )

    if matched_verb is None:
        return None

    people: list[dict[str, Any]] = []

    for entity in accepted_entities:
        if not isinstance(entity, dict):
            continue

        types = entity.get("types", [])

        if (
            not isinstance(types, list)
            or "person" not in {
                str(value)
                for value in types
            }
        ):
            continue

        surface = str(entity.get("surface", ""))
        span = entity.get("evidence", {})

        if (
            not surface
            or not isinstance(span, dict)
            or not isinstance(span.get("start"), int)
            or not isinstance(span.get("end"), int)
        ):
            continue

        people.append({
            "id": str(entity.get("id", "")),
            "surface": surface,
            "start": int(span["start"]),
            "end": int(span["end"]),
        })

    target_mentions = [
        person
        for person in people
        if person["surface"] == object_value
        and person["end"] <= quote_start
    ]

    if not target_mentions:
        return None

    preceding_people = [
        person
        for person in people
        if person["end"] <= quote_start
    ]

    if not preceding_people:
        return None

    nearest_end = max(
        person["end"]
        for person in preceding_people
    )

    nearest_people = [
        person
        for person in preceding_people
        if person["end"] == nearest_end
    ]

    if (
        len(nearest_people) != 1
        or nearest_people[0]["surface"] != object_value
    ):
        return None

    explicit_people_in_quote = [
        person
        for person in people
        if (
            quote_start <= person["start"]
            and person["end"] <= quote_end
        )
    ]

    explicit_surfaces = {
        person["surface"]
        for person in explicit_people_in_quote
    }

    if explicit_surfaces != {subject}:
        return None

    target = nearest_people[0]

    return {
        "resolution": (
            "DETERMINISTIC_LOCAL_RELATION_COREFERENCE_RESOLVED"
        ),
        "subject": subject,
        "object": object_value,
        "matched_verb": matched_verb,
        "target_entity_id": target["id"],
        "target_start": target["start"],
        "target_end": target["end"],
        "evidence_start": quote_start,
        "evidence_end": quote_end,
    }


def resolve_route_evidence(case: dict[str, Any], output: dict[str, Any], attempt: int) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Resolve every provider quote and reject only unsupported individual items."""
    text = str(case["original_text"])
    resolved = {key: deepcopy(value) for key, value in output.items() if key not in {"raw_provider_response", "provider_metadata"}}
    accepted: Counter[str] = Counter()
    rejected: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    entity_spans: set[tuple[int, int]] = set()
    entity_surfaces = {
        str(entity.get("id", "")): str(entity.get("surface", ""))
        for entity in output.get("entities", [])
        if isinstance(entity, dict)
        and str(entity.get("id", ""))
        and str(entity.get("surface", ""))
    }

    for collection, kind in _COLLECTIONS[case["route"]]:
        values = resolved.get(collection, [])
        if not isinstance(values, list):
            rejected.append({"collection": collection, "reason_code": "ROUTE_SEMANTIC_VALIDATION_FAILURE"})
            resolved[collection] = []
            continue
        kept: list[dict[str, Any]] = []
        for index, item in enumerate(values):
            if not isinstance(item, dict):
                rejected.append({"collection": collection, "item_index": index, "reason_code": "ROUTE_SEMANTIC_VALIDATION_FAILURE"})
                continue
            proposed = item.get("evidence", {}) if isinstance(item.get("evidence"), dict) else {}
            span = resolve_evidence_span(text, str(proposed.get("text", "")), proposed.get("start"), proposed.get("end"), _anchors(kind, item))
            record = {
                "case_id": case["case_id"], "route": case["route"], "attempt": attempt,
                "collection": collection, "item_kind": kind, "item_index": index,
                "evidence_object": proposed, "evidence_text": proposed.get("text", ""),
                "model_start": proposed.get("start"), "model_end": proposed.get("end"),
                "source_slice": span.source_slice, "literal_occurrences": list(span.occurrences),
                "resolution": span.status, "reason_code": span.reason_code,
            }
            if span.status == "REJECTED":
                rejected.append(record)
                diagnostics.append(record)
                continue
            item["evidence"] = {"start": span.start, "end": span.end, "text": span.text}
            reason = _semantic_reason(
                text,
                kind,
                item,
                entity_surfaces,
            )
            record["validator"] = (
                "critical_regression._semantic_reason"
            )
            record["semantic_reason"] = reason
            record["reason_code"] = reason

            coreference = None

            if (
                kind == "status"
                and reason
                in {
                    "CROSS_REFERENCE_MISMATCH",
                    "RELATION_EVIDENCE_INSUFFICIENT",
                }
            ):
                coreference = (
                    _resolve_status_coreference(

                        text,
                        item,
                        entity_surfaces,
                        resolved.get("entities", []),
                    )
                )

                if coreference is not None:
                    original_semantic_reason = reason
                    reason = ""
                    record["semantic_reason"] = ""
                    record["reason_code"] = ""
                    record["original_semantic_reason"] = (
                        original_semantic_reason
                    )
                    record["resolution"] = coreference[
                        "resolution"
                    ]
                    record["coreference"] = coreference
                    record["validator"] = (
                        "critical_regression."
                        "_deterministic_status_coreference"
                    )

            elif (
                kind == "relation"
                and reason
                in {
                    "CROSS_REFERENCE_MISMATCH",
                    "RELATION_EVIDENCE_INSUFFICIENT",
                }
            ):
                coreference = (
                    _deterministic_relation_object_coreference(
                        text,
                        item,
                        entity_surfaces,
                        resolved.get("entities", []),
                    )
                )

                if coreference is not None:
                    original_semantic_reason = reason
                    reason = ""
                    record["semantic_reason"] = ""
                    record["reason_code"] = ""
                    record["original_semantic_reason"] = (
                        original_semantic_reason
                    )
                    record["resolution"] = coreference[
                        "resolution"
                    ]
                    record["coreference"] = coreference
                    record["validator"] = (
                        "critical_regression."
                        "_deterministic_relation_object_coreference"
                    )

            diagnostics.append(record)

            if reason:
                rejected.append({
                    **record,
                    "reason_code": reason,
                })
                continue
            if kind == "entity":
                span_key = (int(span.start or -1), int(span.end or -1))
                if span_key in entity_spans:
                    rejected.append({**record, "reason_code": "DUPLICATE_ENTITY_EXACT_SPAN"})
                    continue
                entity_spans.add(span_key)
            kept.append(item)
            accepted[collection] += 1
        resolved[collection] = kept
    # Resolve an ambiguous entity occurrence only when a validated
    # referencing item identifies exactly one occurrence inside its own
    # literal evidence span. This preserves strict literal evidence while
    # preventing valid entity references from becoming dangling after
    # item-level filtering.
    ambiguous_entity_rejections = [
        rejection
        for rejection in rejected
        if rejection.get("collection") == "entities"
        and rejection.get("reason_code") == "EVIDENCE_AMBIGUOUS"
    ]

    restored_rejection_ids: set[int] = set()
    existing_entity_spans = {
        (
            entity.get("evidence", {}).get("start"),
            entity.get("evidence", {}).get("end"),
            entity.get("surface", ""),
        )
        for entity in resolved.get("entities", [])
        if isinstance(entity, dict)
        and isinstance(entity.get("evidence"), dict)
    }

    for rejection in ambiguous_entity_rejections:
        item_index = rejection.get("item_index")

        if not isinstance(item_index, int):
            continue

        source_entities = output.get("entities", [])

        if (
            not isinstance(source_entities, list)
            or not 0 <= item_index < len(source_entities)
            or not isinstance(source_entities[item_index], dict)
        ):
            continue

        entity = deepcopy(source_entities[item_index])
        entity_id = str(entity.get("id", ""))
        entity_surface = str(entity.get("surface", "")).strip()
        evidence = (
            entity.get("evidence", {})
            if isinstance(entity.get("evidence"), dict)
            else {}
        )
        evidence_text = str(evidence.get("text", ""))

        if not entity_id or not evidence_text:
            continue

        reference_spans: list[tuple[int, int]] = []

        for status in resolved.get("statuses", []):
            if (
                isinstance(status, dict)
                and str(status.get("person", "")) == entity_id
            ):
                span = status.get("evidence", {})
                if (
                    isinstance(span, dict)
                    and isinstance(span.get("start"), int)
                    and isinstance(span.get("end"), int)
                ):
                    reference_spans.append(
                        (span["start"], span["end"])
                    )

        for relation in resolved.get("relations", []):
            if (
                isinstance(relation, dict)
                and entity_id
                in {
                    str(relation.get("subject", "")),
                    str(relation.get("object", "")),
                }
            ):
                span = relation.get("evidence", {})
                if (
                    isinstance(span, dict)
                    and isinstance(span.get("start"), int)
                    and isinstance(span.get("end"), int)
                ):
                    reference_spans.append(
                        (span["start"], span["end"])
                    )

        for appointment in resolved.get("appointments", []):
            if (
                isinstance(appointment, dict)
                and entity_id
                in {
                    str(appointment.get("appointee", "")),
                    str(
                        appointment.get(
                            "appointing_authority",
                            "",
                        )
                    ),
                }
            ):
                span = appointment.get("evidence", {})
                if (
                    isinstance(span, dict)
                    and isinstance(span.get("start"), int)
                    and isinstance(span.get("end"), int)
                ):
                    reference_spans.append(
                        (span["start"], span["end"])
                    )

        for isnad in resolved.get("isnads", []):
            narrators = (
                isnad.get("narrators", [])
                if isinstance(isnad, dict)
                else []
            )

            narrator_values = (
                {
                    str(narrator).strip()
                    for narrator in narrators
                }
                if isinstance(narrators, list)
                else set()
            )

            if (
                entity_id in narrator_values
                or (
                    entity_surface
                    and entity_surface in narrator_values
                )
            ):
                span = isnad.get("evidence", {})
                if (
                    isinstance(span, dict)
                    and isinstance(span.get("start"), int)
                    and isinstance(span.get("end"), int)
                ):
                    reference_spans.append(
                        (span["start"], span["end"])
                    )

        occurrences = [
            occurrence
            for occurrence in rejection.get(
                "literal_occurrences",
                [],
            )
            if isinstance(occurrence, int)
        ]

        contextual_occurrences = sorted({
            occurrence
            for occurrence in occurrences
            if any(
                span_start <= occurrence
                and occurrence + len(evidence_text) <= span_end
                for span_start, span_end in reference_spans
            )
        })

        if len(contextual_occurrences) != 1:
            continue

        start = contextual_occurrences[0]
        end = start + len(evidence_text)

        if case["original_text"][start:end] != evidence_text:
            continue

        span_key = (
            start,
            end,
            str(entity.get("surface", "")),
        )

        if span_key in existing_entity_spans:
            continue

        entity["evidence"] = {
            "start": start,
            "end": end,
            "text": evidence_text,
        }

        resolved.setdefault("entities", []).append(entity)
        existing_entity_spans.add(span_key)
        accepted["entities"] += 1
        restored_rejection_ids.add(id(rejection))

        diagnostics.append({
            **rejection,
            "resolution": "CONTEXTUAL_REFERENCE_DISAMBIGUATED",
            "reason_code": "",
            "resolved_start": start,
            "resolved_end": end,
            "reference_spans": [
                {
                    "start": span_start,
                    "end": span_end,
                }
                for span_start, span_end in reference_spans
            ],
            "validator": (
                "critical_regression."
                "contextual_reference_disambiguation"
            ),
        })

    if restored_rejection_ids:
        rejected = [
            rejection
            for rejection in rejected
            if id(rejection) not in restored_rejection_ids
        ]

        resolved["entities"].sort(
            key=lambda entity: (
                entity.get("evidence", {}).get(
                    "start",
                    len(text),
                ),
                entity.get("evidence", {}).get(
                    "end",
                    len(text),
                ),
            )
        )

    # Enforce referential integrity after every filtering and recovery step.
    # A reference is considered an entity reference only when it existed as
    # an entity ID in the provider response; ordinary literal names remain
    # valid route values.
    accepted_entity_ids = {
        str(entity.get("id", ""))
        for entity in resolved.get("entities", [])
        if isinstance(entity, dict)
        and str(entity.get("id", ""))
    }
    provider_entity_ids = set(entity_surfaces)

    reference_specs = {
        "statuses": ("person",),
        "relations": ("subject", "object"),
        "appointments": (
            "appointee",
            "appointing_authority",
        ),
    }

    for collection, fields in reference_specs.items():
        values = resolved.get(collection, [])

        if not isinstance(values, list):
            continue

        kept_values: list[dict[str, Any]] = []

        for index, item in enumerate(values):
            if not isinstance(item, dict):
                continue

            references = [
                str(item.get(field, ""))
                for field in fields
                if str(item.get(field, ""))
                in provider_entity_ids
            ]
            dangling = sorted({
                reference
                for reference in references
                if reference not in accepted_entity_ids
            })

            if dangling:
                record = {
                    "case_id": case["case_id"],
                    "route": case["route"],
                    "attempt": attempt,
                    "collection": collection,
                    "item_index": index,
                    "reason_code": (
                        "DANGLING_ENTITY_REFERENCE"
                    ),
                    "dangling_entity_ids": dangling,
                    "validator": (
                        "critical_regression."
                        "post_filter_reference_integrity"
                    ),
                }
                rejected.append(record)
                diagnostics.append(record)
                continue

            kept_values.append(item)

        resolved[collection] = kept_values
        accepted[collection] = len(kept_values)

    isnads = resolved.get("isnads", [])

    if isinstance(isnads, list):
        kept_isnads: list[dict[str, Any]] = []

        for index, isnad in enumerate(isnads):
            if not isinstance(isnad, dict):
                continue

            narrators = isnad.get("narrators", [])
            references = (
                [
                    str(narrator)
                    for narrator in narrators
                    if str(narrator) in provider_entity_ids
                ]
                if isinstance(narrators, list)
                else []
            )
            dangling = sorted({
                reference
                for reference in references
                if reference not in accepted_entity_ids
            })

            if dangling:
                record = {
                    "case_id": case["case_id"],
                    "route": case["route"],
                    "attempt": attempt,
                    "collection": "isnads",
                    "item_index": index,
                    "reason_code": (
                        "DANGLING_ENTITY_REFERENCE"
                    ),
                    "dangling_entity_ids": dangling,
                    "validator": (
                        "critical_regression."
                        "post_filter_reference_integrity"
                    ),
                }
                rejected.append(record)
                diagnostics.append(record)
                continue

            kept_isnads.append(isnad)

        resolved["isnads"] = kept_isnads
        accepted["isnads"] = len(kept_isnads)

    required = {"PERSON_AND_STATUS": "entities", "APPOINTMENT_AND_OFFICE": "appointments", "ISNAD": "isnads", "SIRA_POETRY": "entities"}[case["route"]]
    validation = {
        "route": case["route"], "accepted_items": sum(accepted.values()),
        "accepted_by_collection": dict(sorted(accepted.items())), "rejected_items": len(rejected),
        "rejections": rejected,
        "repaired_offsets_count": sum(
            item.get("resolution") == "OFFSET_REPAIRED_DETERMINISTICALLY"
            for item in diagnostics
        ),
        "ambiguous_evidence_rejections": sum(item.get("reason_code") == "EVIDENCE_AMBIGUOUS" for item in rejected),
        "non_verbatim_evidence_rejections": sum(item.get("reason_code") == "EVIDENCE_TEXT_NOT_VERBATIM" for item in rejected),
        "validation_hash": integrity_hash(resolved),
    }
    validation["case_status"] = "FAIL" if not resolved.get(required) else ("PARTIAL" if rejected else "PASS")
    return resolved, validation, diagnostics


def _validate_route_output(case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    resolved, validation, _ = resolve_route_evidence(case, output, 1)
    if validation["rejected_items"] or validation["case_status"] == "FAIL":
        reason = validation["rejections"][0]["reason_code"] if validation["rejections"] else "ROUTE_SEMANTIC_VALIDATION_FAILURE"
        raise CriticalEvidenceValidationError(reason)
    return {"status": "VALID", "accepted_entities": len(resolved.get("entities", [])), "route": case["route"], "validation_hash": validation["validation_hash"]}


def _validation_quality(
    validation: dict[str, Any],
) -> tuple[int, int, int]:
    """Prevent a lower-quality repair from replacing a better first result."""
    status_rank = {
        "FAIL": 0,
        "PARTIAL": 1,
        "PASS": 2,
    }.get(str(validation.get("case_status", "FAIL")), 0)

    return (
        status_rank,
        int(validation.get("accepted_items", 0)),
        -int(validation.get("rejected_items", 0)),
    )


def _repair_reason(validation: dict[str, Any]) -> dict[str, Any] | None:
    for item in validation["rejections"]:
        if item.get("reason_code") in _REPAIRABLE:
            return item
    return None


def run_critical_4(
    semantic_root: str | Path,
    provider: SemanticExtractionProvider,
    *, force: bool = False,
    failure_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    hardware = getattr(provider, "hardware", None) or getattr(getattr(provider, "config", None), "hardware", None)
    if hardware and hardware.concurrency != 1:
        raise CriticalRegressionError("CRITICAL_4_REQUIRES_CONCURRENCY_ONE")
    manifest = prepare_critical_4(semantic_root)
    root = critical_root(semantic_root)
    completed: list[dict[str, Any]] = []
    diagnostic_cases: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        case_root = root / case["case_id"]
        checkpoint = case_root / "checkpoint.json"
        if checkpoint.exists() and not force:
            completed.append(_read_json(checkpoint))
            continue
        request = {"source_id": case["source_id"], "locator": case["locator"], "original_text": case["original_text"], "route": case["route"], "case_id": case["case_id"], "repair": False, "record_failure": failure_callback}
        def checkpoint_before_retry(payload: dict[str, Any]) -> None:
            atomic_write_json(case_root / "retry-checkpoint.json", {"schema_version": CRITICAL_SCHEMA_VERSION, "case_id": case["case_id"], **payload})
        request["checkpoint_before_retry"] = checkpoint_before_retry
        started = perf_counter_ns()
        calls = 1
        repair_requests = 0
        output = provider.extract_critical_route(case["route"], request)
        resolved, validation, diagnostics = resolve_route_evidence(case, output, 1)
        diagnostic_cases.append({"case_id": case["case_id"], "route": case["route"], "source_text_hash": integrity_hash(case["original_text"]), "source_text_length": len(case["original_text"]), "attempt": 1, "raw_response_hash": output.get("provider_metadata", {}).get("raw_response_hash", ""), "parsed_response": resolved, "evidence": list(diagnostics)})
        repair = _repair_reason(validation)
        if repair is not None:
            initial_output = output
            initial_resolved = resolved
            initial_validation = validation

            calls += 1
            repair_requests = 1

            repair_request = {
                **request,
                "repair": True,
                "repair_reason": repair["reason_code"],
                "rejected_item": {
                    "collection": repair.get("collection"),
                    "item_kind": repair.get("item_kind"),
                    "evidence_text": repair.get("evidence_text", ""),
                },
                "accepted_output": initial_resolved,
            }

            retry_output = provider.extract_critical_route(
                case["route"],
                repair_request,
            )

            (
                retry_resolved,
                retry_validation,
                retry_diagnostics,
            ) = resolve_route_evidence(
                case,
                retry_output,
                2,
            )

            diagnostics.extend(retry_diagnostics)

            diagnostic_cases.append({
                "case_id": case["case_id"],
                "route": case["route"],
                "source_text_hash": integrity_hash(
                    case["original_text"]
                ),
                "source_text_length": len(
                    case["original_text"]
                ),
                "attempt": 2,
                "raw_response_hash": retry_output.get(
                    "provider_metadata",
                    {},
                ).get(
                    "raw_response_hash",
                    "",
                ),
                "parsed_response": retry_resolved,
                "evidence": retry_diagnostics,
            })

            if _validation_quality(
                retry_validation
            ) > _validation_quality(
                initial_validation
            ):
                output = retry_output
                resolved = retry_resolved
                validation = retry_validation
            else:
                output = initial_output
                resolved = initial_resolved
                validation = initial_validation

        result = {"schema_version": CRITICAL_SCHEMA_VERSION, "case_id": case["case_id"], "route": case["route"], "status": validation["case_status"], "calls": calls, "repair_requests_count": repair_requests, "duration_ns": perf_counter_ns() - started, "output": {**resolved, "provider_metadata": output.get("provider_metadata", {}), "raw_provider_response": output.get("raw_provider_response", {})}, "validation": validation}
        atomic_write_json(case_root / "checkpoint.json", result)
        completed.append(result)
    atomic_write_json(root / "gemini-critical-4-evidence-diagnostics.json", {"schema_version": CRITICAL_SCHEMA_VERSION, "provider_id": getattr(getattr(provider, "identity", None), "provider_id", "UNKNOWN"), "cases": diagnostic_cases})
    counts = Counter(item["status"] for item in completed)
    run = {"schema_version": CRITICAL_SCHEMA_VERSION, "sample": CRITICAL_SAMPLE, "status": "COMPLETED_PENDING_HUMAN_REVIEW" if not counts.get("FAIL") else "COMPLETED_WITH_CASE_FAILURES", "concurrency": 1, "no_parallel_requests": True, "explicit_unload_required": True, "cases": completed, "status_counts": dict(sorted(counts.items())), "total_calls": sum(int(item["calls"]) for item in completed)}
    atomic_write_json(root / "critical-4-run-manifest.json", run)
    return run


__all__ = ["CRITICAL_SAMPLE", "CRITICAL_SCHEMA_VERSION", "CriticalEvidenceValidationError", "CriticalRegressionError", "critical_root", "prepare_critical_4", "resolve_route_evidence", "run_critical_4"]
