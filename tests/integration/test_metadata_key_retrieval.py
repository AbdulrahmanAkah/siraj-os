def test_metadata_key_retrieval(retrieval_runtime_engine, retrieval_index):
    result = retrieval_runtime_engine.retrieve_by_metadata_key(
        "title",
        retrieval_index,
    )

    assert result.match_count == len(retrieval_index.records_by_id)
    assert all("title" in match.record.metadata for match in result.matches)
