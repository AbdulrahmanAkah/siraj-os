from copy import deepcopy

from src.application.local_semantic_intelligence.gold_20_contract import (
    DATASET_ID,
    DATASET_SIZE,
    DIFFICULTY_QUOTAS,
    GOLD_SCHEMA_VERSION,
    METRICS,
    PROHIBITED_GOLD_FIELDS,
    ROUTES,
    ROUTE_QUOTAS,
    build_contract,
    validate_annotation_shell,
    validate_contract,
)


def test_gold_20_contract_is_complete_and_valid() -> None:
    contract = build_contract()

    assert contract["dataset_id"] == DATASET_ID
    assert contract["schema_version"] == GOLD_SCHEMA_VERSION
    assert contract["sample_count"] == DATASET_SIZE
    assert validate_contract(contract) == []


def test_sampling_contract_has_exact_twenty_cases() -> None:
    assert tuple(ROUTE_QUOTAS) == ROUTES
    assert sum(ROUTE_QUOTAS.values()) == DATASET_SIZE
    assert sum(DIFFICULTY_QUOTAS.values()) == DATASET_SIZE
    assert all(value > 0 for value in ROUTE_QUOTAS.values())


def test_metrics_cover_quality_and_operations() -> None:
    required = {
        "route_accuracy",
        "entity_f1",
        "semantic_item_f1",
        "evidence_exact_match",
        "evidence_overlap_f1",
        "abstention_accuracy",
        "hallucination_rate",
        "malformed_output_rate",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "estimated_cost_usd",
    }

    assert required <= set(METRICS)


def test_contract_rejects_provider_output_as_gold() -> None:
    shell = {
        "annotation_id": "gold-20-001",
        "dataset_id": DATASET_ID,
        "schema_version": GOLD_SCHEMA_VERSION,
        "source_id": "source-1",
        "book_id": 1,
        "book_title": "Book",
        "locator": "siraj://book/1/segment/1",
        "segment_id": 1,
        "original_text": "نص تاريخي",
        "source_text_hash": "abc",
        "route": "PERSON_AND_STATUS",
        "status": "PENDING_HUMAN_REVIEW",
        "provider_output": {},
    }

    errors = validate_annotation_shell(shell)

    assert (
        "PROHIBITED_GOLD_FIELD:provider_output"
        in errors
    )


def test_contract_validation_detects_mutation() -> None:
    contract = deepcopy(build_contract())
    contract["sample_count"] = 19
    contract["route_quotas"]["PERSON_AND_STATUS"] = 4

    errors = validate_contract(contract)

    assert "SAMPLE_COUNT_MISMATCH" in errors
    assert "ROUTE_QUOTAS_MISMATCH" in errors
    assert "ROUTE_QUOTA_TOTAL_MISMATCH" in errors


def test_all_prohibited_fields_are_enforced() -> None:
    base = {
        "annotation_id": "gold-20-001",
        "dataset_id": DATASET_ID,
        "schema_version": GOLD_SCHEMA_VERSION,
        "source_id": "source-1",
        "book_id": 1,
        "book_title": "Book",
        "locator": "siraj://book/1/segment/1",
        "segment_id": 1,
        "original_text": "نص تاريخي",
        "source_text_hash": "abc",
        "route": "PERSON_AND_STATUS",
        "status": "PENDING_HUMAN_REVIEW",
    }

    for field in PROHIBITED_GOLD_FIELDS:
        shell = {**base, field: {}}

        assert (
            f"PROHIBITED_GOLD_FIELD:{field}"
            in validate_annotation_shell(shell)
        )