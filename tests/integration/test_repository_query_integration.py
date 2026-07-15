def test_repository_query_integrates_with_knowledge_repository(
    repository_query_engine,
    repository_ingestion_result,
):
    fingerprint = repository_ingestion_result.created_documents[0].fingerprint
    result = repository_query_engine.query_by_fingerprint([fingerprint])

    assert result.matched_records
    assert result.matched_records[0].fingerprint == fingerprint
