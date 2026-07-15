def test_missing_payload_produces_only_invalid_validation(
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
):
    missing_target_id = next(iter(ingestion_payloads))
    payloads = dict(ingestion_payloads)
    payloads.pop(missing_target_id)
    missing_unit = next(
        unit
        for batch in source_ingestion_plan.batches
        for unit in batch.units
        if unit.acquisition_target_id == missing_target_id
    )

    result = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        payloads,
    )

    assert not next(
        item for item in result.validation_results if item.unit_id == missing_unit.unit_id
    ).is_valid
    assert "MISSING_PAYLOAD" in next(
        item for item in result.validation_results if item.unit_id == missing_unit.unit_id
    ).errors
    assert all(
        item.unit_id != missing_unit.unit_id for item in result.normalized_payloads
    )
    assert all(item.unit_id != missing_unit.unit_id for item in result.fingerprints)
    assert all(
        item.unit_id != missing_unit.unit_id
        for item in result.deduplication_results
    )
