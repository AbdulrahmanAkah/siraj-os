def test_media_type_query_matches_exact_media_type(
    repository_query_engine,
):
    result = repository_query_engine.query_by_media_type("image/jpeg")

    assert result.match_count > 0
    assert all(record.media_type == "image/jpeg" for record in result.matched_records)
