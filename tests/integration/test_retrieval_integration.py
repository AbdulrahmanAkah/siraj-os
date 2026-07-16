def test_query_engine_index_runtime_integration(
    repository_query_engine,
    retrieval_index_builder,
    retrieval_runtime_engine,
    retrieval_index,
):
    query_result = repository_query_engine.query_by_media_type("image/jpeg")
    built_index = retrieval_index_builder.build_retrieval_index(query_result)
    runtime_result = retrieval_runtime_engine.retrieve_by_media_type(
        "image/jpeg",
        built_index,
    )

    assert runtime_result.match_count == query_result.match_count
    assert [match.record_id for match in runtime_result.matches] == [
        record.record_id for record in retrieval_index.records_by_id.values()
    ]
