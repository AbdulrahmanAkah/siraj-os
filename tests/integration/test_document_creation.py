from hashlib import sha256


def test_document_creation_uses_unit_and_fingerprint(
    repository_ingestion_result,
):
    document = repository_ingestion_result.created_documents[0]
    key = "\x00".join([document.source_unit_id, document.fingerprint])
    expected = f"repository_document_{sha256(key.encode('utf-8')).hexdigest()[:16]}"
    assert document.document_id == expected
