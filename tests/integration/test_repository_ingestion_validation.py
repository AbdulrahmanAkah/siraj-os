from dataclasses import replace


def test_repository_ingestion_validation_accepts_valid_result(
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

    assert repository_ingestion_engine.validate_repository_ingestion(
        execution,
        result,
    )


def test_repository_ingestion_validation_rejects_inconsistent_count(
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
    invalid_result = replace(result, document_count=result.document_count + 1)

    assert not repository_ingestion_engine.validate_repository_ingestion(
        execution,
        invalid_result,
    )
