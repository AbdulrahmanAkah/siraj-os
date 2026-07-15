def test_fingerprint_query_matches_exact_records(
    repository_query_engine,
    repository_ingestion_result,
):
    fingerprint = repository_ingestion_result.created_documents[0].fingerprint
    result = repository_query_engine.query_by_fingerprint(fingerprint)

    assert result.match_count == 1
    assert result.matched_records[0].fingerprint == fingerprint
