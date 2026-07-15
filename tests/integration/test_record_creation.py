def test_record_creation_preserves_document_fields(
    knowledge_repository,
    repository_ingestion_result,
):
    document = repository_ingestion_result.created_documents[0]
    record = knowledge_repository.create_knowledge_record(document)

    assert record.document_id == document.document_id
    assert record.fingerprint == document.fingerprint
    assert record.media_type == document.media_type
    assert record.metadata == document.metadata
    assert record.created_at == document.ingested_at
