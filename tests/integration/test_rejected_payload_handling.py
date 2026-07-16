def test_rejected_payloads_are_recorded_and_not_created(
    repository_ingestion_engine,
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
):
    missing_target_id = next(iter(ingestion_payloads))
    payloads = dict(ingestion_payloads)
    payloads.pop(missing_target_id)
    execution = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        payloads,
    )
    result = repository_ingestion_engine.ingest_execution_result(execution)

    rejected_unit_id = next(
        item.unit_id
        for item in execution.validation_results
        if "MISSING_PAYLOAD" in item.errors
    )
    assert result.failed_documents == [rejected_unit_id]
    assert rejected_unit_id not in {
        item.source_unit_id for item in result.created_documents
    }
