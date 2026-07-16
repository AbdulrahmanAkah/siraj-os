def test_repository_integration_success_path(
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
    repository_ingestion_engine,
    knowledge_repository,
):
    execution = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        ingestion_payloads,
    )
    repository_result = repository_ingestion_engine.ingest_execution_result(
        execution
    )
    load_result = knowledge_repository.load_repository_documents(
        repository_result.created_documents
    )
    snapshot = knowledge_repository.build_snapshot()

    assert load_result.record_count == repository_result.document_count
    assert snapshot.record_count == load_result.record_count
    assert knowledge_repository.validate_repository(snapshot)
