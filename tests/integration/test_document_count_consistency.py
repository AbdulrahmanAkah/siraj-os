def test_document_count_matches_created_documents(repository_ingestion_result):
    assert repository_ingestion_result.document_count == len(
        repository_ingestion_result.created_documents
    )
    assert repository_ingestion_result.document_count + len(
        repository_ingestion_result.skipped_duplicates
    ) + len(repository_ingestion_result.failed_documents) == 7
