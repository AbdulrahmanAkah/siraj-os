def test_repository_ingestion_creates_documents_from_runtime_result(
    repository_ingestion_result,
):
    assert repository_ingestion_result.execution_id
    assert repository_ingestion_result.document_count == len(
        repository_ingestion_result.created_documents
    )
    assert repository_ingestion_result.document_count > 0


def test_repository_documents_are_repository_ready(repository_ingestion_result):
    for document in repository_ingestion_result.created_documents:
        assert document.document_id.startswith("repository_document_")
        assert document.source_unit_id
        assert document.fingerprint
        assert document.media_type == "image/jpeg"
        assert document.metadata == {"title": "Example"}
        assert document.ingested_at == repository_ingestion_result.execution_id
