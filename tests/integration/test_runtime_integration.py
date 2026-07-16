def test_runtime_result_flows_into_repository_ingestion(
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
    repository_ingestion_engine,
):
    execution = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        ingestion_payloads,
    )
    repository_result = repository_ingestion_engine.ingest_execution_result(
        execution
    )

    assert repository_result.execution_id == execution.execution_id
    assert repository_result.document_count == execution.accepted_count
