def test_duplicate_payloads_are_recorded_and_not_created(
    repository_ingestion_engine,
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
):
    execution = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        ingestion_payloads,
    )
    result = repository_ingestion_engine.ingest_execution_result(execution)
    duplicate_ids = [
        item.unit_id
        for item in execution.deduplication_results
        if item.is_duplicate
    ]
    created_ids = {item.source_unit_id for item in result.created_documents}

    assert result.skipped_duplicates == duplicate_ids
    assert not created_ids.intersection(duplicate_ids)
