def test_execution_counters_partition_processed_units(
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
):
    sha_units = [
        unit
        for batch in source_ingestion_plan.batches
        for unit in batch.units
        if unit.fingerprint_strategy == "SHA256_FINGERPRINT"
    ]
    payloads = dict(ingestion_payloads)
    payloads[sha_units[0].acquisition_target_id] = type(next(iter(payloads.values())))(
        target_id=sha_units[0].acquisition_target_id,
        content_bytes=b"counter-content",
        media_type="image/jpeg",
        metadata={"title": "Same"},
    )
    payloads[sha_units[1].acquisition_target_id] = type(next(iter(payloads.values())))(
        target_id=sha_units[1].acquisition_target_id,
        content_bytes=b"counter-content",
        media_type="image/jpeg",
        metadata={"title": "Same"},
    )
    payloads.pop(next(iter(payloads)))

    result = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        payloads,
    )

    assert result.processed_count == result.accepted_count + result.rejected_count + result.duplicate_count
    assert result.duplicate_count >= 1
    assert result.rejected_count >= 1
