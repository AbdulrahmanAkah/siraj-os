def test_ingestion_runtime_executes_local_payloads(
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
):
    result = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        ingestion_payloads,
    )

    assert result.source_ingestion_plan_id == source_ingestion_plan.plan_id
    assert result.processed_count == len(
        [
            unit
            for batch in source_ingestion_plan.batches
            for unit in batch.units
        ]
    )
    assert result.accepted_count + result.duplicate_count == result.processed_count
    assert result.rejected_count == 0
    assert result.rejected_count == 0
    assert len(result.validation_results) == result.processed_count


def test_runtime_payload_fixture_uses_target_ids(source_ingestion_plan, ingestion_payloads):
    target_ids = {
        unit.acquisition_target_id
        for batch in source_ingestion_plan.batches
        for unit in batch.units
    }
    assert set(ingestion_payloads) == target_ids
