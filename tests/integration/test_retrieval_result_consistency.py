def test_retrieval_result_count_and_ordering(
    retrieval_runtime_engine,
    retrieval_index,
):
    result = retrieval_runtime_engine.retrieve_by_media_type(
        "image/jpeg",
        retrieval_index,
    )
    result_ids = [match.record_id for match in result.matches]

    assert result.match_count == len(result.matches)
    assert len(result_ids) == len(set(result_ids))
    assert result_ids == sorted(result_ids)
