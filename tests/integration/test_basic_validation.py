from src.application.source_ingestion_runtime.models import IngestionPayload


def test_basic_validation_allows_empty_payload_content_and_media(
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
):
    basic_unit = next(
        unit
        for batch in source_ingestion_plan.batches
        for unit in batch.units
        if unit.validation_level == "BASIC"
    )
    payloads = dict(ingestion_payloads)
    payloads[basic_unit.acquisition_target_id] = IngestionPayload(
        target_id=basic_unit.acquisition_target_id,
        content_bytes=b"",
        media_type="",
        metadata={},
    )

    result = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        payloads,
    )
    validation = next(
        item for item in result.validation_results if item.unit_id == basic_unit.unit_id
    )

    assert validation.is_valid
