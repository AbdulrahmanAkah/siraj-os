from src.application.source_ingestion_runtime.models import IngestionPayload


def test_standard_validation_rejects_empty_media_type(
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
):
    standard_unit = next(
        unit
        for batch in source_ingestion_plan.batches
        for unit in batch.units
        if unit.validation_level == "STANDARD"
    )
    payloads = dict(ingestion_payloads)
    payloads[standard_unit.acquisition_target_id] = IngestionPayload(
        target_id=standard_unit.acquisition_target_id,
        content_bytes=b"content",
        media_type="",
        metadata={"title": "Example"},
    )

    result = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        payloads,
    )
    validation = next(
        item
        for item in result.validation_results
        if item.unit_id == standard_unit.unit_id
    )

    assert not validation.is_valid
    assert "EMPTY_MEDIA_TYPE" in validation.errors
