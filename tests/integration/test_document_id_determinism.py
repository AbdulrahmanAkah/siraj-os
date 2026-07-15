def test_document_ids_are_deterministic(
    repository_ingestion_engine,
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
):
    first_execution = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        ingestion_payloads,
    )
    second_execution = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        dict(reversed(list(ingestion_payloads.items()))),
    )
    first = repository_ingestion_engine.ingest_execution_result(first_execution)
    second = repository_ingestion_engine.ingest_execution_result(second_execution)

    assert [item.document_id for item in first.created_documents] == [
        item.document_id for item in second.created_documents
    ]
    assert first.result_id == second.result_id
