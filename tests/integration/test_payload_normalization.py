def test_payload_normalization_preserves_bytes_and_normalizes_text(
    source_ingestion_executor,
    source_ingestion_plan,
    ingestion_payloads,
):
    result = source_ingestion_executor.execute_ingestion(
        source_ingestion_plan,
        ingestion_payloads,
    )

    assert all(payload.normalized_bytes for payload in result.normalized_payloads)
    assert all(
        payload.normalized_media_type == "image/jpeg"
        for payload in result.normalized_payloads
    )
    assert all(
        payload.normalized_metadata == {"title": "Example"}
        for payload in result.normalized_payloads
    )
