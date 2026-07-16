def test_fingerprint_retrieval_is_exact(
    retrieval_runtime_engine,
    retrieval_index,
):
    fingerprint = next(iter(retrieval_index.fingerprint_index))
    result = retrieval_runtime_engine.retrieve_by_fingerprint(
        fingerprint,
        retrieval_index,
    )

    assert result.match_count == 1
    assert result.matches[0].record.fingerprint == fingerprint
