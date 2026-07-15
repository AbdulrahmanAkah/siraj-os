def test_duplicate_detection_points_to_first_accepted_unit(
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
    assert len(sha_units) >= 2
    payloads = dict(ingestion_payloads)
    first, second = sha_units[:2]
    payloads[first.acquisition_target_id] = payloads[second.acquisition_target_id]
    payloads[first.acquisition_target_id] = type(payloads[first.acquisition_target_id])(
        target_id=first.acquisition_target_id,
        content_bytes=b"same-content",
        media_type="image/jpeg",
        metadata={"title": "Same"},
    )
    payloads[second.acquisition_target_id] = type(payloads[second.acquisition_target_id])(
        target_id=second.acquisition_target_id,
        content_bytes=b"same-content",
        media_type="image/jpeg",
        metadata={"title": "Same"},
    )

    result = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        payloads,
    )
    duplicate = next(
        item
        for item in result.deduplication_results
        if item.unit_id == second.unit_id
    )

    assert duplicate.is_duplicate
    assert duplicate.duplicate_of_unit_id == first.unit_id
