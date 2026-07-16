def test_duplicate_fingerprints_are_skipped(
    knowledge_repository,
    repository_ingestion_result,
):
    documents = repository_ingestion_result.created_documents
    first = knowledge_repository.load_repository_documents(documents)
    second = knowledge_repository.load_repository_documents(documents)

    assert first.record_count == len(documents)
    assert second.created_records == []
    assert second.skipped_records == [document.document_id for document in documents]
    assert knowledge_repository.build_snapshot().record_count == len(documents)
