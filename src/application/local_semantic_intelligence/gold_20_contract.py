"""Versioned contract for the SIRAJ Gold-20 Fast Track dataset."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

GOLD_SCHEMA_VERSION = "siraj-gold-semantic-v1"
EVALUATION_SCHEMA_VERSION = "siraj-semantic-evaluation-v1"
DATASET_ID = "gold-20-fast-track-v1"
DATASET_SIZE = 20

ROUTES = (
    "PERSON_AND_STATUS",
    "APPOINTMENT_AND_OFFICE",
    "ISNAD",
    "SIRA_POETRY",
)

ROUTE_QUOTAS = {
    "PERSON_AND_STATUS": 5,
    "APPOINTMENT_AND_OFFICE": 5,
    "ISNAD": 5,
    "SIRA_POETRY": 5,
}

DIFFICULTY_QUOTAS = {
    "DIRECT": 6,
    "COREFERENCE": 5,
    "AMBIGUOUS": 4,
    "MULTI_ITEM": 3,
    "ABSTENTION": 2,
}

REQUIRED_PROVENANCE_FIELDS = (
    "source_id",
    "book_id",
    "book_title",
    "locator",
    "segment_id",
    "original_text",
    "source_text_hash",
)

IMMUTABLE_ANNOTATION_FIELDS = (
    "annotation_id",
    "dataset_id",
    "schema_version",
    "source_id",
    "book_id",
    "locator",
    "segment_id",
    "original_text",
    "source_text_hash",
)

OUTPUT_COLLECTIONS = (
    "entities",
    "statuses",
    "relations",
    "appointments",
    "isnads",
    "events",
)

ANNOTATION_STATUSES = (
    "PENDING_PREANNOTATION",
    "PENDING_HUMAN_REVIEW",
    "NEEDS_ADJUDICATION",
    "GOLD_ACCEPTED",
    "REJECTED_SOURCE",
)

REVIEW_DECISIONS = (
    "ACCEPT",
    "EDIT",
    "ABSTAIN",
    "ESCALATE",
)

METRICS = {
    "route_accuracy": {
        "kind": "exact",
        "required": True,
    },
    "entity_precision": {
        "kind": "set",
        "required": True,
    },
    "entity_recall": {
        "kind": "set",
        "required": True,
    },
    "entity_f1": {
        "kind": "harmonic_mean",
        "required": True,
    },
    "semantic_item_precision": {
        "kind": "set",
        "required": True,
    },
    "semantic_item_recall": {
        "kind": "set",
        "required": True,
    },
    "semantic_item_f1": {
        "kind": "harmonic_mean",
        "required": True,
    },
    "evidence_exact_match": {
        "kind": "span_exact",
        "required": True,
    },
    "evidence_overlap_f1": {
        "kind": "span_overlap",
        "required": True,
    },
    "abstention_accuracy": {
        "kind": "exact",
        "required": True,
    },
    "hallucination_rate": {
        "kind": "error_rate",
        "required": True,
    },
    "malformed_output_rate": {
        "kind": "error_rate",
        "required": True,
    },
    "latency_ms": {
        "kind": "operational",
        "required": True,
    },
    "input_tokens": {
        "kind": "operational",
        "required": True,
    },
    "output_tokens": {
        "kind": "operational",
        "required": True,
    },
    "estimated_cost_usd": {
        "kind": "operational",
        "required": True,
    },
}

QUALITY_GATES = {
    "dataset_contract_valid": True,
    "sample_count": DATASET_SIZE,
    "literal_evidence_required": True,
    "provenance_complete": True,
    "gold_provider_output_separation": True,
    "malformed_output_rate_max": 0.0,
    "critical_hallucination_count_max": 0,
    "unclassified_failure_count_max": 0,
    "all_cases_human_reviewed": True,
}

FAILURE_TAXONOMY = (
    "ROUTE_ERROR",
    "ENTITY_BOUNDARY_ERROR",
    "ENTITY_TYPE_ERROR",
    "RELATION_ERROR",
    "STATUS_ERROR",
    "APPOINTMENT_ERROR",
    "ISNAD_ERROR",
    "EVENT_ERROR",
    "EVIDENCE_ERROR",
    "COREFERENCE_ERROR",
    "ABSTENTION_ERROR",
    "HALLUCINATION",
    "MALFORMED_OUTPUT",
    "SOURCE_AMBIGUITY",
    "ANNOTATION_ERROR",
    "SCHEMA_ERROR",
    "PROVIDER_ERROR",
)

PROHIBITED_GOLD_FIELDS = (
    "provider_output",
    "raw_provider_response",
    "model_answer",
    "provider_metadata",
)


def build_contract() -> dict[str, Any]:
    """Return a defensive copy of the complete Gold-20 contract."""
    return deepcopy(
        {
            "dataset_id": DATASET_ID,
            "schema_version": GOLD_SCHEMA_VERSION,
            "evaluation_schema_version": EVALUATION_SCHEMA_VERSION,
            "sample_count": DATASET_SIZE,
            "routes": list(ROUTES),
            "route_quotas": dict(ROUTE_QUOTAS),
            "difficulty_quotas": dict(DIFFICULTY_QUOTAS),
            "required_provenance_fields": list(
                REQUIRED_PROVENANCE_FIELDS
            ),
            "immutable_annotation_fields": list(
                IMMUTABLE_ANNOTATION_FIELDS
            ),
            "output_collections": list(OUTPUT_COLLECTIONS),
            "annotation_statuses": list(ANNOTATION_STATUSES),
            "review_decisions": list(REVIEW_DECISIONS),
            "metrics": deepcopy(METRICS),
            "quality_gates": deepcopy(QUALITY_GATES),
            "failure_taxonomy": list(FAILURE_TAXONOMY),
            "prohibited_gold_fields": list(
                PROHIBITED_GOLD_FIELDS
            ),
            "annotation_policy": {
                "preannotation_allowed": True,
                "human_review_required": True,
                "second_review": (
                    "ALL_AMBIGUOUS_AND_TEN_PERCENT_CLEAR"
                ),
                "adjudication_required_for_disagreement": True,
                "literal_evidence_only": True,
                "inference_requires_explicit_flag": True,
                "provider_output_is_not_gold": True,
            },
        }
    )


def validate_contract(
    contract: dict[str, Any],
) -> list[str]:
    """Return stable validation errors; an empty list means valid."""
    errors: list[str] = []

    if contract.get("dataset_id") != DATASET_ID:
        errors.append("DATASET_ID_MISMATCH")

    if contract.get("schema_version") != GOLD_SCHEMA_VERSION:
        errors.append("GOLD_SCHEMA_VERSION_MISMATCH")

    if (
        contract.get("evaluation_schema_version")
        != EVALUATION_SCHEMA_VERSION
    ):
        errors.append("EVALUATION_SCHEMA_VERSION_MISMATCH")

    if contract.get("sample_count") != DATASET_SIZE:
        errors.append("SAMPLE_COUNT_MISMATCH")

    routes = tuple(contract.get("routes", ()))

    if routes != ROUTES:
        errors.append("ROUTES_MISMATCH")

    route_quotas = contract.get("route_quotas", {})

    if route_quotas != ROUTE_QUOTAS:
        errors.append("ROUTE_QUOTAS_MISMATCH")

    if sum(route_quotas.values()) != DATASET_SIZE:
        errors.append("ROUTE_QUOTA_TOTAL_MISMATCH")

    difficulty_quotas = contract.get(
        "difficulty_quotas",
        {},
    )

    if difficulty_quotas != DIFFICULTY_QUOTAS:
        errors.append("DIFFICULTY_QUOTAS_MISMATCH")

    if sum(difficulty_quotas.values()) != DATASET_SIZE:
        errors.append("DIFFICULTY_QUOTA_TOTAL_MISMATCH")

    required_provenance = set(
        contract.get("required_provenance_fields", ())
    )

    if required_provenance != set(
        REQUIRED_PROVENANCE_FIELDS
    ):
        errors.append("PROVENANCE_FIELDS_MISMATCH")

    metrics = contract.get("metrics", {})

    if set(metrics) != set(METRICS):
        errors.append("METRICS_MISMATCH")

    quality_gates = contract.get("quality_gates", {})

    if quality_gates != QUALITY_GATES:
        errors.append("QUALITY_GATES_MISMATCH")

    prohibited = set(
        contract.get("prohibited_gold_fields", ())
    )

    if prohibited != set(PROHIBITED_GOLD_FIELDS):
        errors.append("PROHIBITED_FIELDS_MISMATCH")

    policy = contract.get("annotation_policy", {})

    if policy.get("provider_output_is_not_gold") is not True:
        errors.append("GOLD_PROVIDER_SEPARATION_REQUIRED")

    if policy.get("literal_evidence_only") is not True:
        errors.append("LITERAL_EVIDENCE_REQUIRED")

    if policy.get("human_review_required") is not True:
        errors.append("HUMAN_REVIEW_REQUIRED")

    return sorted(set(errors))


def validate_annotation_shell(
    annotation: dict[str, Any],
) -> list[str]:
    """Validate fields that must exist before human annotation."""
    errors: list[str] = []

    for field in REQUIRED_PROVENANCE_FIELDS:
        value = annotation.get(field)

        if value is None or value == "":
            errors.append(
                f"MISSING_PROVENANCE:{field}"
            )

    for field in PROHIBITED_GOLD_FIELDS:
        if field in annotation:
            errors.append(
                f"PROHIBITED_GOLD_FIELD:{field}"
            )

    status = annotation.get("status")

    if status not in ANNOTATION_STATUSES:
        errors.append("INVALID_ANNOTATION_STATUS")

    route = annotation.get("route")

    if route not in ROUTES:
        errors.append("INVALID_ROUTE")

    return sorted(set(errors))


__all__ = [
    "ANNOTATION_STATUSES",
    "DATASET_ID",
    "DATASET_SIZE",
    "DIFFICULTY_QUOTAS",
    "EVALUATION_SCHEMA_VERSION",
    "FAILURE_TAXONOMY",
    "GOLD_SCHEMA_VERSION",
    "IMMUTABLE_ANNOTATION_FIELDS",
    "METRICS",
    "OUTPUT_COLLECTIONS",
    "PROHIBITED_GOLD_FIELDS",
    "QUALITY_GATES",
    "REQUIRED_PROVENANCE_FIELDS",
    "REVIEW_DECISIONS",
    "ROUTES",
    "ROUTE_QUOTAS",
    "build_contract",
    "validate_annotation_shell",
    "validate_contract",
]