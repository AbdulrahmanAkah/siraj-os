def test_metadata_query_matches_all_requested_fields(repository_query_engine):
    result = repository_query_engine.query_by_metadata({"title": "Example"})

    assert result.match_count > 0
    assert all(record.metadata["title"] == "Example" for record in result.matched_records)


def test_metadata_query_requires_exact_values(repository_query_engine):
    result = repository_query_engine.query_by_metadata({"title": "Missing"})

    assert result.match_count == 0
