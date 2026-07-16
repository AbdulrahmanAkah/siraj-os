def test_snapshot_retrieval_uses_explicit_snapshot(
    repository_query_engine,
    retrieval_index_builder,
    retrieval_runtime_engine,
):
    snapshot = repository_query_engine.knowledge_repository.build_snapshot()
    index = retrieval_index_builder.build_retrieval_index(snapshot)
    result = retrieval_runtime_engine.retrieve_by_media_type(
        "image/jpeg",
        index,
    )

    assert index.snapshot_id == snapshot.snapshot_id
    assert result.match_count == snapshot.record_count
