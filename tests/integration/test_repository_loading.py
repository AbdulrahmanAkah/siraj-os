def test_repository_loading_creates_one_record_per_new_document(
    knowledge_repository,
    repository_ingestion_result,
):
    result = knowledge_repository.load_repository_documents(
        repository_ingestion_result.created_documents
    )

    assert result.record_count == len(repository_ingestion_result.created_documents)
    assert len(result.created_records) == result.record_count
    assert result.skipped_records == []
