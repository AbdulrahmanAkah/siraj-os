from src.application.source_ingestion_runtime.models import IngestionPayload


def test_strict_validation_rejects_empty_content(
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
):
    strict_unit = next(
        unit
        for batch in source_ingestion_plan.batches
        for unit in batch.units
        if unit.validation_level == "STRICT"
    )
    payloads = dict(ingestion_payloads)
    payloads[strict_unit.acquisition_target_id] = IngestionPayload(
        target_id=strict_unit.acquisition_target_id,
        content_bytes=b"",
        media_type="image/jpeg",
        metadata={"title": "Example"},
    )

    result = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        payloads,
    )
    validation = next(
        item for item in result.validation_results if item.unit_id == strict_unit.unit_id
    )

    assert not validation.is_valid
    assert "EMPTY_CONTENT" in validation.errors
