def test_index_building_is_deterministic(retrieval_index_builder):
    first = retrieval_index_builder.build_retrieval_index()
    second = retrieval_index_builder.build_retrieval_index()

    assert first == second
    assert first.index_id == second.index_id
