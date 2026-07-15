def test_media_type_retrieval_is_exact(retrieval_runtime_engine, retrieval_index):
    result = retrieval_runtime_engine.retrieve_by_media_type(
        "image/jpeg",
        retrieval_index,
    )

    assert result.match_count == len(retrieval_index.records_by_id)
    assert all(match.record.media_type == "image/jpeg" for match in result.matches)
