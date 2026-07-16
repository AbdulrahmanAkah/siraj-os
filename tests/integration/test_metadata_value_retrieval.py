def test_metadata_value_retrieval(retrieval_runtime_engine, retrieval_index):
    result = retrieval_runtime_engine.retrieve_by_metadata_value(
        "Example",
        retrieval_index,
    )

    assert result.match_count == len(retrieval_index.records_by_id)
    assert all(match.record.metadata["title"] == "Example" for match in result.matches)
