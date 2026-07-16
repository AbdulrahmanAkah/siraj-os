def test_query_result_count_matches_records(repository_query_engine):
    result = repository_query_engine.query_by_media_type("image/jpeg")

    assert result.match_count == len(result.matched_records)
    assert len({record.record_id for record in result.matched_records}) == result.match_count
